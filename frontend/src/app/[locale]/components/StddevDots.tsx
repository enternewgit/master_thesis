import React, { useState } from "react";
import { Switch } from "@/components/ui/switch";

type Props = {
  stddevs: number[];
};

const basePositions: { x: number; y: number; label: string, ch: number }[] = [
  { x: 240 / 300, y: 105 / 300, label: "TP9" ,ch: 0 },  // 左耳
  { x: 195 / 300, y: 165 / 300, label: "AF7" ,ch: 1 },  // 左前頭
  { x: 100 / 300, y: 165 / 300, label: "AF8" ,ch: 2 },  // 右前頭
  { x: 60 / 300, y: 105 / 300, label: "TP10" ,ch: 3 },   // 右耳
];

const getColorValue = (std: number) => {
  if (std < 20) return "rgba(34,197,94,0.8)";
  if (std < 100) return "rgba(250,204,21,0.8)";
  return "rgba(239,68,68,0.8)";
};

const getSize = (std: number) => {
  const min = 8;
  const max = 32;
  return Math.min(max, Math.max(min, Math.log(std) * 5));
};

export function StddevDots({ stddevs }: Props) {
  const [mirrored, setMirrored] = useState(false);


  return (
    <div className="relative w-[250px] h-auto">
      <img
        src={`${process.env.NEXT_PUBLIC_TOP_URL}/MuseS_head_tr.png`}
        alt="EEG headband"
        className={`w-full h-auto transition-transform duration-300 ${mirrored ? "scale-x-[-1] blur-[0.5px]" : ""}`}
      />
      {/* グラデーション光筋オーバーレイ */}
      {mirrored && (
        <div className="absolute inset-0 pointer-events-none z-10">
          <div className="absolute inset-0 bg-[repeating-linear-gradient(135deg,_rgba(200,200,200,0.15)_0px,_transparent_20px,_rgba(200,200,200,0.15)_40px,_transparent_60px)] mix-blend-screen" />
        </div>
      )}


      {/* ドット表示 */}
      {stddevs.map((std, idx) => {
        const base = basePositions[idx];
        const pos = {
          x: mirrored ? 1 - base.x : base.x,
          y: base.y, // Y軸反転
        };
        const size = getSize(std);
        const label = base.label;
        const color = `hsl(${(base.ch * 360) / 4}, 50%, 50%)`;

        return (
          <React.Fragment key={idx}>
            {/* ドット */}
            <div
              className="absolute rounded-full"
              style={{
                left: `${pos.x * 100}%`,
                top: `${pos.y * 100}%`,
                width: size,
                height: size,
                transform: "translate(-50%, -50%)",
                transition: "all 0.3s ease",
                backgroundColor: getColorValue(std),
                boxShadow: `0 0 5px 3px ${getColorValue(std)}`,
              }}
              title={`Stddev: ${std.toFixed(2)}`}
            />

            {/* ラベル */}
            <div
              className="absolute text-sm font-mono drop-shadow-md"
              style={{
                left: `${pos.x * 100}%`,
                top: `${(pos.y * 100) - 12}%`, 
                transform: "translate(-50%, 0)",
                color: color,
                backgroundColor: "rgba(255, 255, 255,0.4)",
                pointerEvents: "none",
              }}
            >
              {label}
            </div>
          </React.Fragment>
        );
      })}

      {/* ミラー切り替えボタン */}
      <div className="absolute top-2 left-2 flex items-center space-x-2 bg-white/80 backdrop-blur-sm px-2 py-1 rounded shadow text-xs">
        <span className="text-black">Mirror</span>
        <Switch checked={mirrored} onCheckedChange={setMirrored} />
      </div>
    </div >

  );
}
