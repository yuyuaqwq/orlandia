# -*- coding: utf-8 -*-
"""v127.5 限时NPC 全链路测试（偶遇 → 在场限时 → 地图/对话可见可找 → 过期同时消失 → 再偶遇恢复）。

覆盖（docs/TIMED_EVENT_PLAN_v1275.md 第 3、4 节行为变更清单）：
1. 偶遇前：『找 老马』不可找（提示"今天还没遇到"）；『对话』空参无野外NPC
2. 偶遇命中：roll_wild_encounter 挂 wild_npc 限时事件（map=oak_plain，60 分钟）
3. 偶遇后：map_view 含在场NPC区块 + ⏳倒计时；_start_talk_list 含它（带序号）
4. 『对话 老马』/『找 老马』可找到并渲染对话
5. 移动离开该图 → map_view 不显示（但未过期）；回图 → 仍在
6. 过期后：map_view 与对话同时不可见/不可找（get_timed 惰性清零）；对话中过期 → "已经离开了"
7. 再偶遇恢复：清冷却再 roll → 重新在场可见可找

固定环境：玩家在 橡木平原(oak_plain)，白天；w_old_trader（游商·老马，duration=60）唯一在场候选。
"""
import sys, os, asyncio, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import FakeEvent, run, clean_db, Main, db, make_player
from content import wild as W

passed = failed = 0
def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

GID, QID = "g1", "1001"

def set_clock():
    """固定白天/夏季/晴（w_old_trader 仅要求 time:day）"""
    W.current_period = lambda: "day"
    W.current_season = lambda: "summer"
    W.today_weather = lambda map_id=None: "sunny"
    from content import time_weather as TW
    try:
        TW.current_period()
    except Exception:
        pass

def clear_last():
    """清 30 分钟偶遇冷却（测试内多次 roll 需要）"""
    meta = W._get_meta(GID, QID)
    meta.setdefault("last", {})["w_old_trader"] = 0
    W._save_meta(GID, QID, meta)

async def ask(m, handler, msg):
    ev = FakeEvent(GID, QID, msg)
    return "".join(str(x) for x in await run(getattr(m, handler), ev))

async def main():
    clean_db()
    db.init_db()
    m = Main(None)
    make_player(GID, QID, "甲", "战士")
    db.update_player(GID, QID, cur_map="oak_plain", cur_subarea="")
    set_clock()
    clear_last()
    # 清残留在场事件（保证从"未偶遇"状态起）
    from content import timed_events as TE
    TE.remove_timed(GID, QID, "wild:w_old_trader")

    print("【1. 偶遇前：不可找、列表无野外NPC】")
    out = await ask(m, "find_npc", "找 游商·老马")
    check("偶遇前『找 老马』提示今天没遇到", "今天还没遇到" in out, out[:120])
    st = db.get_talk_state(GID, QID)
    check("偶遇前不进入对话状态", not (st and st.get("npc")), str(st))
    out = await ask(m, "talk_choice", "对话")
    check("偶遇前『对话』空参无野外NPC", "游商·老马" not in out, out[:120])

    print("【2. 偶遇命中 → 挂在场限时事件】")
    p = db.get_player(GID, QID)
    hit = W.roll_wild_encounter(GID, QID, p, "oak_plain")
    check("橡木平原白天偶遇老马", bool(hit) and hit[0] == "w_old_trader", str(hit))
    ev = TE.get_timed(GID, QID, "wild:w_old_trader")
    check("限时事件已挂载", bool(ev), str(ev))
    check("事件 type=wild_npc / map=oak_plain",
          ev and ev["type"] == "wild_npc" and ev["data"].get("map") == "oak_plain"
          and ev["data"].get("npc_id") == "w_old_trader", str(ev))
    check("时长按 duration 分钟（≈60 分钟）", ev and ev["remain"] > 55 * 60
          and ev["remain"] <= 60 * 60, str(ev and ev["remain"]))

    print("【3. 显示出口：地图 / 裸对话列表】")
    out = await ask(m, "map_view", "地图")
    check("map_view 含『🧭 游历的旅人：』区块", "游历的旅人" in out, out[:400])
    check("map_view 含在场NPC行", "游商·老马" in out, out[:400])
    check("map_view 行带 ⏳ 倒计时", "⏳剩" in out, out[:400])
    out = await ask(m, "talk_choice", "对话")
    check("裸『对话』列表含在场老马", "游商·老马" in out, out[:300])
    check("裸『对话』列表带序号与 ⏳", "1." in out and "⏳剩" in out, out[:300])

    print("【4. 查找出口：『对话 老马』可找】")
    out = await ask(m, "find_npc", "找 老马")
    check("『找 老马』找到并渲染对话", "游商·老马" in out, out[:200])
    out = await ask(m, "talk_choice", "对话 老马")
    check("『对话 老马』找到（talk_choice fallback→find_npc）", "游商·老马" in out, out[:200])
    db.clear_talk_state(GID, QID)

    print("【5. 移动离开该图 → 不显示；回图未过期 → 仍在】")
    db.update_player(GID, QID, cur_map="oak_town", cur_subarea="oak_town_1")
    out = await ask(m, "map_view", "地图")
    check("去橡木镇 map_view 不含橡木平原在场老马", "游商·老马" not in out, out[:300])
    ev = TE.get_timed(GID, QID, "wild:w_old_trader")
    check("离开后事件未过期仍在", bool(ev), str(ev))
    db.update_player(GID, QID, cur_map="oak_plain", cur_subarea="")
    out = await ask(m, "map_view", "地图")
    check("回橡木平原（未过期）仍在场可见", "游商·老马" in out and "⏳剩" in out, out[:300])

    print("【6. 过期 → 显示与对话同时消失】")
    # 短时重挂模拟"时间流逝至过期"（顶替刷新，data 不变）
    TE.set_timed(GID, QID, "wild:w_old_trader", "wild_npc",
                 data={"npc_id": "w_old_trader", "map": "oak_plain"}, duration_sec=1)
    time.sleep(1.2)
    check("过期后 get_timed 返回 None", TE.get_timed(GID, QID, "wild:w_old_trader") is None)
    out = await ask(m, "map_view", "地图")
    check("过期后 map_view 不再显示在场老马", "游商·老马" not in out and "游历的旅人" not in out, out[:300])
    out = await ask(m, "talk_choice", "对话")
    check("过期后裸『对话』列表不含老马", "游商·老马" not in out, out[:300])
    out = await ask(m, "find_npc", "找 老马")
    check("过期后『找 老马』不可找（今天没遇到）", "今天还没遇到" in out, out[:150])
    out = await ask(m, "talk_choice", "对话 老马")
    check("过期后『对话 老马』不可找", "今天还没遇到" in out, out[:150])

    print("【6b. 对话中过期 → 会话作废（'已经离开了'）】")
    db.set_talk_state(GID, QID, "w_old_trader", "start")  # 手动造一个进行中会话
    st = db.get_talk_state(GID, QID)
    check("先造进行中会话", bool(st and st.get("npc") == "w_old_trader"), str(st))
    out = await ask(m, "talk_choice", "继续")
    check("对话中过期 → 已经离开了并清会话", "已经离开" in out, out[:150])
    st = db.get_talk_state(GID, QID)
    check("过期后会话已清除", not (st and st.get("npc")), str(st))

    print("【7. 再偶遇恢复】")
    clear_last()
    hit2 = W.roll_wild_encounter(GID, QID, p, "oak_plain")
    check("再探索偶遇老马恢复", bool(hit2) and hit2[0] == "w_old_trader", str(hit2))
    ev = TE.get_timed(GID, QID, "wild:w_old_trader")
    check("恢复后在场事件重新挂载", bool(ev), str(ev))
    out = await ask(m, "map_view", "地图")
    check("恢复后 map_view 再次显示在场老马 + ⏳", "游商·老马" in out and "⏳剩" in out, out[:300])
    out = await ask(m, "find_npc", "找 老马")
    check("恢复后『找 老马』再次可找", "游商·老马" in out, out[:200])
    db.clear_talk_state(GID, QID)

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
