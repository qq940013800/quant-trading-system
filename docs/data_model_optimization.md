# QuantDinger 数据模型统一与错误处理优化方案

> 基于第一性原理和全球顶级量化机构最佳实践

---

## 一、当前问题分析（第一性原理）

### 1.1 数据冗余问题

**当前数据模型：**
```
qd_strategies_trading 表
├── source_version_id (数据库字段)
└── trading_config (JSONB)
    ├── script_source_id
    └── script_source_version_id
```

**问题本质：**
- 同一信息（策略源代码关联）存储在**两个不同的地方**
- 后端代码优先检查 `trading_config.script_source_id`，如果不存在就报错
- 创建策略时需要**手动同步**两个地方的数据，容易遗漏

**为什么会出现这种问题？**
- 历史演进：早期版本只有 `trading_config`，后来加了 `source_version_id` 字段
- 没有做数据迁移和向后兼容
- 缺乏统一的数据访问层

### 1.2 错误信息问题

**当前错误：**
```
strategyV2.sourceRequired
```

**问题：**
- 没有说明具体缺少哪个字段
- 没有说明应该怎么修复
- 用户不知道是 `source_id` 还是 `version_id` 还是 `code`

### 1.3 创建流程问题

**当前流程：**
1. 创建策略时需要先创建 source
2. 然后创建 version
3. 然后创建 strategy
4. 然后手动设置 `source_version_id`
5. 然后手动设置 `trading_config.script_source_id`
6. 然后手动设置 `trading_config.script_source_version_id`

**问题：**
- 步骤太多，容易出错
- 没有原子性保证
- 没有统一的创建接口

---

## 二、全球最佳实践参考

### 2.1 Renaissance Technologies 的做法

- **单一事实来源（Single Source of Truth）**：每个数据只存储在一个地方
- **数据访问层（DAO）**：所有数据访问都通过统一的DAO层
- **自动关联**：创建策略时自动关联source和version，不需要手动设置

### 2.2 Two Sigma 的做法

- **明确的错误信息**：错误信息必须包含：
  - 缺少的字段名
  - 字段所在的位置
  - 修复建议
- **优雅降级**：向后兼容，新旧字段同时支持

### 2.3 Jane Street 的做法

- **统一的数据模型**：
  - `source_id` 和 `version_id` 是核心字段
  - `trading_config` 只存储策略特定的配置参数
  - 不存储核心关系字段

---

## 三、优化方案设计

### 3.1 数据模型统一方案

**方案A：推荐方案（向后兼容）**

**核心原则：** `source_version_id` 是单一事实来源，`trading_config` 里的是冗余的。

```python
# 统一的数据访问层
def get_strategy_source_info(strategy: dict) -> tuple[int, int]:
    """
    统一获取策略源代码信息
    优先级：source_version_id -> trading_config -> 错误
    """
    # 第一步：优先从 source_version_id 获取（新方式）
    source_version_id = int(strategy.get("source_version_id") or 0)
    
    if source_version_id > 0:
        # 从 source_version 表反查 source_id
        source = get_script_source_service().get_version(source_version_id)
        if source:
            source_id = int(source.get("source_id") or 0)
            return source_id, source_version_id
    
    # 第二步：兼容旧方式（从 trading_config 读取）
    trading_config = _json_object(strategy.get("trading_config"))
    source_id = int(trading_config.get("script_source_id") or 0)
    source_version_id = int(trading_config.get("script_source_version_id") or 0)
    
    if source_id > 0 and source_version_id > 0:
        # 自动同步到 source_version_id 字段
        strategy["source_version_id"] = source_version_id
        return source_id, source_version_id
    
    # 第三步：都没有，抛出明确错误
    raise StrategySourceError(
        "策略缺少源代码关联信息",
        missing_fields=[
            "qd_strategies_trading.source_version_id",
            "trading_config.script_source_id",
            "trading_config.script_source_version_id"
        ],
        fix_hint="创建策略时请通过 create_strategy_with_source() 接口，自动关联源代码"
    )
```

### 3.2 错误信息改进方案

**新的错误格式：**
```python
class StrategySourceError(Exception):
    """策略源代码关联错误"""
    def __init__(self, message: str, missing_fields: list[str] = None, fix_hint: str = None):
        self.message = message
        self.missing_fields = missing_fields or []
        self.fix_hint = fix_hint
        super().__init__(self.format_error())
    
    def format_error(self) -> str:
        lines = [f"❌ {self.message}"]
        if self.missing_fields:
            lines.append("缺少的字段：")
            for f in self.missing_fields:
                lines.append(f"  - {f}")
        if self.fix_hint:
            lines.append(f"💡 修复建议：{self.fix_hint}")
        return "\n".join(lines)
```

**错误输出示例：**
```
❌ 策略缺少源代码关联信息
缺少的字段：
  - qd_strategies_trading.source_version_id
  - trading_config.script_source_id
  - trading_config.script_source_version_id
💡 修复建议：创建策略时请通过 create_strategy_with_source() 接口，自动关联源代码
```

### 3.3 创建流程优化方案

**新的统一创建接口：**
```python
def create_strategy_with_source(
    user_id: int,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    source_id: int,
    version_no: int = None,  # None = 使用最新版本
    trading_config: dict = None
) -> dict:
    """
    创建策略并自动关联源代码
    一站式完成：source检查 -> version选择 -> strategy创建 -> 字段同步
    """
    # 1. 验证 source 存在
    source = get_script_source_service().get(source_id, user_id)
    if not source:
        raise SourceNotFoundError(f"策略源代码不存在: {source_id}")
    
    # 2. 获取指定版本（或最新版本）
    if version_no is None:
        version = get_script_source_service().get_latest_version(source_id, user_id)
    else:
        version = get_script_source_service().get_version_by_no(source_id, version_no, user_id)
    
    if not version:
        raise VersionNotFoundError(f"策略源代码版本不存在: source={source_id}, version={version_no}")
    
    # 3. 创建 strategy 记录
    strategy = {
        "user_id": user_id,
        "strategy_name": strategy_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "source_version_id": version["id"],  # 自动设置
        "trading_config": trading_config or {}
    }
    
    # 4. 自动同步 trading_config
    strategy["trading_config"]["script_source_id"] = source_id
    strategy["trading_config"]["script_source_version_id"] = version["id"]
    
    # 5. 保存到数据库
    strategy_id = save_strategy(strategy)
    
    return {**strategy, "id": strategy_id}
```

---

## 四、实施路线图

### Phase 1: 错误信息改进（快速见效）
1. ✅ 创建 `StrategySourceError` 异常类
2. ✅ 改进 `_load_source()` 方法的错误信息
3. ✅ 测试错误信息是否清晰

### Phase 2: 统一数据访问层
1. ✅ 创建 `get_strategy_source_info()` 统一函数
2. ✅ 替换所有直接访问的代码
3. ✅ 添加自动同步逻辑

### Phase 3: 统一创建接口
1. ✅ 创建 `create_strategy_with_source()` 接口
2. ✅ 前端创建策略时调用这个接口
3. ✅ 弃用手动设置字段的方式

### Phase 4: 数据清理（长期）
1. ⚠️ 数据迁移脚本：从 trading_config 同步到 source_version_id
2. ⚠️ 长期：移除 trading_config 里的冗余字段
3. ⚠️ 添加数据库约束，保证一致性

---

## 五、文档优化

### 5.1 开发者文档

**策略数据模型说明：**
```
qd_strategies_trading 表核心字段：
├── id: 策略ID
├── strategy_name: 策略名称
├── symbol: 交易品种
├── timeframe: 时间周期
├── source_version_id: 【核心】关联的策略源代码版本ID
└── trading_config: 策略特定配置（不存储核心关系字段）

注意：
- source_version_id 是单一事实来源
- trading_config 里的 script_source_id 是为了向后兼容的冗余字段
- 新代码请优先使用 source_version_id
```

### 5.2 常见错误排查文档

**错误：strategyV2.sourceRequired**

**原因：** 策略没有关联源代码

**排查步骤：**
1. 检查 `source_version_id` 字段是否有值
2. 检查 `trading_config.script_source_id` 是否有值
3. 检查 `trading_config.script_source_version_id` 是否有值

**修复方法：**
- 推荐：使用 `create_strategy_with_source()` 重新创建策略
- 临时：手动设置上述三个字段

---

## 六、总结

### 核心改进点

| 改进项 | 之前 | 之后 |
|--------|------|------|
| 数据模型 | 同一信息存储在2个地方 | 单一事实来源（source_version_id） |
| 错误信息 | 模糊的错误代码 | 明确的字段名+修复建议 |
| 创建流程 | 手动设置3个字段 | 一键创建自动关联 |
| 向后兼容 | 不兼容 | 自动同步，优雅降级 |

### 预期收益

1. **减少bug**：不再因为字段不同步导致的错误
2. **提升开发效率**：创建策略更简单，错误信息更清晰
3. **提升可维护性**：统一数据模型，易于理解和维护
4. **更好的用户体验**：错误信息清晰，修复路径明确
