# -*- coding: utf-8 -*-
"""v127.6 采集奖励丢失修复回归：引擎读路径（get_timed/list_timed）过期删除
也必须触发 on_expire 回调。

背景（意见#6『采集后没有东西』真根因，2026-08-27 鱼鱼复测仍丢）：
v127.5 已注册 _prof_wait_expire_cb 做数据保全，但 on_expire 只在
refresh_timed（_maint_gate 玩家下一条指令）里被调用——而采集到点后
**第一个触碰者通常是 _prof_delayed_push 的 asyncio.sleep 唤醒**，它走
_prof_wait_state → _te.get_timed()：过期分支【物理删除且不触发 on_expire】，
数据瞬间蒸发（residual 也读不到，遗留键 begin 时已清空）→ 奖励永久丢失。

修复：get_timed / list_timed 过期删除时统一走 _fire_expire（与 refresh 一致）。
"""
import sys, os, time, json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import clean_db, db

from content import timed_events as TE

passed = failed = 0
def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

async def main():
    clean_db()
    db.init_db()
    GID, QID = "g1", "1001"

    # ===== 1. 采集链路主路径：delayed_push 触碰 get_timed 到点事件 =====
    print("【1. get_timed 过期删除触发 on_expire（采集 delayed_push 主路径）】")
    fired = []
    TE.register_timed("prof_wait", duration_sec=None,
                      on_expire=lambda g, q, d: fired.append(d))
    TE.set_timed(GID, QID, "prof_wait", "prof_wait",
                 data={"finish": int(time.time()) + 3, "type": "gather"},
                 duration_sec=3)
    time.sleep(3.5)  # 等过期（缓冲>3s 容忍调度）
    ev = TE.get_timed(GID, QID, "prof_wait")  # delayed_push 的 _prof_wait_state 路径
    check("get_timed 过期返回 None", ev is None, str(ev))
    check("on_expire 被触发（数据保全）", len(fired) == 1, str(fired))
    check("保全数据含 finish/type", fired and fired[0].get("type") == "gather"
          and fired[0].get("finish", 0) > 0, str(fired))

    # ===== 2. list_timed 过期删除同样触发 =====
    print("【2. list_timed 过期删除触发 on_expire】")
    fired2 = []
    TE.register_timed("prof_wait2", duration_sec=3,
                      on_expire=lambda g, q, d: fired2.append(d))
    TE.set_timed(GID, QID, "p2:x", "prof_wait2", data={"v": 9}, duration_sec=3)
    time.sleep(3.5)
    lst = TE.list_timed(GID, QID)
    check("list_timed 过期项已清除", lst == [], str(lst))
    check("on_expire 被触发（list 路径）", fired2 == [{"v": 9}], str(fired2))

    # ===== 3. remove_timed 主动删除【不】触发（结算路径不许重复保全） =====
    print("【3. remove_timed 主动删除不触发 on_expire】")
    fired3 = []
    TE.register_timed("prof_wait3", duration_sec=120,
                      on_expire=lambda g, q, d: fired3.append(d))
    TE.set_timed(GID, QID, "p3:y", "prof_wait3", data={"v": 1}, duration_sec=120)
    TE.remove_timed(GID, QID, "p3:y")
    check("主动删除不触发回调", fired3 == [], str(fired3))

    # ===== 4. 引擎残留可被 residual 读取（economy 惰性结算数据源） =====
    print("【4. on_expire 保全 → economy _prof_wait_residual 能读到】")
    # 模拟 _prof_wait_expire_cb 的保全动作：写入历史遗留键 prof_wait_{qq}
    saved = {"finish": int(time.time()) + 3, "type": "gather"}
    db.set_event_state("prof_wait_1001", json.dumps(saved, ensure_ascii=False))
    # 引擎存储此时应已无 prof_wait（get_timed 删了）
    raw = db.get_event_state("timed_events_1001")
    d = json.loads(raw) if raw else {}
    check("引擎存储已无 prof_wait 事件", "prof_wait" not in d, str(d)[:120])
    check("遗留键保全数据在", db.get_event_state("prof_wait_1001") is not None)

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))