// =============================
// File: src/components/EEG/EEGatoms.ts
//  PipelineのReload用の世代カウンタと、UI用の軽いフラグ
// =============================
import { atom } from "jotai";


export const pipelineGenerationAtom = atom(0);
export const settingsDirtyAtom = atom(false); // 設定変更後にReloadを促す表示用
export const deviceAtom = atom<"muse" | "mock">("muse");
export const streamingAtom = atom(false);
export const connectedAtom = atom(false);
export const sheetOpenAtom = atom(false);
export const errorMessageAtom = atom<any>(null);
export const batteryLevelAtom = atom(100); // テレメトリ情報