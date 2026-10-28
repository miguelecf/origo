# Origo en contenedor: misma app que en systemd, datos en el volumen /data.
FROM ghcr.io/astral-sh/uv:0.12.18 AS uv

FROM python:3.13-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" \
    DATABASE_URL=sqlite:////data/origo.db HOME=/data XDG_DATA_HOME=/data
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app

RUN useradd --system --uid 10001 --no-create-home --home-dir /data origo && mkdir -p /data && chown origo:origo /data
USER origo
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/offline')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-server-header"]
