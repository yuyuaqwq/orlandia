# -*- coding: utf-8 -*-
"""v101.16 『找』→『对话』改版测试（v123a 更新：裸数字序号找 NPC 已移除）。

覆盖：
1. 『对话 <NPC名>』无对话中 → 找 NPC 开始对话（talk_choice 无状态 fallback）
2. 裸数字『1』→ 不再触发找 NPC 对话（v123a 移除，放行快捷指令）
3. 裸数字无 NPC 时 → 放行快捷指令（fallthrough）
4. 对话树中裸数字 → 选对话选项（talk_choice 复用，保留）
5. 『找』别名仍可用
"""
import sys, os, asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import FakeEvent, run, clean_db, Main, db

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
    from conftest import make_player
    make_player("g1", "1001", "甲", "战士")
    p = db.get_player("g1", "1001")
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")
    check("造玩家", p is not None)

    # 当前子区域（橡木镇·广场）第 1 个 NPC = 行会接待员·小艾
    # ---- 1. 『对话 <NPC名>』无状态开始对话 ----
    db.clear_talk_state("g1", "1001")
    ev = FakeEvent("g1", "1001", "对话 小艾")
    r = "".join(str(x) for x in await run(m.talk_choice, ev))
    print("  [对话 小艾]", r[:100].replace("\n", " | "))
    check("『对话 小艾』命中并渲染", "小艾" in r, r[:100])
    st = db.get_talk_state("g1", "1001")
    check("进入对话状态", bool(st and st.get("npc")), str(st))
    db.clear_talk_state("g1", "1001")

    # ---- 2. 裸数字『1』→ v123a 已移除序号找 NPC：放行（不 yield、不 stop） ----
    ev = FakeEvent("g1", "1001", "1")
    r = "".join(str(x) for x in await run(m.npc_quick_dialog, ev))
    print("  [裸数字1]", (r or "（空=放行）")[:80])
    check("裸数字不再触发 NPC 对话", r == "", r[:100])
    check("裸数字不 stop_event（放行快捷指令）", not ev._stopped)
    db.clear_talk_state("g1", "1001")

    # ---- 3. 对话树中裸数字 → 选选项（保留） ----
    # 先进入小艾对话树
    ev5 = FakeEvent("g1", "1001", "对话 小艾")
    await run(m.talk_choice, ev5)
    st5 = db.get_talk_state("g1", "1001")
    if st5:
        ev6 = FakeEvent("g1", "1001", "1")
        r6 = "".join(str(x) for x in await run(m.npc_quick_dialog, ev6))
        print("  [对话中裸数字1]", r6[:100].replace("\n", " | "))
        check("对话树中裸数字选选项", bool(r6 and len(r6) > 10), r6[:100])
        check("选项后 stop_event", ev6._stopped)
    else:
        check("小艾对话树建立", False, "无 talk_state")
    db.clear_talk_state("g1", "1001")

    # ---- 4. 无 NPC 场景（家里）→ 放行（不 yield，快捷指令兜底） ----
    db.update_player("g1", "1001", cur_map="home_1001", cur_subarea="")
    ev2 = FakeEvent("g1", "1001", "2")
    r2 = "".join(str(x) for x in await run(m.npc_quick_dialog, ev2))
    print("  [家里裸数字2]", (r2 or "（空=放行）")[:80])
    check("无 NPC 放行（不 yield）", r2 == "" and not ev2._stopped, repr(r2[:60]))

    # ---- 5. find_npc 内部查找链仍可用（v127.8『找』不再对外注册，方法保留供『对话』转发） ----
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")
    ev3 = FakeEvent("g1", "1001", "找 小艾")
    r3 = "".join(str(x) for x in await run(m.find_npc, ev3))
    check("find_npc 内部查找链可用（『对话』转发路径）", "小艾" in r3, r3[:120])
    db.clear_talk_state("g1", "1001")

    # ---- 6. 『对话』空参 → NPC 列表（带序号展示） ----
    ev4 = FakeEvent("g1", "1001", "对话")
    r4 = "".join(str(x) for x in await run(m.talk_choice, ev4))
    print("  [对话空参]", r4[:150].replace("\n", " | "))
    check("『对话』空参显示列表", "这里的 NPC" in r4 and "1." in r4, r4[:150])
    check("列表提示引导『对话』", "对话 <名字>" in r4 or "对话 <序号>" in r4, r4[:150])

    # ---- 7. 『对话 <序号>』无状态 → 找第 N 个 NPC（显式指令保留） ----
    # v101.25 测试确定性：oak_town_1 酱油 NPC（卖糖人/新手/老人/顽童）有 roam/appear
    # 随机性，深夜跑全量可能只剩小艾 → 移到 oak_town_2（镇长+文书墨点，墨点无随机配置）
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_2")
    ev7 = FakeEvent("g1", "1001", "对话 2")
    r7 = "".join(str(x) for x in await run(m.talk_choice, ev7))
    print("  [对话 2]", r7[:100].replace("\n", " | "))
    check("『对话 2』命中第 2 个 NPC", "墨点" in r7, r7[:100])

    # ---- 8. 模拟 Loopback 事件（无 stop_event 方法）→ 不抛异常 ----
    class NoStopEvent(FakeEvent):
        def stop_event(self):
            raise AttributeError("_LoopbackEvent has no stop_event")  # 模拟缺失
    ev8 = NoStopEvent("g1", "1001", "1")
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")
    db.clear_talk_state("g1", "1001")
    try:
        r8 = "".join(str(x) for x in await run(m.npc_quick_dialog, ev8))
        check("无 stop_event 事件不抛异常", r8 == "", (r8 or "空=放行")[:100])
    except Exception as e:
        check("无 stop_event 事件不抛异常", False, repr(e))

    # ---- 9. v101.18 回归：裸数字 regex 必须匹配 1-9（曾用全角连字符 [0－9] 只匹配 0/9） ----
    import re as _re2
    num_re = _re2.compile(r"^(?:\[At:[^\]]+\]\s*)?[0-9０-９]\d?$")
    check("regex 匹配 1", bool(num_re.match("1")), "数字1匹配失败")
    check("regex 匹配 2", bool(num_re.match("2")), "数字2匹配失败")
    check("regex 匹配 8", bool(num_re.match("8")), "数字8匹配失败")
    check("regex 匹配 12", bool(num_re.match("12")), "两位数字匹配失败")
    check("regex 匹配全角３", bool(num_re.match("３")), "全角数字匹配失败")
    check("regex 不匹配字母", not num_re.match("a"), "字母误匹配")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
