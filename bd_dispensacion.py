import sqlite3
import os
import uuid
from contextlib import contextmanager

DB_PATH = os.environ.get("DISPENSACION_DB_PATH", "/data/dispensacion.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pacientes (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    rut TEXT NOT NULL UNIQUE,
    fecha_registro TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dispensaciones (
    id TEXT PRIMARY KEY,
    paciente_id TEXT NOT NULL,
    codigo_medicamento TEXT NOT NULL,
    nombre_medicamento TEXT NOT NULL,   -- snapshot: no se re-consulta a Stock después
    cantidad INTEGER NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('activa', 'revertida')),
    fecha TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
);
"""


def _ensure_dir():
    directorio = os.path.dirname(DB_PATH)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio, exist_ok=True)


def init_db():
    _ensure_dir()
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


# ---------- Pacientes ----------

def crear_paciente(conn, nombre: str, rut: str):
    id_paciente = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO pacientes (id, nombre, rut) VALUES (?, ?, ?)",
        (id_paciente, nombre, rut),
    )
    conn.commit()
    return obtener_paciente(conn, id_paciente)


def obtener_paciente(conn, id_paciente: str):
    cur = conn.execute(
        "SELECT id, nombre, rut, fecha_registro FROM pacientes WHERE id = ?",
        (id_paciente,),
    )
    return cur.fetchone()


def listar_pacientes(conn):
    cur = conn.execute(
        "SELECT id, nombre, rut, fecha_registro FROM pacientes ORDER BY fecha_registro DESC"
    )
    return cur.fetchall()


# ---------- Dispensaciones ----------

def crear_dispensacion(conn, id_disp: str, paciente_id: str, codigo_medicamento: str,
                        nombre_medicamento: str, cantidad: int):
    conn.execute(
        "INSERT INTO dispensaciones "
        "(id, paciente_id, codigo_medicamento, nombre_medicamento, cantidad, estado) "
        "VALUES (?, ?, ?, ?, ?, 'activa')",
        (id_disp, paciente_id, codigo_medicamento, nombre_medicamento, cantidad),
    )
    conn.commit()
    return obtener_dispensacion(conn, id_disp)


def obtener_dispensacion(conn, id_disp: str):
    cur = conn.execute(
        "SELECT id, paciente_id, codigo_medicamento, nombre_medicamento, "
        "cantidad, estado, fecha FROM dispensaciones WHERE id = ?",
        (id_disp,),
    )
    return cur.fetchone()


def listar_dispensaciones(conn):
    cur = conn.execute(
        "SELECT id, paciente_id, codigo_medicamento, nombre_medicamento, "
        "cantidad, estado, fecha FROM dispensaciones ORDER BY fecha DESC"
    )
    return cur.fetchall()


def marcar_revertida(conn, id_disp: str):
    conn.execute(
        "UPDATE dispensaciones SET estado = 'revertida' WHERE id = ?",
        (id_disp,),
    )
    conn.commit()
    return obtener_dispensacion(conn, id_disp)
