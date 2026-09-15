# -*- coding: utf-8 -*-
"""v104 修复回归：副业 / 强化 / 附魔 6 项（2026-08-13）

覆盖：
  1. 附魔遗忘不死锁（P0）：拜师附魔→Lv.2→遗忘→学徒资格清空→再激活被拜师门槛拦
     （不再免拜师直冲 Lv.2 门槛死锁）→重新拜师(拜师礼 50 经验)→附魔通过门槛正常拿经验
  2. 强化 +1~+4 失败不掉级（P1）：+2 失败保级；+5 失败掉 2 级（+5→+3）
  3. 满级面板（P2）：Lv.10 显示"已满级"且无空经验条（不再 0/200）
  4. 每日任务重 roll（P1）：锁定任务副业已遗忘→查看任务→重新抽取
  5. 遗忘清等待条件化（P1）：垂钓等待中遗忘炼金→垂钓状态保留（不被误清）
  6. 排行全服(跨群)（v113.5 T1 修订 v104 P1 群内过滤）：群 A 高等级玩家在全服榜中可见（与等级榜 top_players 同口径）

运行：python tests/test_v104_prof_enhance.py（exit=0 全过）
"""
import sys, os, time, random
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
        print(f"  ❌ {name} {detail}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

def reset_profs(gid, qid):
    for k in ("gather", "mining", "fishing", "alchemy", "craft", "cooking", "enhance", "enchant"):
        db.forget_prof(gid, qid, k)

def add_equip(gid, qid, name="试炼剑", quality="blue"):
    key = f"eq_t_{qid}_{name}"
    db.remove_item(gid, qid, key, 999)  # 防跨用例同 key 冲突（inventory UNIQUE(qq_id,item_key)）
    db.add_item(gid, qid, key, {"name": name, "type": "武器", "slot": "weapon",
                                "quality": quality, "lv": 3, "atk": 12, "stackable": False}, 1)

def get_item(gid, qid, name):
    for it in db.get_inventory(gid, qid):
        if it["data"].get("name") == name:
            return it["data"]
    return None

async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")

    # ============ 1. 附魔遗忘不死锁（v104 P0） ============
    print("【1. 附魔遗忘不死锁（v104 P0）】")
    reset_profs("g1", "w1")
    db.update_player("g1", "w1", apprentices=["enchant"], cur_map="oak_town",
                     cur_subarea="oak_town_3", gold=5000)
    db.activate_prof("g1", "w1", "enchant")
    db.add_prof_exp("g1", "w1", "enchant", 50)  # 拜师礼 50 经验 → Lv.2
    check("前置：拜师礼后附魔 Lv.2", db.get_prof_level("g1", "w1", "enchant") == 2,
          str(db.get_prof_level("g1", "w1", "enchant")))
    out = await cmd(m, "prof_forget", "g1", "w1", "遗忘副业 附魔")
    check("遗忘附魔成功", "遗忘了「附魔」" in out, out[:150])
    p = db.get_player("g1", "w1")
    check("v104 P0：学徒资格清空(apprentices 不含 enchant)",
          "enchant" not in (p.get("apprentices") or []), str(p.get("apprentices")))
    check("等级清零回 Lv.1", db.get_prof_level("g1", "w1", "enchant") == 1,
          str(db.get_prof_level("g1", "w1", "enchant")))
    check("激活位空出", "enchant" not in db.get_activated_profs("g1", "w1"),
          str(db.get_activated_profs("g1", "w1")))
    # 再激活：未拜师 → 被拜师门槛拦截（旧版残留学徒=免拜师直冲 Lv.2 门槛→死锁）
    add_equip("g1", "w1", "试炼剑")
    db.add_item("g1", "w1", "rn_brutal_test", {"name": "史诗符文·残忍", "type": "符文",
                                               "effect": "brutal", "lvl": 1,
                                               "desc": "暴击伤害+30%"}, 1)
    out = await cmd(m, "enchant", "g1", "w1", "附魔 试炼剑 史诗符文·残忍")
    check("未拜师再激活被拜师门槛拦（死锁路径已封）", "还没解锁" in out, out[:160])
    check("不再是 Lv.2 门槛死锁", "需要附魔副业 Lv.2" not in out, out[:160])
    # 重新拜师（unlock_prof 拜师礼 50 经验 → Lv.2）→ 附魔通过门槛并正常获得经验
    db.update_player("g1", "w1", apprentices=["enchant"])
    db.add_prof_exp("g1", "w1", "enchant", 50)
    _exp_before = db.get_professions("g1", "w1")["enchant"]["exp"]
    out = await cmd(m, "enchant", "g1", "w1", "附魔 试炼剑 史诗符文·残忍")
    check("重新拜师后附魔成功（死锁解除）", "符文刻印成功" in out, out[:200])
    # 附魔成功 +1 经验（可能叠加每日任务 +50 奖励，只断言经验确有增长）
    _exp_after = db.get_professions("g1", "w1")["enchant"]["exp"]
    check("能正常获取经验(exp 增长)", _exp_after > _exp_before,
          f"before={_exp_before} after={_exp_after}")

    # ============ 2. 强化 +1~+4 失败不掉级（v104 M11） ============
    print("【2. 强化失败不掉级（v104 M11）】")
    reset_profs("g1", "w1")
    db.update_player("g1", "w1", apprentices=["enhance"], cur_map="oak_town",
                     cur_subarea="oak_town_3", gold=50000)
    db.add_prof_exp("g1", "w1", "enhance", 1000)  # Lv.10（+5 需 Lv.6，封顶无干扰）
    add_equip("g1", "w1", "试炼剑")
    _orig_random = random.random
    try:
        random.random = lambda: 0.0  # 强制成功
        for _ in range(2):
            out = await cmd(m, "enhance", "g1", "w1", "强化 试炼剑")
        check("前置：强化到 +2", get_item("g1", "w1", "试炼剑").get("enhance") == 2,
              str(get_item("g1", "w1", "试炼剑")))
        random.random = lambda: 0.9999  # 强制失败
        out = await cmd(m, "enhance", "g1", "w1", "强化 试炼剑")
        d = get_item("g1", "w1", "试炼剑")
        check("+2→+3 失败不掉级(+2 保留)", "保住了等级" in out and d.get("enhance") == 2,
              f"{out[:120]} | item={d}")
        random.random = lambda: 0.0
        for _ in range(3):
            out = await cmd(m, "enhance", "g1", "w1", "强化 试炼剑")
        check("前置：强化到 +5", get_item("g1", "w1", "试炼剑").get("enhance") == 5,
              str(get_item("g1", "w1", "试炼剑")))
        random.random = lambda: 0.9999
        out = await cmd(m, "enhance", "g1", "w1", "强化 试炼剑")
        d = get_item("g1", "w1", "试炼剑")
        check("+5→+6 失败掉 1 级(+5→+4)", "降级到 +4" in out and d.get("enhance") == 4,
              f"{out[:120]} | item={d}")
    finally:
        random.random = _orig_random

    # ============ 3. 满级面板（v104 P2） ============
    print("【3. 满级面板（v104 P2）】")
    reset_profs("g1", "w1")
    db.update_player("g1", "w1", apprentices=["gather"])
    db.activate_prof("g1", "w1", "gather")
    db.add_prof_exp("g1", "w1", "gather", 2200)  # v105 新曲线：累计 2100 满级 Lv.10（原 1000 按旧线性曲线）
    out = await cmd(m, "profession_view", "g1", "w1", "副业")
    check("Lv.10 显示「已满级」", "已满级" in out, out[:200])
    check("无空经验条(不再 0/200) 且显示 Lv.10", "0/200" not in out and "Lv.10" in out, out[:200])

    # ============ 4. 每日任务重 roll（v104 P1） ============
    print("【4. 每日任务重 roll（v104 P1）】")
    reset_profs("g1", "w1")
    db.update_player("g1", "w1", apprentices=["enchant"])
    db.activate_prof("g1", "w1", "enchant")
    today = time.strftime("%Y-%m-%d")
    # 锁定一个指向已遗忘/未激活副业（锻造）的任务
    db.set_event_state(f"prof_daily_w1_{today}", "craft|锻造装备|1|50|0|0")
    out = await cmd(m, "daily_prof", "g1", "w1", "副业任务")
    check("任务重抽为已激活副业(附魔)", "锻造" not in out and "附魔" in out, out[:200])
    raw = db.get_event_state(f"prof_daily_w1_{today}")
    check("重抽已落库(enchant)", bool(raw) and raw.startswith("enchant|"), str(raw))

    # ============ 5. 遗忘清等待条件化（v104 P1） ============
    print("【5. 遗忘清等待条件化（v104 P1）】")
    reset_profs("g1", "w1")
    db.update_player("g1", "w1", apprentices=["fishing", "alchemy"],
                     cur_map="oak_plain", cur_subarea="oak_plain_3")
    db.activate_prof("g1", "w1", "fishing")
    db.activate_prof("g1", "w1", "alchemy")
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    st = m._prof_wait_state("g1", "w1")
    check("前置：垂钓等待中", bool(st) and st.get("type") == "fishing", str(st))
    out = await cmd(m, "prof_forget", "g1", "w1", "遗忘副业 炼金")
    check("遗忘炼金成功", "遗忘了「炼金」" in out, out[:150])
    st2 = m._prof_wait_state("g1", "w1")
    check("v104 P1：垂钓状态保留（不被误清）",
          bool(st2) and st2.get("type") == "fishing", str(st2))
    check("炼金确实已遗忘", "alchemy" not in db.get_activated_profs("g1", "w1"),
          str(db.get_activated_profs("g1", "w1")))
    m._prof_wait_clear("g1", "w1")

    # ============ 6. 排行全服(跨群)（v113.5 T1 修订 v104 群内过滤） ============
    print("【6. 排行全服(跨群)：他群玩家可见（v113.5 T1）】")
    await cmd(m, "register", "gA", "qA", "注册 战士 群A大佬 男")
    await cmd(m, "register", "gB", "qB", "注册 战士 群B萌新 男")
    db.add_prof_exp("gA", "qA", "gather", 1000)  # 群A：Lv.7（总分 14）
    db.add_prof_exp("gB", "qB", "gather", 20)    # 群B：Lv.2（总分 9）
    out = await cmd(m, "profession_view", "gB", "qB", "副业 排行")
    check("群B排行出现群A玩家(全服榜，与等级榜 top_players 同口径)", "群A大佬" in out, out[:200])
    check("群B排行含本群玩家", "群B萌新" in out, out[:200])
    out = await cmd(m, "profession_view", "gA", "qA", "副业 排行")
    check("群A排行含群A玩家", "群A大佬" in out, out[:200])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
