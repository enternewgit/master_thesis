# Realtime Valence/Arousal via WebSocket Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a continuous, low-latency valence/arousal prediction path over WebSocket, displayed as a new floating card in `Chart`, independent of the existing record→generate→play experiment loop.

**Architecture:** A new `@router.websocket("/ws")` endpoint on the existing `/eeg_emotion` router reuses the same EEGMamba model/preprocessing as `POST /eeg_emotion/predict` via a shared helper function. A new frontend floating-card component opens a WebSocket while visible and the EEG device is connected, sends a fresh EEG window every 500ms, and renders the live valence/arousal both locally and into the existing shared `liveVAAtom`.

**Tech Stack:** FastAPI (`WebSocket`/`WebSocketDisconnect`), existing EEGMamba model (`music_ai/loader.py`, `music_ai/infer.py`, `music_ai/eeg_preprocess.py`), Next.js/React client component, jotai atoms, browser `WebSocket` API.

**Spec:** `docs/superpowers/specs/2026-08-25-realtime-emotion-websocket-design.md`

## Global Constraints

- `backend/` and `frontend/` are independent, team-owned git repositories (see project `CLAUDE.md`). **Do not run `git add`/`git commit`/`git push` inside either directory at any point in this plan** — leave changes unstaged for the user to review and commit themselves. This repo's own git (the one containing this plan) is not affected by that restriction.
- No new test framework dependencies (no pytest, no jest/vitest) — neither repo has one today, and adding one is out of scope for this feature (per spec's Testing section). Verification scripts in this plan use only what's already available: `fastapi.testclient.TestClient` (backend, uses the already-installed `httpx`) and `npx tsx` (frontend, already resolvable via npx).
- Match existing code conventions exactly: relative imports between sibling component directories (e.g. `../museClientAtom`, `../EEG/EEGatoms`), `"use client"` directive on frontend components that use hooks/browser APIs, `@/lib/...` import alias for shared frontend helpers.
- Do not modify `Player.tsx` (explicit decision during design — its existing embedded circumplex plot and one-shot analyze/generate flow stay as-is).

---

## File Structure

- **Modify:** `backend/word_haku_api/routers/route_eeg_emotion.py` — extract shared `_predict_from_samples()` helper (Task 1), add `/ws` WebSocket endpoint using it (Task 2).
- **Modify:** `frontend/src/lib/apiBase.ts` — add `getWsBase()` (Task 3).
- **Create:** `frontend/src/app/[locale]/components/Chart/RealtimeEmotion.tsx` — the new floating-card component (Task 4).
- **Modify:** `frontend/src/app/[locale]/components/Chart/chart.tsx` — register the new card (Task 5).

Tasks are ordered so each depends only on earlier tasks: 1 → 2 (same file, helper before endpoint), 3 is independent (pure frontend helper), 4 depends on 3 (imports `getWsBase`), 5 depends on 4 (imports the component).

---

### Task 1: Extract shared `_predict_from_samples()` helper in the backend

**Files:**
- Modify: `backend/word_haku_api/routers/route_eeg_emotion.py`
- Verify: `backend/verify_predict_helper.py` (temporary — delete before finishing this task)

**Interfaces:**
- Produces: `_predict_from_samples(raw_samples: list) -> dict` — module-level function in `route_eeg_emotion.py`. Raises `fastapi.HTTPException` (status 400) for invalid/malformed input, `RuntimeError` if the model itself can't be loaded, or returns `{"valence": float, "arousal": float}` on success. Task 2 calls this directly.

The current `predict_emotion()` (`POST /predict`) inlines: numpy conversion, lazy model loading, shape validation against the model's `n_channels`/`seq_len`, 256→200Hz resampling, and the `predict_from_eeg` call, all in one function. This task pulls everything except the outer try/except translation into a standalone function so the new WebSocket endpoint (Task 2) can reuse it byte-for-byte instead of duplicating ~60 lines of validation logic.

Note: the current endpoint's outer `except Exception as e: raise HTTPException(status_code=500, ...)` incidentally catches and re-wraps any `HTTPException` raised earlier in the same function (since `HTTPException` is an `Exception`), turning e.g. an empty-samples `400` into a `500` with a mangled detail message (`"400: 'samples' is empty"`). This refactor fixes that as a natural side effect of giving the extracted function a clean contract (`HTTPException` = client error, `RuntimeError` = server error) — the wrapper now re-raises `HTTPException` as-is instead of swallowing it. This doesn't change any caller's behavior: `Player.tsx`/`EEGForm.tsx` only check `res.ok` (false for both 400 and 500), never the specific status code.

- [ ] **Step 1: Write the failing verification script**

Create `backend/verify_predict_helper.py`:

```python
"""Temporary verification script for Task 1 — delete after this task passes."""
import numpy as np
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from word_haku_api.routers import route_eeg_emotion as mod

fake_model = MagicMock()
fake_model.params = {"n_channels": 4, "seq_len": 100}

with patch.object(mod, "get_model", return_value=fake_model), \
     patch.object(mod, "predict_from_eeg", return_value={"valence": 0.5, "arousal": 0.5}):

    # Valid 2D input: (4 channels, 128 samples @256Hz) resamples to (4, 100) — matches
    # fake_model.params exactly (dst_n = round(128 * 200/256) == 100).
    valid = np.zeros((4, 128)).tolist()
    result = mod._predict_from_samples(valid)
    assert result == {"valence": 0.5, "arousal": 0.5}, result

    # Empty samples -> HTTPException 400 (not 500)
    try:
        mod._predict_from_samples([])
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400, e.status_code

    # Wrong channel count (3 instead of 4) -> HTTPException 400
    try:
        mod._predict_from_samples(np.zeros((3, 128)).tolist())
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400, e.status_code

print("PASS: _predict_from_samples")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python verify_predict_helper.py`
Expected: FAIL with `AttributeError: module 'word_haku_api.routers.route_eeg_emotion' has no attribute '_predict_from_samples'` (or similar — the function doesn't exist yet).

- [ ] **Step 3: Extract the helper**

In `backend/word_haku_api/routers/route_eeg_emotion.py`, replace:

```python
@router.post("/predict")
async def predict_emotion(body: EEGPredictBody):
    try:
        arr = np.array(body.samples, dtype=float)

        # If the model wasn't loaded at startup, try lazy-loading it now
        if get_model('emotion') is None:
            valence_path = config('EMO_VALENCE_PATH', default=os.path.join(os.path.dirname(__file__), '..', '..', '..', 'valence.pth'))
            arousal_path = config('EMO_AROUSAL_PATH', default=os.path.join(os.path.dirname(__file__), '..', '..', '..', 'arousal.pth'))
            try:
                load_emotion_model('emotion', valence_path=valence_path, arousal_path=arousal_path)
            except Exception as e:
                raise RuntimeError(f"Failed to load emotion model: {e}")

        # Validate input shape and values against model params
        model = get_model('emotion')
        if model is None:
            raise RuntimeError("Model 'emotion' not loaded")

        params = getattr(model, 'params', {}) or {}
        expected_channels = int(params.get('n_channels', 4))
        expected_seq = int(params.get('seq_len', 100))

        if arr.size == 0:
            raise HTTPException(status_code=400, detail="'samples' is empty")

        if not np.isfinite(arr).all():
            raise HTTPException(status_code=400, detail="'samples' contains non-finite values (NaN or Inf)")

        # Shared preprocessing with /experiment/feedback:
        # assume Muse2 stream is 256Hz and resample to model-side 200Hz before inference.
        # Compatibility fallback: if already aligned with expected_seq, keep original.
        arr_before = arr
        try:
            if arr.ndim == 2:
                arr = resample_eeg_channels(arr, src_fs=MUSE_INPUT_FS, dst_fs=MODEL_EEG_FS)
            elif arr.ndim == 3:
                arr = resample_eeg_batch(arr, src_fs=MUSE_INPUT_FS, dst_fs=MODEL_EEG_FS)
            else:
                raise HTTPException(status_code=400, detail="'samples' must be a 2D (channels x seq) or 3D (batch x channels x seq) numeric array")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"EEG resampling failed: {e}")

        if arr.ndim == 2:
            # (channels, seq_len)
            ch, seq = arr.shape
            if ch != expected_channels or seq != expected_seq:
                ch0, seq0 = arr_before.shape
                if ch0 == expected_channels and seq0 == expected_seq:
                    arr = arr_before
                else:
                    raise HTTPException(status_code=400, detail=f"Expected samples shape (channels={expected_channels}, seq_len={expected_seq}) for 2D input, got ({ch}, {seq})")
        elif arr.ndim == 3:
            # (batch, channels, seq_len)
            b, ch, seq = arr.shape
            if ch != expected_channels or seq != expected_seq:
                b0, ch0, seq0 = arr_before.shape
                if ch0 == expected_channels and seq0 == expected_seq:
                    arr = arr_before
                else:
                    raise HTTPException(status_code=400, detail=f"Expected samples shape (batch, channels={expected_channels}, seq_len={expected_seq}) for 3D input, got (batch={b}, channels={ch}, seq_len={seq})")
        else:
            raise HTTPException(status_code=400, detail="'samples' must be a 2D (channels x seq) or 3D (batch x channels x seq) numeric array")

        res = predict_from_eeg('emotion', arr)
        return res
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

with:

```python
def _predict_from_samples(raw_samples: list) -> dict:
    """Validate, preprocess, and run EEGMamba prediction on raw EEG samples.

    `raw_samples` is a 2D (channels x seq) or 3D (batch x channels x seq)
    nested list/array of floats at the raw 256Hz Muse sample rate. Raises
    HTTPException (400) for client-caused errors (bad shape/values), or
    RuntimeError if the model itself isn't available. Shared by both the
    POST /predict endpoint and the /ws WebSocket endpoint.
    """
    arr = np.array(raw_samples, dtype=float)

    # If the model wasn't loaded at startup, try lazy-loading it now
    if get_model('emotion') is None:
        valence_path = config('EMO_VALENCE_PATH', default=os.path.join(os.path.dirname(__file__), '..', '..', '..', 'valence.pth'))
        arousal_path = config('EMO_AROUSAL_PATH', default=os.path.join(os.path.dirname(__file__), '..', '..', '..', 'arousal.pth'))
        try:
            load_emotion_model('emotion', valence_path=valence_path, arousal_path=arousal_path)
        except Exception as e:
            raise RuntimeError(f"Failed to load emotion model: {e}")

    # Validate input shape and values against model params
    model = get_model('emotion')
    if model is None:
        raise RuntimeError("Model 'emotion' not loaded")

    params = getattr(model, 'params', {}) or {}
    expected_channels = int(params.get('n_channels', 4))
    expected_seq = int(params.get('seq_len', 100))

    if arr.size == 0:
        raise HTTPException(status_code=400, detail="'samples' is empty")

    if not np.isfinite(arr).all():
        raise HTTPException(status_code=400, detail="'samples' contains non-finite values (NaN or Inf)")

    # Shared preprocessing with /experiment/feedback:
    # assume Muse2 stream is 256Hz and resample to model-side 200Hz before inference.
    # Compatibility fallback: if already aligned with expected_seq, keep original.
    arr_before = arr
    try:
        if arr.ndim == 2:
            arr = resample_eeg_channels(arr, src_fs=MUSE_INPUT_FS, dst_fs=MODEL_EEG_FS)
        elif arr.ndim == 3:
            arr = resample_eeg_batch(arr, src_fs=MUSE_INPUT_FS, dst_fs=MODEL_EEG_FS)
        else:
            raise HTTPException(status_code=400, detail="'samples' must be a 2D (channels x seq) or 3D (batch x channels x seq) numeric array")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"EEG resampling failed: {e}")

    if arr.ndim == 2:
        # (channels, seq_len)
        ch, seq = arr.shape
        if ch != expected_channels or seq != expected_seq:
            ch0, seq0 = arr_before.shape
            if ch0 == expected_channels and seq0 == expected_seq:
                arr = arr_before
            else:
                raise HTTPException(status_code=400, detail=f"Expected samples shape (channels={expected_channels}, seq_len={expected_seq}) for 2D input, got ({ch}, {seq})")
    elif arr.ndim == 3:
        # (batch, channels, seq_len)
        b, ch, seq = arr.shape
        if ch != expected_channels or seq != expected_seq:
            b0, ch0, seq0 = arr_before.shape
            if ch0 == expected_channels and seq0 == expected_seq:
                arr = arr_before
            else:
                raise HTTPException(status_code=400, detail=f"Expected samples shape (batch, channels={expected_channels}, seq_len={expected_seq}) for 3D input, got (batch={b}, channels={ch}, seq_len={seq})")
    else:
        raise HTTPException(status_code=400, detail="'samples' must be a 2D (channels x seq) or 3D (batch x channels x seq) numeric array")

    return predict_from_eeg('emotion', arr)


@router.post("/predict")
async def predict_emotion(body: EEGPredictBody):
    try:
        return _predict_from_samples(body.samples)
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 4: Run the verification script to see it pass**

Run: `cd backend && .venv/bin/python verify_predict_helper.py`
Expected: PASS, prints `PASS: _predict_from_samples`

- [ ] **Step 5: Delete the temporary verification script**

Run: `cd backend && rm verify_predict_helper.py`

- [ ] **Step 6: Do not commit**

Per Global Constraints, `backend/` is a separate team repo — leave this change unstaged. Do not run `git add`/`git commit` here.

---

### Task 2: Add the `/eeg_emotion/ws` WebSocket endpoint

**Files:**
- Modify: `backend/word_haku_api/routers/route_eeg_emotion.py`
- Verify: `backend/verify_ws_endpoint.py` (temporary — delete before finishing this task)

**Interfaces:**
- Consumes: `_predict_from_samples(raw_samples: list) -> dict` (Task 1).
- Produces: `GET`-upgraded WebSocket route at `/eeg_emotion/ws` (full path, since this router is mounted with prefix `/eeg_emotion` in `main.py`). Accepts `{"samples": <list>}` JSON messages, replies with `{"valence": float, "arousal": float}` on success or `{"error": <string>}` on failure. Connection stays open after an error.

- [ ] **Step 1: Write the failing verification script**

Create `backend/verify_ws_endpoint.py`:

```python
"""Temporary verification script for Task 2 — delete after this task passes."""
import numpy as np
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from word_haku_api.routers import route_eeg_emotion as mod

app = FastAPI()
app.include_router(mod.router)
client = TestClient(app)

fake_model = MagicMock()
fake_model.params = {"n_channels": 4, "seq_len": 100}

valid = np.zeros((4, 128)).tolist()  # resamples to (4, 100), matches fake_model.params

with patch.object(mod, "get_model", return_value=fake_model), \
     patch.object(mod, "predict_from_eeg", return_value={"valence": 0.7, "arousal": 0.2}):

    with client.websocket_connect("/ws") as ws:
        # valid window -> prediction back
        ws.send_json({"samples": valid})
        resp = ws.receive_json()
        assert resp == {"valence": 0.7, "arousal": 0.2}, resp

        # invalid window -> error message, connection stays open
        ws.send_json({"samples": []})
        resp2 = ws.receive_json()
        assert "error" in resp2, resp2

        # connection still alive after an error: send another valid window
        ws.send_json({"samples": valid})
        resp3 = ws.receive_json()
        assert resp3 == {"valence": 0.7, "arousal": 0.2}, resp3

print("PASS: /eeg_emotion/ws")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python verify_ws_endpoint.py`
Expected: FAIL — `client.websocket_connect("/ws")` errors because no such route exists yet (404/connection rejected).

- [ ] **Step 3: Add the WebSocket endpoint**

In `backend/word_haku_api/routers/route_eeg_emotion.py`, change the import line:

```python
from fastapi import APIRouter, HTTPException
```

to:

```python
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
```

Then add this at the end of the file (after the existing `/status` endpoint):

```python
@router.websocket("/ws")
async def eeg_emotion_ws(websocket: WebSocket):
    """Continuous valence/arousal prediction over WebSocket.

    Client sends {"samples": <2D or 3D nested list>} messages (same shape
    POST /predict accepts) at whatever cadence it likes; each message gets
    one prediction back. No producer/consumer queue like some reference
    implementations use — the client already paces sends (500ms in the
    frontend) and inference is fast, so a plain sequential
    receive->infer->send loop is enough.
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            try:
                result = _predict_from_samples(data.get("samples", []))
                await websocket.send_json(result)
            except HTTPException as e:
                await websocket.send_json({"error": str(e.detail)})
            except Exception as e:
                await websocket.send_json({"error": str(e)})
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 4: Run the verification script to see it pass**

Run: `cd backend && .venv/bin/python verify_ws_endpoint.py`
Expected: PASS, prints `PASS: /eeg_emotion/ws`

- [ ] **Step 5: Delete the temporary verification script**

Run: `cd backend && rm verify_ws_endpoint.py`

- [ ] **Step 6: Do not commit**

Per Global Constraints, leave this change unstaged.

---

### Task 3: Add `getWsBase()` to the frontend

**Files:**
- Modify: `frontend/src/lib/apiBase.ts`
- Verify: `frontend/verify_wsbase.ts` (temporary — delete before finishing this task)

**Interfaces:**
- Consumes: `getApiBase(): string` (already exists in this file).
- Produces: `getWsBase(): string` — derives a `ws://`/`wss://` URL from `getApiBase()`'s result. Task 4 imports this.

- [ ] **Step 1: Write the failing verification script**

Create `frontend/verify_wsbase.ts`:

```typescript
// Temporary verification script for Task 3 — delete after this task passes.
import assert from "node:assert";
import { getApiBase, getWsBase } from "./src/lib/apiBase";

function withEnv(vars: Record<string, string | undefined>, fn: () => void) {
  const prev: Record<string, string | undefined> = {};
  for (const k of Object.keys(vars)) {
    prev[k] = process.env[k];
    process.env[k] = vars[k];
  }
  try {
    fn();
  } finally {
    for (const k of Object.keys(vars)) {
      if (prev[k] === undefined) delete process.env[k];
      else process.env[k] = prev[k];
    }
  }
}

// Case 1: no window (server-side render), relative NEXT_PUBLIC_API_URL configured.
withEnv({ NEXT_PUBLIC_API_URL: "/braingram_mg_api" }, () => {
  delete (globalThis as any).window;
  assert.strictEqual(getApiBase(), "/braingram_mg_api", "case1 api");
  assert.strictEqual(getWsBase(), "ws:///braingram_mg_api", "case1 ws");
});

// Case 2: window present, NOT on the local dev port, relative config -> proxied through
// Apache, so keep the relative path and derive ws(s) scheme + host from window.location.
withEnv({ NEXT_PUBLIC_API_URL: "/braingram_mg_api" }, () => {
  (globalThis as any).window = { location: { port: "", protocol: "https:", host: "dna00.bio.kyutech.ac.jp" } };
  assert.strictEqual(getApiBase(), "/braingram_mg_api", "case2 api");
  assert.strictEqual(getWsBase(), "wss://dna00.bio.kyutech.ac.jp/braingram_mg_api", "case2 ws");
});

// Case 3: window present, ON port 3001 (bypassing Apache) -> falls back to the absolute
// local backend URL.
withEnv({ NEXT_PUBLIC_API_URL: "/braingram_mg_api" }, () => {
  (globalThis as any).window = { location: { port: "3001", protocol: "http:", host: "localhost:3001" } };
  assert.strictEqual(getApiBase(), "http://localhost:8001", "case3 api");
  assert.strictEqual(getWsBase(), "ws://localhost:8001", "case3 ws");
});

console.log("PASS: getWsBase");
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx tsx verify_wsbase.ts`
Expected: FAIL — `getWsBase` is not exported from `./src/lib/apiBase` yet (TypeScript/import error).

- [ ] **Step 3: Add `getWsBase()`**

In `frontend/src/lib/apiBase.ts`, add this function after `getApiBase()`:

```typescript
export function getWsBase(): string {
  const base = getApiBase();
  if (base.startsWith("https://")) return "wss://" + base.slice("https://".length);
  if (base.startsWith("http://")) return "ws://" + base.slice("http://".length);
  // Relative path case (proxied via Apache): derive ws(s) scheme and host from the
  // current page, same as the browser would for the http(s) fetches using this base.
  const wsProto = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = typeof window !== "undefined" ? window.location.host : "";
  return `${wsProto}//${host}${base}`;
}
```

- [ ] **Step 4: Run the verification script to see it pass**

Run: `cd frontend && npx tsx verify_wsbase.ts`
Expected: PASS, prints `PASS: getWsBase`

- [ ] **Step 5: Delete the temporary verification script**

Run: `cd frontend && rm verify_wsbase.ts`

- [ ] **Step 6: Do not commit**

Per Global Constraints, leave this change unstaged.

---

### Task 4: Create the `RealtimeEmotion` floating-card component

**Files:**
- Create: `frontend/src/app/[locale]/components/Chart/RealtimeEmotion.tsx`

**Interfaces:**
- Consumes: `getApiBase`, `getWsBase` (Task 3, `@/lib/apiBase`); `rawDataAtom`, `liveVAAtom` (`../museClientAtom`); `connectedAtom` (`../EEG/EEGatoms`).
- Produces: `export default function RealtimeEmotion()` — a React component with no props. Task 5 imports this as the default export.

This task has no automated verification (per spec — no frontend test framework, and this component's behavior depends on a live EEG device + running backend). Verification is manual, via the dev server, after Task 5 wires it into `chart.tsx`.

- [ ] **Step 1: Write the component**

Create `frontend/src/app/[locale]/components/Chart/RealtimeEmotion.tsx`:

```tsx
"use client";
import { useEffect, useRef, useState } from "react";
import { useAtom } from "jotai";
import { rawDataAtom, liveVAAtom } from "../museClientAtom";
import { connectedAtom } from "../EEG/EEGatoms";
import { getApiBase, getWsBase } from "@/lib/apiBase";

type ConnectionStatus = "idle" | "connecting" | "connected" | "error" | "disconnected";

const DEFAULT_SEQ_LEN = 100;
const DEFAULT_CHANNELS = 4;
const SEND_INTERVAL_MS = 500;

export default function RealtimeEmotion() {
  const [connected] = useAtom(connectedAtom);
  const [rawData] = useAtom(rawDataAtom);
  const [, setLiveVA] = useAtom(liveVAAtom);

  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [valence, setValence] = useState<number | null>(null);
  const [arousal, setArousal] = useState<number | null>(null);
  const [vaHistory, setVaHistory] = useState<Array<{ x: number; y: number; t: number }>>([]);
  const [modelParams, setModelParams] = useState<{ n_channels?: number; seq_len?: number } | null>(null);

  // Kept in sync with rawData below so the send interval always reads the latest
  // buffer, instead of a stale snapshot captured when the effect last ran.
  const rawDataRef = useRef(rawData);

  useEffect(() => {
    rawDataRef.current = rawData;
  }, [rawData]);

  // Fetch model shape once, same defaults Player.tsx's handleAnalyze uses.
  useEffect(() => {
    let mounted = true;
    const apiBase = getApiBase();
    fetch(`${apiBase}/eeg_emotion/status`).then(async (res) => {
      try {
        const j = await res.json();
        if (!mounted) return;
        if (j?.params) setModelParams(j.params);
      } catch (e) {
        // ignore
      }
    }).catch(() => {});
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (!connected) {
      setStatus("disconnected");
      return;
    }

    setStatus("connecting");
    const socket = new WebSocket(`${getWsBase()}/eeg_emotion/ws`);

    socket.onopen = () => setStatus("connected");
    socket.onerror = () => setStatus("error");
    socket.onclose = () => setStatus("disconnected");

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.error) return;
        const v = Number(data.valence);
        const a = Number(data.arousal);
        if (!Number.isFinite(v) || !Number.isFinite(a)) return;
        setValence(v);
        setArousal(a);
        setLiveVA({ v, a });
        const tx = v * 2 - 1;
        const ty = a * 2 - 1;
        setVaHistory((s) => s.concat({ x: tx, y: ty, t: Date.now() }).slice(-50));
      } catch (e) {
        // ignore malformed messages
      }
    };

    const seqLen = modelParams?.seq_len ?? DEFAULT_SEQ_LEN;
    const expectedChannels = modelParams?.n_channels ?? DEFAULT_CHANNELS;

    const intervalId = window.setInterval(() => {
      if (socket.readyState !== WebSocket.OPEN) return;
      const current = rawDataRef.current;
      if (!current || current.length === 0) return;

      const windowSlice = current.slice(-seqLen);
      const padCount = seqLen - windowSlice.length;
      const samples: number[][] = Array.from({ length: expectedChannels }, () => Array(seqLen).fill(0));
      for (let t = 0; t < windowSlice.length; t++) {
        const row = windowSlice[t].data || [];
        const targetIdx = padCount + t;
        for (let c = 0; c < expectedChannels; c++) {
          const val = c < row.length && typeof row[c] === "number" && Number.isFinite(row[c]) ? row[c] : 0;
          samples[c][targetIdx] = val;
        }
      }
      socket.send(JSON.stringify({ samples }));
    }, SEND_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close();
      }
    };
  }, [connected, modelParams, setLiveVA]);

  const statusColor = status === "connected" ? "#2e7d32" : status === "error" ? "#c62828" : "#757575";

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <strong>Realtime Emotion</strong>
        <span style={{ marginLeft: 8, fontSize: 12, color: statusColor }}>{status}</span>
      </div>

      <div style={{ marginBottom: 8 }}>
        <strong>Valence:</strong> {valence === null ? "-" : valence.toFixed(3)}
        {", "}
        <strong>Arousal:</strong> {arousal === null ? "-" : arousal.toFixed(3)}
      </div>

      <svg width={240} height={240} viewBox="0 0 240 240" style={{ border: "1px solid #eee", background: "#fff" }}>
        <g>
          <circle cx={120} cy={120} r={90} stroke="#ccc" strokeWidth={1} fill="none" />
          <line x1={30} y1={120} x2={210} y2={120} stroke="#999" strokeWidth={1} />
          <line x1={120} y1={30} x2={120} y2={210} stroke="#999" strokeWidth={1} />
          <text x={160} y={50} fontSize={12} fill="#333">Happy / Excited</text>
          <text x={50} y={50} fontSize={12} fill="#333">Angry / Distressed</text>
          <text x={50} y={190} fontSize={12} fill="#333">Sad / Depressed</text>
          <text x={150} y={190} fontSize={12} fill="#333">Relaxed / Calm</text>

          {vaHistory.length > 0 && (() => {
            const r = 80;
            const cx = 120, cy = 120;
            const points = vaHistory.map((p) => {
              const px = cx + p.x * r;
              const py = cy - p.y * r;
              return `${px},${py}`;
            }).join(" ");
            return <polyline points={points} fill="none" stroke="#2b6cb0" strokeWidth={2} strokeOpacity={0.7} />;
          })()}

          {valence !== null && arousal !== null && (() => {
            const tx = valence * 2 - 1;
            const ty = arousal * 2 - 1;
            const r = 80;
            const cx = 120, cy = 120;
            const px = cx + tx * r;
            const py = cy - ty * r;
            return <circle cx={px} cy={py} r={8} fill="#e53e3e" stroke="#fff" strokeWidth={2} />;
          })()}
        </g>
      </svg>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no new errors mentioning `RealtimeEmotion.tsx` (the file isn't imported anywhere yet after this task alone, so it's fine if `tsc` doesn't report anything about it at all — Task 5 wires it in and re-checks).

- [ ] **Step 3: Do not commit**

Per Global Constraints, leave this change unstaged.

---

### Task 5: Wire `RealtimeEmotion` into `chart.tsx`

**Files:**
- Modify: `frontend/src/app/[locale]/components/Chart/chart.tsx`

**Interfaces:**
- Consumes: `RealtimeEmotion` default export (Task 4).

- [ ] **Step 1: Add the import**

In `frontend/src/app/[locale]/components/Chart/chart.tsx`, change:

```tsx
import MusicComponent from "../Music";
```

to:

```tsx
import MusicComponent from "../Music";
import RealtimeEmotion from "./RealtimeEmotion";
```

- [ ] **Step 2: Register it in `ChartComponentMap`**

Change:

```tsx
const ChartComponentMap: Record<string, React.ReactElement> = {
  eeg: <RealtimeEEG />,
  fft: <FFT />,
  bp: <BandPower />,
  music: <MusicComponent />,
};
```

to:

```tsx
const ChartComponentMap: Record<string, React.ReactElement> = {
  eeg: <RealtimeEEG />,
  fft: <FFT />,
  bp: <BandPower />,
  music: <MusicComponent />,
  emotion_realtime: <RealtimeEmotion />,
};
```

- [ ] **Step 3: Add it to `initialCharts`**

Change:

```tsx
    {
      id: "music",
      title: "Music",
      visible: false,
      position: { x: 150, y: 150 },
      size: { width: 900, height: 750 },
    },
  ];
```

to:

```tsx
    {
      id: "music",
      title: "Music",
      visible: false,
      position: { x: 150, y: 150 },
      size: { width: 900, height: 750 },
    },
    {
      id: "emotion_realtime",
      title: "Emotion (Realtime)",
      visible: false,
      position: { x: 200, y: 200 },
      size: { width: 450, height: 500 },
    },
  ];
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no errors.

- [ ] **Step 5: Manual verification**

Requires: the backend running with the emotion model loaded (`mamba_ssm` installed, `.env`'s `EMO_VALENCE_PATH`/`EMO_AROUSAL_PATH` pointing at real weights), and a connected Muse device (or mock device per `deviceAtom`).

1. Start the frontend dev server and open the app.
2. In the `Chart` toolbar, click the new "Emotion (Realtime)" toggle button — the card should appear.
3. With the EEG device connected, confirm the card's status reads "connecting" then "connected", and the valence/arousal numbers + circumplex dot update roughly every 500ms.
4. Open `Player.tsx`'s Music card at the same time and confirm its existing circumplex plot also updates in sync (via the shared `liveVAAtom`).
5. Toggle the "Emotion (Realtime)" card off (hide it) — confirm (via browser devtools Network/WS tab) that the WebSocket connection closes and no more `/eeg_emotion/ws` traffic occurs while hidden.
6. Disconnect the EEG device — confirm the card's status changes to "disconnected" and sending stops.

- [ ] **Step 6: Do not commit**

Per Global Constraints, leave this change unstaged — let the user review and commit both `backend/` and `frontend/` changes themselves.

---

## Outstanding item from earlier in this project (not part of this plan)

`Chart/chart.tsx`'s fixed `h-[800px]` container (causing the Music card to visually overflow) and the Music component's unstyled native `<button>`/`<select>` elements were flagged earlier in this project but never implemented — that work was superseded by this WebSocket feature request before it got approved. It's still worth doing as a separate, later task; it is not included here since it wasn't part of the approved spec for this plan.
