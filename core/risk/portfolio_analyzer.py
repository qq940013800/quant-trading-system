# -*- coding: utf-8 -*-
"""core/risk/portfolio_analyzer.py —— 组合层面风险诊断。

基于第一性原理：
    分散化是唯一的免费午餐。
    但要注意是"不相关的分散"，不是"同一个风险因子的重复暴露"。

核心功能：
1. 多策略相关性矩阵分析
2. 风险预算分配
3. 分散化效果评估
4. 伪分散化识别
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, List
import numpy as np

logger = logging.getLogger("core.risk.portfolio")


class PortfolioAnalyzer:
    """组合层面风险诊断器。

    用法：
        analyzer = PortfolioAnalyzer()
        result = analyzer.analyze_portfolio(
            strategy_returns={
                'trend_following': [0.01, -0.02, 0.015, ...],
                'mean_reversion': [0.005, 0.008, -0.003, ...],
            },
            strategy_weights={'trend_following': 0.6, 'mean_reversion': 0.4}
        )
    """

    def analyze_portfolio(self,
                         strategy_returns: Dict[str, List[float]],
                         strategy_weights: Dict[str, float]) -> Dict:
        """分析组合风险。

        Args:
            strategy_returns: 各策略收益率序列
            strategy_weights: 各策略资金权重

        Returns:
            组合风险分析报告
        """
        strategies = list(strategy_returns.keys())
        n = len(strategies)

        if n < 2:
            return {
                "status": "insufficient_strategies",
                "message": "至少需要2个策略才能做组合分析",
            }

        # 1. 计算相关性矩阵
        returns_matrix = np.array([strategy_returns[s] for s in strategies])
        corr_matrix = np.corrcoef(returns_matrix)

        # 2. 计算组合波动率
        weights = np.array([strategy_weights.get(s, 1/n) for s in strategies])
        cov_matrix = np.cov(returns_matrix)
        portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)

        # 3. 计算加权平均波动率（不分散的情况）
        avg_vol = np.average(np.sqrt(np.diag(cov_matrix)), weights=weights)

        # 4. 分散化收益（波动率降低的百分比）
        diversification_benefit = (avg_vol - portfolio_vol) / avg_vol * 100 if avg_vol > 0 else 0

        # 5. 识别伪分散化（相关性过高）
        high_corr_pairs = []
        for i in range(n):
            for j in range(i+1, n):
                if corr_matrix[i][j] > 0.7:
                    high_corr_pairs.append({
                        "pair": f"{strategies[i]} vs {strategies[j]}",
                        "correlation": round(float(corr_matrix[i][j]), 2),
                        "warning": "相关性过高，伪分散化风险"
                    })

        # 6. 风险预算（每个策略对组合风险的贡献）
        marginal_risk = cov_matrix @ weights
        risk_contribution = weights * marginal_risk
        risk_budget = risk_contribution / portfolio_vol**2 * 100 if portfolio_vol > 0 else np.zeros(n)

        return {
            "status": "ok",
            "num_strategies": n,
            "portfolio_volatility": round(float(portfolio_vol), 4),
            "average_volatility": round(float(avg_vol), 4),
            "diversification_benefit_pct": round(float(diversification_benefit), 1),
            "correlation_matrix": {
                "strategies": strategies,
                "matrix": corr_matrix.round(3).tolist(),
                "avg_correlation": round(float(np.mean(corr_matrix[np.triu_indices(n, k=1)])), 3),
            },
            "high_correlation_warnings": high_corr_pairs,
            "risk_budget": {
                strategies[i]: round(float(risk_budget[i]), 1)
                for i in range(n)
            },
            "recommendations": self._get_recommendations(
                diversification_benefit, high_corr_pairs, risk_budget
            ),
        }

    def _get_recommendations(self, div_benefit: float,
                            high_corr: list,
                            risk_budget: np.ndarray) -> List[str]:
        """生成组合优化建议。"""
        recs = []

        if div_benefit < 10:
            recs.append("⚠️ 分散化收益不足10%，建议增加低相关性策略")
        elif div_benefit > 30:
            recs.append("✅ 分散化效果优秀（>30%）")

        if high_corr:
            recs.append(f"⚠️ 发现{len(high_corr)}对高相关性策略，存在伪分散化风险")

        max_risk_idx = np.argmax(risk_budget)
        if risk_budget[max_risk_idx] > 50:
            recs.append("⚠️ 单一策略风险贡献超过50%，建议分散风险预算")

        return recs


# ------------------------------------------------------------------
# 单例模式
# ------------------------------------------------------------------
_portfolio_analyzer_instance: Optional[PortfolioAnalyzer] = None


def get_portfolio_analyzer() -> PortfolioAnalyzer:
    """获取全局组合分析器单例。"""
    global _portfolio_analyzer_instance
    if _portfolio_analyzer_instance is None:
        _portfolio_analyzer_instance = PortfolioAnalyzer()
    return _portfolio_analyzer_instance
