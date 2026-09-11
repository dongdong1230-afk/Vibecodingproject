"""数据预处理脚本：加载 C-MAPSS 原始数据 → 计算 RUL → 传感器筛选 →
构造滑动窗口样本 → 保存到 data/processed。

运行方式：
    .venv\\Scripts\\python scripts\\preprocess.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.models import feature_engineering as fe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"

TRAIN_STRIDE = 3   # 训练窗口步长（控制训练样本量与存储体积）


def main():
    PROC.mkdir(parents=True, exist_ok=True)

    # 1. 加载训练数据并计算 RUL
    train = fe.load_raw(RAW / "train_FD001.txt")
    train = fe.compute_rul(train)
    print(f"训练数据: {len(train)} 条, {train['unit'].nunique()} 台发动机")

    # 2. 传感器筛选
    sensor_cols = fe.select_sensors(train, threshold=fe.CORR_THRESHOLD)
    print(f"筛选出传感器 {len(sensor_cols)} 个: {sensor_cols}")

    # 3. 训练序列窗口与统计特征（LSTM / RF 输入）
    X_lstm, y_lstm, scaler = fe.make_sequence_windows(
        train, sensor_cols, window=fe.DEFAULT_WINDOW, stride=TRAIN_STRIDE
    )
    X_rf, y_rf = fe.make_stat_features(
        train, sensor_cols, window=fe.DEFAULT_WINDOW, stride=TRAIN_STRIDE
    )
    print(f"LSTM 训练样本: {X_lstm.shape}, RF 训练样本: {X_rf.shape}")

    np.savez_compressed(
        PROC / "train_windows.npz",
        X_lstm=X_lstm, y_lstm=y_lstm, X_rf=X_rf, y_rf=y_rf,
    )

    # 4. 测试数据：每台取最后 window 个循环作为推理样本，标签来自 RUL_FD001.txt
    test = fe.load_raw(RAW / "test_FD001.txt")
    rul_labels = np.loadtxt(RAW / "RUL_FD001.txt")
    X_test_seq, X_test_stat, unit_ids = [], [], []
    for i, (_, grp) in enumerate(test.groupby("unit", sort=False)):
        seq = fe.last_window_for_unit(grp, sensor_cols, scaler, fe.DEFAULT_WINDOW)
        X_test_seq.append(seq)
        last = grp.iloc[-fe.DEFAULT_WINDOW:].copy()
        feat = []
        for c in sensor_cols:
            lo, hi = scaler[c]
            denom = hi - lo if hi > lo else 1.0
            col = (last[c].to_numpy(dtype=float) - lo) / denom
            slope = np.polyfit(np.arange(len(col)), col, 1)[0]
            feat.extend([col[-1], col.mean(), col.std(), slope])
        X_test_stat.append(feat)
        unit_ids.append(int(grp["unit"].iloc[0]))
    X_test_seq = np.asarray(X_test_seq, dtype=np.float32)
    X_test_stat = np.asarray(X_test_stat, dtype=np.float32)
    np.savez_compressed(
        PROC / "test_windows.npz",
        X_test_seq=X_test_seq, X_test_stat=X_test_stat,
        y_test=rul_labels.astype(np.float32), unit_ids=np.asarray(unit_ids),
    )
    print(f"测试推理样本: {X_test_seq.shape}")

    # 5. 保存预处理元信息
    meta = {
        "sensor_cols": sensor_cols,
        "scaler": scaler,
        "window": fe.DEFAULT_WINDOW,
        "rul_cap": fe.RUL_CAP,
        "train_stride": TRAIN_STRIDE,
        "n_train": int(len(train)),
        "n_test_units": int(len(X_test_seq)),
    }
    (PROC / "preprocess_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("预处理完成，产物已保存至 data/processed/")


if __name__ == "__main__":
    main()
