import re

with open('frontend-pro/index.html', 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.split('\n')

print("=== HTML结构诊断 ===")
print(f"总行数: {len(lines)}")
print(f"文件大小: {len(content)} bytes")

# 1. div标签平衡检查
stack = []
unclosed = []
for i, line in enumerate(lines, 1):
    opens = len(re.findall(r'<div\b', line))
    closes = len(re.findall(r'</div>', line))
    for _ in range(opens):
        stack.append((i, line.strip()[:80]))
    for _ in range(closes):
        if stack:
            stack.pop()
        else:
            print(f"  ⚠️ Line {i}: 多余的</div>")

print(f"\n未闭合div数量: {len(stack)}")
if stack:
    print("未闭合div位置:")
    for line_num, line_text in stack[:10]:
        print(f"  Line {line_num}: {line_text}")

# 2. page-view元素检查
print("\n=== 页面视图元素 ===")
page_views = re.findall(r'<div class="page-view" id="page-(\w+)"', content)
print(f"找到的页面: {page_views}")
print(f"页面数量: {len(page_views)}")

# 3. nav-item数据检查
print("\n=== 导航项 ===")
nav_items = re.findall(r'<div class="nav-item[^"]*" data-page="(\w+)"', content)
print(f"导航项: {nav_items}")
print(f"导航数量: {len(nav_items)}")

# 4. 检查匹配
print("\n=== 匹配检查 ===")
nav_set = set(nav_items)
page_set = set(page_views)
print(f"导航有但页面没有: {nav_set - page_set}")
print(f"页面有但导航没有: {page_set - nav_set}")

# 5. script标签检查
open_scripts = len(re.findall(r'<script\b', content))
close_scripts = len(re.findall(r'</script>', content))
print(f"\nscript标签: 开{open_scripts} 闭{close_scripts}")

# 6. 检查页面切换函数
print("\n=== 页面切换逻辑 ===")
if 'showPage' in content:
    print("✓ showPage函数存在")
else:
    print("✗ showPage函数不存在")

if 'nav-item' in content and 'addEventListener' in content:
    print("✓ 导航事件监听存在")
else:
    print("✗ 导航事件监听可能缺失")
