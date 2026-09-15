# -*- coding: utf-8 -*-
"""v128.1 赶路指令测试：『赶路 [NPC/怪物/场景/设施]』过滤面板 + 进入赶路模式。

覆盖：
1. 『赶路』无参 → 全量可前往面板 + 进入赶路模式
2. 『赶路 NPC』→ 本地 NPC 清单 + 通道 + 赶路提示
3. 『赶路 怪物』→ 本地怪物清单（野外图）
4. 『赶路 场景』→ 场景元素区
5. 『赶路 设施』→ 设施区
6. 无效参数 → 格式提示
7. 赶路模式中序号 → 移动、0 → 结束
8. 正则：『赶路』命中 hurry_view，不被 move 抢
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
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")

    # ---- 1. 无参 ----
    ev = FakeEvent("g1", "1001", "赶路")
    r = "".join(str(x) for x in await run(m.hurry_view, ev))
    print("  [赶路]", r.replace("\n", " | ")[:140])
    check("『赶路』无参含可前往", "可前往" in r, r[:80])
    check("『赶路』无参进入赶路模式", db.get_event_state("move_mode:1001") == "1", str(db.get_event_state("move_mode:1001")))
    check("『赶路』面板带赶路提示", "赶路模式中" in r, r[-80:])

    # ---- 2. NPC 过滤 ----
    ev = FakeEvent("g1", "1001", "赶路 NPC")
    r = "".join(str(x) for x in await run(m.hurry_view, ev))
    print("  [赶路NPC]", r.replace("\n", " | ")[:150])
    check("『赶路 NPC』含 NPC 区", "这里的 NPC" in r, r[:120])
    check("『赶路 NPC』含可前往通道", "可前往" in r, "缺通道")
    check("『赶路 NPC』进模式", db.get_event_state("move_mode:1001") == "1", "未进模式")
    check("『赶路 NPC』带赶路提示", "赶路模式中" in r, r[-80:])

    # ---- 3. 怪物过滤（野外图有怪） ----
    db.update_player("g1", "1001", cur_map="oak_plain", cur_subarea="oak_plain_1")
    ev = FakeEvent("g1", "1001", "赶路 怪物")
    r = "".join(str(x) for x in await run(m.hurry_view, ev))
    print("  [赶路怪物]", r.replace("\n", " | ")[:150])
    check("『赶路 怪物』含怪物区", "此地的怪物" in r, r[:120])
    check("『赶路 怪物』含史莱姆", "史莱姆" in r, r[:120])

    # ---- 4. 城镇怪物过滤 → 没怪提示 ----
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")
    ev = FakeEvent("g1", "1001", "赶路 怪物")
    r = "".join(str(x) for x in await run(m.hurry_view, ev))
    check("『赶路 怪物』城镇安全提示", "没什么怪物" in r, r[:120])

    # ---- 5. 场景过滤 ----
    ev = FakeEvent("g1", "1001", "赶路 场景")
    r = "".join(str(x) for x in await run(m.hurry_view, ev))
    print("  [赶路场景]", r.replace("\n", " | ")[:130])
    check("『赶路 场景』有场景区或提示", ("✨" in r), r[:120])
    check("『赶路 场景』仍有通道", "可前往" in r, "缺通道")

    # ---- 6. 设施过滤 ----
    ev = FakeEvent("g1", "1001", "赶路 设施")
    r = "".join(str(x) for x in await run(m.hurry_view, ev))
    print("  [赶路设施]", r.replace("\n", " | ")[:130])
    check("『赶路 设施』有设施区或提示", ("此地设施" in r or "没有商店/设施" in r), r[:120])

    # ---- 7. 无效参数 ----
    ev = FakeEvent("g1", "1001", "赶路 宝藏")
    r = "".join(str(x) for x in await run(m.hurry_view, ev))
    check("『赶路 宝藏』无效提示", "可选参数" in r, r[:100])

    # ---- 8. 赶路模式中 序号移动 + 0 结束 ----
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")
    db.set_event_state("move_mode:1001", "1")
    ev = FakeEvent("g1", "1001", "5")
    r = "".join(str(x) for x in await run(m.npc_quick_dialog, ev))
    p = db.get_player("g1", "1001")
    check("赶路中序号移动", "东大街" in r or p["cur_subarea"] == "oak_town_street", str(p.get("cur_subarea")))
    check("移动落点带赶路提示", "回复 0 结束" in r, r[-140:])
    ev = FakeEvent("g1", "1001", "0")
    r = "".join(str(x) for x in await run(m.npc_quick_dialog, ev))
    check("赶路中 0 结束", "已结束" in r, r[:80])
    check("状态清除", db.get_event_state("move_mode:1001") != "1", str(db.get_event_state("move_mode:1001")))

    # ---- 8.5 类型过滤跟到落点：赶路 NPC 移到镇长办公处 → 只看 NPC 无场景/怪物 ----
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")
    ev = FakeEvent("g1", "1001", "赶路 NPC")   # 设 hurry_type=npc + 进赶路模式
    await run(m.hurry_view, ev)
    ev = FakeEvent("g1", "1001", "1")          # 冒险者广场 → 镇长办公处(序号1)
    r = "".join(str(x) for x in await run(m.npc_quick_dialog, ev))
    p = db.get_player("g1", "1001")
    print("  [赶路NPC落点]", r.replace("\n", " | ")[:180])
    check("赶路NPC落点本体在办公处", p["cur_subarea"] == "oak_town_2", str(p.get("cur_subarea")))
    check("赶路NPC落点含NPC", "这里的 NPC" in r, r[:150])
    check("赶路NPC落点不含场景", "✨ 场景" not in r, "场景未过滤")
    check("赶路NPC落点不含怪物", "此地的怪物" not in r, "怪物未过滤")
    check("赶路NPC落点仍含通道", "可前往" in r, "缺通道")
    check("赶路NPC落点带赶路提示", "赶路模式中" in r, r[-80:])
    # 结束清过滤类型
    ev = FakeEvent("g1", "1001", "0")
    await run(m.npc_quick_dialog, ev)
    check("0 后过滤类型已清", (db.get_event_state("hurry_type:1001") or "") == "", str(db.get_event_state("hurry_type:1001")))

    # ---- 9. 正则互斥 ----
    import re as _re
    hr = _re.compile(r"^(?:\[At:[^\]]+\]\s*)?赶路(?:[\s\S]*)$")
    mv = _re.compile(r"^(?:\[At:[^\]]+\]\s*)?(?:前往|移动)(?!开始|结束)(?:\s*|$)")
    check("『赶路 NPC』匹配 hurry_view", bool(hr.match("赶路 NPC")), "")
    check("『赶路』不匹配 move", not mv.match("赶路"), "move 误吞赶路")
    check("『前往 5』仍匹配 move", bool(mv.match("前往 5")), "")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
