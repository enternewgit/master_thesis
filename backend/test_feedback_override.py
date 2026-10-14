import requests
import json
import os
from test_helpers import do_test

URL = "http://localhost:8000/experiment/feedback"


if __name__ == "__main__":
    # 設計: テスト向けに current_v/current_a を上書きしてプロンプト生成経路を検証する
    tests = [
        {
            "name": "Override -> Happy-like current",
            "override_current_valence": 0.8,
            "override_current_arousal": 0.7,
            "target_valence": 1.0,
            "target_arousal": 1.0,
            "alpha": 0.5,
            "fname": "out_override_happy.wav",
        },
        {
            "name": "Override -> Sad-like current",
            "override_current_valence": 0.2,
            "override_current_arousal": 0.2,
            "target_valence": 0.0,
            "target_arousal": 0.0,
            "alpha": 0.5,
            "fname": "out_override_sad.wav",
        },
    ]

    # Minimal placeholder samples (length must meet server-side minimum for non-override path,
    # but because we set override_current=True server will skip inference.)
    samples = [[0]*1024 for _ in range(4)]

    for t in tests:
        payload = {
            "samples": samples,
            "target_valence": t["target_valence"],
            "target_arousal": t["target_arousal"],
            "alpha": t["alpha"],
            "override_current": True,
            "override_current_valence": t["override_current_valence"],
            "override_current_arousal": t["override_current_arousal"],
            "duration": 10,
        }
        # request filename used only as temporary holder; final name derived from headers
        do_test(t["name"], payload, t["fname"])
