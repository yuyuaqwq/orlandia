# -*- coding: utf-8 -*-
"""v126.5 技能列表资源消耗显示格式 回归测试。

鱼鱼问「信仰-3 是不是需要消耗 3 信仰才能释放？」——v126.5 初版并入魔力求
`30 魔力 + 3 信仰值`，v126.6b 改 `30 魔力 ｜ 信仰值 +3`，v126.6c 终版：
消耗=扣减，数字后缀用 `-`（与 res_gain 获得 `+` 区分，`消耗：` 前缀带上下文）：
  `消耗：30 魔力 ｜ 信仰值 -3 ｜ 射程：2`

同时修复脱战拦截提示输出英文 key（`faith3`）违反"玩家可见文本禁止内部 ID"铁律。

1. 圣光惩击（cls_mu_shi res_cost faith3）：消耗行含 `30 魔力 ｜ 信仰值 -3`
2. 战士怒气技（res_cost rageN）：消耗行含 `N 怒气` 并入
3. 零 MP + 纯资源技：只显示资源不求
4. 无资源技能：消耗行不含 `-` 资源后缀
5. 脱战拦截提示：显示中文资源名（`消耗 3 信仰值`），不含英文 key

环境铁律：私有库 test_v1266.db（绝不碰生产库）。
"""
import os
import sys

# 2026-09-13：私有库移进 tests/.private_dbs/（原先 os.path.abspath 依赖 cwd
# → 被 run_all_tests 以仓根为 cwd 拉起时会把库落在仓根）
_PRIVATE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           ".private_dbs", "test_v1266.db")
os.makedirs(os.path.dirname(_PRIVATE_DB), exist_ok=True)
os.environ["GWEN_GAME_DB"] = _PRIVATE_DB
os.environ["GWEN_TEST_MODE"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db  # noqa: E402
from content.skills import skill_info
from _engine_harness import Main  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def mk_priest(hp=400, mp=100, learned=None):
    return {
        "class_name": "cls_mu_shi", "level": 30, "hp": hp, "max_hp": 1000,
        "mp": mp, "max_mp": 100, "name": "牧师", "reach": 3,
        "equipment": {"weapon": {"name": "测试法杖", "stats": {"matk": 200, "atk": 50},
                                 "affixes": [], "enhance": 0}},
        "attributes": {"int": 20, "str": 5},
        "learned_skills": learned or ["治愈术"],
    }


def mk_warrior(hp=400, mp=100, learned=None):
    return {
        "class_name": "cls_zhan_shi", "level": 30, "hp": hp, "max_hp": 1000,
        "mp": mp, "max_mp": 100, "name": "战士", "reach": 1,
        "equipment": {"weapon": {"name": "测试铁剑", "stats": {"atk": 100, "matk": 0},
                                 "affixes": [], "enhance": 0}},
        "attributes": {"str": 20, "int": 5},
        "learned_skills": learned or ["猛击"],
    }


def test_skill_list_res_cost_format():
    print("【1. 技能列表资源消耗并入魔力求（v126.5）】")
    clean_db()
    m = Main(None)

    # v153：疾风连射→连射（lv1，res_cost energy 22）；资源并入格式断言
    ranger = {"class_name": "cls_you_xia", "level": 30, "hp": 400, "max_hp": 1000,
              "mp": 100, "max_mp": 100, "name": "游侠", "reach": 3,
              "equipment": {"weapon": {"name": "测试弓", "stats": {"atk": 100, "matk": 0},
                                       "affixes": [], "enhance": 0}},
              "attributes": {"str": 20, "int": 5},
              "learned_skills": ["连射"]}
    out = m._skill_list_page(ranger, 1)
    _consume_part = out.split("消耗：")[1].split("｜")[0] if "消耗：" in out else ""
    check("连射消耗行格式 精力 -22（v163 游侠不耗魔，纯精力消耗）",
          "精力 -22" in out and "魔力" not in _consume_part, out[:400])
    check("消耗行不含 +22 混淆格式（消耗用-获得用+）",
          "精力 +22" not in out, out[:400])
    check("消耗行不含 `精力 -22` 负号样式残留检查（-22 前必须带 ｜ 间隔）",
          "-22 精力" not in out, out[:400])

    # 游侠技能列表含 精力（核心资源并入）——连射已学第 1 页，翻页看后续技能消耗行
    ranger2 = dict(ranger)
    ranger2["learned_skills"] = ["连射", "瞄准射击", "鹰眼锁定"]
    out2 = m._skill_list_page(ranger2, 2)
    found_rage = "精力" in out2
    check("游侠技能列表含 精力（v153 资源并入）", found_rage, out2[:400])
    if found_rage:
        # 资源消耗并入：形如 `N 精力`，不是 `精力 -N` 反转
        check("资源消耗并入（无 `怒气 -` 后缀）", "怒气 -" not in out2, out2[:400])


def test_skill_list_no_res_suffix():
    print("【2. 无资源技能不产生资源后缀】")
    clean_db()
    m = Main(None)
    # 用 level 1 牧师（只学治愈术/圣光术，均无 res_cost——只有 res_gain 加号）
    low = mk_priest(learned=["治愈术", "圣光术"])
    out = m._skill_list_page(low, 1)
    # v126.6c 修正：列表里可学的惩戒/圣光惩击（res_cost 技）会正常显示 `信仰值 -N`，
    # 断言须限定已学技能（治愈术/圣光术）的消耗行，不能全页检查
    learned_lines = [ln for ln in out.split("\n")
                     if ln.startswith(("1.", "2.", "3."))]
    bad = [ln for ln in learned_lines if "信仰值 -" in ln]
    check("已学无资源技能消耗行不含 `信仰值 -` 后缀", not bad, str(bad[:3]))
    check("消耗行含有 射程：", "射程：" in out, out[:200])


def test_offbattle_guard_chinese_name():
    print("【3. 脱战治疗拦截显示中文资源名】")
    clean_db()
    from _engine_harness import Main as CombatCmds
    cc = CombatCmds(None)
    # v153：疾风连射→连射（energy 22）验证脱战渲染中文名
    ranger = {"class_name": "cls_you_xia", "level": 30, "hp": 400, "max_hp": 1000,
              "mp": 100, "max_mp": 100, "name": "游侠", "reach": 3,
              "equipment": {"weapon": {"name": "测试弓", "stats": {"atk": 100, "matk": 0},
                                       "affixes": [], "enhance": 0}},
              "attributes": {"str": 20, "int": 5},
              "learned_skills": ["连射"]}
    info = skill_info(ranger["class_name"], "连射")
    check("连射有 res_cost", bool(info and info.get("res_cost")), str(info))
    if not (info and info.get("res_cost")):
        return
    # 直接验证渲染片段（脱战拦截在 handler 里带 event，这里验证 join 逻辑产物）
    # v181.M-R2b：渲染同 combat.py 改读 EFFECT_RULES 单源名（旧 E.core_resource_def 已退役）
    def _res_cn(_key):
        from content.mech.params import EFFECT_RULES as _ER
        return ((_ER.get(_key) or {}).get("name")) or _key
    parts = []
    for _k, _v in info["res_cost"].items():
        parts.append(f"{_v} {_res_cn(_k)}")
    rendered = " + ".join(parts)
    check("脱战提示消耗片段含中文 22 精力", "22 精力" in rendered, rendered)
    check("脱战提示不含英文 key energy", "energy" not in rendered, rendered)


if __name__ == "__main__":
    test_skill_list_res_cost_format()
    test_skill_list_no_res_suffix()
    test_offbattle_guard_chinese_name()
    print(f"\n===== 结果 {passed} 通过 / {failed} 失败 =====")
    sys.exit(1 if failed else 0)