// =====================================
// File: src/components/EEG/sources/EEGSource.ts
// デバイス接続の共通インターフェース
// =====================================

import type { Observable } from "rxjs";
import { EEGSample } from "muse-js";


// export type EEGSample = {
//     index: number;
//     timestamp: number; // ms
//     data: number[]; // [ch1.., chN, aux?]
// };


export interface EEGSource {
    deviceName?: string;
    connect(): Promise<void>;
    disconnect(): Promise<void> | void;
    start(): void; // ストリーム開始（購読はPipeline側）
    pause(): void; // 一時停止
    readings$: Observable<EEGSample>;
    telemetry$?: Observable<any>;
}