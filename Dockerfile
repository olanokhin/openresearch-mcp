FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml README.md ./
COPY src/ src/
RUN uv pip install --system .

EXPOSE 8000

ENV MCP_TRANSPORT=streamable-http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000

CMD ["openresearch-mcp"]
