import re

with open('frontend-pro/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

stack = []
for i, line in enumerate(lines, 1):
    opens = len(re.findall(r'<div\b', line))
    closes = len(re.findall(r'</div>', line))
    for _ in range(opens):
        stack.append(i)
    for _ in range(closes):
        if stack:
            stack.pop()
        else:
            print(f'Line {i}: extra </div>')

print(f'Unclosed divs: {len(stack)}')
print(f'Unclosed starts at lines: {stack[:30]}')
