from pydantic import BaseModel, Field
from typing import Optional


class NuevoPaciente(BaseModel):
    nombre: str
    rut: str


class Paciente(BaseModel):
    id: str
    nombre: str
    rut: str
    fecha_registro: str


class NuevaDispensacion(BaseModel):
    paciente_id: str
    codigo_medicamento: str
    cantidad: int = Field(gt=0, description="Debe ser mayor que 0")


class Dispensacion(BaseModel):
    id: str
    paciente_id: str
    codigo_medicamento: str
    nombre_medicamento: str
    cantidad: int
    estado: str
    fecha: str


class ErrorEstandar(BaseModel):
    """Formato de error estilo RFC 7807 (Problem Details)."""
    type: str
    title: str
    status: int
    detail: Optional[str] = None
    instance: Optional[str] = None
