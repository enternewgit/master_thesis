// src/components/eeg/pipeline/EEGPipeline.tsx
"use client";
import { useEffect, useRef } from "react";
import { useAtom } from "jotai";
import { eegSettingsAtom, rawDataAtom, jsonDataAtom, lastDataTimestampAtom } from "../museClientAtom";
import { pipelineGenerationAtom, deviceAtom, streamingAtom, connectedAtom, batteryLevelAtom, sheetOpenAtom, errorMessageAtom } from "./EEGatoms";
import { createMockSource } from "./sources/mockSource";
import { createMuseSource } from "./sources/museSource";

import {
    highpassFilter,
    lowpassFilter,
    notchFilter,
    epoch,
    fft,
    powerByBand,
} from "@neurosity/pipes";

import { OperatorFunction } from "rxjs";
import { tap } from "rxjs/operators";

export default function EEGPipeline() {
    const [settings] = useAtom(eegSettingsAtom);
    const [, setRawData] = useAtom(rawDataAtom);
    const [, setJsonData] = useAtom(jsonDataAtom);
    const [, setLastDataTimestamp] = useAtom(lastDataTimestampAtom);

    const [generation] = useAtom(pipelineGenerationAtom);
    const [device] = useAtom(deviceAtom);
    const [isStreaming, setIsStreaming] = useAtom(streamingAtom);
    const [isConnected, setIsConnected] = useAtom(connectedAtom);
    const [open, setOpen] = useAtom(sheetOpenAtom);
    const [batteryLevel, setBatteryLevel] = useAtom(batteryLevelAtom);
    const [, setErrorMessage] = useAtom(errorMessageAtom);

    const sourceRef = useRef<ReturnType<typeof createMuseSource> | ReturnType<typeof createMockSource> | null>(null);
    const subRef = useRef<{ unsub?: () => void } | null>(null);
    const lastDataTimestampRef = useRef<number>(Date.now());
    const isConnectedRef = useRef(false);

    useEffect(() => {
        isConnectedRef.current = isConnected;
    }, [isConnected]);

    // cleanupSub is a plain function (not useCallback) — refs are stable so it never needs memoization
    const cleanupSub = () => {
        const s = subRef.current;
        subRef.current = null;
        s?.unsub?.();
    };

    // Effect 1: source lifecycle — device switch or forced reload
    useEffect(() => {
        console.log("[Pipeline] create source (device=", device, ", gen=", generation, ")");
        cleanupSub();
        sourceRef.current?.pause?.();
        sourceRef.current?.disconnect?.();
        setIsConnected(false);  // user must reconnect after device/gen change
        setIsStreaming(false);
        sourceRef.current = device === "muse"
            ? createMuseSource()
            : createMockSource(settings.SamplingRate ?? 256);

        return () => {
            cleanupSub();
            sourceRef.current?.pause?.();
            sourceRef.current?.disconnect?.();
            sourceRef.current = null;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [device, generation]);

    // Effect 2: connection — BLE connect / disconnect only
    useEffect(() => {
        const src = sourceRef.current;
        if (!src) return;
        let cancelled = false;

        if (isConnected) {
            console.log("[Pipeline] connect()");
            (async () => {
                try {
                    await src.connect();
                    if (cancelled) return;
                    setIsStreaming(true);
                    setErrorMessage(null);
                } catch (error) {
                    if (cancelled) return;
                    console.error("[Pipeline] Connection failed:", error);
                    setErrorMessage(`Connection failed: ${error}`);
                    setIsConnected(false);
                    setIsStreaming(false);
                }
            })();
        } else {
            console.log("[Pipeline] disconnect()");
            cleanupSub();
            setIsStreaming(false);
            (async () => {
                try {
                    await src.pause?.();
                    await src.disconnect?.();
                } catch (error) {
                    console.warn("[Pipeline] Disconnect failed:", error);
                }
            })();
        }

        return () => {
            cancelled = true; // prevent stale async from firing after re-render
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isConnected]);

    // Effect 3: streaming pipeline — build and subscribe to the RxJS pipeline
    // settings intentionally omitted from deps — only applied at start/reload time
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        let cancelled = false;

        cleanupSub(); // ALWAYS first — kill any pre-existing subscription

        const src = sourceRef.current;
        if (!src) return;

        if (!isConnectedRef.current || !isStreaming) {
            src.pause?.();
            return;
        }

        (async () => {
            try {
                // await even though the interface types start() as void —
                // museSource.start() returns a Promise at runtime
                await (src.start as () => Promise<void> | void)();
                if (cancelled) return;
                setOpen(false);
            } catch (error) {
                if (cancelled) return;
                console.error("[Pipeline] Start streaming failed:", error);
                setErrorMessage(`Start streaming failed: ${error}`);
                return; // abort before any subscription is created
            }

            if (cancelled) return;

            console.log("[Pipeline] START streaming, subscribing to readings$");

            const epochOperator = epoch({
                duration: settings.Duration,
                interval: settings.Interval,
                samplingRate: settings.SamplingRate,
            }) as unknown as OperatorFunction<any, any>;

            const notchFilterOperator = notchFilter({
                nbChannels: settings.nbChannels,
                cutoffFrequency: settings.NotchFilterFrequency,
            }) as unknown as OperatorFunction<any, any>;

            const highpassFilterOperator = highpassFilter({
                nbChannels: settings.nbChannels,
                cutoffFrequency: settings.cutOffLow,
            }) as unknown as OperatorFunction<any, any>;

            const lowpassFilterOperator = lowpassFilter({
                nbChannels: settings.nbChannels,
                cutoffFrequency: settings.cutOffHigh,
            }) as unknown as OperatorFunction<any, any>;

            const fftOperator = fft({
                bins: settings.SamplingRate,
            }) as unknown as OperatorFunction<any, any>;

            const powerByBandOperator = powerByBand() as unknown as OperatorFunction<any, any>;

            let pipeline = src.readings$.pipe(
                tap((data: any) => {
                    lastDataTimestampRef.current = Date.now();
                    setLastDataTimestamp(Date.now());
                    setRawData((prevData) => {
                        const maxKeep = Number(settings.SamplingRate || 256) * 80;
                        const out = Array.isArray(prevData) ? prevData.concat(data) : [data];
                        return out.length > maxKeep ? out.slice(-maxKeep) : out;
                    });
                })
            );

            if (settings.NotchFilter) pipeline = pipeline.pipe(notchFilterOperator);
            if (settings.HighpassFilter) pipeline = pipeline.pipe(highpassFilterOperator);
            if (settings.LowpassFilter) pipeline = pipeline.pipe(lowpassFilterOperator);

            let lastData: number[][] = [];
            let lastPSD: number[][] = [];
            let lastInfo: any = {};

            pipeline = pipeline.pipe(
                epochOperator,
                tap((epoched: any) => {
                    lastData = epoched.data;
                }),
                fftOperator,
                tap((fftOut: any) => {
                    lastPSD = fftOut.psd;
                    lastInfo = fftOut.info;
                }),
                powerByBandOperator,
            );

            const sub = pipeline.subscribe({
                next: (bandPowers: any) => {
                    setJsonData({
                        data: lastData,
                        psd: lastPSD,
                        bandPowers: bandPowers,
                        info: lastInfo,
                    });
                },
                error: (error: any) => {
                    console.error("[Pipeline] Data processing error:", error);
                    setErrorMessage(`Data processing error: ${error}`);
                }
            });

            let telemetrySubscription: { unsubscribe: () => void } | undefined;
            if (src.telemetry$) {
                telemetrySubscription = src.telemetry$.subscribe({
                    next: (telemetry) => {
                        if (typeof telemetry.batteryLevel === "number") {
                            setBatteryLevel(telemetry.batteryLevel);
                        }
                    },
                    error: (error) => {
                        console.warn("[Pipeline] Telemetry error:", error);
                    }
                });
            }

            // Final cancelled check: effect may have been cleaned up while the async
            // block was executing — unsubscribe and bail if so
            if (cancelled) {
                sub.unsubscribe();
                telemetrySubscription?.unsubscribe();
                return;
            }

            subRef.current = {
                unsub: () => {
                    sub.unsubscribe();
                    telemetrySubscription?.unsubscribe();
                }
            };
        })();

        return () => {
            cancelled = true; // prevent in-flight start() from creating a subscription
            cleanupSub();
        };
    }, [isStreaming, generation]);



    // データが来ているか監視し、途絶えていたら警告を出す
    useEffect(() => {
        let timeoutId: any;

        if (isStreaming) {
            timeoutId = setInterval(() => {
                const now = Date.now();
                const lastUpdated = lastDataTimestampRef.current || now;
                if (now - lastUpdated > 2000) { // 2秒以上データ更新なし
                    console.warn("No data received for 2 seconds, checking connection...");
                    setErrorMessage("No data received");
                    setIsConnected(false);
                    setIsStreaming(false); 

                    
                }
            }, 5000);// 5秒ごとにチェック
        }

        return () => clearInterval(timeoutId);
    }, [isStreaming]);

    return null;
}
