# No CUDA toolkit in the base image on purpose. jax[cuda12]'s pip wheels
# bundle their own CUDA/cuDNN/cuSPARSE runtime libraries; the only thing this
# container needs from outside is the host's NVIDIA driver, which
# `docker run --gpus all` (via the NVIDIA Container Toolkit) injects at
# runtime. There is no second copy of CUDA anywhere in this image to
# conflict with it -- that mismatch (system CUDA 12.8 vs. venv-bundled 12.9
# via a polluted LD_LIBRARY_PATH) is exactly what caused the segfaults and
# silent CPU fallback described in mrt2_poc/README.txt section 4(2) on
# bare-metal/WSL2. Do not switch to an nvidia/cuda base image, and do not set
# LD_LIBRARY_PATH anywhere in this file, without re-reading that section.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Pinned to the exact versions verified working on the dev machine (RTX 3060
# Ti, driver 560.94, see mrt2_poc/README.txt section 2) so a rebuild months
# from now doesn't silently pick up an incompatible jax/jaxlib/CUDA-plugin
# combination.
RUN pip install --no-cache-dir "magenta-rt==2.0.2" "jax[cuda12]==0.10.2"

COPY server.py docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

ENV XLA_PYTHON_CLIENT_PREALLOCATE=false
ENV XLA_FLAGS="--xla_gpu_autotune_level=0"

EXPOSE 8799

# gpu_ready comes from the /health handler added in server.py; a container
# that's technically "up" but silently running on CPU should read as
# unhealthy, not healthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD curl -fs http://127.0.0.1:8799/health | grep -q '"gpu_ready": *true' || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["--model", "mrt2_small", "--port", "8799", "--host", "0.0.0.0"]
