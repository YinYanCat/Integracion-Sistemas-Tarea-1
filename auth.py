import os
from fastapi import Header, HTTPException, Request

# En un entorno real esto vendria de un secreto gestionado (Vault, etc.),
# no de una variable de entorno plana. Para el alcance del encargo,
# una env var inyectada por docker-compose es suficiente y defendible.
API_KEYS_VALIDAS = set(
    filter(None, os.environ.get("DISPENSACION_API_KEYS", "clave-dev-123").split(","))
)


def problema(status: int, title: str, detail: str, instance: str):
    return {
        "type": f"https://saludtotal.cl/errors/{title.lower().replace(' ', '-')}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
    }


async def verificar_api_key(request: Request, x_api_key: str = Header(default=None)):
  
    if x_api_key is None or x_api_key not in API_KEYS_VALIDAS:
        raise HTTPException(
            status_code=401,
            detail=problema(
                status=401,
                title="No autenticado",
                detail="Falta el header X-API-Key o su valor es inválido",
                instance=str(request.url.path),
            ),
        )
    return x_api_key
