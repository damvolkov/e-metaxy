##### BUILDER #####
FROM ghcr.io/astral-sh/uv:0.13.7-python3.14-trixie-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src /app/src
### the build context has no .git: the release hands the tag's version in, or the package would say 0.0.0.
ARG VERSION=0.0.0
RUN UV_DYNAMIC_VERSIONING_BYPASS=${VERSION} uv sync --frozen --no-dev --no-editable

##### DEPLOY #####
FROM python:3.14-slim-trixie AS deploy
WORKDIR /app
### ORGANON_DATA: one volume, a subtree per section; the store beside them.
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 ORGANON_DATA=/data DB_PATH=/data/store/app.db
COPY --from=builder /app/.venv .venv
### the venv was built for the builder's Python: a deploy stage on another minor would ship an image that cannot import.
RUN python -c "import e_organon"
RUN mkdir -p /data && chown -R nobody /data
VOLUME /data
USER nobody
EXPOSE 45190
### APP_PORT / APP_HOST pick the bind: the house runs it on the host network, at 45190.
CMD ["sh", "-c", "exec granian --interface asgi --factory --host ${APP_HOST:-0.0.0.0} --port ${APP_PORT:-45190} e_organon.main:create_app"]
