# word-haku を EEG→Music 専用アプリにする設計

## 背景・目的

`word-haku` は現在、ログイン付きダッシュボード（学習データ収集・モデル管理・推論・EEGテキスト実験など）を含む大きなアプリだが、その中の「EEGを測定し、Chartで可視化し、その脳波に合わせて音楽を生成する」機能（`Music/` コンポーネント）だけを独立して動かせる最小構成にしたい。

`Music/` はすでに存在するが、現状は以下に依存している。

- ログイン必須のホームページ（`page.tsx`）内の1タブとして存在し、Text機能やログイン導線と同居している
- EEG接続はモノリシックな `components/muse.tsx`（Bluetooth接続・フィルタ処理・UIが1ファイルに同居）に依存
- Chart表示は `components/Chart/` のフローティングカード機構を使っているが、Musicカードとしては未統合

一方、`/home/httpd/braingram/word-haku` には、EEG接続部分だけを `EEG/`フォルダとして責務分離した実装（`EEGRunner` / `EEGPipeline` / `EEGSource`抽象 + Muse実機・Mockデバイスの差し替え可能な実装）が存在し、こちらの方が保守しやすい構造になっている。

本設計では、braingramのEEG実装を移植し、word-hakuをEEG測定・Chart表示・Music生成だけに絞った独立アプリへと作り変える。ログイン・学習データ管理・推論・Text実験などの既存ダッシュボード機能は、今回使わないため削除する。

## 前提・制約

- `word-haku/` はチームメンバー（aueno, fuji3to4）が主体の独立リポジトリ。このセッションからは **git操作（add/commit/push等）を一切行わない**。ファイルの追加・編集・削除は行うが、git状態の変更はユーザー自身が別ブランチ上で行う運用とする。
- 設計・実装の記録（本ドキュメント）は `graduation_research`（本リポジトリ）側の `docs/superpowers/specs/` に置き、そちらでのみコミットする。
- 既存の `word-haku` の未コミット変更（`next.config.mjs`, `main-nav.tsx` 等のfaviconパス変更）はこの作業と無関係のため触らない。

## 全体方針

`word-haku` を「EEG→Music専用アプリ」として作り変える。具体的には以下の3本柱。

1. **EEG接続層の刷新**：`muse.tsx`（モノリシック）を廃止し、braingram の `EEG/` フォルダ一式（`EEGRunner`, `EEGPipeline`, `EEGatoms`, `sources/{EEGSource,museSource,mockSource}`）を移植する。Mockデバイスに切り替えれば実機なしでも動作確認できる。
2. **Music の Chart 統合**：`Chart/chart.tsx` の既存フローティングカード機構（表示/非表示トグル、ドラッグ、リサイズ）に `music` カードを追加し、EEG/FFT/BandPowerと同列に扱う。
3. **不要機能の削除**：ログイン、学習データダッシュボード（`/my` 配下：Analytics/Rawdata、infmodels、infer、profile）、Text実験機能を丸ごと削除し、依存する認証フック・サーバーアクションも削除する。

## コンポーネント設計

### 1. `page.tsx`（全面書き換え）

- `Tabs` / `TabsContent`（Text・Music個別タブ）を廃止。
- ログインボタン、`MainNav`、`LangSwitch`、`Muse` を削除。
- 簡易ヘッダー（アプリ名のテキストのみ）+ EEG接続コントロール（`EEGRunner`）+ `<Chart />` のみのシンプルな1画面構成にする。

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

### 2. `components/EEG/`（新規、braingramから移植）

以下をそのまま（パスのみ調整して）コピーする。両リポジトリの `museClientAtom.tsx` は主要atom（`rawDataAtom`, `filteredDataAtom`, `jsonDataAtom`, `eegSettingsAtom`）が同一名・同一形状のため無改造で接続できる。

- `EEGatoms.ts`：世代カウンタ・デバイス選択・接続状態などのUI用atom
- `EEGpipeline.tsx`：BLE/Mockソースからのストリームをフィルタ→FFT→BandPowerまで処理しatomに書き込むロジック。**1点だけ手を入れる**：生データ受信時（`setRawData` のtap内）に、Neurobeet側にのみ存在する `lastDataTimestampAtom` も更新するよう1行追加する（`ExperimentPlayer.tsx` がこのatomでデータ途絶を検知しているため）。
- `EEGRunner.tsx`：Sheet型の接続UI（デバイス選択・Connect/Disconnect・Start/Stop・フィルタ設定・バッテリー表示）。ページヘッダーに配置する。
- `sources/EEGSource.ts`, `sources/museSource.ts`, `sources/mockSource.ts`：デバイス接続の抽象化とMuse実機/Mock実装。

`EEGdebugHUD.tsx`（コンソールログのみで画面描画なし）は最小構成には含めない。

旧 `components/muse.tsx` は削除する。

### 3. `Chart/chart.tsx`（拡張）

- `ChartComponentMap` に `music: <MusicComponent />` を追加。
- `initialCharts` に Musicカード定義を追加（初期非表示、他カードと同じドラッグ&リサイズ可能。サイズは操作パネル+可視化+オーディオを含むためやや大きめの `900x750` 程度）。
- カード内コンテンツ用ラッパーの `overflow-hidden` を `overflow-auto` に変更（Musicパネルは縦に長くなるため。他のグラフ表示には影響しない）。

### 4. `Music/index.tsx`（微調整のみ）

- カードヘッダーと重複する `<h2>Music / EEG AI</h2>` の見出しを削除。
- `Player.tsx`（プリセット選択→単発生成）と `ExperimentPlayer.tsx`（自動ループ・目標valence/arousalフィードバック）はそのまま維持。

### 5. 削除するもの

- `src/app/[locale]/login/` 一式（`page.tsx`, `auth.tsx`, `signup.tsx`, `google.tsx`）
- `src/app/[locale]/my/` 一式（`page.tsx`, `profile/`, `infmodels/`, `infer/`, `Analytics/Rawdata/`, `components/user-nav.tsx`, `components/chart-hover.tsx`）
- `src/app/[locale]/components/Text/`
- `src/app/[locale]/components/main-nav.tsx`
- `src/app/[locale]/components/muse.tsx`
- `src/hooks/useMutateAuth.ts`, `useProcessRegister.ts`, `useProcessAuth.ts`, `useQueryUser.ts`
- `src/lib/serverActions_Google.ts`

削除後に他のファイルから上記への参照が残っていないか（import漏れ）をビルドで確認する。

### 残すもの

`layout.tsx`（ヘッダー簡素化に伴い調整）, `providers.tsx`, `components/provider.tsx`, `i18n/`, `middleware.ts`（言語ルーティングのみで認証には関与しないため無改造）, `components/museClientAtom.tsx`, `components/StddevMonitor.tsx`, `components/StddevDots.tsx`（未使用なら残置可、実害なし）, `components/params.tsx`（EEG設定関連なら要確認、使用箇所次第で残す）, `Chart/`, `Music/`, 新設 `EEG/`。

## データフロー

```
EEGRunner（Connect/Start操作）
  → EEGPipeline（Muse実機 or Mockソースからreadings$購読）
    → notch/highpass/lowpassフィルタ → epoch → FFT → band power
    → jotai atoms（rawDataAtom / filteredDataAtom / jsonDataAtom / lastDataTimestampAtom）を更新
      → Chart内 RealtimeEEG / FFT / BandPower がjsonDataAtomを描画
      → Music/Player.tsx が rawDataAtom を使って感情推定→音楽生成APIを呼ぶ
      → Music/ExperimentPlayer.tsx が rawDataAtom・liveVAAtom を使って自動ループのフィードバックを行う
```

バックエンド（`word_haku_api`）側のAPIは変更なし（`/eeg_emotion/*`, `/music/generate`, `/experiment/*` はそのまま利用）。

## エラーハンドリング

- EEG接続失敗・データ途絶時のエラー表示は `EEGRunner`（`errorMessageAtom`）にすでに実装済みのものをそのまま利用。
- Music生成API呼び出し失敗時のエラー表示も既存の `Player.tsx` / `ExperimentPlayer.tsx` の実装をそのまま利用（変更なし）。
- ページ削除に伴うビルドエラー（存在しないimport等）は、実装フェーズで `next build` を通してTypeScriptエラーを潰す。

## テスト方針

自動テストは既存にないため、手動確認を実施する。

1. `npm run dev` 起動後、EEGRunnerで **Mockデバイス** を選択→Connect→Start → EEGカードに波形が表示される。
2. Musicカードを表示状態にし、プリセットを選んで「Run analysis / Generate」→ 音声が再生される。
3. Experiment Modeにチェックを入れ、自動ループが開始・Stopで正しく止まることを確認する。
4. `/login`, `/my` 系のURLに直接アクセスして404になる（削除が正しく反映されている）ことを確認する。
5. `next build` がTypeScriptエラーなく通ることを確認する。

## 未確定・要確認事項

- `components/params.tsx` / `StddevDots.tsx` の実際の使用箇所は実装時に再確認し、真に未使用であれば削除、使用されていれば残す。
- `messages/en.json` / `ja.json` 内の `auth` / `my` / `text` 系の翻訳キーは、実害はないため今回は削除必須とせず、目についた範囲でのみ整理する。
