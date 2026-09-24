import os
import logging

import grpc

import stock_pb2
import stock_pb2_grpc

logger = logging.getLogger("stock_client")

STOCK_GRPC_TARGET = os.environ.get("STOCK_GRPC_TARGET", "stock:50051")
TIMEOUT_SEGUNDOS = float(os.environ.get("STOCK_GRPC_TIMEOUT", "2.0"))


class StockNoDisponibleError(Exception):
    """Stock no respondio a tiempo o esta caido (mapear a 503)."""


class StockClient:
    def __init__(self, target: str = STOCK_GRPC_TARGET):
        self._channel = grpc.insecure_channel(target)
        self._stub = stock_pb2_grpc.StockStub(self._channel)

    def consultar(self, codigo_medicamento: str):
        try:
            resp = self._stub.Consultar(
                stock_pb2.ConsultarRequest(codigo_medicamento=codigo_medicamento),
                timeout=TIMEOUT_SEGUNDOS,
            )
        except grpc.RpcError as exc:
            self._traducir_error(exc, "Consultar", codigo_medicamento)
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
            self._traducir_error(exc, "Descontar", codigo_medicamento)
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
            self._traducir_error(exc, "Reponer", codigo_medicamento)
        return resp

    @staticmethod
    def _traducir_error(exc: grpc.RpcError, operacion: str, codigo_medicamento: str):
        code = exc.code()
        logger.warning(
            "Fallo gRPC en %s(codigo=%s): %s - %s",
            operacion, codigo_medicamento, code, exc.details(),
        )
        # DEADLINE_EXCEEDED y UNAVAILABLE (servicio caido o sin
        # Decisión que tomamos para T7
        if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
            raise StockNoDisponibleError(
                f"El servicio de Stock no respondio a tiempo ({code.name})"
            ) from exc
        raise


_cliente_singleton = None


def obtener_cliente() -> StockClient:
    global _cliente_singleton
    if _cliente_singleton is None:
        _cliente_singleton = StockClient()
    return _cliente_singleton