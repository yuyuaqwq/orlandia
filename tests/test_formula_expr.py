# -*- coding: utf-8 -*-
"""v159 表达式公式解释器测试——compile_expr/eval_expr 全覆盖。

运行：python tests/test_formula_expr.py（exit=0 全绿）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: E402  ← 引擎根发现（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）

# 正常包导入。★ R4-4（2026-09-28）：原先这里用 `spec_from_file_location` 按**文件路径**
# 加载引擎模块（"不走包 __init__，避免循环导入"）。但 `saintess_engine/expr/__init__.py`
# 自 E4（`c3eb91b`, 2026-09-25 21:26）起有**包内相对 import**（`from ..config import
# EngineNotConfigured` / `from .. import config as _cfg`）⇒ 按路径加载拿不到包上下文
# ⇒ import 期就抛 `ImportError: attempted relative import beyond top-level package`
#   （一条断言都跑不到）。同仓 `tests/test_v160_exprs.py:25` 早已是正常包导入，照它写。
from saintess_engine.expr import (  # noqa: E402
    compile_expr, eval_expr, build_vars, ExprError)

passed = failed = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")


def approx(a, b, eps=1e-6):
    return abs(a - b) < eps


print("【1. 基础四则运算】")
check("1+2=3", approx(eval_expr("1+2"), 3))
check("10-3=7", approx(eval_expr("10-3"), 7))
check("6*7=42", approx(eval_expr("6*7"), 42))
check("10/4=2.5", approx(eval_expr("10/4"), 2.5))
check("含小数 1.5*2=3", approx(eval_expr("1.5*2"), 3))

print("\n【2. 优先级】")
check("2+3*4=14", approx(eval_expr("2+3*4"), 14))
check("(2+3)*4=20", approx(eval_expr("(2+3)*4"), 20))
check("10-2-3=5", approx(eval_expr("10-2-3"), 5))
check("20/2*5=50", approx(eval_expr("20/2*5"), 50))
check("嵌套 (1+2)*(3+4)=21", approx(eval_expr("(1+2)*(3+4)"), 21))

print("\n【3. 变量】")
vars_ = {"atk": 100, "player_lv": 24, "skill_lv": 5, "max_hp": 500}
check("atk*0.8=80", approx(eval_expr("atk*0.8", vars_), 80))
check("atk*0.8 + player_lv*5=220", approx(eval_expr("atk*0.8 + player_lv*5", vars_), 80 + 120))
check("(atk*0.8 + player_lv*5) * (1 + skill_lv*0.1)=300", approx(eval_expr("(atk*0.8 + player_lv*5) * (1 + skill_lv*0.1)", vars_), 300))
check("max_hp*0.05 + atk*0.3=55", approx(eval_expr("max_hp*0.05 + atk*0.3", vars_), 25 + 30))
# ★ 2026-09-29（引擎审计 L1281 #3）本条**换口径**：原断言钉「未声明变量名静默取 0」，
#   那正是被修掉的静默失效（拼错一个字母 ⇒ 整条公式算出一个看起来正常的错数，无报错）。
#   改为钉**意图**（不是放宽）：变量名不在当前变量表 ⇒ 编译期抛 ExprError，现形在装配期。
try:
    eval_expr("missing*2", vars_)
    check("★ 未声明变量名 ⇒ 抛（不再静默取 0）", False)
except ExprError:
    check("★ 未声明变量名 ⇒ 抛（不再静默取 0）", True)
# 合法名字取值为 0 仍是允许的（属性表里没这一条 ⇒ 该变量本期就是 0，不是拼错）：
check("已声明变量取到 0 照常算", approx(eval_expr("crit*2", vars_), 0))

print("\n【4. 一元负号】")
check("-5=-5", approx(eval_expr("-5"), -5))
check("10 + -3=7", approx(eval_expr("10 + -3"), 7))
check("-(2+3)=-5", approx(eval_expr("-(2+3)"), -5))
check("atk * -1=-100", approx(eval_expr("atk * -1", vars_), -100))

print("\n【5. 除零】")
check("1/0=0（安全）", approx(eval_expr("1/0"), 0))

print("\n【6. 错误处理】")
try:
    eval_expr("1+")
    check("'1+' 报错", False)
except ExprError:
    check("'1+' 报错", True)
try:
    eval_expr("(1+2")
    check("'(1+2' 报错", False)
except ExprError:
    check("'(1+2' 报错", True)
try:
    eval_expr("1 2 3")
    check("'1 2 3' 报错", False)
except ExprError:
    check("'1 2 3' 报错", True)

print("\n【7. 预编译性能】")
code = compile_expr("(atk*0.8 + player_lv*5) * (1 + skill_lv*0.1) + max_hp*0.02")
import time
N = 100000
t0 = time.time()
for _ in range(N):
    eval_expr(code, vars_)
dt = time.time() - t0
print(f"  10万次求值: {dt*1000:.1f}ms（{dt/N*1e6:.2f}µs/次）")
check("10万次求值 < 500ms", dt < 0.5)

print("\n【8. build_vars】")
v = build_vars({"atk": 100, "matk": 80, "max_hp": 500}, player_lv=24, skill_lv=5)
check("atk=100", v["atk"] == 100)
check("player_lv=24", v["player_lv"] == 24)
check("skill_lv=5", v["skill_lv"] == 5)
check("target_max_hp 缺省=max_hp", v["target_max_hp"] == 500)
check("crit_mult=1.5", v["crit_mult"] == 1.5)

print(f"\n结果: {passed} 通过 / {failed} 失败")
sys.exit(1 if failed else 0)
