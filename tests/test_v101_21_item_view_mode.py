# -*- coding: utf-8 -*-
"""v101.21 物品查看模式测试：『物品详情开始』→ 裸数字查看物品 → 『物品详情结束』退出。
（v101.25f 主名改回『物品详情』，旧名『查看物品』已废弃）

1. 『物品详情开始』开启物品查看模式（event_state 落库）
2. 开启后裸数字 → 查看物品详情（背包序号）
3. 『物品详情结束』关闭 → 裸数字回退 NPC 对话
4. 『物品详情 <名称>』直接查看（主名），旧名『查看物品』不再匹配
5. 开关 regex 只匹配开始/结束，不抢『物品详情 <名称>』
"""
import sys, os, asyncio, random, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import FakeEvent, run, clean_db, Main, db, make_player

random.seed(20260811)  # 固定撞怪随机

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
    m = Main(None)
    make_player("g1", "1001", "甲", "战士")
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")
    # 背包塞 2 件物品
    db.add_item("g1", "1001", "t1", {"name": "神愈药水", "type": "消耗品", "stackable": True}, 3)
    db.add_item("g1", "1001", "t2", {"name": "草药茶", "type": "消耗品", "stackable": True}, 1)
    check("造玩家+背包", True)

    # ---- 1. 『物品详情开始』开启 ----
    ev = FakeEvent("g1", "1001", "物品详情开始")
    r = "".join(str(x) for x in await run(m.item_view_mode_cmd, ev))
    print("  [物品详情开始]", r[:80].replace("\n", " | "))
    check("『物品详情开始』响应", "已开启" in r, r[:80])
    check("状态落库", db.get_event_state("item_view_mode:1001") == "1", str(db.get_event_state("item_view_mode:1001")))
    check("开关 stop_event", ev._stopped)

    # ---- 2. 开启后裸数字 1 → 查看物品详情 ----
    ev2 = FakeEvent("g1", "1001", "1")
    r2 = "".join(str(x) for x in await run(m.npc_quick_dialog, ev2))
    print("  [物品模式裸数字1]", r2[:100].replace("\n", " | "))
    check("裸数字触发查看物品", "神愈药水" in r2, r2[:100])
    check("查看后 stop_event", ev2._stopped)

    # ---- 3. 『物品详情结束』关闭 ----
    ev3 = FakeEvent("g1", "1001", "物品详情结束")
    r3 = "".join(str(x) for x in await run(m.item_view_mode_cmd, ev3))
    check("『物品详情结束』响应", "已关闭" in r3, r3[:80])
    check("状态清除", db.get_event_state("item_view_mode:1001") != "1", str(db.get_event_state("item_view_mode:1001")))

    # ---- 4. 关闭后裸数字 → 回退 NPC 对话（广场有 NPC） ----
    ev4 = FakeEvent("g1", "1001", "1")
    r4 = "".join(str(x) for x in await run(m.npc_quick_dialog, ev4))
    print("  [关闭后裸数字1]", r4[:100].replace("\n", " | "))
    check("关闭后裸数字不再查物品", "神愈药水" not in r4, r4[:100])

    # ---- 5. 『物品详情 <名称>』直接查看（主名），旧名『查看物品』已废弃 ----
    ev5 = FakeEvent("g1", "1001", "物品详情 草药茶")
    r5 = "".join(str(x) for x in await run(m.item_detail, ev5))
    print("  [物品详情 草药茶]", r5[:100].replace("\n", " | "))
    check("『物品详情 <名称>』查看", "草药茶" in r5, r5[:100])

    # ---- 6. regex 互斥 ----
    sw_re = re.compile(r"^(?:\[At:[^\]]+\]\s*)?物品详情(?:开始|结束)(?:\s*|$)")
    dt_re = re.compile(r"^(?:\[At:[^\]]+\]\s*)?物品详情(?:[\s\S]*)$")
    check("『物品详情开始』匹配开关", bool(sw_re.match("物品详情开始")), "开关 regex 未匹配")
    check("『物品详情 铁剑』不匹配开关", not sw_re.match("物品详情 铁剑"), "开关 regex 误吞查看指令")
    check("『物品详情 铁剑』匹配详情", bool(dt_re.match("物品详情 铁剑")), "详情 regex 未匹配")
    check("『物品详情 1』匹配详情", bool(dt_re.match("物品详情 1")), "详情 regex 未匹配")
    check("『查看物品 草药茶』旧名已废弃", not dt_re.match("查看物品 草药茶"), "旧名仍被详情 regex 接受")
    check("『背包』不被详情抢", not dt_re.match("背包"), "详情 regex 误匹配背包")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
