FROM python:3.12-slim

WORKDIR /app

COPY dispensacion/requirements.txt .
RUN pip install --no-cache-dir grpcio-tools==1.66.2 && \
    pip install --no-cache-dir -r requirements.txt

COPY contratos/stock.proto ./stock.proto
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. stock.proto

COPY dispensacion/ .

ENV DISPENSACION_DB_PATH=/data/dispensacion.db
ENV STOCK_GRPC_TARGET=stock:50051
ENV STOCK_GRPC_TIMEOUT=2.0

EXPOSE 8000

CMD ["gunicorn", "--preload", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30", "dispensacion_service:app"]