FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml README.md ./
COPY src/ src/
RUN uv pip install --system .

EXPOSE 8000

ENV MCP_TRANSPORT=streamable-http
# SECURITY: 0.0.0.0 binds all interfaces — required so the container is reachable,
# but this server is ZERO-AUTH by design. Do NOT expose this port directly to the
# public internet. Deploy it behind a reverse proxy / API gateway that enforces
# authentication and rate limiting (see SECURITY.md). The local `uvx` path defaults
# to 127.0.0.1 instead (server.py), so only the container opts into all-interfaces.
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000

CMD ["openresearch-mcp"]
