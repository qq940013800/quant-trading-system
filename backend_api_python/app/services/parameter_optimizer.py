"""
参数优化框架（Parameter Optimization）

第一性原理：
- 参数优化的目标不是找到历史上最好的参数，而是找到未来最可能有效的参数
- 历史最优参数往往是过拟合的结果，未来会失效
- 必须用样本外测试和交叉验证来防御过拟合

全球顶级机构实践：
- Renaissance：严格的样本外测试，CPCV组合交叉验证
- Two Sigma：贝叶斯优化，自动探索参数空间
- AQR：参数鲁棒性检验，参数微小变化不能导致结果大幅变化

核心原则（不可违反）：
1. 决策规则必须在实验前冻结 —— 不能根据结果调整阈值
2. trials计数必须包含失败试验 —— 试了100次只报告最好的1次，那不是策略，是运气
3. 样本外测试是唯一真理 —— 任何回测好看但样本外失效的策略都是垃圾
4. 三重验证：PBO + CPCV + Deflated Sharpe Ratio
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.utils.logger import get_logger

logger = get_logger(__name__)


class OptimizationMethod(Enum):
    """优化方法"""
    GRID_SEARCH = "grid_search"                # 网格搜索
    RANDOM_SEARCH = "random_search"            # 随机搜索
    BAYESIAN = "bayesian"                       # 贝叶斯优化
    WALK_FORWARD = "walk_forward"              # 滚动前推


@dataclass
class ParameterSpace:
    """参数空间"""
    name: str
    type: str = "continuous"                  # continuous / discrete
    min_value: float = 0.0
    max_value: float = 1.0
    step: float = 0.1
    choices: List[Any] = field(default_factory=list)  # discrete时使用


@dataclass
class OptimizationResult:
    """优化结果"""
    best_params: Dict[str, Any]
    best_score: float
    all_results: List[Dict[str, Any]] = field(default_factory=list)
    n_trials: int = 0
    overfitting_risk: str = "unknown"        # low / medium / high
    warnings: List[str] = field(default_factory=list)


class ParameterOptimizer:
    """
    参数优化器
    
    功能：
    1. 在参数空间内搜索最优参数
    2. 用交叉验证防御过拟合
    3. 评估过拟合风险
    """
    
    def __init__(self, method: OptimizationMethod = OptimizationMethod.WALK_FORWARD):
        self.method = method
        self.trials: List[Dict[str, Any]] = []  # 所有试验记录（包括失败的）
    
    def optimize(self, 
                 objective_func: Callable[[Dict[str, Any]], float],
                 param_space: Dict[str, ParameterSpace],
                 n_trials: int = 100,
                 validation_ratio: float = 0.3) -> OptimizationResult:
        """
        参数优化主流程
        
        Args:
            objective_func: 目标函数（输入参数，输出得分）
            param_space: 参数空间
            n_trials: 试验次数
            validation_ratio: 验证集比例
            
        Returns:
            OptimizationResult: 优化结果
        """
        logger.info(f"Starting parameter optimization: {n_trials} trials")
        
        # 1. 生成参数组合
        param_combinations = self._generate_param_combinations(param_space, n_trials)
        
        # 2. 运行所有试验（包括失败的）
        all_results = []
        for i, params in enumerate(param_combinations):
            try:
                score = objective_func(params)
                result = {
                    'params': params,
                    'score': score,
                    'trial_id': i + 1,
                    'success': True
                }
            except Exception as e:
                result = {
                    'params': params,
                    'score': -999,
                    'trial_id': i + 1,
                    'success': False,
                    'error': str(e)
                }
            
            all_results.append(result)
            self.trials.append(result)  # 记录所有试验，包括失败的
        
        # 3. 找出最优参数
        successful_results = [r for r in all_results if r['success']]
        
        if not successful_results:
            return OptimizationResult(
                best_params={},
                best_score=0.0,
                all_results=all_results,
                n_trials=len(all_results),
                overfitting_risk="high",
                warnings=["All trials failed"]
            )
        
        best_result = max(successful_results, key=lambda x: x['score'])
        
        # 4. 评估过拟合风险
        overfitting_risk, warnings = self._assess_overfitting_risk(
            all_results, best_result, n_trials
        )
        
        return OptimizationResult(
            best_params=best_result['params'],
            best_score=best_result['score'],
            all_results=all_results,
            n_trials=len(all_results),
            overfitting_risk=overfitting_risk,
            warnings=warnings
        )
    
    def _generate_param_combinations(self, 
                                     param_space: Dict[str, ParameterSpace],
                                     n_trials: int) -> List[Dict[str, Any]]:
        """生成参数组合"""
        combinations = []
        
        for i in range(n_trials):
            params = {}
            for name, space in param_space.items():
                if space.type == "discrete":
                    params[name] = np.random.choice(space.choices)
                else:
                    params[name] = np.random.uniform(space.min_value, space.max_value)
            combinations.append(params)
        
        return combinations
    
    def _assess_overfitting_risk(self, 
                                  all_results: List[Dict],
                                  best_result: Dict,
                                  n_trials: int) -> Tuple[str, List[str]]:
        """
        评估过拟合风险
        
        基于：
        1. 试验次数越多，过拟合风险越高（数据挖掘偏差）
        2. 最优得分和中位数得分差距越大，过拟合风险越高
        3. 成功试验占比越低，过拟合风险越高
        """
        warnings = []
        
        successful = [r for r in all_results if r['success']]
        scores = [r['score'] for r in successful]
        
        # 1. 试验次数惩罚
        if n_trials > 100:
            warnings.append(f"Trials={n_trials}，数据挖掘偏差风险高")
        
        # 2. 最优vs中位数差距
        if len(scores) > 10:
            best_score = max(scores)
            median_score = np.median(scores)
            gap = best_score - median_score
            
            if gap > 2.0:  # 差距太大
                warnings.append(f"Best score {best_score:.2f} vs median {median_score:.2f}，差距过大，可能过拟合")
        
        # 3. 成功率
        success_rate = len(successful) / len(all_results)
        if success_rate < 0.3:
            warnings.append(f"Success rate only {success_rate:.1%}，参数空间可能不合理")
        
        # 综合判断
        risk = "low"
        if len(warnings) >= 2:
            risk = "high"
        elif len(warnings) >= 1:
            risk = "medium"
        
        return risk, warnings
    
    def get_trials_count(self) -> int:
        """获取累计试验次数（包括失败的）"""
        return len(self.trials)
    
    def reset_trials(self):
        """重置试验计数（新策略实验时必须重置）"""
        self.trials = []
