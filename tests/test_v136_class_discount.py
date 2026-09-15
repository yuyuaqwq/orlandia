# -*- coding: utf-8 -*-
"""v136 Phase6 职业套装职业折扣测试（本职业 100% / 非本职业 60%）。

运行: python tests/test_v136_class_discount.py（直跑模式，顶部 import _engine_harness）
"""
from _engine_harness import boot as _eng_cfg  # noqa: F401  (GWEN_GAME_DB + qqbot path)
_eng_cfg()

# ★ PFIX P6（2026-09-15）：**注入面 = 实现本体的那只字典**。
#   `content/panel.py::_set_info()` 读的是**包内门面** `content/tables.SETS`
#   （原文 `from .. import content as C` 已随 D3 面板批次改成 `from . import tables`）。
#   宿主聚合层 `game.content.SETS` 已**不是**同一只字典 —— 实测 `is` → False
#   （两份各 92 条）⇒ 往 C.SETS 注入对 panel **不可见**（静默 no-op，与 P1 同型）。
#   故这里改成注入 `content.tables.SETS`；两个夹具同时改用**唯一名**，让断言真的
#   打在夹具上（旧夹具名「铁皮套」与真实套装同名，注入被真实条目遮蔽 ⇒ 测试靠巧合变绿）。
from content.panel import set_bonus_2, active_sets
import content.tables as _T   # noqa: E402  包内门面（panel 的 SETS 取数面）


def _mk_equip(set_name: str, n: int) -> dict:
    """构造 n 件同套装装备（set 字段 = 套装名）。"""
    eq = {}
    slots = ["weapon", "helm", "armor", "legs", "boots", "ring", "necklace"]
    for i in range(n):
        eq[slots[i]] = {"name": f"测试件{i}", "slot": slots[i], "set": set_name}
    return eq


def test_class_discount_full():
    """本职业穿战士套 = 100%，法师穿战士套 = 60%。"""
    # 构造一个带 class 字段的战士套装（唯一夹具名：不与真实套装同名）
    set_name = "P6铁皮套夹具"
    _T.SETS["set_tie_pi_p6fix"] = {
        "name": set_name,
        "class": "cls_zhan_shi",
        "bonus_2": {"atk": 0.08, "def": 0.08},
        "bonus_4_stats": {"def": 0.10},
    }
    eq2 = _mk_equip(set_name, 2)
    eq4 = _mk_equip(set_name, 4)

    # 本职业：2 件 atk+8% def+8%
    b2_war = set_bonus_2(eq2, "cls_zhan_shi")
    assert abs(b2_war["atk"] - 0.08) < 1e-9, b2_war
    assert abs(b2_war["def"] - 0.08) < 1e-9, b2_war
    # 本职业：4 件再加 def+10%
    b4_war = set_bonus_2(eq4, "cls_zhan_shi")
    assert abs(b4_war["def"] - 0.18) < 1e-9, b4_war  # 0.08 + 0.10

    # 非本职业（法师穿）：×0.6
    b2_mage = set_bonus_2(eq2, "cls_fa_shi")
    assert abs(b2_mage["atk"] - 0.048) < 1e-9, b2_mage  # 0.08×0.6
    assert abs(b2_mage["def"] - 0.048) < 1e-9, b2_mage
    b4_mage = set_bonus_2(eq4, "cls_fa_shi")
    assert abs(b4_mage["def"] - 0.108) < 1e-9, b4_mage  # (0.08+0.10)×0.6

    # 不传 class_name = 不打折（老代码兼容）
    b2_none = set_bonus_2(eq2)
    assert abs(b2_none["atk"] - 0.08) < 1e-9, b2_none


def test_class_discount_no_class_field():
    """无 class 字段的旧套装不打折。"""
    set_name = "P6寒霜套夹具"
    _T.SETS["set_han_shuang_p6fix"] = {
        "name": set_name,
        "bonus_2": {"spd": 0.15},
    }
    eq = _mk_equip(set_name, 2)
    b = set_bonus_2(eq, "cls_zhan_shi")
    assert abs(b["spd"] - 0.15) < 1e-9, b


def test_class_discount_effect_not_discounted():
    """effect 型 bonus_2 不打折（机制向）。"""
    set_name = "P6血誓夹具"
    _T.SETS["set_xue_shi_p6fix"] = {
        "name": set_name,
        "class": "cls_zhan_shi",
        "bonus_2": {"effect": "res_gain", "res": "rage", "value": 1, "on": "on_taken"},
        "bonus_4": {"effect": "elegy_dmg", "value": 0.20},
    }
    eq = _mk_equip(set_name, 2)
    b = set_bonus_2(eq, "cls_fa_shi")
    assert b == {}, b  # effect 型不入 stat 聚合


if __name__ == "__main__":
    test_class_discount_full()
    test_class_discount_no_class_field()
    test_class_discount_effect_not_discounted()
    print("✅ test_v136_class_discount: 3/3 全绿")
