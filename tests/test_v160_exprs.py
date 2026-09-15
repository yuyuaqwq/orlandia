# -*- coding: utf-8 -*-
"""v160 逐级公式 exprs + 技能详情展示——固化测试（防退化）。

覆盖：
1. 引擎选择器：skill_formula_expr / skill_formula_expr_for_seg（exprs 优先/越界取最后/单条 expr 兼容）
2. resolve_formula 段级 exprs：按 _skill_lv 取公式结算
3. 表达式→中文公式翻译器：translate_expr（变量替换/运算符替换/最长词优先）
4. 数值预览：skill_expr_preview（按级代入玩家属性）
5. 展示层：_skill_formula_text（公式行）+ _skill_upgrade_gains（实际数值）+ 未学显示全等级（意见#64）

运行：python tests/test_v160_exprs.py（exit=0 全绿）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, make_player  # noqa: E402
from _engine_harness import Main  # noqa: E402
from saintess_engine.battle.formulas import (  # noqa: E402
    skill_expr_preview,
    skill_formula_expr,
    skill_formula_expr_for_seg,
    resolve_formula,
)
from saintess_engine.expr import translate_expr# noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def test_selector():
    print("【1. 引擎选择器】")
    info = {"exprs": ["atk*0.8 + 20", "atk*0.85 + 25", "atk*0.9 + 30"]}
    check("Lv1 取第1条", skill_formula_expr(info, 1) == "atk*0.8 + 20")
    check("Lv2 取第2条", skill_formula_expr(info, 2) == "atk*0.85 + 25")
    check("Lv3 取第3条", skill_formula_expr(info, 3) == "atk*0.9 + 30")
    check("Lv4 越界取最后", skill_formula_expr(info, 4) == "atk*0.9 + 30")
    check("Lv0 下限取第1", skill_formula_expr(info, 0) == "atk*0.8 + 20")
    seg = {"exprs": ["x+1", "x+2"]}
    check("段级 Lv2", skill_formula_expr_for_seg(seg, 2) == "x+2")
    check("单条 expr 兼容", skill_formula_expr({"expr": "y*2"}, 5) == "y*2")
    check("无公式 None", skill_formula_expr({}, 1) is None)


def test_resolve_seg_exprs():
    print("【2. resolve_formula 段级 exprs】")
    st = {"atk": 100, "matk": 100, "def": 50, "mdef": 50, "max_hp": 500,
          "_player_lv": 10, "_skill_lv": 2}
    fml = [{"exprs": ["atk*0.8 + 20", "atk*0.85 + 25", "atk*0.9 + 30"], "type": "phys"}]
    dmg, _m = resolve_formula(fml, st, 50, 50, variance=0)
    # Lv2: atk*0.85+25 = 100*0.85+25 = 110 → calc_damage(110, 50) = 110^2/160 ≈ 75
    check(f"Lv2 公式伤害≈75（实际 {dmg}）", abs(dmg - 75) <= 1, str(dmg))
    st["_skill_lv"] = 1
    dmg1, _ = resolve_formula(fml, st, 50, 50, variance=0)
    # Lv1: atk*0.8+20 = 100 → calc_damage(100, 50) = 10000/150 ≈ 66
    check(f"Lv1 公式伤害≈66（实际 {dmg1}）", abs(dmg1 - 66) <= 1, str(dmg1))


def test_translate():
    print("【3. 表达式翻译器】")
    t = translate_expr("(atk*0.8 + player_lv*5) * (1 + skill_lv*0.1)")
    check("公式翻译", t == "(攻击×0.8 + 玩家等级×5) × (1 + 技能等级×0.1)", t)
    t2 = translate_expr("matk*1.5 + 20")
    check("matk 翻译", t2 == "魔法攻击×1.5 + 20", t2)
    t3 = translate_expr("max_hp*0.05 + atk*0.3")
    check("max_hp 翻译", t3 == "最大生命×0.05 + 攻击×0.3", t3)
    t4 = translate_expr("target_max_hp*0.1 + base")
    check("target_max_hp 翻译", t4 == "目标最大生命×0.1 + 基础值", t4)
    check("空串", translate_expr("") == "")


def test_preview():
    print("【4. skill_expr_preview】")
    info = {"exprs": ["atk*0.8 + 20", "atk*0.85 + 25", "atk*0.9 + 30"],
            "kind": "物理", "name": "测试斩", "lv": 1}
    stats = {"atk": 100, "matk": 100, "max_hp": 500}
    check("预览 Lv1=100", skill_expr_preview(info, 1, stats) == 100)
    check("预览 Lv2=110", skill_expr_preview(info, 2, stats) == 110)
    check("预览 Lv3=120", skill_expr_preview(info, 3, stats) == 120)
    check("无表达式 0", skill_expr_preview({}, 1, stats) == 0.0)


def test_display():
    print("【5. 技能详情展示】")
    clean_db()  # 防测试库残留（其他测试可能学过技能）
    m = Main()
    make_player("g1", "q1", "测试", "战士", level=10)
    db.update_player("g1", "q1", skill_points=500, cur_map="oak_town")
    p = m._player("g1", "q1")

    # 未学技能：显示全等级数值（意见#64）
    det = m._skill_detail_message(p, "挥砍")
    check("未学详情非空", det is not None and len(det) > 0)
    check("未学显示状态", "未学会" in det or "可学习" in det, (det or "")[:100])
    check("未学也显示数值成长", "数值成长" in (det or ""), (det or "")[:200])
    check("未学逐级全展示", "Lv.1" in (det or "") and "Lv.5" in (det or ""), (det or "")[:400])

    # 已学技能：显示当前级 ▶ 标记
    db.update_player("g1", "q1", learned_skills=["sk_hui_kan"], skill_levels={"sk_hui_kan": 3})
    p2 = m._player("g1", "q1")
    det2 = m._skill_detail_message(p2, "挥砍")
    check("已学状态", "已学会" in (det2 or ""), (det2 or "")[:100])
    check("当前级标记 ▶", "▶ Lv.3" in (det2 or ""), (det2 or "")[:300])
    check("逐级全展示", "Lv.1" in (det2 or "") and "Lv.5" in (det2 or ""), (det2 or "")[:400])

    # 带 exprs 的技能：公式翻译展示 + 实际数值
    _table = C.PLAYER_SKILLS.get(C.resolve("classes", "战士"), {})
    if isinstance(_table, dict) and "skills" in _table:
        _table = _table["skills"]
    sname = next(iter(_table.keys()))
    sinfo = dict(_table[sname])
    sinfo["exprs"] = ["atk*0.8 + 20", "atk*0.85 + 25", "atk*0.9 + 30"]
    ftext = m._skill_formula_text(sinfo, 2)
    check("公式翻译展示", "攻击×0.8" in ftext or "魔法攻击" in ftext or "0.85" in ftext, ftext)
    gains = m._skill_upgrade_gains(sinfo, 2, {"atk": 100, "matk": 50, "max_hp": 500})
    check("升级预览含实际数值", any("≈" in g for g in gains), str(gains))
    # v161：战士挥砍已迁移 LOL 式 exprs → 真实技能应有公式行（不再是"无表达式"）
    check("v161 真实技能有公式行", m._skill_formula_text(_table[sname]) != "", "挥砍已迁移 exprs，应有公式")


if __name__ == "__main__":
    test_selector()
    test_resolve_seg_exprs()
    test_translate()
    test_preview()
    test_display()
    print(f"\n===== 结果：通过 {passed} / 断言 {passed + failed} =====")
    sys.exit(1 if failed else 0)
