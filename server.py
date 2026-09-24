import logging
import os
from concurrent import futures

import grpc

import stock_pb2_grpc
import db
from stock_service import StockServicer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("stock_server")

PORT = os.environ.get("STOCK_GRPC_PORT", "50051")
MAX_WORKERS = int(os.environ.get("STOCK_GRPC_MAX_WORKERS", "10"))


def serve():
    db.init_db()
    logger.info("Base de datos de Stock inicializada en %s", db.DB_PATH)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=MAX_WORKERS))
    stock_pb2_grpc.add_StockServiceServicer_to_server(StockServicer(), server)

    listen_addr = f"[::]:{PORT}"
    server.add_insecure_port(listen_addr)
    server.start()
    logger.info("Servicio de Stock (gRPC) escuchando en %s", listen_addr)

    server.wait_for_termination()


if __name__ == "__main__":
    serve()
