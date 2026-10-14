"use client";
import { useState, useEffect } from "react";
import { atom, useAtom } from "jotai";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Label,
  ResponsiveContainer,
} from "recharts";
import { Toggle } from "@/components/ui/toggle";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";

import { jsonDataAtom, eegSettingsAtom } from "../museClientAtom";


export default function BandPower() {
  const [zipedData] = useAtom(jsonDataAtom);
  const [settings] = useAtom(eegSettingsAtom);
  
  const [ylim, setYlim] = useState(2000);
  const [xlim, setXlim] = useState(settings.Duration);
  const [xmax, setXmax] = useState(256);
  const [xlabel] = useState("Frequency (Hz)");
  const [ylabel] = useState("Power (µV²)");

 
  // const channelNames = ["TP9", "AF7", "AF8", "TP10", "AUX"];


  type DataPoint = {
    x: number;
    [key: string]: number;
  };
  // 初期値を動的に生成
  const [chartData, setChartData] = useState<DataPoint[]>(() => {
    const initialDataPoint: DataPoint = { x: 0 };
    for (let ch = 0; ch < settings.nbChannels; ch++) {
      initialDataPoint[`ch${ch}`] = 0;
    }
    return [initialDataPoint];
  });
  

  // チャンネル表示の状態管理（配列）
  const [showChannels, setShowChannels] = useState<boolean[]>(
    Array(settings.nbChannels).fill(true)
  );


  // チャートデータの更新
  useEffect(() => {
    // console.log("zipedData:", zipedData);
      if (
        zipedData &&
        zipedData.psd &&
        Array.isArray(zipedData.psd) &&
        zipedData.psd.length > 0
      ) {
        if (Array.isArray(zipedData.psd[0]) && zipedData.psd[0].length > 0) {
          const numDataPoints = zipedData.psd[0].length;
          const newChartData: DataPoint[] = [];
          for (let i = 0; i < numDataPoints; i++) {
            const dataPoint: DataPoint = {
              x: i + 1
            };
            for (let ch = 0; ch < settings.nbChannels; ch++) {
              dataPoint[`ch${ch}`] = zipedData.psd[ch][i];
            }
            newChartData.push(dataPoint);
          }
          setChartData(newChartData);
        }
      }
  }, [
    zipedData,
    settings.SamplingRate,
    settings.Duration,
    settings.nbChannels,
  ]);

  useEffect(() => {
      setXlim(settings.SamplingRate / 2);
      setXmax(settings.SamplingRate / 2);
  }, [settings.Duration, settings.SamplingRate]);

  // チャンネル表示のトグル（配列）
  const handleToggle = (index: number) => {
    setShowChannels((prev) =>
      prev.map((val, i) => (i === index ? !val : val))
    );
  };

  return (
    <div className="items-center">
      <ResponsiveContainer aspect={3}>
        <LineChart
          data={chartData}
          margin={{ top: 5, right: 30, left: 20, bottom: 20 }}
        >
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="x"
            type="number"
            domain={[0, xlim]}
            allowDataOverflow
          >
            <Label value={xlabel} offset={-5} position="insideBottom" />
          </XAxis>
          <YAxis type="number" domain={[-ylim, ylim]} allowDataOverflow>
            <Label
              value={ylabel}
              angle={-90}
              position="insideLeft"
              style={{ textAnchor: "middle" }}
              offset={-5}
              dy={20}
            />
          </YAxis>
          {/* <Tooltip /> */}
          {Array.from({ length: settings.nbChannels }).map(
            (_, ch) =>
              showChannels[ch] && (
                <Line
                  key={ch}
                  type="monotone"
                  name={settings.channelNames[ch] || `Ch${ch}`}
                  dataKey={`ch${ch}`}
                  stroke={`hsl(${(ch * 360) / settings.nbChannels}, 50%, 50%)`}
                  isAnimationActive={false}
                  dot={false}
                  activeDot={false}
                />
              )
          )}
        </LineChart>
      </ResponsiveContainer>

      <div className="mt-4 ml-20">
        <div className="flex space-x-3">
          {Array.from({ length: settings.nbChannels }).map((_, ch) => (
            <Toggle
              key={ch}
              variant="outline"
              onPressedChange={() => handleToggle(ch)}
            >
              <span
                style={{
                  color: `hsl(${(ch * 360) / settings.nbChannels}, 50%, 50%)`,
                }}
              >
                &mdash; {settings.channelNames[ch] || `Ch${ch}`}
              </span>
            </Toggle>
          ))}
        </div>
        <div className="flex items-center mt-4">
          <label className="mr-2">Xlim:</label>
          <Input
            type="number"
            value={xlim}
            min={0}
            max={xmax}
            step={0.01}
            onChange={(e) => setXlim(parseInt(e.target.value, 10))}
            className="ml-2 p-1 border rounded mr-2 w-32"
          />
          <Slider
            defaultValue={[xlim]}
            min={0}
            max={xmax}
            step={0.01}
            onValueChange={(value) => setXlim(value[0])}
            className="ml-4 w-full"
          />
        </div>
        <div className="flex items-center mt-4">
          <label className="mr-2">Ylim:</label>
          <Input
            type="number"
            value={ylim}
            min={0}
            max={10000}
            step={10}
            onChange={(e) => setYlim(parseInt(e.target.value, 10))}
            className="ml-2 p-1 border rounded mr-2 w-32"
          />
          <Slider
            defaultValue={[ylim]}
            min={0}
            max={10000}
            step={10}
            onValueChange={(value) => setYlim(value[0])}
            className="ml-4 w-full"
          />
        </div>
      </div>
      {/* <Recoder/> */}
    </div>
  );
}
