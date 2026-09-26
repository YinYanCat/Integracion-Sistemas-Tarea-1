import logging
import sqlite3
import uuid

import grpc
from flask import Flask, request, jsonify
from pydantic import ValidationError

import bd_dispensacion as db
from auth import requiere_api_key, problema
from schemas import NuevoPaciente, NuevaDispensacion
from stock_client import obtener_cliente, StockNoDisponibleError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dispensacion_service")

app = Flask(__name__)

db.init_db()

def _paciente_a_dict(row):
    return {
        "id": row["id"],
        "nombre": row["nombre"],
        "rut": row["rut"],
        "fecha_registro": row["fecha_registro"],
    }

def _dispensacion_a_dict(row):
    return {
        "id": row["id"],
        "paciente_id": row["paciente_id"],
        "codigo_medicamento": row["codigo_medicamento"],
        "nombre_medicamento": row["nombre_medicamento"],
        "cantidad": row["cantidad"],
        "estado": row["estado"],
        "fecha": row["fecha"],
    }

@app.post("/v1/pacientes")
@requiere_api_key
def crear_paciente():
    try:
        cuerpo = NuevoPaciente.model_validate(request.get_json(force=True, silent=True) or {})
    except ValidationError as exc:
        return jsonify(problema(400, "Solicitud invalida", str(exc), request.path)), 400

    with db.get_connection() as conn:
        try:
            paciente = db.crear_paciente(conn, cuerpo.nombre, cuerpo.rut)
        except sqlite3.IntegrityError:
            detalle = f"Ya existe un paciente registrado con el rut '{cuerpo.rut}'"
            cuerpo_error = problema(409, "Rut ya registrado", detalle, request.path)
            return jsonify(cuerpo_error), 409
    return jsonify(_paciente_a_dict(paciente)), 201


@app.get("/v1/pacientes/<id_paciente>")
@requiere_api_key
def obtener_paciente(id_paciente):
    with db.get_connection() as conn:
        paciente = db.obtener_paciente(conn, id_paciente)
    if paciente is None:
        cuerpo = problema(404, "Paciente no encontrado", f"No existe paciente '{id_paciente}'", request.path)
        return jsonify(cuerpo), 404
    return jsonify(_paciente_a_dict(paciente)), 200


@app.get("/v1/pacientes")
@requiere_api_key
def listar_pacientes():
    with db.get_connection() as conn:
        pacientes = db.listar_pacientes(conn)
    return jsonify([_paciente_a_dict(p) for p in pacientes]), 200


@app.get("/v1/medicamentos/<codigo>")
@requiere_api_key
def consultar_disponibilidad(codigo):
    cliente_stock = obtener_cliente()
    try:
        info = cliente_stock.consultar(codigo)
    except StockNoDisponibleError as exc:
        cuerpo_error = problema(503, "Servicio de Stock no disponible", str(exc), request.path)
        return jsonify(cuerpo_error), 503
    except grpc.RpcError as exc:
        if exc.code() == grpc.StatusCode.NOT_FOUND:
            detalle = f"No existe el medicamento '{codigo}'"
            return jsonify(problema(404, "Medicamento no encontrado", detalle, request.path)), 404
        raise

    return jsonify({
        "codigo_medicamento": info.codigo_medicamento,
        "nombre": info.nombre,
        "unidades_disponibles": info.unidades_disponibles,
        "disponible": info.disponible,
    }), 200


@app.post("/v1/dispensaciones")
@requiere_api_key
def crear_dispensacion():
    try:
        cuerpo = NuevaDispensacion.model_validate(request.get_json(force=True, silent=True) or {})
    except ValidationError as exc:
        return jsonify(problema(400, "Solicitud invalida", str(exc), request.path)), 400

    with db.get_connection() as conn:
        if db.obtener_paciente(conn, cuerpo.paciente_id) is None:
            detalle = f"No existe paciente '{cuerpo.paciente_id}'"
            return jsonify(problema(404, "Paciente no encontrado", detalle, request.path)), 404

    id_disp = str(uuid.uuid4())
    cliente_stock = obtener_cliente()

    try:
        resultado = cliente_stock.descontar(
            cuerpo.codigo_medicamento, cuerpo.cantidad, id_disp
        )
    except StockNoDisponibleError as exc:
        cuerpo_error = problema(
            503, "Servicio de Stock no disponible", str(exc), request.path
        )
        return jsonify(cuerpo_error), 503

    if not resultado.exito:
        # insuficiente o no existe
        cuerpo_error = problema(
            409, "No se pudo dispensar", resultado.mensaje, request.path
        )
        return jsonify(cuerpo_error), 409

    try:
        info_medicamento = cliente_stock.consultar(cuerpo.codigo_medicamento)
        nombre_medicamento = info_medicamento.nombre
    except (StockNoDisponibleError, Exception) as exc:
        logger.warning("No se pudo obtener el nombre del medicamento '%s': %s",
                        cuerpo.codigo_medicamento, exc)
        nombre_medicamento = cuerpo.codigo_medicamento

    with db.get_connection() as conn:
        dispensacion = db.crear_dispensacion(
            conn, id_disp, cuerpo.paciente_id, cuerpo.codigo_medicamento,
            nombre_medicamento, cuerpo.cantidad,
        )

    return jsonify(_dispensacion_a_dict(dispensacion)), 201


@app.post("/v1/dispensaciones/<id_disp>/revertir")
@requiere_api_key
def revertir_dispensacion(id_disp):
    with db.get_connection() as conn:
        dispensacion = db.obtener_dispensacion(conn, id_disp)

    if dispensacion is None:
        cuerpo = problema(404, "Dispensacion no encontrada", f"No existe dispensacion '{id_disp}'", request.path)
        return jsonify(cuerpo), 404

    if dispensacion["estado"] == "revertida":
        cuerpo = problema(409, "Ya revertida", "La dispensacion ya fue revertida previamente", request.path)
        return jsonify(cuerpo), 409

    cliente_stock = obtener_cliente()
    try:
        cliente_stock.reponer(
            dispensacion["codigo_medicamento"], dispensacion["cantidad"], id_disp
        )
    except StockNoDisponibleError as exc:
        cuerpo_error = problema(503, "Servicio de Stock no disponible", str(exc), request.path)
        return jsonify(cuerpo_error), 503

    with db.get_connection() as conn:
        dispensacion = db.marcar_revertida(conn, id_disp)

    return jsonify(_dispensacion_a_dict(dispensacion)), 200


@app.get("/v1/dispensaciones/<id_disp>")
@requiere_api_key
def obtener_dispensacion(id_disp):
    with db.get_connection() as conn:
        dispensacion = db.obtener_dispensacion(conn, id_disp)
    if dispensacion is None:
        cuerpo = problema(404, "Dispensacion no encontrada", f"No existe dispensacion '{id_disp}'", request.path)
        return jsonify(cuerpo), 404
    return jsonify(_dispensacion_a_dict(dispensacion)), 200


@app.get("/v1/dispensaciones")
@requiere_api_key
def listar_dispensaciones():
    with db.get_connection() as conn:
        dispensaciones = db.listar_dispensaciones(conn)
    return jsonify([_dispensacion_a_dict(d) for d in dispensaciones]), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)