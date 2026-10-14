"use client";
import { useState, useEffect, useRef } from "react";
import { useAtom } from "jotai";
import { rawDataAtom, liveVAAtom } from "../museClientAtom";
import ExperimentPlayer from "./ExperimentPlayer";
import { getApiBase } from "@/lib/apiBase";
import { Button } from "@/components/ui/button";

export default function Player() {
  const [status, setStatus] = useState<string>("idle");
  const [preset, setPreset] = useState<string>("calm");
  const [provider, setProvider] = useState<string>("mrt2");
  const [valence, setValence] = useState<number | null>(null);
  const [arousal, setArousal] = useState<number | null>(null);
  const [vaHistory, setVaHistory] = useState<Array<{ x: number; y: number; t: number }>>([]);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [rawData] = useAtom(rawDataAtom);
  const [liveVA] = useAtom(liveVAAtom);

  const presets = [
    { id: "calm", name: "Calm / Relaxing", prompt: "A calm, relaxing ambient piano loop" },
    { id: "focus", name: "Focus / Ambient", prompt: "An ambient, minimal focus-friendly background texture" },
    { id: "energetic", name: "Energetic / Upbeat", prompt: "An energetic upbeat short loop with percussion and synth" },

  ];
  const [modelParams, setModelParams] = useState<{ n_channels?: number; seq_len?: number } | null>(null);
  useEffect(() => {
    const apiBase = getApiBase();
    let mounted = true;
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
  const [experimentMode, setExperimentMode] = useState<boolean>(false);
  // sync with ExperimentPlayer live VA if available
  useEffect(() => {
    if (liveVA && liveVA.v !== null && liveVA.a !== null) {
      const tx2 = (liveVA.v * 2) - 1;
      const ty2 = (liveVA.a * 2) - 1;
      setVaHistory((s) => {
        const next = s.concat({ x: tx2, y: ty2, t: Date.now() });
        return next.slice(-50);
      });
    }
  }, [liveVA]);
  

  useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [audioUrl]);

  const handleAnalyze = async () => {
    setStatus("running");
    try {
      // 1) Prepare samples from rawData (channels x seq)
      const DEFAULT_SEQ_LEN = 100; // fallback if model doesn't advertise seq_len
      if (!rawData || rawData.length === 0) {
        throw new Error("No EEG data available");
      }
      // determine seq_len and expected channels from model params when available
      const seqLen = modelParams?.seq_len ?? DEFAULT_SEQ_LEN;

      // build window of last seqLen samples (pad with zeros at start if needed)
      const window = rawData.slice(-seqLen);
      const padCount = seqLen - window.length;

      // channels in the incoming data
      const incomingChannels = window.length > 0 ? (window[0].data?.length ?? 0) : 0;

      // expected channels from model (fallback to incoming or 4)
      const expectedChannels = modelParams?.n_channels ?? (incomingChannels || 4);

      // build samples with shape [expectedChannels][seqLen], initialized to 0
      const samples: number[][] = Array.from({ length: expectedChannels }, () => Array(seqLen).fill(0));

      // fill with padding zeros for first padCount columns (already zeroed)
      for (let t = 0; t < window.length; t++) {
        const row = window[t].data || [];
        const targetIdx = padCount + t;
        for (let c = 0; c < expectedChannels; c++) {
          // If incoming has more channels, we take the first expectedChannels
          // If incoming has fewer channels, missing channels remain 0
          const v = c < row.length && typeof row[c] === "number" && Number.isFinite(row[c]) ? row[c] : 0;
          samples[c][targetIdx] = v;
        }
      }

      // If incomingChannels > expectedChannels, we trimmed extra channels by ignoring them.
      if (incomingChannels > expectedChannels) {
        console.warn(`Incoming EEG has ${incomingChannels} channels, trimming to expected ${expectedChannels}`);
      }

      // 2) Call backend /eeg_emotion/predict
      const apiBase = getApiBase();
      const predictRes = await fetch(`${apiBase}/eeg_emotion/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ samples }),
      });
      if (!predictRes.ok) {
        const text = await predictRes.text();
        throw new Error(`Predict failed: ${text}`);
      }
      const predictJson = await predictRes.json();
      const v = Number(predictJson.valence ?? predictJson.val ?? 0.0);
      const a = Number(predictJson.arousal ?? predictJson.aro ?? 0.0);
      setValence(v);
      setArousal(a);
      // Transform probabilities [0,1] -> circumplex coordinates [-1,1]
      const tx = (v * 2) - 1;
      const ty = (a * 2) - 1;
      setVaHistory((s) => {
        const next = s.concat({ x: tx, y: ty, t: Date.now() });
        // keep recent 50 points
        return next.slice(-50);
      });

      // 3) Build prompt from preset + emotion values
      const presetObj = presets.find((p) => p.id === preset) ?? presets[0];
      const prompt = `${presetObj.prompt}. Match valence ${v.toFixed(2)} and arousal ${a.toFixed(2)}.`;

      // 4) Call music generation endpoint
      const genRes = await fetch(`${apiBase}/music/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, provider, duration: 8 }),
      });

      if (!genRes.ok) {
        const text = await genRes.text();
        throw new Error(`Music generate failed: ${text}`);
      }

      // receive audio as blob and play
      const blob = await genRes.blob();
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);

      // create or reuse audio element
      if (!audioRef.current) {
        audioRef.current = new Audio();
      }
      audioRef.current.src = url;
      await audioRef.current.play();
      setStatus("playing");
      audioRef.current.onended = () => setStatus("done");
    } catch (e: any) {
      console.error(e);
      setStatus("error: " + (e?.message ?? String(e)));
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 8 }}><strong>Music Generator</strong></div>

      <div style={{ marginBottom: 8 }}>
        <label style={{ display: "block", marginBottom: 6 }}>Select preset</label>
        <select value={preset} onChange={(e) => setPreset(e.target.value)}>
          {presets.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      <div style={{ marginBottom: 8 }}>
        <label style={{ display: "block", marginBottom: 6 }}>Music backend</label>
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {/* <option value="stable">Stable Audio Open</option> */}
          <option value="mrt2">Magenta RealTime 2</option>
        </select>
      </div>

      <div style={{ marginBottom: 8 }}>
        <label style={{ marginRight: 12 }}>
          <input type="checkbox" checked={experimentMode} onChange={(e) => setExperimentMode(e.target.checked)} /> Experiment Mode
        </label>
        <Button variant="default" onClick={handleAnalyze} disabled={experimentMode || status === "running" || status === "playing"}>
          {status === "running" ? "Working..." : status === "playing" ? "Playing..." : "Run analysis / Generate"}
        </Button>
      </div>

      <div style={{ marginTop: 8 }}>
        <div><strong>Emotion:</strong> valence: {valence === null ? "-" : valence.toFixed(3)}, arousal: {arousal === null ? "-" : arousal.toFixed(3)}</div>
        <div><strong>Status:</strong> {status}</div>
      </div>

      {/* Circumplex plot: map [0,1] -> [-1,1] with C = (P*2)-1 and render SVG */}
      <div style={{ marginTop: 12 }}>
        <svg width={240} height={240} viewBox="0 0 240 240" style={{ border: "1px solid #eee", background: "#fff" }}>
          {/* center and radius */}
          <g>
            <circle cx={120} cy={120} r={90} stroke="#ccc" strokeWidth={1} fill="none" />
            {/* axes */}
            <line x1={30} y1={120} x2={210} y2={120} stroke="#999" strokeWidth={1} />
            <line x1={120} y1={30} x2={120} y2={210} stroke="#999" strokeWidth={1} />
            {/* quadrant labels */}
            <text x={160} y={50} fontSize={12} fill="#333">Happy / Excited</text>
            <text x={50} y={50} fontSize={12} fill="#333">Angry / Distressed</text>
            <text x={50} y={190} fontSize={12} fill="#333">Sad / Depressed</text>
            <text x={150} y={190} fontSize={12} fill="#333">Relaxed / Calm</text>

            {/* draw trajectory */}
            {vaHistory.length > 0 && (() => {
              const r = 80; // plotting radius inside circle
              const cx = 120, cy = 120;
              const points = vaHistory.map(p => {
                const px = cx + p.x * r;
                const py = cy - p.y * r; // invert Y for SVG
                return `${px},${py}`;
              }).join(" ");
              return (
                <polyline points={points} fill="none" stroke="#2b6cb0" strokeWidth={2} strokeOpacity={0.7} />
              );
            })()}

            {/* current point */}
            {valence !== null && arousal !== null && (() => {
              const tx = (valence * 2) - 1;
              const ty = (arousal * 2) - 1;
              const r = 80;
              const cx = 120, cy = 120;
              const px = cx + tx * r;
              const py = cy - ty * r;
              return (
                <g>
                  <circle cx={px} cy={py} r={8} fill="#e53e3e" stroke="#fff" strokeWidth={2} />
                  <text x={px + 12} y={py - 8} fontSize={12} fill="#111">{`${tx >= 0 ? '+' : ''}${tx.toFixed(2)}, ${ty >= 0 ? '+' : ''}${ty.toFixed(2)}`}</text>
                </g>
              );
            })()}
          </g>
        </svg>
      </div>

      {audioUrl && (
        <div style={{ marginTop: 8 }}>
          <audio controls src={audioUrl} />
        </div>
      )}

      {experimentMode && (
        <div style={{ marginTop: 12 }}>
          <ExperimentPlayer />
        </div>
      )}
    </div>
  );
}
