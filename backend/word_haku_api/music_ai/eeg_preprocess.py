from typing import List
import numpy as np


MUSE_INPUT_FS = 256
MODEL_EEG_FS = 200


def resample_eeg_channels(samples: np.ndarray, src_fs: int = MUSE_INPUT_FS, dst_fs: int = MODEL_EEG_FS) -> np.ndarray:
    """Resample EEG array shaped (channels, time) from src_fs to dst_fs.

    Uses linear interpolation to avoid adding heavy DSP dependencies.
    """
    if samples.ndim != 2:
        raise ValueError("samples must be a 2D array (channels x time)")

    if src_fs <= 0 or dst_fs <= 0:
        raise ValueError("sampling rates must be positive")

    if src_fs == dst_fs:
        return samples

    channels, src_n = samples.shape
    if src_n <= 1:
        return samples

    dst_n = max(1, int(round(src_n * (float(dst_fs) / float(src_fs)))))
    if dst_n == src_n:
        return samples

    src_x = np.linspace(0.0, 1.0, num=src_n, endpoint=False)
    dst_x = np.linspace(0.0, 1.0, num=dst_n, endpoint=False)

    out = np.empty((channels, dst_n), dtype=np.float32)
    for ch in range(channels):
        out[ch, :] = np.interp(dst_x, src_x, samples[ch, :]).astype(np.float32)
    return out


def resample_eeg_batch(batch: np.ndarray, src_fs: int = MUSE_INPUT_FS, dst_fs: int = MODEL_EEG_FS) -> np.ndarray:
    """Resample EEG batch shaped (batch, channels, time) from src_fs to dst_fs."""
    if batch.ndim != 3:
        raise ValueError("batch must be a 3D array (batch x channels x time)")

    out: List[np.ndarray] = []
    for i in range(batch.shape[0]):
        out.append(resample_eeg_channels(batch[i], src_fs=src_fs, dst_fs=dst_fs))
    return np.stack(out, axis=0)
