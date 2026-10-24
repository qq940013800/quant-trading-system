# AI/ML 增强量化交易系统 — 知识库总索引

> 基于第一性原理和全球最佳实践的完整知识体系。
> 所有内容按"行业共识 / 机构实践 / 本设计推断 / 待验证假设"四类标注确定度。

---

## 知识库架构总览

```
quant-trading-expert 技能知识库（16份参考文件）
│
├── 1. 底层原理层（为什么）
│   ├── first-principles.md          # 第一性原理框架
│   ├── top-firm-practices.md        # 全球顶级机构实践
│   └── mental-models.md             # 思维模型工具箱
│
├── 2. 策略与方法层（做什么）
│   ├── trading-strategies.md        # 交易系统与策略体系
│   ├── quant-strategy-landscape.md  # 全球量化策略全景
│   ├── technical-analysis-playbook.md  # 技术分析实战手册
│   └── trading-playbook.md          # 实战总纲（六步闭环）
│
├── 3. AI/ML 层（怎么用 AI）
│   └── ml-playbook.md               # AI/ML 实战手册
│
├── 4. 风控与执行层（怎么控制风险）
│   ├── risk-and-execution.md        # 风控与执行系统
│   ├── position-sizing.md            # 资金仓位管理
│   └── strategy-matching.md         # 策略自动匹配
│
├── 5. 技术分析工具层（用什么指标）
│   ├── non-lagging-indicators.md    # 非滞后指标体系
│   ├── market-structure-analysis.md # 市场结构与价格行为
│   └── tradingview-pine.md          # TradingView / Pine Script
│
└── 6. 工程与系统层（怎么落地）
    ├── system-architecture.md        # 企业级系统架构
    └── dev-practices.md              # 工程最佳实践
```

---

## 核心原则速记

### 过拟合防御（最重要）
1. 样本外测试是唯一真理
2. PBO + CPCV + Deflated Sharpe 三重验证
3. 决策规则必须冻结在实验前
4. trials 计数必须包含失败试验

### 因果与数据
5. 因果单向：只用 `available_at <= bar.close` 的数据
6. 集合分离：估计集/构建集/测试集严格分离
7. 数据质量优先于模型复杂度

### 风控与仓位
8. 截断亏损，让利润奔跑（左尾截断 + 右尾暴露）
9. 分数 Kelly（1/4 ~ 1/2），不用全 Kelly
10. 分散化是分散风险因子，不是分散持仓数量

### ML 使用边界
11. ML 擅长从大量弱信号中提取模式，不擅长预测强趋势
12. 规则方法在逻辑清晰、样本不足时仍不可替代
13. 模型上线即衰减，提前准备退役机制

---

## 优化方案文档

| 文档 | 路径 | 内容 |
|------|------|------|
| 基础优化方案 | docs/OPTIMIZATION_PLAN.md | 9大分层优化、P0/P1/P2优先级、四阶段路线图 |
| 深度优化方案 | docs/DEEP_OPTIMIZATION_PLAN.md | 10大模块深度优化、现状诊断、新增模块清单 |

---

## 代码实现对应

| 知识库概念 | 代码实现位置 | 成熟度 |
|-----------|-------------|--------|
| 第一性原理 Alpha 四分类 | core/features/ 各因子模块 | 骨架级 |
| 市场状态识别（ADX/Hurst） | core/features/regime.py | 骨架级 |
| 市场结构分析 | core/features/structure.py | 骨架级 |
| ATR / 波动率特征 | core/features/atr.py, volatility.py | 基础级 |
| K线形态识别 | core/features/patterns.py | 骨架级 |
| ML 基线模型 | core/models/baseline.py | 中等 |
| 交叉验证 | core/models/cv.py | 骨架级 |
| 标签工程 | core/models/labels.py | 骨架级 |
| Meta-labeling | core/models/meta_label.py | 骨架级 |
| ML 增强趋势策略 | core/models/ml_trend_strategy.py | 中等 |
| 仓位 sizing | core/risk/sizing.py | 骨架级 |
| 止损体系 | core/risk/stops.py | 骨架级 |
| 熔断机制 | core/risk/circuit.py | 骨架级 |
| 回测引擎 | core/backtest/engine.py | 中等 |
| 成本模型 | core/backtest/costs.py | 骨架级 |
| 回测指标 | core/backtest/metrics.py | 骨架级 |

---

## 待落地模块（P0 优先级）

### 第一阶段：生存加固（1-2周）

- [ ] 策略注册表（core/registry/）
- [ ] 四级止损体系（扩充 core/risk/stops.py）
- [ ] 移动止盈系统（core/risk/trailing.py）
- [ ] 高低点序列 + BOS/CHoCH 识别（扩充 core/features/structure.py）
- [ ] 反转K线形态库（扩充 core/features/patterns.py）
- [ ] 过拟合防御（PBO + Deflated Sharpe）（扩充 core/models/cv.py）
- [ ] 滑点模型优化（扩充 core/backtest/costs.py）

### 第二阶段：策略升级（2-4周）

- [ ] AB测试框架（core/experiment/ab_test.py）
- [ ] 策略自动匹配（core/matching/）
- [ ] 入场质量评分系统
- [ ] 多周期共振检测
- [ ] 供需区/订单块识别
- [ ] 参数自动优化框架

---

## 参考来源

- López de Prado《Advances in Financial Machine Learning》
- Renaissance Technologies / Two Sigma / Citadel / Millennium 公开资料
- 海龟交易法则（Richard Dennis）
- ICT（Inner Circle Trader）体系
- CFA Institute / CAIA 教材
- QuantConnect / Zipline / Backtrader 文档
