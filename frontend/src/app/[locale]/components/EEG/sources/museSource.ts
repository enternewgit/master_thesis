// =====================================
// File: src/components/EEG/sources/museSource.ts
// Museソース（※手元のmuse.tsx内の接続/zipSamplesロジックを移植）
// =====================================
import { useState } from "react";
import { Subject, Subscription } from "rxjs";
import { useAtom   } from "jotai";
import type { EEGSource } from "./EEGSource";
import { MuseClient, zipSamples, EEGSample, TelemetryData } from "muse-js";



export function createMuseSource(): EEGSource {
    let readings$ = new Subject<EEGSample>();
    const telemetry$ = new Subject<TelemetryData>();



    let client: MuseClient | null = null;
    let connected = false;
    let streaming = false;

    // async function ensureGatt() {
    //     if (!client?.device?.gatt) throw new Error("No GATT");
    //     if (!client.device.gatt.connected) {
    //         await client.device.gatt.connect();
    //     }
    // }
    let zipSub: Subscription | null = null;
    let teleSub: Subscription | null = null;
    let gattDisconnectListener: (() => void) | null = null;


    return {
        deviceName: "Muse",
        async connect() {
            try {
                if (connected) return;

                // Clean up stale handles from any previous session before creating new client
                // (covers both explicit disconnect path and hardware-disconnect path)
                if (gattDisconnectListener) {
                    (client as any)?._device?.removeEventListener?.(
                        "gattserverdisconnected",
                        gattDisconnectListener
                    );
                    gattDisconnectListener = null;
                }
                zipSub?.unsubscribe();
                zipSub = null;
                teleSub?.unsubscribe();
                teleSub = null;

                // Recreate readings$ so stale observers from @neurosity/pipes
                // that don't propagate unsubscription stay on the old Subject.
                readings$ = new Subject<EEGSample>();

                client = new MuseClient();
                await client.connect();
                connected = true;

                // Store subscriptions so they can be cleaned up on disconnect
                zipSub = client.eegReadings.pipe(zipSamples).subscribe((s: EEGSample) => {
                    readings$.next(s);
                });
                teleSub = client.telemetryData.subscribe((t: TelemetryData) => {
                    telemetry$.next(t);
                });

                // Register disconnect listener; store reference for removal
                gattDisconnectListener = () => {
                    connected = false;
                    streaming = false;
                };
                (client as any)?._device?.addEventListener?.(
                    "gattserverdisconnected",
                    gattDisconnectListener
                );
            } catch (e) {
                console.error("[Muse] connection failed", e);
                connected = false;
                client = null;
                throw e;
            }
        },
        async disconnect() {
            // Remove the GATT event listener before disconnecting
            if (gattDisconnectListener) {
                (client as any)?._device?.removeEventListener?.(
                    "gattserverdisconnected",
                    gattDisconnectListener
                );
                gattDisconnectListener = null;
            }
            // Unsubscribe inner observables
            zipSub?.unsubscribe(); zipSub = null;
            teleSub?.unsubscribe(); teleSub = null;
            // Disconnect BLE client
            try { await client?.disconnect(); } catch { }
            connected = false;
            streaming = false;
            client = null;
        },
        async start() {
            if (!connected || !client) {
                throw new Error("Cannot start: device not connected");
            }
            if (streaming) {
                console.log("[Muse] Already streaming, ignoring start request");
                return; // 既にストリーミング中の場合はエラーにしない
            }
            try {
                await client.start();
                streaming = true;
            } catch (e) {
                console.error("[Muse] start failed", e);
                streaming = false;
                throw e; // 上位にエラーを伝播
            }
        },

        async pause() {
            if (!connected || !streaming || !client) return;
            try {
                await client.pause();
            } catch (e) {
                console.warn("[Muse] pause failed (ignored)", e);
            } finally {
                streaming = false;
            }
        },
        get readings$() { return readings$; },
        telemetry$,
    };
}

