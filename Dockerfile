##### BUILDER #####
FROM ghcr.io/astral-sh/uv:0.12.15-python3.14-trixie-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src /app/src
COPY profiles.yaml ./
RUN uv sync --frozen --no-dev --no-editable

##### DEPLOY #####
FROM python:3.14-slim-trixie AS deploy
RUN apt-get update \
	&& apt-get install -y --no-install-recommends nodejs npm ca-certificates \
	&& rm -rf /var/lib/apt/lists/* \
	&& npm install -g --omit=dev @anthropic-ai/claude-code@2.1.300 \
	&& npm cache clean --force
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HOME=/home/damien
WORKDIR /app
COPY --from=builder /app/.venv .venv
COPY --from=builder /app/profiles.yaml ./profiles.yaml
### the coder's home: the subscription login, the sessions and the hooks ride in as bind mounts at host paths.
RUN useradd -u 1000 -d /home/damien -m metaxy \
	&& mkdir -p /home/damien/.claude /home/damien/.local/share/e-metaxy \
	&& chown -R 1000:1000 /home/damien
USER 1000:1000
EXPOSE 45190
CMD ["python", "-m", "e_metaxy"]
