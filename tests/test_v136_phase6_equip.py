# -*- coding: utf-8 -*-
"""v136 Phase6 职业套装/散装/区域套固化测试。

运行: python tests/test_v136_phase6_equip.py（直跑模式，顶部 import _engine_harness）
覆盖:
1. 数量基线（名册 388 / 配方 424 / 素材 552）
2. 职业套装 90 件可生成 + set 挂载 + req 正确
3. 职业折扣（本职业 100% / 非本职业 60%）
4. 散装不挂套装（自由线）
5. 区域套过渡/毕业档可生成 + 精制前缀
6. 新素材定义 + 配方引用闭环
7. 新装备锻造链路（craft_recipe_make）
"""
from _engine_harness import C as _H  # noqa: E402,F401  （测试侧入口：装配引擎通道 + 私有库）

# W10：包内源（原 `from data.plugins.dragonfall.game import data as C`）—— 6 名分居 3 个门面，
# 其中 CRAFT_RECIPES / SERIES_SETS 的用点去掉 `C.` 前缀（纯模块限定名改写，断言/期望值零改动）
from content import catalog_items as C  # noqa: E402  EQUIP_ROSTER / EQUIP_ROSTER_BY_NAME / MATERIALS / SETS
from content.catalog_life import CRAFT_RECIPES  # noqa: E402
from content.catalog_rules import SERIES_SETS  # noqa: E402
from content.drops import generate_roster_equip
from content.panel import set_bonus_2, player_stats_detail, set_bonus_4 as engine_set_bonus_4
from content.craft import craft_recipe_make

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def test_counts():
    print("【1. 数量基线】")
    check("名册 687 件", len(C.EQUIP_ROSTER) == 687, str(len(C.EQUIP_ROSTER)))  # v171 +6 新手流派白装; v172 路B +24 重锻专属; v173.3 #103 +5 自选礼包武器
    check("配方 426 条", len(CRAFT_RECIPES) == 426, str(len(CRAFT_RECIPES)))
    check("素材 598 个(v167 +30新料 + 后续版本补充)", len(C.MATERIALS) == 598, str(len(C.MATERIALS)))
    # 新素材存在
    for mid in ["mat_ye_zhu_pi", "mat_shan_zei_hui_zhang", "mat_shu_shi_he_xin",
                "mat_yue_ying_zhi_pi", "mat_long_yan_jing_hua"]:
        check(f"新素材 {mid} 定义", mid in C.MATERIALS, mid)
    # 系列映射（职业 18 + 区域 5 = 23 新增）
    for s in ["铁皮", "精铁", "百炼", "学徒", "符文", "秘法", "布衣", "祝福", "圣堂",
              "猎手", "风行", "暗夜", "轻影", "夜行", "阴影", "行者", "石拳", "壁槌",
              "护林", "渡口", "巡林", "霜猎", "龙裔"]:
        check(f"系列 {s} 映射套装", s in SERIES_SETS, s)


    # 猎首远征队恢复（v136 审计 P0：Phase6 游侠装备 id 撞车覆盖旧条目，已换 id 恢复）
    lh_count = sum(1 for r in C.EQUIP_ROSTER.values() if r.get("series") == "猎首远征队")
    check("猎首远征队 4 件", lh_count == 4, str(lh_count))
    lh = C.EQUIP_ROSTER.get("eq_lie_shou_pi_mao")
    check("猎首皮帽恢复", lh is not None and lh.get("quality") == "purple" and lh.get("lv") == 50,
          str(lh))
    # 游侠武器链（P2 对齐）：猎手短弓→风行长弓→暗夜长弓
    fy = C.EQUIP_ROSTER.get("eq_feng_xing_chang_gong")
    check("风行长弓 Lv30", fy is not None and fy.get("lv") == 30 and fy.get("series") == "风行", str(fy))
    ay = C.EQUIP_ROSTER.get("eq_an_ye_chang_gong")
    check("暗夜长弓 Lv50", ay is not None and ay.get("lv") == 50 and ay.get("series") == "暗夜", str(ay))


def test_class_sets():
    print("【2. 职业套装生成】")
    # 每职业 3 阶段，抽查 3 件武器
    samples = [
        ("eq_tiepichangjian", "铁皮长剑", "铁皮套", {"str": 10}, "cls_zhan_shi"),
        ("eq_jingzhizhanjian", None, None, None, None),  # 可能 id 不同，用名字查
    ]
    # 用名字查
    by_name = C.EQUIP_ROSTER_BY_NAME
    for nm in ["铁皮长剑", "精铁战剑", "百炼长剑", "见习法杖", "符文法杖", "秘法法杖",
               "布衣权杖", "祝福权杖", "圣堂权杖", "猎手短弓", "风行长弓", "轻影匕首",
               "夜行匕首", "行者拳套", "石拳拳套"]:
        check(f"职业套装名册 {nm}", nm in by_name, nm)
    # 生成验证
    eq = generate_roster_equip("eq_tiepichangjian")
    check("铁皮长剑生成", eq["name"] == "铁皮长剑", str(eq.get("name")))
    check("铁皮长剑套装", eq.get("set") == "铁皮套", str(eq.get("set")))
    check("铁皮长剑 req", eq.get("req") == {"str": 10}, str(eq.get("req")))
    check("铁皮长剑品质", eq.get("quality") == "blue", str(eq.get("quality")))


def test_class_discount():
    print("【3. 职业折扣】")
    eq = {}
    for s in ["weapon", "helm", "armor", "legs", "boots"]:
        eq[s] = {"name": "测试", "slot": s, "set": "铁皮套"}
    # 战士（本职业）：100%
    st_w, src_w = player_stats_detail("cls_zhan_shi", 30, eq)
    b2_w = set_bonus_2(eq, "cls_zhan_shi")
    check("战士套装 atk+8%", abs(b2_w["atk"] - 0.08) < 1e-9, str(b2_w))
    check("战士套装 def+18%", abs(b2_w["def"] - 0.18) < 1e-9, str(b2_w))
    # 法师（非本职业）：60%
    b2_m = set_bonus_2(eq, "cls_fa_shi")
    check("法师穿战士套 atk×0.6", abs(b2_m["atk"] - 0.048) < 1e-9, str(b2_m))
    check("法师穿战士套 def×0.6", abs(b2_m["def"] - 0.108) < 1e-9, str(b2_m))
    # 不传 class 不打折（老兼容）
    b2_n = set_bonus_2(eq)
    check("不传 class 不打折", abs(b2_n["atk"] - 0.08) < 1e-9, str(b2_n))


def test_scatter():
    print("【4. 散装】")
    # 散装代表：猎风披风 / 熔岩护手 / 苍穹之翼
    for nm in ["猎风披风", "猎风护腿", "熔岩护手", "熔岩护腿", "苍穹之翼", "风神之环",
               "潮汐之环", "龙翼护符"]:
        check(f"散装名册 {nm}", nm in C.EQUIP_ROSTER_BY_NAME, nm)
    # 猎风披风生成（不挂套装）
    rid = next((k for k, v in C.EQUIP_ROSTER.items() if v.get("name") == "猎风披风"), None)
    check("猎风披风名册 id", rid is not None, str(rid))
    if rid:
        gen = generate_roster_equip(rid)
        check("猎风披风生成", gen["name"] == "猎风披风")
        check("猎风披风无套装", gen.get("set") is None, str(gen.get("set")))
        check("猎风披风词条", gen.get("affixes") is not None, str(gen.get("affixes")))

    # v136 审计补：散装不得与职业套装共用系列名（猎手斗篷/猎手之靴曾挂猎手套）
    for nm2 in ["猎手斗篷", "猎手之靴"]:
        rid2 = next((k for k, v in C.EQUIP_ROSTER.items() if v.get("name") == nm2), None)
        check(f"{nm2} 存在", rid2 is not None, str(rid2))
        if rid2:
            gen2 = generate_roster_equip(rid2)
            check(f"{nm2} 散装无套装", gen2.get("set") is None,
                  f"series={gen2.get('series')} set={gen2.get('set')}")


def test_region():
    print("【5. 区域套】")
    # 过渡档（商店）+ 毕业档（精制）
    for nm in ["护林胸甲", "护林护腿", "护林之靴", "精制护林胸甲", "精制护林护腿",
               "渡口胸甲", "精制渡口胸甲", "巡林胸甲", "精制巡林胸甲",
               "霜猎胸甲", "精制霜猎胸甲", "龙裔胸甲", "精制龙裔胸甲"]:
        check(f"区域套名册 {nm}", nm in C.EQUIP_ROSTER_BY_NAME, nm)
    # 精制龙裔胸甲（橙装带专属）
    rid = next((k for k, v in C.EQUIP_ROSTER.items() if v.get("name") == "精制龙裔胸甲"), None)
    check("精制龙裔胸甲名册 id", rid is not None, str(rid))
    if rid:
        gen = generate_roster_equip(rid)
        check("精制龙裔胸甲生成", gen["name"] == "精制龙裔胸甲")
        check("精制龙裔胸甲橙装", gen["quality"] == "orange")
        check("精制龙裔胸甲专属", gen.get("legendary") == "earth_heart", str(gen.get("legendary")))
        check("精制龙裔胸甲套装", gen.get("set") == "龙裔套", str(gen.get("set")))


def test_craft():
    print("【6. 锻造链路】")
    # 铁皮长剑配方
    rec = CRAFT_RECIPES.get("rec_tiepichangjian") or CRAFT_RECIPES.get("rec_tie_pi_chang_jian")
    check("铁皮长剑配方存在", rec is not None, str(rec))
    if rec:
        check("铁皮长剑配方 mats(v167换粗铁)", "mat_cu_tie" in rec["mats"], str(rec["mats"]))
    # 精制渡口胸甲（紫装带图纸）
    rec2 = CRAFT_RECIPES.get("rec_du_kou_chen_xi_xiong_jia")
    check("精制渡口胸甲配方", rec2 is not None, str(rec2))
    if rec2:
        check("精制渡口胸甲图纸", rec2.get("blueprint") == "精制渡口胸甲图纸", str(rec2.get("blueprint")))
    # 锻造产物 = 名册精确生成（craft_recipe_make 用配方 id 查找）
    rec_id = next((k for k, v in CRAFT_RECIPES.items() if v.get("name") == "铁皮长剑"), None)
    check("铁皮长剑配方 id", rec_id is not None, str(rec_id))
    if rec_id:
        eq = craft_recipe_make(rec_id)
        check("锻造铁皮长剑", eq and eq["name"] == "铁皮长剑", str(eq.get("name") if eq else None))
        check("锻造铁皮长剑套装", eq and eq.get("set") == "铁皮套", str(eq.get("set") if eq else None))


def test_set_effects():
    """套装特效注册（v136 审计补：_build_class_sets 必须注册 bonus_4/bonus_3，
    否则战斗侧 set_bonus_4 读不到 effect，玩家白穿套装）"""
    print("【7. 套装特效注册】")
    # v141.3 S1 套装去模板化：铁皮套 4 件 → tie_pi_harden（受击防御）；护林套 3 件 → ranger_regen_wild（攻击回血）
    b4 = C.SETS.get("set_tie_pi_tao", {}).get("bonus_4", {})
    check("铁皮套 bonus_4 注册", b4.get("effect") == "tie_pi_harden", str(b4))
    b4b = C.SETS.get("set_hu_lin_tao", {}).get("bonus_3", {})
    check("护林套 bonus_3 注册", b4b.get("effect") == "ranger_regen_wild", str(b4b))
    eqs = [generate_roster_equip(rid) for rid, r in C.EQUIP_ROSTER.items()
           if r.get("series") == "铁皮"][:4]
    if len(eqs) == 4:
        equipment = {"weapon": eqs[0], "helm": eqs[1], "armor": eqs[2], "legs": eqs[3]}
        effs = engine_set_bonus_4(equipment)
        check("铁皮套4件特效", "tie_pi_harden" in effs, str(effs))
    # 区域套 3 件特效（v136 审计 P1-1：3 槽位凑不齐 4 件，bonus_3 让 3 件生效）
    r3 = [generate_roster_equip(rid) for rid, r in C.EQUIP_ROSTER.items()
          if r.get("series") == "护林" and r.get("source") == "商店"][:3]
    if len(r3) == 3:
        equipment3 = {"armor": r3[0], "legs": r3[1], "boots": r3[2]}
        effs3 = engine_set_bonus_4(equipment3)
        check("护林套3件特效", "ranger_regen_wild" in effs3, str(effs3))
        check("护林套3件属性", "hp" in set_bonus_2(equipment3), str(set_bonus_2(equipment3)))


if __name__ == "__main__":
    test_counts()
    test_class_sets()
    test_class_discount()
    test_scatter()
    test_region()
    test_craft()
    test_set_effects()
    print(f"\n===== 结果：通过 {PASS} / 断言 {PASS + FAIL} =====")
    if FAIL:
        raise SystemExit(1)
