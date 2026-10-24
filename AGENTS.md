# AGENTS.md

## 项目
AI 增强量化交易系统：Python 研究层（core/scripts/ops）+ MQL5 执行层（mt5）。
三条不可协商的不变量：
1. 因果单向——任何计算只用 available_at <= bar.close 的数据
2. 决策可审计——每笔接受/拒绝都能还原各层输入与判断
3. 阈值来自分布——不由绩效网格搜索产生

## 目录与边界
- 可改：core/ scripts/ ops/ tests/ docs/ reports/ experiments/
- 需人工确认才可改：configs/ registry.yaml mt5/
- 禁止改：secrets/ runtime/ ledger/、mt5 中的风控阈值常量
- 禁止读：静默集数据（路径见 docs/data_splits.md）
- 禁止删除任何文件（删除由人执行）

## 命令
- 全量测试：pytest -q
- 枚举映射单测：python tests/test_enum_mapping.py
- Agent 配置校验：python tests/test_agent_config.py
- 缺口清洗：python core/gap_normalizer.py --sym XAUUSD --data data/XAUUSD_M5.csv \
    --out experiments/gate_XAUUSD.yaml   # 产物经人工审核后再放入 configs/
- 阈值校准（默认不看 PnL）：python scripts/calibrate_regime.py --mode distribution
- 实验：./run_gate_experiment.sh --registry registry.yaml --variant <v> --mode dryrun

## 硬规则（违反即打回）
1. 前视守卫：特征/区域/统计量不得读取 t >= 当前 bar 的数据
2. 集合分离：ATR/vol/Hurst 只在 CLEAN 集估计；供需区只用 KNOWN 集构建
3. 因果顺序：L1 位置 → L2 状态 → L3 触发；禁止 L3 结果反哺 L1 定义
4. 止损单调：止损只允许向盈利方向移动；R 倍数用入场冻结的 atr0/entryDist
5. intra-bar：信号与退出决策只允许在已收盘 bar 调用
6. 时区：MT5 服务器偏移必须与 Python 端 --tz 一致，禁止硬编码
7. 异步返回：OrderSend/PositionModify/PositionClosePartial 必须检查返回值并重试
8. 禁止硬编码点值/手数/阈值；走 SymbolInfo* 与 config
9. 禁止 `except Exception: pass`；异常必须带上下文记录
10. 每次改动必须附带或更新单测；黄金集单测不得放宽断言
11. trials_N 只能由实验脚本原子递增（含失败/中止的试验，只增不减）；decision_rule 须在实验前冻结；禁止手工改写 registry.yaml

## 停止条件（必须停下来问人）
- 需要修改 configs/、registry.yaml（实验脚本按规则 11 自动登记除外）、风控阈值、mt5/ 下的常量
- 连续两次测试失败
- 需要删除文件、改数据库、触碰实盘资金路径
- 发现疑似未来函数但无法判定
- 需要访问静默集或扩大数据范围

## 输出要求
每次改动说明四件事：改了哪些文件 / 为什么 / 跑了什么验证 / 剩余风险。
无法自动验证的项（实盘冒烟、经纪商差异）必须显式标注「未验证」。
