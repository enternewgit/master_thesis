# Realtime Valence/Arousal via WebSocket — Design

## Context

`Player.tsx` currently predicts valence/arousal via a one-shot REST call
(`POST /eeg_emotion/predict`) triggered manually by the "Run analysis /
Generate" button. There is also a `liveVAAtom` (jotai) already wired up as a
shared "live valence/arousal" value, and `Player.tsx`'s embedded circumplex
plot already reads it — but today the only thing that writes to it is the
experiment-feedback polling loop (`ExperimentPlayer.tsx`'s
`/experiment/latest` poll), which only runs during an active
generate-music-from-feedback session.

This design adds a continuous, low-latency valence/arousal prediction path
over WebSocket, independent of the music-generation feedback loop, displayed
as a new floating card in the `Chart` component (alongside eeg/fft/bp/music).

Reference implementation studied: `/home/httpd/braingram/word-haku/src/app/[locale]/my/infer/websocket.tsx`
(frontend) and `/home/httpd/braingram/word_haku_api/word_haku_api/routers/route_ai.py`
(backend) — a different, older project using WebSocket for a word-classification
task. We reuse the *pattern* (gate the socket on device-connected state, stream
JSON windows, receive JSON predictions back), not the code — model, preprocessing,
and message shapes are specific to this project's EEGMamba emotion model.

## Goals

- Continuous valence/arousal updates while the new floating card is visible,
  without requiring the record→generate→play experiment cycle.
- Reuse the existing EEGMamba model/preprocessing (`music_ai/loader.py`,
  `music_ai/infer.py`, `music_ai/eeg_preprocess.py`) — no new model code.
- Keep `Player.tsx` untouched (per explicit decision — its existing embedded
  circumplex plot and one-shot analyze/generate flow stay as-is).

## Non-goals

- WebSocket auto-reconnect / retry-on-drop (v1: close on unmount or device
  disconnect, no retry loop — add later only if it proves flaky in practice).
- Changing the music-generation feedback loop (`/experiment/feedback`) or its
  chunking/pipelining (separate, paused discussion pending bottleneck
  measurements from `[experiment][timing]` logs).
- Removing or altering `Player.tsx`'s existing circumplex plot.

## Backend design

### Shared preprocessing helper

`routers/route_eeg_emotion.py`'s `predict_emotion()` (POST `/predict`)
currently inlines: numpy conversion, shape validation against the model's
`n_channels`/`seq_len`, 256→200Hz resampling
(`resample_eeg_channels`/`resample_eeg_batch`), and the `predict_from_eeg`
call. Extract this into a shared function, e.g.:

```python
def _predict_from_samples(raw_samples: list) -> dict:
    # numpy conversion, shape validation, resampling, predict_from_eeg call
    # raises HTTPException/RuntimeError on invalid input, same as today
    ...
```

`predict_emotion()` becomes a thin wrapper calling this and returning the
result. The new WebSocket handler calls the same function, so both paths
share identical validation/preprocessing — no duplicated logic.

### New WebSocket endpoint

Add to `routers/route_eeg_emotion.py` (full path `/eeg_emotion/ws`, reachable
through Apache's existing `/braingram_mg_api/` proxy, which already has
`upgrade=websocket` configured):

```python
@router.websocket("/ws")
async def eeg_emotion_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            try:
                result = _predict_from_samples(data.get("samples", []))
                await websocket.send_json(result)
            except Exception as e:
                await websocket.send_json({"error": str(e)})
    except WebSocketDisconnect:
        pass
```

No producer/consumer queue (unlike the reference implementation) — the
client paces sends at a fixed interval (500ms) and EEGMamba inference is
fast, so a plain sequential receive→infer→send loop is sufficient. If this
ever needs to tolerate a bursty/uncontrolled client, revisit with a queue.

## Frontend design

### `getWsBase()` helper

Extend `frontend/src/lib/apiBase.ts` with a sibling function that derives a
WebSocket URL from the same resolved API base (same local-port-3001-bypass
logic as `getApiBase()`, just mapping `http→ws` / `https→wss`):

```typescript
export function getWsBase(): string {
  const base = getApiBase();
  if (base.startsWith("https://")) return "wss://" + base.slice("https://".length);
  if (base.startsWith("http://")) return "ws://" + base.slice("http://".length);
  // relative path case (proxied via Apache): derive scheme from window.location
  const wsProto = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = typeof window !== "undefined" ? window.location.host : "";
  return `${wsProto}//${host}${base}`;
}
```

### New floating card component

New file, e.g. `frontend/src/app/[locale]/components/Chart/RealtimeEmotion.tsx`:

- `"use client"` component. Reads `connectedAtom` (device connected,
  `EEGatoms.ts`) and `rawDataAtom` (raw EEG stream, `museClientAtom.tsx`) via
  jotai.
- On mount (which only happens while its chart card is visible — `chart.tsx`
  already only renders visible cards' components) and whenever
  `connectedAtom` becomes true: open `new WebSocket(`${getWsBase()}/eeg_emotion/ws`)`.
  On `connectedAtom` becoming false, or component unmount: close the socket.
- On mount, fetch `/eeg_emotion/status` once (same as `Player.tsx` does) to
  get `modelParams.n_channels`/`seq_len`, falling back to the same defaults
  `Player.tsx` uses (4 channels, `DEFAULT_SEQ_LEN = 100`) if the model isn't
  loaded yet.
- A `setInterval` (500ms) while the socket is open: build the latest
  channels×seqLen window from `rawDataAtom` (same zero-padding logic already
  in `Player.tsx`'s `handleAnalyze` — reuse the shape, not shared code) and
  `ws.send(JSON.stringify({ samples }))`. Read `rawDataAtom` via a ref kept
  in sync with the atom (same `xRef.current = xAtomValue` pattern already
  used in `ExperimentPlayer.tsx` for `rawDataRef`), not directly from the
  interval closure — otherwise the interval captures a stale snapshot from
  whenever the effect last ran.
- `ws.onmessage`: parse `{valence, arousal}` or `{error}`. On success, update
  local state (current V/A + trailing history for the plot) **and** write
  into the shared `liveVAAtom` (`setLiveVA({ v: valence, a: arousal })`) so
  `Player.tsx`'s existing circumplex plot also reflects the live stream.
- Renders: connection status (connecting/connected/error/disconnected),
  current valence/arousal readout, and a circumplex SVG plot with trailing
  history — visually similar to `Player.tsx`'s existing plot but independent
  code (no shared/extracted component, per the decision to leave `Player.tsx`
  untouched).

### Wiring into `chart.tsx`

- Add a new entry to `ChartComponentMap` (e.g. `emotion_realtime: <RealtimeEmotion />`).
- Add a new entry to `initialCharts` (title e.g. "Emotion (Realtime)",
  `visible: false` by default like fft/bp/music, sized to comfortably fit
  the existing container — e.g. 450×500 — without depending on the
  container dynamic-sizing fix discussed earlier and not yet implemented).

## Data flow summary

```
rawDataAtom (continuously updated by EEG pipeline)
        |
        | every 500ms, while RealtimeEmotion card visible + device connected
        v
RealtimeEmotion.tsx --ws.send({samples})--> /eeg_emotion/ws (FastAPI)
                                                   |
                                    _predict_from_samples()
                                    (resample, validate, EEGMamba predict)
                                                   |
RealtimeEmotion.tsx <--ws.send({valence,arousal})--+
        |
        +--> local state (plot/readout)
        +--> liveVAAtom (shared) --> Player.tsx's existing circumplex plot
```

## Error handling

- Backend: invalid/malformed samples → `{"error": "..."}` sent back over the
  same socket (connection stays open), matching the reference pattern.
  Unexpected exceptions during predict are caught and reported the same way.
- Frontend: `onerror`/`onclose` set a visible "disconnected"/"error" status
  in the card; no auto-reconnect in v1 (see Non-goals).

## Testing

- No existing automated test suite covers this frontend/WebSocket layer.
  Verification is manual: open the new card with a device connected, confirm
  valence/arousal updates roughly every 500ms, confirm `Player.tsx`'s
  existing circumplex plot updates in sync via `liveVAAtom`, confirm the
  card cleanly stops sending when hidden or the device disconnects.
- Backend: the extracted `_predict_from_samples()` helper is plain sync
  Python and could get a small unit test (valid shape → dict with
  valence/arousal; invalid shape → raises) if useful, though the existing
  REST endpoint has no test coverage today either.
