# Realtime MRT2 Music Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continuous, gapless MRT2 music generation steered by a live valence/arousal target, delivered over a new WebSocket endpoint, with the live prompt text displayed alongside playback in a new floating card.

**Architecture:** A new `/experiment/ws` WebSocket endpoint reuses the existing `build_prompt()`/target-interpolation logic (no EEG inference — the client supplies current valence/arousal from the already-live `liveVAAtom`), generates one MRT2 chunk per request via `asyncio.to_thread`, and replies with a JSON prompt frame followed by a binary WAV frame. A new `RealtimeMusic.tsx` floating card drives this with a two-slot (playing/prefetched) buffer: it requests the next chunk while the current one is still playing (using whatever `liveVAAtom` holds at that moment), so there's no gap waiting for generation when the current chunk ends.

**Tech Stack:** FastAPI (`WebSocket`/`WebSocketDisconnect`, `asyncio.to_thread`), existing `build_prompt()`/`_generate_local()`/`generate_mrt2_local.reset_session()` (backend); Next.js/React, jotai (`liveVAAtom`), browser `WebSocket`/`HTMLAudioElement` (frontend).

**Spec:** `docs/superpowers/specs/2026-08-25-realtime-mrt2-music-streaming-design.md`

## Global Constraints

- `backend/` and `frontend/` are independent, team-owned git repositories (project `CLAUDE.md`). **Never run `git add`/`git commit`/`git push` inside either directory at any point in this plan** — leave changes unstaged for the user to review and commit themselves.
- No new test-framework dependencies. Backend verification uses `fastapi.testclient.TestClient` (already usable via the installed `httpx`) in a temporary script, written, run, and deleted. Frontend has no test framework at all; verification there is a TypeScript typecheck plus manual testing (documented, not automatable by an agent — no physical EEG hardware or MRT2 server access).
- Do not modify `/experiment/feedback`, `ExperimentPlayer.tsx`, `Player.tsx`, or `RealtimeEmotion.tsx` — this plan adds a new, separate path alongside them.
- `build_prompt()` and `_generate_local()` (both already in `backend/word_haku_api/routers/route_experiment.py`) are used with their existing signatures, unchanged: `build_prompt(current_v, current_a, next_v, next_a, target_v, target_a, *, base_prompt=None, duration=None) -> str`; `_generate_local(provider, *, prompt, out_path, seconds_total, reset=False)`.
- No `seed` field/RNG-seeding in the new endpoint — MRT2 has no exposed seed (its JAX sampling PRNGKey is baked in at model-load time; see `generate_mrt2_local.py`'s module docstring), so RNG-seeding code from `/experiment/feedback` (which only ever affected the now-removed Stable Audio path) must not be carried over.
- MRT2's stream continuation state (`mrt2_poc/server.py`'s `_state`) is a single global, not per-session: the new endpoint's first chunk on each connection always uses `reset=True`, and the connection resets the shared MRT2 state again on disconnect (mirroring `/experiment/stop`'s existing `reset_session()` call) so whatever runs next starts clean.

---

## File Structure

- **Modify:** `backend/word_haku_api/routers/route_experiment.py` — add the `/ws` WebSocket endpoint (Task 1).
- **Create:** `frontend/src/app/[locale]/components/Chart/RealtimeMusic.tsx` — the new floating-card component (Task 2).
- **Modify:** `frontend/src/app/[locale]/components/Chart/chart.tsx` — register the new card (Task 3).

Task 3 depends on Task 2 (imports the component). Task 2 depends on Task 1 only in that it targets the same message contract — they can be implemented in either order, but this plan does backend first so the frontend implementer can test the message shape against a real running endpoint later if desired.

---

### Task 1: Add the `/experiment/ws` WebSocket endpoint

**Files:**
- Modify: `backend/word_haku_api/routers/route_experiment.py`
- Verify: `backend/verify_experiment_ws.py` (temporary — delete before finishing this task)

**Interfaces:**
- Consumes: `build_prompt(current_v, current_a, next_v, next_a, target_v, target_a, *, base_prompt=None, duration=None) -> str` and `_generate_local(provider, *, prompt, out_path, seconds_total, reset=False)` (both already exist in this file, unchanged).
- Produces: a WebSocket route at `/experiment/ws` (full path, since this router is mounted with prefix `/experiment` in `main.py`). Client sends `{"current_v": float, "current_a": float, "target_valence": float, "target_arousal": float, "alpha": float?, "duration": float?, "base_prompt": string?}`. On success, server sends one JSON text frame `{"prompt": str, "current_v": float, "current_a": float, "next_v": float, "next_a": float}` followed by one binary frame (WAV bytes). On failure, one JSON text frame `{"error": str}` only.

- [ ] **Step 1: Write the failing verification script**

Create `backend/verify_experiment_ws.py`:

```python
"""Temporary verification script for Task 1 — delete after this task passes."""
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from word_haku_api.routers import route_experiment as mod

app = FastAPI()
app.include_router(mod.router)
client = TestClient(app)

fake_audio = b"FAKE_WAV_BYTES"


def fake_generate_local(provider, *, prompt, out_path, seconds_total, reset=False):
    fake_generate_local.calls.append({"provider": provider, "prompt": prompt, "reset": reset})
    return fake_audio


fake_generate_local.calls = []


def fake_build_prompt(current_v, current_a, next_v, next_a, target_v, target_a, *, base_prompt=None, duration=None):
    return f"prompt for v={next_v:.2f} a={next_a:.2f}"


with patch.object(mod, "_generate_local", side_effect=fake_generate_local), \
     patch.object(mod, "build_prompt", side_effect=fake_build_prompt), \
     patch("word_haku_api.music_ai.generate_mrt2_local.reset_session", MagicMock()):
    # reset_session is imported locally inside experiment_ws()'s `finally` block
    # (from ..music_ai.generate_mrt2_local import reset_session as reset_mrt2_session),
    # not as a module-level attribute of route_experiment -- so it must be patched at
    # its source module, not via patch.object(mod, ...). The inline import picks up
    # this patched version since it happens fresh each time the finally block runs.

    with client.websocket_connect("/ws") as ws:
        # Chunk 1: valid request -> JSON frame then binary frame, reset=True (first chunk)
        ws.send_json({
            "current_v": 0.5, "current_a": 0.5,
            "target_valence": 0.8, "target_arousal": 0.3,
            "alpha": 0.3, "duration": 8,
        })
        msg1 = ws.receive_json()
        assert "prompt" in msg1, msg1
        assert msg1["current_v"] == 0.5 and msg1["current_a"] == 0.5, msg1
        expected_next_v = 0.5 + 0.3 * (0.8 - 0.5)
        expected_next_a = 0.5 + 0.3 * (0.3 - 0.5)
        assert abs(msg1["next_v"] - expected_next_v) < 1e-9, msg1
        assert abs(msg1["next_a"] - expected_next_a) < 1e-9, msg1
        audio1 = ws.receive_bytes()
        assert audio1 == fake_audio, audio1

        # Chunk 2 on the SAME connection -> reset must now be False
        ws.send_json({
            "current_v": 0.6, "current_a": 0.4,
            "target_valence": 0.8, "target_arousal": 0.3,
            "duration": 8,
        })
        msg2 = ws.receive_json()
        assert "prompt" in msg2, msg2
        audio2 = ws.receive_bytes()
        assert audio2 == fake_audio, audio2

        assert fake_generate_local.calls[0]["reset"] is True, fake_generate_local.calls
        assert fake_generate_local.calls[1]["reset"] is False, fake_generate_local.calls

        # Invalid request (missing required field) -> error frame only, connection stays open
        ws.send_json({"current_v": 0.5})  # missing target_valence etc.
        err = ws.receive_json()
        assert "error" in err, err

        # Connection still alive: a valid request after the error still works
        ws.send_json({
            "current_v": 0.5, "current_a": 0.5,
            "target_valence": 0.8, "target_arousal": 0.3,
            "duration": 8,
        })
        msg3 = ws.receive_json()
        assert "prompt" in msg3, msg3
        ws.receive_bytes()

print("PASS: /experiment/ws")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python verify_experiment_ws.py`
Expected: FAIL — `client.websocket_connect("/ws")` errors because no such route exists yet on this router (connection rejected / import error referencing `mod.build_prompt` or `mod._generate_local` not being patchable in the expected way is also an acceptable failure signal at this stage — the point is it doesn't pass yet).

- [ ] **Step 3: Add the WebSocket endpoint**

In `backend/word_haku_api/routers/route_experiment.py`, change the import line:

```python
from fastapi import APIRouter, HTTPException
```

to:

```python
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
```

Then add this at the very end of the file (after the existing `/stop` endpoint):

```python
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
            reset_mrt2_session()
        except Exception as e:
            print(f"[experiment] mrt2 session reset skipped: {e}")
```

- [ ] **Step 4: Run the verification script to see it pass**

Run: `cd backend && .venv/bin/python verify_experiment_ws.py`
Expected: PASS, prints `PASS: /experiment/ws`

- [ ] **Step 5: Delete the temporary verification script**

Run: `cd backend && rm verify_experiment_ws.py`

- [ ] **Step 6: Do not commit**

Per Global Constraints, `backend/` is a separate team repo — leave this change unstaged.

---

### Task 2: Create the `RealtimeMusic` floating-card component

**Files:**
- Create: `frontend/src/app/[locale]/components/Chart/RealtimeMusic.tsx`

**Interfaces:**
- Consumes: `getWsBase()` (`@/lib/apiBase`, already exists — no changes needed); `liveVAAtom` (`../museClientAtom`, already exists, read-only here).
- Produces: `export default function RealtimeMusic()` — a React component with no props. Task 3 imports this as the default export.

No automated test for this task (per spec — no frontend test framework, and behavior depends on a live MRT2 server + browser). Verification is a TypeScript typecheck; full manual verification happens after Task 3 wires it in.

- [ ] **Step 1: Write the component**

Create `frontend/src/app/[locale]/components/Chart/RealtimeMusic.tsx`:

```tsx
"use client";
import { useEffect, useRef, useState } from "react";
import { useAtom } from "jotai";
import { liveVAAtom } from "../museClientAtom";
import { getWsBase } from "@/lib/apiBase";

type ConnectionStatus = "idle" | "connecting" | "connected" | "error" | "disconnected";

const DEFAULT_DURATION = 8;
const PREFETCH_LEAD_SECONDS = 3;

type PendingChunk = { prompt: string; audioUrl: string };

export default function RealtimeMusic() {
  const [liveVA] = useAtom(liveVAAtom);

  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [targetValence, setTargetValence] = useState(0.8);
  const [targetArousal, setTargetArousal] = useState(0.3);
  const [duration, setDuration] = useState(DEFAULT_DURATION);
  const [currentPrompt, setCurrentPrompt] = useState<string | null>(null);

  const liveVARef = useRef(liveVA);
  useEffect(() => {
    liveVARef.current = liveVA;
  }, [liveVA]);

  const targetRef = useRef({ targetValence, targetArousal, duration });
  useEffect(() => {
    targetRef.current = { targetValence, targetArousal, duration };
  }, [targetValence, targetArousal, duration]);

  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const pendingPromptRef = useRef<string | null>(null);
  const prefetchedRef = useRef<PendingChunk | null>(null);
  const requestInFlightRef = useRef(false);
  const runningRef = useRef(false);

  const sendChunkRequest = (socket: WebSocket) => {
    const va = liveVARef.current;
    if (!va || va.v === null || va.a === null) return;
    const { targetValence: tv, targetArousal: ta, duration: dur } = targetRef.current;
    requestInFlightRef.current = true;
    socket.send(JSON.stringify({
      current_v: va.v,
      current_a: va.a,
      target_valence: tv,
      target_arousal: ta,
      duration: dur,
    }));
  };

  const playChunk = (chunk: PendingChunk) => {
    if (!audioRef.current) audioRef.current = new Audio();
    const audio = audioRef.current;
    audio.src = chunk.audioUrl;
    setCurrentPrompt(chunk.prompt);
    audio.play().catch(() => {});
  };

  const handleStart = () => {
    if (runningRef.current) return;
    runningRef.current = true;
    setRunning(true);
    setErrorMessage(null);
    setStatus("connecting");

    const socket = new WebSocket(`${getWsBase()}/experiment/ws`);
    wsRef.current = socket;

    socket.onopen = () => {
      setStatus("connected");
      sendChunkRequest(socket);
    };

    socket.onerror = () => setStatus("error");

    socket.onclose = () => {
      setStatus("disconnected");
      runningRef.current = false;
      setRunning(false);
    };

    socket.onmessage = (event) => {
      if (typeof event.data === "string") {
        let data: any;
        try {
          data = JSON.parse(event.data);
        } catch (e) {
          return;
        }
        if (data.error) {
          setErrorMessage(String(data.error));
          requestInFlightRef.current = false;
          return;
        }
        pendingPromptRef.current = String(data.prompt ?? "");
      } else {
        const blob = event.data instanceof Blob ? event.data : new Blob([event.data]);
        const audioUrl = URL.createObjectURL(blob);
        const prompt = pendingPromptRef.current ?? "";
        pendingPromptRef.current = null;
        requestInFlightRef.current = false;

        if (!audioRef.current || audioRef.current.paused) {
          playChunk({ prompt, audioUrl });
        } else {
          prefetchedRef.current = { prompt, audioUrl };
        }
      }
    };

    if (!audioRef.current) audioRef.current = new Audio();
    const audio = audioRef.current;

    audio.ontimeupdate = () => {
      if (!runningRef.current) return;
      if (requestInFlightRef.current) return;
      if (prefetchedRef.current) return;
      if (!Number.isFinite(audio.duration) || audio.duration <= 0) return;
      const remaining = audio.duration - audio.currentTime;
      if (remaining < PREFETCH_LEAD_SECONDS && wsRef.current?.readyState === WebSocket.OPEN) {
        sendChunkRequest(wsRef.current);
      }
    };

    audio.onended = () => {
      if (prefetchedRef.current) {
        const next = prefetchedRef.current;
        prefetchedRef.current = null;
        playChunk(next);
      }
    };
  };

  const handleStop = () => {
    runningRef.current = false;
    setRunning(false);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
    }
    pendingPromptRef.current = null;
    prefetchedRef.current = null;
    requestInFlightRef.current = false;
    setCurrentPrompt(null);
    setStatus("idle");
  };

  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (audioRef.current) audioRef.current.pause();
    };
  }, []);

  const statusColor = status === "connected" ? "#2e7d32" : status === "error" ? "#c62828" : "#757575";

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <strong>Realtime Music</strong>
        <span style={{ marginLeft: 8, fontSize: 12, color: statusColor }}>{status}</span>
        {errorMessage && (
          <span style={{ marginLeft: 8, fontSize: 12, color: "#c62828" }}>({errorMessage})</span>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center", flexWrap: "wrap" }}>
        <label>Target Valence: <input type="number" value={targetValence} min={0} max={1} step={0.01}
          onChange={(e) => setTargetValence(Number(e.target.value))} disabled={running} /></label>
        <label>Target Arousal: <input type="number" value={targetArousal} min={0} max={1} step={0.01}
          onChange={(e) => setTargetArousal(Number(e.target.value))} disabled={running} /></label>
        <label>Duration(s): <input type="number" value={duration} min={1} max={120} step={1}
          onChange={(e) => setDuration(Number(e.target.value))} disabled={running} /></label>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <button onClick={handleStart} disabled={running}>Start</button>
        <button onClick={handleStop} disabled={!running}>Stop</button>
      </div>

      <div style={{ fontSize: 13 }}>
        <strong>Prompt:</strong> {currentPrompt ?? "-"}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no errors mentioning `RealtimeMusic.tsx` (it isn't imported anywhere yet after this task alone — Task 3 wires it in and re-checks).

- [ ] **Step 3: Do not commit**

Per Global Constraints, leave this change unstaged.

---

### Task 3: Wire `RealtimeMusic` into `chart.tsx`

**Files:**
- Modify: `frontend/src/app/[locale]/components/Chart/chart.tsx`

**Interfaces:**
- Consumes: `RealtimeMusic` default export (Task 2).

- [ ] **Step 1: Add the import**

In `frontend/src/app/[locale]/components/Chart/chart.tsx`, change:

```tsx
import RealtimeEmotion from "./RealtimeEmotion";
```

to:

```tsx
import RealtimeEmotion from "./RealtimeEmotion";
import RealtimeMusic from "./RealtimeMusic";
```

(If `RealtimeEmotion`'s import line has already changed since this plan was written, add the `RealtimeMusic` import as its own new line next to it instead — the exact anchor text matters less than importing it once, alongside the other Chart component imports.)

- [ ] **Step 2: Register it in `ChartComponentMap`**

Change:

```tsx
const ChartComponentMap: Record<string, React.ReactElement> = {
  eeg: <RealtimeEEG />,
  fft: <FFT />,
  bp: <BandPower />,
  music: <MusicComponent />,
  emotion_realtime: <RealtimeEmotion />,
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
  music_realtime: <RealtimeMusic />,
};
```

- [ ] **Step 3: Add it to `initialCharts`**

Change:

```tsx
    {
      id: "emotion_realtime",
      title: "Emotion (Realtime)",
      visible: false,
      position: { x: 200, y: 200 },
      size: { width: 450, height: 500 },
    },
  ];
```

to:

```tsx
    {
      id: "emotion_realtime",
      title: "Emotion (Realtime)",
      visible: false,
      position: { x: 200, y: 200 },
      size: { width: 450, height: 500 },
    },
    {
      id: "music_realtime",
      title: "Music (Realtime)",
      visible: false,
      position: { x: 250, y: 250 },
      size: { width: 450, height: 350 },
    },
  ];
```

(As with Step 1, if the surrounding `initialCharts` entries have shifted since this plan was written, add the `music_realtime` object as a new entry in the array — the exact neighboring entry matters less than it being present once, with these exact field values.)

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no errors.

- [ ] **Step 5: Manual verification**

Requires: the backend running with `/experiment/ws` reachable, the MRT2 server running (`mrt2_poc/server.py` or its Docker image, per `backend/README.md`), and a connected EEG device (or mock) so the Emotion (Realtime) card is producing live valence/arousal.

1. Open the Emotion (Realtime) card first and confirm it's showing live valence/arousal (this feeds `liveVAAtom`, which the new card reads).
2. Open the new "Music (Realtime)" card, set target valence/arousal and duration, click Start.
3. Confirm status goes "connecting" → "connected", audio begins playing shortly after, and the prompt text updates.
4. Let it play across at least 2-3 chunk transitions — confirm there's no (or minimal) gap between chunks, and the prompt text updates at each transition.
5. Click Stop — confirm audio stops and the WebSocket closes (check the browser's Network/WS tab).
6. Restart (Start again) — confirm it works again from a clean state (this exercises the `reset_session()` cleanup from the previous Stop).

- [ ] **Step 6: Do not commit**

Per Global Constraints, leave this change unstaged — let the user review and commit both `backend/` and `frontend/` changes themselves.
