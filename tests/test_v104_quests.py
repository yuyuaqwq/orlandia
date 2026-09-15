# -*- coding: utf-8 -*-
"""v104 任务系统 9 项修复回归（test_v104_quests.py）

覆盖：
 1. q5_5 collect 交付：接取→背包凑齐圣光百合→对话树交付/『交付任务』→完成推进（e78ac70 P0；v1.2 国王有对话树后走对话交付）
 2. q3_4 链修复：q3_4.next=q3_5→q3_6→q4_1（数据断言 + 模拟链推进）（e78ac70 P1）
 3. 主线 explore 未接取不自动完成：pending 到达目标图→不完成不发奖（e78ac70）
 4. 支线接取 min_level：Lv.1 接取 Lv.40 雾中灯塔→被拒（b477bd8 P1-1）
 5. 复合目标门槛一致：魔剑士试炼 2/3 残页→quest_view 可交 + turn_in 判定一致（b477bd8 P1-3）
 6. 巴德对话不崩：对话 老水手·巴德→正常返回不 NameError（b477bd8 P0-1）
 7. 告示板地图过滤：非本图委托不显示（ef95d7f M20）
 8. 日常委托新 2 项：DAILY_QUESTS 含 行会委托/采集任务 + 进度消费端（ef95d7f M20）
 9. 击杀 key 统一：杀精英变体→面板计数用 obj kill key 展示（ef95d7f M19 P2）

运行：python tests/test_v104_quests.py（exit=0 全绿）
"""
import sys, os, asyncio, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run, make_player
from content.quests_flow import quest_kill_progress  # v181 L3-P2：_update_quests 壳收编订阅方，击杀推进直调 services
from content import wild as _wild  # C.ALL_WILD → 包内派生读口（content/wild.py PEP 562）
from content import world_cmds as _WC  # 旧壳 `WorldCmds._bump_daily_progress` 的包内真源（同名函数在
                                       # `content.profession_quests` 另有一份异签名私有体，走 Main 会歧义）

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
    return "".join(str(x) for x in results)

def qdata(mid, status="active", progress=None, daily=None, side=None, completed=None):
    return {
        "main_quest": mid, "main_status": status,
        "main_progress": progress or {},
        "daily": daily or {}, "completed_main": completed or [], "side": side or {},
    }

def get_q(gid, qid):
    return db.get_quests(gid, qid)

async def main():
    clean_db()
    m = Main(None)

    # ============ 1. q5_5 collect 交付（接了能交） ============
    print("\n[1] q5_5 collect 交付")
    make_player("g1", "p1", "格温", "战士")
    db.update_player("g1", "p1", cur_map="dawn_city", cur_subarea="dawn_city_2")
    q5 = next(q for q in C.MAIN_QUESTS if q["id"] == "q5_5")
    check("q5_5 数据: collect 圣光百合×1", q5["objective"] == {"collect": "圣光百合", "count": 1}, str(q5["objective"]))
    gold0 = db.get_player("g1", "p1")["gold"]
    db.save_quests("g1", "p1", qdata("q5_5", "active"))
    # 背包没有花时对话 → 进入对话树，不自动交付（国王有树后走对话交付，world.py _deliver_hint）
    out = await cmd(m, "talk_choice", "g1", "p1", "对话 国王")
    check("无花对话不交付", "任务完成" not in out, out[:120])
    check("状态仍 active", get_q("g1", "p1")["main_status"] == "active", get_q("g1", "p1")["main_status"])
    # 凑齐圣光百合 → 对话树交付：首屏不显示交付（active 未 ready）→ 选『我手头的王命』
    # 触发 _talk_quest_progress 收集检测（材料已齐→ready）→ 交付选项出现 → 收下赏赐
    db.add_item("g1", "p1", "mat_sheng_guang_bai_he", {"name": "圣光百合", "type": "材料", "stackable": True, "price": 30}, 1)
    out = await cmd(m, "talk_choice", "g1", "p1", "对话 国王")
    check("凑齐后首屏不交付", "王命完成了" not in out and "任务完成" not in out, out[:120])
    out = await cmd(m, "talk_choice", "g1", "p1", "1")
    check("选王命触发收集检测", "材料已齐" in out and "王命完成了" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "p1", "1")
    check("交付节点台词", "深渊的腥味" in out, out[:200])
    out = await cmd(m, "talk_choice", "g1", "p1", "1")
    qq = get_q("g1", "p1")
    check("凑齐后对话完成推进", "任务完成" in out, out[:160])
    check("推进到 q5_6", qq["main_quest"] == "q5_6", str(qq["main_quest"]))
    check("q5_5 入完成列表", "q5_5" in qq["completed_main"], str(qq["completed_main"]))
    check("圣光百合被扣除", db.count_item("g1", "p1", "圣光百合") == 0, str(db.count_item("g1", "p1", "圣光百合")))
    check("奖励金币入账", db.get_player("g1", "p1")["gold"] == gold0 + 1110, str(db.get_player("g1", "p1")["gold"] - gold0))  # v169.2 金币校直 q5_5 600→1110
    # 『交付任务』指令路径（ready 态直接交）
    make_player("g1", "p2", "罗兰", "战士")
    db.update_player("g1", "p2", cur_map="dawn_city", cur_subarea="dawn_city_3")
    db.add_item("g1", "p2", "圣光百合", {"name": "圣光百合", "type": "材料", "stackable": True, "price": 30}, 1)
    db.save_quests("g1", "p2", qdata("q5_5", "ready", {"圣光百合": 1}))
    out = await cmd(m, "turn_in", "g1", "p2", "交付任务")
    check("『交付任务』路径完成", "任务完成" in out and "罗兰的试炼" in out, out[:160])
    check("turn_in 后状态 pending 新主线", get_q("g1", "p2")["main_status"] == "pending" and get_q("g1", "p2")["main_quest"] == "q5_6",
          str(get_q("g1", "p2")["main_quest"]))

    # ============ 2. q3_4 链修复 ============
    print("\n[2] q3_4 链: q3_4→q3_5→q3_6→q4_1")
    qm = {q["id"]: q for q in C.MAIN_QUESTS}
    check("q3_4.next == q3_5", qm["q3_4"]["next"] == "q3_5", qm["q3_4"]["next"])
    check("q3_5.next == q3_6", qm["q3_5"]["next"] == "q3_6", qm["q3_5"]["next"])
    check("q3_6.next == q4_1", qm["q3_6"]["next"] == "q4_1", qm["q3_6"]["next"])
    # 模拟链推进：q3_4 交付 → q3_5 接+交 → q3_6 接+交 → q4_1
    make_player("g2", "p3", "艾拉", "法师")
    db.update_player("g2", "p3", cur_map="ironharbor", cur_subarea="ironharbor_1")
    db.save_quests("g2", "p3", qdata("q3_4", "ready", {"white_abbey": 1}))
    npc_gm = C.NPCS["npc_guildmaster"]
    m._take_main_quest("g2", "p3", "npc_guildmaster", npc_gm)
    check("q3_4 交付→q3_5", get_q("g2", "p3")["main_quest"] == "q3_5", get_q("g2", "p3")["main_quest"])
    # q3_5 talk 型：接取即 ready，再对话交付
    m._take_main_quest("g2", "p3", "npc_guildmaster", npc_gm)
    m._take_main_quest("g2", "p3", "npc_guildmaster", npc_gm)
    check("q3_5 交付→q3_6", get_q("g2", "p3")["main_quest"] == "q3_6", get_q("g2", "p3")["main_quest"])
    m._take_main_quest("g2", "p3", "npc_auctioneer", C.NPCS["npc_auctioneer"])
    m._take_main_quest("g2", "p3", "npc_auctioneer", C.NPCS["npc_auctioneer"])
    check("q3_6 交付→q4_1", get_q("g2", "p3")["main_quest"] == "q4_1", get_q("g2", "p3")["main_quest"])

    # ============ 3. 主线 explore 未接取不自动完成 ============
    print("\n[3] 主线 explore 守卫（pending 不自动完成）")
    make_player("g3", "p4", "影刃", "游侠")
    db.update_player("g3", "p4", cur_map="white_deer_forest")
    gold0 = db.get_player("g3", "p4")["gold"]
    db.save_quests("g3", "p4", qdata("q1_5", "pending"))
    lines = m._update_explore_quests("g3", "p4", "white_deer_forest")
    qq = get_q("g3", "p4")
    check("pending 到达目标图不完成", qq["main_status"] == "pending" and qq["main_quest"] == "q1_5",
          f"{qq['main_status']}/{qq['main_quest']}")
    check("pending 不发奖", db.get_player("g3", "p4")["gold"] == gold0 and lines == [],
          f"lines={lines} gold+{db.get_player('g3','p4')['gold']-gold0}")
    # active 到达 → 完成推进
    db.save_quests("g3", "p4", qdata("q1_5", "active"))
    lines = m._update_explore_quests("g3", "p4", "white_deer_forest")
    qq = get_q("g3", "p4")
    check("active 到达目标图完成推进", qq["main_quest"] == "q1_6" and "q1_5" in qq["completed_main"],
          str(qq["main_quest"]))
    check("active 发奖", db.get_player("g3", "p4")["gold"] == gold0 + 410 and any("达成" in l for l in lines),
          f"gold+{db.get_player('g3','p4')['gold']-gold0} lines={lines}")  # v169.2 金币校直 q1_5 40→410

    # ============ 4. 支线接取 min_level ============
    print("\n[4] 支线接取 min_level（Lv.1 拒接 Lv.40）")
    sl = next(q for q in C.SIDE_QUESTS if q["id"] == "s_lighthouse")
    check("雾中灯塔数据 min_level=40", sl.get("min_level") == 40, str(sl.get("min_level")))
    make_player("g4", "p5", "小豆", "战士", level=1)
    out = await cmd(m, "quest_accept", "g4", "p5", "接取 雾中灯塔")
    check("Lv.1 接取被拒", "Lv.40" in out, out[:120])
    check("未入 side", "s_lighthouse" not in (get_q("g4", "p5").get("side") or {}), str(get_q("g4", "p5").get("side")))

    # ============ 5. 复合目标门槛一致（v112：原魔剑士试炼并入龙裔线，改用 s7 修道院的玫瑰） ============
    print("\n[5] 复合目标 collect_count 门槛一致")
    st = next(q for q in C.SIDE_QUESTS if q["id"] == "s7")
    check("试炼数据 kill5+collect3", st["objective"].get("count") == 5 and st["objective"].get("collect_count") == 3,
          str(st["objective"]))
    make_player("g5", "p6", "剑心", "战士", level=60)
    db.update_player("g5", "p6", cur_map="white_abbey")
    db.add_item("g5", "p6", "染黑玫瑰", {"name": "染黑玫瑰", "type": "材料", "stackable": True, "price": 100}, 3)
    db.save_quests("g5", "p6", qdata(None, "pending", side={"s7": {"status": "active", "progress": {}}}))
    out = await cmd(m, "quest_view", "g5", "p6", "任务")
    check("quest_view 3/3 玫瑰显示可交", "可交" in out, out[out.find("支线"):out.find("支线")+300] if "支线" in out else out[:200])
    out = await cmd(m, "turn_in", "g5", "p6", "交付任务")
    check("turn_in 材料门槛放行(卡击杀)", "腐蚀修女" in out and "还差" not in out, out[:160])
    # 击杀齐 → 可完整交付
    db.save_quests("g5", "p6", qdata(None, "pending",
                                     side={"s7": {"status": "active", "progress": {"腐蚀修女": 5}}}))
    out = await cmd(m, "turn_in", "g5", "p6", "交付任务")
    qq = get_q("g5", "p6")
    check("击杀+玫瑰齐 → 完整交付", "支线完成" in out, out[:160])
    check("交付后 done", qq["side"]["s7"]["status"] == "done", str(qq["side"]["s7"]))
    check("玫瑰扣除", db.count_item("g5", "p6", "染黑玫瑰") == 0, str(db.count_item("g5", "p6", "染黑玫瑰")))

    # ============ 6. 巴德对话不崩（NameError 回归） ============
    print("\n[6] 对话 老水手·巴德 不崩")
    make_player("g6", "p7", "浪花", "战士", level=1)
    db.update_player("g6", "p7", cur_map="mist_tide_passage", cur_subarea="mist_tide_passage_1")
    try:
        out = await cmd(m, "talk_choice", "g6", "p7", "对话 老水手·巴德")
        ok = True
    except Exception as e:
        out, ok = str(e), False
    check("对话正常返回不 NameError", ok and "Lv.40" in out, out[:200])
    check("Lv.1 未自动接走雾中灯塔", "s_lighthouse" not in (get_q("g6", "p7").get("side") or {}), str(get_q("g6", "p7").get("side")))

    # ============ 7. 告示板地图过滤 ============
    print("\n[7] 告示板地图过滤")
    make_player("g7", "p8", "看板娘", "战士")
    db.update_player("g7", "p8", cur_map="oak_town", cur_subarea="oak_town_1")
    out = await cmd(m, "interact_prop", "g7", "p8", "交互 告示板")
    check("本图(橡木镇)显示寻猫·虎斑", "寻猫·虎斑" in out, out[:200])
    # 非本图委托不显示（复刻代码过滤逻辑：board 委托取 map 字段，qmap != cur 跳过）
    board_qs = [sq for sq in C.SIDE_QUESTS if sq.get("board")]
    def board_filter(cur):
        shown = []
        for sq in board_qs:
            qmap = sq.get("map")
            if not qmap:
                _g = C.NPCS.get(sq.get("giver")) or _wild.ALL_WILD.get(sq.get("giver")) or {}
                qmap = _g.get("map")
            if qmap and qmap != cur:
                continue
            shown.append(sq["id"])
        return shown
    check("过滤逻辑: 橡木镇显示 s_board_cat", "s_board_cat" in board_filter("oak_town"), str(board_filter("oak_town")))
    check("过滤逻辑: 其他图不显示", "s_board_cat" not in board_filter("white_deer"), str(board_filter("white_deer")))
    # 非告示板地图接取被拦 / 告示板前可接
    db.update_player("g7", "p8", cur_map="white_deer", cur_subarea="white_deer_forest_1")
    out = await cmd(m, "quest_accept", "g7", "p8", "接取 寻猫·虎斑")
    check("非板前接取被拦", "告示板" in out, out[:120])
    db.update_player("g7", "p8", cur_map="oak_town", cur_subarea="oak_town_1")
    out = await cmd(m, "quest_accept", "g7", "p8", "接取 寻猫·虎斑")
    check("板前接取成功", "寻猫·虎斑" in out and "s_board_cat" in (get_q("g7", "p8").get("side") or {}), out[:120])

    # ============ 8. 日常委托新 2 项 ============
    print("\n[8] 日常委托: 行会委托 / 采集任务")
    dnames = {d["name"]: d for d in C.DAILY_QUESTS}
    check("DAILY_QUESTS 含 行会委托", "行会委托" in dnames, str(list(dnames)))
    check("行会委托 objective complete_side=2", dnames.get("行会委托", {}).get("objective") == {"complete_side": 2},
          str(dnames.get("行会委托", {}).get("objective")))
    check("DAILY_QUESTS 含 采集任务", "采集任务" in dnames, str(list(dnames)))
    check("采集任务 objective collect_any=5", dnames.get("采集任务", {}).get("objective") == {"collect_any": 5},
          str(dnames.get("采集任务", {}).get("objective")))
    # 消费端：完成支线 → 行会委托 +1
    make_player("g8", "p9", "委托仔", "战士")
    db.update_player("g8", "p9", cur_map="oak_town", cur_subarea="oak_town_1")
    today = datetime.date.today().isoformat()
    daily = {"_date": today, "d0": {"name": "行会委托", "desc": "完成 2 条支线任务",
                                    "objective": {"complete_side": 2}, "reward_exp": 750, "reward_gold": 300, "progress": 1}}
    db.save_quests("g8", "p9", qdata(None, "pending", daily=daily,
                                     side={"s1": {"status": "active", "progress": {}}}))
    db.add_item("g8", "p9", "史莱姆黏液", {"name": "史莱姆黏液", "type": "物品", "stackable": True, "price": 5}, 5)
    gold0 = db.get_player("g8", "p9")["gold"]
    out = m._complete_side_quest("g8", "p9", "s1")
    check("完成支线触发行会委托达标", any("行会委托" in l and "完成" in l for l in out), str(out))
    # v97.5 quest_deliver 彩蛋（30% 随机 10-25 金币）可能让金币多出——断言用 >=（彩蛋只加不减）
    # 支线 ×5 通胀校准：s1 史莱姆果冻 60（原 300）+ 行会委托每日 300 = 360
    check("行会委托奖励入账+移除", db.get_player("g8", "p9")["gold"] >= gold0 + 360 and "d0" not in get_q("g8", "p9")["daily"],
          f"gold+{db.get_player('g8','p9')['gold']-gold0} daily={get_q('g8','p9')['daily']}")
    # 消费端：采集材料 → 采集任务 +1
    daily2 = {"_date": today, "d0": {"name": "采集任务", "desc": "采集 5 份材料",
                                     "objective": {"collect_any": 5}, "reward_exp": 400, "reward_gold": 150, "progress": 4}}
    db.save_quests("g8", "p9", qdata(None, "pending", daily=daily2))
    gold0 = db.get_player("g8", "p9")["gold"]
    out = _WC._bump_daily_progress(m, "g8", "p9", "collect_any")
    check("采集 +1 达标发奖移除", db.get_player("g8", "p9")["gold"] == gold0 + 150 and "d0" not in get_q("g8", "p9")["daily"],
          f"gold+{db.get_player('g8','p9')['gold']-gold0} daily={get_q('g8','p9')['daily']}")

    # ============ 9. 击杀 key 统一（精英变体→obj kill key） ============
    print("\n[9] 击杀 key 统一")
    make_player("g9", "p10", "猎手", "战士")
    db.save_quests("g9", "p10", qdata("q1_3", "active"))
    # v104 M20 P2：击杀匹配改前缀精确（== 或 「目标·」开头）——「·」后缀精英变体计入，
    # 前缀式命名（精英野猪/巨型野猪/霜巨魔王等）不再误伤
    lines = quest_kill_progress("g9", "p10", {"name": "野猪·精英"})
    qq = get_q("g9", "p10")
    check("杀『野猪·精英』计数入 obj key", qq["main_progress"] == {"野猪": 1}, str(qq["main_progress"]))
    check("面板进度显示 1/5", any("1/5" in l for l in lines), str(lines))
    out = await cmd(m, "quest_view", "g9", "p10", "任务")
    check("quest_view 进度 1/5", "1/5" in out, out[:200])
    lines = quest_kill_progress("g9", "p10", {"name": "巨型野猪"})
    check("前缀式『巨型野猪』不误伤", get_q("g9", "p10")["main_progress"] == {"野猪": 1}, str(get_q("g9", "p10")["main_progress"]))
    for _ in range(4):
        quest_kill_progress("g9", "p10", {"name": "野猪"})
    check("5 只后置 ready", get_q("g9", "p10")["main_status"] == "ready", get_q("g9", "p10")["main_status"])
    # 支线 kill key 一致（精确名）
    db.save_quests("g9", "p10", qdata("q1_3", "active", side={"s3": {"status": "active", "progress": {}}}))
    quest_kill_progress("g9", "p10", {"name": "森林狼"})
    qq = get_q("g9", "p10")
    check("支线 kill 计数入 obj key", qq["side"]["s3"]["progress"] == {"森林狼": 1}, str(qq["side"]["s3"]["progress"]))
    quest_kill_progress("g9", "p10", {"name": "森林狼·头狼"})
    qq = get_q("g9", "p10")
    check("支线『·』变体计入（前缀精确）",
          qq["side"]["s3"]["progress"] == {"森林狼": 2}, str(qq["side"]["s3"]["progress"]))
    quest_kill_progress("g9", "p10", {"name": "精英森林狼"})
    qq = get_q("g9", "p10")
    check("支线前缀式『精英森林狼』不误伤",
          qq["side"]["s3"]["progress"] == {"森林狼": 2}, str(qq["side"]["s3"]["progress"]))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)

asyncio.run(main())
