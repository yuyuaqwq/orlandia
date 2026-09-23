# -*- coding: utf-8 -*-
"""v181 世界 Boss GM 伤害倍率接线验收：game/services/battle_worldboss_procs。

## 背景（回归守卫）

`gm_伤害 <倍率>` 把倍率写进 event_state，`combat.py` 讨伐时读出、作为
`Battle(..., dmg_mult=<倍率>)` 传给引擎。**battle2 引擎只存不读该参数**
（旧引擎 `_boss_dmg_filter` 里的 `dmg = int(dmg * self.dmg_mult)` 没迁过来）
→ GM 倍率静默失效，而面板仍承诺「『讨伐』时生效」。

修复 = 走引擎既有 `taken_calc` 承伤乘区（零引擎改动）。本测试锁住：

1. `apply_gm_dmg_mult` 装配形态（挂 triggers["taken_calc"]；=1.0 不挂；幂等；改回 1 撤声明）
2. **端到端**：真跑 `landing.deal_damage`，倍率确实乘在「打 Boss」的伤害上
   （10× / 0.5× / 未被挂倍率的 Boss 不受影响 = 零噪音）
3. 乘区复利正确（与既有 taken_calc 减伤同容器相加相乘，不互相覆盖）

跑法：python tests/test_v181_worldboss_gm_dmg.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_wb.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from ext_combat import Battle as B2, make_actor  # noqa: E402
from ext_combat.battle.landing import deal_damage  # noqa: E402
from _engine_harness import boot as _eng_cfg  # noqa: E402
_eng_cfg()
from content.mech import worldboss as WBP  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_player():
    return make_actor(uid="p1", name="勇者", side="player", kind="player",
                      human_controlled=True, class_name="cls_zhan_shi", level=20,
                      hp=2000, max_hp=2000, mp=200, max_mp=200,
                      atk=100, matk=80, spd=15, crit=0.0,
                      equipment={}, skills=[], learned_skills=[],
                      race=None, evolve_path=0, class_tier=0, attributes={},
                      **{"def": 40, "mdef": 30})


def mk_boss(hp=100000):
    a = make_actor(uid="e1", name="世界Boss", side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=1, matk=1, spd=5, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 0, "mdef": 0})
    a["is_boss"] = True
    a["effects"] = {}
    return a


def hit(boss, amount=1000, player=None):
    """真跑落地：玩家对 Boss 打 amount 点。返回实际扣血。"""
    p = player or mk_player()
    b = B2(btype="worldboss", sides={"player": [p], "enemy": [boss]})
    logs = []
    return deal_damage(b, p, boss, amount, logs, dmg_kind="phys")


def wb_trigs(actor):
    return [x for x in ((actor.get("triggers") or {}).get("taken_calc") or [])
            if isinstance(x, dict) and x.get("action") == "wb_gm_dmg_mult"]


def test_install():
    print("【1. 装配形态】")
    e = mk_boss()
    check("倍率 1.0 不挂声明（零噪音）", WBP.apply_gm_dmg_mult(e, 1.0) is False and not wb_trigs(e),
          f"trig={wb_trigs(e)}")
    check("倍率 10 挂上且 factor=10", WBP.apply_gm_dmg_mult(e, 10.0) is True
          and wb_trigs(e)[0].get("factor") == 10.0, f"trig={wb_trigs(e)}")
    WBP.apply_gm_dmg_mult(e, 3.0)
    check("重复调用幂等（只 1 条，值就地更新）",
          len(wb_trigs(e)) == 1 and wb_trigs(e)[0].get("factor") == 3.0, f"trig={wb_trigs(e)}")
    check("改回 1.0 撤掉声明", WBP.apply_gm_dmg_mult(e, 1.0) is False and not wb_trigs(e),
          f"trig={wb_trigs(e)}")
    check("非法值不挂（'abc'）", WBP.apply_gm_dmg_mult(e, "abc") is False and not wb_trigs(e))
    check("非 dict actor 不炸", WBP.apply_gm_dmg_mult(None, 5.0) is False)


def test_end_to_end():
    print("【2. 端到端：倍率真乘在打 Boss 的伤害上】")
    base = hit(mk_boss())
    check("无倍率：1000 进 → 1000 出", base == 1000, f"base={base}")

    e10 = mk_boss()
    WBP.apply_gm_dmg_mult(e10, 10.0)
    d10 = hit(e10)
    check("×10：1000 → 10000", d10 == 10000, f"d10={d10}")

    e05 = mk_boss()
    WBP.apply_gm_dmg_mult(e05, 0.5)
    d05 = hit(e05)
    check("×0.5：1000 → 500", d05 == 500, f"d05={d05}")

    e100 = mk_boss()
    WBP.apply_gm_dmg_mult(e100, 100.0)
    check("×100：1000 → 100000", hit(e100) == 100000, f"d={hit(e100)}")

    # 零噪音：同一场里没挂倍率的怪不受影响
    plain = mk_boss()
    check("未挂倍率的 Boss 不受影响", hit(plain) == 1000, f"plain={hit(plain)}")

    # 反例：倍率 1.0 走的是「不挂」路径 → 与 base 同
    e1 = mk_boss()
    WBP.apply_gm_dmg_mult(e1, 1.0)
    check("倍率 1.0 与无倍率等价", hit(e1) == base, f"e1={hit(e1)}")


def test_compose_with_taken_calc():
    print("【3. 与既有 taken_calc 乘区共存（不互相覆盖）】")
    e = mk_boss()
    WBP.apply_gm_dmg_mult(e, 10.0)
    # 再挂一条内容侧减伤（同容器、同 ctx.mult，模拟「Boss 又开了减伤阶段」）
    e.setdefault("triggers", {}).setdefault("taken_calc", []).append(
        {"action": "wb_test_half"})

    from ext_combat.battle.effects import register_action

    @register_action("wb_test_half")
    def _half(battle, caster, target, params, logs):
        ctx = getattr(battle, "_fire_ctx", None)
        if ctx is not None:
            ctx["mult"] = float(ctx.get("mult", 1.0) or 1.0) * 0.5

    d = hit(e)
    check("×10（GM）与 ×0.5（内容减伤）复利 = ×5（1000→5000）", d == 5000, f"d={d}")


if __name__ == "__main__":
    test_install()
    test_end_to_end()
    test_compose_with_taken_calc()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
