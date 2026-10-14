import { atom } from "jotai";
import { channelNames } from "muse-js";
import { eegSettings, JsonData, StreamData, EEGsv2 } from "@/types/types";

export const eegSettingsAtom = atom<eegSettings>({
  DeviceName: "",
  FFT: false,
  NotchFilter: true,
  NotchFilterFrequency: 60,
  LowpassFilter: true,
  HighpassFilter: true,
  cutOffLow: 0.3,
  cutOffHigh: 50,
  Duration: 256,
  Interval: 25,
  SamplingRate: 256,
  nbChannels: 4,
  channelNames: channelNames,
});

export const jsonDataAtom = atom<JsonData>({
  data: [],
  psd: [],
  bandPowers: {
    delta: [],
    theta: [],
    alpha: [],
    beta: [],
    gamma: [],
  },
  info: { samplingRate: 0, startTime: 0 },
});

export const rawDataAtom = atom<StreamData[]>([]);
// Timestamp of the last raw frame received (ms since epoch)
export const lastDataTimestampAtom = atom<number>(Date.now());
// Live valence/arousal pair (probabilities 0..1 or null)
export const liveVAAtom = atom<{ v: number | null; a: number | null } | null>({ v: null, a: null });
// export const dbRawAtom = atom<EEGsv2>();
// export const dbFilteredAtom = atom<EEGsv2>();