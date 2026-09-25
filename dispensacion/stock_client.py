import os
import logging
import json

import grpc
from google.protobuf.json_format import MessageToDict, ParseDict

import stock_pb2
import stock_pb2_grpc

import redis # es dispensador quien consulta muchas veces (llama a stock y stock a su bdd)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CACHE_TTL = int(os.environ.get("STOCK_CACHE_TTL", "30"))          # 30 s: cuánto recordamos un id ya visto

logger = logging.getLogger("stock_client")

STOCK_GRPC_TARGET = os.environ.get("STOCK_GRPC_TARGET", "stock:50051")
TIMEOUT_SEGUNDOS = float(os.environ.get("STOCK_GRPC_TIMEOUT", "2.0"))


class StockNoDisponibleError(Exception):
    """Stock no respondio a tiempo o esta caido (mapear a 503)."""

def _clave_cache(codigo_medicamento: str) -> str:
    return f"stock:{codigo_medicamento}" #convención de redis namespace:id útil si hacemos O2 asi separamos

class StockClient:
    def __init__(self, target: str = STOCK_GRPC_TARGET, redis_url: str = REDIS_URL):
        self._channel = grpc.insecure_channel(target)
        self._stub = stock_pb2_grpc.StockStub(self._channel)
        try:
            self._cache = redis.Redis.from_url(redis_url, socket_connect_timeout=1)
            self._cache.ping()
        except redis.RedisError as exc:
            logger.warning(f"Redis no disponible, cache no disponible: {exc}")
            self._cache = None
            
    def consultar(self, codigo_medicamento: str):
        clave = _clave_cache(codigo_medicamento)

        if self._cache is not None:
            try:
                dato = self._cache.get(clave)
            except redis.RedisError as exc:
                logger.warning(f"Fallo de lectura en Redis, se ignora cache: {exc}")
                dato = None
            if dato is not None:
                logger.debug(f"Cache HIT para {clave}")
                return ParseDict(json.loads(dato), stock_pb2.ConsultarResponse())
            logger.debug(f"Cache MISS para {clave}")

        try:
            resp = self._stub.Consultar(
                stock_pb2.ConsultarRequest(codigo_medicamento=codigo_medicamento),
                timeout=TIMEOUT_SEGUNDOS,
            )
        except grpc.RpcError as exc:
            self.traducir_error(exc, "Consultar", codigo_medicamento)

        if self._cache is not None:
            self.guardar(clave, resp)
        return resp

    def descontar(self, codigo_medicamento: str, cantidad: int, id_dispensacion: str):
        try:
            resp = self._stub.Descontar(
                stock_pb2.DescontarRequest(
                    codigo_medicamento=codigo_medicamento,
                    cantidad=cantidad,
                    id_dispensacion=id_dispensacion,
                ),
                timeout=TIMEOUT_SEGUNDOS,
            )
        except grpc.RpcError as exc:
            self.traducir_error(exc, "Descontar", codigo_medicamento)

        if resp.exito:
            self.invalidar(codigo_medicamento)
        return resp

    def reponer(self, codigo_medicamento: str, cantidad: int, id_dispensacion: str):
        try:
            resp = self._stub.Reponer(
                stock_pb2.ReponerRequest(
                    codigo_medicamento=codigo_medicamento,
                    cantidad=cantidad,
                    id_dispensacion=id_dispensacion,
                ),
                timeout=TIMEOUT_SEGUNDOS,
            )
        except grpc.RpcError as exc:
            self.traducir_error(exc, "Reponer", codigo_medicamento)

        if resp.exito:
            self.invalidar(codigo_medicamento)
        return resp

    @staticmethod
    def traducir_error(exc: grpc.RpcError, operacion: str, codigo_medicamento: str):
        code = exc.code()
        logger.warning(
            "Fallo gRPC en %s(codigo=%s): %s - %s",
            operacion, codigo_medicamento, code, exc.details(),
        )
        # DEADLINE_EXCEEDED y UNAVAILABLE (servicio caido o sin conexión)
        # Decisión que tomamos para T7
        if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
            raise StockNoDisponibleError(
                f"El servicio de Stock no respondio a tiempo ({code.name})"
            ) from exc
        raise

# Helpers para cache

    def guardar(self, clave: str, resp):
        try:
            self._cache.set(
                clave,
                json.dumps(MessageToDict(resp, preserving_proto_field_name=True)),
                ex=CACHE_TTL,
            )
        except redis.RedisError as exc:
            logger.warning(f"Fallo de escritura en Redis, se ignora: {exc}")

    def invalidar(self, codigo_medicamento: str):
        if self._cache is None:
            return
        try:
            self._cache.delete(_clave_cache(codigo_medicamento))
        except redis.RedisError as exc:
            logger.warning(f"Fallo al invalidar cache de {codigo_medicamento}: {exc}")

_cliente_singleton = None


def obtener_cliente() -> StockClient:
    global _cliente_singleton
    if _cliente_singleton is None:
        _cliente_singleton = StockClient()
    return _cliente_singleton
