FROM python:3.12-slim

WORKDIR /app

COPY stock/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY contratos/stock.proto ./stock.proto
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. stock.proto

COPY stock/ .

ENV STOCK_DB_PATH=/data/stock.db
ENV STOCK_GRPC_PORT=50051

EXPOSE 50051

CMD ["python", "server.py"]