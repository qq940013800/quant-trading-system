# -*- coding: utf-8 -*-
"""把 tests/test_registry 变成包：解决与 tests/test_strategy_registry.py
同 basename 的 pytest 收集冲突（import file mismatch）。

pytest 默认 prepend 导入模式下，无 __init__.py 的两个同名测试文件会被
导入成同一个模块名 `test_strategy_registry`，导致全量收集在 1 个错误处中断。
本文件只声明包边界，不改变任何测试逻辑。
"""
