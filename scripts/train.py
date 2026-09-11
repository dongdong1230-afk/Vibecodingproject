"""模型训练脚本：训练 LSTM 与随机森林基线，评估测试集指标，保存模型。

运行方式：
    .venv\\Scripts\\python scripts\\train.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.models import feature_engineering as fe  # noqa: E402
from backend.models.lstm_model import train_lstm, save_model  # noqa: E402
from backend.models.ml_baseline import train_rf, save_rf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"


def main():
    # 训练窗口样本（若不存在则先运行 preprocess.py）
    if not (PROC / "train_windows.npz").exists():
        print("未找到训练样本，请先运行 scripts/preprocess.py")
        return

    d = np.load(PROC / "train_windows.npz")
    X_lstm, y_lstm = d["X_lstm"], d["y_lstm"]
    X_rf, y_rf = d["X_rf"], d["y_rf"]

    meta = __import__("json").loads(
        (PROC / "preprocess_meta.json").read_text(encoding="utf-8")
    )
    sensor_cols = meta["sensor_cols"]
    scaler = meta["scaler"]
    window = int(meta["window"])

    # 1. 训练 LSTM
    print("===== 训练 LSTM =====")
    lstm, lstm_metrics = train_lstm(X_lstm, y_lstm, hidden=128, epochs=60, verbose=True)
    save_model(lstm, lstm_metrics, sensor_cols, scaler, window, name="lstm_fd001")
    print(f"LSTM 验证 RMSE: {lstm_metrics['val_rmse']:.2f}")

    # 2. 训练随机森林基线
    print("===== 训练随机森林基线 =====")
    rf, rf_metrics = train_rf(X_rf, y_rf)
    save_rf(rf, rf_metrics, name="rf_fd001")
    print(f"RF 训练 RMSE: {rf_metrics['train_rmse']:.2f}")

    # 3. 测试集评估（C-MAPSS 标准：测试集每台取最后窗口预测）
    t = np.load(PROC / "test_windows.npz")
    X_test_seq, X_test_stat, y_test = t["X_test_seq"], t["X_test_stat"], t["y_test"]

    from backend.models.lstm_model import RulLSTM
    import torch

    torch.manual_seed(0)
    m_meta = __import__("json").loads(
        (ROOT / "backend/models/lstm_fd001.json").read_text(encoding="utf-8")
    )
    model = RulLSTM(
        n_features=X_test_seq.shape[2],
        hidden=int(m_meta["arch"]["hidden"]),
        layers=int(m_meta["arch"]["layers"]),
    )
    model.load_state_dict(torch.load(
        ROOT / "backend/models/lstm_fd001.pt", map_location="cpu"))
    model.eval()
    with torch.no_grad():
        pred_lstm = model(torch.from_numpy(X_test_seq).float()).numpy().ravel()
    pred_lstm = np.clip(pred_lstm, 0, None)

    from backend.models.ml_baseline import RfPredictor

    rf_pred = RfPredictor("rf_fd001").model.predict(X_test_stat)

    rmse_lstm = float(np.sqrt(np.mean((pred_lstm - y_test) ** 2)))
    rmse_rf = float(np.sqrt(np.mean((rf_pred - y_test) ** 2)))
    print(f"测试集 RMSE: LSTM={rmse_lstm:.2f}  RF={rmse_rf:.2f}")

    # 把测试集指标回写进模型元信息
    import json

    meta_path = ROOT / "backend/models/lstm_fd001.json"
    m = json.loads(meta_path.read_text(encoding="utf-8"))
    m["metrics"]["test_rmse"] = rmse_lstm
    m["metrics"]["test_rmse_rf"] = rmse_rf
    meta_path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    print("模型与指标已保存至 backend/models/")


if __name__ == "__main__":
    main()
