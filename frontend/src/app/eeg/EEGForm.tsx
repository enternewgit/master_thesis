"use client";
import { useEffect, useState } from "react";
import { getApiBase } from "@/lib/apiBase";

type ModelParams = {
  n_channels: number;
  seq_len: number;
  n_classes?: number;
  d_model?: number;
  n_layers?: number;
  dropout?: number;
};

export default function EEGForm() {
  const [input, setInput] = useState<string>("[[]]");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [modelParams, setModelParams] = useState<ModelParams | null>(null);
  const [modelLoaded, setModelLoaded] = useState<boolean>(false);
  const apiBase = getApiBase();

  useEffect(() => {
    // fetch model status so frontend can validate against expected shape
    let mounted = true;
    fetch(`${apiBase}/eeg_emotion/status`).then(async (res) => {
      try {
        const j = await res.json();
        if (!mounted) return;
        setModelLoaded(Boolean(j?.loaded));
        if (j?.params) setModelParams(j.params as ModelParams);
      } catch (e) {
        // ignore
      }
    }).catch(() => {
      // ignore
    });
    return () => { mounted = false; };
  }, [apiBase]);

  function validateAndParse(text: string) {
    const errs: string[] = [];
    let parsed: any = null;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      errs.push("Invalid JSON");
      return { ok: false, errors: errs, samples: null };
    }

    if (!Array.isArray(parsed)) {
      errs.push("Top-level JSON must be an array");
      return { ok: false, errors: errs, samples: null };
    }

    if (parsed.length === 0) {
      errs.push("Array is empty");
      return { ok: false, errors: errs, samples: null };
    }

    // detect shape
    // 2D: channels x seq -> parsed[0] is number[]
    // 3D: batch x channels x seq -> parsed[0][0] is number[]
    const is2D = parsed.every((r: any) => Array.isArray(r) && r.length > 0 && typeof r[0] === "number");
    const is3D = parsed.every((b: any) => Array.isArray(b) && b.length > 0 && Array.isArray(b[0]) && typeof b[0][0] === "number");

    if (!is2D && !is3D) {
      errs.push("Array must be 2D (channels x seq) or 3D (batch x channels x seq) of numbers");
      return { ok: false, errors: errs, samples: null };
    }

    let channels = 0;
    let seq = 0;
    if (is2D) {
      channels = parsed.length;
      seq = parsed[0].length;
      // check all rows same length and numeric
      for (let i = 0; i < parsed.length; i++) {
        if (!Array.isArray(parsed[i])) { errs.push(`Row ${i} is not an array`); break; }
        if (parsed[i].length !== seq) { errs.push(`Row ${i} length ${parsed[i].length} != ${seq}`); break; }
        for (let j = 0; j < parsed[i].length; j++) {
          const v = parsed[i][j];
          if (typeof v !== "number" || !Number.isFinite(v)) { errs.push(`Non-finite value at [${i}][${j}]`); break; }
        }
        if (errs.length) break;
      }
    } else {
      // 3D
      const batch = parsed.length;
      channels = parsed[0].length;
      seq = parsed[0][0].length;
      for (let b = 0; b < parsed.length; b++) {
        if (!Array.isArray(parsed[b])) { errs.push(`Batch ${b} is not array`); break; }
        if (parsed[b].length !== channels) { errs.push(`Batch ${b} channels ${parsed[b].length} != ${channels}`); break; }
        for (let c = 0; c < parsed[b].length; c++) {
          if (!Array.isArray(parsed[b][c])) { errs.push(`Batch ${b} channel ${c} not array`); break; }
          if (parsed[b][c].length !== seq) { errs.push(`Batch ${b} channel ${c} length ${parsed[b][c].length} != ${seq}`); break; }
          for (let t = 0; t < parsed[b][c].length; t++) {
            const v = parsed[b][c][t];
            if (typeof v !== "number" || !Number.isFinite(v)) { errs.push(`Non-finite value at [${b}][${c}][${t}]`); break; }
          }
          if (errs.length) break;
        }
        if (errs.length) break;
      }
    }

    // check against model params if available
    if (modelParams) {
      if (channels !== modelParams.n_channels) {
        errs.push(`Expected ${modelParams.n_channels} channels, got ${channels}`);
      }
      if (seq !== modelParams.seq_len) {
        errs.push(`Expected seq_len ${modelParams.seq_len}, got ${seq}`);
      }
    }

    return { ok: errs.length === 0, errors: errs, samples: parsed };
  }

  function onInputChange(v: string) {
    setInput(v);
    const ret = validateAndParse(v);
    setErrors(ret.errors);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setResult(null);
    const val = validateAndParse(input);
    if (!val.ok) {
      setErrors(val.errors);
      return;
    }
    if (!modelLoaded) {
      setErrors(["Model not loaded on server yet"]);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/eeg_emotion/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ samples: val.samples }),
      });
      const data = await res.json();
      setResult({ status: res.status, body: data });
    } catch (err) {
      setResult({ error: String(err) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit}>
        <label>EEG samples (JSON array):</label>
        <textarea
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          rows={10}
          style={{ width: "100%" }}
        />

        <div style={{ marginTop: 8 }}>
          <button type="submit" disabled={loading || !modelLoaded || errors.length > 0}>
            {modelLoaded ? (loading ? "Predicting..." : "Predict Emotion") : "Model loading..."}
          </button>
        </div>
      </form>

      <div style={{ marginTop: 12 }}>
        <strong>Model:</strong>
        <pre>{JSON.stringify(modelParams ?? { loaded: modelLoaded }, null, 2)}</pre>
      </div>

      <div style={{ marginTop: 12 }}>
        <strong>Validation Errors:</strong>
        {errors.length === 0 ? (
          <div>None</div>
        ) : (
          <ul>
            {errors.map((e, i) => (
              <li key={i} style={{ color: "#a00" }}>{e}</li>
            ))}
          </ul>
        )}
      </div>

      <div style={{ marginTop: 12 }}>
        <strong>Result:</strong>
        <pre>{JSON.stringify(result, null, 2)}</pre>
      </div>
    </div>
  );
}
