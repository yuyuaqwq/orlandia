# -*- coding: utf-8 -*-
"""v127.4 未注册用户静默测试：未注册玩家发序号/翻页符号不再弹"未注册"提示。

背景：鱼鱼反馈"有人直接发 1,2 这些序号，如果这个人没注册会提示未注册"；
群里蚕蛹吐槽「这bot就不能对未注册用户只处理注册指令吗」。
根因：裸数字/翻页快捷键链路挂了 @require_player()，未注册用户发『1』『2』『+』
被 npc_quick_dialog / page_flip 拦截弹 REGISTER_HINT。

v127.4 修复：npc_quick_dialog / page_flip 去掉 @require_player()，
函数内对未注册玩家静默 return（不 yield、不 stop）——因为对话树/移动模式/
快捷绑定都是已注册玩家专属的交互状态，未注册用户无任何状态可消费，
不应被"🆕 你还没有角色"打扰（claude 群蚕蛹 905584670 反馈同类问题）。

覆盖：
1. 未注册发裸数字『1』→ npc_quick_dialog 静默（无回复、不 stop）
2. 未注册发裸数字『2』→ 同上（隔壁玩家/路人数字消息）
3. 未注册发翻页符号『+』→ page_flip 静默（无回复、不转发）
4. 对照：已注册玩家裸数字仍正常消费（对话树选项 / 移动模式 / 翻页转发）
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

    # ============ 1. 未注册发裸数字『1』→ 静默 ============
    print("【1. 未注册发裸数字 → npc_quick_dialog 静默（v127.4）】")
    ev = FakeEvent("g1", "9999", "1")  # 9999 未注册
    r = "".join(str(x) for x in await run(m.npc_quick_dialog, ev))
    check("未注册裸数字『1』无回复", r == "", repr(r[:80]))
    check("未注册裸数字『1』不 stop（放行后续）", not ev._stopped)

    # ============ 2. 未注册发裸数字『2』→ 静默 ============
    ev = FakeEvent("g1", "9999", "2")
    r = "".join(str(x) for x in await run(m.npc_quick_dialog, ev))
    check("未注册裸数字『2』无回复", r == "", repr(r[:80]))
    check("未注册裸数字『2』不 stop", not ev._stopped)

    # ============ 3. 未注册发翻页符号『+』→ page_flip 静默 ============
    print("【3. 未注册发翻页符号 → page_flip 静默（v127.4）】")
    captured = []
    orig = m._run_shortcut
    async def fake_run_shortcut(event, cmd_text):
        captured.append(cmd_text)
        yield None
    m._run_shortcut = fake_run_shortcut
    ev = FakeEvent("g1", "9999", "+")
    r = "".join(str(x) for x in await run(m.page_flip, ev))
    check("未注册『+』无回复", r == "", repr(r[:80]))
    check("未注册『+』不转发", captured == [], str(captured))
    m._run_shortcut = orig

    # ============ 4. 对照：已注册玩家裸数字仍正常消费 ============
    print("【4. 对照：已注册玩家裸数字/翻页不受影响】")
    make_player("g1", "1001", "甲", "战士")
    # 4a. 移动模式：已注册发『5』→ 赶路
    db.set_event_state("move_mode:1001", "1")
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_1")
    ev = FakeEvent("g1", "1001", "5")
    r = "".join(str(x) for x in await run(m.npc_quick_dialog, ev))
    check("已注册移动模式裸数字仍赶路", bool(r), repr(r[:80]))
    check("已注册移动模式 stop", ev._stopped)
    db.set_event_state("move_mode:1001", "")
    # 4b. 翻页：已注册『+』仍转发
    db.set_event_state(f"last_list_1001", '{"cmd": "背包", "page": 1, "pages": 2}')
    captured2 = []
    async def fake_run_shortcut2(event, cmd_text):
        captured2.append(cmd_text)
        yield None
    m._run_shortcut = fake_run_shortcut2
    ev = FakeEvent("g1", "1001", "+")
    r = "".join(str(x) for x in await run(m.page_flip, ev) if x is not None)
    check("已注册『+』无回复（命中转发）", r == "", repr(r[:80]))
    check("已注册『+』正常转发背包翻页", captured2 and "背包 2" in captured2[0], str(captured2))
    m._run_shortcut = orig
    db.set_event_state(f"last_list_1001", "")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    asyncio.run(main())
