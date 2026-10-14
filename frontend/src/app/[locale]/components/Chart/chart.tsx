"use client";
import React, { useState, useRef } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FaEye, FaEyeSlash } from "react-icons/fa";
import { RiResetLeftFill } from "react-icons/ri";
import { IoMdMove } from "react-icons/io";

// グラフコンポーネント
import RealtimeEEG from "./eeg";
import FFT from "./fft";
import BandPower from "./bp";
import MusicComponent from "../Music";
import RealtimeEmotion from "../Music/RealtimeEmotion";
import RealtimeMusic from "../Music/RealtimeMusic";

interface ChartData {
  id: string;
  title: string;
  visible: boolean;
  position: { x: number; y: number };
  size: { width: number; height: number };
}

// コンポーネントマッピング
const ChartComponentMap: Record<string, React.ReactElement> = {
  eeg: <RealtimeEEG />,
  fft: <FFT />,
  bp: <BandPower />,
  music: <MusicComponent />,
  emotion_realtime: <RealtimeEmotion />,
  music_realtime: <RealtimeMusic />,
};

export default function Chart() {
  const initialCharts: ChartData[] = [
    {
      id: "eeg",
      title: "EEG",
      visible: true,
      position: { x: 0, y: 0 },
      size: { width: 800, height: 600 },
    },
    {
      id: "fft",
      title: "FFT",
      visible: false,
      position: { x: 100, y: 100 },
      size: { width: 800, height: 600 },
    },
    {
      id: "bp",
      title: "Band Power",
      visible: false,
      position: { x: 120, y: 120 },
      size: { width: 800, height: 600 },
    },
    {
      id: "music",
      title: "Music",
      visible: false,
      position: { x: 150, y: 150 },
      size: { width: 900, height: 750 },
    },
    {
      id: "emotion_realtime",
      title: "Emotion (Realtime)",
      visible: false,
      position: { x: 200, y: 200 },
      size: { width: 450, height: 500 },
    },
    {
      id: "music_realtime",
      title: "Music (Realtime)",
      visible: false,
      position: { x: 250, y: 250 },
      size: { width: 450, height: 350 },
    },
  ];
  const [charts, setCharts] = useState<ChartData[]>(initialCharts);


  const [dragState, setDragState] = useState<{
    isDragging: boolean;
    chartId: string | null;
    startPos: { x: number; y: number };
    startChartPos: { x: number; y: number };
  }>({
    isDragging: false,
    chartId: null,
    startPos: { x: 0, y: 0 },
    startChartPos: { x: 0, y: 0 },
  });

  const [resizeState, setResizeState] = useState<{
    isResizing: boolean;
    chartId: string | null;
    startPos: { x: number; y: number };
    startSize: { width: number; height: number };
  }>({
    isResizing: false,
    chartId: null,
    startPos: { x: 0, y: 0 },
    startSize: { width: 0, height: 0 },
  });

  const containerRef = useRef<HTMLDivElement>(null);

  const toggleVisibility = (chartId: string) => {
    setCharts((prev) =>
      prev.map((chart) => {
        if (chart.id === chartId) {
          if (!chart.visible) {
            // 表示する場合 → 中央に大きく表示
            return {
              ...chart,
              visible: true,
              position: { x: 0, y: 0 },
              size: { width: 800, height: 600 },
            };
          } else {
            return { ...chart, visible: false };
          }
        }
        return chart;
      })
    );
  };


  const handleMouseDown = (
    e: React.MouseEvent,
    chartId: string,
    action: "drag" | "resize"
  ) => {
    e.preventDefault();
    const chart = charts.find((c) => c.id === chartId);
    if (!chart) return;

    if (action === "drag") {
      setDragState({
        isDragging: true,
        chartId,
        startPos: { x: e.clientX, y: e.clientY },
        startChartPos: chart.position,
      });
    } else {
      setResizeState({
        isResizing: true,
        chartId,
        startPos: { x: e.clientX, y: e.clientY },
        startSize: chart.size,
      });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (dragState.isDragging && dragState.chartId) {
      const deltaX = e.clientX - dragState.startPos.x;
      const deltaY = e.clientY - dragState.startPos.y;

      setCharts((prev) =>
        prev.map((chart) =>
          chart.id === dragState.chartId
            ? {
              ...chart,
              position: {
                x: Math.max(0, dragState.startChartPos.x + deltaX),
                y: Math.max(0, dragState.startChartPos.y + deltaY),
              },
            }
            : chart
        )
      );
    }

    if (resizeState.isResizing && resizeState.chartId) {
      const deltaX = e.clientX - resizeState.startPos.x;
      const deltaY = e.clientY - resizeState.startPos.y;

      setCharts((prev) =>
        prev.map((chart) =>
          chart.id === resizeState.chartId
            ? {
              ...chart,
              size: {
                width: Math.max(200, resizeState.startSize.width + deltaX),
                height: Math.max(150, resizeState.startSize.height + deltaY),
              },
            }
            : chart
        )
      );
    }
  };

  const handleMouseUp = () => {
    setDragState({
      isDragging: false,
      chartId: null,
      startPos: { x: 0, y: 0 },
      startChartPos: { x: 0, y: 0 },
    });
    setResizeState({
      isResizing: false,
      chartId: null,
      startPos: { x: 0, y: 0 },
      startSize: { width: 0, height: 0 },
    });
  };

  const resetLayout = () => {
    setCharts(initialCharts);
  };


  return (
    <>
      <div className="flex gap-2">
        {charts.map((chart) => (
          <Button
            key={chart.id}
            variant={chart.visible ? "default" : "outline"}
            size="sm"
            onClick={() => toggleVisibility(chart.id)}
            className="flex items-center gap-2"
          >
            {chart.visible ? <FaEye className="w-4 h-4" /> : <FaEyeSlash className="w-4 h-4" />}
            {chart.title}
          </Button>
        ))}
        <Button
          variant="outline"
          size="sm"
          onClick={resetLayout}
          className="flex items-center gap-2"
        >
          <RiResetLeftFill className="w-4 h-4" />
          Reset Layout
        </Button>
      </div>

      <div
        ref={containerRef}
        className="relative w-full h-[800px] bg-white rounded-lg border overflow-auto"
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {charts
          .filter((chart) => chart.visible)
          .map((chart) => (
            <Card
              key={chart.id}
              className="absolute border-2 shadow-lg hover:shadow-xl transition-shadow cursor-move flex flex-col overflow-hidden"
              style={{
                left: chart.position.x,
                top: chart.position.y,
                width: chart.size.width,
                height: chart.size.height,
                zIndex: dragState.chartId === chart.id ? 10 : 1,
              }}
            >
              <CardHeader
                className="pb-2 cursor-move flex flex-row items-center justify-between flex-shrink-0"
                onMouseDown={(e) => handleMouseDown(e, chart.id, "drag")}
              >
                <CardTitle className="text-lg flex items-center gap-2">
                  <IoMdMove className="w-4 h-4 text-gray-400" />
                  {chart.title}
                </CardTitle>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleVisibility(chart.id);
                    }}
                    className="p-1 h-6 w-6"
                  >
                    <FaEyeSlash className="w-3 h-3" />
                  </Button>
                </div>
              </CardHeader>

              <CardContent className="p-4 flex-1 overflow-hidden min-h-0">
                <div className="h-full relative">
                  <div className="h-full w-full overflow-auto">
                    {ChartComponentMap[chart.id] || <div>Unknown chart</div>}
                  </div>
                </div>
                <div
                  className="absolute bottom-0 right-0 w-4 h-4 bg-blue-500 cursor-se-resize hover:bg-gray-400 transition-colors"
                  onMouseDown={(e) => handleMouseDown(e, chart.id, "resize")}
                  style={{
                    clipPath: "polygon(100% 0%, 0% 100%, 100% 100%)",
                  }}
                />
              </CardContent>
            </Card>
          ))}
      </div>
    </>
  );
}
