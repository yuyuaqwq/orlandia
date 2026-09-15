# -*- coding: utf-8 -*-
"""commands 层：v65 NPC 多轮对话系统

验证：
  1. 对话树入口：找有树 NPC 显示选项
  2. 推进：裸数字 N 选菜单选项（v101.25 #320 起『对话 N』=找 NPC）；对话 0 结束
  3. 结束：对话 0 / 再见 / 告辞
  4. 会话生命周期：无会话提示 / 移动后惰性失效 / 重复找重置
  5. 条件选项：quest_pending 按主线状态显隐
  6. 动作：set_flag / open_shop / give_item / give_gold / hint
  7. 兼容：无对话树 NPC 走旧单轮台词
"""
import sys, os, sqlite3, time, json, re
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
        print(f"  ❌ {name} {detail}")


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", level=5, gold=1000, cur_map="oak_town", cur_subarea="oak_town_2")

    print("【v65 对话树：入口】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("找镇长进入对话树", "1. 史莱姆是怎么回事？" in out and "0. 结束对话" in out, out[:200])
    check("quest_pending 显示任务选项", "我需要任务。" in out, out[:200])
    check("对话树保留功能提示", "接任务" in out or "任务" in out, out[:200])

    print("【v65 对话树：推进】")
    # v101.25 #320：『对话 N』有会话时=找 NPC（完整指令优先），菜单选项用裸数字
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("对话1推进到史莱姆分支", "黏糊糊的绿家伙" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("对话1推进到誓言", "好样的！镇子西边的草地" in out and "包在我身上！" in out, out[:200])
    # set_flag pledged 已写入（选"我这就去解决它们！"时触发）
    flags = db.get_talk_flags("g1", "w1", "npc_mayor")
    check("set_flag 写入", "pledged" in flags, str(flags))
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("包在我身上接取主线", "接取任务" in out and "冒险日志" in out, out[:300])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("出发结束对话", "那就再会了" in out, out[:200])

    print("【v101.16 对话改版：无会话时『对话 N』直接开始对话】")
    out = await cmd(m, "talk_choice", "g1", "w1", "对话 1")
    check("无会话『对话 1』开始对话", "史莱姆是怎么回事" in out or "镇长" in out, out[:200])

    print("【v65 对话树：重复找重置】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("重新找回到 start", "1. 史莱姆是怎么回事？" in out, out[:200])
    # 镇长接取 q1 后（find_npc 自动接），quest_pending 选项隐藏
    out = await cmd(m, "talk_choice", "g1", "w1", "2")
    check("对话2到镇子近况", "镇子还算太平" in out, out[:200])

    print("【v65 对话树：分支与结束】")
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("town 分支可回史莱姆", "黏糊糊的绿家伙" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "0")
    check("对话0结束", "那就再会了" in out, out[:120])
    out = await cmd(m, "talk_choice", "g1", "w1", "再见")
    check("结束词再见提示无会话", "没有正在进行的对话" in out, out[:120])

    print("【v65 对话树：结束词/无参渲染】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("重新进入对话", "0. 结束对话" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "对话")
    check("无参对话重渲染当前节点", "0. 结束对话" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "告辞")
    check("告辞结束", "那就再会了" in out, out[:120])

    print("【v65 对话树：移动后惰性失效】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("再次进入对话", "0. 结束对话" in out, out[:200])
    db.update_player("g1", "w1", cur_map="oak_plain")  # 模拟移动走
    out = await cmd(m, "talk_choice", "g1", "w1", "对话 1")
    check("离开地图会话失效", "不在这里了" in out, out[:200])
    st = db.get_talk_state("g1", "w1")
    check("会话已清", st is None, str(st))

    print("【v65 对话树：条件显隐】")
    # 主线全部完成 → quest_pending 不再显示
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
    db.save_quests("g1", "w1", {"main_quest": None, "main_status": "pending", "main_progress": {},
                                "daily": {}, "completed_main": ["q1"], "side": {}})
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("主线完成后任务选项隐藏", "我需要任务" not in out and "1. 史莱姆是怎么回事？" in out, out[:200])

    print("【v65 对话树：动作执行】")
    # 铁匠：open_shop 动作
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_3")
    out = await cmd(m, "find_npc", "g1", "w1", "找 铁匠")
    check("铁匠对话树", "1. 看看你的货。" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("open_shop 提示", "输入『商店』可以买东西" in out and "慢慢挑" in out, out[:200])
    # give_item / give_gold 动作（直接测 apply 方法）
    notices = m._apply_talk_action("g1", "w1", db.get_player("g1", "w1"), "npc_mayor",
                                   {"give_gold": 50, "give_exp": 30, "give_item": {"key": "狼皮", "count": 2}})
    p = db.get_player("g1", "w1")
    check("give_gold 生效", p["gold"] == 1050, str(p["gold"]))
    check("give_exp 生效", p["exp"] == 30, str(p["exp"]))
    check("give_item 通知", any("狼皮 ×2" in n for n in notices), str(notices))
    check("give_item 入包", db.count_item("g1", "w1", "狼皮") == 2, str(db.count_item("g1", "w1", "狼皮")))
    # hint 动作
    notices = m._apply_talk_action("g1", "w1", db.get_player("g1", "w1"), "npc_mayor", {"hint": "输入『住宿』恢复满血"})
    check("hint 通知", any("住宿" in n for n in notices), str(notices))

    print("【v65 兼容：无对话树 NPC 走旧单轮】")
    db.update_player("g1", "w1", cur_map="dawn_city")
    out = await cmd(m, "find_npc", "g1", "w1", "找 旅店")
    check("旧单轮台词", "远道而来的冒险者" in out or "旅店" in out, out[:200])

    print("【v95.9 对话式任务接取/交付（取代『交任务』指令）】")
    # 场景A：主线 pending → 对话接取（两段式：我需要任务 → 交给我了）
    q = db.get_quests("g1", "w1")
    q["main_quest"] = "q1_4"; q["main_status"] = "pending"; q["main_progress"] = {}; q["side"] = {}
    db.save_quests("g1", "w1", q)
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("A:选项📜我需要任务", "我需要任务" in out, out[:250])
    out = await cmd(m, "talk_choice", "g1", "w1", "3")
    check("A:进入任务对话", "交给我了" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("A:接取成功", "接取任务" in out, out[:150])
    check("A:主线=active", db.get_quests("g1", "w1").get("main_status") == "active",
          str(db.get_quests("g1", "w1").get("main_status")))
    # 场景B：主线 ready → 对话交付
    q = db.get_quests("g1", "w1")
    q["main_status"] = "ready"; q["main_progress"] = {"kill": 3}
    db.save_quests("g1", "w1", q)
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("B:选项✅任务完成了", "任务完成了" in out, out[:250])
    mm = re.search(r"(\d+)\. ✅ 任务完成了", out)  # v101.24：动态定位（选项序号会随 side_available 等条件变化）
    opt = mm.group(1) if mm else "4"
    out = await cmd(m, "talk_choice", "g1", "w1", f"{opt}")
    check("B:进入交付对话", "报酬" in out, out[:150])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("B:交付成功", "任务完成" in out, out[:150])
    check("B:主线推进 q1_5", db.get_quests("g1", "w1").get("main_quest") == "q1_5",
          str(db.get_quests("g1", "w1").get("main_quest")))
    # 场景C：支线收集型 → 对话交付（玛莎 s1 史莱姆果冻）
    q = db.get_quests("g1", "w1")
    q["side"] = {"s1": {"status": "active", "progress": {}}}
    db.save_quests("g1", "w1", q)
    db.add_item("g1", "w1", "史莱姆黏液", {}, 5)
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_4")
    out = await cmd(m, "find_npc", "g1", "w1", "找 玛莎")
    mm = re.search(r"(\d+)\. ✅ 有东西要交给你", out)
    check("C:选项✅有东西要交给你", mm is not None, out[:250])
    opt = mm.group(1) if mm else "5"
    out = await cmd(m, "talk_choice", "g1", "w1", f"{opt}")
    check("C:支线交付成功", "任务完成" in out or "史莱姆" in out, out[:200])
    # v95.12：交付后条目标记 done 保留（防自动重接），不再删除
    check("C:支线标记done", (db.get_quests("g1", "w1").get("side") or {}).get("s1", {}).get("status") == "done",
          str(db.get_quests("g1", "w1").get("side")))
    # 场景D：找有对话树的任务 NPC 不再自动接支线（提示引导对话）
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    # v95.12：side 里只剩 done 标记（无 active）即视为无待办支线
    _side = db.get_quests("g1", "w1").get("side") or {}
    check("D:支线提示不自动接", "可接取" in out and not any(sq.get("status") != "done" for sq in _side.values()),
          f"{out[:150]} | side={_side}")

    print("【v101.19 对话树任务入口补全：dogs分支/行会接待员/矮人长老】")
    # guild_clerks：q1_2 行会入门 pending → chat 分支对话接取（此前 chat 无任务选项=死路）
    db.save_quests("g1", "w1", {"main_quest": "q1_2", "main_status": "pending", "main_progress": {},
                                "daily": {}, "completed_main": ["q1_1"], "side": {}})
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_1")
    out = await cmd(m, "find_npc", "g1", "w1", "找 行会")
    check("行会:找NPC进对话树", "新委托" in out or "就职" in out, out[:250])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("行会:进入chat分支", "新委托" in out, out[:250])
    mm = re.search(r"(\d+)\. 📜 行会有任务委托吗", out)
    check("行会:任务选项可见", mm is not None, out[:250])
    opt = mm.group(1) if mm else "1"
    out = await cmd(m, "talk_choice", "g1", "w1", f"{opt}")
    check("行会:进入任务对话", "交给我了" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("行会:接取q1_2", "接取任务" in out and "行会入门" in out, out[:250])
    check("行会:主线已接取", db.get_quests("g1", "w1").get("main_status") in ("active", "ready"),
          str(db.get_quests("g1", "w1").get("main_status")))

    # dwarf_elder：q8_3 铁砧要塞 pending → welcome 对话接取（此前只有闲聊=死路）
    db.save_quests("g1", "w1", {"main_quest": "q8_3", "main_status": "pending", "main_progress": {},
                                "daily": {}, "completed_main": ["q7_6"], "side": {}})
    # v169.1：q8_3 有 min_level=65，测试玩家提到 65 过门槛（本段只测接取流程不测等级门）
    db.update_player("g1", "w1", level=65, cur_map="anvil_fort", cur_subarea="anvil_fort_2")
    out = await cmd(m, "find_npc", "g1", "w1", "找 托尔丁")
    check("矮人:找NPC进对话树", "地精" in out, out[:250])
    mm = re.search(r"(\d+)\. 📜 我能帮上什么忙", out)
    check("矮人:任务选项可见", mm is not None, out[:250])
    opt = mm.group(1) if mm else "1"
    out = await cmd(m, "talk_choice", "g1", "w1", f"{opt}")
    check("矮人:进入任务对话", "交给我了" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "w1", "1")
    check("矮人:接取q8_3", "接取任务" in out and "铁砧要塞" in out, out[:250])

    print("【v59.#51 找NPC方向提示：同名NPC只列当前地图位置】")
    # 玩家在铁港城找『城主』：3 城都有城主（+珍珠城城主侍女也含"城主"）
    # v113.5 O90：同图但目标在别的子区域 → 统一"（你现在不在这里）"样式，全列表保留
    db.update_player("g1", "w1", cur_map="ironharbor", cur_subarea="ironharbor_1")
    out = await cmd(m, "find_npc", "g1", "w1", "找 城主")
    check("#51:城主只列当前地图", "铁港城·城主府" in out and "你现在不在这里" in out, out[:250])
    # 玩家在橡木镇（非镇长所在子区域）找『镇长』→ 同样按 O90 样式
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_4")
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("#51:镇长只列当前地图", "橡木镇·镇长办公处" in out and "你现在不在这里" in out, out[:250])
    # 玩家所在地图无同名 NPC → 保留"你现在不在这里"+全列表（跨城镇导航）
    db.update_player("g1", "w1", cur_map="ironharbor", cur_subarea="ironharbor_1")
    out = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("#51:跨地图保留全列表", "你现在不在这里" in out and "橡木镇·镇长办公处" in out and "铁盾镇·镇公所" in out, out[:250])

    print("【v65 引擎：数据完整性】")
    # 所有对话树节点引用合法：next 要么是 __end__ 要么是存在的节点
    bad = []
    for npc_id, dlg in C.DIALOGUES.items():
        nodes = dlg.get("nodes", {})
        if dlg.get("start") not in nodes:
            bad.append(f"{npc_id}:start")
        for nid, nd in nodes.items():
            for opt in nd.get("options", []):
                nxt = opt.get("next", "__end__")
                if nxt != "__end__" and nxt not in nodes:
                    bad.append(f"{npc_id}:{nid}->{nxt}")
    check("对话树引用全部合法", len(bad) == 0, str(bad[:5]))
    # 有对话树的 NPC 都在 NPCS 或野外 NPC(ALL_WILD) 里（v95.8：隐士·莱德等野外 NPC 也有对话树）
    orphan = [nid for nid in C.DIALOGUES if nid not in C.NPCS and nid not in C.ALL_WILD]
    check("对话树 NPC 全部存在", len(orphan) == 0, str(orphan))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
