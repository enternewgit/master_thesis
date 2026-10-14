// =====================================
// File: src/components/eeg/EEGSheetRunner.tsx
// (新規) SheetベースのUI（接続/Start/Stop、フィルタ設定、Reload）
// =====================================
"use client";
import { useState, useEffect, useRef } from "react";
import { useCookies } from "react-cookie";
import { useAtom } from "jotai";
import EEGPipeline from "./EEGpipeline";
import { pipelineGenerationAtom, settingsDirtyAtom, deviceAtom, streamingAtom, connectedAtom, sheetOpenAtom, batteryLevelAtom, errorMessageAtom } from "./EEGatoms";
import { eegSettingsAtom, jsonDataAtom } from "../museClientAtom";
import { eegSettings } from "@/types/types";

import { StddevMonitor } from "../StddevMonitor";

// shadcn/ui
import { Button } from "@/components/ui/button";
import { Sheet, SheetTrigger, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

import { PiWaveformBold, PiWaveformSlashBold } from "react-icons/pi";
import { IoReload } from "react-icons/io5";
import {
    FaBatteryFull,
    FaBatteryThreeQuarters,
    FaBatteryHalf,
    FaBatteryQuarter,
    FaBatteryEmpty,
} from "react-icons/fa";
import { AlertCircle } from "lucide-react";

export default function EEGSheetRunner() {
    const [device, setDevice] = useAtom(deviceAtom);
    const [isStreaming, setStreaming] = useAtom(streamingAtom);
    const [isConnected, setConnected] = useAtom(connectedAtom);
    const [open, setOpen] = useAtom(sheetOpenAtom);
    const [batteryLevel] = useAtom(batteryLevelAtom);
    const [errorMessage, setErrorMessage] = useAtom(errorMessageAtom);

    const [JsonData] = useAtom(jsonDataAtom);
    const [settingsAtom, setSettingsAtom] = useAtom(eegSettingsAtom);

    const [dirty, setDirty] = useState(false);

    let BatteryIcon;
    let iconColor;

    if (batteryLevel >= 90) {
        BatteryIcon = FaBatteryFull;
        iconColor = "text-green-500";
    } else if (batteryLevel >= 50) {
        BatteryIcon = FaBatteryThreeQuarters;
        iconColor = "text-white";
    } else if (batteryLevel >= 30) {
        BatteryIcon = FaBatteryHalf;
        iconColor = "text-orange-500";
    } else if (batteryLevel > 0) {
        BatteryIcon = FaBatteryQuarter;
        iconColor = "text-red-500";
    } else {
        BatteryIcon = FaBatteryEmpty;
        iconColor = "text-gray-200";
    }


    // const [, setGeneration] = useAtom(pipelineGenerationAtom);


    const [cookies, setCookie] = useCookies(["museSettings"]);

    // Cookieから設定を読み込むか、デフォルト値を使用
    const [settings, setSettings] = useState<eegSettings>(() => {
        return cookies.museSettings || settingsAtom;
    });

    // 設定が変更されたらCookieに保存
    useEffect(() => {
        setCookie("museSettings", settingsAtom, {
            path: "/",
            maxAge: 7 * 24 * 60 * 60, // 7日間
            sameSite: true,
        });
    }, [settingsAtom, setCookie]);

    const handleSetting = (name: string, value: any) => {
        setSettings((prevSettings) => ({
            ...prevSettings,
            [name]: value,
        }));
    };

    type SettingKeys =
        | "FFT"
        | "HighpassFilter"
        | "LowpassFilter";
    const toggleSwitch = (name: SettingKeys) => {
        setSettings((prevSettings) => ({
            ...prevSettings,
            [name]: !prevSettings[name],
        }));
    };

    const handleValueChange = (value: string) => {
        if (value === "false") {
            handleSetting("NotchFilter", false);
        } else {
            handleSetting("NotchFilter", true);
            const frequency = parseInt(value, 10);
            if (!isNaN(frequency)) {
                handleSetting("NotchFilterFrequency", frequency);
            }
        }
    };

    const skipNextSettingsEffect = useRef(true);
      useEffect(() => {
    if (skipNextSettingsEffect.current) {
      skipNextSettingsEffect.current = false;
      return; // 最初の1回をスキップ
    }
    console.log("Settings changed:", settings);
    setDirty(true);
  }, [settings]);

    const handleConnect = () => {
        setErrorMessage(null); // エラーメッセージをクリア
        setConnected(true);
    };
    const handleDisconnect = () => {
        setStreaming(false);
        setConnected(false);
        setErrorMessage(null); // エラーメッセージをクリア
    };

    const handleStart = () => {
        setStreaming(true);
        setDirty(false);
    };
    const handleStop = () => setStreaming(false);

    const reloadPipeline = () => {
        // エラーメッセージをクリア
        setErrorMessage(null);

        // まず完全にストップ
        setStreaming(false);
        setSettingsAtom(settings); // グローバル設定を更新

        // パイプラインの世代を更新してから少し待ってstart
        // setGeneration((g: number) => g + 1);

        // 状態更新を待ってからstart
        setTimeout(() => {
            setStreaming(true);
            setDirty(false);
        }, 200); // 少し長めに待つ
    };

    useEffect(() => {
        if (errorMessage) {
            setOpen(true);
            // console.log("OpenFlag:", open);
        }
    }, [errorMessage]);


    return (
        <div className="flex items-center">
            <Sheet open={open} onOpenChange={setOpen}>
                <SheetTrigger asChild>
                    <Button variant="link" className="text-white">
                        {isConnected ? (
                            <>
                                <PiWaveformBold size={20} />
                                {device === "muse" ? "Muse" : "Mock"} EEG

                            </>
                        ) : (
                            <>
                                <PiWaveformSlashBold size={20} />
                                Connect {device === "muse" ? "Muse" : "Mock"}
                            </>
                        )}
                    </Button>
                </SheetTrigger>

                <SheetContent className="overflow-y-auto max-h-[90vh]">
                    <SheetHeader>
                        <SheetTitle>{device === "muse" ? "Muse" : "Mock"} Connection</SheetTitle>
                        <SheetDescription>
                            Use this panel to connect, start/stop streaming, and adjust filters. Press Reload to apply filter changes.
                        </SheetDescription>
                    </SheetHeader>

                    {/* デバイス切り替え */}
                    <div className="mt-4">
                        <Select
                            value={device}
                            onValueChange={(v: "muse" | "mock") => setDevice(v)}
                            defaultValue="muse"
                        >
                            <SelectTrigger className="w-[180px] h-8 text-xs mb-4">
                                <div className="flex space-x-1 items-center text-muted-foreground">
                                    <span>Device:</span>
                                </div>
                                <SelectValue placeholder="Select device" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="muse">Muse</SelectItem>
                                <SelectItem value="mock">Mock</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {/* 接続ボタン群 */}
                    <div className="flex items-center mt-4 gap-2">
                        {!isConnected ? (
                            <Button className="bg-blue-500 hover:bg-blue-400" onClick={handleConnect}>Connect</Button>
                        ) : (
                            <Button className="bg-red-500 hover:bg-red-400" onClick={handleDisconnect}>Disconnect</Button>
                        )}

                        {isConnected && !isStreaming && (
                            <Button className="bg-green-500 hover:bg-green-400" onClick={handleStart}>Start</Button>
                        )}
                        {isConnected && isStreaming && (
                            <Button className="bg-gray-500 hover:bg-gray-400" onClick={handleStop}>Stop</Button>
                        )}

                        {isConnected && isStreaming && dirty && (
                            <div className="relative">
                                <Button className="bg-green-500 hover:bg-green-400 text-white" onClick={reloadPipeline}>
                                    Reload
                                    <span className="absolute top-0 right-0 translate-x-1 -translate-y-1">
                                        <span className="relative flex h-4 w-4">
                                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
                                            <span className="relative inline-flex rounded-full h-4 w-4 bg-sky-500"></span>
                                        </span>
                                    </span>
                                </Button>
                            </div>
                        )}
                    </div>

                    {errorMessage && (
                        <Alert variant="destructive" className="relative">
                            <AlertCircle className="h-4 w-4" />
                            <AlertTitle>
                                Device connection failure. Please retry.
                            </AlertTitle>
                            <AlertDescription>{errorMessage.toString()}</AlertDescription>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="absolute top-2 right-2 h-6 w-6 p-0"
                                onClick={() => setErrorMessage(null)}
                            >
                                ×
                            </Button>
                        </Alert>
                    )}
                    <hr className="my-4 border-t border-border" />

                    {/* フィルタ設定 */}
                    <div className="mt-2 p-4 pb-0 flex">
                        <h4 className="mr-2">HighpassFilter:</h4>
                        <Switch
                            id="HighpassFilter"
                            checked={settings.HighpassFilter}
                            onCheckedChange={() => toggleSwitch("HighpassFilter")}
                        />
                    </div>

                    {settings.HighpassFilter && (
                        <>
                            <div className="p-4 pb-0">
                                <label className="mr-2">
                                    CutOffLow:
                                    <input
                                        type="number"
                                        value={settings.cutOffLow}
                                        step={0.1}
                                        min={0}
                                        max={settings.SamplingRate / 2}
                                        onChange={(e) =>
                                            handleSetting(
                                                "cutOffLow",
                                                Number.parseFloat(e.target.value)
                                            )
                                        }
                                        className="ml-2 p-1 border rounded mr-2"
                                    />
                                    Hz
                                </label>
                                <Button
                                    className="p-2"
                                    variant="outline"
                                    onClick={() => handleSetting("cutOffLow", 0.3)}
                                >
                                    <IoReload />
                                </Button>
                                <Slider
                                    defaultValue={[settings.cutOffLow]}
                                    min={0}
                                    max={settings.SamplingRate / 2}
                                    step={0.1}
                                    onValueChange={(value) =>
                                        handleSetting("cutOffLow", value[0])
                                    }
                                />
                            </div>
                        </>
                    )}
                    <div className="p-4 pb-0 flex mt-2">
                        <h4 className="mr-2">LowpassFilter:</h4>
                        <Switch
                            id="lowpassFilterEnabled"
                            checked={settings.LowpassFilter}
                            onCheckedChange={() => toggleSwitch("LowpassFilter")}
                        />
                    </div>
                    {settings.LowpassFilter && (
                        <>
                            <div className="p-4">
                                <label className="mr-2">
                                    CutOffHigh:
                                    <input
                                        type="number"
                                        value={settings.cutOffHigh}
                                        step={0.1}
                                        min={0}
                                        max={settings.SamplingRate / 2}
                                        onChange={(e) =>
                                            handleSetting(
                                                "CutOffHigh",
                                                Number.parseFloat(e.target.value)
                                            )
                                        }
                                        className="ml-2 p-1 border rounded mr-2"
                                    />
                                    Hz
                                </label>
                                <Button
                                    className="p-2"
                                    variant="outline"
                                    onClick={() => handleSetting("cutOffHigh", 50)}
                                >
                                    <IoReload />
                                </Button>
                                <Slider
                                    defaultValue={[settings.cutOffHigh]}
                                    min={0}
                                    max={settings.SamplingRate / 2}
                                    step={0.1}
                                    onValueChange={(value) =>
                                        handleSetting("cutOffHigh", value[0])
                                    }
                                />
                            </div>
                        </>
                    )}

                    <div className="p-4">
                        <Select
                            value={
                                settings.NotchFilter
                                    ? settings.NotchFilterFrequency.toString()
                                    : "false"
                            }
                            onValueChange={handleValueChange}
                        >
                            <SelectTrigger>
                                <SelectValue>
                                    {settings.NotchFilter
                                        ? `NotchFilterFrequency: ${settings.NotchFilterFrequency} Hz`
                                        : "NotchFilter: Off"}
                                </SelectValue>
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="false">Off</SelectItem>
                                <SelectItem value="50">50 Hz</SelectItem>
                                <SelectItem value="60">60 Hz</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="p-4 pb-0">
                        <label className="mr-2">
                            Duration:
                            <input
                                type="number"
                                value={settings.Duration}
                                min={1}
                                max={1024}
                                onChange={(e) =>
                                    handleSetting("Duration", parseInt(e.target.value, 10))
                                }
                                className="ml-2 p-1 border rounded mr-2"
                            />
                            points
                        </label>
                        <Button
                            className="p-2"
                            variant="outline"
                            onClick={() => handleSetting("Duration", 256)}
                        >
                            <IoReload />
                        </Button>
                        <Slider
                            defaultValue={[settings.Duration]}
                            min={1}
                            max={1024}
                            step={1}
                            onValueChange={(value) => handleSetting("Duration", value[0])}
                        />
                    </div>
                    <div className="p-4">
                        <label className="mr-2">
                            Interval:
                            <input
                                type="number"
                                value={settings.Interval}
                                min={1}
                                max={1024}
                                onChange={(e) =>
                                    handleSetting("Interval", Number.parseInt(e.target.value))
                                }
                                className="ml-2 p-1 border rounded mr-2"
                            />
                            points
                        </label>
                        <Button
                            className="p-2"
                            variant="outline"
                            onClick={() => handleSetting("Interval", 25)}
                        >
                            <IoReload />
                        </Button>
                        <Slider
                            defaultValue={[settings.Interval]}
                            min={1}
                            max={1024}
                            step={1}
                            onValueChange={(value) => handleSetting("Interval", value[0])}
                        />
                    </div>


                </SheetContent>
            </Sheet>
            {isConnected && (
                <>
                    <BatteryIcon className={`mr-2 ${iconColor}`} size={24} />
                    <span className={`${iconColor}`}> {batteryLevel}%</span>
                    <StddevMonitor data={JsonData.data} />
                </>
            )}

            {/* 実処理本体 */}
            <EEGPipeline />
        </div>
    );
}
