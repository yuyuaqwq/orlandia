# -*- coding: utf-8 -*-
"""v127.8 『找』指令删除 + 『对话』仅用于找 NPC

鱼鱼拍板：
1. 『找 X』不再是指令（find_npc 改为内部方法，仅被『对话』转发调用）
2. 对话树进行中：『对话 X』被拦截（不能回复选项、不能跳别的 NPC），
   选项回复走裸数字 1/2/3…，回复 0 结束对话
3. 无会话时：『对话 <名字/序号>』= 找 NPC 开始对话（保留原行为）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run

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
    results = await run(getattr(m, handler_name), ev)
    return results[-1] if results else ""

async def main():
    clean_db()
    m = Main(None)

    print("【1. 『找』不再对外注册】")
    from _engine_harness import harness as _harness
    COMMAND_REGEX = {k for _rx, k in _harness().declarations_for_static()}
    check("注册表无 find_npc 键", "find_npc" not in COMMAND_REGEX, str("find_npc" in COMMAND_REGEX))
    import inspect
    # 终态实现体在包内 `content.world_cmds.py`（旧宿主壳已薄壳化）
    from content.world_cmds import _find_npc_in_map as _find_npc_impl
    src = inspect.getsource(_find_npc_impl)
    check("find_npc 无 @filter.regex 装饰器", "@filter.regex" not in src and "@declared" not in src,
          "@filter.regex 残留")

    print("【2. 无会话『对话 <名字>』找 NPC 开始对话（保留）】")
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
    out = await cmd(m, "talk_choice", "g1", "w1", "对话 镇长")
    check("『对话 镇长』开始对话", "镇长" in out and "0. 结束对话" in out, out[:200])

    print("【3. 对话进行中『对话 X』被拦截（不回复/不跳NPC）】")
    out = await cmd(m, "talk_choice", "g1", "w1", "对话 铁匠")
    check("对话中『对话 铁匠』被拦截提示", "正在和" in out and "回复 0 结束" in out, out[:200])
    st = db.get_talk_state("g1", "w1")
    check("对话状态未被清除（仍在原NPC）", bool(st and st.get("npc") == "npc_mayor"), str(st))

    print("【4. 对话中裸数字选选项（保留）】")
    out = await cmd(m, "talk_choice", "g1", "w1", "2")
    check("裸数字 2 选选项推进", "镇子还算太平" in out, out[:200])

    print("【5. 对话中『对话 0』同样被拦截（v127.8b）】")
    out = await cmd(m, "talk_choice", "g1", "w1", "对话 0")
    check("对话中『对话 0』被拦截提示", "正在和" in out and "回复 0 结束" in out, out[:200])
    st = db.get_talk_state("g1", "w1")
    check("对话状态未被清除（『对话 0』不结束）", bool(st and st.get("npc") == "npc_mayor"), str(st))

    print("【6. 裸数字 0 结束对话（唯一结束通道）】")
    out = await cmd(m, "talk_choice", "g1", "w1", "0")
    check("裸数字 0 结束对话", "那就再会了" in out, out[:120])
    check("对话状态已清", db.get_talk_state("g1", "w1") is None, "")

    print("【7. 对话结束后裸数字放行（不触发对话）】")
    # 第6步已清对话状态，这里直接发裸数字 → npc_quick_dialog 放行
    ev = FakeEvent("g1", "w1", "9")
    r = "".join(str(x) for x in await run(m.npc_quick_dialog, ev))
    check("对话外裸数字放行", r == "" and not ev._stopped, (r or "空=放行")[:80])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
