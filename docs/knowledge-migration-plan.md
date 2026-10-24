# 知识迁移落地方案

> 基于第一性原理：知识不能迁移 = 知识等于不存在。
> 本文档定义本项目知识如何在跨AI、跨会话、跨项目、跨平台间流动。

## 1. 现状盘点

| 知识层 | 位置 | 状态 |
|--------|------|------|
| **通用技能知识** | `.user_skills/quant-trading-expert/`（36份参考文档） | ✅ 已建立 |
| **项目架构文档** | `D:\Trader\docs\`（17份文档） | ✅ 已建立 |
| **项目规则** | `D:\Trader\AGENTS.md` | ✅ 已建立 |
| **Git仓库** | Gitee: taoaiguo/quant-trading-system | ✅ 已推送 |
| **飞书云文档** | 未同步 | ❌ 待做 |
| **决策审计日志** | 数据库表未建 | ❌ 待做 |
| **运行时知识沉淀** | 代码层未实现 | ❌ 待做 |

## 2. 单一事实来源（SSOT）架构

```
权威源：Git仓库（Gitee + 本地D:\Trader）
    │
    ├──→ 本地技能包（.user_skills/quant-trading-expert/）
    │     用途：AI对话时自动加载，提供通用量化知识
    │     同步方式：从Git仓库skills/目录复制
    │
    ├──→ 项目docs/（D:\Trader\docs/）
    │     用途：项目特定知识，AGENTS.md + ADR + FAQ + 架构文档
    │     同步方式：Git直接管理
    │
    ├──→ 飞书云文档（未来）
    │     用途：团队协作、可视化展示
    │     同步方式：从Git单向import，不回写
    │
    └──→ GitHub备份（未来）
          用途：公开备份、跨网络访问
          同步方式：git push
```

## 3. 跨会话知识启动清单

每次新开对话，按此顺序让AI加载知识：

```
Step 1: 读 AGENTS.md
  → 项目是什么、三条不可协商不变量、目录边界、命令、停止条件

Step 2: 读 docs/README.md
  → 项目全貌、当前状态、下一步

Step 3: 读 docs/faq.md
  → 常见问题与解决方案（避免重复踩坑）

Step 4: 读最近的ADR（docs/decisions/）
  → 最近做了什么架构决策

Step 5: 明确本轮任务
  → 告诉AI这次要解决什么问题
```

## 4. 跨项目知识复用规则

### 通用知识 → 抽象到技能包

判断标准：这个经验是否适用于任何量化交易项目？

| 项目经验 | 处理方式 |
|---------|---------|
| "统一数据模型，单一事实来源" | ✅ 已抽象到 system-optimization-patterns.md |
| "错误信息要明确指出缺少哪个字段" | ✅ 已抽象到 system-optimization-patterns.md |
| "知识沉淀四层模型" | ✅ 已抽象到 knowledge-management.md |
| "跨AI知识迁移机制" | ✅ 已抽象到 knowledge-migration.md |
| "strategyV2.sourceRequired错误怎么修" | ❌ QuantDinger特定，留在docs/faq.md |
| "Docker端口映射要在compose里固定" | ⚠️ 通用，但偏Docker运维，已在docker-troubleshooting.md |

### 项目特定知识 → 留在docs/

- 项目架构图、ADR、FAQ、实验记录、复盘报告
- 数据库表结构、API端点、配置参数
- 故障记录、解决方案、代码提交

## 5. 跨平台同步计划

### Phase 1: Git为主（已完成）
- [x] 代码 + 文档都在Git仓库
- [x] Gitee推送成功
- [x] 技能包在本地.user_skills/

### Phase 2: 飞书同步（下一步）
- [ ] 把核心文档导入飞书云文档
- [ ] 建立飞书Wiki知识空间
- [ ] 团队协作时在飞书讨论，结论回写Git

### Phase 3: GitHub备份
- [ ] 解决GitHub推送网络问题
- [ ] 建立GitHub → Gitee双向镜像
- [ ] 公开README和核心文档

## 6. 知识过期管理

每条知识文档头部标注：

```yaml
---
status: stable          # draft / stable / archived / deprecated
last_verified: 2026-10-25
applicable_to: [QuantDinger, PostgreSQL, Docker]
---
```

- **draft**：刚写，未经验证
- **stable**：经过实战验证，当前有效
- **archived**：不再用，但保留参考价值
- **deprecated**：已被新方案替代，不要使用

## 7. 日常知识沉淀流程

```
遇到问题
  ↓
解决问题
  ↓
判断：这是项目特定问题还是通用经验？
  ├── 项目特定 → 记录到 docs/faq.md 或 docs/decisions/
  └── 通用经验 → 抽象后更新到技能包 references/
  ↓
Git commit + push
  ↓
定期同步到飞书/GitHub
```

## 8. 工作纪律

- **Git是唯一权威源**：所有知识修改在Git里做commit
- **飞书是视图不是源**：不要在飞书里编辑后再回写
- **按需加载**：不要把整个知识库塞给AI，SKILL.md做索引，references按需读
- **知识会过期**：每条知识标注状态和最后验证时间
- **沉淀是习惯不是任务**：每次解决问题后花5分钟记录经验
