# word_haku_api を EEG→Music専用APIにする設計

## 背景・目的

`word-haku`（フロントエンド）は先行する作業で、ログイン付きダッシュボード（学習データ収集・モデル管理・推論・Text実験）を廃止し、「EEG測定 → Chart表示 → 脳波に合わせた音楽生成」だけを行う独立アプリに作り変えた（`docs/superpowers/specs/2026-08-25-word-haku-eeg-music-lab-design.md` 参照）。

このバックエンドである `word_haku_api` は現在も15個のFastAPI routerを持つ大きなAPIサーバーのままだが、フロントエンドの削減に伴い実際に呼ばれているエンドポイントは以下の3系統だけになっている。

- `GET /eeg_emotion/status`, `POST /eeg_emotion/predict`（`Music/Player.tsx`）
- `POST /music/generate`（`Music/Player.tsx`）
- `POST /experiment/feedback`, `GET /experiment/latest`, `POST /experiment/stop`（`Music/ExperimentPlayer.tsx`）

本設計では、`word_haku_api` をこの3系統のみを提供する最小構成に作り変える。

## 依存関係の調査結果

`route_eeg_emotion.py` / `route_music.py` / `route_experiment.py` の3ファイルの import を確認したところ、この3つは `music_ai/` 配下のモジュール（`loader`, `infer`, `eeg_preprocess`, `generator`, `generate_stableaudio_local`, `generate_mrt2_local`, `stableaudio_server`）にのみ依存しており、以下には一切依存していないことを確認した。

- 認証（`auth_utils.py`, JWT/Cookie関連）
- データベース（`database.py`, `databasev2.py`, MongoDB/motor）
- リクエスト/レスポンスの型定義（`schemas.py`）
- 学習・推論用モデルコード（`routers/eeg2word/`）

逆に、残り12個のrouter（`route_eegs`, `route_eegsv2`, `route_pred`, `route_auth`, `route_users`, `route_OAuth`, `route_ai`, `route_ai_YesNo`, `route_ai_beta`, `route_infmodels`, `route_folders`, `route_admin`）は、上記の認証・DB・`schemas.py`・`routers/eeg2word/` のいずれか（または複数）に依存しており、これらのrouterを全て削除すれば、依存先も完全に不要になる。

また、以下は今回のフロントエンド削減とは無関係に、**既に**どこからも参照されていない孤立コードであることを確認した。

- `word_haku_api/ai/eeg_emotion.py` — リポジトリ全体を検索して参照ゼロ
- `music_ai/generate_music.py` — Hugging Face MusicGen APIを叩く旧実装。参照ゼロ（`generator.py`が代わりに使われている）
- `music_ai/generate_stableaudio.py` — Stable Audio のHosted API版の旧実装。参照ゼロ（`generate_stableaudio_local.py`に置き換え済み）

## 残すもの

- `word_haku_api/main.py`（大幅簡素化。後述）
- `word_haku_api/routers/route_eeg_emotion.py`
- `word_haku_api/routers/route_music.py`
- `word_haku_api/routers/route_experiment.py`
- `word_haku_api/music_ai/`（`generate_music.py` と `generate_stableaudio.py` の2ファイルを除く：`__init__.py`, `eeg_preprocess.py`, `emotion_model.py`, `generate_mrt2_local.py`, `generate_stableaudio_local.py`, `generator.py`, `infer.py`, `loader.py`, `stableaudio_server.py`）
- `word_haku_api/test_model_loading.py`（`music_ai.emotion_model` の手動スモークテストスクリプト。残す `music_ai` に対応するコードなので維持）
- `stable-audio-tools-v2/`（`music_ai/stableaudio_server.py` と `route_experiment.py` が直接依存する、音楽生成に必須のベンダリング済みパッケージ）
- `tests/`（中身は空の `__init__.py` のみで実害がないため、削除必須とはしない）

## 削除するもの

- `word_haku_api/routers/route_eegs.py`
- `word_haku_api/routers/route_eegsv2.py`
- `word_haku_api/routers/route_pred.py`
- `word_haku_api/routers/route_auth.py`
- `word_haku_api/routers/route_users.py`
- `word_haku_api/routers/route_OAuth.py`
- `word_haku_api/routers/route_ai.py`
- `word_haku_api/routers/route_ai_YesNo.py`
- `word_haku_api/routers/route_ai_beta.py`
- `word_haku_api/routers/route_infmodels.py`
- `word_haku_api/routers/route_folders.py`
- `word_haku_api/routers/route_admin.py`
- `word_haku_api/routers/eeg2word/`（フォルダ全体。上記routerからのみ参照されていた学習・推論用モデルコード一式）
- `word_haku_api/database.py`
- `word_haku_api/databasev2.py`
- `word_haku_api/auth_utils.py`
- `word_haku_api/schemas.py`
- `word_haku_api/ai/`（フォルダ全体。`eeg_emotion.py` 1ファイルのみで、既に孤立コード）
- `word_haku_api/music_ai/generate_music.py`
- `word_haku_api/music_ai/generate_stableaudio.py`

## `main.py` の変更内容

現在の `main.py` は15個のrouterをinclude し、CSRF保護（`CsrfProtect`, `schemas.CsrfSettings`）を設定している。CSRF保護は削除対象のログイン系routerのためのものであり、残す3つのrouterはいずれも `CsrfProtect` に依存していない（コード上で確認済み）。

変更後は以下のみを残す。

- FastAPIアプリ生成
- CORSミドルウェア（`FRONTEND_URL` を許可、フロントエンドとの通信に必須）
- `route_eeg_emotion`（prefix `/eeg_emotion`）, `route_music`（prefix `/music`）, `route_experiment`（prefix `/experiment`）のinclude
- `route_experiment` の `startup_prefetch_worker`/`stop_prefetch_worker`（`/experiment/feedback` のプリフェッチキャッシュに必須）
- ルートの `GET /`（`Welcome to word-haku-API`）

CSRF関連のimport・設定・例外ハンドラ、および削除するrouterのimport/includeを全て取り除く。`schemas.py` を削除するため、ルートの `GET /` は `response_model=SuccessMsg` を外し、残す3つのrouterと同様に `response_model` を指定しないプレーンな辞書を返す形に変更する(`return {"message": "Welcome to word-haku-API"}` は変えず、型指定だけ外す)。

## 変更しないもの

- `pyproject.toml` の依存関係（`motor`, `pyjwt`, `bcrypt`, `fastapi-csrf-protect`, `braindecode` 等が実質不要になるが、依存関係の削除は別作業とし、今回は対象外とする。フロントエンド側の `package.json` を今回のスコープ外としたのと同じ方針）
- `stable-audio-tools-v2/`, `mrt2_poc/`（このディレクトリの外にある兄弟プロジェクトで、今回の `word_haku_api/` 整理の対象外）
- 残す3つのrouterおよび `music_ai/` 内部のロジック自体（動作を変更しない、削除のみ）

## データフロー

変更なし。フロントエンドの `Music/Player.tsx` / `Music/ExperimentPlayer.tsx` が呼ぶ6エンドポイントの実装・挙動はそのまま維持する。

```
フロントエンド (Music/Player.tsx, Music/ExperimentPlayer.tsx)
  → GET /eeg_emotion/status, POST /eeg_emotion/predict
  → POST /music/generate
  → POST /experiment/feedback, GET /experiment/latest, POST /experiment/stop
    → music_ai/{loader,infer,eeg_preprocess,generator,generate_stableaudio_local,generate_mrt2_local,stableaudio_server}
      → stable-audio-tools-v2 (Stable Audio Open ローカル生成)
      → mrt2_poc 経由の外部サーバー (Magenta RealTime 2、必要な場合)
```

## エラーハンドリング

残す3つのrouter自体のエラーハンドリングは変更しない（既存の `HTTPException` ベースの実装をそのまま使う）。`main.py` からCSRF例外ハンドラを削除するが、これは削除するCSRF保護に対応するものであり、残るrouterには影響しない。

## テスト方針

このリポジトリに自動テストは存在しない（`tests/__init__.py` のみで中身は空）。手動確認は以下の通り。

1. `uvicorn word_haku_api.main:app` （または既存の起動コマンド）でサーバーが起動エラーなく立ち上がることを確認する。
2. `curl` で `GET /eeg_emotion/status` が200を返すことを確認する。
3. `curl` で `GET /experiment/latest` が200（`EXPERIMENT_STATE`のJSON）を返すことを確認する。
4. 削除したrouterのエンドポイント（例: `GET /auth/...`, `GET /infmodels/...`）が404になることを確認する。
5. 可能であればフロントエンド（word-haku, `neurobeet`ブランチ）と組み合わせて、Mockデバイス→Music生成の一連の流れが通ることを確認する。
