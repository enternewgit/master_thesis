可視化ツール README

目的
- Stable Audio 等で生成した音声ファイルが、意図したプロンプト（Valence, Arousal）に応じて音響特徴を持つかを検証するための可視化ツール。

ファイル構成
- `analysis.py` : 2ファイル比較用（スペクトログラム、波形、基本統計量をCSV出力）
- `batch_viz.py` : 同ディレクトリ内のファイル群を接頭辞でグルーピングし、ペア比較を一括実行

使い方
1) 単一ペア比較
```
python analysis.py --file1 /path/to/out_happy.wav --file2 /path/to/out_sad.wav --label1 "Valence=1.0 (Happy)" --label2 "Valence=0.0 (Sad)" --outdir viz
```

2) バッチ比較（同ディレクトリに `out_happy*.wav` と `out_sad*.wav` がある想定）
```
python batch_viz.py --dir . --prefix1 out_happy --prefix2 out_sad --outdir viz_batch
```

出力
- 各ペアごとにフォルダを作成し、`comparison_spectrogram_waveform.png` と `stats_comparison.csv` を出力します。

論文向けメモ
- `stats_comparison.csv` の `centroid`（スペクトル重心）や `rms`（音響エネルギー）は、Valence/Arousal の変化による傾向を定量的に示す際に便利です。

依存ライブラリ
- `librosa`, `matplotlib`, `numpy`

補足
- ファイル名命名規則: 接頭辞（例: `out_happy`）の後に `_a10`, `_a70` などのサフィックスを付けると、同じサフィックス同士で比較されます。サフィックスが無い場合は `base` として扱われます。
