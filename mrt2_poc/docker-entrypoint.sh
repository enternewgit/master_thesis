#!/bin/sh
set -e

# Model weights (MusicCoCa/SpectroStream + the streaming model itself, a few
# GB) are downloaded by the `mrt` CLI to $HOME/Documents/Magenta/magenta-rt-v2
# rather than baked into the image, so mount that path as a volume: it
# survives container restarts/rebuilds and doesn't get re-downloaded every
# time.
#
# NB: `docker run -v <name>:/path` auto-creates an empty directory at the
# mount point on first use, even though nothing has been downloaded into it
# yet -- so checking `[ -d "$MAGENTA_HOME" ]` alone is always true and never
# triggers a download (confirmed the hard way: server crashed with
# FileNotFoundError on the .safetensors checkpoint despite this entrypoint
# logging "skipping download"). Check for the specific model's checkpoint
# file instead. This still only checks the *requested* model -- if you
# switch models (e.g. mrt2_small -> mrt2_base) it downloads the new one
# alongside the old one on the same volume, it doesn't clean up.
MAGENTA_HOME="${HOME:-/root}/Documents/Magenta/magenta-rt-v2"

MODEL_NAME="mrt2_small"
prev=""
for arg in "$@"; do
  if [ "$prev" = "--model" ]; then
    MODEL_NAME="$arg"
  fi
  prev="$arg"
done

CHECKPOINT="$MAGENTA_HOME/checkpoints/$MODEL_NAME.safetensors"
if [ ! -f "$CHECKPOINT" ]; then
  echo "[entrypoint] No checkpoint at $CHECKPOINT -- running first-time setup. This downloads several GB and only needs to happen once per volume."
  mrt models init
  mrt models download "$MODEL_NAME"
  # `mrt models download` only fetches models/<name>/ (MLX format +
  # _state.safetensors), which is NOT what MagentaRT2Jax (the JAX backend
  # this server uses) reads. The JAX backend loads from checkpoints/, which
  # is populated by a *separate* command, `mrt checkpoints download` --
  # undocumented in mrt2_poc/README.txt section 3, discovered by hitting a
  # FileNotFoundError on checkpoints/<model>.safetensors after `mrt models
  # download` reported success.
  mrt checkpoints download "$MODEL_NAME.safetensors"
else
  echo "[entrypoint] Found existing checkpoint at $CHECKPOINT, skipping download."
fi

exec python server.py "$@"
