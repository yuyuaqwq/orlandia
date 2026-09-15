# -*- coding: utf-8 -*-
"""v97.1 告示委托系统验证：寻猫·虎斑 完整链路

覆盖：
  1. 告示板交互展示委托单
  2. 非告示板子区域接取被拒
  3. 告示板前接取成功（side 写入 active）
  4. find 型条件探索事件：白鹿之森探索按概率触发，任务推进 ready
  5. 交付：回橡木镇找玛莎（交付任务）→ 任务完成 + 奖励
  6. 完成后再看告示板：委托撤下
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail).encode('utf-8', 'replace').decode('utf-8', 'replace')[:300]}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 委托猎人 男")
    # 橡木镇广场（有告示板）
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_1")

    print("【1. 告示板展示委托】")
    out = await cmd(m, "interact_prop", "g1", "w1", "交互 告示板")
    check("展示委托单", "寻猫·虎斑" in out and "告示委托" in out, out[:400])

    print("【2. 非告示板子区域接取被拒】")
    db.update_player("g1", "w1", cur_subarea="oak_town_2")
    out = await cmd(m, "quest_accept", "g1", "w1", "接取 寻猫·虎斑")
    check("提示去告示板", "告示板" in out and "接取" in out, out[:200])

    print("【3. 告示板前接取成功】")
    db.update_player("g1", "w1", cur_subarea="oak_town_1")
    out = await cmd(m, "quest_accept", "g1", "w1", "接取 寻猫·虎斑")
    check("接取成功", "支线" in out and "寻猫" in out, out[:300])
    qs = db.get_quests("g1", "w1")
    check("任务状态 active", qs["side"].get("s_board_cat", {}).get("status") == "active", str(qs.get("side")))
    out = await cmd(m, "quest_accept", "g1", "w1", "接取 寻猫·虎斑")
    check("重复接取提示已接", "已接取" in out, out[:200])

    print("【4. find 条件探索事件】")
    # 错误地图不触发（v101.19c 确定性修复：探索事件随机给金币/经验/战斗，前后重置消除污染）
    db.update_player("g1", "w1", gold=50, exp=0, cur_map="oak_plain", cur_subarea="")
    handled, ev_text = m._handle_explore_event("g1", "w1", db.get_player("g1", "w1"), C.MAP_BY_ID["oak_plain"])
    check("错误地图不触发(正常事件)", handled is True and "虎斑" not in str(ev_text), str(ev_text)[:200])
    _p0 = db.get_player("g1", "w1")
    db.update_player("g1", "w1", gold=50, exp=0, hp=_p0["max_hp"], mp=_p0["max_mp"])
    qs = db.get_quests("g1", "w1")
    check("任务仍 active", qs["side"]["s_board_cat"]["status"] == "active", str(qs["side"]["s_board_cat"]))
    # 正确地图 + 强制命中（mock random.random → 0）
    db.update_player("g1", "w1", cur_map="white_deer_forest", cur_subarea="")
    orig_random = random.random
    random.random = lambda: 0.0
    try:
        out = m._roll_find_quest_events("g1", "w1", db.get_player("g1", "w1"), C.MAP_BY_ID["white_deer_forest"])
    finally:
        random.random = orig_random
    check("触发找到虎斑猫", out is not None and "虎斑猫" in out, str(out)[:300])
    check("提示回去找玛莎", "玛莎" in out, str(out)[:300])
    qs = db.get_quests("g1", "w1")
    check("任务推进 ready", qs["side"]["s_board_cat"]["status"] == "ready", str(qs["side"]["s_board_cat"]))
    # 任务 ready 后不再重复触发
    out2 = m._roll_find_quest_events("g1", "w1", db.get_player("g1", "w1"), C.MAP_BY_ID["white_deer_forest"])
    check("ready 后不再触发", out2 is None, str(out2))

    print("【5. 交付结算】")
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_1")
    out = await cmd(m, "turn_in", "g1", "w1", "交付任务")
    check("交付成功", "寻猫" in out and "完成" in out, out[:300])
    qs = db.get_quests("g1", "w1")
    check("任务 done", qs["side"]["s_board_cat"]["status"] == "done", str(qs["side"]["s_board_cat"]))
    p = db.get_player("g1", "w1")
    check("奖励到账(升级结算)", p["gold"] >= 110 and p["level"] >= 2, f"gold={p['gold']} level={p['level']} exp={p['exp']}")

    print("【6. 完成后告示板撤下委托】")
    out = await cmd(m, "interact_prop", "g1", "w1", "交互 告示板")
    check("委托已撤下", "告示委托" not in out or "恢复" in out, out[:300])

    print("【7. find 目标文案显示】")
    out = await cmd(m, "quest_view", "g1", "w1", "任务")
    # v101.25i3：任务面板过滤 done——已完成任务不再显示（鱼鱼拍板）
    check("任务视图过滤已完成", "寻猫" not in out, out[:300])

    print(f"\n结果：{passed} 通过 / {failed} 失败")
    return 1 if failed else 0

if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
