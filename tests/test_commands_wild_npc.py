# -*- coding: utf-8 -*-
"""commands/core 层：9.4 野外 NPC + 时间季节系统（18 章）

验证：
  1. 数据完整性：WILD_NPCS/HIDDEN_NPCS 结构（map 存在/条件合法/unlock 前缀）
  2. 时间季节天气：时段/季节/天气判定（monkeypatch 固定）
  3. 条件判定：time/season/weather/min_level/flag/item
  4. 偶遇：条件满足 → 见闻录记录 + 30 分钟冷却 + 保底
  5. 『时间』指令 / 『见闻录』指令
  6. 『找 <野外NPC>』对话 + 支线 S36 offer + collect 交付（修复的 bug）
"""
import sys, os, sqlite3, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run
from content import time_weather as TW
from content import wild as W

# ★ P5D-REPOINT：原宿主薄壳 `game/services/quests_flow.py` 的注入
#   `quests_svc = game.services.quests` 随 game/** 删除而消失。按 REPOINT_MAP §2，
#   `game.services.quests` 的真源 = `content.profession_quests`
#   （bump_daily_progress / settle_daily_quest / DAILY_META_KEYS）。
#   这里把该注入补回（与已删薄壳逐键同义），否则包内 `_bump_daily_progress`
#   会落到 facade `_PKG_SURFACE["quests_svc"]` 指到的 `content.persistence.quests`
#   （存档半边，无此函数）⇒ 交任务路径 AttributeError。
from content import profession_quests as _profession_quests  # noqa: E402
from content import quests_flow as _quests_flow  # noqa: E402
_quests_flow.bind_host(quests_svc=_profession_quests)

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


def set_clock(period="day", season="summer", weather="sunny"):
    """monkeypatch wild 模块的时间/天气（wild 里是 import 绑定，改 W 属性）"""
    W.current_period = lambda: period
    W.current_season = lambda: season
    W.today_weather = lambda map_id=None: weather
    W.current_period_orig = TW.current_period
    # ★ P5D-REPOINT：原 `C.current_period = lambda: period`（v95.15 #71）在终态取下：
    #   生产侧读点 = 包内 `content/wild.py` 的**模块全局**（`_wild_unseen_hint` 经包内取件；
    #   宿主 `game.content` 已退役）。包侧聚合门面 `_engine_harness.C` 是 `_Aggregate`
    #   转发面（无 `current_period` 可写），上面那行 `W.current_period` 已打在真读点上
    #   —— 与同函数里 2026-09-14 对 `C.current_season` 的处置同款（冗余行，等价语义）。
    #   判据零改动：本文件全部断言仍作用于 W/TW 真源与命令输出。


def clear_wild_meta(gid, qid):
    db.delete_event_state(W.wild_meta_key(gid, qid) if hasattr(W, "wild_meta_key") else f"wildmeta_{gid}_{qid}")


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    await cmd(m, "register", "g1", "w2", "注册 法师 新手 男")
    db.update_player("g1", "w1", level=20, gold=5000, cur_map="oak_plain")
    set_clock("day", "summer", "sunny")
    clear_wild_meta("g1", "w1")
    clear_wild_meta("g1", "w2")

    print("【9.4 数据完整性】")
    check("WILD_NPCS ≥28", len(C.WILD_NPCS) >= 28, str(len(C.WILD_NPCS)))
    check("HIDDEN_NPCS ≥13（v87 增 3）", len(C.HIDDEN_NPCS) >= 13, str(len(C.HIDDEN_NPCS)))
    bad = []
    # ★ P5D-REPOINT：`C.ALL_WILD` 在包侧聚合门面未登记（宿主门面 PEP 562 读口）
    #   ⇒ 取真源模块的 PEP 562 兼容读口 `content/wild.py::_ALL_WILD()`（`W` 已在顶部
    #   直接取自包内真源），条数与宿主门面同值（63）。断言文字未改。
    for nid, npc in W._ALL_WILD().items():
        if not npc.get("name") or not npc.get("icon"):
            bad.append((nid, "缺名字/图标"))
        if not npc.get("map") and not npc.get("roam"):
            bad.append((nid, "缺地图和 roam"))
        if npc.get("map") and npc["map"] not in C.MAP_BY_ID:
            bad.append((nid, f"地图不存在 {npc['map']}"))
        if npc.get("roam"):
            for rm in npc["roam"]:
                if rm not in C.MAP_BY_ID:
                    bad.append((nid, f"roam 地图不存在 {rm}"))
        un = npc.get("unlock")
        if un and not un.startswith(("flag:", "item:", "quest:", "quest_done:", "stats:")):
            bad.append((nid, f"unlock 前缀非法 {un}"))
        cond = npc.get("condition", {})
        for t in cond.get("time", []):
            if t not in ("morning", "day", "evening", "night"):
                bad.append((nid, f"time 非法 {t}"))
    check("38 个 NPC 结构完整（map/unlock/条件合法）", not bad, str(bad[:3]))

    print("【9.4 时间/季节/天气】")
    check("当前时段合法", TW.current_period() in ("morning", "day", "evening", "night"), TW.current_period())
    check("当前季节合法", TW.current_season() in ("spring", "summer", "autumn", "winter"), TW.current_season())
    import datetime
    check("固定时刻=黄昏", TW.current_period(datetime.datetime(2026, 8, 6, 19, 0)) == "evening")
    check("固定时刻=清晨", TW.current_period(datetime.datetime(2026, 8, 6, 6, 0)) == "morning")
    check("固定月份=冬", TW.current_season(datetime.datetime(2026, 1, 6)) == "winter")
    check("固定月份=秋", TW.current_season(datetime.datetime(2026, 10, 6)) == "autumn")

    print("【9.4 条件判定】")
    p = {"level": 20}
    npc_day = {"condition": {"time": ["day"]}}
    npc_night = {"condition": {"time": ["night"]}}
    npc_winter = {"condition": {"season": ["winter"]}}
    npc_rain = {"condition": {"weather": "rain"}}
    npc_minlv = {"condition": {"min_level": 30}}
    check("白天 NPC 条件满足", W.base_conditions_met("t1", npc_day, p, "g1", "w1"))
    check("夜晚 NPC 白天不满足", not W.base_conditions_met("t2", npc_night, p, "g1", "w1"))
    check("冬季 NPC 夏季不满足", not W.base_conditions_met("t3", npc_winter, p, "g1", "w1"))
    check("雨天 NPC 晴天不满足", not W.base_conditions_met("t4", npc_rain, p, "g1", "w1"))
    check("等级不足不满足", not W.base_conditions_met("t5", npc_minlv, p, "g1", "w1"))
    set_clock("night", "winter", "rain")
    check("夜晚+冬季+雨天全满足", W.base_conditions_met("t2", npc_night, p, "g1", "w1")
          and W.base_conditions_met("t3", npc_winter, p, "g1", "w1")
          and W.base_conditions_met("t4", npc_rain, p, "g1", "w1"))
    set_clock("day", "summer", "sunny")

    print("【9.4 偶遇 + 见闻录 + 冷却】")
    hit = W.roll_wild_encounter("g1", "w1", p, "oak_plain")
    check("白天 oak_plain 偶遇老马", hit and hit[0] == "w_old_trader", str(hit))
    check("见闻录记录老马", "w_old_trader" in W.met_wild("g1", "w1"), str(W.met_wild("g1", "w1")))
    # 30 分钟冷却：立刻再 roll 不返回
    hit2 = W.roll_wild_encounter("g1", "w1", p, "oak_plain")
    check("30 分钟冷却内不重复偶遇", hit2 is None, str(hit2))

    print("【9.4 保底机制】")
    # _roll_random 单测：miss=7 → 必出（不管 chance）
    meta = W._get_meta("g1", "w2")
    meta["miss"] = {"h_owl": 7}
    W._save_meta("g1", "w2", meta)
    random.seed(1)
    check("保底：miss=7 必出", W._roll_random("h_owl", {"chance": 0.05}, "g1", "w2") is True)
    check("保底后 miss 清零", "h_owl" not in W._get_meta("g1", "w2").get("miss", {}), str(W._get_meta("g1", "w2")))
    # miss=6 且概率不中 → 计数 +1
    meta = W._get_meta("g1", "w2")
    meta["miss"] = {"h_owl": 6}
    W._save_meta("g1", "w2", meta)
    random.seed(1)
    W._roll_random("h_owl", {"chance": 0.0001}, "g1", "w2")
    check("miss=6 未中 → 计数到 7", W._get_meta("g1", "w2").get("miss", {}).get("h_owl") == 7, str(W._get_meta("g1", "w2")))
    clear_wild_meta("g1", "w2")

    print("【9.4 『时间』指令】")
    out = await cmd(m, "time_cmd", "g1", "w1", "时间")
    check("时间面板显示时段/季节/天气", "【时间】" in out and ("白天" in out or "夜晚" in out or "清晨" in out or "黄昏" in out), out[:200])
    check("附近人影提示（老马白天在橡木平原）", "附近似乎有人影" in out and "游商·老马" in out, out[:300])

    print("【9.4 『见闻录』指令】")
    out = await cmd(m, "wild_notes", "g1", "w2", "见闻录")
    check("w2 见闻录空白", "还是空白" in out, out[:200])
    out = await cmd(m, "wild_notes", "g1", "w1", "见闻录")
    check("w1 见闻录有老马", "游商·老马" in out, out[:300])

    print("【9.4 『找 野外NPC』】")
    db.update_player("g1", "w1", cur_map="white_deer_forest")
    out = await cmd(m, "find_npc", "g1", "w1", "找 隐士·莱德")
    check("白天找隐士（黄昏/夜晚出现）→ 时段未到提示(#71)", "还没到出现的时候" in out and "🧭" in out, out[:200])
    set_clock("night", "summer", "sunny")
    # v127.5 限时NPC：偶遇制——先在夜晚偶遇隐士（白鹿之森夜晚候选首个）才在场
    p = {"level": 20}
    hit = W.roll_wild_encounter("g1", "w1", p, "white_deer_forest")
    check("夜晚白鹿之森偶遇隐士（在场）", bool(hit) and hit[0] == "w_sage_ryder", str(hit))
    out = await cmd(m, "find_npc", "g1", "w1", "找 隐士·莱德")
    check("夜晚找隐士 → 找到并对话", "隐士·莱德" in out and "今天还没遇到" not in out, out[:300])
    set_clock("day", "summer", "sunny")

    print("【9.4 支线 S36：采药女 offer + 『交任务』交付（修复 bug）】")
    db.update_player("g1", "w1", cur_map="white_deer_forest")
    set_clock("day", "summer", "sunny")
    # v127.5 限时NPC：偶遇制——任务 giver 也先偶遇在场才能接/交（鱼鱼拍板：在场期可接可交）
    hit = W.roll_wild_encounter("g1", "w1", p, "white_deer_forest")
    check("白天白鹿之森偶遇采药女（在场）", bool(hit) and hit[0] == "w_forest_girl", str(hit))
    out = await cmd(m, "find_npc", "g1", "w1", "找 采药女·小荨")
    check("找采药女接 S36", "采药女的心愿" in out, out[:400])
    q = db.get_quests("g1", "w1")
    check("S36 已接取", "s36" in q.get("side", {}), str(q.get("side")))
    # 材料不够时交任务 → 提示缺材料
    out = await cmd(m, "turn_in", "g1", "w1", "交付任务")
    check("材料不够提示（月光草×10）", "月光草" in out and "还差" in out, out[:300])
    # 给 10 份月光草（mat_ ID 入包）→ 交任务完成
    db.add_item("g1", "w1", "mat_yue_guang_cao", {"name": "月光草", "type": "材料", "stackable": True}, 10)
    out = await cmd(m, "turn_in", "g1", "w1", "交付任务")
    check("交付完成 S36", "支线完成" in out and "采药女的心愿" in out, out[:400])
    q = db.get_quests("g1", "w1")
    # v95.12：交付后条目标记 done 保留（防自动重接）
    check("S36 标记 done（完成）", q.get("side", {}).get("s36", {}).get("status") == "done", str(q.get("side")))
    have = db.count_item("g1", "w1", "mat_yue_guang_cao")
    check("月光草被扣除（collect 修复生效）", have == 0, f"剩余 {have}")

    print("【#151 商店上下文：野外行商货摊标题跟随在场 NPC】")
    # 小荨（w_forest_girl，morning/day 出现，funcs 含 trade）在白鹿之森 → 商店标题应是她而非游商老马
    db.update_player("g1", "w1", cur_map="white_deer_forest")
    set_clock("day", "summer", "sunny")
    out = await cmd(m, "shop", "g1", "w1", "商店")
    check("#151 小荨在场 → 货摊标题=采药女·小荨", "采药女·小荨的货摊" in out, out[:300])
    check("#151 不再误显示游商·老马的货摊", "游商·老马的货摊" not in out, out[:300])
    # 老马（w_old_trader，day 出现）在橡木平原 → 标题应为老马
    db.update_player("g1", "w1", cur_map="oak_plain")
    out = await cmd(m, "shop", "g1", "w1", "商店")
    check("#151 老马在场 → 货摊标题=游商·老马", "游商·老马的货摊" in out, out[:300])

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
