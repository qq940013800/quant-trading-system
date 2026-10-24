---
description: "Python 层规范：时间戳、因果纪律、数值稳健、错误处理、测试。Use when editing core, scripts, ops or tests Python files."
applyTo: "core/**/*.py,scripts/**/*.py,ops/**/*.py,tests/**/*.py"
---
# Python 层规范

## 类型与时间视角
- 时间戳统一毫秒 int；跨层传递的对象必须带 available_at
- 禁止用 float 表示时间；禁止 naive datetime 混 tz-aware
- 公共函数必须有完整 type hint 与 docstring（含"输入约束/不变量"两节）

## 因果纪律
- 禁止 shift(-n)、center=True、未来索引切片出现在特征/区域构造中
- 标签构造必须显式 shift(-horizon)，并注明"仅可用于训练切分"
- 任何 reindex 后必须 ffill 或显式 fill，禁止静默 NaN 参与统计

## 数值与稳健
- 除法分母一律加 1e-9；log 前校验正数
- 滚动统计必须给 min_periods；样本不足返回 NaN 而非 0
- 随机性：所有采样显式传 seed，禁止依赖全局状态

## 错误处理
- 断言用于不变量（AssertionError 带上下文）；异常用于运行时故障
- 禁止裸 except；捕获后必须记录并决定重抛或降级
- 数据契约校验放在入口（列名、dtype、单调索引、缺失率）

## 测试
- 新增统计量必须配"不变性测试"（如插入假缺口后 ATR 不变）
- 新增退出分支必须配"单调性测试"与"优先级测试"
- 黄金集 tests/golden_20bars.csv 不得修改；新用例另建文件
