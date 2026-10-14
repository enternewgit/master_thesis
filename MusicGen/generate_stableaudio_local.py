"""
Local Stable Audio generation using stable-audio-tools.

This script runs inference locally with the pretrained model. It requires a suitable
PyTorch + torchaudio installation (GPU recommended for speed). See README for install notes.

Example:
  .venv/bin/python3 generate_stableaudio_local.py \
    --model stabilityai/stable-audio-open-1.0 \
    --prompt "High energy, driving tech house track, 163 BPM, major key, featuring a bright, pulsing synth bass and dynamic stereo percussion. Energetic and joyful." \
    --seconds_total 47 \
    --steps 100 \
    --out demo_local.wav

Notes:
- Installing torch/torchaudio must match your CUDA or CPU configuration.
- The script uses `stable-audio-tools` API. See that package's docs for model names and options.
"""
import argparse
import torch
import torchaudio
from einops import rearrange
from stable_audio_tools import get_pretrained_model
from stable_audio_tools.inference.generation import generate_diffusion_cond


def main():
    p = argparse.ArgumentParser(description="Generate audio locally using stable-audio-tools")
    p.add_argument("--model", default="stabilityai/stable-audio-open-1.0", help="Pretrained model id")
    p.add_argument("--prompt", required=True, help="Text prompt for generation")
    p.add_argument("--seconds_total", type=float, default=8.0, help="Total seconds to generate")
    p.add_argument("--seconds_start", type=float, default=0.0, help="Start offset seconds")
    p.add_argument("--steps", type=int, default=100, help="Sampling steps")
    p.add_argument("--cfg_scale", type=float, default=7.0, help="Classifier-free guidance scale")
    p.add_argument("--sigma_min", type=float, default=0.3)
    p.add_argument("--sigma_max", type=float, default=500.0)
    p.add_argument("--sampler_type", default="dpmpp-3m-sde", help="Sampler type for diffusion")
    p.add_argument("--out", default="stable_local_out.wav", help="Output WAV filename")
    args = p.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    print(f"Downloading model {args.model}...")
    model, model_config = get_pretrained_model(args.model)
    sample_rate = model_config.get("sample_rate", 44100)
    sample_size = model_config.get("sample_size", 65536)

    model = model.to(device)

    conditioning = [{
        "prompt": args.prompt,
        "seconds_start": float(args.seconds_start),
        "seconds_total": float(args.seconds_total)
    }]

    print("Generating audio (this may take time)...")
    output = generate_diffusion_cond(
        model,
        steps=args.steps,
        cfg_scale=args.cfg_scale,
        conditioning=conditioning,
        sample_size=sample_size,
        sigma_min=args.sigma_min,
        sigma_max=args.sigma_max,
        sampler_type=args.sampler_type,
        device=device,
    )

    # Rearrange audio batch to single sequence
    # output shape: (batch, channels, frames)
    output = rearrange(output, "b d n -> d (b n)")

    # Trim or pad the output to requested duration (seconds_total)
    # output shape: (channels, frames)
    target_frames = int(args.seconds_total * sample_rate)
    cur_frames = output.shape[1]
    if cur_frames > target_frames:
        output = output[:, :target_frames]
        print(f"Trimmed output from {cur_frames} frames to {target_frames} frames ({args.seconds_total}s)")
    elif cur_frames < target_frames:
        # pad with zeros if shorter than requested
        pad = torch.zeros((output.shape[0], target_frames - cur_frames), dtype=output.dtype, device=output.device)
        output = torch.cat([output, pad], dim=1)
        print(f"Padded output from {cur_frames} frames to {target_frames} frames ({args.seconds_total}s)")

    # Normalize and convert to int16
    output = output.to(torch.float32)
    maxv = torch.max(torch.abs(output))
    if maxv > 0:
        output = output.div(maxv)
    output = output.clamp(-1, 1).mul(32767).to(torch.int16).cpu()

    # Save as WAV (torchaudio expects shape [channels, frames])
    torchaudio.save(args.out, output, sample_rate)
    print(f"Saved {args.out} (sample_rate={sample_rate}, frames={output.shape[1]})")


if __name__ == '__main__':
    main()
