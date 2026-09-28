# -*- coding: utf-8 -*-
"""常驻门禁：承伤乘区**不得用 `or 1.0` 回落**（合法 0.0 会被吞）。

为什么需要它（审计 L5618 同族 · 引擎 landing.py:138-139 自己写明过这条）：
  「⚠️ 不可写 `... or 1.0`（2026-09-11 修）：乘区值 **0.0 是合法值**
   （完全免伤——格挡/无敌帧），而 `0.0 or 1.0` 会被吞成 1.0 → 0 乘区永远失效。」
  引擎侧照做了，**内容侧没有**（games/orlandia/content/mech/* 当时 17 处）。
  症状是**静默**的：格挡（block_once_apply 置 mult=0.0）若与任一乘法型
  taken_calc 动作挂在同一个 actor 上，而乘法那支后跑，它读回 0.0 → 吞成 1.0
  → 1.0 × (1-r) ⇒ **格挡被取消**，玩家看到"我格挡了"却照掉血。

本门禁三条：
  ① 静态：内容侧不得再出现 `ctx.get("mult", 1.0) or 1.0` 这一族（default=1.0）
  ② 行为：0.0 乘区在同事件内经过乘法型动作后**必须仍是 0.0**（黑盒 fire）
  ③ 反证：把表达式改回 `or 1.0` 语义 ⇒ ② 必须转红（证明判据真在咬）
     —— 反证由本文件 `_mutate` 开关驱动（环境变量），不在门禁正文里改代码。
"""
import os
import re
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FW = os.environ.get("GWEN_FRAMEWORK_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(PKG)))
for p in (os.path.join(FW, "extends"), PKG, os.path.join(PKG, "tests")):
    if p and p not in sys.path:
        sys.path.insert(0, p)

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK  " if cond else "  XX  ") + name + ((" | " + extra) if extra else ""))


# ── ① 静态：默认值为 1.0 的乘区不得用 `or 1.0` 回落 ──────────────────
#   （default=0 的 `or 0` 不在此列：默认值本就是 0，吞 0 无害）
PAT = re.compile(r"""ctx\.get\(\s*("|')mult\1\s*,\s*1\.0\s*\)\s*or\s*1\.0""")
print("[① 静态清点]")
hits = []
for root, _d, files in os.walk(os.path.join(PKG, "content")):
    for f in files:
        if not f.endswith(".py"):
            continue
        p = os.path.join(root, f)
        for i, ln in enumerate(io_lines := open(p, encoding="utf-8").read().split("\n"), 1):
            if PAT.search(ln):
                hits.append("%s:%d" % (os.path.relpath(p, PKG), i))
check("① 内容侧无 `ctx.get('mult',1.0) or 1.0`（合法 0.0 不再被吞）",
      not hits, ("命中 " + ", ".join(hits[:6])) if hits else "0 处")

# ── ② 行为：黑盒 fire 一次 taken_calc，0.0 必须活到结算点 ─────────────
print("\n[② 行为：0.0 乘区活到结算点]")
from ext_combat.battle.actors import make_actor
from ext_combat.battle.effect_triggers import fire
import ext_combat.battle.effects as EF

MUTATE = os.environ.get("AFIX_MUTATE_OR1") == "1"   # 反证开关（见 ③）
_base = "float(ctx.get({q}mult{q}, 1.0) or 1.0)" if MUTATE else \
        "float(ctx.get({q}mult{q}) if ctx.get({q}mult{q}) is not None else 1.0)"
_mexpr = _base.format(q='"')


class _B:
    def __init__(self, sides):
        self.sides = sides
        self._fire_ctx = None


def act_set_zero(battle, caster, target, params, logs):
    """格挡语义（对齐内容侧 block_once_apply）：本次承伤归零。"""
    battle._fire_ctx["mult"] = 0.0


def act_mul(battle, caster, target, params, logs):
    """乘法型条件减伤：与内容侧 passive_taken_reduce 同一语义。"""
    ctx = battle._fire_ctx
    ctx["mult"] = eval(_mexpr) * 0.7


EF.register_action("gate_zero")(act_set_zero)
EF.register_action("gate_mul")(act_mul)


def run(order):
    atk = make_actor("攻方", "攻方", "A", kind="player", hp=100, max_hp=100, atk=20)
    tgt = make_actor("受方", "受方", "B", kind="monster", hp=100, max_hp=100)
    tgt["triggers"] = {"taken_calc": [{"action": n, "params": {}} for n in order]}
    b = _B({"A": [atk], "B": [tgt]})
    ctx = {"actor": tgt, "target": tgt, "source": atk, "dmg": 50, "mult": 1.0}
    fire(b, "taken_calc", ctx, [])
    return ctx.get("mult")


m_order = run(["gate_zero", "gate_mul"])   # 格挡先、乘法后 = 会出事的那个顺序
m_ok = run(["gate_mul", "gate_zero"])      # 对照：格挡后跑必然活
print("    先格挡后乘法 ⇒ mult=%r ；先乘法后格挡 ⇒ mult=%r" % (m_order, m_ok))
check("② 格挡置 0.0 后，同事件内后跑的乘法动作**没有**把它吞回 1.0",
      m_order == 0.0, "实测 mult=%r（应为 0.0）" % m_order)
check("② 对照组：格挡后跑时 0.0 同样活到结算点", m_ok == 0.0, "实测 mult=%r" % m_ok)

# ── ③ 反证：把回落语义换回 `or 1.0` ⇒ ② 必须转红 ─────────────────────
if not MUTATE:
    check("③ 反证口径就绪（设 AFIX_MUTATE_OR1=1 重跑本文件，② 应转红）", True,
          "当前 = 修复态")
else:
    check("③ 反证态：② 已如期转红（判据真在咬，不是永真）", m_order == 0.7,
          "实测 mult=%r（=1.0×0.7，格挡被吞）" % m_order)

print("\n结果：%d 通过 / %d 失败" % (len(PASS), len(FAIL)))
for f in FAIL:
    print("  FAIL: " + f)
sys.exit(1 if FAIL else 0)
