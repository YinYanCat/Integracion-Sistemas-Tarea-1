
import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("STOCK_DB_PATH", "/data/stock.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS medicamentos (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    unidades_disponibles INTEGER NOT NULL CHECK (unidades_disponibles >= 0)
);

CREATE TABLE IF NOT EXISTS movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_medicamento TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('descuento', 'reposicion')),
    cantidad INTEGER NOT NULL,
    id_dispensacion TEXT,
    fecha TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (codigo_medicamento) REFERENCES medicamentos(codigo)
);
"""

# Datos semilla minimos para poder probar el sistema end-to-end
SEED = [
    ("MED-1", "Paracetamol 500mg", 50),
    ("MED-2", "Ibuprofeno 400mg", 30),
    ("MED-3", "Amoxicilina 500mg", 0),   # a proposito en 0, para probar el caso "sin stock"
    ("MED-4", "Loratadina 10mg", 15),
]


def _ensure_dir():
    directorio = os.path.dirname(DB_PATH)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio, exist_ok=True)


def init_db():
    """Crea el esquema y carga datos semilla si la tabla esta vacia."""
    _ensure_dir()
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        cur = conn.execute("SELECT COUNT(*) FROM medicamentos")
        if cur.fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO medicamentos (codigo, nombre, unidades_disponibles) VALUES (?, ?, ?)",
                SEED,
            )
        conn.commit()


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # mejor concurrencia lectura/escritura
    try:
        yield conn
    finally:
        conn.close()


def obtener_medicamento(conn, codigo: str):
    cur = conn.execute(
        "SELECT codigo, nombre, unidades_disponibles FROM medicamentos WHERE codigo = ?",
        (codigo,),
    )
    return cur.fetchone()


def listar_medicamentos(conn, offset: int, limit: int):
    cur = conn.execute(
        "SELECT codigo, nombre, unidades_disponibles FROM medicamentos "
        "ORDER BY codigo LIMIT ? OFFSET ?",
        (limit, offset),
    )
    items = cur.fetchall()
    total = conn.execute("SELECT COUNT(*) FROM medicamentos").fetchone()[0]
    return items, total


def descontar_unidades(conn, codigo: str, cantidad: int, id_dispensacion: str):
    
    med = obtener_medicamento(conn, codigo)
    if med is None:
        return False, 0, f"medicamento '{codigo}' no existe"

    cur = conn.execute(
        "UPDATE medicamentos SET unidades_disponibles = unidades_disponibles - ? "
        "WHERE codigo = ? AND unidades_disponibles >= ?",
        (cantidad, codigo, cantidad),
    )
    if cur.rowcount == 0:
        return False, med["unidades_disponibles"], "stock insuficiente"

    conn.execute(
        "INSERT INTO movimientos (codigo_medicamento, tipo, cantidad, id_dispensacion) "
        "VALUES (?, 'descuento', ?, ?)",
        (codigo, cantidad, id_dispensacion),
    )
    conn.commit()
    nuevo = obtener_medicamento(conn, codigo)
    return True, nuevo["unidades_disponibles"], "ok"


def reponer_unidades(conn, codigo: str, cantidad: int, id_dispensacion: str):
    """Repone unidades (revertir una dispensación previa)."""
    med = obtener_medicamento(conn, codigo)
    if med is None:
        return False, 0, f"medicamento '{codigo}' no existe"

    conn.execute(
        "UPDATE medicamentos SET unidades_disponibles = unidades_disponibles + ? "
        "WHERE codigo = ?",
        (cantidad, codigo),
    )
    conn.execute(
        "INSERT INTO movimientos (codigo_medicamento, tipo, cantidad, id_dispensacion) "
        "VALUES (?, 'reposicion', ?, ?)",
        (codigo, cantidad, id_dispensacion),
    )
    conn.commit()
    nuevo = obtener_medicamento(conn, codigo)
    return True, nuevo["unidades_disponibles"], "ok"
