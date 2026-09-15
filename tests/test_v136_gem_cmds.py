# -*- coding: utf-8 -*-
"""v136 原石系统命令层验收（GWEN_GAME_DB 隔离，不碰生产库）

覆盖：打孔（白装拦截/成功加孔/副业门槛拦截/重复打孔拦截/金币不足）、
镶嵌（空孔成功/层数超范围拦截/孔位已占拦截/无孔拦截）、
拆卸（扣钱+原石回背包）、合成（3→1 上级/不足拦截/传说II拦截）、
面板（_render_equip 带 sockets 显示孔位）。

独立运行：python tests/test_v136_gem_cmds.py
"""
import os
import sys
import asyncio
import random

os.environ.setdefault("GWEN_GAME_DB", os.path.abspath("test_v136_gem_cmds.db"))
sys.path.insert(0, "tests")

from _engine_harness import clean_db, make_player, Main, FakeEvent, run  # noqa: E402
from _engine_harness import C, db  # noqa: E402

g = "g_gem"
q = "q_gem"

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
    """把玩家放到橡木镇铁匠铺（oak_town_3, craft funcs）。"""
    db.update_player(g, q, cur_map="oak_town", cur_subarea="oak_town_3")


def craft_to_lv(g, q, lv):
    """把锻造副业升到指定等级。"""
    db.activate_prof(g, q, "craft")
    for _ in range(500):
        nv, _ = db.add_prof_exp(g, q, "craft", 10)
        if nv >= lv:
            return nv
    return db.get_prof_level(g, q, "craft")


def make_gem(tier, stat="atk"):
    """构造一颗确定属性的原石（stats 值 = 该层 mult）。"""
    return {
        "name": f"{C.GEM_TIER_NAMES[tier]}·攻击+{int(C.GEM_TIERS[tier]['mult'] * 100)}%",
        "type": "幸运宝石",
        "gem": True,
        "stats": {stat: C.GEM_TIERS[tier]["mult"]},
        "tier": tier,
        "icon": "💎",
    }


def main():
    print("== v136 原石系统命令层验收 ==")
    # ---------- 0. 数据表/核心层 ----------
    print("[0] 数据表/核心层")
    check("GEM_DRILL 蓝装 500/锻造Lv.1", C.GEM_DRILL["blue"]["cost"] == 500 and C.GEM_DRILL["blue"]["craft_lv"] == 1)
    check("GEM_SOCKETS 蓝装 1 孔(S1)", C.GEM_SOCKETS["blue"]["count"] == 1)
    check("GEM_SOCKETS 紫装 2 孔(S2)", C.GEM_SOCKETS["purple"]["count"] == 2)
    check("GEM_SOCKETS 橙装 3 孔(S3)", C.GEM_SOCKETS["orange"]["count"] == 3)
    gem = make_gem(1)
    g2 = C.gem_combine([gem, gem, gem])
    check("gem_combine 3×tier1 → tier2", g2["tier"] == 2, g2["name"])
    check("拆卸费 tier1 = 500", C.gem_socket_cost(gem) == 500)

    # ---------- 1. 打孔 ----------
    print("[1] 打孔")
    # 1a. 白装不能打孔
    clean_db()
    m = Main(None)
    make_player(g, q, name="打孔白装", cls="战士", level=30)
    db.update_player(g, q, gold=999999)
    eq_w = C.generate_roster_equip("eq_tie_jian")  # white
    db.add_item(g, q, "eq_w1", eq_w)
    craft_to_lv(g, q, 5)
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, "打孔 铁剑")
    out = asyncio.run(run(m.gem_drill, ev))
    txt = out[0] if out else ""
    check("白装打孔拦截", "没有孔位" in txt, txt[:120])
    # 1b. 蓝装打孔成功（扣 500 金 + sockets）
    clean_db()
    m = Main(None)
    make_player(g, q, name="打孔蓝装", cls="战士", level=30)
    db.update_player(g, q, gold=999999)
    eq_b = C.generate_roster_equip("eq_tie_jian")
    eq_b["quality"] = "blue"
    eq_b["name"] = "🔵·铁剑"
    db.add_item(g, q, "eq_b1", eq_b)
    craft_to_lv(g, q, 3)
    goto_smith(m, g, q)
    gold_before = db.get_player(g, q)["gold"]
    ev = FakeEvent(g, q, "打孔 铁剑")
    out = asyncio.run(run(m.gem_drill, ev))
    txt = out[0] if out else ""
    check("蓝装打孔成功提示", "打孔成功" in txt, txt[:120])
    inv = db.get_inventory(g, q)
    d = inv[0]["data"] if inv else {}
    check("sockets 写入 S1 空孔", d.get("sockets") == {"S1": None}, str(d.get("sockets")))
    gold_after = db.get_player(g, q)["gold"]
    check("打孔扣 500 金", gold_before - gold_after == 500, f"diff={gold_before - gold_after}")
    # 1c. 已有孔位重复打孔拦截
    ev = FakeEvent(g, q, "打孔 铁剑")
    out = asyncio.run(run(m.gem_drill, ev))
    txt = out[0] if out else ""
    check("已有孔位重复打孔拦截", "已经有" in txt and "不用再打" in txt, txt[:120])
    # 1d. 锻造副业不足拦截
    clean_db()
    m = Main(None)
    make_player(g, q, name="打孔副业", cls="战士", level=30)
    db.update_player(g, q, gold=999999)
    eq_p = C.generate_roster_equip("eq_tie_jian")
    eq_p["quality"] = "purple"
    eq_p["name"] = "🟣·铁剑"
    db.add_item(g, q, "eq_p1", eq_p)
    db.activate_prof(g, q, "craft")  # 学徒 Lv.1，紫色打孔需 Lv.3
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, "打孔 铁剑")
    out = asyncio.run(run(m.gem_drill, ev))
    txt = out[0] if out else ""
    check("紫装打孔副业不足拦截(需Lv.3)", "锻造副业 Lv.3" in txt, txt[:120])
    # 1e. 金币不足拦截
    clean_db()
    m = Main(None)
    make_player(g, q, name="打孔缺钱", cls="战士", level=30)
    db.update_player(g, q, gold=100)
    eq_b2 = C.generate_roster_equip("eq_tie_jian")
    eq_b2["quality"] = "blue"
    eq_b2["name"] = "🔵·铁剑"
    db.add_item(g, q, "eq_b2", eq_b2)
    craft_to_lv(g, q, 2)
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, "打孔 铁剑")
    out = asyncio.run(run(m.gem_drill, ev))
    txt = out[0] if out else ""
    check("金币不足拦截", "金币" in txt, txt[:120])
    # 1f. 非铁匠铺拦截
    db.update_player(g, q, cur_map="oak_town", cur_subarea="oak_town_4")  # 旅店
    ev = FakeEvent(g, q, "打孔 铁剑")
    out = asyncio.run(run(m.gem_drill, ev))
    txt = out[0] if out else ""
    check("非铁匠铺拦截", "需要到铁匠铺" in txt, txt[:120])

    # ---------- 2. 镶嵌 ----------
    print("[2] 镶嵌")
    # 2a. 空孔镶嵌成功（原石扣出背包，sockets 写入）
    clean_db()
    m = Main(None)
    make_player(g, q, name="镶嵌成功", cls="战士", level=30)
    db.update_player(g, q, gold=999999)
    eq_b = C.generate_roster_equip("eq_tie_jian")
    eq_b["quality"] = "blue"
    eq_b["name"] = "🔵·铁剑"
    eq_b["sockets"] = {"S1": None}
    db.add_item(g, q, "eq_b1", eq_b)
    gem1 = make_gem(1)
    db.add_item(g, q, "gem_a1", gem1)
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, f"镶嵌 铁剑 {gem1['name']}")
    out = asyncio.run(run(m.gem_socket, ev))
    txt = out[0] if out else ""
    check("镶嵌成功提示", "镶嵌成功" in txt, txt[:120])
    inv = db.get_inventory(g, q)
    d = inv[0]["data"] if inv else {}
    check("S1 已镶入原石", d.get("sockets", {}).get("S1", {}).get("name") == gem1["name"],
          str(d.get("sockets")))
    gems_left = [it for it in inv if it["data"].get("gem")]
    check("原石已扣出背包", len(gems_left) == 0, f"剩 {len(gems_left)} 颗")
    # 2b. 层数超范围拦截（蓝孔 1-2 层，用 tier 3）
    clean_db()
    m = Main(None)
    make_player(g, q, name="层数超", cls="战士", level=30)
    eq_b = C.generate_roster_equip("eq_tie_jian")
    eq_b["quality"] = "blue"
    eq_b["name"] = "🔵·铁剑"
    eq_b["sockets"] = {"S1": None}
    db.add_item(g, q, "eq_b1", eq_b)
    gem3 = make_gem(3)
    db.add_item(g, q, "gem_a3", gem3)
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, f"镶嵌 铁剑 {gem3['name']}")
    out = asyncio.run(run(m.gem_socket, ev))
    txt = out[0] if out else ""
    check("层数超范围拦截", "只能镶" in txt, txt[:120])
    inv = db.get_inventory(g, q)
    d = inv[0]["data"] if inv else {}
    check("拦截后孔位仍空", d.get("sockets", {}).get("S1") is None, str(d.get("sockets")))
    check("拦截后原石未扣", len([it for it in inv if it["data"].get("gem")]) == 1)
    # 2c. 孔位已占重复镶嵌拦截
    clean_db()
    m = Main(None)
    make_player(g, q, name="重复镶", cls="战士", level=30)
    eq_b = C.generate_roster_equip("eq_tie_jian")
    eq_b["quality"] = "blue"
    eq_b["name"] = "🔵·铁剑"
    eq_b["sockets"] = {"S1": dict(make_gem(1))}
    db.add_item(g, q, "eq_b1", eq_b)
    gem2 = make_gem(2)
    db.add_item(g, q, "gem_a2", gem2)
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, f"镶嵌 铁剑 {gem2['name']}")
    out = asyncio.run(run(m.gem_socket, ev))
    txt = out[0] if out else ""
    check("孔位已占拦截", "已经镶了" in txt or "都满了" in txt, txt[:120])
    inv = db.get_inventory(g, q)
    check("拦截后原石未扣", len([it for it in inv if it["data"].get("gem")]) == 1)
    # 2d. 无孔位装备拦截
    clean_db()
    m = Main(None)
    make_player(g, q, name="无孔", cls="战士", level=30)
    eq_b = C.generate_roster_equip("eq_tie_jian")
    eq_b["quality"] = "blue"
    eq_b["name"] = "🔵·铁剑"
    db.add_item(g, q, "eq_b1", eq_b)
    gem1 = make_gem(1)
    db.add_item(g, q, "gem_a1", gem1)
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, f"镶嵌 铁剑 {gem1['name']}")
    out = asyncio.run(run(m.gem_socket, ev))
    txt = out[0] if out else ""
    check("无孔位拦截", "还没有孔位" in txt, txt[:120])

    # ---------- 3. 拆卸 ----------
    print("[3] 拆卸")
    clean_db()
    m = Main(None)
    make_player(g, q, name="拆卸", cls="战士", level=30)
    db.update_player(g, q, gold=999999)
    eq_b = C.generate_roster_equip("eq_tie_jian")
    eq_b["quality"] = "blue"
    eq_b["name"] = "🔵·铁剑"
    eq_b["sockets"] = {"S1": dict(make_gem(1))}
    db.add_item(g, q, "eq_b1", eq_b)
    goto_smith(m, g, q)
    gold_before = db.get_player(g, q)["gold"]
    ev = FakeEvent(g, q, "拆卸 铁剑 S1")
    out = asyncio.run(run(m.gem_remove, ev))
    txt = out[0] if out else ""
    check("拆卸成功提示", "拆卸成功" in txt, txt[:120])
    gold_after = db.get_player(g, q)["gold"]
    check("拆卸扣 500 金(tier1)", gold_before - gold_after == 500, f"diff={gold_before - gold_after}")
    inv = db.get_inventory(g, q)
    d = inv[0]["data"] if inv else {}
    check("孔位已清空", d.get("sockets", {}).get("S1") is None, str(d.get("sockets")))
    gems_back = [it for it in inv if it["data"].get("gem")]
    check("原石已回背包", len(gems_back) == 1 and gems_back[0]["data"]["name"].startswith("碎裂的幸运宝石"),
          str([it["data"].get("name") for it in gems_back]))
    check("回包 key 为 gem_ 前缀", gems_back[0]["key"].startswith("gem_"), gems_back[0]["key"])
    # 空孔拆卸拦截
    ev = FakeEvent(g, q, "拆卸 铁剑 S1")
    out = asyncio.run(run(m.gem_remove, ev))
    txt = out[0] if out else ""
    check("空孔拆卸拦截", "空孔" in txt, txt[:120])

    # ---------- 4. 合成 ----------
    print("[4] 合成")
    # 4a. 3 颗同级 → 1 颗上级
    clean_db()
    m = Main(None)
    make_player(g, q, name="合成", cls="战士", level=30)
    db.update_player(g, q, gold=999999)
    gem1 = make_gem(1)
    for i in range(3):
        db.add_item(g, q, f"gem_c{i}", dict(gem1))
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, f"原石合成 {gem1['name']}")
    out = asyncio.run(run(m.gem_combine, ev))
    txt = out[0] if out else ""
    check("合成成功提示", "合成成功" in txt, txt[:120])
    inv = db.get_inventory(g, q)
    gems = [it for it in inv if it["data"].get("gem")]
    check("3 颗 → 1 颗", len(gems) == 1 and sum(it["count"] for it in gems) == 1, str([(it["key"], it["data"].get("tier")) for it in gems]))
    check("合成后 tier=2", gems[0]["data"]["tier"] == 2, gems[0]["data"]["name"])
    # 4b. 不足 3 颗拦截
    clean_db()
    m = Main(None)
    make_player(g, q, name="不足", cls="战士", level=30)
    gem1 = make_gem(1)
    db.add_item(g, q, "gem_x", dict(gem1))
    db.add_item(g, q, "gem_y", dict(gem1))
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, f"原石合成 {gem1['name']}")
    out = asyncio.run(run(m.gem_combine, ev))
    txt = out[0] if out else ""
    check("不足 3 颗拦截", "需要 3 颗" in txt, txt[:120])
    inv = db.get_inventory(g, q)
    check("拦截后原石未扣", sum(it["count"] for it in inv if it["data"].get("gem")) == 2)
    # 4c. 神话(tier=10) 不可再合成
    clean_db()
    m = Main(None)
    make_player(g, q, name="传说", cls="战士", level=30)
    gem10 = make_gem(10)
    for i in range(3):
        db.add_item(g, q, f"gem_t{i}", dict(gem10))
    goto_smith(m, g, q)
    ev = FakeEvent(g, q, f"原石合成 {gem10['name']}")
    out = asyncio.run(run(m.gem_combine, ev))
    txt = out[0] if out else ""
    check("神话 不可再合成拦截", "无法再合成" in txt, txt[:120])
    inv = db.get_inventory(g, q)
    check("神话 拦截后未扣", sum(it["count"] for it in inv if it["data"].get("gem")) == 3)

    # ---------- 5. 原石查看 + 面板 ----------
    print("[5] 原石查看/面板")
    clean_db()
    m = Main(None)
    make_player(g, q, name="查看", cls="战士", level=30)
    gem1 = make_gem(1)
    gem5 = make_gem(5)
    db.add_item(g, q, "gem_v1", dict(gem1))
    db.add_item(g, q, "gem_v2", dict(gem5))
    ev = FakeEvent(g, q, "原石")
    out = asyncio.run(run(m.gem_view, ev))
    txt = out[0] if out else ""
    check("原石面板含名称", "碎裂的幸运宝石" in txt, txt[:150])
    check("原石面板含层数/孔位需求", "阶1" in txt and "蓝孔" in txt, txt[:150])
    check("原石面板含属性", "攻击" in txt, txt[:150])
    # 5b. 空背包原石面板提示
    clean_db()
    m = Main(None)
    make_player(g, q, name="空", cls="战士", level=30)
    ev = FakeEvent(g, q, "原石")
    out = asyncio.run(run(m.gem_view, ev))
    txt = out[0] if out else ""
    check("空背包原石提示", "还没有幸运宝石" in txt, txt[:120])
    # 5c. 面板 _render_equip 带 sockets 显示孔位
    from content.economy_cmds import _render_equip
    eq_p = C.generate_roster_equip("eq_tie_jian")
    eq_p["quality"] = "purple"
    eq_p["name"] = "🟣·铁剑"
    eq_p["sockets"] = {"S1": dict(make_gem(2)), "S2": None}
    _lines = []
    _render_equip(eq_p, _lines, equipped=False)
    _rc = "\n".join(_lines)
    check("面板含原石孔位行", "💎 幸运宝石：" in _rc, _rc[:300])
    check("面板 S1 显示已镶原石", "S1:💎" in _rc, _rc[:300])
    check("面板 S2 显示空孔", "S2:空" in _rc, _rc[:300])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

# pytest 兼容入口：直接跑本文件为独立脚本（main() 内全部断言）；
# pytest 收集时自动执行（与 tests/test_v135_upgrade.py 同款双模式脚手架）
if os.environ.get("PYTEST_CURRENT_TEST"):
    main()
