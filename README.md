# AI/ML 增强量化交易系统

> 基于第一性原理和全球顶级量化机构最佳实践构建

## 项目概述

这是一个 AI/ML 增强的企业级量化交易系统，包含：

- **策略研究与开发**：趋势跟踪、均值回归、统计套利、ML预测等
- **回测与验证**：过拟合防御、前视偏差检测、样本外测试
- **实盘执行**：券商API对接、风控系统、仓位管理
- **监控与运维**：漂移监控、绩效分析、决策审计

## 三大核心原则

### 1. 因果单向
任何计算只能使用 `available_at <= bar.close` 的数据，杜绝前视偏差。

### 2. 决策可审计
每笔交易的接受/拒绝都能还原各层输入与判断，支持事后复盘。

### 3. 阈值来自分布
策略参数和阈值来自数据分布，而非绩效网格搜索。

## 目录结构

```
├── core/                    # 核心业务逻辑
│   ├── integration/         # 集成模块（桥接、验证中间件、守门员）
│   ├── strategies/          # 策略实现
│   ├── risk/                # 风控模块
│   └── data/                # 数据处理
├── scripts/                 # 工具脚本
├── tests/                   # 测试用例
├── docs/                    # 文档
├── skills/                  # AI技能知识库
│   └── quant-trading-expert/ # 量化交易专家技能
├── dashboard.html           # AI验证层监控面板
└── AGENTS.md                # 项目规则
```

## 快速开始

### 环境要求
- Python 3.10+
- Docker & Docker Compose
- PostgreSQL 14+

### 安装运行
```bash
# 克隆仓库
git clone https://github.com/yourusername/quant-trading-system.git
cd quant-trading-system

# 安装依赖
pip install -r requirements.txt

# 启动服务栈
docker-compose up -d

# 运行测试
pytest tests/ -q
```

## 核心模块

### 1. 验证层守门员
策略上线/实盘交易前的"守门员"，包含：
- 过拟合检测
- 前视偏差扫描
- 漂移监控
- 压力测试
- 组合风控

### 2. API桥接模块
连接验证层和执行层（QuantDinger/Freqtrade）的桥梁。

### 3. AI验证层监控面板
基于 Web 的实时监控界面。

## 知识库

### 量化交易专家技能
包含31份参考文档，覆盖：
- 第一性原理框架
- 全球顶级机构实践
- ML实战手册
- 风控与执行系统
- 思维模型工具箱
- 过拟合防御方法论
- 回测真实性建模
- MLOps与实验管理
- 等等...

详见：[skills/quant-trading-expert/](skills/quant-trading-expert/)

## 测试

```bash
# 运行全部测试
pytest tests/ -q

# 运行特定测试
pytest tests/test_enum_mapping.py -v
```

## 最佳实践参考

本系统设计参考了以下顶级量化机构的实践：
- Renaissance Technologies（大奖章基金）
- Two Sigma
- Citadel
- Millennium
- Jane Street
- Jump Trading

## 许可证

MIT License

## 贡献指南

1. Fork 本仓库
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

---

**注意：本系统仅供学习和研究使用，不构成投资建议。实盘交易有风险，入市需谨慎。**
