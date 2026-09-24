import os
from functools import wraps

from flask import request, jsonify

# En un entorno real esto vendria de un secreto gestionado (Vault, etc.),
# no de una variable de entorno plana. Para el alcance del encargo,
# una env var inyectada por docker-compose es suficiente y defendible.
API_KEYS_VALIDAS = set(
    filter(None, os.environ.get("DISPENSACION_API_KEYS", "clave-dev-123").split(","))
)


def problema(status: int, title: str, detail: str, instance: str):
    slug = title.lower().replace(" ", "-")
    return {
        "type": f"https://saludtotal.cl/errors/{slug}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
    }


def requiere_api_key(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        x_api_key = request.headers.get("X-API-Key")
        if x_api_key is None or x_api_key not in API_KEYS_VALIDAS:
            cuerpo = problema(
                status=401,
                title="No autenticado",
                detail="Falta el header X-API-Key o su valor es invalido",
                instance=request.path,
            )
            return jsonify(cuerpo), 401
        return vista(*args, **kwargs)

    return envoltura