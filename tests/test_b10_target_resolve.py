# -*- coding: utf-8 -*-
"""B10 收口批回归（2026-09-13）—— ①目标串解析 → actor ②胜利结算怪等级读口。

① `_resolve_target_arg`（`content/combat_cmds.py`）：命令层原来把『攻击 <名字>』/『技能1 a2』的
   **字符串**直传引擎（`ActCtx.target` 只认 actor dict）→ 伤害落地段 `target.get("hp")` 抛
   `AttributeError: 'str' object has no attribute 'get'`；而站位图面板一直教玩家『技能1 a2』。
   本测试钉两件事：(a) 编号解析结果 == **面板上显示的那个编号**（同源 `formation.numbered_units`）；
   (b) 解析不中 → `None`（= 自动选敌），**绝不把字符串交给引擎**。

② `_mon_lv`（`content/settlement.py`）：`bridge.monster_to_actor` 把 `lv → level` 且**不透传 lv**，
   而胜利结算原来 3 处 `monster["lv"]` 直接下标 → 每次击杀抛 `KeyError: 'lv'`（改前既有）。
   本测试钉：actor dict（`level`）/ 原始怪 dict（`lv`）/ 缺字段 三种形态都能取到等级，
   且 `settlement.py` 里不再有 `monster["lv"]` 直读。

跑法：python tests/test_b10_target_resolve.py
"""
import ast
import os
import re
import sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
sys.path.insert(0, PLUGIN)
_shim = os.path.join(PLUGIN, "tests", "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN, "test_b10_target_resolve.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")

# ★ P5F 前置②（去壳）：原装配口 = 待删壳 `game.bootstrap.package_apply()`
#   （`from game import bootstrap as BST`）。终态 `game/**` 删除后该 import 直接 ImportError。
#   换成测试侧**引擎通道装配口** `_engine_harness.boot`（幂等；内部即 `load_package`，
#   与旧壳 `package_apply()` 同一件事：加载包 + 扇出 `bind_host` 注入面）。
_TESTS_DIR = os.path.join(PLUGIN, "tests")
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
from _engine_harness import boot as _eng_boot                    # noqa: E402

_eng_boot()
from saintess_engine import Battle as BT, make_actor             # noqa: E402
from saintess_engine.formation import alive_units, formation_view  # noqa: E402
from content.combat_cmds import _resolve_target_arg              # noqa: E402
from content.settlement import _mon_lv                           # noqa: E402

PASS = FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✅ %s" % name)
    else:
        FAIL += 1
        FAILURES.append("%s: %s" % (name, detail))
        print("  ❌ %s %s" % (name, detail))


def _a(uid, side, rank=2, hp=100, name=None):
    _st = dict(hp=hp, max_hp=hp, atk=30, matk=10, mdef=5, spd=50, crit=0.0, level=10)
    _st["def"] = 5                      # `def` 是关键字，只能这样塞
    a = make_actor(uid=uid, name=name or uid, side=side,
                   kind="player" if side == "player" else "monster",
                   human_controlled=(side == "player"), **_st)
    a["rank"] = rank
    return a


def _battle():
    """2 层敌（rank1 一只、rank2 两只）+ 玩家 —— 编号 a1..a3 / b1。"""
    p = _a("p1", "player", rank=2, name="甲")
    e1 = _a("e1", "enemy", rank=1, name="野狼")
    e2 = _a("e2", "enemy", rank=2, name="黑熊")
    e3 = _a("e3", "enemy", rank=2, name="深渊信徒")
    b = BT(btype="monster", sides={"player": [p], "enemy": [e1, e2, e3]})
    b._now = 0.0
    return b, p, [e1, e2, e3]


print("【1】编号解析 == 面板标签（同源 numbered_units）")
b, p, enemies = _battle()
labels = {}
for row in formation_view(alive_units(b.sides["enemy"]), side="enemy"):
    for seg in row.split(" | "):
        m = re.match(r"^(a\d+)\s+(\S+)", seg.strip())
        if m:
            labels[m.group(1)] = m.group(2)
print("     面板敌方标签：%s" % labels)
for lab, nm in sorted(labels.items()):
    got = _resolve_target_arg(b, lab)
    check("『%s』→ 面板上那只（%s）" % (lab, nm), bool(got) and got.get("name") == nm,
          "解析得 %r" % (got or {}).get("name"))
check("『b1』→ 我方玩家", (_resolve_target_arg(b, "b1") or {}).get("uid") == "p1")

print("【2】纯数字 / 大小写 / 名字 / 兜底")
check("『2』= a2（面板引导『纯数字同义』）", (_resolve_target_arg(b, "2") or {}).get("uid") == "e2",
      (_resolve_target_arg(b, "2") or {}).get("uid"))
check("『A3』大小写不敏感 → a3", (_resolve_target_arg(b, "A3") or {}).get("uid") == "e3")
check("名字精确『黑熊』→ e2", (_resolve_target_arg(b, "黑熊") or {}).get("uid") == "e2")
check("名字前缀『深渊』→ e3", (_resolve_target_arg(b, "深渊") or {}).get("uid") == "e3")
check("名字包含『信徒』→ e3", (_resolve_target_arg(b, "信徒") or {}).get("uid") == "e3")
for bad in ("", "   ", "不存在的东西", "a9", "b9", "0"):
    _got = _resolve_target_arg(b, bad)
    check("解析不中『%s』→ None（不再把字符串给引擎）" % bad, _got is None, repr(_got))
check("None 入参 → None（无参=自动选敌）", _resolve_target_arg(b, None) is None)
b.sides["enemy"][1]["hp"] = 0                      # a2 阵亡
check("尸体不算：a2 死后『2』落到下一个存活单位",
      (_resolve_target_arg(b, "2") or {}).get("uid") == "e3",
      (_resolve_target_arg(b, "2") or {}).get("uid"))
check("battle_state dict 形态也可解析（instance 分支用）",
      (_resolve_target_arg({"sides": {"enemy": [{"uid": "x", "hp": 5, "rank": 1, "name": "x"}]}}, "a1") or {}
       ).get("uid") == "x")

print("【3】胜利结算怪等级读口 _mon_lv")
check("actor dict（只有 level=88）→ 88", _mon_lv({"level": 88}) == 88)
check("原始怪 dict（lv=88）→ 88", _mon_lv({"lv": 88}) == 88)
check("两者都有 → 优先 lv", _mon_lv({"lv": 7, "level": 88}) == 7)
check("都缺 → 1", _mon_lv({}) == 1)
check("非 dict / None → 1", _mon_lv(None) == 1 and _mon_lv("x") == 1)
_settle = os.path.join(PLUGIN, "content", "settlement.py")
with open(_settle, encoding="utf-8") as f:
    _src = f.read()
_ast = ast.parse(_src)
# 用 AST 数（不看注释/文档字符串 —— 纯文本扫会把我这条说明自己数进去，源码扫描式门禁的老坑）
_bad_lv = [n.lineno for n in ast.walk(_ast)
           if isinstance(n, ast.Subscript) and getattr(n.value, "id", "") == "monster"
           and isinstance(n.slice, ast.Constant) and n.slice.value == "lv"]
_calls = [n.lineno for n in ast.walk(_ast)
          if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_mon_lv"]
check("settlement.py 不再有 monster[\"lv\"] 直读下标（回归哨兵，AST 口径）", not _bad_lv,
      "仍在行 %s" % _bad_lv)
check("settlement.py 里 _mon_lv 用在 3 处（pet/roll_drop/exp_curve）", len(_calls) == 3,
      "实际 %d 处：行 %s" % (len(_calls), _calls))

print("【4】we_dot 文案占位符（改前既有缺陷：`_DOT_LOG` 从不 .format()）")
from content.mech.we_procs import we_dot, _DOT_LOG             # noqa: E402
_b2, _p2, _e2 = _battle()
for _k, _v in sorted(_DOT_LOG.items()):
    _logs = []
    we_dot(_b2, _p2, _e2[0], {"key": _k, "dot_key": _k, "amount": 1, "turns": 4}, _logs)
    _txt = _logs[0] if _logs else ""
    check("『%s』文案无残留占位符（%s）" % (_k, _txt[:26]), "{" not in _txt and _txt, _txt)
_logs2 = []
we_dot(_b2, _p2, _e2[0], {"key": "不存在的key", "dot_key": "bleed", "amount": 1, "turns": 4}, _logs2)
check("缺 key 走兜底文案且已填好（%s）" % (_logs2[0][:26] if _logs2 else ""),
      bool(_logs2) and "{" not in _logs2[0])

print("\n=== 结果 PASS=%d FAIL=%d ===" % (PASS, FAIL))
if FAILURES:
    print("失败项：")
    for x in FAILURES:
        print("  - %s" % x)
sys.exit(1 if FAIL else 0)
