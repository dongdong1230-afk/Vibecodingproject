"""LSTM 剩余寿命预测模型：网络定义、训练、保存与推理。

对应课程技术方向：深度学习（循环神经网络 LSTM）。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

MODEL_DIR = Path(__file__).resolve().parent


class RulLSTM(nn.Module):
    """输入 (batch, window, n_sensor) 的 LSTM 回归网络。"""

    def __init__(self, n_features: int, hidden: int = 64, layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features,
            hidden_size=hidden,
            num_layers=layers,
            batch_first=True,
            dropout=dropout if layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)  # (B, W, hidden)
        out = out[:, -1, :]  # 取最后一个时间步
        return self.head(out).squeeze(-1)


def train_lstm(
    X: np.ndarray,
    y: np.ndarray,
    hidden: int = 64,
    layers: int = 2,
    epochs: int = 30,
    batch_size: int = 128,
    lr: float = 1e-3,
    val_ratio: float = 0.15,
    seed: int = 42,
    verbose: bool = True,
) -> tuple[RulLSTM, dict]:
    """训练 LSTM 模型，返回 (模型, 指标)。"""
    torch.manual_seed(seed)
    np.random.seed(seed)

    X = torch.from_numpy(X).float()
    y = torch.from_numpy(y).float()
    n = len(X)
    n_val = max(1, int(n * val_ratio))
    perm = torch.randperm(n)
    X_tr, y_tr = X[perm[n_val:]], y[perm[n_val:]]
    X_va, y_va = X[perm[:n_val]], y[perm[:n_val]]

    model = RulLSTM(n_features=X.shape[2], hidden=hidden, layers=layers)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    best_va, best_state = float("inf"), None
    for epoch in range(1, epochs + 1):
        model.train()
        order = torch.randperm(len(X_tr))
        total_loss = 0.0
        for i in range(0, len(X_tr), batch_size):
            idx = order[i : i + batch_size]
            opt.zero_grad()
            pred = model(X_tr[idx])
            loss = loss_fn(pred, y_tr[idx])
            loss.backward()
            opt.step()
            total_loss += loss.item() * len(idx)
        tr_loss = total_loss / len(X_tr)

        model.eval()
        with torch.no_grad():
            va_loss = loss_fn(model(X_va), y_va).item()
        if va_loss < best_va:
            best_va = va_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        if verbose and (epoch % 5 == 0 or epoch == 1):
            print(f"epoch {epoch:02d}  train_mse={tr_loss:.4f}  val_mse={va_loss:.4f}")

    model.load_state_dict(best_state)
    metrics = {
        "val_mse": float(best_va),
        "val_rmse": float(np.sqrt(best_va)),
        "epochs": epochs,
        "hidden": hidden,
        "layers": layers,
    }
    return model, metrics


def save_model(
    model: RulLSTM,
    metrics: dict,
    sensor_cols: list[str],
    scaler: dict,
    window: int,
    name: str = "lstm_fd001",
):
    """保存模型权重与配套元信息。"""
    torch.save(model.state_dict(), MODEL_DIR / f"{name}.pt")
    meta = {
        "model": name,
        "arch": {"n_features": len(sensor_cols), "hidden": model.lstm.hidden_size,
                 "layers": model.lstm.num_layers},
        "sensor_cols": sensor_cols,
        "scaler": scaler,
        "window": window,
        "metrics": metrics,
    }
    (MODEL_DIR / f"{name}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class LstmPredictor:
    """加载已训练模型并执行推理。"""

    def __init__(self, name: str = "lstm_fd001"):
        meta_path = MODEL_DIR / f"{name}.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"未找到模型元信息 {meta_path}，请先运行 scripts/train.py")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.window = int(self.meta["window"])
        self.sensor_cols = self.meta["sensor_cols"]
        self.scaler = self.meta["scaler"]
        n_feat = int(self.meta["arch"]["n_features"])
        hidden = int(self.meta["arch"]["hidden"])
        layers = int(self.meta["arch"]["layers"])
        self.model = RulLSTM(n_features=n_feat, hidden=hidden, layers=layers)
        self.model.load_state_dict(torch.load(MODEL_DIR / f"{name}.pt", map_location="cpu"))
        self.model.eval()

    def predict(self, seq: np.ndarray) -> float:
        """seq: (window, n_sensor) 归一化序列，返回 RUL 预测值。"""
        x = torch.from_numpy(seq).float().unsqueeze(0)
        with torch.no_grad():
            rul = float(self.model(x).item())
        return max(0.0, round(rul, 2))
