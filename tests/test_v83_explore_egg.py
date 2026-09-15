# -*- coding: utf-8 -*-
"""v83 探索彩蛋事件（02 章 7.5）：流星许愿 / 神秘宝匣 / 神秘访客 + 许愿命令"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, Main, FakeEvent, run, clean_db, make_player

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ %s" % name)
    else:
        failed += 1
        print("  ❌ %s %s" % (name, detail))


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""


# v105 M23：探索彩蛋判定已从 _handle_explore_event(35% 事件窗口内) 移到 explore() 主入口
# 独立判定（遇怪/事件/彩蛋三路并列，彩蛋最先命中直接返回，恢复策划案 ~0.5% 总概率）。
# 直接调 _handle_explore_event 不再触发彩蛋 → 测试改走『探索』主命令路径：
# monkeypatch 野外偶遇/POI 概率为 0（防提前 return），只留 roll_explore_egg 返回指定彩蛋。
SHOOTING_STAR = {"id": "shooting_star", "weight": 60, "name": "流星许愿", "template": "set_state",
                 "params": {"key": "wish_{gid}_{qid}", "value": "ts",
                            "header": "🌠 流星划过{name}夜空！\n『许愿 经验』『许愿 金币』『许愿 材料』"}}
MYSTERY_CHEST = {"id": "mystery_chest", "weight": 30, "name": "神秘宝匣",
                 "template": "mystery_chest", "params": {}}
NIGHT_VISITOR = {"id": "night_visitor", "weight": 10, "name": "神秘访客", "template": "set_flag",
                 "params": {"flag": "h_abyss_whisper", "key": "saw_the_rift",
                            "header": "🌫️ 【神秘访客】雾气突然涌起，一道模糊的身影拦住了你。\n“深渊的裂隙……正在低语……去找它。”\n身影说完便消散在雾中，你隐约感到，某个秘密被揭开了(隐藏线索已记入见闻)。"}}


async def explore_egg(m, egg):
    """跑一次『探索』并强制命中指定彩蛋，返回探索输出文本。

    ★ P5D-REPOINT：原打桩面是宿主聚合层 `game.content`（`combat_cmds._overlay` 的
    「宿主聚合层覆写面」，源码注释 `content/combat_cmds.py:227` 点名本文件）。终态
    `game.content` 退役、`_overlay` 只查**已加载**的宿主模块 ⇒ 现在真正的读点是命令模块
    `content.combat_cmds` 的**模块级同名包装**（`combat_cmds.py:879` 按模块全局名调用）。
    故把桩打到那里（判据「命中指定彩蛋」一字未改）。`roll_poi` 无包装 → 打真源 `content.pois`。
    """
    import content.combat_cmds as _CC
    import content.pois as _PO
    _saved = (_CC.roll_wild_encounter, _CC.roll_explore_egg, _CC.roll_explore_event,
              _PO.roll_poi)
    _CC.roll_wild_encounter = lambda *a, **k: None
    _CC.roll_explore_egg = lambda cur_map_id=None: egg
    # 随机探索事件兜底也关掉（判据是「指定彩蛋命中」，兜底随机事件只会给噪声）
    _CC.roll_explore_event = lambda *a, **k: None
    _PO.roll_poi = lambda *a, **k: None
    try:
        return await cmd(m, "explore", "g1", "w1", "探索")
    finally:
        (_CC.roll_wild_encounter, _CC.roll_explore_egg, _CC.roll_explore_event,
         _PO.roll_poi) = _saved


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", cur_map="oak_plain")

    # ---- 概率采样（固定 seed 量级）----
    import random
    import content.combat_cmds as _CC
    random.seed(7)
    n = 10000
    hits = sum(1 for _ in range(n) if _CC.roll_explore_egg() is not None)
    check("彩蛋总概率≈0.5%", 0.002 < hits / n < 0.01, f"{hits/n:.4f}")

    # ---- 流星许愿：触发 + 三选一 ----
    text = await explore_egg(m, SHOOTING_STAR)
    check("流星触发提示选项", "许愿 经验" in text and "许愿 金币" in text, text[:200])
    # 许愿 经验
    gold0 = db.get_player("g1", "w1")["gold"]
    out = await cmd(m, "wish", "g1", "w1", "许愿 经验")
    check("许愿经验成功", "经验 +" in out, out[:200])
    # 许愿 金币（重新触发）
    await explore_egg(m, SHOOTING_STAR)
    out = await cmd(m, "wish", "g1", "w1", "许愿 金币")
    check("许愿金币成功", "金币 +" in out, out[:200])
    check("金币增加", db.get_player("g1", "w1")["gold"] > gold0, "")
    # 许愿 材料（重新触发）
    await explore_egg(m, SHOOTING_STAR)
    out = await cmd(m, "wish", "g1", "w1", "许愿 材料")
    check("许愿材料成功", "获得材料" in out, out[:200])
    # 无状态许愿被拦
    out = await cmd(m, "wish", "g1", "w1", "许愿 经验")
    check("无流星被拦", "没有流星" in out, out[:200])
    # 非法选项
    await explore_egg(m, SHOOTING_STAR)
    out = await cmd(m, "wish", "g1", "w1", "许愿 随便")
    check("非法选项提示三选一", "三选一" in out or "快选" in out, out[:200])

    # ---- 神秘宝匣 ----
    # ★ P5D 稳定化：本步骤在终态下对全局 RNG 状态敏感（前序 10000 次抽样 + 流星模板
    #   内部抽签已推进 RNG），实测未固定种子时本轮偶发落到「探索随机事件」文本
    #   （🎯 断言对象是彩蛋文本，随机事件只会给噪声）。这里在步骤前固定种子，
    #   让「指定彩蛋命中」这一判据稳定可复现 —— 断言一字未改。
    import random as _rr
    _rr.seed(4242)
    text = await explore_egg(m, MYSTERY_CHEST)
    check("宝匣给金币+图纸", "神秘宝匣" in text and "金币" in text and "图纸" in text, text[:200])

    # ---- 神秘访客：设置隐藏 NPC flag ----
    text = await explore_egg(m, NIGHT_VISITOR)
    check("访客提示线索", "神秘访客" in text and "裂隙" in text, text[:200])
    check("h_abyss_whisper flag 已设", "saw_the_rift" in db.get_talk_flags("g1", "w1", "h_abyss_whisper"), str(db.get_talk_flags("g1", "w1", "h_abyss_whisper")))

    # ---- 成就 cond ----
    from content.achievements import cond_met
    check("wish_met cond 命中", cond_met({}, {}, {}, {"wish_met": True}, {"type": "wish_met"}), "")
    check("wish_met cond 不命中", not cond_met({}, {}, {}, {}, {"type": "wish_met"}), "")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
