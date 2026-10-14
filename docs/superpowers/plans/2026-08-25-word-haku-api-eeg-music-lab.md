# word_haku_api EEG→Music専用API化 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `word_haku_api`(FastAPIバックエンド)を、実際にフロントエンド(`word-haku`)から呼ばれている `/eeg_emotion/*`, `/music/generate`, `/experiment/*` の3系統のみを提供する最小構成に作り変える。

**Architecture:** `main.py` を先に15router登録から3router登録に縮小し、その後、参照されなくなった認証・DB・学習用モデルコード一式(12個のrouterとその依存先)を段階的に削除する。既に孤立している旧実装(`ai/eeg_emotion.py`, `music_ai/generate_music.py`, `music_ai/generate_stableaudio.py`)も併せて削除する。

**Tech Stack:** Python 3.12 / FastAPI / uvicorn / torch / stable-audio-tools(ベンダリング版 `stable-audio-tools-v2`)。パッケージ追加・削除は行わない(`pyproject.toml`は対象外)。

**Spec:** `docs/superpowers/specs/2026-08-25-word-haku-api-eeg-music-lab-design.md`

## Global Constraints

- **`word_haku_api/` では git操作(add/commit/push/revert等)を一切行わない。** 各タスク末尾は「動作確認」ステップとし、コミットはユーザー(またはコントローラーセッション)が別リポジトリ側(graduation_research)で行う。
- 自動テストフレームワーク・型チェッカー設定(mypy等)はこのリポジトリに存在しない。各タスクの検証は、仮想環境の Python で `word_haku_api.main` を実際にimportして例外が出ないことを確認する方法を基本とする(FastAPIの `app = FastAPI()` やrouter登録はimport時に実行されるため、この方法で「参照が壊れていないこと」を実際に検証できる。`@app.on_event("startup")` の中身はuvicorn起動時にしか実行されないため、この時点ではモデル読み込み等の重い処理は走らない)。
- Pythonの実行には毎回 `cd /home/httpd/Neurobeet/word_haku_api && source .venv/bin/activate && <コマンド>` の形を使う(このシェル環境では `source` によるvenv有効化は同一コマンド内でのみ有効なため、確認コマンドは都度 `source ... &&` から書くこと)。
- `pyproject.toml` の依存関係、`stable-audio-tools-v2/`、`mrt2_poc/`、`tests/`(中身は空)には手を入れない。
- コマンドはすべて `cd /home/httpd/Neurobeet/word_haku_api` した状態で実行する前提。

---

## Task 1: main.py を3router構成に縮小する

**Files:**
- Modify: `word_haku_api/main.py`(全面書き換え)

**Interfaces:**
- Consumes: `word_haku_api/routers/route_eeg_emotion.py`, `route_music.py`, `route_experiment.py` の `router`(既存、変更なし)。`route_experiment.py` の `start_prefetch_worker`, `stop_prefetch_worker`(既存、変更なし)。
- Produces: なし(アプリのエントリポイント)

- [ ] **Step 1: `main.py` を以下の内容に置き換える**

```python
import os
import torch
# Limit CPU threads used by native libraries to avoid saturating the host
# (prevents heavy inference from starving other components like Bluetooth handling)
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
try:
    torch.set_num_threads(1)
except Exception:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from word_haku_api.routers.route_eeg_emotion import router as route_eeg_emotion
from word_haku_api.routers.route_music import router as route_music
from word_haku_api.routers.route_experiment import router as route_experiment
from word_haku_api.routers.route_experiment import start_prefetch_worker, stop_prefetch_worker
from decouple import config

app = FastAPI()
FRONTEND_URL = config('FRONTEND_URL')

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],  # ReactからのAPIアクセスを許可
    allow_credentials=True,
    allow_methods=["*"],  # 全てのHTTPメソッドを許可
    allow_headers=["*"],  # 全てのHTTPヘッダーを許可
)

app.include_router(route_eeg_emotion, prefix="/eeg_emotion", tags=["eeg_emotion"])
app.include_router(route_music, prefix="/music", tags=["music"])
app.include_router(route_experiment, prefix="/experiment", tags=["experiment"])


@app.on_event("startup")
async def startup_event():
    start_prefetch_worker()


@app.on_event("shutdown")
async def shutdown_event():
    stop_prefetch_worker()


@app.get("/")
def root():
    return {"message": "Welcome to word-haku-API"}
```

- [ ] **Step 2: importが成功することを確認する**

Run:
```bash
cd /home/httpd/Neurobeet/word_haku_api && source .venv/bin/activate && python -c "from word_haku_api.main import app; print('OK')"
```
Expected: `OK` とだけ出力され、例外が出ないこと。

- [ ] **Step 3: 変更内容を確認する(git操作は行わない)**

Run: `git status` で `main.py` が modified になっていることを目視確認するのみ。add/commit は行わない。

---

## Task 2: 使われなくなった12個のrouterとeeg2word/を削除する

**Files:**
- Delete: `word_haku_api/routers/route_eegs.py`
- Delete: `word_haku_api/routers/route_eegsv2.py`
- Delete: `word_haku_api/routers/route_pred.py`
- Delete: `word_haku_api/routers/route_auth.py`
- Delete: `word_haku_api/routers/route_users.py`
- Delete: `word_haku_api/routers/route_OAuth.py`
- Delete: `word_haku_api/routers/route_ai.py`
- Delete: `word_haku_api/routers/route_ai_YesNo.py`
- Delete: `word_haku_api/routers/route_ai_beta.py`
- Delete: `word_haku_api/routers/route_infmodels.py`
- Delete: `word_haku_api/routers/route_folders.py`
- Delete: `word_haku_api/routers/route_admin.py`
- Delete: `word_haku_api/routers/eeg2word/`(フォルダ全体)

Task 1で `main.py` がこれらを一切importしなくなったため、安全に削除できる。

**Interfaces:**
- Consumes: なし
- Produces: なし(削除のみ)

- [ ] **Step 1: 対象ファイル・フォルダを削除する**

```bash
cd /home/httpd/Neurobeet/word_haku_api
rm -f word_haku_api/routers/route_eegs.py
rm -f word_haku_api/routers/route_eegsv2.py
rm -f word_haku_api/routers/route_pred.py
rm -f word_haku_api/routers/route_auth.py
rm -f word_haku_api/routers/route_users.py
rm -f word_haku_api/routers/route_OAuth.py
rm -f word_haku_api/routers/route_ai.py
rm -f word_haku_api/routers/route_ai_YesNo.py
rm -f word_haku_api/routers/route_ai_beta.py
rm -f word_haku_api/routers/route_infmodels.py
rm -f word_haku_api/routers/route_folders.py
rm -f word_haku_api/routers/route_admin.py
rm -rf word_haku_api/routers/eeg2word
```

- [ ] **Step 2: 残存参照が無いことを確認する**

Run:
```bash
grep -rnE "route_eegs\b|route_eegsv2\b|route_pred\b|route_auth\b|route_users\b|route_OAuth\b|route_ai\b|route_ai_YesNo\b|route_ai_beta\b|route_infmodels\b|route_folders\b|route_admin\b|eeg2word" word_haku_api --include="*.py"
```
Expected: 何も出力されないこと。

- [ ] **Step 3: importが成功することを確認する**

Run:
```bash
cd /home/httpd/Neurobeet/word_haku_api && source .venv/bin/activate && python -c "from word_haku_api.main import app; print('OK')"
```
Expected: `OK` とだけ出力され、例外が出ないこと。

- [ ] **Step 4: 変更内容を確認する(git操作は行わない)**

Run: `git status` で該当ファイル・フォルダが deleted になっていることを目視確認するのみ。add/commit は行わない。

---

## Task 3: 認証・DB・スキーマ定義を削除する

**Files:**
- Delete: `word_haku_api/database.py`
- Delete: `word_haku_api/databasev2.py`
- Delete: `word_haku_api/auth_utils.py`
- Delete: `word_haku_api/schemas.py`

Task 2で削除した12個のrouterがこれらの唯一の参照元だったため(`main.py`もTask 1で参照を外している)、安全に削除できる。

**Interfaces:**
- Consumes: なし
- Produces: なし(削除のみ)

- [ ] **Step 1: 対象ファイルを削除する**

```bash
cd /home/httpd/Neurobeet/word_haku_api
rm -f word_haku_api/database.py
rm -f word_haku_api/databasev2.py
rm -f word_haku_api/auth_utils.py
rm -f word_haku_api/schemas.py
```

- [ ] **Step 2: 残存参照が無いことを確認する**

Run:
```bash
grep -rnE "from \.\.database\b|from \.database\b|from \.\.databasev2\b|from \.databasev2\b|from \.\.auth_utils\b|from \.auth_utils\b|from \.\.schemas\b|from \.schemas\b|word_haku_api\.database\b|word_haku_api\.databasev2\b|word_haku_api\.auth_utils\b|word_haku_api\.schemas\b" word_haku_api --include="*.py"
```
Expected: 何も出力されないこと。

- [ ] **Step 3: importが成功することを確認する**

Run:
```bash
cd /home/httpd/Neurobeet/word_haku_api && source .venv/bin/activate && python -c "from word_haku_api.main import app; print('OK')"
```
Expected: `OK` とだけ出力され、例外が出ないこと。

- [ ] **Step 4: 変更内容を確認する(git操作は行わない)**

Run: `git status` で該当4ファイルが deleted になっていることを目視確認するのみ。add/commit は行わない。

---

## Task 4: 既に孤立していた旧実装を削除する

**Files:**
- Delete: `word_haku_api/ai/`(フォルダ全体。`eeg_emotion.py` 1ファイルのみを含み、リポジトリ全体から参照が無いことを確認済み)
- Delete: `word_haku_api/music_ai/generate_music.py`(Hugging Face MusicGen APIを叩く旧実装。`generator.py`に置き換え済みで参照が無いことを確認済み)
- Delete: `word_haku_api/music_ai/generate_stableaudio.py`(Stable Audio HostedAPI版の旧実装。`generate_stableaudio_local.py`に置き換え済みで参照が無いことを確認済み)

これら3つは今回のTask 1〜3の削除とは無関係に、作業開始前から既にどこからも参照されていなかったコードである。

**Interfaces:**
- Consumes: なし
- Produces: なし(削除のみ)

- [ ] **Step 1: 対象ファイル・フォルダを削除する**

```bash
cd /home/httpd/Neurobeet/word_haku_api
rm -rf word_haku_api/ai
rm -f word_haku_api/music_ai/generate_music.py
rm -f word_haku_api/music_ai/generate_stableaudio.py
```

- [ ] **Step 2: 残存参照が無いことを確認する**

Run:
```bash
grep -rnE "ai\.eeg_emotion|from \.\.ai\b|from \.ai\b|generate_music\b|generate_stableaudio\b" word_haku_api --include="*.py" | grep -v "generate_stableaudio_local"
```
Expected: 何も出力されないこと(`generate_stableaudio_local` はこのタスクの削除対象ではないため、grepの結果から除外している)。

- [ ] **Step 3: importが成功することを確認する**

Run:
```bash
cd /home/httpd/Neurobeet/word_haku_api && source .venv/bin/activate && python -c "from word_haku_api.main import app; print('OK')"
```
Expected: `OK` とだけ出力され、例外が出ないこと。

- [ ] **Step 4: 変更内容を確認する(git操作は行わない)**

Run: `git status` で該当ファイル・フォルダが deleted になっていることを目視確認するのみ。add/commit は行わない。

---

## Task 5: 最終動作確認

**Files:** なし(確認のみ)

**Interfaces:**
- Consumes: Task 1〜4で完成した全体
- Produces: なし

- [ ] **Step 1: サーバーをバックグラウンドで起動する**

Run:
```bash
cd /home/httpd/Neurobeet/word_haku_api && source .venv/bin/activate && nohup python -m uvicorn word_haku_api.main:app --host 127.0.0.1 --port 8010 > /tmp/word_haku_api_smoketest.log 2>&1 &
sleep 3
cat /tmp/word_haku_api_smoketest.log
```
Expected: ログにエラー(traceback)が出力されていないこと。ポートは既存のバックエンドプロセスと衝突しないよう `8010` を使う(既に何かが `8010` を使っている場合は `ss -ltnp | grep 8010` で確認し、空いている別のポート番号に読み替えて実施する)。

- [ ] **Step 2: 残す3系統のエンドポイントが応答することを確認する**

Run:
```bash
curl -s -o /dev/null -w "GET /eeg_emotion/status -> %{http_code}\n" http://127.0.0.1:8010/eeg_emotion/status
curl -s -o /dev/null -w "GET /experiment/latest -> %{http_code}\n" http://127.0.0.1:8010/experiment/latest
curl -s -o /dev/null -w "GET / -> %{http_code}\n" http://127.0.0.1:8010/
```
Expected: いずれも `200`。(`/music/generate` はPOST専用かつ実際の音楽生成が走り時間がかかるため、ここでは疎通確認のみ行い、GETでの404確認は不要。エンドポイント自体が登録されていることは Task 1〜4 の import 確認で担保されている。)

- [ ] **Step 3: 削除したエンドポイントが404になることを確認する**

Run:
```bash
curl -s -o /dev/null -w "GET /auth/userinfo/ -> %{http_code}\n" http://127.0.0.1:8010/auth/userinfo/
curl -s -o /dev/null -w "GET /infmodels/ -> %{http_code}\n" http://127.0.0.1:8010/infmodels/
curl -s -o /dev/null -w "GET /folders/ -> %{http_code}\n" http://127.0.0.1:8010/folders/
```
Expected: いずれも `404`。

- [ ] **Step 4: サーバーを停止する**

Run:
```bash
pkill -f "uvicorn word_haku_api.main:app --host 127.0.0.1 --port 8010"
ss -ltnp | grep 8010 || echo "port 8010 released"
```
Expected: `port 8010 released` と表示されること(プロセスが残っていないこと)。

- [ ] **Step 5: 最終的な差分の一覧を確認する**

Run: `git status`
Expected: Task 1〜4 で意図した変更・削除のみが表示されること。add/commit はコントローラーセッション側(graduation_research)で行うため、このタスクからは実行しない。
