# word-haku EEG→Music専用アプリ化 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `word-haku` を、ログイン・学習データ管理ダッシュボードを廃止し、「EEG測定 → Chart表示 → 脳波に合わせた音楽生成」だけが動く独立アプリに作り変える。

**Architecture:** braingram版の `EEG/` フォルダ（Pipeline/Source抽象化されたEEG接続層）を word-haku に移植し、既存の `Chart/chart.tsx` のフローティングカード機構に Music カードを追加する。ログイン・`/my` ダッシュボード・Text実験・認証基盤は、EEG→Music機能から一切参照されなくなるため丸ごと削除する。

**Tech Stack:** Next.js (App Router) / React / TypeScript / jotai / rxjs / `@neurosity/pipes` / `muse-js` / recharts。パッケージ追加は不要（braingram側で使われている依存は全て word-haku の package.json に既存）。

**Spec:** `docs/superpowers/specs/2026-08-25-word-haku-eeg-music-lab-design.md`

## Global Constraints

- **word-haku/ と word_haku_api/ では git操作（add/commit/push/revert等）を一切行わない。** 各タスク末尾は「動作確認」ステップとし、コミットはユーザーが自分の作業ブランチ上で行う。
- 自動テストフレームワークはこのリポジトリに存在しない。各タスクの検証は `npx tsc --noEmit`（型チェック）と、削除タスクでは「参照が残っていないことをgrepで確認」を基本とし、最終タスクでのみ `npm run build` と手動スモークテストを行う。
- `src/components/ui/*`（shadcn/ui のプリミティブ）、`src/types/types.ts`、`package.json` の依存関係には手を入れない（未使用でも実害がないため対象外）。
- 既存の未コミット変更（`next.config.mjs`, `package.json`, `main-nav.tsx` のfaviconパス変更等）はこの作業と無関係なので触らない。
- コマンドはすべて `cd /home/httpd/Neurobeet/word-haku` した状態で実行する前提。

---

## Task 1: EEG接続層を braingram から移植する

**Files:**
- Create: `src/app/[locale]/components/EEG/EEGatoms.ts`
- Create: `src/app/[locale]/components/EEG/EEGpipeline.tsx`
- Create: `src/app/[locale]/components/EEG/EEGRunner.tsx`
- Create: `src/app/[locale]/components/EEG/sources/EEGSource.ts`
- Create: `src/app/[locale]/components/EEG/sources/museSource.ts`
- Create: `src/app/[locale]/components/EEG/sources/mockSource.ts`

**Interfaces:**
- Consumes: `rawDataAtom`, `filteredDataAtom`, `jsonDataAtom`, `eegSettingsAtom`, `lastDataTimestampAtom`（`../museClientAtom` に既存）, `StddevMonitor`（`../StddevMonitor` に既存、変更不要）
- Produces: `EEGRunner`（`./EEG/EEGRunner` の default export）— Task 2 で `page.tsx` から使用する

- [ ] **Step 1: EEGatoms.ts / EEGRunner.tsx / sources/* をそのままコピーする**

```bash
cd /home/httpd/Neurobeet/word-haku
mkdir -p "src/app/[locale]/components/EEG/sources"
cp "/home/httpd/braingram/word-haku/src/app/[locale]/components/EEG/EEGatoms.ts" \
   "src/app/[locale]/components/EEG/EEGatoms.ts"
cp "/home/httpd/braingram/word-haku/src/app/[locale]/components/EEG/EEGRunner.tsx" \
   "src/app/[locale]/components/EEG/EEGRunner.tsx"
cp "/home/httpd/braingram/word-haku/src/app/[locale]/components/EEG/sources/EEGSource.ts" \
   "src/app/[locale]/components/EEG/sources/EEGSource.ts"
cp "/home/httpd/braingram/word-haku/src/app/[locale]/components/EEG/sources/museSource.ts" \
   "src/app/[locale]/components/EEG/sources/museSource.ts"
cp "/home/httpd/braingram/word-haku/src/app/[locale]/components/EEG/sources/mockSource.ts" \
   "src/app/[locale]/components/EEG/sources/mockSource.ts"
```

- [ ] **Step 2: EEGpipeline.tsx をコピーし、`lastDataTimestampAtom` の更新を追加する**

```bash
cp "/home/httpd/braingram/word-haku/src/app/[locale]/components/EEG/EEGpipeline.tsx" \
   "src/app/[locale]/components/EEG/EEGpipeline.tsx"
```

コピーした `src/app/[locale]/components/EEG/EEGpipeline.tsx` の import 行を以下のように変更する（`lastDataTimestampAtom` を追加）。

変更前:
```tsx
import { eegSettingsAtom, rawDataAtom, filteredDataAtom, jsonDataAtom } from "../museClientAtom";
```

変更後:
```tsx
import { eegSettingsAtom, rawDataAtom, filteredDataAtom, jsonDataAtom, lastDataTimestampAtom } from "../museClientAtom";
```

同ファイル内の atom 宣言部分を以下のように変更する。

変更前:
```tsx
    const [settings] = useAtom(eegSettingsAtom);
    const [, setRawData] = useAtom(rawDataAtom);
    const [, setFilteredData] = useAtom(filteredDataAtom);
    const [, setJsonData] = useAtom(jsonDataAtom);
```

変更後:
```tsx
    const [settings] = useAtom(eegSettingsAtom);
    const [, setRawData] = useAtom(rawDataAtom);
    const [, setFilteredData] = useAtom(filteredDataAtom);
    const [, setJsonData] = useAtom(jsonDataAtom);
    const [, setLastDataTimestamp] = useAtom(lastDataTimestampAtom);
```

生データ受信時の tap 処理を以下のように変更する（`ExperimentPlayer.tsx` がデータ途絶検知に使う `lastDataTimestampAtom` をここで更新する）。

変更前:
```tsx
            let pipeline = src.readings$.pipe(
                tap((data: any) => {
                    lastDataTimestampRef.current = Date.now();
                    setRawData((prevData) => {
```

変更後:
```tsx
            let pipeline = src.readings$.pipe(
                tap((data: any) => {
                    lastDataTimestampRef.current = Date.now();
                    setLastDataTimestamp(Date.now());
                    setRawData((prevData) => {
```

- [ ] **Step 3: 型チェックで新規ファイルにエラーが無いことを確認する**

Run: `npx tsc --noEmit`
Expected: `src/app/[locale]/components/EEG/` 配下のファイルに起因するエラーが出ないこと（他の未変更ファイルの既存エラーが仮にあっても、このタスクでは EEG/ 関連のエラーが無いことだけ確認すれば良い）。

- [ ] **Step 4: 変更内容を確認する（git操作は行わない）**

Run: `git status` で `EEG/` 配下が新規追加として表示されることを目視確認するのみ。add/commit は行わない。

---

## Task 2: page.tsx を最小構成に書き換える

**Files:**
- Modify: `src/app/[locale]/page.tsx`（全面書き換え）

**Interfaces:**
- Consumes: `EEGRunner`（Task 1, `./components/EEG/EEGRunner` の default export）, `Chart`（`./components/Chart/chart` の default export、Task 3 で拡張されるが現時点でも動作する）
- Produces: なし（末端のページコンポーネント）

- [ ] **Step 1: page.tsx を以下の内容に置き換える**

```tsx
"use client";
import dynamic from "next/dynamic";
import EEGRunner from "./components/EEG/EEGRunner";

const Chart = dynamic(() => import("./components/Chart/chart"), { ssr: false });

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="flex h-14 items-center px-4 bg-indigo-800 text-white">
        <span className="text-lg font-bold">EEG → Music Lab</span>
        <div className="ml-auto">
          <EEGRunner />
        </div>
      </header>
      <main className="p-4">
        <Chart />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: 型チェックを実行する**

Run: `npx tsc --noEmit`
Expected: `page.tsx` に起因するエラーが出ないこと。

- [ ] **Step 3: 開発サーバーで表示を確認する**

Run: `npm run dev`
ブラウザで `http://localhost:3001/en` を開き、ヘッダーに「EEG → Music Lab」とEEG接続ボタン（Mock/Museデバイス選択）が表示され、その下にChartのフローティングカード操作バー（EEG/FFT/Band Power/Reset Layout ボタン）が表示されることを確認する。開発サーバーは確認後 Ctrl+C で停止する。

- [ ] **Step 4: 変更内容を確認する（git操作は行わない）**

Run: `git status` で `page.tsx` が modified になっていることを目視確認するのみ。add/commit は行わない。

---

## Task 3: Music カードを Chart のフローティングカード機構に統合する

**Files:**
- Modify: `src/app/[locale]/components/Chart/chart.tsx`
- Modify: `src/app/[locale]/components/Chart/eeg.tsx`（未使用importの削除）
- Modify: `src/app/[locale]/components/Music/index.tsx`（重複見出しの削除）

**Interfaces:**
- Consumes: `MusicComponent`（`../Music` の default export、既存・変更なし）
- Produces: `chart.tsx` の `ChartComponentMap` に `music` キーが追加される（Task 10 の手動確認で使用）

- [ ] **Step 1: chart.tsx に Music コンポーネントの import を追加する**

変更前:
```tsx
// グラフコンポーネント
import RealtimeEEG from "./eeg";
import FFT from "./fft";
import BandPower from "./bp";
```

変更後:
```tsx
// グラフコンポーネント
import RealtimeEEG from "./eeg";
import FFT from "./fft";
import BandPower from "./bp";
import MusicComponent from "../Music";
```

- [ ] **Step 2: ChartComponentMap に music を追加する**

変更前:
```tsx
// コンポーネントマッピング
const ChartComponentMap: Record<string, React.ReactElement> = {
  eeg: <RealtimeEEG />,
  fft: <FFT />,
  bp: <BandPower />,
};
```

変更後:
```tsx
// コンポーネントマッピング
const ChartComponentMap: Record<string, React.ReactElement> = {
  eeg: <RealtimeEEG />,
  fft: <FFT />,
  bp: <BandPower />,
  music: <MusicComponent />,
};
```

- [ ] **Step 3: initialCharts に music カードを追加する**

変更前:
```tsx
    {
      id: "bp",
      title: "Band Power",
      visible: false,
      position: { x: 120, y: 120 },
      size: { width: 800, height: 600 },
    },
  ];
```

変更後:
```tsx
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
  ];
```

- [ ] **Step 4: カード内コンテンツの overflow を auto に変更する**

Music カードは操作パネル・SVGプロット・オーディオ要素・自動ループパネルを含み縦に長くなるため、`overflow-hidden` のままだと内容が見切れる。EEG/FFT/BandPower はグラフが親要素サイズに追従するため `overflow-auto` に変えても表示は変わらない。

変更前:
```tsx
              <CardContent className="p-4 h-full">
                <div className="h-full relative">
                  <div className="h-full w-full overflow-hidden">
                    {ChartComponentMap[chart.id] || <div>Unknown chart</div>}
                  </div>
                </div>
```

変更後:
```tsx
              <CardContent className="p-4 h-full">
                <div className="h-full relative">
                  <div className="h-full w-full overflow-auto">
                    {ChartComponentMap[chart.id] || <div>Unknown chart</div>}
                  </div>
                </div>
```

- [ ] **Step 5: eeg.tsx の未使用 import を削除する**

`Recoder` は既にコメントアウトされて使われておらず、Task 6 で `recorder.tsx` 自体を削除するため、先にこの import を消しておく。

変更前:
```tsx
import { jsonDataAtom, eegSettingsAtom } from "../museClientAtom";
import  Recoder  from "./recorder";
import { zip } from "rxjs";
```

変更後:
```tsx
import { jsonDataAtom, eegSettingsAtom } from "../museClientAtom";
```

ファイル末尾付近にある以下のコメントアウト行も削除する。

変更前:
```tsx
      {/* <Recoder/> */}
    </div>
  );
}
```

変更後:
```tsx
    </div>
  );
}
```

- [ ] **Step 6: Music/index.tsx の重複見出しを削除する**

`Card` の `CardTitle` で既に "Music" と表示されるため、内部の `<h2>` 見出しは重複になる。

変更前:
```tsx
export default function MusicComponent() {
  return (
    <div>
      <h2>Music / EEG AI</h2>
      <p>音楽生成のプリセットを選んで、脳波に合わせた生成や分析を行えます。</p>
      <div style={{ border: "1px solid #eee", padding: 12, borderRadius: 6 }}>
        <Player />
      </div>
    </div>
  );
}
```

変更後:
```tsx
export default function MusicComponent() {
  return (
    <div>
      <p>音楽生成のプリセットを選んで、脳波に合わせた生成や分析を行えます。</p>
      <div style={{ border: "1px solid #eee", padding: 12, borderRadius: 6 }}>
        <Player />
      </div>
    </div>
  );
}
```

- [ ] **Step 7: 型チェックを実行する**

Run: `npx tsc --noEmit`
Expected: `Chart/chart.tsx`, `Chart/eeg.tsx`, `Music/index.tsx` に起因するエラーが出ないこと。

- [ ] **Step 8: 変更内容を確認する（git操作は行わない）**

Run: `git status` で該当3ファイルが modified になっていることを目視確認するのみ。add/commit は行わない。

---

## Task 4: `/my` ダッシュボード配下を削除する

**Files:**
- Delete: `src/app/[locale]/my/`（配下18ファイル全て）

**Interfaces:**
- Consumes: なし
- Produces: なし（このタスクは削除のみ）

- [ ] **Step 1: `/my` フォルダを削除する**

```bash
cd /home/httpd/Neurobeet/word-haku
rm -rf "src/app/[locale]/my"
```

- [ ] **Step 2: 他の場所から `/my` 配下への import が残っていないことを確認する**

Run:
```bash
grep -rn "\[locale\]/my/\|from \"\.\./my\|from \"\./my" src --include="*.ts" --include="*.tsx"
```
Expected: 何も出力されないこと（出力があれば、その参照元ファイルを確認し対応する）。

- [ ] **Step 3: 変更内容を確認する（git操作は行わない）**

Run: `git status` で `src/app/[locale]/my/` が deleted として表示されることを目視確認するのみ。add/commit は行わない。

---

## Task 5: ログイン・認証基盤を削除する

**Files:**
- Delete: `src/app/[locale]/login/`（`page.tsx`, `auth.tsx`, `signup.tsx`, `google.tsx`）
- Delete: `src/app/[locale]/api/`（NextAuthのAPIルート `api/auth/[...nextauth]/route.ts` のみを含むフォルダ）
- Delete: `src/lib/auth.ts`
- Delete: `src/lib/middleware.ts`（`src/middleware.ts` とは別物。`export { auth as middleware } from "./auth"` のみの未使用ファイル）
- Delete: `src/lib/serverActions_Google.ts`

**Interfaces:**
- Consumes: なし
- Produces: なし（このタスクは削除のみ）

- [ ] **Step 1: ログイン・NextAuth関連ファイルを削除する**

```bash
cd /home/httpd/Neurobeet/word-haku
rm -rf "src/app/[locale]/login"
rm -rf "src/app/[locale]/api"
rm -f src/lib/auth.ts
rm -f src/lib/middleware.ts
rm -f src/lib/serverActions_Google.ts
```

- [ ] **Step 2: 残存参照が無いことを確認する**

Run:
```bash
grep -rn "lib/auth\"\|lib/middleware\"\|serverActions_Google\|\[locale\]/login" src --include="*.ts" --include="*.tsx"
```
Expected: 何も出力されないこと。

- [ ] **Step 3: 変更内容を確認する（git操作は行わない）**

Run: `git status` で該当ファイル・フォルダが deleted になっていることを目視確認するのみ。add/commit は行わない。

---

## Task 6: Text機能・旧EEG接続・main-nav・付随ライブラリを削除する

**Files:**
- Delete: `src/app/[locale]/components/Text/`（フォルダ全体）
- Delete: `src/app/[locale]/components/main-nav.tsx`
- Delete: `src/app/[locale]/components/params.tsx`
- Delete: `src/app/[locale]/components/muse.tsx`
- Delete: `src/app/[locale]/components/Chart/recorder.tsx`
- Delete: `src/app/[locale]/components/Chart/chartEEGs.tsx`
- Delete: `src/app/[locale]/components/Chart/bp_timeaxis.tsx`
- Delete: `src/lib/filterEEGs.ts`

これらは Task 4・5 で `/my` と `/login` を削除した時点で参照元が無くなる（`Text/` は `/my` と旧 `page.tsx` からのみ、`main-nav.tsx` は `/my` `/login` と旧 `page.tsx` からのみ、`params.tsx` は `/my` `Text/` とそれらのhooksからのみ、`recorder.tsx`/`chartEEGs.tsx`/`bp_timeaxis.tsx` は `/my/Analytics` と `Text/` からのみ、`filterEEGs.ts` は `/my/Analytics` と `Text/` からのみ参照されていたため）。

**Interfaces:**
- Consumes: なし
- Produces: なし（このタスクは削除のみ）

- [ ] **Step 1: 該当ファイル・フォルダを削除する**

```bash
cd /home/httpd/Neurobeet/word-haku
rm -rf "src/app/[locale]/components/Text"
rm -f "src/app/[locale]/components/main-nav.tsx"
rm -f "src/app/[locale]/components/params.tsx"
rm -f "src/app/[locale]/components/muse.tsx"
rm -f "src/app/[locale]/components/Chart/recorder.tsx"
rm -f "src/app/[locale]/components/Chart/chartEEGs.tsx"
rm -f "src/app/[locale]/components/Chart/bp_timeaxis.tsx"
rm -f src/lib/filterEEGs.ts
```

- [ ] **Step 2: 残存参照が無いことを確認する**

Run:
```bash
grep -rn "components/Text\|main-nav\|components/params\|components/muse\"\|from \"\./muse\"\|Chart/recorder\|from \"\./recorder\"\|chartEEGs\|bp_timeaxis\|filterEEGs" src --include="*.ts" --include="*.tsx"
```
Expected: 何も出力されないこと。

- [ ] **Step 3: 変更内容を確認する（git操作は行わない）**

Run: `git status` で該当ファイル・フォルダが deleted になっていることを目視確認するのみ。add/commit は行わない。

---

## Task 7: 認証・ダッシュボード専用の hooks を削除する

**Files:**
- Delete: `src/hooks/` 配下の `use-toast.ts` を除く全ファイル（21ファイル中20ファイル）
  - `useDataProcessFromEEGsv2.ts`, `useMutateAddTags.ts`, `useMutateAuth.ts`, `useMutateDeleteInfModels.ts`, `useMutateDeleteTags.ts`, `useMutateEEGsv2.ts`, `useMutateFolderMove.ts`, `useMutateFolders.ts`, `useProcessAddTags.ts`, `useProcessAuth.ts`, `useProcessDeleteInfModels.ts`, `useProcessDeleteTags.ts`, `useProcessEEGsv2.ts`, `useProcessFolderMove.ts`, `useProcessFolders.ts`, `useProcessRegister.ts`, `useQueryEEGsv2.ts`, `useQueryFolders.ts`, `useQueryInfModels.ts`, `useQueryTrainIds.ts`, `useQueryUser.ts`

`use-toast.ts` のみ `src/components/ui/toaster.tsx`（`layout.tsx` から使用、維持対象）から参照されているため残す。他の20ファイルは全て `/my`, `/login`, `Text/`, `Chart/recorder.tsx` からのみ参照されていた（Task 4〜6 で参照元を削除済み）。

**Interfaces:**
- Consumes: なし
- Produces: なし（このタスクは削除のみ）

- [ ] **Step 1: 対象ファイルを削除する**

```bash
cd /home/httpd/Neurobeet/word-haku
cd src/hooks
rm -f useDataProcessFromEEGsv2.ts useMutateAddTags.ts useMutateAuth.ts \
      useMutateDeleteInfModels.ts useMutateDeleteTags.ts useMutateEEGsv2.ts \
      useMutateFolderMove.ts useMutateFolders.ts useProcessAddTags.ts \
      useProcessAuth.ts useProcessDeleteInfModels.ts useProcessDeleteTags.ts \
      useProcessEEGsv2.ts useProcessFolderMove.ts useProcessFolders.ts \
      useProcessRegister.ts useQueryEEGsv2.ts useQueryFolders.ts \
      useQueryInfModels.ts useQueryTrainIds.ts useQueryUser.ts
cd /home/httpd/Neurobeet/word-haku
ls src/hooks/
```
Expected: `use-toast.ts` だけが残っていること。

- [ ] **Step 2: 残存参照が無いことを確認する**

Run:
```bash
grep -rnE "hooks/(useDataProcessFromEEGsv2|useMutateAddTags|useMutateAuth|useMutateDeleteInfModels|useMutateDeleteTags|useMutateEEGsv2|useMutateFolderMove|useMutateFolders|useProcessAddTags|useProcessAuth|useProcessDeleteInfModels|useProcessDeleteTags|useProcessEEGsv2|useProcessFolderMove|useProcessFolders|useProcessRegister|useQueryEEGsv2|useQueryFolders|useQueryInfModels|useQueryTrainIds|useQueryUser)" src --include="*.ts" --include="*.tsx"
```
Expected: 何も出力されないこと(出力されたら、その参照元ファイルを確認して対応する)。

- [ ] **Step 3: 変更内容を確認する（git操作は行わない）**

Run: `git status` で `src/hooks/` 配下20ファイルが deleted になっていることを目視確認するのみ。add/commit は行わない。

---

## Task 8: museClientAtom.tsx の未使用atomを削除する

**Files:**
- Modify: `src/app/[locale]/components/museClientAtom.tsx`

Task 4〜7 で `museClientAtom`（MuseClientインスタンスを保持するatom）を使っていた `muse.tsx`, `Chart/recorder.tsx`, `Text/*`, `my/infer/*` が全て削除されたため、このatomは完全に未使用になる。

**Interfaces:**
- Consumes: なし
- Produces: なし（`rawDataAtom`, `filteredDataAtom`, `jsonDataAtom`, `eegSettingsAtom`, `lastDataTimestampAtom`, `liveVAAtom` は変更せず維持。Chart/EEG/Musicが引き続き使用する）

- [ ] **Step 1: 未使用の import と atom 宣言を削除する**

変更前:
```tsx
import { atom } from "jotai";
import { MuseClient, channelNames } from "muse-js";
import { eegSettings, JsonData, StreamData, EEGsv2 } from "@/types/types";

export const museClientAtom = atom<MuseClient | null>(null);
export const eegSettingsAtom = atom<eegSettings>({
```

変更後:
```tsx
import { atom } from "jotai";
import { channelNames } from "muse-js";
import { eegSettings, JsonData, StreamData, EEGsv2 } from "@/types/types";

export const eegSettingsAtom = atom<eegSettings>({
```

- [ ] **Step 2: 残存参照が無いことを確認する**

Run:
```bash
grep -rn "museClientAtom\b" src --include="*.ts" --include="*.tsx"
```
Expected: `src/app/[locale]/components/museClientAtom.tsx` 自体の定義以外に出力が無いこと。

- [ ] **Step 3: 型チェックを実行する**

Run: `npx tsc --noEmit`
Expected: エラーが出ないこと。

- [ ] **Step 4: 変更内容を確認する（git操作は行わない）**

Run: `git status` で `museClientAtom.tsx` が modified になっていることを目視確認するのみ。add/commit は行わない。

---

## Task 9: 未使用のi18nメッセージ名前空間を削除する

**Files:**
- Modify: `messages/en.json`
- Modify: `messages/ja.json`

新しい `page.tsx` は `useTranslations` を使わず、`Chart/`・`Music/`・`EEG/` 配下も文言をハードコードしている。唯一 `StddevMonitor.tsx` が `useTranslations("muse")` を使用しているため、`muse` 名前空間だけを残し、他の全ての最上位キー（`home`, `chart`, `text`, `auth`, `my`, `Test`, `Analysis`, `ai_beta`, `folder`, `trains`, `nav`, `Profile`, `Inference model construction`）を削除する。

**Interfaces:**
- Consumes: なし
- Produces: なし

- [ ] **Step 1: 残す名前空間を確認する**

Run:
```bash
grep -rn 'useTranslations(' "src/app/[locale]/components/Chart" "src/app/[locale]/components/Music" "src/app/[locale]/components/EEG" "src/app/[locale]/page.tsx" "src/app/[locale]/layout.tsx" "src/app/[locale]/providers.tsx" "src/app/[locale]/components/provider.tsx"
```
Expected: `StddevMonitor.tsx:    const t = useTranslations("muse");` の1件のみ。

- [ ] **Step 2: messages/en.json と messages/ja.json を `muse` キーのみに絞る**

それぞれのJSONファイルを開き、トップレベルキーが `muse` だけになるよう編集する（`muse` の中身は変更しない）。編集後は以下のように、有効なJSONとして `muse` キーのみが残っていることを確認する。

```bash
python3 -c "
import json
for f in ['messages/en.json', 'messages/ja.json']:
    d = json.load(open(f))
    assert list(d.keys()) == ['muse'], (f, list(d.keys()))
    print(f, 'OK')
"
```

- [ ] **Step 3: 開発サーバーで文言崩れが無いことを確認する**

Run: `npm run dev`
ブラウザで `http://localhost:3001/en` を開き、EEG接続パネル（Sheetを開いた際のバッテリー表示等、`muse` 名前空間の文言を使う部分）が正しく表示されることを確認する。確認後 Ctrl+C で停止する。

- [ ] **Step 4: 変更内容を確認する（git操作は行わない）**

Run: `git status` で両JSONファイルが modified になっていることを目視確認するのみ。add/commit は行わない。

---

## Task 10: 最終ビルド確認と手動スモークテスト

**Files:** なし（確認のみ）

**Interfaces:**
- Consumes: Task 1〜9 で完成した全体
- Produces: なし

- [ ] **Step 1: 本番ビルドを実行する**

Run: `npm run build`
Expected: TypeScriptエラー・ビルドエラーが無く成功すること。

- [ ] **Step 2: 開発サーバーでMockデバイスによる一連の動作を確認する**

Run: `npm run dev`

ブラウザで `http://localhost:3001/en` を開き、以下を確認する。

1. ヘッダー右上のEEG接続ボタンを開き、Deviceを "Mock" に切り替える。
2. "Connect" → "Start" を押し、EEGカードに波形が流れ始めることを確認する。
3. 操作バーの "Music" ボタンでMusicカードを表示状態にする。
4. プリセットを1つ選び、"Run analysis / Generate" を押す。バックエンド（`word_haku_api`）が起動していればしばらくして音声が再生されることを確認する（バックエンド未起動の場合はエラー表示が出ることを確認する程度でよい）。
5. "Experiment Mode" のチェックボックスをオンにし、`ExperimentPlayer` の "Run analysis / Generate" → "Stop" が正しく動作する（エラーで固まらない）ことを確認する。

確認後 Ctrl+C でサーバーを停止する。

- [ ] **Step 3: 削除したルートが404になることを確認する**

`npm run dev` を再度起動し、ブラウザで以下のURLに直接アクセスして404になることを確認する。

- `http://localhost:3001/en/login`
- `http://localhost:3001/en/my`

確認後 Ctrl+C でサーバーを停止する。

- [ ] **Step 4: 最終的な差分の一覧を確認する**

Run: `git status`
Expected: Task 1〜9 で意図した追加・変更・削除のみが表示されること。add/commit はユーザー自身が行うため、このセッションからは実行しない。
