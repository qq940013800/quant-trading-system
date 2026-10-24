# -*- coding: utf-8 -*-
"""core/audit/strategy_health_monitor.py —— 策略绩效自动诊断。

基于第一性原理：
    任何 Alpha 都会衰减。
    被动等待策略失效 = 亏钱。
    顶级机构（Renaissance/Two Sigma）都有严格的策略健康监控体系。

核心功能：
1. 自动计算策略健康度评分
2. 红灯预警：策略衰减信号
3. 绿灯/黄灯/红灯三级诊断
4. 退役建议：什么时候应该下线策略
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, List

from .db_writer import _get_pg_conn

logger = logging.getLogger("core.audit.health")


# ------------------------------------------------------------------
# 策略健康监控器
# ------------------------------------------------------------------
class StrategyHealthMonitor:
    """策略绩效自动诊断器。

    用法：
        monitor = StrategyHealthMonitor()
        diagnosis = monitor.diagnose_strategy(strategy_id=1)
        print(diagnosis)
    """

    # 诊断阈值（基于行业经验）
    GREEN_WIN_RATE = 0.50           # 胜率 > 50% = 绿灯
    YELLOW_WIN_RATE = 0.45          # 胜率 45-50% = 黄灯
    # 胜率 < 45% = 红灯

    GREEN_PROFIT_FACTOR = 1.3       # Profit Factor > 1.3 = 绿灯
    YELLOW_PROFIT_FACTOR = 1.1      # Profit Factor 1.1-1.3 = 黄灯
    # Profit Factor < 1.1 = 红灯

    GREEN_AVG_R = 1.0                # 平均R > 1.0 = 绿灯
    YELLOW_AVG_R = 0.5               # 平均R 0.5-1.0 = 黄灯
    # 平均R < 0.5 = 红灯

    def diagnose_strategy(self, strategy_id: int) -> Dict:
        """诊断策略健康度。

        Args:
            strategy_id: 策略ID

        Returns:
            诊断报告字典
        """
        # 1. 从交易日志计算绩效指标
        metrics = self._calc_strategy_metrics(strategy_id)

        if not metrics or metrics.get("total_trades", 0) < 10:
            return {
                "strategy_id": strategy_id,
                "status": "insufficient_data",
                "message": "交易数据不足10笔，无法诊断",
                "recommendation": "继续观察，积累更多数据",
            }

        # 2. 三级诊断
        score = self._calc_health_score(metrics)

        if score >= 80:
            status = "green"
            recommendation = "策略健康，继续运行"
        elif score >= 60:
            status = "yellow"
            recommendation = "策略表现下滑，建议优化参数或减少仓位"
        else:
            status = "red"
            recommendation = "策略严重衰减，建议下线或重大调整"

        return {
            "strategy_id": strategy_id,
            "status": status,
            "health_score": score,
            "metrics": metrics,
            "recommendation": recommendation,
            "warning_signs": self._detect_warnings(metrics),
        }

    def _calc_strategy_metrics(self, strategy_id: int) -> Dict:
        """计算策略绩效指标。"""
        conn = _get_pg_conn()
        if conn is None:
            return {}

        try:
            sql = """
                SELECT
                    COUNT(*) AS total_trades,
                    COUNT(*) FILTER (WHERE net_pnl > 0) AS wins,
                    ROUND(AVG(net_pnl), 2) AS avg_pnl,
                    ROUND(AVG(r_multiple), 2) AS avg_r,
                    ROUND(SUM(net_pnl), 2) AS total_pnl,
                    ROUND(
                        SUM(net_pnl) FILTER (WHERE net_pnl > 0) /
                        NULLIF(ABS(SUM(net_pnl) FILTER (WHERE net_pnl < 0)), 0),
                        2
                    ) AS profit_factor
                FROM qd_trade_journal
                WHERE strategy_id = %s AND status = 'closed'
            """

            with conn.cursor() as cur:
                cur.execute(sql, (strategy_id,))
                columns = [desc[0] for desc in cur.description]
                row = cur.fetchone()

                if not row:
                    return {}

                result = dict(zip(columns, row))
                result["win_rate_pct"] = round(
                    result["wins"] / result["total_trades"] * 100, 1
                ) if result["total_trades"] > 0 else 0

                return result

        except Exception as e:
            logger.warning("failed to calc strategy metrics: %s", e)
            return {}

    def _calc_health_score(self, metrics: Dict) -> int:
        """计算健康度评分（0-100）。"""
        score = 50  # 基础分

        # 胜率评分（30分）
        win_rate = metrics.get("win_rate_pct", 0)
        if win_rate >= 55:
            score += 30
        elif win_rate >= 50:
            score += 20
        elif win_rate >= 45:
            score += 10

        # Profit Factor评分（40分）
        pf = metrics.get("profit_factor") or 0
        if pf >= 1.5:
            score += 40
        elif pf >= 1.3:
            score += 30
        elif pf >= 1.1:
            score += 15

        # 平均R倍数评分（30分）
        avg_r = metrics.get("avg_r") or 0
        if avg_r >= 1.5:
            score += 30
        elif avg_r >= 1.0:
            score += 20
        elif avg_r >= 0.5:
            score += 10

        return min(100, score)

    def _detect_warnings(self, metrics: Dict) -> List[str]:
        """检测预警信号。"""
        warnings = []

        win_rate = metrics.get("win_rate_pct", 0)
        pf = metrics.get("profit_factor") or 0
        avg_r = metrics.get("avg_r") or 0

        if win_rate < 45:
            warnings.append(f"胜率过低: {win_rate}%")

        if pf < 1.1:
            warnings.append(f"Profit Factor过低: {pf}")

        if avg_r < 0.5:
            warnings.append(f"平均R倍数过低: {avg_r}")

        return warnings


# ------------------------------------------------------------------
# 单例模式
# ------------------------------------------------------------------
_health_monitor_instance: Optional[StrategyHealthMonitor] = None


def get_strategy_health_monitor() -> StrategyHealthMonitor:
    """获取全局策略健康监控器单例。"""
    global _health_monitor_instance
    if _health_monitor_instance is None:
        _health_monitor_instance = StrategyHealthMonitor()
    return _health_monitor_instance
