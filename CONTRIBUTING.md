# 贡献指南

感谢你对 AI/ML 增强量化交易系统的关注！我们欢迎任何形式的贡献。

## 行为准则

请保持尊重和专业的交流氛围。我们致力于为每个人提供友好、安全的环境。

## 如何贡献

### 报告 Bug

如果你发现了 bug，请：
1. 搜索现有 issue 避免重复
2. 创建新 issue，包含：
   - 清晰的标题
   - 详细的描述
   - 复现步骤
   - 预期行为和实际行为
   - 环境信息（OS、Python 版本等）

### 提出新功能

如果你有新功能想法：
1. 先讨论这个功能是否符合项目方向
2. 说明这个功能解决了什么问题
3. 描述你设想的实现方式

### 提交代码

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m "Add your feature"`
4. 推送到分支：`git push origin feature/your-feature`
5. 创建 Pull Request

## 代码规范

### Python 代码
- 遵循 PEP 8 风格指南
- 使用类型提示
- 编写单元测试
- 保持函数简洁，单一职责

### 提交信息
- 使用清晰、描述性的提交信息
- 首行不超过 50 个字符
- 正文详细说明更改内容和原因

## 项目规则

### 三大不可协商的不变量
1. **因果单向**：任何计算只用 available_at <= bar.close 的数据
2. **决策可审计**：每笔接受/拒绝都能还原各层输入与判断
3. **阈值来自分布**：不由绩效网格搜索产生

### 目录边界
- 可改：core/ scripts/ ops/ tests/ docs/ reports/ experiments/
- 需人工确认才可改：configs/ registry.yaml mt5/
- 禁止改：secrets/ runtime/ ledger/

## 测试

提交代码前请确保：
```bash
# 运行全部测试
pytest tests/ -q

# 测试覆盖率
pytest --cov=core tests/
```

## 许可证

提交代码即表示你同意将你的代码以 MIT 许可证发布。

---

感谢你的贡献！🚀
