# -*- coding: utf-8 -*-
"""v127.5 通用倒计时事件引擎（timed_events.py）单测。

覆盖：
1. set/get 基本读写（未过期返回 {remain} 等字段）
2. 过期 → get 惰性清除返回 None（显示出口不可见）
3. refresh_timed 物理清理 + on_expire 回调触发
4. remove_timed 主动删除
5. list_timed 过滤（type / data_match 子集）
6. 多事件互不覆盖（同玩家不同 key 各自倒计时）
7. 同 key 重复 set = 顶替刷新
8. 惰性正确性：过期残留未 refresh 时，get/list 都不读旧状态
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

    # ===== 1. set/get 基本读写 =====
    print("【1. set/get 基本读写】")
    TE.register_timed("test_a", duration_sec=120)
    exp = TE.set_timed(GID, QID, "a:x", "test_a", data={"map": "m1"})
    ev = TE.get_timed(GID, QID, "a:x")
    check("挂载后 get 返回事件", bool(ev), str(ev))
    check("get 含 type/data/expire/remain", ev and ev["type"] == "test_a"
          and ev["data"] == {"map": "m1"} and ev["expire"] == exp
          and ev["remain"] > 0, str(ev))
    check("默认时长 120s", ev and ev["remain"] <= 120 and ev["remain"] > 115, str(ev))
    check("不存在的 key 返回 None", TE.get_timed(GID, QID, "nope") is None)

    # ===== 2. 过期 → get 惰性清除 =====
    print("【2. 过期 → get 惰性清除】")
    # 并发/高负载下 time.sleep 与实际流逝有抖动，时长不用极短 1s（秒级边界碰线），用 3s
    TE.set_timed(GID, QID, "a:short", "test_a", data={}, duration_sec=3)
    ev = TE.get_timed(GID, QID, "a:short")
    check("3s 事件未过期", bool(ev), str(ev))
    check("3s 事件 remain≤3", ev and 0 < ev["remain"] <= 3, str(ev))
    time.sleep(3.5)  # 缓冲 >3s，容忍调度延迟
    ev = TE.get_timed(GID, QID, "a:short")
    check("过期后 get 返回 None", ev is None, str(ev))

    # ===== 3. refresh 物理清理 + on_expire =====
    print("【3. refresh_timed 物理清理 + on_expire 回调】")
    fired = []
    TE.register_timed("test_b", duration_sec=3, on_expire=lambda g, q, d: fired.append(d))
    TE.set_timed(GID, QID, "b:y", "test_b", data={"v": 7})
    time.sleep(3.5)  # 缓冲 >3s，容忍调度延迟
    n = TE.refresh_timed(GID, QID)
    check("refresh 清理 1 条", n == 1, str(n))
    check("on_expire 回调收到 data", fired == [{"v": 7}], str(fired))
    check("过期键已删（键不存在）", TE.get_timed(GID, QID, "b:y") is None)

    # ===== 4. remove_timed =====
    print("【4. remove_timed 主动删除】")
    TE.set_timed(GID, QID, "a:x", "test_a")  # 重新挂
    ok = TE.remove_timed(GID, QID, "a:x")
    check("remove 返回 True", ok is True)
    check("remove 后 get None", TE.get_timed(GID, QID, "a:x") is None)
    check("remove 不存在返回 False", TE.remove_timed(GID, QID, "a:x") is False)

    # ===== 5. list_timed 过滤 =====
    print("【5. list_timed 过滤】")
    TE.register_timed("test_c", duration_sec=300)
    TE.set_timed(GID, QID, "c:1", "test_c", data={"map": "m1"})
    TE.set_timed(GID, QID, "c:2", "test_c", data={"map": "m2"})
    all_ = TE.list_timed(GID, QID)
    check("list 全量 2 条", len(all_) == 2, str(all_))
    by_type = TE.list_timed(GID, QID, type_key="test_c")
    check("list 按 type 过滤 2 条", len(by_type) == 2, str(by_type))
    by_map = TE.list_timed(GID, QID, type_key="test_c", data_match={"map": "m1"})
    check("list 按 data 子集过滤 1 条", len(by_map) == 1 and by_map[0]["key"] == "c:1",
          str(by_map))

    # ===== 6. 多事件互不覆盖 =====
    print("【6. 多事件互不覆盖】")
    TE.set_timed(GID, QID, "c:1", "test_c", data={"map": "m1"})
    TE.set_timed(GID, QID, "c:2", "test_c", data={"map": "m2"})
    e1 = TE.get_timed(GID, QID, "c:1")
    e2 = TE.get_timed(GID, QID, "c:2")
    check("两个事件同时存在", bool(e1 and e2), str((e1, e2)))
    check("data 各自独立", e1["data"]["map"] == "m1" and e2["data"]["map"] == "m2",
          str((e1, e2)))

    # ===== 7. 同 key 重复 set = 顶替 =====
    print("【7. 同 key 重复 set 顶替刷新】")
    TE.register_timed("test_c", duration_sec=300)
    TE.set_timed(GID, QID, "c:1", "test_c", data={"map": "m1"})
    ev_before = TE.get_timed(GID, QID, "c:1")
    remain_before = ev_before["remain"] if ev_before else -1
    time.sleep(1.1)  # 让时间流逝，验证顶替会重建而非保留旧 expire
    TE.set_timed(GID, QID, "c:1", "test_c", data={"map": "m1_new"})
    ev_after = TE.get_timed(GID, QID, "c:1")
    check("重复 set 后 remain 拉满（顶替刷新）",
          ev_after and ev_after["remain"] >= min(remain_before, 299),
          f"{remain_before} -> {ev_after and ev_after['remain']}")
    check("重复 set 新 data 覆盖", ev_after and ev_after["data"]["map"] == "m1_new",
          str(ev_after))

    # ===== 8. 惰性正确性：残留不可读 =====
    print("【8. 惰性正确性：过期残留不可读】")
    TE.set_timed(GID, QID, "c:8", "test_c", data={}, duration_sec=1)
    time.sleep(1.2)  # 过期但不 refresh
    ev = TE.get_timed(GID, QID, "c:8")
    check("过期未 refresh get 仍 None", ev is None, str(ev))
    lst = TE.list_timed(GID, QID)
    check("过期未 refresh list 不含它", all(k != "c:8" for k in
          [x["key"] for x in lst]), str(lst))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    asyncio.run(main())
