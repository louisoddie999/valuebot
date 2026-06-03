# ValueBot API + auto-refresh, single container.
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY . .
RUN chmod +x entrypoint.sh
ENV DB_PATH=data/serve.sqlite PORT=8000 SCOPE=ahead REFRESH_HOURS=12
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1
CMD ["./entrypoint.sh"]
