"use client";
import { useEffect, useRef, useState } from "react";
import { useAtom } from "jotai";
import { liveVAAtom } from "../museClientAtom";
import { getWsBase } from "@/lib/apiBase";
import { Button } from "@/components/ui/button";

type ConnectionStatus = "idle" | "connecting" | "connected" | "error" | "disconnected";

const DEFAULT_DURATION = 12;

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
  const requestInFlightRef = useRef(false);
  const runningRef = useRef(false);
  const currentAudioUrlRef = useRef<string | null>(null);

  const sendChunkRequest = (socket: WebSocket): boolean => {
    const va = liveVARef.current;
    if (!va || va.v === null || va.a === null) return false;
    const { targetValence: tv, targetArousal: ta, duration: dur } = targetRef.current;
    requestInFlightRef.current = true;
    socket.send(JSON.stringify({
      current_v: va.v,
      current_a: va.a,
      target_valence: tv,
      target_arousal: ta,
      duration: dur,
    }));
    return true;
  };

  // Retries the initial chunk request while waiting for a live valence/arousal
  // reading to become available. Only relevant before the first chunk has
  // arrived -- once one plays, onmessage requests every subsequent chunk itself.
  const scheduleInitialRetry = (socket: WebSocket) => {
    setTimeout(() => {
      if (!runningRef.current) return;
      if (socket.readyState !== WebSocket.OPEN) return;
      if (requestInFlightRef.current) return;
      if (audioRef.current && !audioRef.current.paused) return;

      const sent = sendChunkRequest(socket);
      if (!sent) {
        setErrorMessage("Waiting for live valence/arousal...");
        scheduleInitialRetry(socket);
      } else {
        setErrorMessage(null);
      }
    }, 500);
  };

  // Every chunk plays on loop until the next one arrives and swaps in -- however
  // long generation takes, there's never dead air, since the current chunk just
  // keeps repeating in the meantime.
  const playChunk = (chunk: PendingChunk) => {
    if (!audioRef.current) audioRef.current = new Audio();
    const audio = audioRef.current;
    if (currentAudioUrlRef.current) {
      URL.revokeObjectURL(currentAudioUrlRef.current);
    }
    currentAudioUrlRef.current = chunk.audioUrl;
    audio.loop = true;
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
      const sent = sendChunkRequest(socket);
      if (!sent) {
        setErrorMessage("Waiting for live valence/arousal...");
        scheduleInitialRetry(socket);
      }
    };

    socket.onerror = () => setStatus("error");

    socket.onclose = () => {
      setStatus("disconnected");
      runningRef.current = false;
      setRunning(false);
      requestInFlightRef.current = false;
      pendingPromptRef.current = null;
    };

    socket.onmessage = (event) => {
      if (!runningRef.current) return;
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
        setErrorMessage(null);

        // Swap in the new chunk right away -- the chunk that was looping keeps
        // covering playback until this exact moment, so there's no gap to time.
        playChunk({ prompt, audioUrl });

        // Start generating the next chunk immediately. No rush: the chunk we just
        // started playing loops for as long as it takes, so this only maximizes
        // how much lead time generation gets.
        if (runningRef.current && wsRef.current?.readyState === WebSocket.OPEN) {
          sendChunkRequest(wsRef.current);
        }
      }
    };
  };

  const handleStop = () => {
    runningRef.current = false;
    setRunning(false);
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
    }
    if (currentAudioUrlRef.current) {
      URL.revokeObjectURL(currentAudioUrlRef.current);
      currentAudioUrlRef.current = null;
    }
    pendingPromptRef.current = null;
    requestInFlightRef.current = false;
    setCurrentPrompt(null);
    setErrorMessage(null);
    setStatus("idle");
  };

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.onopen = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.onmessage = null;
        wsRef.current.close();
      }
      if (audioRef.current) audioRef.current.pause();
      if (currentAudioUrlRef.current) {
        URL.revokeObjectURL(currentAudioUrlRef.current);
        currentAudioUrlRef.current = null;
      }
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
        <Button variant="default" onClick={handleStart} disabled={running}>Start</Button>
        <Button variant="destructive" onClick={handleStop} disabled={!running}>Stop</Button>
      </div>

      <div style={{ fontSize: 13 }}>
        <strong>Prompt:</strong> {currentPrompt ?? "-"}
      </div>
    </div>
  );
}
