# word_haku_api — Prompt template examples

このリポジトリの音楽生成エンドポイントでは、`base_prompt` にテンプレート文字列を渡すことで、内部で計算されたパラメータを埋め込できます。
利用可能なプレースホルダ（mapping）は次のとおりです。

- `current_v`, `current_a`: 現在の平均 Valence/Arousal（小数）
- `next_v`, `next_a`: 計算された Next Goal Valence/Arousal（小数）
- `target_v`, `target_a`: リクエストで与えたターゲット Valence/Arousal（小数）
- `bpm`: 推奨テンポ（整数）
- `dynamics`: 音量／ダイナミクス表現（文字列）
- `key_hint`: キーのヒント（例: "C Major" / "C Minor"）
- `instruments`: 推奨楽器列挙（文字列）
- `texture`: テクスチャ／密度のヒント（文字列）

以下は実験・開発で推奨するテンプレート例です。実験ノートや論文のメソッド記述には、どのテンプレートで生成を行ったかを明示してください。

## 例1: Ehrlich-style Control（実験用・厳密制御）

目的: 数値パラメータ（BPM, Key）と音楽的特徴（Dynamics, Texture）を明示して実験条件を固定する。

```python
# テンプレート例 1: Ehrlich-style Control
base_prompt = (
	"A {dynamics} {texture} piece played by {instruments}. "
	"Key of {key_hint}, Tempo {bpm} BPM. "
	"The music is {next_v}"
)

# 注意: `get_evolution_prompt` により遷移語（例: "Crescendo, Becoming brighter"）は
# 自動的にプロンプト末尾へ付加されます。`base_prompt` に `{evolution}` を含めると
# フォーマットでエラーになりますので含めないでください。

# 生成例:
# "A Fortissimo, Dynamic Dense texture piece played by Cinematic Classical, Chamber Orchestra, Piano, Cello, Strings. Key of C Major, Tempo 140 BPM. The music is Becoming brighter. Crescendo, Becoming brighter"
```

## 例2: Mood-driven with Evolution（デモ・体験用）

目的: ムードと変化（Evolution）を強調し、生成AIの表現力を活かす。

```python
# テンプレート例 2: Mood-driven with Evolution
base_prompt = (
	"Atmosphere: {texture}. Instruments: {instruments}."
)

# 注意: `mood` というプレースホルダは自動的に提供されません。
# 気分を表す語をテンプレートに直接入れたい場合は、`{next_v}` や生成時に付加される
# 遷移語（サーバーログで確認）を参照してください。

# 生成例:
# "Atmosphere: Dense texture. Instruments: Cinematic Classical, Piano, Cello, Strings."
```

## 運用メモ
- テンプレートを固定したら、まず数回生成してプロンプトが数値パラメータ（`bpm` 等）と意味的に矛盾していないか確認してください。
- A/B テストや閾値調整（`get_evolution_prompt` の閾値）は、テンプレートが確定してから実施することを推奨します。

---
（このファイルはテンプレート例を集めたもので、より詳細な記録は論文や実験ノートに残してください。）

