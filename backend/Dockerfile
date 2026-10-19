FROM nvidia/cuda:12.8.1-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /backend
ENV UV_PYTHON=python3.12

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

EXPOSE 8001
CMD ["uv", "run", "uvicorn", "word_haku_api.main:app", "--host", "0.0.0.0", "--port", "8001"]