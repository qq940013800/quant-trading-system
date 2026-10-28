#!/usr/bin/env python3
"""
错误自动追踪脚本
用法：
  python scripts/error_tracker.py add --type "部署" --desc "API 502" --root "nginx upstream别名错误" --fix "修改nginx配置"
  python scripts/error_tracker.py stats
  python scripts/error_tracker.py search "502"

作用：自动记录错误，统计重复次数，提示升级到RULES
"""
import sys
import os
from datetime import datetime

ERROR_LOG_PATH = "docs/ERROR_LOG.md"
RULES_PATH = "docs/RULES.md"

def add_error(error_type, desc, root_cause, fix):
    """添加错误记录"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 读取现有错误数量
    existing_count = 0
    if os.path.exists(ERROR_LOG_PATH):
        with open(ERROR_LOG_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
            existing_count = content.count("### E")
    
    error_id = f"E{existing_count + 1:03d}"
    
    new_entry = f"""
### {error_id}：{desc}

**时间**：{now}
**错误类型**：{error_type}
**严重程度**：🟡 P1

**现象**：
{desc}

**根因**：
{root_cause}

**修复方案**：
{fix}

**沉淀**：
- ⏳ 待观察：同类错误出现≥2次后升级到RULES铁律
"""
    
    # 追加到ERROR_LOG
    with open(ERROR_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(new_entry)
    
    print(f"✅ 已记录错误 {error_id}")
    print(f"📝 位置：{ERROR_LOG_PATH}")
    print(f"\n💡 提示：如果同类错误再次出现，请运行 python scripts/error_tracker.py stats 检查是否需要升级到RULES")

def stats():
    """统计错误，提示需要升级到RULES的"""
    if not os.path.exists(ERROR_LOG_PATH):
        print("❌ ERROR_LOG.md 不存在")
        return
    
    with open(ERROR_LOG_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 统计错误类型
    lines = content.split('\n')
    error_types = {}
    for line in lines:
        if '**错误类型**' in line:
            etype = line.split('：')[1].strip()
            error_types[etype] = error_types.get(etype, 0) + 1
    
    print("=" * 50)
    print("📊 错误统计")
    print("=" * 50)
    
    total = sum(error_types.values())
    print(f"\n总错误数：{total}")
    
    print("\n按类型统计：")
    for etype, count in sorted(error_types.items(), key=lambda x: -x[1]):
        flag = " 🔴 需要升级到RULES！" if count >= 2 else ""
        print(f"  {etype}: {count} 次{flag}")
    
    # 检查RULES里有没有对应的铁律
    if os.path.exists(RULES_PATH):
        with open(RULES_PATH, 'r', encoding='utf-8') as f:
            rules_content = f.read()
        
        print("\n🔍 检查：哪些错误已经沉淀成RULES？")
        for etype, count in error_types.items():
            if count >= 2:
                if etype in rules_content:
                    print(f"  ✅ {etype}：已在RULES中")
                else:
                    print(f"  ❌ {etype}：出现{count}次，但还没沉淀成RULES铁律！")
                    print(f"     → 建议：在RULES.md新增'{etype}'相关铁律")

def search(keyword):
    """搜索历史错误经验"""
    if not os.path.exists(ERROR_LOG_PATH):
        print("❌ ERROR_LOG.md 不存在")
        return
    
    with open(ERROR_LOG_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"🔍 搜索关键词：{keyword}")
    print("=" * 50)
    
    # 按错误块分割
    blocks = content.split('### E')
    found = []
    for block in blocks[1:]:  # 跳过第一个（标题）
        if keyword.lower() in block.lower():
            found.append("### E" + block)
    
    if found:
        print(f"\n✅ 找到 {len(found)} 条相关历史经验：\n")
        for i, block in enumerate(found, 1):
            # 只打印前几行
            lines = block.strip().split('\n')[:6]
            print(f"--- 经验 {i} ---")
            for line in lines:
                print(line)
            print()
        
        print("💡 提示：查看完整内容请打开 docs/ERROR_LOG.md")
    else:
        print("\n❌ 没找到相关历史经验")
        print("💡 建议：如果这次解决了，请运行 python scripts/error_tracker.py add 记录下来")

def main():
    if len(sys.argv) < 2:
        print("用法：")
        print("  python scripts/error_tracker.py add --type <类型> --desc <现象> --root <根因> --fix <修复方案>")
        print("  python scripts/error_tracker.py stats")
        print("  python scripts/error_tracker.py search <关键词>")
        return
    
    cmd = sys.argv[1]
    
    if cmd == "add":
        # 解析参数
        args = {}
        i = 2
        while i < len(sys.argv):
            if sys.argv[i].startswith('--'):
                key = sys.argv[i][2:]
                value = sys.argv[i+1] if i+1 < len(sys.argv) else ""
                args[key] = value
                i += 2
            else:
                i += 1
        
        add_error(
            args.get('type', '未分类'),
            args.get('desc', '无描述'),
            args.get('root', '待分析'),
            args.get('fix', '待修复')
        )
    
    elif cmd == "stats":
        stats()
    
    elif cmd == "search":
        if len(sys.argv) < 3:
            print("❌ 请提供搜索关键词")
            return
        search(sys.argv[2])
    
    else:
        print(f"❌ 未知命令：{cmd}")

if __name__ == "__main__":
    main()
