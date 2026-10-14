// rxjs v6
import { Subject, interval } from "rxjs";
import { map, takeUntil } from "rxjs/operators";
import type { EEGSource } from "./EEGSource";
import type { EEGSample } from "muse-js";

export function createMockSource(sr = 256, BATCH_SIZE = 24): EEGSource {
  let stop$ = new Subject<void>();
  let readings$ = new Subject<EEGSample>();
  let running = false;

  // 時間系
  const stepMs = 1000 / sr;                 // 3.90625ms
  const burstPeriodMs = BATCH_SIZE * stepMs; // 24なら ~93.75ms
  let epochStartAligned = 0;                // サンプル0のepoch時刻（ms, 小数）
  let n = 0;                                // 連番（総サンプル数）
  let burstIndex = 0;                       // Muse互換の index（バースト毎に+1）

  // µVスケール（シンプル）
  const INTENSITY = 1.0;
  const DRIFT_FREQ_HZ = 0.18;
  const DRIFT_UV = 5 * INTENSITY;
  const NOISE_UV_STD = 3.0 * INTENSITY;
  const BLINK_PROB = 0.002;
  const BLINK_UV = 70 * INTENSITY;
  const BLINK_LEN_S = 0.20;

  const s2 = (f:number, a:number, t:number, p=0) => a*Math.sin(2*Math.PI*f*t+p);
  const noise = (std:number) => std * (Math.random()*2 - 1);

  const emitBurst = () => {
    // バースト開始時刻（epoch ms、小数）…最初のサンプルの timestamp
    const t0_s = n / sr;
    // ブリンク包絡（あればバースト全体に乗る）
    let blinkAF = 0;
    const blinkOn = Math.random() < BLINK_PROB;
    const blinkT0 = t0_s;
    const blinkEnv = (t: number) => {
      if (!blinkOn) return 0;
      const u = (t - blinkT0) / BLINK_LEN_S;
      return u >= 0 && u <= 1 ? Math.sin(Math.PI * u) : 0;
    };

    for (let i = 0; i < BATCH_SIZE; i++) {
      const t = (n + i) / sr;                     // 秒
      const ts = epochStartAligned + (n + i) * stepMs;  // epoch ms（小数）… 3.90625ms グリッド

      const drift = s2(DRIFT_FREQ_HZ, DRIFT_UV, t);
      blinkAF = BLINK_UV * blinkEnv(t);

      // α/β/θ（µV）＋ドリフト＋ブリンク＋ホワイトノイズ
      const ch1 = 45*s2(10,1,t) + 20*s2(20,1,t,0.2) + 15*s2(6,1,t,0.6) + drift + 0.3*blinkAF + noise(NOISE_UV_STD);
      const ch2 = 42*s2(11,1,t,0.1) + 18*s2(21,1,t,0.5) + 14*s2(5.5,1,t,0.7) + drift + 1.0*blinkAF + noise(NOISE_UV_STD);
      const ch3 = 40*s2(9.5,1,t,0.25) + 22*s2(19,1,t,0.35) + 16*s2(6.5,1,t,0.8)+ drift + 1.0*blinkAF + noise(NOISE_UV_STD);
      const ch4 = 43*s2(10.5,1,t,0.15)+ 19*s2(18,1,t,0.45)+ 13*s2(7,1,t,0.9) + drift + 0.3*blinkAF + noise(NOISE_UV_STD);

      readings$.next({
        index: burstIndex,                      // ★ バースト共通 index
        timestamp: Math.round(ts / stepMs)*stepMs, // 念のため丸め（= グリッド）
        data: [ch1, ch2, ch3, ch4, Number.NaN], // µV
      });
    }

    n += BATCH_SIZE;     // 総サンプルカウントを進める
    burstIndex += 1;     // ★ Muse同様、バースト毎に index++
  };

  const startStream = () => {
    // バースト周期で tick → その都度 24 件（or 12 件）まとめて next
    interval(Math.max(1, Math.round(burstPeriodMs)))
      .pipe(takeUntil(stop$), map(() => 0))
      .subscribe(() => {
        emitBurst();
      });
    // 立ち上がりですぐ1バースト出しておく（Museの見え方に近づける）
    emitBurst();
  };

  return {
    deviceName: "Mock(4ch)",
    async connect() {
      running = false;
      stop$.next(); stop$.complete(); // stop any in-flight interval before reconnecting
      stop$ = new Subject<void>();
      // Recreate readings$ so stale observers from the previous session
      // (left by @neurosity/pipes operators that don't propagate unsubscription)
      // stay on the old Subject and never receive new data.
      readings$ = new Subject<EEGSample>();
      // epoch基準（小数ms）を 3.90625ms グリッドにスナップ
      const nowEpochMs = performance.timeOrigin + performance.now();
      epochStartAligned = Math.round(nowEpochMs / stepMs) * stepMs;
      n = 0;
      burstIndex = Math.floor((epochStartAligned / 1000) * (sr / BATCH_SIZE)) || 0; // 任意: 初期indexのズレを持たせたいなら調整
      // ↑ index を0開始で良ければ 0 固定でOK
    },
    disconnect() {
      running = false;
      stop$.next(); stop$.complete();
      stop$ = new Subject<void>();
    },
    start() {
      if (running) return;
      running = true;
      startStream();
    },
    pause() {
      running = false;
      stop$.next(); stop$.complete();
      stop$ = new Subject<void>();
    },
    get readings$() { return readings$; },
  };
}
