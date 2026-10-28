#!/usr/bin/env python3
"""
经验自动检索脚本
用法：python scripts/memory_search.py "API 502"

作用：遇到问题时，自动搜索所有知识文档，快速找到历史解决方案
"""
import sys
import os

# 知识文档路径
KNOWLEDGE_FILES = [
    ("ERROR_LOG", "docs/ERROR_LOG.md", "错误日志"),
    ("RULES", "docs/RULES.md", "避坑铁律"),
    ("MEMORY", "docs/MEMORY.md", "经验记忆"),
    ("SUCCESS", "docs/SUCCESS_PLAYBOOK.md", "成功经验"),
    ("ANTI_FRAGILE", "docs/ANTI_FRAGILE.md", "反脆弱清单"),
    ("WIKI", "docs/WIKI.md", "知识地图"),
]

def search_in_file(keyword, filepath, label):
    """在单个文件中搜索"""
    if not os.path.exists(filepath):
        return []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    results = []
    current_section = ""
    
    for i, line in enumerate(lines):
        # 跟踪当前章节
        if line.startswith('#'):
            current_section = line.strip()
        
        if keyword.lower() in line.lower():
            # 找到匹配行，前后各取2行作为上下文
            start = max(0, i-2)
            end = min(len(lines), i+3)
            context = ''.join(lines[start:end]).strip()
            results.append({
                'section': current_section,
                'line_num': i+1,
                'context': context
            })
    
    return results

def main():
    if len(sys.argv) < 2:
        print("=" * 60)
        print("🔍 经验自动检索 - 遇到问题先搜历史经验，不要从零开始")
        print("=" * 60)
        print("\n用法：python scripts/memory_search.py <关键词>")
        print("\n示例：")
        print("  python scripts/memory_search.py 502")
        print("  python scripts/memory_search.py docker 崩溃")
        print("  python scripts/memory_search.py OKX 下单")
        print("\n💡 提示：这是自我进化引擎的一部分")
        print("   踩坑 → 自动记录 → 下次自动检索 → 自动避免")
        return
    
    keyword = ' '.join(sys.argv[1:])
    
    print("=" * 60)
    print(f"🔍 搜索历史经验：{keyword}")
    print("=" * 60)
    
    total_results = 0
    
    for name, path, desc in KNOWLEDGE_FILES:
        results = search_in_file(keyword, path, desc)
        if results:
            print(f"\n📁 {desc} ({name}) - {len(results)} 条结果")
            print("-" * 40)
            for r in results[:3]:  # 每个文件最多显示3条
                print(f"  [{r['section']}]")
                print(f"  {r['context'][:150]}...")
                print()
            if len(results) > 3:
                print(f"  ... 还有 {len(results)-3} 条，打开 {path} 查看完整内容")
            total_results += len(results)
    
    print("\n" + "=" * 60)
    if total_results > 0:
        print(f"✅ 总共找到 {total_results} 条相关历史经验！")
        print("\n💡 建议：")
        print("  1. 先看ERROR_LOG里有没有完全一样的错误，直接用修复命令")
        print("  2. 再看RULES里有没有相关铁律，不要违反")
        print("  3. 最后看SUCCESS里有没有验证过的解决方案")
    else:
        print("❌ 没找到相关历史经验")
        print("\n💡 提示：")
        print("  1. 试试换个关键词搜索（比如用'nginx'代替'502'）")
        print("  2. 如果这次解决了，请运行 python scripts/error_tracker.py add 记录下来")
        print("  3. 这样下次遇到同样问题，系统就能自动找到解决方案了")

if __name__ == "__main__":
    main()
