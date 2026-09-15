# -*- coding: utf-8 -*-
"""v140 波3.3/3.7：章节礼包 + 每日补给箱 + 事件菜单命令行为测试

覆盖：
1. 章节礼包：engine.check_player_level_up 每 10 级发一次（event_state 防重复）
2. 每日补给箱：『领取补给箱』命令（SUPPLY_BOX 3 档限额）
3. 事件菜单：『今日事件』总览 / 『事件 <地图名>』深查
4. 称号发放：任务奖励 title 字段（兼容 id/中文名）
"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, r"C:/Users/yuyu/qqbot")
os.environ.setdefault("GWEN_GAME_DB", "test_game_data_v140_cmds.db")
from _engine_harness import FakeEvent, run, clean_db, make_player, new_main
from _engine_harness import C, db
from content.gameplay_rules import check_player_level_up

passed = 0
def check(name, cond, detail=""):
    global passed
    assert cond, f"{name}: {detail}"
    passed += 1
    print(f"  ✓ {name}")

def test_chapter_pack():
    print("【1. 章节礼包（每 10 级发一次）】")
    clean_db()
    m = new_main()
    p = make_player("g1", "q1", "测试", "战士", level=9)
    p["exp"] = C.exp_to_next(9) * 3  # 连升 3 级（9→12）
    # 检查升级日志包含章节礼包
    logs, p2 = check_player_level_up("g1", "q1", dict(p))
    check("9→10 级发章节礼包", any("章节里程碑" in l for l in logs), str(logs))
    # 防重复：同一级不再发
    ck = f"chapter_pack_10_q1"
    check("event_state 已记录", db.get_event_state(ck) is not None)

def test_supply_box():
    print("【2. 每日补给箱（3 档限额）】")
    clean_db()
    m = new_main()
    make_player("g1", "q1", "测试", "战士", level=1)
    ev = FakeEvent("g1", "q1", "领取补给箱")
    outs = asyncio.get_event_loop().run_until_complete(run(m.event_menu, ev))
    joined = "\n".join(outs)
    check("补给箱命令有输出", len(outs) > 0, str(outs[:2]))
    check("材料箱发放", "每日材料箱" in joined or "材料箱" in joined, joined[:200])
    # 再领一次应提示已领
    outs2 = asyncio.get_event_loop().run_until_complete(run(m.event_menu, ev))
    joined2 = "\n".join(outs2)
    check("重复领取提示已领", "已领取" in joined2 or "已领" in joined2, joined2[:200])

def test_event_menu():
    print("【3. 事件菜单（今日事件总览 + 单图深查）】")
    clean_db()
    m = new_main()
    make_player("g1", "q1", "测试", "战士", level=1)
    ev = FakeEvent("g1", "q1", "今日事件")
    outs = asyncio.get_event_loop().run_until_complete(run(m.event_menu, ev))
    joined = "\n".join(outs)
    check("今日事件总览有输出", len(outs) > 0, str(outs[:2]))
    check("包含今日奇遇栏", "今日奇遇" in joined, joined[:300])
    # 单图深查（用第一个地图）
    first_map = (C.MAPS[0] if isinstance(C.MAPS, list) else list(C.MAPS.values())[0])
    mname = first_map.get("name", "")
    if mname:
        ev2 = FakeEvent("g1", "q1", f"事件 {mname}")
        outs2 = asyncio.get_event_loop().run_until_complete(run(m.event_menu, ev2))
        joined2 = "\n".join(outs2)
        check(f"事件 {mname} 有输出", len(outs2) > 0, str(outs2[:2]))

def test_title_grant():
    print("【4. 称号发放（q1_6 铁牌冒险者）】")
    clean_db()
    # 找 q1_6 任务（MAIN_QUESTS 是 list）
    q = next((x for x in C.MAIN_QUESTS if x.get("id") == "q1_6"), None) or {}
    check("q1_6 存在", bool(q), str([x.get("id") for x in C.MAIN_QUESTS[:10]]))
    if q:
        check("q1_6 带 title 字段", q.get("title") in ("iron_adventurer", "铁牌冒险者")
              or "铁牌" in str(q.get("title", "")), str(q.get("title")))
    # ★ PFIX P3：`C.QUEST_ADD`（旧 `game/data/quest_add_v140.py`）随 B14 `90fc06b`
    #   「删宿主 game/data 87 文件」退场（`content/catalog_legacy.py:GAP_REASON` 记录
    #   「宿主 data 子模块句柄（随 data 消失；实测无真读点）」），包内无该真源，
    #   也不造数据。P3 二选一取「测试改读包内真源」：
    #     · q1_6 的 v140 称号真源 = `content/catalog_quests.MAIN_QUESTS` 的 `title` 字段
    #       （id `iron_adventurer`；上面第 1 条 check 读的 C.MAIN_QUESTS 与它同源）；
    #     · 称号条件真源 = `content/title_conds.py::_t_iron_adventurer`（`@register`）。
    from content.catalog_quests import MAIN_QUESTS as _MAIN_QUESTS
    from content import title_conds as _TC
    qa = next((x for x in _MAIN_QUESTS if x.get("id") == "q1_6"), None) or {}
    check("包内真源 q1_6 的 title = iron_adventurer（v140 铁牌冒险者）",
          qa.get("title") == "iron_adventurer", str(qa))
    _conds = getattr(_TC, "CONDITIONS", {}) or {}
    check("包内真源注册了 iron_adventurer 称号条件（铁牌冒险者）",
          "iron_adventurer" in _conds, str(sorted(_conds)[:8]))

def test_supply_box_data():
    print("【5. 补给箱数据完整性】")
    boxes = getattr(C, "SUPPLY_BOX", None) or []
    check("SUPPLY_BOX 3 档", len(boxes) == 3, str(boxes))
    ids = [b.get("id") for b in boxes]
    check("3 档 id 正确", ids == ["supply_mat", "supply_tool", "supply_rich"], str(ids))

def test_chapter_pack_data():
    print("【6. 章节礼包数据完整性】")
    packs = getattr(C, "CHAPTER_PACK", None) or []
    check("CHAPTER_PACK 10 档", len(packs) == 10, str(len(packs)))
    lvs = [p.get("lv") for p in packs]
    check("Lv10-100 每 10 级", lvs == [10, 20, 30, 40, 50, 60, 70, 80, 90, 100], str(lvs))

if __name__ == "__main__":
    test_chapter_pack_data()
    test_supply_box_data()
    test_chapter_pack()
    test_supply_box()
    test_event_menu()
    test_title_grant()
    print(f"\n结果: {passed} 通过, 0 失败")
