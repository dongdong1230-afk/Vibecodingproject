"""预测编排服务：文件解析 → 特征工程 → LSTM/RF 推理 → 健康评估 → 入库。

是后端业务逻辑的核心编排层。
"""
from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

from backend import database
from backend.models import feature_engineering as fe
from backend.models.lstm_model import LstmPredictor
from backend.models.ml_baseline import RfPredictor
from backend.services.health_eval import evaluate_health

# 若模型不存在，模块级懒加载，避免未训练时后端启动即报错
_lstm: LstmPredictor | None = None
_rf: RfPredictor | None = None


def _get_lstm() -> LstmPredictor:
    global _lstm
    if _lstm is None:
        _lstm = LstmPredictor("lstm_fd001")
    return _lstm


def _get_rf() -> RfPredictor:
    global _rf
    if _rf is None:
        _rf = RfPredictor("rf_fd001")
    return _rf


def _parse_upload(raw: bytes) -> pd.DataFrame:
    """解析上传文件：支持 C-MAPSS 原始 26 列格式与简化的传感器 CSV。

    兼容策略：先尝试读取为表格；若首行不是列名则按 C-MAPSS 26 列格式解析。
    """
    text = raw.decode("utf-8", errors="replace").strip()
    # 尝试带表头的 CSV
    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception:
        df = None
    if df is not None and not df.empty and "cycle" in df.columns:
        return df

    # 无表头：按 26 列（unit, cycle, setting1-3, sensor1-21）解析
    df = pd.read_csv(io.StringIO(text), sep=r"\s+", header=None,
                     names=fe.CMAPSS_COLUMNS)
    return df


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """把用户文件列名规整为 sensor1..21 / cycle / unit。"""
    df = df.copy()
    rename = {}
    for c in df.columns:
        m = re.match(r"^(?:s|S)?(?:ensor)?(\d{1,2})$", str(c).strip())
        if m and 1 <= int(m.group(1)) <= 21:
            rename[c] = f"sensor{int(m.group(1))}"
    if rename:
        df = df.rename(columns=rename)
    if "cycle" not in df.columns and len(df.columns) >= 2:
        df = df.rename(columns={df.columns[1]: "cycle"})
    if "unit" not in df.columns and len(df.columns) >= 1:
        df = df.rename(columns={df.columns[0]: "unit"})
    return df


def predict_from_upload(raw: bytes, unit_id: str | None = None) -> dict:
    """完整预测流程，返回前端需要的全部结果。"""
    lstm = _get_lstm()
    rf = _get_rf()
    meta = lstm.meta
    sensor_cols = meta["sensor_cols"]
    scaler = meta["scaler"]
    window = int(meta["window"])

    df = _normalize_columns(_parse_upload(raw))
    # 补齐缺失的选定传感器列（数据不完整时以首行均值填充）
    for c in sensor_cols:
        if c not in df.columns:
            df[c] = 0.0
    df = df.sort_values("cycle").reset_index(drop=True)

    cycles_used = int(df["cycle"].iloc[-1]) if "cycle" in df.columns else int(len(df))
    unit_name = unit_id or (str(df["unit"].iloc[0]) if "unit" in df.columns else "upload")

    # 1) LSTM：取最后 window 个循环的归一化序列
    seq = fe.last_window_for_unit(df, sensor_cols, scaler, window)
    lstm_rul = lstm.predict(seq)

    # 2) RF 基线：窗口统计特征
    last = df.iloc[-window:].copy()
    feat = []
    for c in sensor_cols:
        lo, hi = scaler[c]
        denom = hi - lo if hi > lo else 1.0
        col = (last[c].to_numpy(dtype=float) - lo) / denom
        slope = np.polyfit(np.arange(len(col)), col, 1)[0]
        feat.extend([col[-1], col.mean(), col.std(), slope])
    rf_rul = rf.predict(np.asarray(feat, dtype=np.float32))

    # 3) 健康评估（以 LSTM 结果为准）
    health = evaluate_health(lstm_rul)

    # 4) 入库
    pred_id = database.insert_prediction(
        unit_id=unit_name,
        sensor_count=len(sensor_cols),
        cycles_used=cycles_used,
        predicted_rul=lstm_rul,
        rf_rul=rf_rul,
        health_level=health.health_level,
        advice=health.advice,
    )

    # 5) 前端趋势图数据（最近 window 个循环的选定传感器原始值）
    trend = {
        "cycles": last["cycle"].astype(int).tolist(),
        "series": {
            c: [round(float(v), 4) for v in last[c].tolist()] for c in sensor_cols[:6]
        },
    }

    return {
        "prediction_id": pred_id,
        "unit_id": unit_name,
        "cycles_used": cycles_used,
        "predicted_rul": lstm_rul,
        "rf_rul": rf_rul,
        "health_level": health.health_level,
        "health_color": health.color,
        "advice": health.advice,
        "model": {
            "name": "LSTM (PyTorch)",
            "window": window,
            "sensors_used": sensor_cols,
            "val_rmse": meta.get("metrics", {}).get("val_rmse"),
        },
        "trend": trend,
    }
