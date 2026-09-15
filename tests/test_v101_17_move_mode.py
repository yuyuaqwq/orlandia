# -*- coding: utf-8 -*-
"""v128.2 赶路模式测试：『位置』精简面板 + 唯一入口『赶路』指令。

v128 曾支持『位置』面板回复 0 进入赶路模式；v128.2（鱼鱼拍板）移除该旧捷径——
『位置 0』/『位置0』/裸 0 不再进入赶路模式，要赶路必须发『赶路』指令。

覆盖：
1. 『位置』响应精简面板（当前位置/可前往/赶路入口提示『赶路』指令）
2. 旧捷径移除：裸 0 / 『位置 0』/『位置0』 均不进入赶路模式（状态不落库）
3. 『赶路』进入赶路模式（唯一入口）
4. 赶路模式中裸数字 → 执行移动（位置变化）
5. 赶路模式中回复 0 → 关闭（状态清除）
6. 关闭后裸数字 → 放行（不再赶路）
7. 移动落点带『回复 0 结束』提示
8. 正则矩阵：『位置/位置0』命中 location_view，『位置』≠『地图』，旧『前往开始』不让 move 吞
"""
import sys, os, asyncio, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import FakeEvent, run, clean_db, Main, db

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
    from conftest import make_player
    make_player("g1", "1001", "甲", "战士")
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")
    check("造玩家", True)

    # ---- 1. 『位置』精简面板 ----
    ev = FakeEvent("g1", "1001", "位置")
    r = "".join(str(x) for x in await run(m.location_view, ev))
    print("  [位置]", r[:140].replace("\n", " | "))
    check("『位置』响应标题", "冒险者广场" in r, r[:60])
    check("『位置』有当前位置", "当前位置" in r, r[:60])
    check("『位置』有可前往", "可前往" in r, r[:60])
    check("『位置』提示用『赶路』指令", "『赶路』" in r, r[:140])
    check("『位置』不再提示回复0进赶路", "回复 0 进入赶路模式" not in r, "旧捷径提示未移除")
    check("『位置』非完整地图(无设施区)", "此地设施" not in r, "位置面板未精简")

    # ---- 2. 旧捷径移除：裸 0 / 『位置 0』/『位置0』 不再进入赶路模式 ----
    ev2 = FakeEvent("g1", "1001", "0")
    r2 = "".join(str(x) for x in await run(m.npc_quick_dialog, ev2))
    print("  [裸0]", (r2 or "（空=放行）")[:80])
    check("裸 0 不再开启赶路模式", "赶路模式已开启" not in r2 and not ev2._stopped, r2[:80])
    check("裸 0 状态未落库", db.get_event_state("move_mode:1001") != "1", str(db.get_event_state("move_mode:1001")))
    ev2b = FakeEvent("g1", "1001", "位置 0")
    r2b = "".join(str(x) for x in await run(m.location_view, ev2b))
    print("  [位置 0]", r2b[:140].replace("\n", " | "))
    check("『位置 0』不进入赶路模式", "赶路模式已开启" not in r2b, r2b[:140])
    check("『位置 0』状态未落库", db.get_event_state("move_mode:1001") != "1", str(db.get_event_state("move_mode:1001")))
    check("『位置 0』提示用『赶路』", "『赶路』" in r2b, r2b[:140])
    ev2c = FakeEvent("g1", "1001", "位置0")
    r2c = "".join(str(x) for x in await run(m.location_view, ev2c))
    print("  [位置0]", r2c[:140].replace("\n", " | "))
    check("『位置0』(无空格)不进入赶路", "赶路模式已开启" not in r2c, r2c[:140])
    check("『位置0』状态未落库", db.get_event_state("move_mode:1001") != "1", str(db.get_event_state("move_mode:1001")))

    # ---- 3. 『赶路』= 唯一入口：进入赶路模式 ----
    ev3 = FakeEvent("g1", "1001", "赶路")
    r3 = "".join(str(x) for x in await run(m.hurry_view, ev3))
    print("  [赶路]", r3[:80].replace("\n", " | "))
    check("『赶路』进入赶路模式", db.get_event_state("move_mode:1001") == "1", str(db.get_event_state("move_mode:1001")))

    # ---- 4. 赶路模式中裸数字 → 移动（广场 → 东大街 5） ----
    ev4 = FakeEvent("g1", "1001", "5")
    r4 = "".join(str(x) for x in await run(m.npc_quick_dialog, ev4))
    p4 = db.get_player("g1", "1001")
    print("  [赶路模式裸数字5]", r4[:100].replace("\n", " | "))
    check("裸数字触发移动", "东大街" in r4 or p4["cur_subarea"] == "oak_town_street", f"{p4.get('cur_subarea')}")
    check("移动后 stop_event", ev4._stopped)

    # ---- 5. 赶路模式中回复 0 → 关闭 ----
    ev5 = FakeEvent("g1", "1001", "0")
    r5 = "".join(str(x) for x in await run(m.npc_quick_dialog, ev5))
    print("  [0 关闭]", r5[:80].replace("\n", " | "))
    check("0 关闭响应", "已结束" in r5, r5[:80])
    check("状态清除", db.get_event_state("move_mode:1001") != "1", str(db.get_event_state("move_mode:1001")))

    # ---- 6. 关闭后裸数字 → 放行（不再赶路） ----
    ev6 = FakeEvent("g1", "1001", "1")
    r6 = "".join(str(x) for x in await run(m.npc_quick_dialog, ev6))
    print("  [关闭后裸数字1]", (r6 or "（空=放行）")[:100])
    check("关闭后裸数字放行", r6 == "" and not ev6._stopped, r6[:100])

    # ---- 7. 赶路模式中移动落点带『回复 0 结束』提示 ----
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")  # 回广场
    ev7 = FakeEvent("g1", "1001", "赶路")
    await run(m.hurry_view, ev7)
    ev8 = FakeEvent("g1", "1001", "5")
    r8 = "".join(str(x) for x in await run(m.npc_quick_dialog, ev8))
    p8 = db.get_player("g1", "1001")
    check("移动落点带赶路提示", "回复 0 结束" in r8, r8[-140:])
    check("第7步确实移动到东大街", p8["cur_subarea"] == "oak_town_street", str(p8.get("cur_subarea")))
    ev9 = FakeEvent("g1", "1001", "0")
    await run(m.npc_quick_dialog, ev9)

    # ---- 8. 正则矩阵：『位置/位置0』命中 location_view，『位置』≠『地图』，旧『前往开始』不让 move 吞 ----
    import re as _re
    loc_re = _re.compile(r"^(?:\[At:[^\]]+\]\s*)?位置(?:\s*0)?(?:\s*|$)")
    mv_re = _re.compile(r"^(?:\[At:[^\]]+\]\s*)?(?:地图|周围)(?:\s*|$)")
    mm_re = _re.compile(r"^(?:\[At:[^\]]+\]\s*)?(?:前往|移动)(?!开始|结束)(?:\s*|$)")
    nq_re = _re.compile(r"^(?:\[At:[^\]]+\]\s*)?[0-9０-９]\d?$")
    check("『位置』匹配 location_view", bool(loc_re.match("位置")), "")
    check("『位置 0』匹配 location_view", bool(loc_re.match("位置 0")), "")
    check("『位置0』匹配 location_view", bool(loc_re.match("位置0")), "")
    check("『位置 0』不匹配 npc_quick_dialog", not nq_re.match("位置 0"), "裸数字正则误吞")
    check("『位置』不匹配 map_view", not mv_re.match("位置"), "map_view 误含位置")
    check("『地图』匹配 map_view", bool(mv_re.match("地图")), "")
    check("『前往开始』不匹配 move", not mm_re.match("前往开始"), "move 误吞旧指令")
    check("『前往 5』匹配 move", bool(mm_re.match("前往 5")), "")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)