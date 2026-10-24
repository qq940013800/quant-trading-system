# AI/ML 增强量化交易系统知识库索引

> 基于第一性原理和全球最佳实践的完整知识体系。
> 所有内容按"行业共识 / 机构实践 / 本设计推断 / 待验证假设"四类标注确定度。

---

## 知识库结构总览

```
quant-trading-expert 技能知识库
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
│   ├── position-sizing.md          # 资金仓位管理
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

## 核心文件速查

### 1. 底层原理

| 文件 | 核心内容 | 什么时候读 |
|------|---------|-----------|
| **first-principles.md** | 价格=信息+流动性+噪声；Alpha 四分类（信息优势/行为偏差/统计偏差/结构红利）；风险=永久性资本损失 | 论证策略逻辑、思考 Alpha 来源时 |
| **top-firm-practices.md** | Renaissance（海量弱信号+防过拟合）、Millennium（pod 风险预算）、Citadel Securities（做市赚即时性）、Jane Street（期权做市） | 对标行业最佳实践、评估策略门槛时 |
| **mental-models.md** | 第一性原理、概率思维、逆向思维、二阶思维、能力圈、胖尾风险 | 压力测试、评估策略脆弱性时 |

### 2. 策略体系

| 文件 | 核心内容 | 什么时候读 |
|------|---------|-----------|
| **trading-strategies.md** | CTA/海龟/趋势跟踪、价格行为/K线形态、供需区/机构订单/ICT、流动性猎杀 | 设计具体交易策略时 |
| **quant-strategy-landscape.md** | 统计套利、做市、因子投资、事件驱动、高频低延迟、另类数据、ML 驱动 | 选择策略路线、对比不同策略类型时 |
| **technical-analysis-playbook.md** | 趋势跟踪/反转/突破/区间四大策略、多周期共振、完整交易流程 | 选择交易策略、设计入场出场规则时 |
| **trading-playbook.md** | 六步闭环：市场诊断→策略匹配→入场确认→仓位止损→持仓管理→复盘迭代 | 实际交易操作时的快速参考 |

### 3. AI/ML 方法

| 文件 | 核心内容 | 什么时候读 |
|------|---------|-----------|
| **ml-playbook.md** | 模型选择决策树（GBDT/Transformer/RL 边界）、三重障碍标签、meta-labeling、PBO+CPCV+Deflated Sharpe 过拟合防御 | 设计 ML 模型、特征工程、回测验证时 |

### 4. 风控与执行

| 文件 | 核心内容 | 什么时候读 |
|------|---------|-----------|
| **risk-and-execution.md** | 四层限额、分级熔断、四类止损（时间/ATR/信号/跟踪）、ES 替代 VaR、尾部对冲 | 设计风控体系、优化执行时 |
| **position-sizing.md** | 固定比例、Kelly 公式（1/4~1/2 分数 Kelly）、波动率目标、风险平价、固定 R 倍数法、蒙特卡洛验证 | 计算仓位大小、评估风险敞口时 |
| **strategy-matching.md** | 四级市场状态识别、策略匹配决策树、组合优化、动态切换、防抖动滞回阈值 | 根据市场状态选择策略时 |

### 5. 技术分析工具

| 文件 | 核心内容 | 什么时候读 |
|------|---------|-----------|
| **non-lagging-indicators.md** | 价格行为（最领先）、成交量/持仓量、RSI/KDJ/CCI 振荡器、ATR/布林带波动率、订单流 | 选择指标、评估指标滞后性时 |
| **market-structure-analysis.md** | 高低点序列、BOS（结构突破）、CHoCH（结构转换）、趋势三阶段、K线形态、供需区/订单块、真突破vs假突破 | 判断市场状态、识别趋势结构时 |
| **tradingview-pine.md** | Pine Script 语言基础、最佳实践、常见策略模板、Pine+Python 两步工作流 | 快速原型验证、开发指标时 |

### 6. 工程与系统

| 文件 | 核心内容 | 什么时候读 |
|------|---------|-----------|
| **system-architecture.md** | 数据层→研究层→ML/MLOps→执行层→风控层；技术栈选型；高可用灾备 | 设计系统架构、选择技术栈时 |
| **dev-practices.md** | Python 研究层 + C++ 执行层选型；分层架构；测试金字塔；CI/CD MLOps | 设计代码架构、建立测试体系时 |

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
10. 分散化是不相关的分散，不是同一风险因子重复暴露

### ML 使用边界
11. ML 擅长从大量弱信号中提取模式，不擅长预测强趋势
12. 规则方法在逻辑清晰、样本不足时仍不可替代
13. 模型上线即衰减，提前准备退役机制

---

## 代码实现对应

| 知识库概念 | 代码实现位置 |
|-----------|-------------|
| 第一性原理 Alpha 四分类 | `core/features/` 下各因子模块 |
| 市场状态识别（ADX/Hurst） | `core/features/regime.py` |
| 市场结构分析 | `core/features/structure.py` |
| ATR / 波动率特征 | `core/features/atr.py`, `core/features/volatility.py` |
| ML 基线模型 | `core/models/baseline.py` |
| Meta-labeling 策略 | `core/models/ml_trend_strategy.py` |
| 仓位 sizing | `core/risk/sizing.py` |
| 止损体系 | `core/risk/stops.py` |
| 熔断机制 | `core/risk/circuit.py` |
| 回测引擎 | `core/backtest/engine.py` |
| 过拟合防御（CV） | `core/models/cv.py` |

---

## 参考来源

- López de Prado《Advances in Financial Machine Learning》
- Renaissance Technologies / Two Sigma / Citadel / Millennium 公开资料
- 海龟交易法则（Richard Dennis）
- ICT（Inner Circle Trader）体系
- CFA Institute / CAIA 教材
- QuantConnect / Zipline / Backtrader 文档
