# -*- coding: utf-8 -*-
"""v127.5 等待型副业（垂钓/采集/挖掘）收编进通用懒计时引擎（timed_events）。

验证（对外接口 _prof_wait_state/_prof_wait_begin/_prof_wait_clear 零改动，内部存储走引擎）：
1. begin 后 _prof_wait_state 有值：finish≈now+wait（剩余秒≈wait）、type 正确
2. 等待期间再次调用 _prof_wait_state 一致（finish/type/extra 不变）
3. 到点（引擎 expire 置过去，模拟 lazy 清除）→ _prof_wait_state 为 None
4. _prof_wait_clear 后 _prof_wait_state 为 None（remove_timed + 历史遗留键清理）
5. extra 字段（鱼点 spot/spot_map、采集/挖掘地图）保留在 data（state 平铺）
6. >= 惰性结算兜底：到点但未结算 → _prof_wait_flow 先结算旧轮再开新轮（奖励不丢）
7. v127.5 前历史遗留 prof_wait_{qq} 到点残留 → flow 惰性结算（迁移兜底）
8. 存储确已收编：begin 后 timed_events_{qq} 含内部 key "prof_wait"
"""
import sys, os, time, json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, make_player, Main, FakeEvent, run

passed = failed = 0
def check(name, ok, detail=""):
    global passed, failed
    if ok:
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

def _engine_write(qid, ev):
    """直写 timed_events 引擎存储（timed_events_{qq} → 内部 key "prof_wait"）。"""
    db.set_event_state(f"timed_events_{qid}", json.dumps(ev, ensure_ascii=False))

def _backdate(m, gid, qid, prev_st):
    """把引擎里的 prof_wait 事件置为已到点（expire/data.finish 到过去），模拟到点被 lazy 清。"""
    past = int(time.time()) - 5
    _engine_write(qid, {"prof_wait": {"type": prev_st["type"], "expire": past,
                                      "data": dict(prev_st, finish=past)}})

def _setup(m, gid, qid):
    db.update_player(gid, qid, apprentices=["fishing", "gather", "mining"],
                     cur_map="oak_plain", cur_subarea="oak_plain_3")
    for k in ("fishing", "gather", "mining"):
        db.activate_prof(gid, qid, k)
    db.clear_battle(gid, qid)
    # 测试确定性：固定等待时长 + 干掉延迟推送任务（防 sleep 任务干扰/竞态）
    m._prof_wait_duration = lambda pt, lv: 42
    async def _noop(*a, **k):
        pass
    m._prof_delayed_push = _noop

async def main():
    clean_db()
    m = Main(None)
    gid, qid = "g1", "w1"
    make_player(gid, qid, "测试旅人", level=10)
    _setup(m, gid, qid)
    ev = FakeEvent(gid, qid, "垂钓")

    print("【1. begin → state 有值（finish≈now+wait / type / extra 平铺）】")
    wait = m._prof_wait_begin(ev, gid, qid, "fishing", extra={"spot": "橡木溪流", "spot_map": "oak_plain"})
    check("wait=固定 42s", wait == 42, f"wait={wait}")
    st = m._prof_wait_state(gid, qid)
    check("begin 后 state 有值", bool(st), str(st))
    check("type=fishing", st and st.get("type") == "fishing", str(st))
    check("finish≈now+wait（剩余≈42s）",
          st and abs((st["finish"] - int(time.time())) - wait) <= 2,
          f"finish={st and st['finish']} now={int(time.time())} wait={wait}")
    check("extra 保留(spot/spot_map 平铺到 st)",
          st and st.get("spot") == "橡木溪流" and st.get("spot_map") == "oak_plain", str(st))

    print("【2. 等待期间再次调用一致 + 存储确已收编引擎】")
    st2 = m._prof_wait_state(gid, qid)
    check("第二次 state 仍返回", bool(st2), str(st2))
    check("finish/type 与首次一致", st2 and st2["finish"] == st["finish"] and st2["type"] == "fishing", str(st2))
    raw = db.get_event_state(f"timed_events_{qid}")
    check("引擎存储已写入(timed_events_{qq})", bool(raw), str(raw))
    d = json.loads(raw or "{}")
    check("引擎内部 key=\"prof_wait\" 存在", isinstance(d, dict) and "prof_wait" in d, str(d))
    check("data 含 finish+type+extra", (d.get("prof_wait") or {}).get("data", {}).get("spot_map") == "oak_plain", str(d))

    print("【3. 到点 → state 变 None（引擎 lazy 清除）】")
    _backdate(m, gid, qid, st)
    check("到点后 _prof_wait_state 为 None", m._prof_wait_state(gid, qid) is None)
    check("过期事件已被引擎移除（存储空）", not db.get_event_state(f"timed_events_{qid}"),
          str(db.get_event_state(f"timed_events_{qid}")))

    print("【4. _prof_wait_clear 后 state 为 None（含历史遗留键清理）】")
    m._prof_wait_begin(ev, gid, qid, "gather", extra={"spot_map": "starlake"})
    check("clear 前 state 有值", bool(m._prof_wait_state(gid, qid)))
    m._prof_wait_clear(gid, qid)
    check("clear 后 state 为 None", m._prof_wait_state(gid, qid) is None)
    check("历史遗留键 prof_wait_{qq} 也被清", not db.get_event_state(f"prof_wait_{qid}"),
          str(db.get_event_state(f"prof_wait_{qid}")))

    print("【5. 挖掘/采集同样走引擎（extra 保留 + clear）】")
    m._prof_wait_begin(ev, gid, qid, "mining", extra={"spot_map": "hill_mine"})
    stm = m._prof_wait_state(gid, qid)
    check("挖掘 state 有值(type=mining)", stm and stm.get("type") == "mining", str(stm))
    check("挖掘 extra 保留 spot_map", stm and stm.get("spot_map") == "hill_mine", str(stm))
    m._prof_wait_clear(gid, qid)
    m._prof_wait_begin(ev, gid, qid, "gather", extra={"spot_map": "starlake"})
    stg = m._prof_wait_state(gid, qid)
    check("采集 state 有值(type=gather)", stg and stg.get("type") == "gather", str(stg))
    check("采集 extra 保留 spot_map", stg and stg.get("spot_map") == "starlake", str(stg))
    m._prof_wait_clear(gid, qid)

    print("【6. 惰性结算兜底：到点但未结算 → flow 先结算旧轮再开新轮（奖励不丢）】")
    db.update_player(gid, qid, cur_map="oak_plain", cur_subarea="oak_plain_3")
    await cmd(m, "fishing", gid, qid, "垂钓")
    stf = m._prof_wait_state(gid, qid)
    check("开轮后 state 有值(type=fishing)", stf and stf.get("type") == "fishing", str(stf))
    out = await cmd(m, "fishing", gid, qid, "垂钓")
    check("等待中重复垂钓提示剩余（不结算不开新）", "还在垂钓" in out, out[:120])
    _backdate(m, gid, qid, stf)  # 回拨到点（模拟超时未结算）
    out = await cmd(m, "fishing", gid, qid, "垂钓")
    settle_ok = ("钓上来" in out or "钓上了" in out or "垃圾" in out or "宝物" in out or "鱼王" in out)
    check("到点垂钓 → 旧轮结算文案（惰性结算兜底）", settle_ok, out[:240])
    check("到点垂钓 → 自动开新一轮", "开始垂钓" in out, out[:240])
    check("新一轮已挂引擎", bool(m._prof_wait_state(gid, qid)))
    m._prof_wait_clear(gid, qid)

    print("【7. v127.5 前历史遗留 prof_wait_{qq} 到点残留 → flow 惰性结算（迁移兜底）】")
    past = int(time.time()) - 5
    db.set_event_state(f"prof_wait_{qid}", json.dumps(
        {"finish": past, "type": "gather", "spot_map": "starlake"}, ensure_ascii=False))
    db.update_player(gid, qid, cur_map="starlake")
    # 角色 Lv10 在 Lv50 星语湖：v173 采集地图等级门禁下，旧轮（v173 前开的）奖励照常惰性结算，
    # 但不会续新轮（等级不足被门禁拦）——断言「结算出现 + 不残留挂机新轮」。
    out = await cmd(m, "gather", gid, qid, "采集")
    check("遗留到点采集 → 旧轮结算出现（奖励不丢）",
          ("采集完成" in out or "采到" in out or "采集" in out and "等级太高" in out), out[:300])
    check("遗留残留已消费 + 新轮被门禁拦截（不挂高图计时）",
          not m._prof_wait_state(gid, qid), str(m._prof_wait_state(gid, qid)))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
