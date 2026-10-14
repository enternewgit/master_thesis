# Realtime MRT2 Music Streaming via WebSocket — Design

## Context

Two pieces already exist from recent work:

- **`/eeg_emotion/ws`** (backend) + the **"Emotion (Realtime)" card** (`RealtimeEmotion.tsx`, frontend): continuously predicts valence/arousal from live EEG every 500ms and writes it into the shared `liveVAAtom` (jotai).
- **`/experiment/feedback`** (backend, `route_experiment.py`): a REST, record→generate→play cycle. Given `target_valence`/`target_arousal`, it runs EEG-windowed inference itself, interpolates `next_v/a = current + alpha*(target - current)`, builds a text prompt via `build_prompt()`, and generates one MRT2 audio chunk of a given `duration`. `ExperimentPlayer.tsx` drives this today: record N seconds → POST → wait for the full WAV → play → repeat.

This design adds a **third, continuous path**: a new WebSocket endpoint plus a new "Realtime Music" floating card that pipelines chunk requests using the *already-live* valence/arousal from `liveVAAtom` (skipping EEG-windowed inference entirely — that's already `/eeg_emotion/ws`'s job), so music generation and playback can run gaplessly while the user steers toward a target, same as `/experiment/feedback` conceptually, but continuous instead of one-shot-per-manual-trigger.

## Goals

- Continuous, gapless music playback that steers toward a user-set target valence/arousal, reusing the existing `build_prompt()`/target-interpolation logic unchanged.
- Display the actual prompt text used for each generated chunk, live.
- Reuse `liveVAAtom` as the valence/arousal source — no new EEG inference path.
- Client-side prefetch: request the next chunk while the current one is still playing, so there's no playback gap waiting for generation.

## Non-goals

- Modifying `/experiment/feedback` or `ExperimentPlayer.tsx` — they stay as-is, a separate, already-existing flow.
- Sample-level audio streaming — MRT2's persistent server (`mrt2_poc/server.py`) generates a whole requested duration before returning; "gapless" here means client-side prefetch/crossfade-free back-to-back playback of whole chunks, not true incremental streaming.
- WebSocket auto-reconnect (matches the emotion card's v1 scope — Stop/error requires the user to press Start again).

## Backend design

### New endpoint: `/experiment/ws`

Added to `route_experiment.py` (mounted under the existing `/experiment` prefix, so full path `/experiment/ws`). One WebSocket connection = one continuous session.

**Client → server**, one message per chunk request:
```json
{
  "current_v": 0.62, "current_a": 0.4,
  "target_valence": 0.8, "target_arousal": 0.3,
  "alpha": 0.3,
  "duration": 10,
  "base_prompt": null
}
```
No `seed` field: `/experiment/feedback`'s RNG-seeding (`random.seed`/`torch.manual_seed`) only ever affected the now-removed Stable Audio path — `generate_mrt2_local.py`'s own docstring confirms MRT2's JAX sampling PRNGKey is baked in at model-load time with no exposed seed, and `build_prompt()` takes no seed either. Carrying that dead code into a new mrt2-only endpoint would be misleading.
`current_v`/`current_a` come from the client's own `liveVAAtom` snapshot at request time — the server does **no EEG inference** on this path.

**Server → client**, two frames per successful chunk, in order:
1. One **text** frame (JSON): `{"prompt": "...", "current_v":..., "current_a":..., "next_v":..., "next_a":...}`
2. One **binary** frame: the raw WAV bytes.

On failure, only a text frame: `{"error": "..."}` (no binary frame follows for that request).

**Handler sketch** (illustrating the key decisions, not final code):
```python
@router.websocket("/ws")
async def experiment_ws(websocket: WebSocket):
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
                prompt = build_prompt(current_v, current_a, next_v, next_a, target_v, target_a,
                                       base_prompt=body.get("base_prompt"), duration=duration)
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
                    "prompt": prompt, "current_v": current_v, "current_a": current_a,
                    "next_v": next_v, "next_a": next_a,
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
            reset_mrt2_session()
        except Exception:
            pass
```

Key decisions baked into this sketch:
- **`asyncio.to_thread`** wraps the (blocking, multi-second) generation call — critical here unlike the emotion WS, since MRT2 generation can take several seconds and must not block the whole event loop (which also serves `/eeg_emotion/ws` and everything else).
- **`is_first_chunk`** (a plain local variable, not the module-level `EXPERIMENT_STATE`/`_ensure_session_seed()` machinery `/experiment/feedback` uses) decides `reset=` for `_generate_local`. Rationale: MRT2's stream continuation state (`mrt2_poc/server.py`'s `_state`) is a single global, not per-session — so this connection can't safely assume it's the only session that's ever touched it. Starting `reset=True` on this connection's first chunk guarantees a clean start regardless of what `/experiment/feedback` did previously.
- **`reset_mrt2_session()` in a `finally`** (mirroring `/experiment/stop`) leaves MRT2's shared stream clean for whatever runs next — including a future `/experiment/feedback` session or another `/experiment/ws` connection.
- Both the receive/generate step and the send step have independent error handling, following the same pattern already fixed in `/eeg_emotion/ws`: `WebSocketDisconnect` always propagates to the outer handler; any other exception during send is swallowed (nothing to do if the client's already gone).
- `build_prompt()` is called exactly as it exists today — no signature change.

## Frontend design

### New floating card: `RealtimeMusic.tsx`

Registered in `chart.tsx` alongside the other cards (same `ChartComponentMap`/`initialCharts` pattern as `RealtimeEmotion.tsx`).

**Controls** (mirroring `ExperimentPlayer.tsx`'s existing inputs): target valence, target arousal, duration, Start/Stop.

**State machine:**
- Reads `liveVAAtom` for the current valence/arousal (no atom writes from this card — `liveVAAtom` is fed by the emotion card, this card only reads it).
- On **Start**: open `new WebSocket(`${getWsBase()}/experiment/ws`)`; once open, send the first chunk request using whatever `liveVAAtom` currently holds.
- Two buffer slots: **playing** and **prefetched**. When a chunk's frames arrive (JSON prompt, then binary audio), if nothing is playing, start playing it immediately and display its prompt; if something is already playing, store it as the prefetched chunk.
- An `<audio>` `timeupdate` listener checks remaining time (`duration - currentTime`); once remaining time drops below `PREFETCH_LEAD_SECONDS = 3` **and** no request is currently in flight **and** no prefetched chunk is already buffered, send the next chunk request using the *current* `liveVAAtom` value at that moment. (3s is a starting default, not a measured value — generation can take longer than that, in which case a brief gap occurs; see the `ended`-handler note below. Tune after manual verification if gaps are frequent.)
- On the playing chunk's `ended` event: if a prefetched chunk is ready, swap to it immediately (zero gap) and display its prompt; if not ready yet, playback pauses briefly until it arrives (a genuine gap — acceptable degraded case, not the target path).
- On **Stop**: close the WebSocket (server-side `reset_mrt2_session()` follows automatically via the `finally` block), stop/clear both audio slots.
- On `{"error": ...}`: show the error, stop sending further prefetch requests until Start is pressed again (matches the emotion card's v1 error posture — no auto-reconnect).

### `getWsBase()` reuse

No changes needed to `frontend/src/lib/apiBase.ts` — `getWsBase()` already derives the right `ws(s)://` origin; this card just points at a different path (`/experiment/ws` instead of `/eeg_emotion/ws`).

## Data flow summary

```
liveVAAtom (fed continuously by the Emotion (Realtime) card via /eeg_emotion/ws)
        |
        | read at request time (no new EEG inference here)
        v
RealtimeMusic.tsx --ws.send({current_v, current_a, target_valence, target_arousal, duration})--> /experiment/ws
                                                                                                        |
                                                                                          next_v/a = current + alpha*(target-current)
                                                                                          build_prompt() (unchanged)
                                                                                          asyncio.to_thread(_generate_local, "mrt2", reset=is_first_chunk)
                                                                                                        |
RealtimeMusic.tsx <--{"prompt", current_v, current_a, next_v, next_a}--+
RealtimeMusic.tsx <--binary WAV bytes-------------------------------------+
        |
        +--> prompt readout
        +--> audio buffer (playing now, or prefetched for gapless swap)
```

## Error handling

- Backend: any exception during receive/build/generate → `{"error": "..."}` text frame, loop continues (connection stays open); send failures after that point are swallowed (client's likely gone).
- Frontend: shows the error message; halts further automatic prefetching until the user presses Start again (no auto-reconnect, matching the emotion card's v1 scope).
- Shared MRT2 stream state: documented as a known, existing constraint (not something this design fixes) — only one continuous MRT2 session (this endpoint or `/experiment/feedback`) should meaningfully run at a time app-wide. `reset=True`-on-first-chunk plus `reset_mrt2_session()`-on-disconnect keeps each session's *start* clean even if a previous session didn't clean up properly, but doesn't prevent two sessions running concurrently from interfering with each other mid-stream.

## Testing

- Backend: a `TestClient`-based verification script (written, run, deleted — same posture as prior work; no permanent pytest suite exists in this repo) mocking `_generate_local`/`build_prompt` dependencies, confirming: a valid request returns a JSON frame followed by a binary frame with the mocked bytes; `is_first_chunk` is `True` only for the connection's first request (verify the mock is called with `reset=True` then `reset=False` on a second request on the same connection); an error case returns only a JSON `{"error": ...}` frame and the connection stays open for a subsequent valid request.
- Frontend: no test framework exists (matches prior work); manual verification requires the MRT2 server running, a connected EEG device, and a browser — confirm gapless playback across at least 2-3 chunk transitions, confirm the prompt text updates each time, confirm Stop cleanly closes the socket and stops audio.
