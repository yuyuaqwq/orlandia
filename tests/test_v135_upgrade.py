# -*- coding: utf-8 -*-
"""v172 装备升级机制（真等级化）验收测试（GWEN_GAME_DB 隔离，不碰生产库）

v172 拍板（鱼鱼）：升级 = 装备 lv 真实 +1（上限追平玩家等级），属性随 equip_stats
重算，upgrade_lv 倍率层作废（存量装备 upgrade_lv → lv 补差迁移）。
覆盖：
  1. 数据表：UPGRADE_TABLE 保留 cost 阶梯（无 mult 乘区）
  2. 升级命令成功：Lv3 皮甲 → Lv4，属性按 equip_stats 涨（stats 重算含分系）
  3. 上限：装备 lv 追平玩家等级后拦截（不许超前）
  4. engine 结算：无 upgrade 乘区（同装备属性不随 upgrade_lv 字段变化）
  5. 拦截分支：铁匠铺/材料/金币/副业等级
  6. 存量迁移：upgrade_lv=3 旧档 → 读档 lv+3（背包 _hydrate 与已穿戴 get_player 两入口）
  7. 升级保留 affixes/enchant/sockets/calamity_bonus（个体字段全保留，只重算 stats+price）

独立运行：python tests/test_v135_upgrade.py
"""
import os
import sys
import asyncio

os.environ.setdefault("GWEN_GAME_DB", os.path.abspath("test_v135_upgrade.db"))
sys.path.insert(0, "tests")

from _engine_harness import clean_db, make_player, Main, FakeEvent, run  # noqa: E402
from _engine_harness import C, db  # noqa: E402
from content.panel import player_stats_detail as E_player_stats_detail  # noqa: E402

g = "g_test_upg"
q = "q_test_upg"

passed = 0
failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {extra}")


def goto_smith(m, g, q):
    """把玩家放到橡木镇老铁铁匠铺（oak_town_3, craft funcs）。"""
    db.update_player(g, q, cur_map="oak_town", cur_subarea="oak_town_3")


def prof_to_lv(g, q, lv):
    """把强化副业升到指定等级。"""
    db.activate_prof(g, q, "enhance")
    for _ in range(500):
        nv, _ = db.add_prof_exp(g, q, "enhance", 10)
        if nv >= lv:
            return nv
    return db.get_prof_level(g, q, "enhance")


def stone(g, q):
    db.add_item(g, q, "i_stone_refine", {"name": "精炼强化石", "type": "材料", "stackable": True, "price": 30})


def main():
    print("== v172 装备升级（真等级化）验收 ==")

    # 1. 数据表
    print("[1] 数据表")
    check("UPGRADE_TABLE 保留 10 级 cost 阶梯（无 mult）", len(C.UPGRADE_TABLE) == 10
          and all("mult" not in v for v in C.UPGRADE_TABLE.values()), str(len(C.UPGRADE_TABLE)))
    check("成本递增", C.UPGRADE_TABLE[2]["cost"] > C.UPGRADE_TABLE[1]["cost"])

    # 2. 升级命令成功路径：Lv3 皮甲 → Lv4（真等级化 lv+1 + stats 重算）
    print("[2] 升级命令成功：Lv3 皮甲 → Lv4")
    clean_db()
    m = Main(None)
    make_player(g, q, name="测试升级", cls="游侠", level=30)
    db.update_player(g, q, gold=999999)
    # 皮甲 = 名册防具（leather 族：req agi → armor_family），Lv3
    eq = C.generate_roster_equip("eq_pi_jia") if "eq_pi_jia" in C.EQUIP_ROSTER else None
    if eq is None:
        # 名册无皮甲 → 手搓一件 leather 皮甲（用随机防具 Lv3 覆盖成皮甲语义）
        eq = C.generate_equip("armor", 3, "green")
        eq["lv"] = 3
        eq["req"] = {"agi": 6}
    eq["lv"] = 3
    # 个体字段（升级必须全保留）
    eq["affixes"] = ["swift", "dodge"]
    eq["enchant"] = [{"stat": "atk", "value": 5}]
    eq["sockets"] = {"S1": {"name": "碎裂I", "stats": {"atk": 0.01}}}
    eq["calamity_bonus"] = {"atk": 0.03}
    eq.pop("upgrade_lv", None)
    db.add_item(g, q, "eq_test1", eq)
    stone(g, q)
    prof_to_lv(g, q, 5)
    goto_smith(m, g, q)

    gold_before = db.get_player(g, q)["gold"]
    ev = FakeEvent(g, q, "升级 皮甲")
    out = asyncio.run(run(m.equip_upgrade, ev))
    txt = out[0] if out else ""
    check("升级成功提示", "装备升级成功" in txt, txt[:150])
    inv = db.get_inventory(g, q)
    d = inv[0]["data"] if inv else {}
    check("装备 lv 3→4（真等级化）", d.get("lv", 0) == 4, f"got {d.get('lv')}")
    check("upgrade_lv 字段已清除", "upgrade_lv" not in d, str(d.keys()))
    # 属性按 equip_stats 重算：Lv4 皮甲面板 ≥ Lv3（equip_stats 随 lv 递增）
    st_lv3 = C.equip_stats("armor", 3, d.get("quality", "green"))
    st_lv4 = C.equip_stats("armor", 4, d.get("quality", "green"))
    _hp4 = sum(v for k, v in d.get("stats", {}).items() if k not in C.PCT_STATS)
    check("stats 按 equip_stats(Lv4) 重算", d["stats"].get("hp", 0) >= st_lv4.get("hp", 0) * 0.5,
          f"hp={d['stats'].get('hp')} base4={st_lv4.get('hp')}")
    check("属性随等级上涨", _hp4 > sum(v for k, v in st_lv3.items() if k not in C.PCT_STATS),
          f"new={_hp4}")
    check("affixes 保留", d.get("affixes") == ["swift", "dodge"], str(d.get("affixes")))
    check("enchant 保留", d.get("enchant") == [{"stat": "atk", "value": 5}], str(d.get("enchant")))
    check("sockets 保留", (d.get("sockets") or {}).get("S1", {}).get("name") == "碎裂I", str(d.get("sockets")))
    check("calamity_bonus 保留", (d.get("calamity_bonus") or {}).get("atk") == 0.03, str(d.get("calamity_bonus")))
    gold_after = db.get_player(g, q)["gold"]
    # Lv3→4 cost 3 级档 675 - 每日副业任务奖励 50 = 625（若每日任务未触发则 675，容差）
    check("金币扣减（含副业奖励容差）", gold_before - gold_after in (625, 675),
          f"diff={gold_before-gold_after}")
    check("精炼强化石扣 1", db.count_item(g, q, "i_stone_refine") == 0)

    # 3. engine 结算：无 upgrade 乘区（真等级化后 lv 提升经 stats 重算，upgrade_lv 字段不再乘）
    print("[3] engine 属性结算（无 upgrade 乘区）")
    st0, _ = E_player_stats_detail("cls_zhan_shi", 1, {}, 0, None, 0, None, "human")
    eq2 = C.generate_roster_equip("eq_tie_jian")
    eq2["stats"] = {"atk": 10}
    eq2["upgrade_lv"] = 5  # 存量脏字段：engine 不再消费（不迁移路径的兜底）
    st1, _ = E_player_stats_detail(
        "cls_zhan_shi", 1,
        {"weapon": eq2}, 0, None, 0, None, "human",
    )
    atk_diff = st1.get("atk", 0) - st0.get("atk", 0)
    check("upgrade_lv=5 不再乘区（atk=10 无放大）", atk_diff == 10, f"diff={atk_diff}")
    # 升级+强化叠加：强化 2(×1.22) 仍生效
    eq3 = C.generate_roster_equip("eq_tie_jian")
    eq3["stats"] = {"atk": 10}
    eq3["enhance"] = 2
    eq3["upgrade_lv"] = 5
    st2, _ = E_player_stats_detail(
        "cls_zhan_shi", 1,
        {"weapon": eq3}, 0, None, 0, None, "human",
    )
    atk_diff2 = st2.get("atk", 0) - st0.get("atk", 0)
    # ENHANCE_TABLE[2].mult = 1.14（v156 数值重标后）+2 段位），10×1.14=11.4 → 11
    check("强化 ×1.14 仍生效（10*1.14=11）", atk_diff2 == 11, f"diff={atk_diff2}")

    # 4. 上限：装备 lv 追平玩家等级后拦截（不许超前）
    print("[4] 上限拦截（追平玩家等级）")
    clean_db()
    m = Main(None)
    make_player(g, q, name="上限", cls="战士", level=5)
    db.update_player(g, q, gold=999999)
    eq4 = C.generate_roster_equip("eq_tie_jian")
    eq4["lv"] = 5  # 已追平玩家 Lv5
    eq4.pop("upgrade_lv", None)
    db.add_item(g, q, "eq_test4", eq4)
    stone(g, q)
    prof_to_lv(g, q, 5)
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, "升级 铁剑")
    out = asyncio.run(run(m.equip_upgrade, ev))
    txt = out[0] if out else ""
    check("追平玩家等级拦截（再升需 Lv6）", "已是 Lv.5" in txt and "Lv.6" in txt, txt[:150])
    # 4b. 追平边界：Lv4（未到上限）→ 升到 Lv5 = 玩家等级 成功
    clean_db()
    m = Main(None)
    make_player(g, q, name="上限边", cls="战士", level=5)
    db.update_player(g, q, gold=999999)
    eq4b = C.generate_roster_equip("eq_tie_jian")
    eq4b["lv"] = 4
    eq4b.pop("upgrade_lv", None)
    db.add_item(g, q, "eq_test4b", eq4b)
    stone(g, q)
    prof_to_lv(g, q, 5)
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, "升级 铁剑")
    out = asyncio.run(run(m.equip_upgrade, ev))
    txt = out[0] if out else ""
    check("Lv4 → Lv5 追平成功（未超前）", "装备升级成功" in txt and "Lv.4 → Lv.5" in txt, txt[:150])
    d4b = db.get_inventory(g, q)[0]["data"]
    check("升级后装备 lv=5", d4b.get("lv") == 5, f"lv={d4b.get('lv')}")

    # 5. 拦截分支（每个独立重建玩家）
    print("[5] 拦截分支")
    # 5a. 非铁匠铺拦截
    db.update_player(g, q, cur_map="oak_town", cur_subarea="oak_town_4")  # 旅店
    ev = FakeEvent(g, q, "升级 铁剑")
    out = asyncio.run(run(m.equip_upgrade, ev))
    txt = out[0] if out else ""
    check("非铁匠铺拦截", "需要到铁匠铺" in txt, txt[:150])
    # 5b. 无材料拦截（独立玩家：有石头再清空）
    clean_db()
    m = Main(None)
    make_player(g, q, name="无材料", cls="战士", level=30)
    db.update_player(g, q, gold=999999)
    eq4c = C.generate_roster_equip("eq_tie_jian")
    eq4c["lv"] = 3
    eq4c.pop("upgrade_lv", None)
    db.add_item(g, q, "eq_test4c", eq4c)
    stone(g, q)
    prof_to_lv(g, q, 5)
    goto_smith(m, g, q)
    db.remove_item(g, q, "i_stone_refine", 99)
    ev = FakeEvent(g, q, "升级 铁剑")
    out = asyncio.run(run(m.equip_upgrade, ev))
    txt = out[0] if out else ""
    check("无材料拦截", "精炼强化石" in txt, txt[:150])
    # 5c. 金币不足拦截（独立玩家）
    clean_db()
    m = Main(None)
    make_player(g, q, name="缺钱", cls="战士", level=30)
    db.update_player(g, q, gold=1)
    eq4d = C.generate_roster_equip("eq_tie_jian")
    eq4d["lv"] = 3
    eq4d.pop("upgrade_lv", None)
    db.add_item(g, q, "eq_test4d", eq4d)
    stone(g, q)
    prof_to_lv(g, q, 5)
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, "升级 铁剑")
    out = asyncio.run(run(m.equip_upgrade, ev))
    txt = out[0] if out else ""
    check("金币不足拦截", "金币" in txt, txt[:150])
    # 5d. 副业等级不足拦截：装备 lv=4 → 升 Lv.5 需要副业 Lv.5（Lv.1 不够）
    clean_db()
    m = Main(None)
    make_player(g, q, name="副业", cls="战士", level=30)
    db.update_player(g, q, gold=999999)
    eq5 = C.generate_roster_equip("eq_tie_jian")
    eq5["lv"] = 4
    eq5.pop("upgrade_lv", None)
    db.add_item(g, q, "eq_test5", eq5)
    stone(g, q)
    db.activate_prof(g, q, "enhance")  # 学徒 Lv.1
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, "升级 铁剑")
    out = asyncio.run(run(m.equip_upgrade, ev))
    txt = out[0] if out else ""
    check("副业等级不足拦截(升Lv.5需Lv.5)", "需要强化副业" in txt, txt[:150])

    # 6. 存量迁移：upgrade_lv=3 旧档 → lv+3（背包 _hydrate + 已穿戴 get_player 两入口）
    print("[6] 存量 upgrade_lv → lv 补差迁移")
    # 6a. 背包（_hydrate 兜底）
    clean_db()
    m = Main(None)
    make_player(g, q, name="迁移背", cls="战士", level=30)
    eq6 = C.generate_roster_equip("eq_tie_jian")
    eq6["lv"] = 3
    eq6["upgrade_lv"] = 3
    db.add_item(g, q, "eq_test6", eq6)
    d6 = db.get_inventory(g, q)[0]["data"]
    check("背包旧档 upgrade_lv=3 → lv 3+3=6", d6.get("lv") == 6, f"lv={d6.get('lv')}")
    check("upgrade_lv 已删除", "upgrade_lv" not in d6, str(d6.keys()))
    # 6b. 已穿戴（get_player equipment 入口）
    clean_db()
    m = Main(None)
    make_player(g, q, name="迁移穿", cls="战士", level=30)
    eq6w = C.generate_roster_equip("eq_tie_jian")
    eq6w["lv"] = 3
    eq6w["upgrade_lv"] = 3
    db.update_player(g, q, equipment={"weapon": eq6w})
    d6w = db.get_player(g, q)["equipment"]["weapon"]
    check("已穿戴旧档 upgrade_lv=3 → lv 3+3=6", d6w.get("lv") == 6, f"lv={d6w.get('lv')}")
    check("已穿戴 upgrade_lv 已删除", "upgrade_lv" not in d6w, str(d6w.keys()))

    # 7. 详情显示：无『升级：Lv.X』行（真等级化 lv 显示在 Lv.N）
    print("[7] 详情显示")
    eq7 = C.generate_roster_equip("eq_tie_jian")
    eq7["lv"] = 6
    eq7.pop("upgrade_lv", None)
    from content.economy_cmds import _render_equip
    _lines = []
    _render_equip(eq7, _lines, equipped=False)
    _rc = "\n".join(_lines)
    check("详情不再显示『升级：Lv.X』行", "升级：Lv." not in _rc, _rc[:200])
    check("详情需求等级显示新 lv", "Lv.6" in _rc, _rc[:200])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
