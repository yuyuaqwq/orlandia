# -*- coding: utf-8 -*-
"""v104 成就/称号修复项回归验收（8 项）

覆盖 v104 审计修复（M18/M22/M13 相关，模块：core/achievements.py、
core/achievement_conds.py、store/professions.py、commands/base.py、
commands/combat.py、data/achievements.py、data/maps.py）：

1. main_done 不再 TypeError：completed_main 含 q12_6 → ach_main12 可判定可解锁
2. flag 成就走 talk_flags：db.set_talk_flag 落库 → ach_bard_all/ach_truth 可判定
3. 无怪物成就改条件：ach_slime100/ach_goblin100 关键词引用现有怪物（数据断言）
4. hidden_area 语义：普通区域到访不计数，隐藏区域才计数（ach_mythril/ach_hidden3）
5. 称号 bonus 单次：采集 Lv.10 称号 hp 加成只加一次（不双倍发放）
6. 全知全能：ach_apprentice8 解锁 → add_prof_exp 经验 ×1.10（ceil）
7. 副业排行全服(跨群)：prof_top(group_id) 包含他群玩家（v113.5 T1）
8. world_events 写入：世界事件期间战斗结算 → stats.world_events 递增

独立运行：python tests/test_v104_achievements.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, Main, FakeEvent, clean_db, make_player  # noqa: F401
from content.achievements import cond_met, check_achievements

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")


def stats_of(gid, qid):
    return db.get_stats(gid, qid) or {}


def profs_of(gid, qid):
    return db.get_professions(gid, qid)


# ============ 1. main_done 不再 TypeError ============
print("【1. main_done（主线 12 章）不再 TypeError】")
clean_db()
p1 = make_player("g1", "q1", "测试甲", "战士", level=40)
s1 = stats_of("g1", "q1")
pr1 = profs_of("g1", "q1")
# q12_6 = 主线第 12 章『黎明之后』交付任务 id（main_done 判定依据）
COMPLETED_12 = [f"q{i}_1" for i in range(1, 13)] + ["q12_6"]
db.save_quests("g1", "q1", {
    "main_quest": "q12_6", "main_status": "done", "main_progress": {},
    "daily": {},
    "completed_main": COMPLETED_12,
    "side": {},
})
check("无 group_id → False（旧行为，不抛异常）",
      cond_met(p1, s1, pr1, {}, {"type": "main_done"}) is False)
check("有 group_id + q12_6 完成 → True（不再 TypeError 吞掉）",
      cond_met(p1, s1, pr1, {}, {"type": "main_done"}, "g1") is True)
check("main_quest_done(q6_1) → True（ach_saint_save 配套修复）",
      cond_met(p1, s1, pr1, {}, {"type": "main_quest_done", "key": "q6_1"}, "g1") is True)
db.save_quests("g1", "q1", {
    "main_quest": "q1_1", "main_status": "pending", "main_progress": {},
    "daily": {},
    "completed_main": ["q1_1", "q2_1"],
    "side": {},
})
check("未完成 q12_6 → False", cond_met(p1, s1, pr1, {}, {"type": "main_done"}, "g1") is False)
# 端到端：check_achievements 可解锁 ach_main12
db.save_quests("g1", "q1", {
    "main_quest": "q12_6", "main_status": "done", "main_progress": {},
    "daily": {},
    "completed_main": COMPLETED_12,
    "side": {},
})
new1 = check_achievements("g1", "q1", db.get_player("g1", "q1"), {})
ids1 = {a["id"] for a in new1}
check("check_achievements 解锁 ach_main12（黎明继承者）", "ach_main12" in ids1)
check("check_achievements 解锁 ach_saint_save（圣女守护者）", "ach_saint_save" in ids1)

# ============ 2. flag 成就走 talk_flags ============
print("【2. flag 成就走 talk_flags（对话系统落库）】")
clean_db()
p2 = make_player("g1", "q2", "测试乙", "战士", level=1)
s2 = stats_of("g1", "q2")
pr2 = profs_of("g1", "q2")
check("extra.flags 显式上下文 → True（测试兼容）",
      cond_met(p2, s2, pr2, {"flags": {"heard_song": True}},
               {"type": "flag", "flag": "heard_song"}) is True)
check("talk_flags 未设置 → False",
      cond_met(p2, s2, pr2, {}, {"type": "flag", "flag": "heard_song"}, "g1") is False)
db.set_talk_flag("g1", "q2", "npc_bard", "heard_song")
check("set_talk_flag 落库 heard_song → ach_bard_all 可判定 True",
      cond_met(p2, s2, pr2, {}, {"type": "flag", "flag": "heard_song"}, "g1") is True)
db.set_talk_flag("g1", "q2", "npc_rift", "saw_the_rift")
check("set_talk_flag 落库 saw_the_rift → ach_truth 可判定 True",
      cond_met(p2, s2, pr2, {}, {"type": "flag", "flag": "saw_the_rift"}, "g1") is True)
new2 = check_achievements("g1", "q2", db.get_player("g1", "q2"), {})
ids2 = {a["id"] for a in new2}
check("check_achievements 解锁 ach_bard_all（史诗聆听者）", "ach_bard_all" in ids2)
check("check_achievements 解锁 ach_truth（真相追寻者）", "ach_truth" in ids2)

# ============ 3. 无怪物成就改条件（数据断言） ============
print("【3. 无怪物成就改条件（kills_type 关键词必须命中现有怪物）】")
monster_names = set(C._INDEXES["monsters"]["id_to_name"].values())
byid = {a["id"]: a for a in C.ACHIEVEMENTS}
for aid in ("ach_slime100", "ach_goblin100"):
    cond3 = byid[aid]["cond"]
    kws = cond3.get("keywords") or [cond3["keyword"]]
    for kw in kws:
        check(f"{aid} 关键词『{kw}』存在对应怪物",
              any(kw in n for n in monster_names))
# 全量清扫：所有 kills_type 成就关键词都必须命中（防同类死锁回潮）
missing_all = []
for a in C.ACHIEVEMENTS:
    c = a.get("cond") or {}
    if c.get("type") != "kills_type":
        continue
    for kw in (c.get("keywords") or [c["keyword"]]):
        if not any(kw in n for n in monster_names):
            missing_all.append((a["id"], kw))
check("全部 kills_type 成就关键词均命中现有怪物（共扫 %d 条）" % len(missing_all),
      not missing_all)
if missing_all:
    print("  未命中:", missing_all)

# ============ 4. hidden_area 语义 ============
print("【4. hidden_area 只统计隐藏区域】")
clean_db()
p4 = make_player("g1", "q4", "测试丁", "战士", level=1)
s4 = stats_of("g1", "q4")
pr4 = profs_of("g1", "q4")
for mid in ("oak_plain", "white_deer_forest", "emerald_forest"):  # 3 个普通区域
    db.add_visited("g1", "q4", mid)
check("3 个普通区域 → ach_hidden3(value=2) 不计数",
      cond_met(p4, s4, pr4, {}, {"type": "hidden_area", "value": 2}, "g1") is False)
check("普通区域对 ach_mythril(value=1) 也不计数（旧实现误送）",
      cond_met(p4, s4, pr4, {}, {"type": "hidden_area", "value": 1}, "g1") is False)
db.add_visited("g1", "q4", "lost_library")
check("到访 1 个隐藏区域 → value=1 True",
      cond_met(p4, s4, pr4, {}, {"type": "hidden_area", "value": 1}, "g1") is True)
db.add_visited("g1", "q4", "ember_corridor")
check("到访 2 个隐藏区域 → value=2 True",
      cond_met(p4, s4, pr4, {}, {"type": "hidden_area", "value": 2}, "g1") is True)
new4 = check_achievements("g1", "q4", db.get_player("g1", "q4"), {})
ids4 = {a["id"] for a in new4}
check("check_achievements 解锁 ach_mythril（秘银追寻者）", "ach_mythril" in ids4)
check("check_achievements 解锁 ach_hidden3（v104 补测修复：value 3→2，2 隐藏区域可达）", "ach_hidden3" in ids4)

# ============ 5. 称号 bonus 单次 ============
print("【5. 称号 bonus 单次（Lv.10 大师称号不双倍发放）】")
clean_db()
make_player("g1", "q5", "测试戊", "战士", level=1)
db.add_prof_exp("g1", "q5", "gather", 2200)          # 采集 → Lv.10（v105 曲线累计 2100）
db.set_achievement("g1", "q5", "ach_pro_gather10", 1, 0)  # 同名成就『万物采集大师』也解锁
m5 = Main(None)
b5 = m5._title_bonus("g1", "q5")
check("采集 Lv.10：hp 加成 30（单次，非 60）", b5.get("hp") == 30)
db.set_achievement("g1", "q5", "ach_kill500", 1, 0)  # 无同名 TITLES 的成就 bonus 对照
b5b = m5._title_bonus("g1", "q5")
check("非重复成就 bonus 仍生效：ach_kill500 atk+5", b5b.get("atk") == 5)

# ============ 6. 全知全能副业经验 ×1.10 ============
print("【6. 全知全能（ach_apprentice8）→ 副业经验 ×1.10】")
clean_db()
make_player("g1", "q6", "测试己", "战士", level=1)
make_player("g1", "q7", "测试庚", "战士", level=1)
# v134.1 人类副业亲和+10%会干扰本测试（无成就基线）→ 测试玩家改用精灵
db.update_player("g1", "q6", race="elf")
db.update_player("g1", "q7", race="elf")
db.add_prof_exp("g1", "q6", "gather", 1)
check("无成就：gather exp +1", profs_of("g1", "q6")["gather"]["exp"] == 1)
db.set_achievement("g1", "q7", "ach_apprentice8", 1, 0)
db.add_prof_exp("g1", "q7", "gather", 1)
check("ach_apprentice8 解锁：exp +2（ceil(1×1.10)，保底 +1）",
      profs_of("g1", "q7")["gather"]["exp"] == 2)

# ============ 7. 副业排行全服(跨群) ============
print("【7. 副业排行 prof_top 全服(跨群，v113.5 T1)】")
clean_db()
make_player("g1", "q8", "测试辛", "战士", level=1)
make_player("g1", "q9", "测试壬", "战士", level=1)
make_player("g2", "q10", "测试癸", "战士", level=1)
db.add_prof_exp("g1", "q8", "gather", 1200)   # q8 总分高(1200→Lv.8，严格高于 q10 的 Lv.7)
db.add_prof_exp("g1", "q9", "mining", 300)    # q9 总分低
db.add_prof_exp("g2", "q10", "gather", 1000)  # 他群高总分，全服榜应计入（与等级榜 top_players 同口径）
# v113.6：prof_top 只计已激活副业等级（未激活不计分）——测试需先激活
db.activate_prof("g1", "q8", "gather")
db.activate_prof("g1", "q9", "mining")
db.activate_prof("g2", "q10", "gather")
tops7 = db.prof_top("g1", 10)
ids7 = {r["qq_id"] for r in tops7}
check("prof_top(g1) 全服含 q8/q9/q10", ids7 == {"q8", "q9", "q10"})
check("他群玩家 q10 计入全服榜", "q10" in ids7)
check("全服第一名 q8", bool(tops7) and tops7[0]["qq_id"] == "q8")
check("总分排序（q8 total > q9 total）",
      bool(tops7) and next(r["total"] for r in tops7 if r["qq_id"] == "q8")
      > next(r["total"] for r in tops7 if r["qq_id"] == "q9"))

# ============ 8. world_events 写入 ============
print("【8. 世界事件期间战斗 → stats.world_events 递增】")
clean_db()
p8 = make_player("g1", "q11", "测试子", "战士", level=1)
m8 = Main(None)
ev8 = FakeEvent("g1", "q11", "")
monster8 = {"id": "m_test_boar", "name": "测试野猪", "lv": 1, "role": "normal",
            "exp": 10, "gold": 5, "is_boss": False, "is_elite": False,
            "map_area": None, "drops": ["兽肉"]}
db.clear_world_event()
list(m8._handle_victory(ev8, "g1", "q11", db.get_player("g1", "q11"), monster8, "⚔️ 你发起了攻击！"))
check("无世界事件：world_events 保持 0", stats_of("g1", "q11").get("world_events", 0) == 0)
db.save_world_event("omen", int(time.time()) + 3600, {"desc": "测试事件"})
list(m8._handle_victory(ev8, "g1", "q11", db.get_player("g1", "q11"), monster8, "⚔️ 你发起了攻击！"))
st8 = stats_of("g1", "q11")
check("事件中战斗结算：world_events ≥ 1", st8.get("world_events", 0) >= 1)
check("world_event 条件可判定（ach_event10 计数打通）",
      cond_met(p8, st8, profs_of("g1", "q11"), {}, {"type": "world_event", "value": 1}) is True)
check("event_all 条件可判定（ach_event_all 计数打通）",
      cond_met(p8, st8, profs_of("g1", "q11"), {}, {"type": "event_all", "value": 1}) is True)

print()
print(f"结果: {PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)
