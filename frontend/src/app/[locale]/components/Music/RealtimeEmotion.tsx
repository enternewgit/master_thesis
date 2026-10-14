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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Kept in sync with rawData below so the send interval always reads the latest
  // buffer, instead of a stale snapshot captured when the effect last ran.
  const rawDataRef = useRef(rawData);
  // Tracks whether a previously sent window is still awaiting a response, so the
  // send interval can back off instead of piling up requests on a busy backend.
  const pendingRef = useRef(false);
  // Kept in sync with modelParams below so it can be read inside the send interval
  // without being a dependency of the WebSocket-lifecycle effect -- if it were,
  // the fetch below resolving mid-handshake would tear down and recreate the
  // socket, closing it before it finished connecting.
  const modelParamsRef = useRef(modelParams);

  useEffect(() => {
    rawDataRef.current = rawData;
  }, [rawData]);

  useEffect(() => {
    modelParamsRef.current = modelParams;
  }, [modelParams]);

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
      pendingRef.current = false;
      try {
        const data = JSON.parse(event.data);
        if (data.error) {
          setErrorMessage(String(data.error));
          return;
        }
        const v = Number(data.valence);
        const a = Number(data.arousal);
        if (!Number.isFinite(v) || !Number.isFinite(a)) return;
        setErrorMessage(null);
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

    const intervalId = window.setInterval(() => {
      if (socket.readyState !== WebSocket.OPEN) return;
      if (pendingRef.current) return;
      const current = rawDataRef.current;
      if (!current || current.length === 0) return;

      const seqLen = modelParamsRef.current?.seq_len ?? DEFAULT_SEQ_LEN;
      const expectedChannels = modelParamsRef.current?.n_channels ?? DEFAULT_CHANNELS;

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
      pendingRef.current = true;
      socket.send(JSON.stringify({ samples }));
    }, SEND_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
      socket.onopen = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close();
      }
    };
  }, [connected, setLiveVA]);

  const statusColor = status === "connected" ? "#2e7d32" : status === "error" ? "#c62828" : "#757575";

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <strong>Realtime Emotion</strong>
        <span style={{ marginLeft: 8, fontSize: 12, color: statusColor }}>{status}</span>
        {errorMessage && (
          <span style={{ marginLeft: 8, fontSize: 12, color: "#c62828" }}>({errorMessage})</span>
        )}
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
