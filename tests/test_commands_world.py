# -*- coding: utf-8 -*-
"""commands 层：世界域（地图/移动/传送/NPC/任务/探索/事件/垂钓/采集）（源自 v6/v6_events/v7/v11/v18/v19/v20/v30/v36/v38）

验证：
  1. 地图/移动：地图列表/移动/跨地图
  2. 传送：方碑激活/传送付费
  3. NPC：找/对话（含主线完成动态台词）
  4. 任务：主线/每日/支线接取与交还
  5. 探索：野外探索/精英怪
  6. 世界事件：讨伐/拍卖
  7. 垂钓/采集/挖掘
"""
import sys, os, sqlite3, time, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run  # ★ P5C-REPOINT：conftest 兼容面（同名同义）
from content.quests_flow import quest_kill_progress  # ★ P5C-REPOINT：直取包内真源（原 game.services.quests_flow）

# ★ P5C-REPOINT：原宿主薄壳 `game/services/quests_flow.py` 的注入
#   `quests_svc = game.services.quests` 随 game/** 删除而消失。按 REPOINT_MAP §2，
#   `game.services.quests` 的真源 = `content.profession_quests`
#   （bump_daily_progress / settle_daily_quest / DAILY_META_KEYS）。这里把该注入补回，
#   与已删薄壳逐键同义 —— 否则包内 `_bump_daily_progress` 会落到 facade
#   `_PKG_SURFACE["quests_svc"]` 指到的 `content.persistence.quests`（存档半边，无此函数）。
from content import profession_quests as _profession_quests  # noqa: E402
from content import quests_flow as _quests_flow  # noqa: E402
_quests_flow.bind_host(quests_svc=_profession_quests)

# ★ P5D-REPOINT：本文件「探索」步会经命令层真实开战
#   （`content.world_cmds.move` → `content.combat_cmds._open_battle` → `_attach_tlog`），
#   需要宿主平台件 `attach_tlog`（原 `game/services/battle_bridge.py::attach_tlog`）。
#   该宿主壳随 game/** 退役后终态无人注入 ⇒ 包内 fail-closed 抛 RuntimeError。
#   这里按宿主契约补上测试侧替身（**与宿主实现同义**：未启用流水 → 零行为返回 b；
#   启用 → 用包内采集器 `content.tlog_collect.BattleTLog` 挂引擎流水句柄）。
#   注：本文件断言的是世界域命令行为，流水只是开战路径上的平台副作用，判据一条未动。
from content import combat_cmds as _CC  # noqa: E402


def _attach_tlog(b, *, btype="monster", player=None, enemies=None, seed=None):
    from _engine_harness import tlog_setup
    try:
        tl = tlog_setup.tlog()
        if tl is None:
            return b
        from content.tlog_collect import BattleTLog
        BattleTLog(tl).attach(b, btype=btype, seed=seed, player=player, enemies=enemies)
    except Exception:                                        # noqa: BLE001
        pass
    return b


_CC.bind_host(attach_tlog=_attach_tlog)

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


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", level=5, gold=1000, cur_map="oak_town")

    print("【地图：地图列表】")
    out = await cmd(m, "map_view", "g1", "w1", "地图")
    check("地图显示", "橡木" in out or "地图" in out, out[:120])

    print("【移动】")
    # v87.14 空间连接：出城需先到出口子区域
    # v87.16 街道链：广场可达 1=镇长办公处 2=铁匠铺 3=旅店 4=草药铺 5=东大街
    # 出镇路径：广场 → 东大街(5) → 镇郊(1) → 橡木平原(2)
    out = await cmd(m, "move", "g1", "w1", "前往 5")
    p = db.get_player("g1", "w1")
    check("移动到东大街", p.get("cur_subarea") == "oak_town_street", str(p.get("cur_subarea")))
    out = await cmd(m, "move", "g1", "w1", "前往 1")
    p = db.get_player("g1", "w1")
    check("移动到镇郊", p.get("cur_subarea") == "oak_town_outskirts", str(p.get("cur_subarea")))
    out = await cmd(m, "move", "g1", "w1", "前往 橡木平原")
    check("移动有返回", len(out) > 5, out[:120])
    p = db.get_player("g1", "w1")
    check("地图切换", p.get("cur_map") == "oak_plain", str(p.get("cur_map")))
    # v54.1 修复：垂钓点地图查看不再抛 get_prof_level 缺参异常
    db.update_player("g1", "w1", cur_map="oak_plain")
    out = await cmd(m, "map_view", "g1", "w1", "地图")
    check("垂钓点地图显示正常", len(out) > 5 and "垂钓" in out or "此地" in out, out[:150])

    print("【探索：野外】")
    db.update_player("g1", "w1", cur_map="oak_plain")
    out = await cmd(m, "explore", "g1", "w1", "探索")
    check("探索有返回", len(out) > 10, out[:100])

    print("【传送：方碑】")
    out = await cmd(m, "portal_view", "g1", "w1", "方碑")
    check("方碑有返回", len(out) > 3, out[:120])
    # 激活/传送（若已激活过则提示不同）
    out = await cmd(m, "portal_activate", "g1", "w1", "激活 橡木镇")
    check("激活有返回", len(out) > 3, out[:120])

    print("【NPC：找/对话】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 铁匠")
    check("找NPC有返回", len(out) > 5, out[:120])
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("NPC对话有返回", len(out) > 5, out[:120])

    print("【任务：主线】")
    out = await cmd(m, "quest_view", "g1", "w1", "任务")
    check("任务列表有返回", "主线" in out or "任务" in out, out[:120])
    # 主线完成 → NPC 台词动态化（v36 模式）
    db.save_quests("g1", "w1", {"main_quest": None, "main_status": "", "main_progress": 0,
                               "daily": {}, "completed_main": ["q1"], "side": []})
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("主线完成后NPC台词", len(out) > 5, out[:120])

    print("【世界事件：讨伐】")
    out = await cmd(m, "world_event", "g1", "w1", "事件")
    check("事件列表有返回", len(out) > 5, out[:120])

    print("【垂钓/采集】")
    db.update_player("g1", "w1", cur_map="oak_plain", cur_subarea="oak_plain_3", apprentices=["fishing", "gather"])  # v87.17 垂钓点=溪边草地 + v95.22 拜师模拟
    db.clear_battle("g1", "w1")  # v55：先清战斗状态（前面探索/事件可能进过战斗）
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("垂钓有返回", len(out) > 5, out[:120])
    # v55 等待制：开始垂钓后是等待状态，立即再发提示剩余
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("垂钓等待中提示剩余", "还在垂钓" in out, out[:120])
    # v55 等待制：垂钓等待中采集被互斥拦截
    out = await cmd(m, "gather", "g1", "w1", "采集")
    check("等待中采集互斥拦截", "还在垂钓" in out, out[:120])
    # v55 等待制：把完成时间改成过去 → 惰性结算 + 自动开新轮
    # v127.5：等待存储已收编进 timed_events 引擎（timed_events_{qq} → key "prof_wait"），
    # 回拨完成时间改为直接写引擎存储：data.finish 与 expire 同时置到过去（到点被引擎 lazy 清）。
    st = m._prof_wait_state("g1", "w1")
    st["finish"] = int(time.time()) - 1
    db.set_event_state(f"timed_events_w1", json.dumps(
        {"prof_wait": {"type": st["type"], "expire": st["finish"],
                       "data": {"finish": st["finish"], "type": st["type"],
                                "spot": st.get("spot"), "spot_map": st.get("spot_map")}}},
        ensure_ascii=False))
    db.set_event_state(m._prof_wait_key("g1", "w1"), "")  # 清历史遗留键，防 residual 误读串台
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("垂钓到期结算+自动开新", ("钓上来" in out or "钓上了" in out or "垃圾" in out or "宝物" in out or "鱼王" in out) and "开始垂钓" in out, out[:200])
    # v55 等待制：清状态后采集正常开轮
    m._prof_wait_clear("g1", "w1")
    out = await cmd(m, "gather", "g1", "w1", "采集")
    check("采集有返回", len(out) > 5 and "开始采集" in out, out[:120])
    # v55 等待制：等级越高等待越短 + 保底 10 秒
    db.add_prof_exp("g1", "w1", "fishing", 900)
    lv = db.get_prof_level("g1", "w1", "fishing")
    # v110：固定 randint 取区间上界——_prof_wait_duration 未 seed 随机(基准±25%抖动)，
    # 高等级抽高值/低等级抽低值会翻转断言（run_all 内曾实测 47s>46s 假失败）
    _orig_randint = random.randint
    random.randint = lambda a, b: b
    try:
        wait_hi = m._prof_wait_duration("fishing", lv)
        wait_lo = m._prof_wait_duration("fishing", 1)
    finally:
        random.randint = _orig_randint
    check("等待随等级缩短", wait_hi <= wait_lo and wait_hi >= 10, f"Lv{lv}={wait_hi}s Lv1={wait_lo}s")
    # v55 装饰器统一互斥：垂钓等待中 移动/传送/探索/副本/讨伐 全被拦
    m._prof_wait_clear("g1", "w1")  # 先清掉前面测试残留的采集等待
    await cmd(m, "fishing", "g1", "w1", "垂钓")
    for hname, msg, label in [("move", "前往 橡木镇", "前往"), ("portal_travel", "传送 橡木镇", "传送"),
                               ("explore", "探索", "探索"), ("instance_cmd", "副本", "副本"), ("hunt_boss", "讨伐", "讨伐")]:
        out = await cmd(m, hname, "g1", "w1", msg)
        check(f"副业等待中{label}被拦", "还在垂钓" in out, out[:80])

    print("【数据：主线任务完整性】")
    missing = [q for q in C.MAIN_QUESTS if not q.get("story") or not q.get("ending")] if hasattr(C, "MAIN_QUESTS") else []
    if hasattr(C, "MAIN_QUESTS"):
        check("30 主线任务全部有 story/ending", len(missing) == 0, str([q.get("id") for q in missing[:5]]))
    else:
        print("  ⚠️ MAIN_QUESTS 未暴露，跳过")

    print("【v95.20 #103：指名接取进行中主线 → 明确提示而非支线列表】")
    clean_db()
    m2 = Main(None)
    await cmd(m2, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", level=5, gold=1000, cur_map="oak_town")
    # 找到第一环主线（pending）并推进到进行中（active）
    mq0 = C.MAIN_QUESTS[0]
    qs = db.get_quests("g1", "w1")
    qs["main_quest"] = mq0["id"]
    qs["main_status"] = "active"
    db.save_quests("g1", "w1", qs)
    out = await cmd(m2, "quest_accept", "g1", "w1", f"接取 {mq0['name']}")
    check("指名进行中主线→进行中提示", "进行中" in out and "无需重复" in out, out[:120])
    check("不回显支线列表", "【可接取任务】" not in out, out[:120])

    print("【v123d：『接取 <序号>』按列表序号接取（参数统一：展示序号即可选）】")
    clean_db()
    m4 = Main(None)
    await cmd(m4, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", level=10, gold=1000, cur_map="oak_town")
    # 主线 pending（giver 在橡木镇）→ 『接取 1』序号映射到主线名并接取
    out = await cmd(m4, "quest_accept", "g1", "w1", "接取 1")
    qs = db.get_quests("g1", "w1")
    check("『接取 1』接取主线（序号映射）", qs.get("main_status") == "active", str(qs.get("main_status")))
    # 主线 active 时无参数『接取』提示进行中（现有行为）
    out = await cmd(m4, "quest_accept", "g1", "w1", "接取")
    check("主线进行中提示", "进行中" in out, out[:120])
    # 主线完成（main_quest=None）→ 『接取』显示支线列表（带序号）
    qs["main_quest"] = None
    qs["completed_main"] = ["done"]
    db.save_quests("g1", "w1", qs)
    out = await cmd(m4, "quest_accept", "g1", "w1", "接取")
    check("接取列表带序号", "【可接取任务】" in out and "1. 📜" in out, out[:150])
    # 『接取 1』→ 接第一个支线（史莱姆果冻，s1）
    out = await cmd(m4, "quest_accept", "g1", "w1", "接取 1")
    qs = db.get_quests("g1", "w1")
    check("『接取 1』接取支线", "s1" in (qs.get("side") or {}), str(qs.get("side")))
    # 越界序号
    out = await cmd(m4, "quest_accept", "g1", "w1", "接取 99")
    check("越界序号提示无效", "序号无效" in out, out[:120])

    print("【v95.13 #126：kill_any 支线计数（护送商货）】")
    clean_db()
    m3 = Main(None)
    await cmd(m3, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", level=10, gold=1000, cur_map="silver_wind_road")
    qs = db.get_quests("g1", "w1")
    qs["side"] = {"s_caravan_escort": {"status": "active", "progress": {}}}
    db.save_quests("g1", "w1", qs)
    # 击杀任意怪 3 次（进度 1/5 → 3/5）
    for i in range(3):
        lines = quest_kill_progress("g1", "w1", {"name": "野狗"})
        joined = "|".join(lines)
        check(f"kill_any 第{i+1}次击杀有进度提示", f"{i+1}/5" in joined, joined[:100])
    qs2 = db.get_quests("g1", "w1")
    sq2 = qs2["side"]["s_caravan_escort"]
    check("progress any 累计 3", sq2.get("progress", {}).get("any") == 3, str(sq2.get("progress")))
    check("3/5 未 ready", sq2.get("status") == "active", str(sq2.get("status")))
    # 再杀 2 只（任意怪名不同也可）→ 5/5 ready
    for i in range(2):
        lines = quest_kill_progress("g1", "w1", {"name": "森林狼"})
        joined = "|".join(lines)
    qs3 = db.get_quests("g1", "w1")
    sq3 = qs3["side"]["s_caravan_escort"]
    check("5/5 转 ready", sq3.get("status") == "ready", str(sq3.get("status")))
    check("目标达成提示", "目标达成" in "|".join(lines), "|".join(lines)[:120])
    # 交付验证
    p0 = db.get_player("g1", "w1")
    g0, e0 = p0.get("gold", 0), p0.get("exp", 0)
    out = m3._complete_side_quest("g1", "w1", "s_caravan_escort")
    p1 = db.get_player("g1", "w1")
    check("kill_any 支线可交付", "奖励" in "|".join(out) or out == [], "|".join(out)[:150])
    # v169.2 金币校直：护送商货 gold 150→280（按耗时当量）；委托人谢礼仍允许浮动
    _lv = p0.get("level", 1)
    check("交付后金币+280（允许 v97.5 委托人谢礼加成）",
          g0 + 280 <= p1.get("gold", 0) <= g0 + 280 + 25 + _lv, f"{g0}->{p1.get('gold',0)}")
    check("交付后经验+1854（v169.1 任务经验校直：护送商货 300→1854）", p1.get("exp", 0) == e0 + 1854, f"{e0}->{p1.get('exp',0)}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
