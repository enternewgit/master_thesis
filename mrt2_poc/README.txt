Magenta RealTime 2 (MRT2) 検証環境 README
==========================================

このディレクトリは、word_haku_api の音楽生成AI（現行: Stable Audio Open）を
Google Magenta RealTime 2 (MRT2) に差し替えられるか検証するための、独立した
PoC用venvです。word_haku_api の本体venv（torch/CUDA）とは意図的に完全分離
しています。


1. 背景・目的
-------------
- 本家リポジトリ: https://github.com/magenta/magenta-realtime
- MRT2はJAX(Linux/NVIDIA GPU)またはMLX(Apple Silicon)で動く音楽生成モデル。
  「リアルタイムストリーミング」はApple Silicon専用で、Linux上ではJAXバック
  エンドによる「オフライン/バッチ生成」のみサポート対象。
- word_haku_apiは torch ベース(Stable Audio Open / EEG感情モデル)のため、
  同一プロセス・同一venvでJAXを混在させると、GPUメモリの競合や依存関係の
  衝突が起きるリスクがある。そのため本検証は別venv・別プロセス(サブプロセス
  呼び出し)を前提に行った。


2. 実行環境
-----------
- OS: WSL2 (Linux 6.18 microsoft-standard-WSL2)
- GPU: NVIDIA GeForce RTX 3060 Ti (VRAM 8192MiB)
- ドライバ: NVIDIA 560.94 / CUDA Version 12.6 (nvidia-smi表示)
  → 公式ドキュメントは jax[cuda13] を推奨しているが、このドライバでは
    cuda13 wheelの要件を満たさない可能性が高いため jax[cuda12] を使用した。
- Python: 3.12 (uv管理)


3. セットアップ手順
-------------------
    cd mrt2_poc
    uv venv --python 3.12
    uv pip install "magenta-rt" "jax[cuda12]"

    # 共有リソース(MusicCoCa / SpectroStream)のダウンロード
    .venv/bin/mrt models init

    # ストリーミングモデル本体のダウンロード(まずは小さいmrt2_smallを推奨)
    # models/<name>/ に MLX形式 + _state.safetensors を保存する。JAXバック
    # エンド(server.py が使う MagentaRT2Jax)はこれを読まない。
    .venv/bin/mrt models download mrt2_small

    # JAXバックエンドが実際に読む checkpoints/ ディレクトリは別コマンドで
    # 取得する必要がある(旧版のこのREADMEには記載がなく、Docker化作業
    # (6.5節)でハマって判明した)。これを忘れると
    # "FileNotFoundError: .../checkpoints/mrt2_small.safetensors" で起動
    # 時に落ちる。
    .venv/bin/mrt checkpoints download mrt2_small.safetensors

  モデル資産は ~/Documents/Magenta/magenta-rt-v2/ 以下に保存される
  (venv/プロジェクトディレクトリの外)。


4. 既知の問題と対処
-------------------

(1) セグメンテーションフォールト（最重要・対処必須）
    症状:
      `mrt jax generate` 実行時に、コンパイル中(INFO:magenta_rt.jax.system:
      Compiling...)にセグフォルトで異常終了する。
    原因:
      XLAのGPUオートチューニングが、このWSL2 + 8GB VRAM環境で大きなメモリ
      確保を行おうとしてクラッシュする。
    対処:
      以下の環境変数を必ず設定してから実行する。

        export XLA_PYTHON_CLIENT_PREALLOCATE=false
        export XLA_FLAGS="--xla_gpu_autotune_level=0"

(2) LD_LIBRARY_PATH 汚染によるCUDAライブラリバージョン不整合（未解消・恒久対処不可、起動時に毎回回避が必要）
    症状:
      ~/.bashrc の以下の行により、システムのCUDA 12.8がLD_LIBRARY_PATHに
      グローバルにexportされている(2026-07-06時点でも解消されていないことを確認済み):

        export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}

      このvenvはpipで新しめのCUDAライブラリ(nvidia-cusparse-cu12 /
      nvidia-nvjitlink-cu12==12.9.86 等)をvenv内に持っているが、
      LD_LIBRARY_PATH経由でシステムの古いCUDA 12.8(libnvJitLink.so.12.8.93)
      が先に解決されてしまう。cuSPARSEは `__nvJitLinkGetErrorLogSize_12_9`
      というシンボルを要求するが、システム版の12.8にはこのシンボルが無い。
      その結果、以下の2通りの壊れ方をする:
        (a) cuDNNバージョン不整合 → `CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH`
            エラーでセグフォルト
        (b) cuSPARSE/nvJitLinkのシンボル不整合 → エラーにはならず、
            JAXが黙ってCPUバックエンドにフォールバックする(GPUが刺さって
            いるのに `jax.devices()` が `[CpuDevice(id=0)]` を返す。
            ログには `Unable to load cuSPARSE` 等のWARNING/ERRORが出る)。
    対処:
      ~/.bashrc 側の恒久修正は行っていない(他プロジェクト
      ( ~/practice/MagentaRealTime2/mrt2-next )が同じ変数に依存しており、
      迂闊に削除すると壊れるため)。このvenvでJAX/GPUを使うプロセスを
      起動する際は、必ず `env -u LD_LIBRARY_PATH` を前置してシステムの
      LD_LIBRARY_PATHを外し、venv同梱ライブラリのRPATH解決に任せること
      (6節(0)、9節のコマンド例を参照)。これを忘れるとエラーなくCPUに
      フォールバックするため気づきにくい。起動後は必ずログか
      `jax.devices()` の出力でGPU(`CudaDevice`)が使われているか確認する。

(3) mrt2_base はおそらくVRAM不足
    mrt2_small (230M) 実測ピークVRAM が約3.1GBだったのに対し、mrt2_base は
    パラメータ数が約10倍(2.4B)。8GB VRAMのこのマシンでは収まらない可能性が
    高く、未検証。試す場合はOOM/クラッシュの可能性を踏まえること。


5. 動作確認済みの性能 (mrt2_small, JAXバックエンド)
---------------------------------------------------
    実行コマンド例:
      XLA_PYTHON_CLIENT_PREALLOCATE=false \
      XLA_FLAGS="--xla_gpu_autotune_level=0" \
      .venv/bin/mrt jax generate --prompt "disco funk" --duration 4.0 --model=mrt2_small

    結果:
      - 生成速度: 26〜27.2 steps/s (リアルタイム基準 25 steps/s を上回る)
      - 初回コンパイル時間: 16〜19秒 (2回目以降のコンパイルキャッシュ次第で短縮の余地あり)
      - ピークVRAM使用量: 約3.1GB (8GB中、十分な余裕あり)
      - 出力: 48kHz / ステレオ / 16bit PCM WAV
      - 出力先(固定パス): ~/Documents/Magenta/magenta-rt-v2/outputs/output_audio_jax_<model名>.wav
        ※ --output のようなパス指定オプションはCLIに無く、モデル名ごとの固定ファイル名で
          常に上書きされる。


6. word_haku_api との連携
-------------------------
word_haku_api 側には、この検証結果を踏まえて provider="mrt2" を追加済み。

  当初は `mrt` CLIをリクエストのたびにサブプロセスとして起動する方式だったが、
  これだとJAXのJITコンパイル(~15〜20秒)を毎回払い直すことになり、
  4秒の音声生成でも30秒以上かかっていた。現在は mrt2_poc/server.py という
  常駐HTTPサーバーに切り替え、コンパイルを起動時の1回だけに抑えている。

  (0) MRT2常駐サーバーの起動(word_haku_apiを使う前に毎回必要)

      cd mrt2_poc
      env -u LD_LIBRARY_PATH \
        XLA_PYTHON_CLIENT_PREALLOCATE=false \
        XLA_FLAGS="--xla_gpu_autotune_level=0" \
        .venv/bin/python server.py --model mrt2_small --port 8799

      起動には ~20秒(JITコンパイル)かかる。ログに
      "MRT2 model ready and warmed up." と
      "MRT2 server listening on http://127.0.0.1:8799" が出れば準備完了。
      ヘルスチェック: curl http://127.0.0.1:8799/health

      実測: 4秒生成が約4秒、12秒生成が約9.5秒(コンパイル待ちなし)。
      Stable Audio Openサーバー(下記)が既にGPUに常駐している場合でも、
      release_gpu_memory()経由の退避処理により正常に動作する(後述)。

  (0.5) Stable Audio Open常駐サーバーの起動(2026-07-06改修: word_haku_api本体
        プロセスから分離。以前はFastAPIのstartupイベントでモデルを
        preload_model()していたため、~5-6GBの重みがauth/eeg/experiment等
        全ルートと同一プロセスに乗ってしまい、Stable Audio Openだけを
        止めることができなかった。MRT2と同じ「別プロセス+常駐HTTPサーバー」
        方式に揃え、それぞれ独立に起動・停止できるようにした)

      cd backend
      .venv/bin/python -m word_haku_api.music_ai.stableaudio_server --port 8798

      起動には初回ロードで~20秒程度かかる。ログに
      "Stable Audio Open model ready." と
      "Stable Audio Open server listening on http://127.0.0.1:8798" が
      出れば準備完了。ヘルスチェック: curl http://127.0.0.1:8798/health
      word_haku_api本体(main.py)はこのサーバーの起動有無に関わらず
      問題なく起動する(未起動の場合、provider="stable"のリクエスト時のみ
      分かりやすいエラーを返す)。

  - backend/word_haku_api/music_ai/generate_mrt2_local.py
    backend/word_haku_api/music_ai/generate_stableaudio_local.py
      それぞれの常駐サーバーにHTTPでリクエストするだけの薄いクライアント。
      サーバーに接続できない場合は、起動コマンドを含む分かりやすいエラーを
      返す。同時リクエストは各ファイル内のロックで直列化される。

  (0.7) MRT2のstate継続(なめらかな遷移)

      magenta_rtの MagentaRT2Jax.generate() は state引数でストリーミング
      stateを前回呼び出しから引き継げる(styleだけ変えてstateは継続、という
      使い方が可能)。mrt2_poc/server.py はこれを使い、モジュールグローバル
      の _state を呼び出しごとに更新・再利用する:

        POST /generate に {"reset": true} を渡すと新規シーケンスから開始、
        省略時(デフォルトfalse)は前回のstateを引き継いで生成する。
        レスポンスヘッダ X-State-Continued: true/false で実際に継続した
        かどうかを確認できる。
        POST /reset は生成せずにstateだけクリアする(新しいフィードバック
        セッションの開始時に呼ぶ)。

      generate_mrt2_local.py 側は generate_local(..., reset=bool) と
      reset_session() で対応。route_experiment.py は
      EXPERIMENT_STATE["seed"] が None かどうかをセッション境界として使い、
      セッション最初の生成だけ reset=True を渡す。/experiment/stop で
      reset_session() を呼ぶ(MRT2サーバー未起動時はベストエフォートで
      無視)。

      注意: prefetch_worker (route_experiment.py) は投機的に次の生成を
      先読みする仕組みだが、mrt2はサーバー側で状態を共有するため、
      投機的な呼び出しが実際に使われるかどうかに関わらずstateを進めてしまう。
      そのため provider="mrt2" の場合は prefetch_worker 側でスキップする
      よう実装している(stable audioは元々ステートレスなので影響なし)。

  - backend/word_haku_api/music_ai/stableaudio_server.py
      Stable Audio Openを常駐ロードし、POST /generate ・ POST /evict ・
      GET /health を提供するサーバー本体(mrt2_poc/server.pyと対の構成)。
      /evict は、キャッシュ済みモデルをCPUへ退避しtorch.cuda.empty_cache()
      でVRAMを解放する(8GBカードでは両モデル同時常駐が不可能なため)。
      次に/generateが呼ばれた際は自動的にGPUへ戻る。
      generate_mrt2_local.pyはmrt2呼び出し前にこのエンドポイントを叩く。

  - backend/word_haku_api/music_ai/generator.py
      generate() / generate_async() に provider="mrt2" を追加済み。
      呼び出し例:
        POST /music/generate
        { "prompt": "ambient pads with sub bass", "provider": "mrt2", "duration": 4 }

  設定可能な環境変数(word_haku_api側):
    MRT2_SERVER_URL          : MRT2常駐サーバーのURL
                               既定: http://127.0.0.1:8799
    MRT2_LOCAL_MODEL         : 使用モデル名 (既定: mrt2_small)
                               ※ サーバー起動時の --model と一致させること。
                                 不一致の場合はサーバーが400エラーを返す。
    MRT2_SERVER_KEY          : MRT2常駐サーバーへの共有シークレット(任意)。
                               サーバー起動時にも同名の環境変数として設定する
                               こと(サーバー側・クライアント側で値を揃える)。
                               未設定の場合、サーバーは認証なしで応答する
                               (127.0.0.1限定のローカル利用のみ許容)。
                               サーバーをネットワーク越しに公開する場合
                               (例: 6.6節のRunPodデプロイ)は必ず設定する
                               こと。RunPodはPod自体が公開URL(HTTPSプロキシ)
                               を発行してくれるため、Tailscale等のVPNは不要。
    STABLE_AUDIO_SERVER_URL  : Stable Audio Open常駐サーバーのURL
                               既定: http://127.0.0.1:8798
    STABLE_LOCAL_MODEL       : 使用モデル名
                               (既定: stabilityai/stable-audio-open-1.0)
    STABLE_AUDIO_SERVER_KEY  : Stable Audio Open常駐サーバーへの共有シークレット
                               (任意)。MRT2_SERVER_KEYと同様、サーバー・
                               クライアント双方に同じ値を設定する。

  いずれのサーバーも duration は最大120秒までしか受け付けない
  (超過時は400エラー)。


6.5. Docker化(環境依存性の解消)
-------------------------------
4節(1)(2)のセグフォルト/LD_LIBRARY_PATH問題は、ホストの~/.bashrcやシステム
CUDAとvenv内CUDAライブラリの衝突が原因。Dockerコンテナ化すればホスト環境を
一切継承しないため、この種の問題が構造的に発生しなくなる。加えて、研究室PC
とRunPod等のクラウドGPUの両方で同じイメージを使い回せる(環境差分の心配が
なくなる)。

  ビルド:
    cd mrt2_poc
    docker build -t mrt2-server .

  実行(モデルキャッシュを永続化するボリュームを指定):
    docker run --rm --gpus all \
      -p 8799:8799 \
      -v mrt2-models:/root/Documents/Magenta/magenta-rt-v2 \
      -e MRT2_SERVER_KEY=<ネットワーク越し公開時のみ設定> \
      mrt2-server

    初回起動時はモデルダウンロード(数GB)が走るため時間がかかる。2回目以降は
    ボリュームにキャッシュが残っているためスキップされる。

  ヘルスチェック:
    curl http://127.0.0.1:8799/health
    → {"status": "ok", "model": "mrt2_small", "device_platform": "gpu",
       "device_kind": "...", "gpu_ready": true} となっていることを確認。
       gpu_ready が false の場合、コンテナ内でCPUフォールバックしている
       (--gpus all の指定漏れ、ホスト側nvidia-container-toolkit未設定などを
       疑う)。

  前提:
    - ホスト側にNVIDIA Container Toolkitがインストール・設定済みであること
      (`docker info` の Runtimes に `nvidia` が含まれているか確認)。
    - イメージ自体にはCUDA toolkitを含めていない(jax[cuda12]のpipホイールが
      CUDA/cuDNN等のランタイムライブラリを同梱しているため)。ベースイメージ
      をnvidia/cuda系に変更する場合、LD_LIBRARY_PATHの二重定義で4節(2)と
      同じ問題を再現しないよう注意すること。

  実機検証済み(2026-08-19、研究室PC/WSL2/RTX 3060 Ti):
    - docker build → docker run --gpus all → /health(gpu_ready: true,
      device_kind: "NVIDIA GeForce RTX 3060 Ti") → /generate(state継続
      込み、X-State-Continued: true/false) → /reset まで、モデルの
      初回ダウンロードから含めてフルパスで動作確認済み。
      env -u LD_LIBRARY_PATH のようなおまじないは一切不要だった。

  検証中に見つけたバグ2件(修正済み):
    (a) docker-entrypoint.shの初期実装は「モデルキャッシュ用ディレクトリの
        存在」でダウンロード要否を判定していたが、`docker run -v
        <name>:/path` は名前付きボリュームを初回マウントする際に空の
        ディレクトリを自動作成するため、この判定は常にtrueになり、
        一度もダウンロードされずにサーバーが
        `FileNotFoundError: .../checkpoints/mrt2_small.safetensors`
        で落ちていた。チェックポイントファイル自体の存在チェックに修正済み。
    (b) `mrt models download` だけでは checkpoints/ ディレクトリが作られず
        (3節参照)、これもentrypoint未対応で同じFileNotFoundErrorを引いて
        いた。`mrt checkpoints download <model>.safetensors` の呼び出しを
        entrypointに追加済み。

  既知の未検証事項:
    - mrt2_base等、mrt2_small以外のモデルへの切り替えはentrypoint側で
      素朴なチェックポイントファイル存在チェックしかしておらず、モデルを
      切り替えた場合に正しく検出できない可能性がある
      (docker-entrypoint.sh参照)。
    - RunPod上でのGPUパススルー込みの動作確認はまだ行っていない
      (6.6節参照、Pod未デプロイ)。研究室PC実機では確認済みなので、大きな
      問題は出ない見込みだが未確認。


6.6. RunPodへのデプロイ(学会デモ用Plan B)
-------------------------------------------
学会デモ当日にこのマシン(研究室PC)を会場に持ち込めないため、MRT2サーバー
だけをクラウドGPUで動かし、会場のノートPC(フロントエンド word-haku +
バックエンド word_haku_api)からネットワーク越しに叩く構成。

  構成のポイント:
    - 会場で動かすのはノートPC上の word-haku(フロント)と word_haku_api
      (バックエンド)のみ。EEGMambaの感情推定は軽量なのでノートPCのCPUで
      動く。重いのは音楽生成(MRT2)だけなので、そこだけ切り出して外部に
      置く。
    - バックエンドの MRT2_SERVER_URL 環境変数をRunPodの公開URLに向ける
      だけでよい。Tailscale等のVPNは不要(RunPodのPodがHTTPSプロキシURL
      を自動発行するため)。

  イメージ:
    Docker Hubにpush済み: enternewdocker/mrt2-server:latest
    (6.5節のDockerfileをそのままビルド・push。:latestタグのままだが、
    本番運用するならバージョンタグに固定した方が安全)

  RunPod Pod設定(2026-08-19時点でテンプレート準備済み、デプロイは未実行):
    - Container Image: enternewdocker/mrt2-server:latest
    - GPU: RTX A5000(24GB VRAM, $0.27/hr)を選択。mrt2_smallの実測ピーク
      VRAMは約3.1GBなので大きく余裕がある。RTX A4000($0.25/hr, 16GB)は
      在庫切れで選べなかったため、在庫が多い(表示上「最大10個」)A5000に
      変更した。他の候補: RTX A4500($0.25/hr, 20GB)。
      B200/H200/H100等の高価なGPUは今回のワークロードには完全に
      オーバースペックなので選ばないこと。
    - Container Disk: 30GB
    - Volume Disk: 50GB、マウント先を /root/Documents/Magenta/magenta-rt-v2
      に変更(デフォルトの /workspace のままだとentrypointが期待する
      モデル保存先と食い違うため必須)。
    - Exposed HTTP Ports: 8799(デフォルトの8888から変更)
    - 環境変数: MRT2_SERVER_KEY を設定(ネットワーク越し公開のため必須。
      デプロイ前に値を変更すること — 準備作業中にチャットに残った値は
      使い回さない)
    - 「Deploy a Pod」の画面はRunPod: Serverlessではなく Pods を使うこと。
      Serverlessはコールドスタート前提でジョブキューAPIが必要になり、
      このサーバーの常駐設計・素のHTTP API(/health, /generate, /reset)
      とは合わない。

  デプロイ手順(次回の作業):
    1. RunPodアカウントの残高をチャージ(未チャージだとGPU起動不可)
    2. GPU選択が「Instance not available」になっていないか確認してから
      デプロイ
    3. Pod起動後、詳細画面の公開URL(https://<pod-id>-8799.proxy.runpod.net
      のような形式)を確認
    4. curl <公開URL>/health で gpu_ready: true を確認
    5. curl -X POST <公開URL>/generate で音声が返ってくるか、複数回叩いて
      X-State-Continued が期待通りtrue/falseになるか確認(6節(0.7)参照)
    6. word_haku_api側の .env で MRT2_SERVER_URL=<公開URL>,
      MRT2_SERVER_KEY=<設定した値> を指定して実際に /experiment/feedback
      経由での生成まで確認
    7. 確認が終わったら、使わない間は必ずPodを停止/削除する(起動中は
      ミリ秒単位で課金され続ける)


7. 既知の制約・今後の課題
-------------------------
- mrt2_base は未検証(VRAM不足の可能性)。常駐サーバーはモデルを1つしか
  ロードしないため、mrt2_base を使うには別ポートでサーバーをもう1つ
  起動する(--model mrt2_base --port <別番号>)か、既存サーバーを止めて
  --model mrt2_base で起動し直す必要がある。
- 同時に複数リクエストが来るとサーバー内部ロックで直列化され、レイテンシが
  積み上がる(Stable Audio Openのローカル生成と同じ制約)。
- word_haku_api・MRT2常駐サーバーのどちらも、このマシン固有のパス/ポートが
  デフォルト値になっている箇所があるので、本番運用するなら環境変数で明示的に
  指定する運用にすること(6節参照)。
- プロンプトは MusicCoCa(スタイル埋め込みモデル)経由で解釈されるため、
  Stable Audio Openほど詳細な自由文プロンプトでの制御性は未検証。
- MRT2常駐サーバーはこのPoCの一部であり、systemdやプロセスマネージャ等での
  自動起動・自動再起動は未設定。手動で起動しておく必要がある(8節参照)。


8. プロダクト本体(Braingram / word_haku_api + word-haku)の立ち上げ方
----------------------------------------------------------------------
このディレクトリ(mrt2_poc)はMRT2差し替え検証用のPoCであり、実際に運用する
プロダクトの本体は下記の2つ。

  バックエンド: ~/graduation_research/backend  (FastAPI, uv管理)
  フロントエンド: ~/graduation_research/frontend (Next.js, "Braingram")

(1) バックエンド起動 (FastAPI, http://localhost:8000)

    cd ~/graduation_research/backend
    uv run uvicorn word_haku_api.main:app --reload --host 0.0.0.0 --port 8000

    前提:
      - backend/.env が設定済みであること
        (EMO_VALENCE_PATH, EMO_AROUSAL_PATH: EEG感情モデルの重みファイルパス
         FRONTEND_URL, CSRF_KEY, JWT_KEY, MONGO_API_KEY 等)
      - MONGO_API_KEY は接続文字列(Atlas等)なので、ローカルにMongoDBを
        別途起動する必要はない。
      - 2026-07-06の改修でStable Audio Openは本体プロセスから分離した
        (6節(0.5)参照)。バックエンド自体はStable Audio Open/MRT2どちらの
        常駐サーバーも起動していなくてもすぐ立ち上がる。
      - Stable Audio Open (provider="stable" / デフォルト) を使う場合は、
        事前に6節(0.5)のStable Audio Open常駐サーバーを別途起動して
        おくこと。起動していないと「Could not reach the Stable Audio
        server ...」エラーになる。
      - MRT2 (provider="mrt2") を使う場合は、事前に6節(0)のMRT2常駐
        サーバーを別途起動しておくこと。起動していないと
        「Could not reach the MRT2 server ...」エラーになる。

(2) フロントエンド起動 (Next.js, http://localhost:3000)

    別ターミナルで:
    cd ~/graduation_research/frontend
    npm install   # 初回のみ
    npm run dev

    ブラウザで http://localhost:3000 を開く。
    frontend/.env の NEXT_PUBLIC_API_URL / NEXT_PUBLIC_WS_PATH が
    http://localhost:8000 / ws://localhost:8000/ai/ws/ を指しているため、
    (1)のバックエンドを先に起動しておくこと。

(3) 起動順序のまとめ
    1. (必要なら) backend/.env の内容を確認
    2. (Stable Audio Openを使うなら) Stable Audio Open常駐サーバー起動
       (6節(0.5)、8798番、~20秒)
    3. (MRT2を使うなら) MRT2常駐サーバー起動(6節(0)、8799番、~20秒)
    4. バックエンド起動 (8000番)
    5. フロントエンド起動 (3000番)
    6. ブラウザで http://localhost:3000 を開いて動作確認

    ※ (2)(3)はどちらか片方だけ、両方、あるいはどちらも起動せずに
      バックエンドだけ動かす、という運用も可能(それぞれ独立プロセス
      なので、使わない方はメモリ節約のため起動しなくてよい)。


9. (参考) MRT2単体の対話的動作確認用PoC
------------------------------------------
上記プロダクト本体とは別に、MRT2をブラウザから直接試すための独立した
PoCが ~/practice/MagentaRealTime2/mrt2-next/ に存在する
(Next.jsフロントエンド + Python WebSocketバックエンド構成)。
word_haku_api本体には組み込まれておらず、あくまでMRT2単体の音の確認用。

  バックエンド (WebSocket, ws://0.0.0.0:8765):
    cd ~/practice/MagentaRealTime2/mrt2-next
    env -u LD_LIBRARY_PATH \
      XLA_PYTHON_CLIENT_PREALLOCATE=false \
      XLA_FLAGS="--xla_gpu_autotune_level=0" \
      .venv/bin/python app.py
    ※ MRT2のロードに失敗すると自動でMOCK_MODE(ダミー音)にフォールバック
      するため、起動ログで "Mode: MRT2 LIVE" か "Mode: MOCK" かを確認。

  フロントエンド (http://localhost:3000):
    cd ~/practice/MagentaRealTime2/mrt2-next
    npm install   # 初回のみ
    npm run dev
    画面のWebSocket URL既定値は ws://localhost:8765。

  ※ word-haku(本体フロントエンド)もデフォルトで3000番を使うため、
    両方を同時に立ち上げる場合はポートが衝突する。片方を
    `npm run dev -- -p 3001` のように変更すること。
