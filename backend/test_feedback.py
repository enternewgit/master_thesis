import requests
from test_helpers import do_test

URL = "http://localhost:8000/experiment/feedback"

scenario_happy = {
    "samples": [[0]*100, [0]*100, [0]*100, [0]*100],
    "target_valence": 1.0,
    "target_arousal": 1.0,
    "alpha": 0.3,
    "base_prompt": "A {dynamics} {texture} piece played by {instruments}. Key of {key_hint}, Tempo {bpm} BPM.",
    "duration": 4
}

scenario_sad = {
    "samples": [[0]*100, [0]*100, [0]*100, [0]*100],
    "target_valence": 0.0,
    "target_arousal": 0.0,
    "alpha": 0.3,
    "base_prompt": "A {dynamics} {texture} piece played by {instruments}. Key of {key_hint}, Tempo {bpm} BPM.",
    "duration": 4
}

if __name__ == "__main__":
    alphas = [0.1, 0.7]
    for a in alphas:
        s_h = dict(scenario_happy)
        s_h['alpha'] = a
        do_test(f"Happy -> High Arousal/Valence (alpha={a})", s_h, f"out_happy_a{int(a*100)}.wav")

        s_s = dict(scenario_sad)
        s_s['alpha'] = a
        do_test(f"Sad -> Low Arousal/Valence (alpha={a})", s_s, f"out_sad_a{int(a*100)}.wav")