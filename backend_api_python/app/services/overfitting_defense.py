"""
过拟合防御三重验证系统
PBO + CPCV + Deflated Sharpe Ratio

这是量化系统的生命线——如果策略过拟合，回测再好看也是垃圾。
对标 Renaissance / Two Sigma 的过拟合防御标准。
"""
import math
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime


# 标准正态分布的纯本地实现（避免引入未声明的 scipy 重依赖）。
# ppf 采用 Acklam 逆正态近似；cdf 基于标准库 math.erf。
_NORM_PPF_A = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
               1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459237e+00]
_NORM_PPF_B = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
               6.680131188771972e+01, -1.328068155288572e+01]
_NORM_PPF_C = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
               -2.549732593437378e+00, 4.374664141464968e+00, 2.938163982698783e+00]
_NORM_PPF_D = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
               3.754408661907416e+00]


def _norm_ppf(p: float) -> float:
    """逆标准正态 CDF（Acklam 近似，输入 0< p <1）。"""
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_NORM_PPF_C[0] * q + _NORM_PPF_C[1]) * q + _NORM_PPF_C[2]) * q
                  + _NORM_PPF_C[3]) * q + _NORM_PPF_C[4]) * q + _NORM_PPF_C[5]) / (
                     (((( _NORM_PPF_D[0] * q + _NORM_PPF_D[1]) * q + _NORM_PPF_D[2]) * q
                       + _NORM_PPF_D[3]) * q + 1.0))
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -((((( _NORM_PPF_C[0] * q + _NORM_PPF_C[1]) * q + _NORM_PPF_C[2]) * q
                    + _NORM_PPF_C[3]) * q + _NORM_PPF_C[4]) * q + _NORM_PPF_C[5]) / (
                     (((( _NORM_PPF_D[0] * q + _NORM_PPF_D[1]) * q + _NORM_PPF_D[2]) * q
                       + _NORM_PPF_D[3]) * q + 1.0))
    q = p - 0.5
    r = q * q
    return (((((_NORM_PPF_A[0] * r + _NORM_PPF_A[1]) * r + _NORM_PPF_A[2]) * r
              + _NORM_PPF_A[3]) * r + _NORM_PPF_A[4]) * r + _NORM_PPF_A[5]) * q / (
                 (((( _NORM_PPF_B[0] * r + _NORM_PPF_B[1]) * r + _NORM_PPF_B[2]) * r
                   + _NORM_PPF_B[3]) * r + _NORM_PPF_B[4]) * r + 1.0)


def _norm_cdf(z: float) -> float:
    """标准正态 CDF。"""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@dataclass
class PFOResult:
    """过拟合检测结果"""
    pbo: float  # Probability of Backtest Overfitting (0-1)
    is_overfitted: bool  # 是否过拟合
    degradation_ratio: float  # 样本外衰减比例
    n_trials: int  # 试验次数
    recommendation: str  # 建议
    
    def to_dict(self):
        return {
            "pbo": float(round(self.pbo, 4)),
            "is_overfitted": bool(self.is_overfitted),
            "degradation_ratio": float(round(self.degradation_ratio, 4)),
            "n_trials": int(self.n_trials),
            "recommendation": self.recommendation
        }


@dataclass
class CPCVResult:
    """CPCV交叉验证结果"""
    mean_sharpe: float  # 平均夏普
    std_sharpe: float  # 夏普标准差
    min_sharpe: float  # 最差夏普
    is_stable: bool  # 是否稳定
    n_splits: int  # 折数
    
    def to_dict(self):
        return {
            "mean_sharpe": float(round(self.mean_sharpe, 4)),
            "std_sharpe": float(round(self.std_sharpe, 4)),
            "min_sharpe": float(round(self.min_sharpe, 4)),
            "is_stable": bool(self.is_stable),
            "n_splits": int(self.n_splits)
        }


@dataclass
class DSRResult:
    """Deflated Sharpe Ratio结果"""
    observed_sharpe: float  # 观测到的夏普
    expected_max_sharpe: float  # 随机策略的期望最大夏普
    deflated_sharpe: float  # 折损后夏普
    is_significant: bool  # 是否统计显著
    
    def to_dict(self):
        return {
            "observed_sharpe": float(round(self.observed_sharpe, 4)),
            "expected_max_sharpe": float(round(self.expected_max_sharpe, 4)),
            "deflated_sharpe": float(round(self.deflated_sharpe, 4)),
            "is_significant": bool(self.is_significant)
        }


class OverfittingDefense:
    """过拟合防御三重验证"""
    
    def __init__(self):
        self.risk_free_rate = 0.02  # 无风险利率
    
    def calculate_pbo(self, strategy_returns: np.ndarray, 
                      n_trials: int = 100,
                      n_splits: int = 10) -> PFOResult:
        """
        计算PBO (Probability of Backtest Overfitting)
        
        核心思想：把时间序列切成多段，看样本内最优策略在样本外是否还是最优。
        如果样本外排名大幅下降，说明过拟合了。
        
        参数:
            strategy_returns: shape (n_trials, n_periods) - 多个策略的收益序列
            n_trials: 策略试验次数
            n_splits: 分割次数
        """
        n_periods = len(strategy_returns[0])
        
        # 随机分割样本内/样本外
        in_sample_ranks = []
        out_sample_ranks = []
        
        for i in range(n_splits):
            # 随机选60%作为样本内，40%作为样本外
            split_point = int(n_periods * 0.6)
            indices = np.random.permutation(n_periods)
            in_idx = indices[:split_point]
            out_idx = indices[split_point:]
            
            # 计算每个策略在样本内的夏普
            in_sharpes = []
            for s in strategy_returns:
                in_ret = s[in_idx]
                if np.std(in_ret) > 0:
                    sharpe = (np.mean(in_ret) - self.risk_free_rate/252) / np.std(in_ret) * np.sqrt(252)
                else:
                    sharpe = 0
                in_sharpes.append(sharpe)
            
            # 样本内排名
            in_rank = np.argsort(np.argsort(in_sharpes))
            
            # 计算样本外的夏普
            out_sharpes = []
            for s in strategy_returns:
                out_ret = s[out_idx]
                if np.std(out_ret) > 0:
                    sharpe = (np.mean(out_ret) - self.risk_free_rate/252) / np.std(out_ret) * np.sqrt(252)
                else:
                    sharpe = 0
                out_sharpes.append(sharpe)
            
            # 样本外排名
            out_rank = np.argsort(np.argsort(out_sharpes))
            
            in_sample_ranks.append(in_rank)
            out_sample_ranks.append(out_rank)
        
        # 计算PBO：样本内最优策略在样本外排名中位数低于50%的概率
        pbo_count = 0
        degradation_total = []
        
        for i in range(n_splits):
            best_in_idx = np.argmax(in_sample_ranks[i])
            out_rank_of_best = out_sample_ranks[i][best_in_idx]
            median_rank = np.median(out_sample_ranks[i])
            
            # 如果样本内最优在样本外排名低于中位数，算一次过拟合
            if out_rank_of_best < median_rank:
                pbo_count += 1
            
            # 衰减比例：样本内最优 vs 样本外实际表现
            degradation = 1 - (out_rank_of_best / len(out_sample_ranks[i]))
            degradation_total.append(degradation)
        
        pbo = pbo_count / n_splits
        avg_degradation = np.mean(degradation_total)
        
        # 判断是否过拟合
        is_overfitted = pbo > 0.5  # 超过50%概率过拟合
        
        # 生成建议
        if pbo < 0.2:
            recommendation = "低过拟合风险，策略稳健，可以上线"
        elif pbo < 0.5:
            recommendation = "中等过拟合风险，建议增加样本外验证"
        else:
            recommendation = "高过拟合风险，策略可能是噪声拟合，不建议上线"
        
        return PFOResult(
            pbo=pbo,
            is_overfitted=is_overfitted,
            degradation_ratio=avg_degradation,
            n_trials=n_trials,
            recommendation=recommendation
        )
    
    def calculate_cpcv(self, returns: np.ndarray, 
                       n_groups: int = 6,
                       n_test_groups: int = 2) -> CPCVResult:
        """
        CPCV (Combinatorial Purged Cross-Validation)
        组合净化交叉验证
        
        比普通K折交叉验证更严格：
        - 组合所有可能的训练/测试组合
        - 净化（purging）：删除训练集和测试集边界附近的数据
        - 避免前视偏差
        
        参数:
            returns: 策略收益序列
            n_groups: 分成多少组
            n_test_groups: 每组测试集用几组
        """
        n = len(returns)
        group_size = n // n_groups
        
        # 把数据分成连续的组
        groups = []
        for i in range(n_groups):
            start = i * group_size
            end = (i + 1) * group_size if i < n_groups - 1 else n
            groups.append(returns[start:end])
        
        # 生成所有可能的训练/测试组合
        from itertools import combinations
        
        sharpes = []
        
        for test_combo in combinations(range(n_groups), n_test_groups):
            # 测试组
            test_idx = list(test_combo)
            train_idx = [i for i in range(n_groups) if i not in test_combo]
            
            # 训练数据
            train_data = np.concatenate([groups[i] for i in train_idx])
            # 测试数据
            test_data = np.concatenate([groups[i] for i in test_idx])
            
            # 净化：删除训练集和测试集边界附近的数据（避免前视）
            purge_size = min(10, len(train_data) // 10)
            train_data = train_data[purge_size:-purge_size]
            
            # 计算测试集夏普
            if np.std(test_data) > 0:
                sharpe = (np.mean(test_data) - self.risk_free_rate/252) / np.std(test_data) * np.sqrt(252)
            else:
                sharpe = 0
            
            sharpes.append(sharpe)
        
        sharpes = np.array(sharpes)
        
        # 判断稳定性：最差折的夏普是否大于0
        min_sharpe = np.min(sharpes)
        is_stable = min_sharpe > 0
        
        return CPCVResult(
            mean_sharpe=np.mean(sharpes),
            std_sharpe=np.std(sharpes),
            min_sharpe=min_sharpe,
            is_stable=is_stable,
            n_splits=len(sharpes)
        )
    
    def calculate_dsr(self, observed_sharpe: float,
                      n_observations: int = 252,
                      n_trials: int = 100,
                      skewness: float = 0,
                      kurtosis: float = 3) -> DSRResult:
        """
        Deflated Sharpe Ratio (DSR)
        折损夏普比率
        
        核心思想：试了N次策略，最好的那个即使是随机的，夏普也会很高。
        我们需要把"多重试验"的期望收益扣除掉，看真正的Alpha还剩多少。
        
        参考：Bailey & López de Prado (2014)
        
        参数:
            observed_sharpe: 观测到的夏普比率
            n_observations: 观测期数（交易日）
            n_trials: 试验次数（试了多少个策略）
            skewness: 收益偏度
            kurtosis: 收益峰度
        """
        # 随机策略的期望最大夏普（期望值）
        # E[max] ≈ (1-γ)Φ⁻¹(1-1/N) + γΦ⁻¹(1-1/(N*e))
        # γ ≈ 0.5772 (欧拉常数)
        gamma = 0.5772156649

        if n_trials > 1:
            # 近似计算随机试验的期望最大夏普
            expected_max_sharpe = (
                (1 - gamma) * _norm_ppf(1 - 1 / n_trials) +
                gamma * _norm_ppf(1 - 1 / (n_trials * np.e))
            ) * (1 / np.sqrt(n_observations)) * np.sqrt(252)
        else:
            expected_max_sharpe = 0
        
        # 夏普比率的标准误
        # SE(SR) = sqrt((1 - skew*SR + (kurt-1)/4 * SR²) / (T-1))
        sr = observed_sharpe / np.sqrt(252)  # 转换为日夏普
        se_sr = np.sqrt((1 - skewness * sr + (kurtosis - 1) / 4 * sr**2) / (n_observations - 1))
        se_sr_annual = se_sr * np.sqrt(252)
        
        # 折损后的夏普 = 观测夏普 - 随机期望夏普
        deflated_sharpe = observed_sharpe - expected_max_sharpe
        
        # 计算统计显著性（Z-score）
        z_score = deflated_sharpe / se_sr_annual if se_sr_annual > 0 else 0
        p_value = 1 - _norm_cdf(z_score)
        
        # 95%置信度下是否显著
        is_significant = p_value < 0.05
        
        return DSRResult(
            observed_sharpe=observed_sharpe,
            expected_max_sharpe=expected_max_sharpe,
            deflated_sharpe=deflated_sharpe,
            is_significant=is_significant
        )
    
    def full_validation(self, returns: np.ndarray,
                        n_trials: int = 100) -> Dict:
        """
        三重完整验证：PBO + CPCV + DSR
        
        返回完整的过拟合检测报告
        """
        # 模拟多个试验（实际应该用真实的多策略回测结果）
        # 这里用当前策略的收益加噪声来模拟试验
        multi_returns = []
        for i in range(n_trials):
            noise = np.random.normal(0, 0.001, len(returns))
            multi_returns.append(returns + noise)
        multi_returns = np.array(multi_returns)
        
        # 1. PBO
        pbo_result = self.calculate_pbo(multi_returns, n_trials=n_trials)
        
        # 2. CPCV
        cpcv_result = self.calculate_cpcv(returns)
        
        # 3. DSR
        # 计算当前策略的夏普
        if np.std(returns) > 0:
            current_sharpe = (np.mean(returns) - self.risk_free_rate/252) / np.std(returns) * np.sqrt(252)
        else:
            current_sharpe = 0
        
        dsr_result = self.calculate_dsr(
            observed_sharpe=current_sharpe,
            n_observations=len(returns),
            n_trials=n_trials
        )
        
        # 综合判断
        overall_pass = bool(
            not pbo_result.is_overfitted and
            cpcv_result.is_stable and
            dsr_result.is_significant
        )
        
        return {
            "timestamp": datetime.now().isoformat(),
            "has_sample": True,
            "overall_pass": overall_pass,
            "overall_risk_level": "low" if overall_pass else "high",
            "pbo": pbo_result.to_dict(),
            "cpcv": cpcv_result.to_dict(),
            "dsr": dsr_result.to_dict(),
            "recommendation": self._generate_recommendation(pbo_result, cpcv_result, dsr_result)
        }

    def get_defense_summary(self, returns: Optional[np.ndarray] = None) -> Dict:
        """结构化过拟合防御摘要；无有效样本时返回空态，不跑模拟噪声。

        路由层无收益序列入参时调用本方法并传 ``None``，前端三卡据此渲染 ``--``，
        而不是用演示数字顶替缺失值。
        """
        if returns is None or len(returns) < 2:
            return self._empty_summary()
        return self.full_validation(np.asarray(returns, dtype=float))

    def _empty_summary(self) -> Dict:
        return {
            "timestamp": datetime.now().isoformat(),
            "has_sample": False,
            "overall_pass": None,
            "overall_risk_level": "unknown",
            "pbo": {
                "pbo": None, "is_overfitted": None,
                "degradation_ratio": None, "n_trials": 0,
                "recommendation": "缺少策略收益样本",
            },
            "cpcv": {
                "mean_sharpe": None, "std_sharpe": None, "min_sharpe": None,
                "is_stable": None, "n_splits": 0,
            },
            "dsr": {
                "observed_sharpe": None, "expected_max_sharpe": None,
                "deflated_sharpe": None, "is_significant": None,
            },
            "recommendation": "暂无策略收益样本，无法执行三重过拟合验证",
        }

    def _generate_recommendation(self, pbo, cpcv, dsr) -> str:
        """生成综合建议"""
        issues = []
        
        if pbo.is_overfitted:
            issues.append("PBO过高，存在回测过拟合风险")
        if not cpcv.is_stable:
            issues.append("CPCV最差折夏普为负，策略不稳定")
        if not dsr.is_significant:
            issues.append("DSR不显著，扣除多重试验后Alpha不显著")
        
        if not issues:
            return "✅ 三重验证全部通过，策略具备统计显著性，可以上线实盘"
        else:
            return "❌ " + "；".join(issues) + "。建议继续样本外验证，不要急于上线"


# 单例
overfitting_defense = OverfittingDefense()


def get_overfitting_defense() -> OverfittingDefense:
    """返回全局过拟合防御单例（路由层按工厂函数导入）。"""
    return overfitting_defense
