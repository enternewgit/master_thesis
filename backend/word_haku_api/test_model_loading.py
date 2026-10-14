import torch
import numpy as np
from music_ai.emotion_model import EmotionModel  # 更新したファイルをインポート

def smoke_test():
    print("--- Starting Smoke Test ---")
    
    # 1. ダミーデータの作成 (バッチサイズ1, 4チャンネル, 100サンプル)
    # 論文のウィンドウサイズ(0.5秒 = 100サンプル)に合わせる
    dummy_input = np.random.randn(1, 4, 100).astype(np.float32)
    
    try:
        # 2. モデルの初期化 (パスは実際の環境に合わせてください)
        # 引数は無視される仕様になったので、適当なパスでOKですが、
        # 実際の .pth と .joblib ファイルが所定のフォルダにあるか確認してください
        model = EmotionModel(
            valence_path="dummy_v.pth", 
            arousal_path="dummy_a.pth",
        )
        print("[OK] Model initialized and files loaded.")
        
        # 3. 推論の実行
        val, aro = model.predict(dummy_input)
        
        print(f"[OK] Prediction successful.")
        print(f"   - Valence Score: {val:.4f}")
        print(f"   - Arousal Score: {aro:.4f}")
        
        # 4. 値の範囲チェック
        if 0.0 <= val <= 1.0 and 0.0 <= aro <= 1.0:
            print("[OK] Scores are within valid range (0-1).")
        else:
            print("[WARNING] Scores are out of range!")

    except Exception as e:
        print(f"[FAIL] An error occurred: {e}")
        # よくあるエラー: ファイルパスが見つからない、joblibのバージョン不整合など

if __name__ == "__main__":
    smoke_test()