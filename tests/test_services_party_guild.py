# -*- coding: utf-8 -*-
"""P4-6 services 直测：party.py（组队域）+ guild.py（公会域）——不依赖 Main/FakeEvent。

覆盖（对齐任务卡新增 role/捐献规则直测 + 每日重置/跨天逻辑）：
  1. resolve_party_target：按名/按 qq/At 剥离/找不到
  2. party_join 新建队/拉人计数（bump_stats party_count）+ 拒绝路径
  3. party_leave_execute：普通退队/队长解散清理
  4. guild_create_check 门槛 + guild_create 建会扣金币
  5. guild_join / guild_leave_check（会长不能退） / guild_disband
  6. guild_sign 每日一次 + 数值
  7. guild_task_view 跨天重置展示
  8. guild_donate：材料判定（含任务道具排除）/扣料/每日一次 event_state
  9. guild_appoint role 校验（副会长 Lv3 门槛/精英无门槛/非会长/已在职）+ guild_demote
 10. guild_kill_progress：击杀推进 + 跨天重置 + 达标发奖（对齐 combat 击杀结算调用形态）

运行（沙盒）：
  "C:/Users/yuyu/AppData/Roaming/uv/tools/astrbot/Scripts/python.exe" tests/test_services_party_guild.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import db, clean_db
from content.persistence.social import guild_get_member as _ggm

from content.party import (
    resolve_party_target, party_join, party_leave_execute,
    party_leave_check, party_leave_inst_member,
)
from content.social_guild import (
    guild_create_check, guild_create, guild_join, guild_leave_check,
    guild_leave, guild_disband, guild_sign, guild_task_view,
    guild_donate, guild_donate_total, guild_donate_inventory,
    guild_appoint_check_role, guild_appoint_level_ok, guild_find_member,
    guild_appoint, guild_demote, guild_kill_progress,
)

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

def _mk_player(gid, qid, name, level=30, gold=10000):
    from _engine_harness import db as _db
    from _engine_harness import C as _C
    from content.panel import player_stats_detail
    cls = _C.CLASSES[_C.resolve("classes", "战士")]
    st0, _ = player_stats_detail("warrior", 1, {}, 0, None, 0, None, "human")
    _db.create_player(gid, qid, name, "warrior", cls["base"], st0["max_hp"], st0["max_mp"], "human", "male")
    _db.update_player(gid, qid, level=level, gold=gold, cur_map="oak_town")
    _db.init_stats(gid, qid)
    return _db.get_player(gid, qid)

def main():
    clean_db()
    # ---- 注册玩家（直接 store 建号，services 直测不依赖命令层）----
    p1 = _mk_player("g1", "s1", "会长")
    p2 = _mk_player("g1", "s2", "会员")
    p3 = _mk_player("g1", "s3", "精英")

    print("【party: resolve_party_target】")
    tq, err = resolve_party_target("g1", "s1", "会员")
    check("按名解析", tq == "s2" and err is None, f"{tq} {err}")
    tq, err = resolve_party_target("g1", "s1", "s3")
    check("按 qq 解析", tq == "s3", f"{tq}")
    tq, err = resolve_party_target("g1", "s1", "队伍会员")
    check("『队伍』前缀剥离", tq == "s2", f"{tq}")
    tq, err = resolve_party_target("g1", "s1", "组队[At:12345]")
    check("At 标记剥离（找不到该 qq）", tq is None and err is not None, f"{tq} {err}")
    tq, err = resolve_party_target("g1", "s1", "不存在的人")
    check("找不到玩家", err is not None and "找不到" in err, f"{err}")
    tq, err = resolve_party_target("g1", "s1", "")
    check("空参 = 面板（None,None）", tq is None and err is None, f"{tq} {err}")

    print("【party: party_join 新建 2 人队 + party_count】")
    ok, lines, _ = party_join("g1", "s1", "s2", "会员", [], check_achievements=lambda *a, **k: [])
    check("创建成功", ok and "组队成功" in lines[0], lines[0][:80])
    members = db.party_members("g1", "s1")
    check("队伍 2 人（队长 s1 首位）", len(members) == 2 and str(members[0]) == "s1", str(members))
    st1 = db.get_stats("g1", "s1")
    st2 = db.get_stats("g1", "s2")
    check("双方 party_count+1", (st1 or {}).get("party_count", 0) == 1 and (st2 or {}).get("party_count", 0) == 1,
          f"{st1} {st2}")
    ok, lines, _ = party_join("g1", "s3", "s1", "会长", [], check_achievements=lambda *a, **k: [])
    check("已有队伍者不能再建", not ok and "无法与" in lines[0], lines[0][:80])

    print("【party: party_join 拉人 + 拒绝路径】")
    # s1 是队长拉 s3 入队（3 人）
    ok, lines, _ = party_join("g1", "s1", "s3", "精英", db.party_members("g1", "s1"),
                              check_achievements=lambda *a, **k: [])
    check("队长拉人成功", ok and "加入了你的队伍" in lines[0], lines[0][:100])
    check("队伍 3 人", len(db.party_members("g1", "s1")) == 3, str(db.party_members("g1", "s1")))
    # 拉已在队的人（s2）→ party_add 拒绝
    ok, lines, _ = party_join("g1", "s1", "s2", "会员", db.party_members("g1", "s1"),
                              check_achievements=lambda *a, **k: [])
    check("拉已在队的人被拒", not ok and "无法拉入" in lines[0], lines[0][:100])

    print("【party: party_leave_execute】")
    left, ok_lines, _ = party_leave_execute("g1", "s3", False)
    check("队员退队成功", left and "退出队伍" in ok_lines[0], ok_lines[0])
    check("队伍回 2 人", len(db.party_members("g1", "s1")) == 2, str(db.party_members("g1", "s1")))
    # 队长退队 = 解散
    left, ok_lines, _ = party_leave_execute("g1", "s1", False)
    check("队长退队解散", left, ok_lines[0])
    check("队伍空", db.party_members("g1", "s1") == [], str(db.party_members("g1", "s1")))
    left, _, err_lines = party_leave_execute("g1", "s1", False)
    check("无队退队报错", not left and "还没有队伍" in err_lines[0], err_lines[0])
    ok, _, _ = party_join("g1", "s1", "s2", "会员", [], check_achievements=lambda *a, **k: [])
    check("重建队伍（清场后）", ok, "")

    print("【party: party_leave_check（副本中队长禁退）】")
    # 手工给 s1 写 instance battle 行（队长）
    _st = {"type": "instance", "leader": "s1", "members": ["s1", "s2"], "retreated": False}
    db.save_battle("g1", "s1", _st)
    blocked, msg = party_leave_check("g1", "s1")
    check("副本进行中队长禁退", blocked and "副本进行中不能退队" in msg, msg)
    inst = party_leave_inst_member("g1", "s2")
    check("队员挂在副本中判定", inst, "")
    db.clear_battle("g1", "s1")
    db.clear_battle("g1", "s2")

    print("【guild: guild_create_check + guild_create】")
    ok, err = guild_create_check(p1)
    check("30 级万金可建", ok and err is None, f"{ok} {err}")
    low = _mk_player("g1", "s9", "低等", level=10)
    ok, err = guild_create_check(low)
    check("10 级被拦（30 级门槛）", not ok and "30 级" in err, f"{err}")
    poor = _mk_player("g1", "s10", "穷鬼", level=30, gold=10)
    ok, err = guild_create_check(poor)
    check("金币不足被拦（1000）", not ok and "1000 金币" in err, f"{err}")
    gold_before = p1["gold"]
    ok, gid, err = guild_create("g1", "s1", p1, "屠龙勇士")
    check("建会成功", ok and gid, f"{ok} {gid} {err}")
    g = db.guild_get_by_leader("s1")
    check("公会落库 + desc 含玩家名", g is not None and "会长 创立的公会" in g.get("desc", ""), str(g))
    check("创建扣 1000 金币", db.get_player("g1", "s1")["gold"] == gold_before - 1000,
          f"{db.get_player('g1', 's1')['gold']}")
    ok, gid2, err = guild_create("g1", "s1", p1, "屠龙勇士")
    check("重名返回已存在", not ok and "已存在" in err, f"{err}")

    print("【guild: guild_join / guild_leave_check / guild_disband】")
    ok, g2, err = guild_join("g1", "s2", "屠龙勇士")
    check("加入成功", ok and g2["gid"] == g["gid"], f"{ok} {err}")
    check("成员 2 人", len(db.guild_members(g["gid"])) == 2, "")
    ok, g2, err = guild_join("g1", "s2", "不存在的会")
    check("找不到公会", not ok and "找不到公会" in err, f"{err}")
    blocked, msg = guild_leave_check(g, "s1")
    check("会长不能退会", blocked and "会长" in msg, msg)
    guild_leave(g, "s2")
    check("会员退会后 1 人", len(db.guild_members(g["gid"])) == 1, "")
    # 再入
    guild_join("g1", "s2", "屠龙勇士")

    print("【guild: guild_sign 每日一次 + 数值】")
    p_before = db.get_player("g1", "s2")["gold"]
    ok, lines, err = guild_sign("g1", "s2", g)
    check("签到成功", ok and "公会签到" in lines[0], lines[0][:100])
    cfg_sign_gold = 50
    check("签到金币 +50", db.get_player("g1", "s2")["gold"] == p_before + cfg_sign_gold,
          f"{p_before} → {db.get_player('g1','s2')['gold']}")
    gm = _ggm(g["gid"], "s2")
    check("成员贡献 +10", gm["contribute"] == 10, str(gm))
    ok, _, err = guild_sign("g1", "s2", g)
    check("同日再签被拦", not ok and "已经公会签过到" in err, f"{err}")

    print("【guild: guild_task_view 跨天重置】")
    db.guild_set_task(g["gid"], "s2", "2000-01-01", 3)
    ok, lines, _ = guild_task_view("g1", "s2", g)
    check("跨天重置为 0/5", ok and "(当前 0/5)" in lines[0], lines[0])
    db.guild_set_task(g["gid"], "s2", __import__("datetime").date.today().isoformat(), 5)
    ok, _, err = guild_task_view("g1", "s2", g)
    check("今日已完成被拦", not ok and "已完成" in err, f"{err}")

    print("【guild: guild_donate 判定/扣料/每日一次】")
    from content.persistence.inventory import add_item
    # 材料 mat_（普通）+ 任务道具 mat_（应排除）
    add_item("g1", "s2", "mat_iron", {"name": "铁矿", "type": "材料", "stackable": True}, 5)
    add_item("g1", "s2", "mat_quest_1", {"name": "烬火信标", "type": "任务道具", "stackable": True}, 99)
    mats = guild_donate_inventory("g1", "s2")
    check("任务道具被排除", all(it["key"] != "mat_quest_1" for it in mats), str([m["key"] for m in mats]))
    check("可捐材料 5 份", guild_donate_total(mats) == 5, "")
    ok, lines, err, need, total = guild_donate("g1", "s2", g)
    check("捐献成功", ok and "捐献完成" in lines[0], lines[0][:100])
    check("扣 3 份材料剩 2", guild_donate_total(guild_donate_inventory("g1", "s2")) == 2,
          str(guild_donate_total(guild_donate_inventory("g1", "s2"))))
    ok, _, err, _, _ = guild_donate("g1", "s2", g)
    check("当日再捐被拦", not ok and "已完成" in err, f"{err}")
    # 跨天清 event_state 后可再捐（模拟次日；先补料——首捐已扣 3 份剩 2）
    db.set_event_state(f"guild_donate:{g['gid']}:s2", "2000-01-01")
    add_item("g1", "s2", "mat_iron", {"name": "铁矿", "type": "材料", "stackable": True}, 3)
    ok, lines, err, need, total = guild_donate("g1", "s2", g)
    check("次日可再捐（重置判定走 event_state 日期）", ok and "捐献完成" in lines[0], f"{ok} {err}")
    # 材料不足路径
    _poor_m = _mk_player("g1", "s20", "无料人", level=30)
    guild_join("g1", "s20", "屠龙勇士")
    db.set_event_state(f"guild_donate:{g['gid']}:s20", "2000-01-01")
    ok, _, err, need, total = guild_donate("g1", "s20", g)
    check("无料不足文案含 need/total", not ok and "需要上交 3 份材料(当前 0/3)" in err and total == 0, f"{err}")

    print("【guild: role 校验（任命/免职）】")
    ok, err = guild_appoint_level_ok(g, "vice_leader")
    check("公会 Lv.1 任命副会长被拦（需 Lv.3）", not ok and "需要公会 Lv.3" in err, f"{err}")
    ok, err = guild_appoint_level_ok(g, "elite")
    check("精英无门槛", ok and err is None, f"{ok} {err}")
    check("role_map 副会长→vice_leader", guild_appoint_check_role("副会长") == "vice_leader", "")
    check("role_map 未知职位→None", guild_appoint_check_role("长老") is None, "")
    tm, tgt, err = guild_find_member(g, "会长")
    check("查到自己（会长）", tm is not None and tgt["qq_id"] == "s1", f"{err}")
    tm, tgt, err = guild_find_member(g, "不存在")
    check("查无此人", err is not None and "没找到玩家" in err, f"{err}")
    # 冲公会到 Lv.3
    db.guild_add_exp(g["gid"], 100000)
    g = db.guild_get_by_leader("s1")
    check("公会升到 Lv.3+", g["level"] >= 3, str(g["level"]))
    _label, _icon = guild_appoint(g, {"qq_id": "s2", "name": "会员"}, "vice_leader")
    check("任命副会长落库", _label == "副会长" and _ggm(g["gid"], "s2")["role"] == "vice_leader",
          f"{_label}")
    _label, _icon = guild_appoint(g, {"qq_id": "s20", "name": "无料人"}, "elite")
    check("任命精英落库", _label == "精英" and _ggm(g["gid"], "s20")["role"] == "elite", "")
    guild_demote(g, {"qq_id": "s2", "name": "会员"})
    check("免职降回 member", _ggm(g["gid"], "s2")["role"] == "member", "")

    print("【guild: guild_kill_progress 击杀推进 + 跨天重置 + 达标发奖】")
    _kbase = db.get_player("g1", "s2")["gold"]
    p_before = _kbase
    # 昨天已 4/5 → 今天击杀（跨天重置 → 1/5）
    db.guild_set_task(g["gid"], "s2", "2000-01-01", 4)
    lines, rewarded = guild_kill_progress("g1", "s2", g)
    check("跨天重置后 1/5", len(lines) == 1 and "1/5" in lines[0], str(lines))
    check("未达标不发奖", not rewarded, "")
    # 再杀 4 次到 5/5 达标（进度从 1 → 5）
    for _ in range(4):
        lines, rewarded = guild_kill_progress("g1", "s2", g)
    check("达标发奖行", rewarded and "公会任务完成" in lines[0], str(lines))
    _cfg = {"task_exp": 40, "task_contribute": 20, "task_gold": 100}
    # 5 次击杀中仅达标那次发 +100（前 4 次进度 1→4 不发金币）
    check("发奖金币 +100（仅达标那次）", db.get_player("g1", "s2")["gold"] == p_before + _cfg["task_gold"],
          f"{p_before} → {db.get_player('g1','s2')['gold']}")
    lines, rewarded = guild_kill_progress("g1", "s2", g)
    check("达标后再击杀无推进行", lines == [] and not rewarded, str(lines))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
