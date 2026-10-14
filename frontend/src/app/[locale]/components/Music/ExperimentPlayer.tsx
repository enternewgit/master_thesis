"use client";
import React, { useEffect, useRef, useState } from "react";
import { useAtom } from "jotai";
import { rawDataAtom, eegSettingsAtom, lastDataTimestampAtom, liveVAAtom } from "../museClientAtom";
import { getApiBase } from "@/lib/apiBase";
import { Button } from "@/components/ui/button";
import {
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ScatterChart,
  ComposedChart,
  Scatter,
  ReferenceLine,
} from "recharts";

type StreamSample = { data?: number[]; timestamp?: number };

export default function ExperimentPlayer() {
  const [rawData, setRawData] = useAtom<any>(rawDataAtom);
  const [lastDataTimestamp] = useAtom<number>(lastDataTimestampAtom as any);
  // settings can have various shapes depending on source; treat as any to avoid TS errors
  const [settings] = useAtom<any>(eegSettingsAtom as any);
  const [recording, setRecording] = useState(false);
  const [buffer, setBuffer] = useState<StreamSample[]>([]);
  const bufferArrayRef = useRef<StreamSample[]>([]);
  const [modelExpectedChannels, setModelExpectedChannels] = useState<number>(4);
  const [modelWindowLength, setModelWindowLength] = useState<number | null>(null);
  const bufferRef = useRef<number>(0);
  const lastSeenRef = useRef(0);
  const rawDataRef = useRef<any[]>([]);
  const stagnantRef = useRef(0);
  const recordingTimerRef = useRef<number | null>(null);
  // controller for aborting inflight fetches
  const fetchControllerRef = useRef<AbortController | null>(null);
  // guard: whether cycles should continue; Stop sets to false
  const shouldContinueRef = useRef<boolean>(true);
  // allow startCycleWithBlob to expose its timer-starter to the global poller
  const startTimerRef = useRef<(() => void) | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [history, setHistory] = useState<Array<{ time: number; currentV: number; currentA: number; targetV: number; targetA: number }>>([]);
  const [targetValence, setTargetValence] = useState<number>(0.8);
  const [targetArousal, setTargetArousal] = useState<number>(0.3);
  const [seed, setSeed] = useState<string>("");
  const [duration, setDuration] = useState<number>(12);
  const [provider, setProvider] = useState<string>("mrt2");
  const [autoRepeat, setAutoRepeat] = useState<boolean>(false);
  const [spamInjecting, setSpamInjecting] = useState<boolean>(false);
  const [livePolling, setLivePolling] = useState<boolean>(false);
  const [livePoints, setLivePoints] = useState<Array<{ t: number; v: number | null; a: number | null }>>([]);
  const [liveCurrentV, setLiveCurrentV] = useState<number | null>(null);
  const [liveCurrentA, setLiveCurrentA] = useState<number | null>(null);
  const [, setLiveVA] = useAtom(liveVAAtom as any);

  const samplingRate = (settings && (((settings as any).SamplingRate) || ((settings as any).Duration) || ((settings as any).samplingRate))) || 256;
  const requiredSamples = Math.floor(Number(samplingRate) * (duration || 60));

  // watch rawData while recording and append new frames
  // fetch model expected channels once on mount (do NOT run on every rawData change)
  useEffect(() => {
    (async () => {
      try {
        const apiBase = getApiBase();
        const res = await fetch(`${apiBase}/eeg_emotion/status`);
        if (res.ok) {
          const j = await res.json();
          const n = j?.params?.n_channels ?? j?.params?.n_channels ?? 4;
          // model may expose sequence/window length under various keys
          const seq = j?.params?.seq_len ?? j?.params?.seq_length ?? j?.params?.window_length ?? j?.params?.window ?? null;
          setModelExpectedChannels(Number(n));
          if (seq != null) setModelWindowLength(Number(seq));
        }
      } catch (e) {
        // ignore
      }
    })();
  }, []);

  // always keep a ref to the latest rawData so interval callback can read it
  useEffect(() => {
    rawDataRef.current = Array.isArray(rawData) ? rawData : [];
  }, [rawData]);

  useEffect(() => {
    let id: number | undefined;
    if (recording) {
      id = window.setInterval(() => {
        try {
          const current = rawDataRef.current;
          const len = Array.isArray(current) ? current.length : 0;
          console.debug("ExperimentPlayer poll", { len, lastSeen: lastSeenRef.current, bufferLen: bufferRef.current });
          if (len > lastSeenRef.current) {
            const newItems = current.slice(lastSeenRef.current, len) as StreamSample[];
            lastSeenRef.current = len;
            setBuffer((prev) => {
              const merged = prev.concat(newItems);
              const out = merged.length > requiredSamples ? merged.slice(-requiredSamples) : merged;
              bufferRef.current = out.length;
              bufferArrayRef.current = out;
              console.debug('[ExperimentPlayer] buffer updated length', bufferRef.current);
              return out;
            });
            // If buffer reached requiredSamples and timer not yet started, trigger it
            try {
              if (recording && !recordingTimerRef.current && bufferRef.current >= requiredSamples && startTimerRef.current) {
                console.debug('[ExperimentPlayer] buffer reached requiredSamples; triggering timer via startTimerRef');
                try { startTimerRef.current(); } catch (e) {}
                startTimerRef.current = null;
              }
            } catch (e) {}
            // If we receive new frames while recording, ensure status reflects active recording
            try {
              if (recording) setStatus("recording");
            } catch (e) {}
            stagnantRef.current = 0;
          } else {
            stagnantRef.current += 1;
            // 変化が無い場合、時々（5回に1回）直近のフレームを出力して原因確認
            if (stagnantRef.current % 5 === 0) {
              const lastItems = Array.isArray(current) ? current.slice(Math.max(0, len - 3), len) : [];
              console.debug("[ExperimentPlayer] no new frames; lastItems:", lastItems);
            }
            if (stagnantRef.current >= 15) {
              // If we've been stagnant for a while, only mark no-data and stop
              // when we actually have no buffered frames. If buffer has data,
              // keep recording/status as active and trust buffered frames.
              try {
                const bufLenNow = bufferArrayRef.current?.length || 0;
                if (bufLenNow === 0) {
                  if (recording) {
                    setStatus("no data incoming");
                    setRecording(false);
                    // clear any recording timer to avoid sending partial/old buffers
                    if (recordingTimerRef.current) {
                      window.clearTimeout(recordingTimerRef.current);
                      recordingTimerRef.current = null;
                    }
                    // ensure audio is stopped
                    if (audioRef.current) {
                      try {
                        audioRef.current.pause();
                        audioRef.current.loop = false;
                        audioRef.current.currentTime = 0;
                      } catch (e) {}
                    }
                  }
                } else {
                  // we do have buffered frames; ensure status reflects active recording
                  if (recording) setStatus("recording");
                }
              } catch (e) {}
            }
          }
        } catch (err) {
          console.error("ExperimentPlayer poll error", err);
        }
      }, 200);
    }
    return () => {
      if (id) window.clearInterval(id);
    };
  }, [recording, requiredSamples]);

  // spam inject interval for debugging
  useEffect(() => {
    let sid: number | undefined;
    if (spamInjecting) {
      sid = window.setInterval(() => {
        try {
          const ch = ((settings as any)?.nbChannels) || 4;
          const frames = Array.from({ length: 8 }).map(() => ({ data: Array.from({ length: ch }, () => (Math.random() - 0.5) * 100), timestamp: Date.now() }));
          (setRawData as any)((prev: any[]) => (Array.isArray(prev) ? prev.concat(frames) : frames));
          rawDataRef.current = (Array.isArray(rawDataRef.current) ? rawDataRef.current.concat(frames) : frames);
        } catch (e) {
          console.error("spam inject error", e);
        }
      }, 200);
    }
    return () => {
      if (sid) window.clearInterval(sid);
    };
  }, [spamInjecting, setRawData, settings]);

  // live polling effect: fetch /experiment/latest while livePolling is true
  useEffect(() => {
    let pid: number | null = null;
    if (livePolling) {
      const apiBase = getApiBase();
      const doPoll = async () => {
        try {
          const res = await fetch(`${apiBase}/experiment/latest`);
          if (!res.ok) return;
          const j = await res.json();
          const v = j.current_v === null ? null : Number(j.current_v);
          const a = j.current_a === null ? null : Number(j.current_a);
          setLiveCurrentV(v);
          setLiveCurrentA(a);
          try { setLiveVA({ v, a }); } catch (e) {}
          setLivePoints((prev) => {
            const next = prev.concat({ t: Date.now(), v, a });
            // keep last 60 minutes of points
            return next.length > 60 ? next.slice(-60) : next;
          });
        } catch (e) {
          // ignore polling errors
        }
      };
      doPoll();
      // Poll once per minute (user only needs per-minute updates)
      pid = window.setInterval(doPoll, 60000) as unknown as number;
    }
    return () => {
      if (pid) window.clearInterval(pid);
    };
  }, [livePolling]);

  // start the fully automatic cycle: request initial track then begin loop+record
  const handleStart = async () => {
    shouldContinueRef.current = true;
    try {
      // enable live polling UI
      setLivePolling(true);
      setStatus("generating");
      // prepare a minimal empty sample payload so backend returns a first track
      const expectedChannels = modelExpectedChannels || 4;
      const seqLen = modelWindowLength || 100;
      const samplePlaceholder = Array.from({ length: expectedChannels }).map(() => Array(seqLen).fill(0));
      const apiBase = getApiBase();
      const payload: any = {
        samples: samplePlaceholder,
        target_valence: Number(targetValence),
        target_arousal: Number(targetArousal),
        duration: Number(duration),
        provider,
      };
      if (seed !== "") payload.seed = Number(seed);
      // attach AbortController so we can cancel this request if user stops
      let res: Response | null = null;
      try {
        const controller = new AbortController();
        fetchControllerRef.current = controller;
        res = await fetch(`${apiBase}/experiment/feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: controller.signal,
        });
        fetchControllerRef.current = null;

        if (!res.ok) {
          const text = await res.text();
          throw new Error(`Initial experiment request failed: ${text}`);
        }
      } catch (err: any) {
        fetchControllerRef.current = null;
        if (err && err.name === "AbortError") {
          // aborted by user; quietly return
          setStatus("stopped");
          return;
        }
        throw err;
      }
      // parse headers for emotion metrics
      try {
        const h = res.headers;
        const cv = parseFloat(h.get("x-current-valence") ?? "NaN");
        const ca = parseFloat(h.get("x-current-arousal") ?? "NaN");
        const tv = parseFloat(h.get("x-target-valence") ?? "NaN");
        const ta = parseFloat(h.get("x-target-arousal") ?? "NaN");
        if (Number.isFinite(cv) && Number.isFinite(ca)) {
          setHistory((s) => s.concat({ time: Date.now(), currentV: cv, currentA: ca, targetV: tv, targetA: ta }));
          try { setLiveVA({ v: cv, a: ca }); } catch (e) {}
        }
      } catch (e) {
        // ignore
      }
      const blob = await res.blob();
      // start the loop+record cycle with the returned blob
      // if user already requested stop, don't start
      if (!shouldContinueRef.current) {
        setStatus("stopped");
        return;
      }
      await startCycleWithBlob(blob);
    } catch (e: any) {
      console.error(e);
      setStatus("error: " + (e?.message ?? String(e)));
    }
  };

  const handleStop = () => {
    shouldContinueRef.current = false;
    setRecording(false);
    // stop live polling and notify backend
    setLivePolling(false);
    setStatus("stopped");
    if (recordingTimerRef.current) {
      window.clearTimeout(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.loop = false;
      try {
        audioRef.current.src = "";
      } catch {}
    }
    setBuffer([]);
    bufferArrayRef.current = [];
    bufferRef.current = 0;
    // abort any inflight fetch
    try {
      if (fetchControllerRef.current) {
        fetchControllerRef.current.abort();
        fetchControllerRef.current = null;
      }
    } catch (e) {}
    // notify backend to stop exposing live state
    try {
      const apiBase = getApiBase();
      fetch(`${apiBase}/experiment/stop`, { method: "POST" }).catch(() => {});
    } catch (e) {}
  };

  // core cycle: start playback of a blob, record for 60s, then send and wait for next blob
  const startCycleWithBlob = async (playBlob: Blob) => {
    const recSeconds = Math.floor(requiredSamples / Number(samplingRate)) || 60;
    const url2 = URL.createObjectURL(playBlob);
    if (!audioRef.current) audioRef.current = new Audio();
    // set audio and begin looping playback
    audioRef.current.src = url2;
    audioRef.current.loop = true;
    // reset buffer and refs
    setBuffer([]);
    bufferArrayRef.current = [];
    bufferRef.current = 0;
    // 完全リセット: 再生開始時に過去のデータを破棄して計測を"今"から始める
    try {
      (setRawData as any)([]);
    } catch (e) {
      // ignore if atom setter not available
    }
    rawDataRef.current = [];
    lastSeenRef.current = 0;
    stagnantRef.current = 0;
    setRecording(true);
    console.debug("[Experiment] Cycle Start. Performed full rawData reset. Start Index: 0");
    // if no buffered frames yet, show waiting state until some data arrives
    if ((bufferArrayRef.current?.length || 0) === 0) {
      setStatus("waiting for data");
    } else {
      setStatus("recording");
    }
    try {
      await audioRef.current.play();
    } catch (e) {
      console.warn("audio play failed", e);
    }

    // Start the actual 60s recording timer only after we have incoming frames.
    if (recordingTimerRef.current) {
      window.clearTimeout(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    const startTimerWhenReady = () => {
      if (recordingTimerRef.current) return; // already started
      console.debug('[ExperimentPlayer] starting recording timer for', recSeconds, 's');
      // expose starter so poller can trigger it when buffer fills
      startTimerRef.current = startTimerWhenReady;
      recordingTimerRef.current = window.setTimeout(async () => {
        console.debug('[ExperimentPlayer] recording timer fired');
        // Keep the current chunk looping (audio.loop is already true from
        // startCycleWithBlob) while the next one is requested/generated below --
        // however long that takes, there's no dead air. startCycleWithBlob's own
        // src/loop reassignment swaps in the new chunk the moment it arrives.
        // time's up: mark as generating and ensure polling/stagnation state cleared
        setStatus("generating");
        stagnantRef.current = 0;
        // stop recording immediately so poll stops
        setRecording(false);
        // Defer aborting until we know whether we have any buffered frames to send.
        // If we do have frames, proceed even if the lastDataTimestamp is stale.
        // Only abort when the buffer is empty and no recent frames were received.
        try {
          const last = lastDataTimestamp || 0;
          const age = Date.now() - last;
          const MAX_AGE_MS = 5000; // if no data for 5s, consider device stalled
          const bufLenNow = bufferArrayRef.current?.length || 0;
          if (bufLenNow === 0 && age > MAX_AGE_MS) {
            setStatus("no data incoming");
            console.warn('[ExperimentPlayer] aborting send: no buffered frames and last data age', age);
            // clear buffer and stop
            setBuffer([]);
            bufferArrayRef.current = [];
            bufferRef.current = 0;
            return;
          }
        } catch (e) {}
        const bufToSend = bufferArrayRef.current.slice(-requiredSamples);
        // build samples matrix; if we have fewer than model window length, pad with zeros
        const tlen = bufToSend.length || 0;
        const seqWindow = modelWindowLength || 100;
        const outgoingLen = Math.max(tlen, seqWindow);
        // 常にサーバが期待するチャンネル数(`modelExpectedChannels`)に合わせる。
        // デバイス側がAUXなどで余分なチャンネルを返す場合は切り落とし、
        // 足りない場合はゼロパディングする。
        const expectedChannels = modelExpectedChannels || 4;
        const samples: number[][] = Array.from({ length: expectedChannels }, () => Array(outgoingLen).fill(0));
        for (let t = 0; t < outgoingLen; t++) {
          const row = t < tlen ? (bufToSend[t]?.data || []) : [];
          for (let c = 0; c < expectedChannels; c++) {
            const v = c < row.length && typeof row[c] === "number" && Number.isFinite(row[c]) ? row[c] : 0;
            samples[c][t] = v;
          }
        }
        if (tlen < seqWindow) {
          setStatus(`padded ${tlen}→${seqWindow} samples`);
        }
        // clear existing buffer
        setBuffer([]);
        bufferArrayRef.current = [];
        bufferRef.current = 0;
        // ensure global raw data is cleared so polling restarts from zero
        try {
          console.debug('[ExperimentPlayer] clearing global rawData and lastSeen before send');
          (setRawData as any)([]);
        } catch (e) {}
        rawDataRef.current = [];
        lastSeenRef.current = 0;
        console.debug('[ExperimentPlayer] sent buffer and cleared local buffer');
        try {
          const apiBase2 = getApiBase();
          const payload2: any = {
            samples,
            target_valence: Number(targetValence),
            target_arousal: Number(targetArousal),
            duration: Number(duration),
            provider,
          };
          if (seed !== "") payload2.seed = Number(seed);

          // attach AbortController for the next request
          const controller2 = new AbortController();
          fetchControllerRef.current = controller2;
          const nextRes2 = await fetch(`${apiBase2}/experiment/feedback`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload2),
            signal: controller2.signal,
          });
          fetchControllerRef.current = null;
          if (!nextRes2.ok) {
            const text2 = await nextRes2.text();
            throw new Error(text2);
          }
          // parse headers for emotion metrics on the next response
          try {
            const h2 = nextRes2.headers;
            const cv2 = parseFloat(h2.get("x-current-valence") ?? "NaN");
            const ca2 = parseFloat(h2.get("x-current-arousal") ?? "NaN");
            const tv2 = parseFloat(h2.get("x-target-valence") ?? "NaN");
            const ta2 = parseFloat(h2.get("x-target-arousal") ?? "NaN");
            if (Number.isFinite(cv2) && Number.isFinite(ca2)) {
              setHistory((s) => s.concat({ time: Date.now(), currentV: cv2, currentA: ca2, targetV: tv2, targetA: ta2 }));
              try { setLiveVA({ v: cv2, a: ca2 }); } catch (e) {}
            }
          } catch (e) {
            // ignore
          }
          const nextBlob2 = await nextRes2.blob();
          try {
            URL.revokeObjectURL(url2);
          } catch {}
          // Do not start next cycle if user requested stop in the meantime
          if (!shouldContinueRef.current) {
            setStatus("stopped");
            return;
          }
          // immediately start next cycle with returned blob
          await startCycleWithBlob(nextBlob2);
        } catch (e: any) {
          // handle aborts quietly
          if (e && e.name === "AbortError") {
            console.debug("Experiment fetch aborted");
            setStatus("stopped");
            return;
          }
          console.error(e);
          setStatus("error: " + (e?.message ?? String(e)));
        }
      }, Math.floor(recSeconds * 1000));
    };
    // make starter available immediately (in case buffer already has frames)
    startTimerRef.current = startTimerWhenReady;

    if ((bufferArrayRef.current?.length || 0) > 0) {
      setStatus("recording");
      startTimerWhenReady();
    } else {
      const waitId = window.setInterval(() => {
        if ((bufferArrayRef.current?.length || 0) > 0) {
          window.clearInterval(waitId);
          setStatus("recording");
          startTimerWhenReady();
        }
      }, 200);
    }
  };

  // submitBuffer removed: cycle uses startCycleWithBlob and explicit timers

  const recordedSeconds = Math.floor((buffer.length || 0) / Number(samplingRate));

  return (
    <div style={{ border: "1px solid #ddd", padding: 10, borderRadius: 6 }}>
      <div style={{ marginBottom: 8 }}><strong>Experiment Player</strong></div>

      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <Button variant="default" onClick={handleStart} disabled={recording || status === "generating" || status.startsWith("playing")}>Run analysis / Generate</Button>
        <Button variant="destructive" onClick={handleStop} disabled={!recording}>Stop</Button>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
        <label>Target Valence: <input type="number" value={targetValence} min={0} max={1} step={0.01} onChange={(e) => setTargetValence(Number(e.target.value))} /></label>
        <label>Target Arousal: <input type="number" value={targetArousal} min={0} max={1} step={0.01} onChange={(e) => setTargetArousal(Number(e.target.value))} /></label>
        <label>Duration(s): <input type="number" value={duration} min={1} max={120} step={1} onChange={(e) => setDuration(Number(e.target.value))} /></label>
        <label>Seed: <input type="text" value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="optional integer" /></label>
        <label>Music backend: <select value={provider} onChange={(e) => setProvider(e.target.value)} disabled={recording}>
          {/* <option value="stable">Stable Audio Open</option> */}
          <option value="mrt2">Magenta RealTime 2</option>
        </select></label>
      </div>

      <div style={{ marginBottom: 8 }}>
        <div><strong>Status:</strong> {status}</div>
        <div><strong>Recording:</strong> {recording ? `Recording... ${recordedSeconds}/60s` : "Not recording"}</div>
        <div><strong>Buffered frames:</strong> {buffer.length} / {requiredSamples}</div>
      </div>
      {/* Live polling display (continuous until Stop pressed) */}
      <div style={{ marginBottom: 12, padding: 8, border: '1px solid #eee', borderRadius: 6 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 8 }}>
          <div><strong>Live Current Valence:</strong> {liveCurrentV === null ? '-' : liveCurrentV.toFixed(4)}</div>
          <div><strong>Live Current Arousal:</strong> {liveCurrentA === null ? '-' : liveCurrentA.toFixed(4)}</div>
          <div style={{ marginLeft: 'auto' }}><small>{livePolling ? 'Polling /experiment/latest' : 'Not polling'}</small></div>
        </div>
        <div style={{ height: 120, width: '100%' }}>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={livePoints.map((p, i) => ({ i, v: p.v, a: p.a }))}>
              <XAxis dataKey="i" hide />
              <YAxis domain={[0,1]} />
              <Tooltip />
              <Line type="monotone" dataKey="v" stroke="#1976d2" dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="a" stroke="#d32f2f" dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
