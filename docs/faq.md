# 常见问题与解决方案（FAQ）

## 实盘相关

### Q: 启动策略报错 `strategyV2.sourceRequired`
**A:** 策略缺少 `source_version_id` 关联。

**解决步骤：**
1. 检查策略是否设置了 `source_version_id`
2. 如果没有，关联一个现有的源代码版本
3. 数据库触发器会自动同步到 `trading_config`

**SQL 修复示例：**
```sql
-- 为策略设置 source_version_id
UPDATE qd_strategies_trading
SET source_version_id = 15
WHERE id = 1;
```

---

### Q: 前端显示策略"运行中"，但实际是"已停止"
**A:** 前后端状态不同步。

**解决步骤：**
1. 检查后端策略状态：`SELECT id, status FROM qd_strategies_trading;`
2. 刷新前端页面
3. 如果还是不对，检查前端 API 调用是否正确

---

### Q: 回测显示总收益率 0%，但权益曲线明显上涨
**A:** 回测汇总指标没有被正确计算或保存。

**原因：** 回测完成后需要计算汇总指标（total_return、sharpe、max_drawdown 等）并保存到数据库。

**检查：**
```sql
SELECT id, total_return, sharpe, max_drawdown
FROM qd_backtest_runs
WHERE id = 5;
```

---

## 部署相关

### Q: Docker 容器启动了，但 API 连不上
**A:** 可能是端口映射或 API 前缀问题。

**排查步骤：**
1. 检查容器是否在运行：`docker ps`
2. 检查端口映射：`docker port quantdinger-backend`
3. 检查 API 路径是否正确：默认前缀是 `/api/agent/v1`
4. 检查环境变量是否加载：`docker exec quantdinger-backend env`

**常见坑：**
- 手动 `docker run` 启动，端口映射配置丢失
- API 前缀少了 `/api`

---

## 数据模型相关

### Q: 创建策略时需要手动设置很多字段，容易遗漏
**A:** 这是旧的设计。现在应该自动关联。

**正确流程：**
1. 用户只需要输入策略名称 + 选择源代码版本
2. 系统自动：
   - 从 source_version 找到 source
   - 设置 source_version_id
   - 自动填充 trading_config
   - 验证完整性

---

## 验证层相关

### Q: 什么是 AI 验证层守门员？
**A:** 策略上线前的"守门员"，包含五层检查：
1. 过拟合检测
2. 前视偏差扫描
3. 漂移监控
4. 压力测试
5. 组合风控

**设计原则：** 优雅降级——如果某个模块不可用，自动降级到简化版，不要崩溃。
