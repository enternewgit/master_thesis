# word-haku — 音楽による感情ニューロフィードバックシステム

EEG（脳波）からリアルタイムに感情状態（Valence / Arousal）を推定し、目標の感情状態へ誘導するための音楽を自動生成する**ニューロフィードバック**システムです。

---

## システム概要

```
┌──────────────┐     BLE      ┌─────────────────┐     REST/WS     ┌──────────────────────┐
│  Muse S2     │ ──────────── │  Next.js         │ ──────────────  │  FastAPI             │
│  (EEGデバイス)│              │  フロントエンド     │                │  バックエンド          │
└──────────────┘              └─────────────────┘                └──────────┬───────────┘
                                                                           │
                                                         ┌────────────────┴────────────────┐
                                                         │                                 │
                                                  ┌──────▼──────┐                ┌─────────▼──────────┐
                                                  │ Bi-Mamba     │                │ Stable Audio Open  │
                                                  │ 感情推定モデル │                │ 音楽生成モデル       │
                                                  │ (V/A推定)    │                │ (ローカルGPU推論)    │
                                                  └──────┬──────┘                └─────────┬──────────┘
                                                         │                                 │
                                                         └────────────────┬────────────────┘
                                                                          │
                                                              ┌───────────▼──────────┐
                                                              │ ルールベースマッピング   │
                                                              │ (Russell 感情円環モデル) │
                                                              │  V/A → プロンプト構築    │
                                                              └──────────────────────┘
```

### フィードバックループ

1. **EEG取得**: Muse S2 から BLE 経由で 4ch 脳波を取得
2. **感情推定**: EEGMamba（双方向 Mamba SSM）で Valence / Arousal を推定
3. **目標補間**: `next = current + α × (target − current)` で段階的な目標値を算出
4. **プロンプト生成**: Russell 感情円環モデルに基づき、BPM・ダイナミクス・キー・楽器・テクスチャをルールベースで決定
5. **音楽生成**: Stable Audio Open でプロンプトから WAV を生成
6. **再生 → 次のEEG取得**: 生成された音楽をユーザに再生し、ループを繰り返す

---

## 技術スタック

| レイヤー | 技術 |
|---|---|
| EEG デバイス | Muse S2（BLE） |
| フロントエンド | Next.js 15 / React 19 / TypeScript / Tailwind CSS / Radix UI |
| EEG 信号処理 | muse-js / @neurosity/pipes |
| 状態管理 | Redux Toolkit / Jotai / TanStack React Query |
| 国際化 | next-intl（日本語 / 英語） |
| 認証（FE） | NextAuth v5 |
| バックエンド API | FastAPI / Python 3.12+ |
| データベース | MongoDB Atlas（Motor async / GridFS） |
| 認証（BE） | JWT + CSRF + OAuth |
| 感情推定モデル | PyTorch / Mamba SSM（EEGMamba Bidirectional） |
| 音楽生成 | Stable Audio Open（stable-audio-tools） / MusicGen（HF API） |
| 可視化・分析 | librosa / matplotlib / scipy |

---

## ディレクトリ構成

本プロジェクトはチーム開発です。フロントエンド / バックエンドは他メンバーが主体となり
独立した GitHub リポジトリとして開発・管理しています。自分（sumi_masahiro312）の担当範囲は
**EEG感情推定モデル（EEGMamba）の学習・実装**、**音楽生成プロトタイプ（MusicGen / mrt2_poc）の検証・実装**、
**研究統括・実験設計・可視化分析** です。

| ディレクトリ | 実体 | 説明 |
|---|---|---|
| [`frontend/`](https://github.com/aueno/word-haku)（旧 word-haku） | チームメンバー主体の独立リポジトリ (243 commits, 主著者: aueno, fuji3to4) | フロントエンド (Next.js 15 / React 19)。EEG可視化、音楽再生、認証、多言語対応 |
| [`backend/`](https://github.com/aueno/word_haku_api)（旧 word_haku_api） | チームメンバー主体の独立リポジトリ (119 commits, 主著者: aueno, fuji3to4) | バックエンド (FastAPI)。感情推定・音楽生成API、フィードバックループの核心ロジック |
| `MusicGen/` | 本リポジトリ管理下（**自分の担当**） | 初期プロトタイプ。MusicGen / Stable Audio のローカル生成・ストリーミング検証 |
| `mrt2_poc/` | 本リポジトリ管理下（**自分の担当**） | Magenta RealTime を使った音楽生成方式のPoC |
| `models/` | 本リポジトリ管理下（**自分の担当**） | 学習済みEEGMambaモデル重み (Valence / Arousal の `.pth`) と正規化統計量 (`.joblib`)。デモのポータビリティ確保のためgit管理下に追加済み（`.gitignore`対象ではない） |
| `analysis_results/` | 本リポジトリ管理下（**自分の担当**、gitignore対象） | 生成音声の可視化・統計分析の出力 |

```
graduation_research/
├── frontend/                   # フロントエンド (Next.js) — チームメンバー主体の独立リポジトリ
│   ├── src/
│   │   ├── app/[locale]/       # ロケール別ページ
│   │   │   ├── components/     # Chart, Music, Muse(BLE), StddevMonitor
│   │   │   └── my/             # Analytics, Infer, InfModels, Profile
│   │   └── hooks/              # 22個のカスタムフック (CRUD, 認証, EEG)
│   └── messages/               # 国際化リソース (en.json, ja.json)
│
├── backend/                    # バックエンド (FastAPI) — チームメンバー主体の独立リポジトリ
│   ├── word_haku_api/
│   │   ├── main.py             # FastAPI アプリ定義 (15 ルーター)
│   │   ├── schemas.py          # Pydantic モデル定義
│   │   ├── auth_utils.py       # JWT / CSRF 認証
│   │   ├── database.py         # MongoDB v1 操作
│   │   ├── databasev2.py       # MongoDB v2 操作
│   │   ├── music_ai/
│   │   │   ├── emotion_model.py         # EEGMamba 感情推定モデル
│   │   │   ├── infer.py                 # 推論ラッパー (単体 / バッチ)
│   │   │   ├── loader.py                # モデルレジストリ
│   │   │   ├── generator.py             # 音楽生成プロバイダ抽象化
│   │   │   └── generate_stableaudio_local.py  # ローカル Stable Audio 推論
│   │   └── routers/
│   │       ├── route_experiment.py      # 実験フィードバックループ (核心)
│   │       ├── route_eeg_emotion.py     # 感情推定 REST API
│   │       ├── route_music.py           # 音楽生成 REST API
│   │       └── ...                      # EEG, Auth, Folders 等の各ルーター
│   ├── analysis.py             # 生成音声の可視化・比較ツール
│   ├── batch_viz.py            # バッチ可視化
│   ├── stats_tests.py          # 統計検定 (t検定, Mann-Whitney U, Cohen's d)
│   └── pyproject.toml          # uv 依存管理
│
├── MusicGen/                   # 音楽生成プロトタイプ (v1)
│   ├── proxy.py                # Lyria RealTime WebSocket プロキシ
│   ├── streaming_server.py     # ストリーミングデモサーバ
│   └── generate_*.py           # 各種生成スクリプト
│
├── mrt2_poc/                   # Magenta RealTime PoC (v2)
├── models/                     # 学習済みモデル重み・正規化統計量
└── analysis_results/           # 可視化・統計分析の出力
```

---

## セットアップ

### 前提条件

- Python 3.12（`uv`管理。[uvのインストール](https://docs.astral.sh/uv/getting-started/installation/)が必要。`backend/.python-version`で3.12に固定済みなので`uv sync`が自動でこのバージョンを使う。固定していないと、マシンにより新しいPython(3.14等)が入っていた場合にそちらが優先され、後述のpandasビルド問題を誘発することがある）
- Node.js 18+
- MongoDB Atlas アカウント（またはローカル MongoDB）
- CUDA 12.8 対応 GPU（ローカル音楽生成・EEG感情推定モデルのビルド用、推奨。`torch==2.9.1`がcu128向けに固定されている）
- Muse S2 デバイス（EEG 取得用）

### 1. バックエンド

依存関係は `uv` で管理しています（`poetry`ではありません。`poetry.lock`は無く`uv.lock`のみ存在します）。

```bash
cd backend

# uv で依存をインストール（torch/torchaudio/torchvisionもpyproject.tomlでcu128向けに
# 固定済みなので、ここで自動的にインストールされる。個別にpip installする必要はない）
uv sync

# flash-attn はソースからコンパイルされるため数分〜十数分かかることがある
# （pyproject.tomlの [tool.uv] no-build-isolation-package 設定で対応済み）

# mamba-ssm は pyproject.toml に含まれておらず(emotion_model.py が
# `from mamba_ssm import Mamba` している)、別途手動インストールが必要。
# ビルド時にtorchを直接importするため([tool.uv] no-build-isolation-package
# に含めて対応済み)、上のuv syncを先に済ませてtorchを入れてから実行すること
uv pip install mamba-ssm

# 環境変数ファイルを作成（.env.example は存在しないため、直接作成する）
touch .env
```

> `uv sync` / `uv pip install mamba-ssm` がエラーになる場合は、まず
> [トラブルシューティング](#トラブルシューティング)を確認してください。

`.env` に以下を設定：

```env
MONGO_API_KEY=mongodb+srv://...
JWT_KEY=your_jwt_secret
CSRF_KEY=your_csrf_secret
FRONTEND_URL=http://localhost:3000

# 感情推定モデルのパス（省略時は backend/word_haku_api/routers/ から見た
# ../../../valence.pth = プロジェクトルート直下を自動検出しようとするが、実際の
# 重みは models/ 以下にあるため、必ず明示的に設定すること）
EMO_VALENCE_PATH=../models/valence.pth
EMO_AROUSAL_PATH=../models/arousal.pth

# 音楽生成（ローカル使用時は不要）
# HF_API_TOKEN=hf_...
# STABLE_AUDIO_API_URL=...
```

音楽生成の常駐サーバーを起動（**バックエンド本体より先に起動しておくこと**。
起動していないと `/experiment/feedback` や `/music/generate` が
「Could not reach the ... server」で失敗する）：

```bash
# MRT2（provider="mrt2"）を使う場合。word_haku_api本体とは別プロセス・別venv
# （JAXとtorchのCUDAライブラリ競合を避けるため）。Docker化済みなのでこちらを推奨:
cd mrt2_poc
docker build -t mrt2-server .
docker run --rm --gpus all -p 8799:8799 \
  -v mrt2-models:/root/Documents/Magenta/magenta-rt-v2 \
  mrt2-server
# 初回はモデルダウンロードで数分かかる。ヘルスチェック:
#   curl http://127.0.0.1:8799/health
#   → "gpu_ready": true になっていることを確認。
# ネイティブ実行(venv直接)や詳細なトラブルシューティングは
# mrt2_poc/README.txt の6節・6.5節・6.6節(RunPodデプロイ)を参照。
```

補足として、Stable Audio Open（provider="stable"、デフォルト）を使う場合は以下：

```bash
uv run python -m word_haku_api.music_ai.stableaudio_server --port 8798
```

バックエンド起動：

```bash
# 開発
uv run uvicorn word_haku_api.main:app --reload --host 0.0.0.0 --port 8000

# 推論時の CPU スレッド制御（BLE 通信との競合防止）
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run uvicorn word_haku_api.main:app --host 0.0.0.0 --port 8000
```

### 2. フロントエンド

```bash
cd frontend

npm install
```

`.env.local` を作成：

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

```bash
npm run dev
# → http://localhost:3000
```

バックエンド（8000番）を先に起動しておくこと。起動していないと、ブラウザの
コンソールに `Failed to fetch` が出る。

---

## トラブルシューティング

### `uv sync` が `stable-audio-tools` のメタデータ生成で失敗する

```
Failed to generate package metadata for `stable-audio-tools==0.0.22 @ directory+stable-audio-tools-v2`
  Caused by: ... does not appear to be a Python project, as neither `pyproject.toml` nor `setup.py` are present in the directory
```

`backend/stable-audio-tools-v2/` は Stability AI 公式リポジトリを
ローカルで軽微に修正したフォークで、`pyproject.toml` からローカル
ディレクトリとして参照している。過去にこのディレクトリが独自の `.git` を
持つネストしたリポジトリだったため `backend` 本体のgit管理下に無く
（`.gitmodules` にも未登録の壊れたgitlinkとして記録されていた）、clone
しても中身が空になっていた。現在は通常ファイルとして取り込み済み。もし
再現する場合はリポジトリが最新化されていない可能性があるので、`git pull`
してから再度 `uv sync` を試すこと。

### `uv sync` が `pandas==2.0.2` のビルドで失敗する

```
ModuleNotFoundError: No module named 'pkg_resources'
```

`pandas==2.0.2`（`stable-audio-tools` 経由の間接依存）が
`build-system.requires` に `setuptools` を明記しておらず、uvの隔離ビルド
環境に `pkg_resources` が無い状態になるのが原因。加えて `setuptools>=81`
は `pkg_resources` モジュール自体を削除している（84.0.0のwheelで確認済み、
80.0.0にはまだ存在）ため、単に `setuptools` を足すだけでは直らない。
`backend/pyproject.toml` の `[tool.uv]` に以下を追記して解消済み：

```toml
[tool.uv]
extra-build-dependencies = { pandas = ["setuptools<81"] }
```

### `uv pip install mamba-ssm` が `ModuleNotFoundError: No module named 'torch'` で失敗する

`mamba-ssm` はビルド時（`setup.py`）に `torch` を直接importするが、
`uv pip install` は隔離ビルド環境を使うため `torch` が見えず失敗する
（`flash-attn` と同種の問題）。`backend/pyproject.toml` の
`[tool.uv] no-build-isolation-package` に `mamba-ssm` を追加済み。これが
効くには、先に `uv sync` を実行して `torch` がプロジェクトの `.venv` に
インストール済みである必要がある。

### `docker run` が `port is already allocated` で失敗する

MRT2の常駐サーバーは既に別のターミナルなどで起動済みで、正常に動いている
可能性が高い。`docker ps` で `mrt2-server` イメージのコンテナが `healthy`
になっていないか確認し、動いていれば `docker run` は不要（そのまま次の
手順に進んでよい）。念のため再起動したい場合は `docker stop <name>` して
から `docker run` し直す。

### フロントエンドで `Failed to fetch` が出る

だいたい次のどちらか：

- バックエンド（`uvicorn`、8000番）が起動していない
- `frontend/.env.local` が無い、または `NEXT_PUBLIC_API_URL` が
  未設定・間違っている

`curl http://localhost:8000/` で接続できるか確認すること。

---

## 主要 API エンドポイント

### 感情推定

| メソッド | パス | 説明 |
|---|---|---|
| `POST` | `/eeg_emotion/predict` | EEG データから Valence / Arousal を推定 |
| `GET` | `/eeg_emotion/status` | モデルロード状態の確認 |

### 実験フィードバック

| メソッド | パス | 説明 |
|---|---|---|
| `POST` | `/experiment/feedback` | 60秒 EEG → 感情推定 → 音楽生成 → WAV ストリーミング |
| `GET` | `/experiment/latest` | 最新の実験状態（ポーリング UI 用） |
| `POST` | `/experiment/stop` | 実験の停止 |

### 音楽生成

| メソッド | パス | 説明 |
|---|---|---|
| `POST` | `/music/generate` | プロンプトから音楽を生成（HF / Stable Audio） |

### データ管理

| メソッド | パス | 説明 |
|---|---|---|
| `POST` | `/eegsv2/` | EEG データ保存 (v2) |
| `GET` | `/eegsv2/{train_id}` | EEG データ取得 |
| `POST` | `/folders/` | フォルダ作成 |
| `POST` | `/auth/login` | ログイン |

---

## 感情推定モデル（EEGMamba）

### アーキテクチャ

**Bidirectional Mamba SSM** を採用した脳波解析モデルです。

```
入力: (batch, 4ch, 100samples)
       │
  ┌────▼────┐
  │ Linear  │  n_channels → d_model (64)
  └────┬────┘
       │
  ┌────▼──────────────┐
  │ Mamba Forward      │──┐
  │ Mamba Backward     │──┤  双方向処理
  └────────────────────┘  │
       │                  │
  ┌────▼──────────────────▼──┐
  │ Global Average Pooling    │
  │ Concatenate (d_model × 2) │
  └────────────┬──────────────┘
               │
  ┌────────────▼────────────┐
  │ Linear → softmax (2cls) │
  └─────────────────────────┘
出力: Valence or Arousal 確率
```

- **入力**: 4チャンネル EEG（TP9, AF7, AF8, TP10）× 100 サンプル
- **出力**: High/Low の 2 値分類（Valence モデル, Arousal モデルの 2 つを使用）
- **正規化**: チャンネルごと z-score（事前計算した統計量を使用）
- **バッチ推論**: 60 秒の EEG をスライディングウィンドウで分割、バッチ推論で高速化

---

## プロンプト生成ルール

Russell 感情円環モデルに基づき、Valence / Arousal のスコアから音楽パラメータを決定します。

| パラメータ | マッピングルール |
|---|---|
| **BPM** | `60 + (arousal × 90)` → 60〜150 BPM |
| **ダイナミクス** | A > 0.66: Fortissimo / A < 0.33: Pianissimo / 中間: Mezzo-forte |
| **キー** | V > 0.6: C Major / V < 0.4: C Minor |
| **テクスチャ** | A > 0.6: Dense / A < 0.4: Sparse |
| **ムード** | 4象限: Joyful / Tense / Melancholic / Peaceful |

### 遷移プロンプト（Evolution）

現在 → 目標の差分に応じて、遷移指示を自動生成：

- **ΔA > 0.18**: Crescendo, Increasing density
- **ΔA < -0.18**: Decrescendo, Becoming sparser
- **ΔV > 0.15**: Becoming brighter, Resolving harmonies
- **ΔV < -0.25**: Becoming darker, Building tension

### テンプレート例

```python
base_prompt = (
    "A {dynamics} {texture} piece played by {instruments}. "
    "Key of {key_hint}, Tempo {bpm} BPM."
)
```

利用可能な変数: `{current_v}`, `{current_a}`, `{next_v}`, `{next_a}`, `{target_v}`, `{target_a}`, `{bpm}`, `{dynamics}`, `{key_hint}`, `{instruments}`, `{texture}`

---

## 可視化・統計分析ツール

生成音声の音響特徴を比較するためのスクリプト群です。

```bash
cd backend

# 2つの音声ファイルを比較（スペクトログラム + 統計 CSV）
uv run python analysis.py --file1 happy.wav --file2 sad.wav \
    --label1 "Happy" --label2 "Sad" --outdir viz

# Happy/Sad のバッチ比較
uv run python batch_viz.py

# 統計検定（Welch t検定, Mann-Whitney U, Cohen's d）
uv run python stats_tests.py
```

出力:
- スペクトログラム / 波形比較画像
- スペクトル重心 / 帯域幅 / RMS の統計 CSV
- 有意差検定結果

---

## パフォーマンスのヒント

- **GPU 推奨**: Stable Audio Open のローカル生成には CUDA 対応 GPU を推奨（AMP 自動有効化）
- **CPU スレッド制御**: EEG 推論時に `OMP_NUM_THREADS=1` を設定すると、BLE 通信との競合を防止できる
- **バッチ推論**: EEG のウィンドウ推論はバッチ処理で GPU 効率を最大化

### テスト

```bash
# 基本的なフィードバックテスト
uv run python test_feedback.py

# Override テスト（推論スキップ、プロンプト生成経路のみ検証）
uv run python test_feedback_override.py
```

---

## ライセンス

本プロジェクトは卒業研究として開発されています。


