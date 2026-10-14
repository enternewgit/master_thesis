import React from "react";
import { StddevDots } from "./StddevDots";
import { Button } from "@/components/ui/button";
import { FaEye, FaEyeSlash } from "react-icons/fa";
import { useTranslations } from "next-intl";

interface StddevMonitorProps {
    data: any[][];
}

export function StddevMonitor({ data }: StddevMonitorProps) {

    const [showMonitor, setShowMonitor] = React.useState(true);
    const t = useTranslations("muse");

    if (!data || data.length === 0) {
        return (
            <div className="fixed bottom-4 right-4 bg-gray-900 text-white text-xs p-2 rounded shadow-lg w-56 h-40 overflow-auto whitespace-pre-wrap font-mono z-50">
                No data available
            </div>
        );
    }

    // 標準偏差を計算する関数
    const calculateStdDev = (arr: number[]) => {
        if (arr.length === 0) return 0;
        const mean = arr.reduce((sum, val) => sum + val, 0) / arr.length;
        const variance = arr.reduce((sum, val) => sum + (val - mean) ** 2, 0) / arr.length;
        return Math.sqrt(variance);
    };

    // 有効な数値配列のみ抽出し、標準偏差を算出
    const stddevs: number[] = data.map((arr) =>
        Array.isArray(arr) &&
            arr.length > 0 &&
            arr.every(v => typeof v === "number" && Number.isFinite(v))
            ? calculateStdDev(arr)
            : null
    ).filter((v): v is number => v !== null);

    const toggleMonitor = () => {
        setShowMonitor(prev => !prev);
    };

    return (
        <>
            {/* 数値表示用モニター */}
            <div className="fixed bottom-4 right-4 z-50">
                <Button onClick={toggleMonitor} className="mb-2">
                    {showMonitor ? <FaEye /> : <FaEyeSlash />} {showMonitor ? t("Hide monitor") : t("Display monitor")}
                </Button>

                {/* ドットビジュアライザ（背景に重ねる） */}
                {showMonitor && <StddevDots stddevs={stddevs} />}
                {/* {stddevs.map((std, idx) => (
                    <div key={idx}>
                        Array {idx}: {std.toFixed(4)}
                    </div>
                ))} */}
            </div>

        </>
    );
}
