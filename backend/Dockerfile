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
# runtimeイメージにはnvccが無いため、torch 2.9 / CUDA 12 / cp312 向けのビルド済みwheelを直接入れる
RUN uv pip install "https://github.com/state-spaces/mamba/releases/download/v2.3.2.post1/mamba_ssm-2.3.2.post1+cu12torch2.9cxx11abiTRUE-cp312-cp312-linux_x86_64.whl"

EXPOSE 8001
CMD ["uv", "run", "uvicorn", "word_haku_api.main:app", "--host", "0.0.0.0", "--port", "8001"]