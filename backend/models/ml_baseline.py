"""随机森林基线模型：训练、保存与推理。

对应课程技术方向：机器学习回归。用于与 LSTM 深度学习方法做对照，
验证深度学习在 RUL 预测上的增益。
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor

MODEL_DIR = Path(__file__).resolve().parent


def train_rf(
    X: np.ndarray,
    y: np.ndarray,
    n_estimators: int = 200,
    max_depth: int = 20,
    seed: int = 42,
) -> tuple[RandomForestRegressor, dict]:
    """训练随机森林回归模型。"""
    model = RandomForestRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(X, y)
    metrics = {
        "train_rmse": float(np.sqrt(np.mean((model.predict(X) - y) ** 2))),
    }
    return model, metrics


def save_rf(model: RandomForestRegressor, metrics: dict, name: str = "rf_fd001"):
    joblib.dump(model, MODEL_DIR / f"{name}.joblib")
    (MODEL_DIR / f"{name}.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class RfPredictor:
    """加载已训练随机森林模型并执行推理。"""

    def __init__(self, name: str = "rf_fd001"):
        path = MODEL_DIR / f"{name}.joblib"
        if not path.exists():
            raise FileNotFoundError(f"未找到模型 {path}，请先运行 scripts/train.py")
        self.model = joblib.load(path)

    def predict(self, feat: np.ndarray) -> float:
        """feat: 窗口统计特征向量，返回 RUL 预测值。"""
        return max(0.0, round(float(self.model.predict(np.asarray([feat]))[0]), 2))
