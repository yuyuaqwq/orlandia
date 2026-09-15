# -*- coding: utf-8 -*-
"""O74/O80/O99/O100/O115 命令兼容修复回归测试

覆盖（对应 playtest 攒批修复项）：
  1. O74 『返回 <地名>』：v101.25i 删 move_back 后旧指令零回复（第 7 次复现）——
     注册 back_cmd 提示 handler，回复引导『前往 <地名>』/『传送』，不再只回标题
  2. O80 『打造』：v82 改名『锻造』后旧指令无别名零回复——注册『打造』为别名，
     『打造 <参数>』与『锻造 <参数>』同 handler 同解析
  3. O115 『问路 <地名>』：只回标题零内容——补 ask_way 路线指引
     （同图子区域直达提示 / 跨图 MAP_CONNECTIONS 最短路径）
  4. O99 『对话 0』状态判定不一致（影刃宗师处提示无对话但树仍在、移动被拦截；
     吟游诗人处可正常退出）——统一 _talk_active 判定：损坏残留键清除、
     全角 ０ 与 ASCII 0 同判、无状态退出指令不再误入 find_npc
  5. O100 『交付任务』不按 NPC 过滤（城主处误报"护送商货需找老赵"）——
     优先交付当前地图 NPC 的任务；无当场可交时列出全部可交付任务清单
"""
import sys, os, asyncio, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail)[:300]}")


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return "\n".join(str(x) for x in results)


async def test_o74_back_cmd(m, gid, qid):
    print("【1. O74 『返回 <地名>』→ 提示『前往』（不再零回复）】")
    # 静态注册表命中（此前 _find_handler 只命中 _maint_gate → 零回复）
    hit = m._find_handler("返回 橡木镇")
    hit_name = getattr(hit[0], "handler_name", hit[0]) if hit else None
    check("『返回 橡木镇』命中 back_cmd handler", hit_name == "back_cmd", str(hit)[:160])
    out = await cmd(m, "back_cmd", gid, qid, "返回 橡木镇")
    check("带地名回复含『前往 橡木镇』引导", "前往 橡木镇" in out, out)
    out2 = await cmd(m, "back_cmd", gid, qid, "返回")
    check("空参回复含『前往 <地名>』引导", "前往 <地名>" in out2, out2)


async def test_o80_craft_alias(m, gid, qid):
    print("【2. O80 『打造』=『锻造』别名（v82 改名后旧指令零回复）】")
    db.update_player(gid, qid, cur_map="ironharbor", cur_subarea="ironharbor_9")  # 海风锻造坊
    out_new = await cmd(m, "craft", gid, qid, "打造 1")
    out_old = await cmd(m, "craft", gid, qid, "锻造 1")
    check("『打造 1』有回复（不再零回复）", bool(out_new.strip()), out_new[:120])
    check("『打造』与『锻造』同 handler 同解析", out_new == out_old,
          f"new={out_new[:80]!r} old={out_old[:80]!r}")
    out_list = await cmd(m, "craft", gid, qid, "打造")
    check("『打造』空参展示锻造列表", "锻造" in out_list or "配方" in out_list, out_list[:120])


async def test_o99_talk_zero(m, gid, qid):
    print("【3. O99 『对话 0』统一对话结束状态判定】")
    # 3.1 影刃宗师：v151 隐藏职业已删，血脉试炼任务（s_shadow_blade_trial）移除 →
    # 对话树只剩 lore/氛围行（无选项、不建 talk_state）。验证：正常渲染 lore + 无状态
    # 裸数字 0 不崩溃 + 移动放行（与吟游诗人对照组的「有树退出」行为分开）
    db.update_player(gid, qid, cur_map="jade_port", cur_subarea="jade_port_1", race="halfling")
    out = await cmd(m, "talk_choice", gid, qid, "对话 影刃宗师·夜枭")
    check("影刃宗师对话树渲染（含 lore）", "影刃宗师" in out and ("传说" in out or "影豹" in out), out[:200])
    check("影刃宗师无转职选项（隐藏职业已删）", "转职" not in out and "1." not in out, out[:200])
    check("影刃宗师无对话状态（无树）", db.get_talk_state(gid, qid) is None, str(db.get_talk_state(gid, qid)))
    out = await cmd(m, "talk_choice", gid, qid, "0")
    check("影刃宗师裸数字 0 不崩溃", bool(out.strip()), out[:100])
    db.set_event_state(db.talk_state_key(gid, qid), None)
    out = await cmd(m, "move", gid, qid, "前往 1")
    check("裸数字 0 后移动不再被拦截", "交谈中" not in out and "🗺️" in out, out[:80])
    out = await cmd(m, "talk_choice", gid, qid, "对话 0")
    check("无状态『对话 0』提示无对话", "没有正在进行的对话" in out, out)
    out = await cmd(m, "talk_choice", gid, qid, "对话 ０")
    check("无状态『对话 ０』(全角)同样提示无对话", "没有正在进行的对话" in out and "第 0 位" not in out, out)
    # 3.3 损坏残留键：get_talk_state 解析失败 → 判定无对话 + 残留键清除（移动不再拦截）
    db.set_event_state(db.talk_state_key(gid, qid), "{'npc': 'npc_shadow_master'}")  # 单引号非法 JSON
    out = await cmd(m, "talk_choice", gid, qid, "对话 0")
    check("损坏状态『对话 0』提示无对话", "没有正在进行的对话" in out, out)
    check("损坏残留键已被清除", db.get_event_state(db.talk_state_key(gid, qid)) is None, "")
    out = await cmd(m, "move", gid, qid, "前往 1")
    check("损坏键清除后移动放行", "🗺️" in out, out[:80])
    # 3.4 对照：吟游诗人处裸数字 0 可正常退出
    db.update_player(gid, qid, cur_map="ironharbor", cur_subarea="ironharbor_1")
    out = await cmd(m, "talk_choice", gid, qid, "对话 吟游诗人·莎拉")
    check("吟游诗人对话树渲染", "结束对话" in out, out[:120])
    out = await cmd(m, "talk_choice", gid, qid, "0")  # v127.8b: 裸数字 0 结束对话
    check("吟游诗人裸数字 0 正常告别", "那就再会了" in out, out)
    check("吟游诗人裸数字 0 后状态清除", db.get_talk_state(gid, qid) is None, "")


async def test_o100_turn_in(m, gid, qid):
    print("【4. O100 『交付任务』按当前 NPC/地图过滤】")
    # 4.1 城主（ironharbor）处：护送商货(老赵/别处) 与 码头的猫(城主/本图) 均 ready
    #     → 必须当场交付『码头的猫』，不得误报"护送商货需找老赵"
    db.update_player(gid, qid, cur_map="ironharbor", cur_subarea="ironharbor_2")
    quests = db.get_quests(gid, qid) or {}
    quests["side"] = {
        "s_caravan_escort": {"status": "ready", "progress": {}},  # 故意排前（dict 顺序）
        "s5": {"status": "ready", "progress": {}},
    }
    db.save_quests(gid, qid, quests)
    out = await cmd(m, "turn_in", gid, qid, "交付任务")
    check("城主处当场交付『码头的猫』", "码头的猫" in out and "【支线完成】" in out, out[:200])
    check("不再误报护送商货需找老赵", "护送商货" not in out, out[:200])
    q2 = db.get_quests(gid, qid)
    check("码头的猫标记 done", q2["side"].get("s5", {}).get("status") == "done", str(q2["side"]))
    check("护送商货未被误交付", q2["side"].get("s_caravan_escort", {}).get("status") == "ready",
          str(q2["side"]))
    # 4.2 别处（无本图可交）→ 列出全部可交付任务清单（带 NPC/位置）
    db.update_player(gid, qid, cur_map="white_deer", cur_subarea="")
    out = await cmd(m, "turn_in", gid, qid, "交付任务")
    check("别处列出可交付任务清单", "可交付任务" in out and "护送商货" in out, out)
    check("清单含交付 NPC 位置", "老赵" in out and "银风商道" in out, out)


async def test_o115_ask_way(m, gid, qid):
    print("【5. O115 『问路 <地名>』路线指引】")
    db.update_player(gid, qid, cur_map="jade_port", cur_subarea="jade_port_1")
    hit = m._find_handler("问路 海蚀洞窟")
    hit_name = getattr(hit[0], "handler_name", hit[0]) if hit else None
    check("『问路 海蚀洞窟』命中 ask_way handler", hit_name == "ask_way", str(hit)[:160])
    out = await cmd(m, "ask_way", gid, qid, "问路 海蚀洞窟")
    check("跨图路线含路径链", "翡翠港" in out and "铁港城" in out and "海蚀洞窟" in out, out)
    # v128 顺手修复预存在 flaky：asway 尾部 _tip('move') 随机抽到「传送」条时无「前往」字样，
    # 断言改为兼容随机（只要有移动/传送引导即可）
    check("路线含引导提示（前往/传送）", ("前往" in out) or ("传送" in out), out)
    # 同图子区域
    out = await cmd(m, "ask_way", gid, qid, "问路 翡翠码头")
    check("同图子区域给『前往』直达提示", "翡翠码头" in out and "前往" in out, out)
    # 已在目标
    out = await cmd(m, "ask_way", gid, qid, "问路 翡翠港")
    check("已在目标地图提示", "已经" in out, out)
    # 未知名
    out = await cmd(m, "ask_way", gid, qid, "问路 不存在的秘境")
    check("未知地名提示没找到", "没找到" in out, out)
    # 空参
    out = await cmd(m, "ask_way", gid, qid, "问路")
    check("空参给格式提示", "格式" in out, out)


async def main():
    clean_db()
    m = Main(None)
    GID, QID = "gO", "qO"
    from conftest import make_player
    make_player(GID, QID, name="修复", cls="战士", level=25)
    db.update_player(GID, QID, gold=99999)

    await test_o74_back_cmd(m, GID, QID)
    await test_o80_craft_alias(m, GID, QID)
    await test_o99_talk_zero(m, GID, QID)
    await test_o100_turn_in(m, GID, QID)
    await test_o115_ask_way(m, GID, QID)

    print(f"\n===== O74/O80/O99/O100/O115 修复回归: {passed} passed, {failed} failed =====")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
