"""列出Flask应用的所有路由。"""
import sys
sys.path.insert(0, '.')

from app import create_app
app = create_app()

print("=== 所有路由 ===")
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
    print(f"{rule.rule:50s} [{methods}]")
