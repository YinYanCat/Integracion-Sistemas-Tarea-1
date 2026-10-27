"""
Uso:
    python medir_cache_disponibilidad.py --iteraciones 100 --output-csv resultados_cache.csv
"""

import argparse
import csv
import statistics
import sys
import time
from datetime import datetime

import requests

try:
    import redis
except ImportError:
    redis = None

BASE_URL_DEFAULT = "http://localhost:8000/v1"
API_KEY_DEFAULT = "clave-dev-123"
REDIS_URL_DEFAULT = "redis://localhost:6379/0"


def percentil(valores, p):
    valores = sorted(valores)
    if not valores:
        return None
    k = (len(valores) - 1) * (p / 100)
    f, c = int(k), min(int(k) + 1, len(valores) - 1)
    if f == c:
        return valores[f]
    return valores[f] + (valores[c] - valores[f]) * (k - f)


def resumen(nombre, tiempos_ms):
    if not tiempos_ms:
        print(f"{nombre}: sin muestras")
        return None
    fila = {
        "n": len(tiempos_ms),
        "promedio_ms": round(statistics.mean(tiempos_ms), 2),
        "mediana_ms": round(statistics.median(tiempos_ms), 2),
        "stdev_ms": round(statistics.stdev(tiempos_ms), 2) if len(tiempos_ms) > 1 else 0.0,
        "min_ms": round(min(tiempos_ms), 2),
        "max_ms": round(max(tiempos_ms), 2),
        "p95_ms": round(percentil(tiempos_ms, 95), 2),
    }
    print(f"\n{nombre}")
    print(f"  n={fila['n']}")
    print(f"  promedio={fila['promedio_ms']} ms  mediana={fila['mediana_ms']} ms  "
          f"stdev={fila['stdev_ms']} ms")
    print(f"  min={fila['min_ms']} ms  max={fila['max_ms']} ms  p95={fila['p95_ms']} ms")
    return fila


def guardar_registros_csv(filepath, registros):
    """Guarda cada request realizada en un archivo CSV."""
    encabezados = [
        "timestamp",
        "iteracion",
        "es_warmup",
        "tipo_cache",
        "medicamento",
        "status_code",
        "tiempo_ms",
    ]
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=encabezados)
        writer.writeheader()
        writer.writerows(registros)
    print(f"\n[+] Datos de requests guardados en: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Compara latencia con cache HIT vs MISS")
    parser.add_argument("--base-url", default=BASE_URL_DEFAULT)
    parser.add_argument("--api-key", default=API_KEY_DEFAULT)
    parser.add_argument("--redis-url", default=REDIS_URL_DEFAULT)
    parser.add_argument("--medicamento", default="MED-1",
                        help="Cualquier código válido sirve, incluso MED-3 (0 stock), "
                             "porque este endpoint no depende de tener unidades")
    parser.add_argument("--iteraciones", type=int, default=500)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--output-csv", default="resultados_cache.csv",
                        help="Ruta del archivo CSV para exportar las métricas de cada request")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"X-API-Key": args.api_key})

    if redis is None:
        print("Error: la librería 'redis' no está instalada.")
        sys.exit(1)

    try:
        cache = redis.Redis.from_url(args.redis_url, socket_connect_timeout=2)
        cache.ping()
    except redis.RedisError as exc:
        print(f"Error conectando a Redis: {exc}")
        sys.exit(1)

    clave_cache = f"stock:{args.medicamento}"
    url = f"{args.base_url}/medicamentos/{args.medicamento}"

    tiempos_miss, tiempos_hit = [], []
    registros_csv = []
    total = args.warmup + args.iteraciones

    for i in range(total):
        medido = i >= args.warmup
        es_warmup = not medido

        # --- Forzar MISS ---
        cache.delete(clave_cache)
        ts_miss = datetime.now().isoformat()
        t0 = time.perf_counter()
        r1 = session.get(url)
        t1 = time.perf_counter()
        duracion_miss_ms = (t1 - t0) * 1000

        registros_csv.append({
            "timestamp": ts_miss,
            "iteracion": i,
            "es_warmup": es_warmup,
            "tipo_cache": "MISS",
            "medicamento": args.medicamento,
            "status_code": r1.status_code,
            "tiempo_ms": round(duracion_miss_ms, 3),
        })

        if r1.status_code != 200:
            print(f"  iter {i} (MISS): {r1.status_code} {r1.text[:120]}")
            continue

        # --- Debería ser HIT (la request anterior ya la cacheó) ---
        ts_hit = datetime.now().isoformat()
        t2 = time.perf_counter()
        r2 = session.get(url)
        t3 = time.perf_counter()
        duracion_hit_ms = (t3 - t2) * 1000

        registros_csv.append({
            "timestamp": ts_hit,
            "iteracion": i,
            "es_warmup": es_warmup,
            "tipo_cache": "HIT",
            "medicamento": args.medicamento,
            "status_code": r2.status_code,
            "tiempo_ms": round(duracion_hit_ms, 3),
        })

        if r2.status_code != 200:
            print(f"  iter {i} (HIT): {r2.status_code} {r2.text[:120]}")
            continue

        if medido:
            tiempos_miss.append(duracion_miss_ms)
            tiempos_hit.append(duracion_hit_ms)

    # Exportar datos a CSV
    if args.output_csv:
        guardar_registros_csv(args.output_csv, registros_csv)

    print(f"\nMedicamento: {args.medicamento}   (warmup descartado: {args.warmup} iteraciones)")
    fila_miss = resumen("Cache MISS (consulta va hasta gRPC/Stock)", tiempos_miss)
    fila_hit = resumen("Cache HIT (responde desde Redis)", tiempos_hit)

    if fila_miss and fila_hit and fila_hit["promedio_ms"] > 0:
        mejora = (fila_miss["promedio_ms"] - fila_hit["promedio_ms"]) / fila_miss["promedio_ms"] * 100
        veces = fila_miss["promedio_ms"] / fila_hit["promedio_ms"]
        print(f"\n=> La caché reduce la latencia promedio en {mejora:.2f}% "
              f"({veces:.2f}x más rápido) en esta consulta frecuente.")


if __name__ == "__main__":
    main()