import os
import torch
import torch.nn as nn
import numpy as np
import joblib
from mamba_ssm import Mamba
from typing import Optional, Dict, Any


class BiMambaBlock(nn.Module):
    def __init__(self, d_model, d_state=16, d_conv=4, expand=2, dropout=0.1):
        super().__init__()
        self.mamba_fwd = Mamba(d_model=d_model, d_state=d_state, d_conv=d_conv, expand=expand)
        self.mamba_bwd = Mamba(d_model=d_model, d_state=d_state, d_conv=d_conv, expand=expand)
        self.norm = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        res = x
        x = self.norm(x)
        out = self.mamba_fwd(x) + self.mamba_bwd(x.flip(dims=[1])).flip(dims=[1])
        return res + self.dropout(out)


class EEGMamba(nn.Module):
    """Architecture aligned with prod checkpoints (EEGMamba_Bi_Final)."""

    def __init__(self, n_channels=4, seq_len=100, n_classes=2, d_model=64, **_: Any):
        super().__init__()
        self.d_model = d_model
        self.proj = nn.Linear(n_channels, self.d_model)
        self.mamba_fwd = Mamba(d_model=self.d_model, d_state=16, d_conv=4, expand=2)
        self.mamba_bwd = Mamba(d_model=self.d_model, d_state=16, d_conv=4, expand=2)
        self.head = nn.Linear(self.d_model * 2, n_classes)

    def forward(self, x):
        # checkpoints expect bidirectional processing with global pooling
        x = x.permute(0, 2, 1)
        x = self.proj(x)
        f_out = self.mamba_fwd(x)
        b_out = self.mamba_bwd(x.flip(1)).flip(1)
        feat = torch.cat([f_out.mean(1), b_out.mean(1)], dim=1)
        return self.head(feat)


class EmotionModel:
    """Wrapper that loads valence and arousal EEGMamba models and runs prediction.

    Use by creating an instance with explicit paths for valence/arousal .pth files.
    """
    def __init__(self, valence_path: str, arousal_path: str, params: Optional[Dict[str, Any]] = None):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        default_assets_dir = self._default_assets_dir()
        valence_dir = self._resolve_asset_dir(valence_path, default_assets_dir)
        arousal_dir = self._resolve_asset_dir(arousal_path, default_assets_dir)
        self.valence_path = os.path.join(valence_dir, "prod_Mamba_Bi_4ch_Valence.pth")
        self.arousal_path = os.path.join(arousal_dir, "prod_Mamba_Bi_4ch_Arousal.pth")
        self.valence_stats_path = os.path.join(valence_dir, "prod_Mamba_Bi_4ch_Valence_stats.joblib")
        self.arousal_stats_path = os.path.join(arousal_dir, "prod_Mamba_Bi_4ch_Arousal_stats.joblib")
        self.mean_v: Optional[torch.Tensor] = None
        self.std_v: Optional[torch.Tensor] = None
        self.mean_a: Optional[torch.Tensor] = None
        self.std_a: Optional[torch.Tensor] = None
        # default params
        default_params = {
            'n_channels': 4,
            'seq_len': 100,
            'n_classes': 2,
            'd_model': 64,
            'n_layers': 2,
            'dropout': 0.1
        }
        if params is None:
            params = default_params
        else:
            # fill missing keys with defaults
            for k, v in default_params.items():
                params.setdefault(k, v)

        params['n_channels'] = 4
        self.params = params

        print(f"EmotionModel device: {self.device}")

        # instantiate models
        try:
            self.model_v = EEGMamba(n_channels=params['n_channels'], seq_len=params['seq_len'],
                                    n_classes=params['n_classes'], d_model=params['d_model'],
                                    n_layers=params['n_layers'], dropout=params['dropout']).to(self.device)
        except Exception as e:
            self.model_v = None
            print(f"Failed to instantiate valence model: {e}")

        try:
            self.model_a = EEGMamba(n_channels=params['n_channels'], seq_len=params['seq_len'],
                                    n_classes=params['n_classes'], d_model=params['d_model'],
                                    n_layers=params['n_layers'], dropout=params['dropout']).to(self.device)
        except Exception as e:
            self.model_a = None
            print(f"Failed to instantiate arousal model: {e}")

        # load weights
        try:
            if self.model_v is not None and os.path.exists(self.valence_path):
                state_v = torch.load(self.valence_path, map_location=self.device, weights_only=True)
                # support either full checkpoint or state_dict
                if isinstance(state_v, dict) and 'state_dict' in state_v:
                    state_v = state_v['state_dict']
                self.model_v.load_state_dict(state_v)
                self.model_v.eval()
                print("✅ Valence model loaded.")
            else:
                print(f"Valence path does not exist or model not instantiated: {self.valence_path}")
                self.model_v = None
        except Exception as e:
            print(f"❌ Failed to load Valence model: {e}")
            self.model_v = None

        try:
            if self.model_a is not None and os.path.exists(self.arousal_path):
                state_a = torch.load(self.arousal_path, map_location=self.device, weights_only=True)
                if isinstance(state_a, dict) and 'state_dict' in state_a:
                    state_a = state_a['state_dict']
                self.model_a.load_state_dict(state_a)
                self.model_a.eval()
                print("✅ Arousal model loaded.")
            else:
                print(f"Arousal path does not exist or model not instantiated: {self.arousal_path}")
                self.model_a = None
        except Exception as e:
            print(f"❌ Failed to load Arousal model: {e}")
            self.model_a = None

        self.mean_v, self.std_v = self._load_stats(self.valence_stats_path)
        self.mean_a, self.std_a = self._load_stats(self.arousal_stats_path)

    def predict(self, eeg_data: np.ndarray):
        """
        eeg_data: numpy array shape (channels, seq_len) or (batch, channels, seq_len)
        returns: (valence_prob, arousal_prob)
        """
        if self.model_v is None or self.model_a is None:
            print("Warning: Models not loaded correctly.")
            return 0.5, 0.5

        try:
            x = torch.tensor(eeg_data, dtype=torch.float32)
            if x.dim() == 2:
                x = x.unsqueeze(0)
            x = x.to(self.device)

            x_v = self._normalize_with_stats(x, self.mean_v, self.std_v)
            x_a = self._normalize_with_stats(x, self.mean_a, self.std_a)

            with torch.no_grad():
                logits_v = self.model_v(x_v)
                logits_a = self.model_a(x_a)

                prob_v = torch.softmax(logits_v, dim=1)[0, 1].item()
                prob_a = torch.softmax(logits_a, dim=1)[0, 1].item()

            return prob_v, prob_a

        except Exception as e:
            print(f"Prediction Error: {e}")
            return 0.5, 0.5

    def predict_batch(self, eeg_batch: np.ndarray):
        """Batch prediction for multiple windows.

        eeg_batch: numpy array shape (batch, channels, seq_len)
        returns: list of (valence_prob, arousal_prob) tuples
        """
        if self.model_v is None or self.model_a is None:
            print("Warning: Models not loaded correctly.")
            return [(0.5, 0.5)] * eeg_batch.shape[0]

        try:
            x = torch.tensor(eeg_batch, dtype=torch.float32)
            if x.dim() == 2:
                x = x.unsqueeze(0)
            x = x.to(self.device)

            x_v = self._normalize_with_stats(x, self.mean_v, self.std_v)
            x_a = self._normalize_with_stats(x, self.mean_a, self.std_a)

            with torch.no_grad():
                logits_v = self.model_v(x_v)
                logits_a = self.model_a(x_a)

                probs_v = torch.softmax(logits_v, dim=1)[:, 1].cpu().tolist()
                probs_a = torch.softmax(logits_a, dim=1)[:, 1].cpu().tolist()

            return list(zip(probs_v, probs_a))

        except Exception as e:
            print(f"Batch Prediction Error: {e}")
            return [(0.5, 0.5)] * eeg_batch.shape[0]

    @classmethod
    def load_from_checkpoints(cls, valence_path: str, arousal_path: str, params: Optional[Dict[str, Any]] = None, device: Optional[torch.device] = None):
        """
        Create an EmotionModel by detecting per-checkpoint dimensions (d_model, seq_len, n_channels)
        and instantiating internal EEGMamba models accordingly, then loading weights.

        Falls back to non-strict loading if strict load fails.
        """
        if device is None:
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # helper: load state_dict (or inner state_dict) on CPU
        def _load_state(path):
            if not os.path.exists(path):
                return None
            sd = torch.load(path, map_location='cpu', weights_only=True)
            if isinstance(sd, dict) and 'state_dict' in sd:
                sd = sd['state_dict']
            return sd

        default_assets_dir = cls._default_assets_dir()
        valence_dir = cls._resolve_asset_dir(valence_path, default_assets_dir)
        arousal_dir = cls._resolve_asset_dir(arousal_path, default_assets_dir)
        valence_path = os.path.join(valence_dir, "prod_Mamba_Bi_4ch_Valence.pth")
        arousal_path = os.path.join(arousal_dir, "prod_Mamba_Bi_4ch_Arousal.pth")
        valence_stats_path = os.path.join(valence_dir, "prod_Mamba_Bi_4ch_Valence_stats.joblib")
        arousal_stats_path = os.path.join(arousal_dir, "prod_Mamba_Bi_4ch_Arousal_stats.joblib")

        sd_v = _load_state(valence_path)
        sd_a = _load_state(arousal_path)

        # default params if not given
        default_params = {
            'n_channels': 4,
            'seq_len': 100,
            'n_classes': 2,
            'd_model': 64,
            'n_layers': 2,
            'dropout': 0.1
        }
        if params is None:
            params = default_params.copy()
        else:
            for k, v in default_params.items():
                params.setdefault(k, v)

        # detect per-checkpoint settings
        def detect_params_from_state(sd, fallback):
            out = fallback.copy()
            if sd is None:
                return out
            # detect d_model from input_proj.weight shape[0]
            try:
                if 'input_proj.weight' in sd:
                    w = sd['input_proj.weight']
                    out['d_model'] = int(w.shape[0])
                    out['n_channels'] = int(w.shape[1])
            except Exception:
                pass
            # detect seq_len from pos_embed if available (pos_embed shape: 1, seq_len+1, d_model)
            try:
                if 'pos_embed' in sd:
                    p = sd['pos_embed']
                    out['seq_len'] = int(p.shape[1]) - 1
            except Exception:
                pass
            return out

        pv = detect_params_from_state(sd_v, params)
        pa = detect_params_from_state(sd_a, params)
        pv['n_channels'] = 4
        pa['n_channels'] = 4

        # instantiate wrapper without running the regular constructor weight-loading
        model_wrapper = cls.__new__(cls)
        model_wrapper.device = device
        params['n_channels'] = 4
        model_wrapper.params = params
        model_wrapper.valence_path = valence_path
        model_wrapper.arousal_path = arousal_path
        model_wrapper.valence_stats_path = valence_stats_path
        model_wrapper.arousal_stats_path = arousal_stats_path
        model_wrapper.mean_v = None
        model_wrapper.std_v = None
        model_wrapper.mean_a = None
        model_wrapper.std_a = None
        # create model instances per detected config
        try:
            mv = EEGMamba(n_channels=pv.get('n_channels', params['n_channels']), seq_len=pv.get('seq_len', params['seq_len']), n_classes=params.get('n_classes', 2), d_model=pv.get('d_model', params['d_model']), n_layers=params.get('n_layers', 2), dropout=params.get('dropout', 0.1)).to(device)
        except Exception as e:
            print(f"Failed to instantiate valence model with detected params: {e}")
            mv = None
        try:
            ma = EEGMamba(n_channels=pa.get('n_channels', params['n_channels']), seq_len=pa.get('seq_len', params['seq_len']), n_classes=params.get('n_classes', 2), d_model=pa.get('d_model', params['d_model']), n_layers=params.get('n_layers', 2), dropout=params.get('dropout', 0.1)).to(device)
        except Exception as e:
            print(f"Failed to instantiate arousal model with detected params: {e}")
            ma = None

        model_wrapper.model_v = mv
        model_wrapper.model_a = ma

        # attempt to load state dicts (strict True, then fallback False)
        def _try_load(model, sd, path, name):
            if model is None or sd is None:
                print(f"{name} model or state_dict missing; skipping load for {path}")
                return False
            try:
                model.load_state_dict(sd)
                model.eval()
                print(f"✅ {name} model loaded (strict=True): {path}")
                return True
            except Exception as e:
                print(f"strict load failed for {name}: {e}; trying strict=False")
                try:
                    model.load_state_dict(sd, strict=False)
                    model.eval()
                    print(f"✅ {name} model loaded (strict=False): {path}")
                    return True
                except Exception as e2:
                    print(f"❌ Failed to load {name} model from {path}: {e2}")
                    return False

        _try_load(model_wrapper.model_v, sd_v, valence_path, 'Valence')
        _try_load(model_wrapper.model_a, sd_a, arousal_path, 'Arousal')

        model_wrapper.mean_v, model_wrapper.std_v = model_wrapper._load_stats(valence_stats_path)
        model_wrapper.mean_a, model_wrapper.std_a = model_wrapper._load_stats(arousal_stats_path)

        return model_wrapper

    @staticmethod
    def _default_assets_dir() -> str:
        env_dir = os.getenv("EMOTION_MODEL_DIR")
        if env_dir and os.path.isdir(env_dir):
            return env_dir
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

    @staticmethod
    def _resolve_asset_dir(provided_path: Optional[str], fallback_dir: str) -> str:
        if provided_path:
            if os.path.isdir(provided_path):
                return provided_path
            candidate = os.path.dirname(provided_path)
            if candidate and os.path.isdir(candidate):
                return candidate
        return fallback_dir

    def _load_stats(self, path: str):
        if not os.path.exists(path):
            print(f"Stats file missing: {path}")
            return None, None
        try:
            mean, std = joblib.load(path)
            mean_tensor = torch.tensor(mean, dtype=torch.float32)
            std_tensor = torch.tensor(std, dtype=torch.float32)
            return mean_tensor, std_tensor
        except Exception as exc:
            print(f"Failed to load stats from {path}: {exc}")
            return None, None

    def _normalize_with_stats(self, x: torch.Tensor, mean: Optional[torch.Tensor], std: Optional[torch.Tensor]):
        if mean is None or std is None:
            return x
        mean = mean.to(x.device)
        std = std.to(x.device)
        while mean.dim() < x.dim():
            mean = mean.unsqueeze(0)
            std = std.unsqueeze(0)
        return (x - mean) / (std + 1e-6)
