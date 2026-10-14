from typing import List, Tuple, Optional
import asyncio
import time
import io
import os
import tempfile
import numpy as np
import random
import shutil
try:
    import torch
except Exception:
    torch = None

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from ..music_ai.loader import get_model, load_emotion_model
from ..music_ai.generate_mrt2_local import generate_local as generate_local_mrt2
from ..music_ai.infer import predict_from_eeg, predict_batch_from_eeg
from ..music_ai.generator import _file_iterator
from ..music_ai.eeg_preprocess import MUSE_INPUT_FS, MODEL_EEG_FS, resample_eeg_channels

router = APIRouter()


def _generate_local(provider: Optional[str], *, prompt: str, out_path, seconds_total: float, reset: bool = False):
    """Generate audio via MRT2.

    `reset` starts a fresh streaming sequence instead of continuing from the
    previous call's state (see generate_mrt2_local.py). Pass reset=True for
    the first generation of a new feedback session. `provider` is accepted
    for call-site compatibility but only 'mrt2' is supported.
    """
    if provider and provider.lower() != "mrt2":
        raise RuntimeError(f"Unsupported provider: {provider!r} (only 'mrt2' is supported)")
    return generate_local_mrt2(
        prompt=prompt, out_path=out_path, seconds_total=seconds_total,
        model=os.environ.get("MRT2_LOCAL_MODEL", "mrt2_small"),
        reset=reset,
    )

"""
Module: route_experiment
このモジュールは EEG -> Valence/Arousal 推定を受け取り、ルールベースで
音楽生成プロンプトを構築してローカル生成器に渡します。

利用可能なテンプレート変数（`base_prompt` で利用可能）:

- `current_v`, `current_a` : 現在の平均 Valence/Arousal（小数）
- `next_v`, `next_a`     : 次のゴール Valence/Arousal（小数）
- `target_v`, `target_a` : リクエストで与えたターゲット（小数）
- `bpm`                  : 推奨テンポ（整数）
- `dynamics`             : 音量／ダイナミクス表現（文字列）
- `key_hint`             : キーヒント（例: "C Major" / "C Minor"）
- `instruments`          : 推奨楽器列挙（文字列）
- `texture`              : 密度／テクスチャのヒント（文字列）

使用例（Ehrlich-style）:

    base_prompt = (
        "A {dynamics} {texture} piece played by {instruments}. "
        "Key of {key_hint}, Tempo {bpm} BPM. "
        "The music is {next_v}"
    )

この docstring はテンプレート利用の一例です。詳細は README を参照してください。
"""

# in-memory state for simple live UI polling
EXPERIMENT_STATE = {
    "current_v": None,
    "current_a": None,
    "next_v": None,
    "next_a": None,
    "target_v": None,
    "target_a": None,
    "duration": None,
    "base_prompt": None,
    "provider": None,
    "seed": None,
    "running": False,
}

def _ensure_session_seed() -> int:
    seed = EXPERIMENT_STATE.get("seed")
    if seed is None:
        seed = random.randint(0, 2**32 - 1)
        EXPERIMENT_STATE["seed"] = seed
    return int(seed)


class FeedbackRequest(BaseModel):
    """Request body for experiment feedback.

    - `samples`: channels x samples (List[List[float]]) representing 60s of continuous EEG.
    - `target_valence` / `target_arousal`: desired target scores in [0,1].
    - `alpha`: feedback interpolation coefficient (optional, default 0.3).
    - `hop`: sliding window hop size in samples (optional). If omitted, defaults to seq_len//2.
    """
    samples: List[List[float]] = Field(..., description="channels x time samples (float)")
    target_valence: float = Field(..., ge=0.0, le=1.0)
    target_arousal: float = Field(..., ge=0.0, le=1.0)
    alpha: Optional[float] = Field(0.3, ge=0.0, le=1.0)
    hop: Optional[int] = Field(None, description="Hop size in samples for sliding windows; default = seq_len//2")
    duration: Optional[float] = Field(None, description="Requested output audio duration in seconds (optional). If omitted, defaults to 8s")
    base_prompt: Optional[str] = Field(None, description="Optional prompt template for generation. Use placeholders like {next_v}, {next_a}, {target_v}, {target_a}, {current_v}, {current_a}")
    provider: Optional[str] = Field("mrt2", description="Music generation backend; only 'mrt2' (Magenta RealTime 2) is supported")
    seed: Optional[int] = Field(None, description="Optional integer seed for reproducible generation")
    # Testing overrides: when `override_current` is true, the server will use these
    # values as the "current" valence/arousal instead of running inference.
    override_current: Optional[bool] = Field(False, description="If true, use override_current_valence/arousal as current scores (testing only)")
    override_current_valence: Optional[float] = Field(None, ge=0.0, le=1.0)
    override_current_arousal: Optional[float] = Field(None, ge=0.0, le=1.0)


def _slice_windows(samples: np.ndarray, seq_len: int, hop: Optional[int] = None) -> np.ndarray:
    """Slice `samples` (channels x time) into windows of length `seq_len`.

    Returns array shaped (n_windows, channels, seq_len).
    Uses overlap controlled by `hop`. If hop is None, defaults to seq_len//2.
    """
    if samples.ndim != 2:
        raise ValueError("samples must be a 2D array (channels x time)")

    channels, total = samples.shape
    if total < seq_len:
        raise ValueError(f"Not enough samples ({total}) for one window of length {seq_len}")

    if hop is None:
        hop = max(1, seq_len // 2)

    starts = list(range(0, total - seq_len + 1, hop))
    windows = np.stack([samples[:, s : s + seq_len] for s in starts], axis=0)
    return windows


def _log_stage_timing(t_request_start, t_preprocess_done, t_inference_done, t_prompt_done,
                       gen_time: Optional[float], seconds_to_gen: float) -> None:
    """Print a per-stage timing breakdown for one /feedback call (bottleneck spike)."""
    total_time = time.time() - t_request_start
    rtf = (seconds_to_gen / gen_time) if gen_time and gen_time > 0 else None
    generation_part = f"generation={gen_time:.3f}s" if gen_time is not None else "generation=n/a"
    rtf_part = f" (audio={seconds_to_gen:.1f}s, rtf={rtf:.2f}x)" if rtf is not None else ""
    print(
        "[experiment][timing] "
        f"preprocess={t_preprocess_done - t_request_start:.3f}s "
        f"inference={t_inference_done - t_preprocess_done:.3f}s "
        f"prompt={t_prompt_done - t_inference_done:.3f}s "
        f"{generation_part}{rtf_part} "
        f"total={total_time:.3f}s"
    )


def _mean_scores(scores: List[Tuple[float, float]]) -> Tuple[float, float]:
    if len(scores) == 0:
        return 0.5, 0.5
    arr = np.array(scores, dtype=float)
    mean_v = float(np.mean(arr[:, 0]))
    mean_a = float(np.mean(arr[:, 1]))
    return mean_v, mean_a


def get_music_description(v: float, a: float) -> str:
    """Convert valence (v) and arousal (a) into a concrete music description string.

    The function accepts v/a in [0,1] (probability) or [-1,1] (Russell). If inputs
    are in [0,1], they are mapped to [-1,1] internally.
    """
    # Ensure inputs are within 0..1
    try:
        v = float(v)
        a = float(a)
    except Exception:
        v = 0.5
        a = 0.5

    v = max(0.0, min(1.0, v))
    a = max(0.0, min(1.0, a))

    # map to Russell space [-1,1]
    v_map = v * 2.0 - 1.0
    a_map = a * 2.0 - 1.0

    keywords = []

    # Base instrumentation inspired by Ehrlich-style mappings
    instruments = "Cinematic Classical, Chamber Orchestra, Piano, Cello, Strings"
    keywords.append(instruments)

    # Quadrant-driven mood / tonal hints
    if v_map >= 0 and a_map >= 0:
        keywords.append("Uplifting, Joyful, Triumphant, Bright, Major key, High pitch")
    elif v_map < 0 and a_map >= 0:
        keywords.append("Tense, Anxious, Dissonant, Dark, Minor key, Aggressive, Dramatic")
    elif v_map < 0 and a_map < 0:
        keywords.append("Melancholic, Sad, Emotional, Somber, Minimalist, Legato, Low pitch")
    else:  # v_map >=0 and a_map < 0
        keywords.append("Peaceful, Serene, Ethereal, Meditative, Soft, Flowing, Major key")

    # Arousal-driven texture / rhythm density
    if a > 0.6:
        keywords.append("Dense texture, Complex rhythm, Staccato, Percussive elements")
    elif a < 0.4:
        keywords.append("Sparse texture, Long sustained notes, Ambient, Spacious")

    return ", ".join(keywords)


def get_default_music_prompt(v: float, a: float, duration: int = 10) -> str:
    """Compose a descriptive music prompt from valence/arousal and duration.

    Inputs `v` and `a` are expected in [0,1]. The function clamps values and
    returns a descriptive prompt including mood, genre, instruments, tempo, key,
    and a short note about duration and arrangement.
    """
    # sanitize inputs
    try:
        v = float(v)
        a = float(a)
    except Exception:
        v = 0.5
        a = 0.5

    v = max(0.0, min(1.0, v))
    a = max(0.0, min(1.0, a))

    # 1) qualitative base description
    base_desc = get_music_description(v, a)

    # 2) BPM mapping: 60..150 BPM as a increases
    bpm = int(60 + (a * 90))

    # 3) dynamics / loudness descriptors
    if a > 0.66:
        dynamics = "Fortissimo, Dynamic, Powerful"
    elif a < 0.33:
        dynamics = "Pianissimo, Gentle, Soft"
    else:
        dynamics = "Mezzo-forte, Moderate dynamics"

    # 4) explicit key hints
    key_hint = None
    if v > 0.6:
        key_hint = "C Major"
    elif v < 0.4:
        key_hint = "C Minor"

    # 5) quality tags
    quality = "High Quality, Stereo"

    parts = [base_desc, f"Tempo: {bpm} BPM", dynamics]
    if key_hint:
        parts.append(key_hint)
    parts.append(quality)
    parts.append(f"Duration: {int(max(1, duration))} seconds")

    final_prompt = ", ".join(parts)
    return final_prompt


# Every generated chunk gets looped client-side (RealtimeMusic.tsx, ExperimentPlayer.tsx)
# regardless of how much the emotional target is shifting, so this hint is appended to
# every prompt build_prompt() produces, not just the low-magnitude-change case.
LOOP_FRIENDLY_HINT = (
    "Seamless loop, smooth transition back to the beginning, consistent tempo and key "
    "throughout, no abrupt ending"
)


def get_evolution_prompt(current_v: float, current_a: float, target_v: float, target_a: float) -> str:
    """Build an evolution/transition prompt from current -> target VA scores.

    Returns a short comma-separated description instructing how the music should
    evolve (e.g., "Crescendo, Rising energy, Becoming brighter").
    """
    try:
        cv = float(current_v)
        ca = float(current_a)
        tv = float(target_v)
        ta = float(target_a)
    except Exception:
        cv, ca, tv, ta = 0.5, 0.5, 0.5, 0.5

    diff_v = tv - cv
    diff_a = ta - ca
    magnitude = (diff_v ** 2 + diff_a ** 2) ** 0.5

    keywords = []

    # Magnitude-based style (conservative thresholds)
    if magnitude < 0.08:
        keywords.append("Steady rhythm, Loopable, Minimal changes, Constant atmosphere")
    elif magnitude > 0.35:
        keywords.append("Dramatic transition, Sudden change, Explosive, Fast evolution")
    else:
        keywords.append("Smooth transition, Evolving texture, Progressive")

    # Arousal direction -> map to loudness/density changes (Ehrlich-style)
    if diff_a > 0.18:
        keywords.append("Crescendo, Increasing loudness, Becoming denser, More rhythmic activity")
    elif diff_a < -0.18:
        keywords.append("Decrescendo, Decreasing loudness, Becoming sparser, Less rhythmic activity")

    # Valence direction -> map to consonance/pitch and tension changes
    # Positive valence shifts -> brighter, more resolving harmonies
    if diff_v > 0.15:
        keywords.append("Becoming brighter, Resolving harmonies, Increasing consonance, Brighter timbres")
    elif diff_v > 0.05:
        keywords.append("Slightly brighter, Gentle lift in harmony, Warmer textures")
    # Negative valence shifts -> darker, more tension/dissonance
    elif diff_v < -0.25:
        keywords.append("Becoming darker, Building tension, Increasing dissonance, Heavy low-end")
    elif diff_v < -0.05:
        keywords.append("Slightly darker, Introduce minor harmonies, Sparse bright leads, More dissonance")

    return ", ".join(keywords)


def build_prompt(
    current_v: float,
    current_a: float,
    next_v: float,
    next_a: float,
    target_v: float,
    target_a: float,
    *,
    base_prompt: Optional[str] = None,
    duration: Optional[float] = None,
) -> str:
    """Build the final generation prompt from the current and target VA state."""
    if base_prompt:
        try:
            bpm_tmpl = int(60 + (float(next_a) * 90))
        except Exception:
            bpm_tmpl = 90
        try:
            if float(next_a) > 0.66:
                dynamics_tmpl = "Fortissimo, Dynamic, Powerful"
            elif float(next_a) < 0.33:
                dynamics_tmpl = "Pianissimo, Gentle, Soft"
            else:
                dynamics_tmpl = "Mezzo-forte, Moderate dynamics"
        except Exception:
            dynamics_tmpl = "Moderate dynamics"

        try:
            if float(next_v) > 0.6:
                key_hint_tmpl = "C Major"
            elif float(next_v) < 0.4:
                key_hint_tmpl = "C Minor"
            else:
                key_hint_tmpl = "C Major"
        except Exception:
            key_hint_tmpl = "C Major"

        instruments_tmpl = "Cinematic Classical, Chamber Orchestra, Piano, Cello, Strings"
        try:
            if float(next_a) > 0.6:
                texture_tmpl = "Dense texture"
            elif float(next_a) < 0.4:
                texture_tmpl = "Sparse texture"
            else:
                texture_tmpl = "Moderate texture"
        except Exception:
            texture_tmpl = "Moderate texture"

        mapping = {
            "current_v": f"{current_v:.4f}",
            "current_a": f"{current_a:.4f}",
            "next_v": f"{next_v:.4f}",
            "next_a": f"{next_a:.4f}",
            "target_v": f"{target_v:.4f}",
            "target_a": f"{target_a:.4f}",
            "bpm": str(bpm_tmpl),
            "dynamics": dynamics_tmpl,
            "key_hint": key_hint_tmpl,
            "instruments": instruments_tmpl,
            "texture": texture_tmpl,
        }
        try:
            prompt = base_prompt.format(**mapping)
            try:
                evo = get_evolution_prompt(current_v, current_a, target_v, target_a)
                if evo:
                    prompt = f"{prompt}. {evo}"
            except Exception:
                pass
        except Exception as e:
            print(f"[experiment] warning: base_prompt formatting failed: {e}")
            prompt = (
                f"Generate an instrumental piece aimed to steer listener's emotion toward "
                f"valence {next_v:.2f} and arousal {next_a:.2f}. Keep it smooth and suitable for neurofeedback."
            )
        return f"{prompt}. {LOOP_FRIENDLY_HINT}"

    try:
        duration_for_prompt = int(duration) if duration is not None else 8
    except Exception:
        duration_for_prompt = 8
    default_prompt = get_default_music_prompt(next_v, next_a, duration=duration_for_prompt)
    try:
        evo = get_evolution_prompt(current_v, current_a, target_v, target_a)
    except Exception:
        evo = ""
    if evo:
        return (
            f"{default_prompt}. {evo}. Aim to steer listener toward valence {next_v:.2f} and arousal {next_a:.2f}. "
            f"Keep it smooth and suitable for neurofeedback. {LOOP_FRIENDLY_HINT}"
        )
    return (
        f"{default_prompt}. Aim to steer listener toward valence {next_v:.2f} and arousal {next_a:.2f}. "
        f"Keep it smooth and suitable for neurofeedback. {LOOP_FRIENDLY_HINT}"
    )


@router.post("/feedback")
async def feedback_endpoint(body: FeedbackRequest):
    """Receive 60s of EEG (channels x samples) and a target (valence/arousal).

    Algorithm:
    - ensure emotion model loaded
    - slice 60s data into sliding windows (seq_len)
    - run per-window inference and average scores
    - compute Next Goal = Current + (Target - Current) * alpha
    - generate audio locally to move toward Next Goal and stream WAV
    """
    t_request_start = time.time()
    try:
        # ensure emotion model loaded (mirror behavior in route_eeg_emotion)
        model = get_model("emotion")
        if model is None:
            # try lazy load from env defaults
            import decouple
            valence_path = decouple.config("EMO_VALENCE_PATH", default=os.path.join(os.path.dirname(__file__), '..', '..', '..', 'valence.pth'))
            arousal_path = decouple.config("EMO_AROUSAL_PATH", default=os.path.join(os.path.dirname(__file__), '..', '..', '..', 'arousal.pth'))
            try:
                load_emotion_model("emotion", valence_path=valence_path, arousal_path=arousal_path)
                model = get_model("emotion")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to load emotion model: {e}")

        params = getattr(model, "params", {}) or {}
        expected_channels = int(params.get("n_channels", 4))
        seq_len = int(params.get("seq_len", 100))

        # Convert samples to numpy array (channels x time)
        arr = np.array(body.samples, dtype=float)
        if arr.ndim != 2:
            raise HTTPException(status_code=400, detail="'samples' must be 2D (channels x time)")

        # Server-side preprocessing for Muse2 stream: 256Hz -> 200Hz before inference.
        # This keeps model time-scale consistent with training-time assumptions.
        try:
            orig_total = int(arr.shape[1])
            arr = resample_eeg_channels(arr, src_fs=MUSE_INPUT_FS, dst_fs=MODEL_EEG_FS)
            new_total = int(arr.shape[1])
            if new_total != orig_total:
                print(f"[experiment] resampled EEG: {orig_total} samples @ {MUSE_INPUT_FS}Hz -> {new_total} samples @ {MODEL_EEG_FS}Hz")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"EEG resampling failed: {e}")
        t_preprocess_done = time.time()

        ch, total = arr.shape
        if ch != expected_channels:
            raise HTTPException(status_code=400, detail=f"Expected {expected_channels} channels, got {ch}")

        # EXPERIMENT_STATE["seed"] is None exactly at the start of a session
        # (cleared by /experiment/stop, set once by _ensure_session_seed()
        # below) -- reuse that as the mrt2 session boundary: the first
        # generation of a session starts a fresh streaming sequence, later
        # ones continue it.
        is_new_mrt2_session = EXPERIMENT_STATE.get("seed") is None

        # Testing override: allow tests to force current_v/current_a and skip inference
        if getattr(body, "override_current", False):
            try:
                current_v = float(body.override_current_valence) if body.override_current_valence is not None else 0.5
            except Exception:
                current_v = 0.5
            try:
                current_a = float(body.override_current_arousal) if body.override_current_arousal is not None else 0.5
            except Exception:
                current_a = 0.5
            # targets come from request
            target_v = float(body.target_valence)
            target_a = float(body.target_arousal)
            try:
                alpha = float(body.alpha) if getattr(body, 'alpha', None) is not None else 0.3
            except Exception:
                alpha = 0.3
            alpha = max(0.0, min(1.0, alpha))
            next_v = float(current_v + alpha * (target_v - current_v))
            next_a = float(current_a + alpha * (target_a - current_a))
            print(f"[experiment] TEST OVERRIDE: current_v={current_v:.4f}, current_a={current_a:.4f}, next_v={next_v:.4f}, next_a={next_a:.4f}")
            # expose to polling UI
            EXPERIMENT_STATE.update({
                "current_v": float(current_v),
                "current_a": float(current_a),
                "next_v": float(next_v),
                "next_a": float(next_a),
                "target_v": float(target_v),
                "target_a": float(target_a),
                "running": True,
                "seed": _ensure_session_seed(),
            })
            # skip the windowed inference path
        else:
            # Warm-up safety: if very few samples were provided (e.g. user pressed Start without real data),
            # skip per-window inference and use a neutral/relaxing prompt instead of reacting to near-zero data.
            MIN_SECONDS_WARMUP = 10
            MIN_SAMPLES_WARMUP = MODEL_EEG_FS * MIN_SECONDS_WARMUP
            if total < MIN_SAMPLES_WARMUP:
                print(f"[experiment] Warm-up: Data too short ({total} samples). Using default prompt and neutral scores.")
                # set neutral current scores (safe defaults)
                current_v, current_a = 0.0, 0.0
                # targets come from request
                target_v = float(body.target_valence)
                target_a = float(body.target_arousal)
                # compute Next Goal using interpolation: Current + alpha * (Target - Current)
                try:
                    alpha = float(body.alpha) if getattr(body, 'alpha', None) is not None else 0.5
                except Exception:
                    alpha = 0.5
                alpha = max(0.0, min(1.0, alpha))
                next_v = float(current_v + alpha * (target_v - current_v))
                next_a = float(current_a + alpha * (target_a - current_a))
                # fixed calm prompt for warm-up
                prompt = (
                    "Mood: Relaxing, Neutral, Calm; Genre: Ambient, Soft Electronic; "
                    "Instruments: Pad, Soft Piano; Tempo: Slow to moderate; "
                    "Starting session music."
                )
                # expose to polling UI
                EXPERIMENT_STATE.update({
                    "current_v": float(current_v),
                    "current_a": float(current_a),
                    "next_v": float(next_v),
                    "next_a": float(next_a),
                    "target_v": float(target_v),
                    "target_a": float(target_a),
                    "running": True,
                    "seed": _ensure_session_seed(),
                })
            else:
                # Slice into windows and run normal per-window inference
                if body.hop is not None:
                    # Convert incoming hop (Muse 256Hz domain) into model domain (200Hz).
                    hop = max(1, int(round(float(body.hop) * MODEL_EEG_FS / MUSE_INPUT_FS)))
                else:
                    hop = max(1, seq_len // 2)
                print(f"[experiment] slicing {total} samples into windows (seq_len={seq_len}, hop={hop})")
                try:
                    windows = _slice_windows(arr, seq_len=seq_len, hop=hop)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))

                n_windows = int(windows.shape[0])
                print(f"[experiment] windows count: {n_windows}")

                # Batch inference (all windows at once for GPU efficiency)
                scores = []
                print(f"[experiment] running batch inference on {n_windows} windows...")
                try:
                    batch_results = predict_batch_from_eeg("emotion", windows)
                    scores = [(float(r["valence"]), float(r["arousal"])) for r in batch_results]
                except Exception as e:
                    print(f"[experiment] batch inference failed, falling back to per-window: {e}")
                    for i in range(n_windows):
                        win = windows[i]
                        try:
                            res = predict_from_eeg("emotion", win)
                            v = float(res.get("valence", 0.5))
                            a = float(res.get("arousal", 0.5))
                        except Exception as e2:
                            print(f"[experiment] warning: inference failed on window {i}: {e2}")
                            v, a = 0.5, 0.5
                        scores.append((v, a))

                current_v, current_a = _mean_scores(scores)
                print(f"[experiment] current mean valence={current_v:.4f}, arousal={current_a:.4f}")
                # expose to polling UI
                EXPERIMENT_STATE.update({
                    "current_v": float(current_v),
                    "current_a": float(current_a),
                    "target_v": float(body.target_valence),
                    "target_a": float(body.target_arousal),
                    "running": True,
                    "seed": _ensure_session_seed(),
                })
                # compute Next Goal using interpolation: Current + alpha * (Target - Current)
                target_v = float(body.target_valence)
                target_a = float(body.target_arousal)
                try:
                    alpha = float(body.alpha) if getattr(body, 'alpha', None) is not None else 0.3
                except Exception:
                    alpha = 0.3
                alpha = max(0.0, min(1.0, alpha))
                next_v = float(current_v + alpha * (target_v - current_v))
                next_a = float(current_a + alpha * (target_a - current_a))
                print(f"[experiment] next goal valence={next_v:.4f}, arousal={next_a:.4f}")
        t_inference_done = time.time()
        prompt = build_prompt(
            current_v,
            current_a,
            next_v,
            next_a,
            target_v,
            target_a,
            base_prompt=body.base_prompt,
            duration=body.duration,
        )
        t_prompt_done = time.time()
        print(f"[experiment] prompt: {prompt}")

        EXPERIMENT_STATE.update({
            "duration": body.duration,
            "base_prompt": body.base_prompt,
            "provider": body.provider,
        })

        # Generate locally using MRT2
        print("[experiment] starting local generation...")
        # determine seed (use provided or random) and set RNGs for reproducibility
        seed_used = int(body.seed) if getattr(body, "seed", None) is not None else random.randint(0, 2**31 - 1)
        print(f"[experiment] using seed={seed_used}")
        random.seed(seed_used)
        np.random.seed(seed_used % (2**32))
        if torch is not None:
            try:
                torch.manual_seed(seed_used)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(seed_used)
            except Exception:
                pass
        try:
            # determine seconds to generate
            seconds_to_gen = float(body.duration) if (body.duration is not None) else 8.0
            if seconds_to_gen <= 0:
                raise HTTPException(status_code=400, detail="'duration' must be positive")
            # cap to reasonable upper bound to avoid runaway generation (e.g., 120s)
            if seconds_to_gen > 120:
                seconds_to_gen = 120.0

            # call local generator (reproducible via RNG seeding above)
            try:
                # Request in-memory WAV (avoid disk I/O)
                print(f"[experiment] generating with provider=mrt2 reset={is_new_mrt2_session}")
                t_gen_start = time.time()
                generated = _generate_local(body.provider, prompt=prompt, out_path=None, seconds_total=seconds_to_gen, reset=is_new_mrt2_session)
                t_gen_end = time.time()
            except Exception as e:
                print(f"[experiment] generation exception: {e}")
                import traceback
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Local generation failed: {e}")
        except Exception as e:
            print(f"[experiment] generation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Local generation failed: {e}")

        # generated can be bytes (when out_path=None) or a filepath string (fallback)
        # prepare common headers for responses
        headers = {
            "X-Seed": str(seed_used),
            "X-Current-Valence": f"{current_v:.6f}",
            "X-Current-Arousal": f"{current_a:.6f}",
            "X-Target-Valence": f"{target_v:.6f}",
            "X-Target-Arousal": f"{target_a:.6f}",
        }

        if isinstance(generated, (bytes, bytearray)):
            gen_time = (t_gen_end - t_gen_start) if ('t_gen_end' in locals() and 't_gen_start' in locals()) else None
            print(f"[experiment] generation finished, streaming in-memory bytes (seed={seed_used}) gen_time={gen_time}")
            _log_stage_timing(t_request_start, t_preprocess_done, t_inference_done, t_prompt_done, gen_time, seconds_to_gen)
            def _bytes_iter(b: bytes, chunk_size: int = 8192):
                bio = io.BytesIO(b)
                while True:
                    chunk = bio.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

            stream_iter = _bytes_iter(generated)
            media_type = "audio/wav"
            if gen_time is not None:
                headers["X-Gen-Time"] = f"{gen_time:.3f}"
            resp = StreamingResponse(stream_iter, media_type=media_type, headers=headers)
            EXPERIMENT_STATE["running"] = False
            return resp
        else:
            out_path = str(generated)
            print(f"[experiment] generation finished, streaming {out_path} (seed={seed_used})")
            gen_time = (t_gen_end - t_gen_start) if ('t_gen_end' in locals() and 't_gen_start' in locals()) else None
            _log_stage_timing(t_request_start, t_preprocess_done, t_inference_done, t_prompt_done, gen_time, seconds_to_gen)

        # mark not running after generation
        EXPERIMENT_STATE["running"] = False

        headers = {
            "X-Seed": str(seed_used),
            "X-Current-Valence": f"{current_v:.6f}",
            "X-Current-Arousal": f"{current_a:.6f}",
            "X-Target-Valence": f"{target_v:.6f}",
            "X-Target-Arousal": f"{target_a:.6f}",
        }

        # Rename/copy generated file into standardized filename for easy identification:
        # out_<currentV%>_<currentA%>_<targetV%>_<targetA%>.wav (percent integers)
        try:
            try:
                cv_pct = int(round(float(current_v) * 100))
            except Exception:
                cv_pct = 0
            try:
                ca_pct = int(round(float(current_a) * 100))
            except Exception:
                ca_pct = 0
            try:
                tv_pct = int(round(float(target_v) * 100))
            except Exception:
                tv_pct = 0
            try:
                ta_pct = int(round(float(target_a) * 100))
            except Exception:
                ta_pct = 0

            out_dir = os.path.dirname(out_path) or "."
            new_fname = f"out_{cv_pct}_{ca_pct}_{tv_pct}_{ta_pct}.wav"
            new_path = os.path.join(out_dir, new_fname)
            # copy so original generator file remains intact if needed
            shutil.copyfile(out_path, new_path)
            # expose filename in headers for client convenience
            headers["X-Output-Filename"] = new_fname
            stream_path = new_path
        except Exception as e:
            # fallback to original path if any error
            print(f"[experiment] warning: failed to rename/copy output file: {e}")
            stream_path = out_path

        return StreamingResponse(_file_iterator(stream_path), media_type="audio/wav", headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest")
async def experiment_latest():
    """Return latest experiment values for polling UIs."""
    return JSONResponse(EXPERIMENT_STATE)


@router.post("/stop")
async def experiment_stop():
    """Set running=False so UIs stop polling/indicate stopped."""
    EXPERIMENT_STATE["running"] = False
    EXPERIMENT_STATE["seed"] = None
    try:
        from ..music_ai.generate_mrt2_local import reset_session as reset_mrt2_session
        reset_mrt2_session()
    except Exception as e:
        # Best-effort: the mrt2 server may simply not be running, which
        # shouldn't block stopping the experiment.
        print(f"[experiment] mrt2 session reset skipped: {e}")
    return JSONResponse({"stopped": True})


@router.websocket("/ws")
async def experiment_ws(websocket: WebSocket):
    """Continuous MRT2 music generation over WebSocket, steered by a live
    target valence/arousal.

    One connection = one continuous session. Client sends one JSON message
    per chunk request: {"current_v", "current_a", "target_valence",
    "target_arousal", "alpha"?, "duration"?, "base_prompt"?}. `current_v`/
    `current_a` come from the client's own live valence/arousal (e.g. the
    shared liveVAAtom fed by /eeg_emotion/ws) -- this endpoint does no EEG
    inference itself.

    On success, replies with two frames in order: a JSON text frame
    {"prompt", "current_v", "current_a", "next_v", "next_a"}, then a binary
    frame with the raw WAV bytes. On failure, only a JSON {"error": ...}
    text frame (no binary frame follows), and the connection stays open.

    MRT2's stream continuation state (mrt2_poc/server.py's `_state`) is a
    single global, not per-session, so this connection can't assume it's the
    only session that's touched it: the first chunk on this connection
    always resets (reset=True) to start clean, and the connection resets
    the shared MRT2 state again on disconnect so whatever runs next (this
    endpoint again, or /experiment/feedback) also starts clean.
    """
    await websocket.accept()
    is_first_chunk = True
    try:
        while True:
            try:
                body = await websocket.receive_json()
                current_v = float(body["current_v"])
                current_a = float(body["current_a"])
                target_v = float(body["target_valence"])
                target_a = float(body["target_arousal"])
                alpha = float(body.get("alpha", 0.3))
                duration = float(body.get("duration", 8.0))
                next_v = current_v + alpha * (target_v - current_v)
                next_a = current_a + alpha * (target_a - current_a)
                prompt = build_prompt(
                    current_v, current_a, next_v, next_a, target_v, target_a,
                    base_prompt=body.get("base_prompt"), duration=duration,
                )
                audio_bytes = await asyncio.to_thread(
                    _generate_local, "mrt2", prompt=prompt, out_path=None,
                    seconds_total=duration, reset=is_first_chunk,
                )
                is_first_chunk = False
            except WebSocketDisconnect:
                raise
            except Exception as e:
                await websocket.send_json({"error": str(e)})
                continue
            try:
                await websocket.send_json({
                    "prompt": prompt,
                    "current_v": current_v,
                    "current_a": current_a,
                    "next_v": next_v,
                    "next_a": next_a,
                })
                await websocket.send_bytes(audio_bytes)
            except WebSocketDisconnect:
                raise
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        try:
            from ..music_ai.generate_mrt2_local import reset_session as reset_mrt2_session
            await asyncio.to_thread(reset_mrt2_session)
        except Exception as e:
            print(f"[experiment] mrt2 session reset skipped: {e}")
