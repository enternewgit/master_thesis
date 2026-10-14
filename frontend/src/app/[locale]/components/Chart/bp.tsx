"use client";
import { useState, useEffect } from "react";
import { useAtom } from "jotai";

import {
  BarChart,
  Bar,
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

  const [ylim, setYlim] = useState(300);
  const [xlabel] = useState("Frequency Band");
  const [ylabel] = useState("Power (µV²)");

  const [showChannels, setShowChannels] = useState<boolean[]>(
    Array(settings.nbChannels).fill(true)
  );

  type DataPoint = {
    x: string; // Delta, Theta, ...
    [key: string]: number | string;
  };

  const [chartData, setChartData] = useState<DataPoint[]>([]);

  useEffect(() => {
  if (
    zipedData &&
    zipedData.bandPowers &&
    typeof zipedData.bandPowers === "object"
  ) {
    const freqBands = ["delta", "theta", "alpha", "beta", "gamma"];
    const newChartData: DataPoint[] = [];

    for (const band of freqBands) {
      const bandLabel = band.charAt(0).toUpperCase() + band.slice(1); // e.g. "Alpha"
      const bandData: DataPoint = { x: bandLabel };

      for (let ch = 0; ch < settings.nbChannels; ch++) {
        const power = zipedData.bandPowers[band as keyof typeof zipedData.bandPowers]?.[ch];
        bandData[`ch${ch}`] = power ?? 0;
      }

      newChartData.push(bandData);
    }

    setChartData(newChartData);
  }
}, [zipedData, settings.nbChannels]);


  const handleToggle = (index: number) => {
    setShowChannels((prev) =>
      prev.map((val, i) => (i === index ? !val : val))
    );
  };

  return (
    <div className="items-center">
      <ResponsiveContainer aspect={2.5}>
        <BarChart
          data={chartData}
          margin={{ top: 10, right: 30, left: 20, bottom: 30 }}
        >
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="x">
            <Label value={xlabel} offset={-20} position="insideBottom" />
          </XAxis>
          <YAxis domain={[0, ylim]}>
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
                <Bar
                  key={ch}
                  name={settings.channelNames?.[ch] || `Ch${ch}`}
                  dataKey={`ch${ch}`}
                  fill={`hsl(${(ch * 360) / settings.nbChannels}, 50%, 50%)`}
                  isAnimationActive={false}
                />
              )
          )}
        </BarChart>
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
                &mdash; {settings.channelNames?.[ch] || `Ch${ch}`}
              </span>
            </Toggle>
          ))}
        </div>

        <div className="flex items-center mt-4">
          <label className="mr-2">Ylim:</label>
          <Input
            type="number"
            value={ylim}
            min={0}
            max={1000}
            step={10}
            onChange={(e) => setYlim(parseInt(e.target.value, 10))}
            className="ml-2 p-1 border rounded mr-2 w-32"
          />
          <Slider
            defaultValue={[ylim]}
            min={0}
            max={1000}
            step={10}
            onValueChange={(value) => setYlim(value[0])}
            className="ml-4 w-full"
          />
        </div>
      </div>
    </div>
  );
}
