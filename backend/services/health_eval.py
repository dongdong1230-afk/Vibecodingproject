"""健康状态评估与维护决策模块。

对应课程技术方向：健康状态评估与决策。
将预测的剩余寿命 RUL 映射为健康等级，并给出可执行的维护建议。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HealthResult:
    rul: float
    health_level: str
    advice: str
    color: str  # 前端展示用颜色


def evaluate_health(rul: float) -> HealthResult:
    """根据 RUL 输出健康等级与维护建议。"""
    if rul <= 20:
        return HealthResult(
            rul=rul,
            health_level="失效风险",
            advice="剩余寿命极低，存在失效风险，应立即安排停运检修，更换关键部件。",
            color="#d93026",
        )
    if rul <= 50:
        return HealthResult(
            rul=rul,
            health_level="危险",
            advice="设备已进入快速退化期，建议近期安排检修，并加密状态监测频次。",
            color="#f5a623",
        )
    if rul <= 100:
        return HealthResult(
            rul=rul,
            health_level="退化",
            advice="设备出现明显退化趋势，建议纳入计划性维护窗口，持续跟踪趋势。",
            color="#f7d154",
        )
    return HealthResult(
        rul=rul,
        health_level="健康",
        advice="设备状态健康，按常规周期维护即可，无需额外干预。",
        color="#2ecc71",
    )
