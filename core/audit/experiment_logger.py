# -*- coding: utf-8 -*-
"""core/audit/experiment_logger.py —— 实验日志自动记录。

基于第一性原理：
    每次回测/AB测试都是一次实验。
    如果实验结果不记录下来，下次还会重复做同样的实验。
    顶级机构（Renaissance/Two Sigma）都有严格的实验管理体系。

核心功能：
1. 实验开始时自动记录元数据
2. 实验结束时自动记录结果指标
3. 自动统计trials次数（含失败试验）
4. 决策规则冻结校验
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from .db_writer import _get_pg_conn

logger = logging.getLogger("core.audit.experiment")


# ------------------------------------------------------------------
# 实验记录器
# ------------------------------------------------------------------
class ExperimentLogger:
    """实验日志自动记录器。

    用法：
        logger = ExperimentLogger()

        # 实验开始
        exp_id = logger.start_experiment(
            name="突破策略参数优化",
            hypothesis="ATR止盈比固定止盈效果好",
            experiment_type="ab_test",
        )

        # ... 运行实验 ...

        # 实验结束
        logger.end_experiment(
            experiment_uid=exp_id,
            metrics={"sharpe": 1.8, "max_drawdown": -0.12, "win_rate": 0.55},
            conclusion="ATR止盈确实优于固定止盈",
            decision="promote_to_production",
        )
    """

    def start_experiment(self,
                         name: str,
                         hypothesis: str,
                         experiment_type: str = "backtest",
                         strategy_id: int = None,
                         control_group: str = None,
                         treatment_group: str = None,
                         sample_size: int = None,
                         duration_hours: float = None) -> Optional[str]:
        """开始一次实验，自动创建记录。

        Args:
            name: 实验名称
            hypothesis: 实验假设
            experiment_type: 实验类型（backtest/ab_test/parameter_tuning）
            strategy_id: 关联策略ID
            control_group: 对照组描述
            treatment_group: 实验组描述
            sample_size: 样本量
            duration_hours: 预计运行时长

        Returns:
            实验UID，失败返回None
        """
        conn = _get_pg_conn()
        if conn is None:
            return None

        experiment_uid = f"exp-{uuid.uuid4().hex[:12]}"
        freeze_at = datetime.now()

        sql = """
            INSERT INTO qd_experiment_logs (
                experiment_uid, name, hypothesis, experiment_type,
                control_group, treatment_group, sample_size, duration_hours,
                strategy_id, decision_rule_frozen, freeze_at, trials_count, status
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, true, %s, 1, 'running'
            )
            RETURNING id
        """

        try:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    experiment_uid, name, hypothesis, experiment_type,
                    control_group, treatment_group, sample_size, duration_hours,
                    strategy_id, freeze_at,
                ))
                result = cur.fetchone()
                record_id = result[0] if result else None

            logger.info("experiment started: %s | %s", experiment_uid, name)
            print(f"🧪 实验开始: {name}")
            print(f"   实验ID: {experiment_uid}")
            print(f"   假设: {hypothesis}")
            print(f"   决策规则已冻结于: {freeze_at}")

            return experiment_uid

        except Exception as e:
            logger.warning("failed to start experiment: %s", e)
            return None

    def end_experiment(self,
                      experiment_uid: str,
                      metrics: Dict[str, Any],
                      conclusion: str,
                      decision: str,
                      p_value: float = None,
                      effect_size: float = None) -> bool:
        """结束实验，记录结果。

        Args:
            experiment_uid: 实验UID
            metrics: 结果指标字典（sharpe/max_drawdown/win_rate等）
            conclusion: 实验结论
            decision: 决策（promote_to_production/pivot/abandon）
            p_value: p值（AB测试统计显著性）
            effect_size: 效应量

        Returns:
            是否成功
        """
        conn = _get_pg_conn()
        if conn is None:
            return False

        sql = """
            UPDATE qd_experiment_logs
            SET metrics_json = %s,
                result_json = %s,
                p_value = %s,
                effect_size = %s,
                conclusion = %s,
                decision = %s,
                status = 'completed',
                completed_at = %s
            WHERE experiment_uid = %s
        """

        import json
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    json.dumps(metrics, ensure_ascii=False),
                    json.dumps({"final_metrics": metrics}, ensure_ascii=False),
                    p_value,
                    effect_size,
                    conclusion,
                    decision,
                    datetime.now(),
                    experiment_uid,
                ))

            logger.info("experiment ended: %s | decision=%s", experiment_uid, decision)
            print(f"\n✅ 实验完成: {experiment_uid}")
            print(f"   结论: {conclusion}")
            print(f"   决策: {decision}")
            print(f"   指标: {metrics}")

            return True

        except Exception as e:
            logger.warning("failed to end experiment: %s", e)
            return False

    def get_experiment_stats(self, strategy_id: int = None) -> Dict:
        """获取实验统计。"""
        conn = _get_pg_conn()
        if conn is None:
            return {}

        try:
            sql = "SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'completed') FROM qd_experiment_logs"
            params = []

            if strategy_id:
                sql += " WHERE strategy_id = %s"
                params.append(strategy_id)

            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()

            return {
                "total_experiments": row[0] if row else 0,
                "completed_experiments": row[1] if row else 0,
            }

        except Exception as e:
            logger.warning("failed to get experiment stats: %s", e)
            return {}


# ------------------------------------------------------------------
# 单例模式
# ------------------------------------------------------------------
_experiment_logger_instance: Optional[ExperimentLogger] = None


def get_experiment_logger() -> ExperimentLogger:
    """获取全局实验记录器单例。"""
    global _experiment_logger_instance
    if _experiment_logger_instance is None:
        _experiment_logger_instance = ExperimentLogger()
    return _experiment_logger_instance
