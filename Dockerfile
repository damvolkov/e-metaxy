##### BUILDER #####
FROM ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src /app/src
COPY profiles.yaml ./
RUN uv sync --frozen --no-dev --no-editable

##### DEPLOY #####
FROM python:3.14-slim-trixie AS deploy
### the coder works like the owner at a terminal: git and gh to ship, make and jq for the house scripts, node for
### the hooks and the npx MCP servers. uv, rust and the native claude come from the host, mounted read-only.
RUN apt-get update \
	&& apt-get install -y --no-install-recommends nodejs npm ca-certificates git gh make jq curl \
	&& rm -rf /var/lib/apt/lists/* \
	&& npm install -g --omit=dev @anthropic-ai/claude-code@2.1.300 \
	&& npm cache clean --force
### the host's tools first, as in the owner's shell; the bridge's venv last, so a coder's `python` is never it.
ENV HOME=/home/damien PYTHONUNBUFFERED=1 \
	PATH="/home/damien/.local/bin:/home/damien/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/app/.venv/bin"
WORKDIR /app
COPY --from=builder /app/.venv .venv
COPY --from=builder /app/profiles.yaml ./profiles.yaml
### the coder's home: the subscription login, the sessions and the hooks ride in as bind mounts at host paths.
RUN useradd -u 1000 -d /home/damien -m metaxy \
	&& mkdir -p /home/damien/.claude /home/damien/.local/share/e-metaxy /home/damien/.local/state \
		/home/damien/.config /home/damien/.cache \
	&& chown -R 1000:1000 /home/damien
USER 1000:1000
EXPOSE 45190
CMD ["/app/.venv/bin/python", "-m", "e_metaxy"]
