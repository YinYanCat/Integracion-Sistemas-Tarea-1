import logging

import stock_pb2
import stock_pb2_grpc
import db

logger = logging.getLogger("stock_service")


class StockServicer(stock_pb2_grpc.StockServiceServicer):

    def ConsultarStock(self, request, context):
        with db.get_connection() as conn:
            med = db.obtener_medicamento(conn, request.codigo_medicamento)

        if med is None:
            from grpc import StatusCode
            context.set_code(StatusCode.NOT_FOUND)
            context.set_details(f"medicamento '{request.codigo_medicamento}' no existe")
            return stock_pb2.ConsultarStockResponse()

        return stock_pb2.ConsultarStockResponse(
            codigo_medicamento=med["codigo"],
            nombre=med["nombre"],
            unidades_disponibles=med["unidades_disponibles"],
            disponible=med["unidades_disponibles"] > 0,
        )

    def ListarStock(self, request, context):
        pagina = request.pagina if request.pagina > 0 else 1
        tamano = request.tamano_pagina if request.tamano_pagina > 0 else 20
        offset = (pagina - 1) * tamano

        with db.get_connection() as conn:
            items, total = db.listar_medicamentos(conn, offset, tamano)

        respuesta = stock_pb2.ListarStockResponse(total=total)
        for med in items:
            respuesta.items.append(
                stock_pb2.ConsultarStockResponse(
                    codigo_medicamento=med["codigo"],
                    nombre=med["nombre"],
                    unidades_disponibles=med["unidades_disponibles"],
                    disponible=med["unidades_disponibles"] > 0,
                )
            )
        return respuesta

    def DescontarUnidades(self, request, context):
        if request.cantidad <= 0:
            from grpc import StatusCode
            context.set_code(StatusCode.INVALID_ARGUMENT)
            context.set_details("la cantidad a descontar debe ser mayor que 0")
            return stock_pb2.MovimientoStockResponse()

        with db.get_connection() as conn:
            exito, unidades, mensaje = db.descontar_unidades(
                conn, request.codigo_medicamento, request.cantidad, request.id_dispensacion
            )

        logger.info(
            "DescontarUnidades codigo=%s cantidad=%s exito=%s mensaje=%s",
            request.codigo_medicamento, request.cantidad, exito, mensaje,
        )
        return stock_pb2.MovimientoStockResponse(
            exito=exito, unidades_resultantes=unidades, mensaje=mensaje
        )

    def ReponerUnidades(self, request, context):
        if request.cantidad <= 0:
            from grpc import StatusCode
            context.set_code(StatusCode.INVALID_ARGUMENT)
            context.set_details("la cantidad a reponer debe ser mayor que 0")
            return stock_pb2.MovimientoStockResponse()

        with db.get_connection() as conn:
            exito, unidades, mensaje = db.reponer_unidades(
                conn, request.codigo_medicamento, request.cantidad, request.id_dispensacion
            )

        logger.info(
            "ReponerUnidades codigo=%s cantidad=%s exito=%s mensaje=%s",
            request.codigo_medicamento, request.cantidad, exito, mensaje,
        )
        return stock_pb2.MovimientoStockResponse(
            exito=exito, unidades_resultantes=unidades, mensaje=mensaje
        )
