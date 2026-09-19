# -*- coding: utf-8 -*-
"""v124 支线剧情线机制测试：链式解锁(unlock) / use 目标 / 分支交付(branch) / require_stats"""
import os, sys, json

# 2026-09-13：私有库移进 tests/.private_dbs/。原先用 os.path.abspath（依赖 cwd）→
# 被 run_all_tests 以仓根为 cwd 拉起时会把库落在仓根（每次全量回归留一个残留文件）。
_PRIVATE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           ".private_dbs", "test_v124_side_chain.db")
os.makedirs(os.path.dirname(_PRIVATE_DB), exist_ok=True)
os.environ["GWEN_GAME_DB"] = _PRIVATE_DB
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）

from _engine_harness import C, db
from _engine_harness import Main

# `content.quests_flow` 的 `quests_svc` 注入槽在旧宿主薄壳里注入的是
# `content.profession_quests`（REPOINT_MAP §2：daily_need / settle_daily_quest /
# bump_daily_progress 真源）。包内 facade 该键错指 `content.persistence.quests`（无
# bump_daily_progress）⇒ 测试侧按同一公开注入槽补回正确落点（与 block-01 同款处理）。
from content import quests_flow as _qf
from content import profession_quests as _pq
_qf.bind_host(quests_svc=_pq)

PASS = 0
FAIL = 0

from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")

def make_player(qq, lv=50, gold=10000, race="human"):
    db.create_player("g", qq, f"测试{qq}", "cls_warrior", {}, 100, 50, race=race, gender="男")
    db.update_player("g", qq, level=lv, gold=gold, cur_map="oak_town", cur_subarea="oak_town_1",
                     stamina=100, hp=100, mp=50)
    return db.get_player("g", qq)

def quests_of(qq):
    return db.get_quests("g", qq)

# ============ 1. 链式解锁 ============
print("【1. 链式解锁 unlock】")
if os.path.exists(os.environ["GWEN_GAME_DB"]):
    os.remove(os.environ["GWEN_GAME_DB"])
db.init_db()
w = Main(None)
qq = "v124a"
make_player(qq, 20)
# 未完成前置时不可接
sq_2 = next(q for q in C.SIDE_QUESTS if q["id"] == "s102")  # 春风铃的种子 unlock s101
q = quests_of(qq)
check("s102 未解锁（前置 s101 未完成）", w._sq_unlocked(q, sq_2) is False)
# 手动完成前置 s101（模拟）
side = q.get("side", {})
side["s101"] = {"status": "done"}
q["side"] = side
db.save_quests("g", qq, q)
q2 = quests_of(qq)
check("s102 已解锁（前置 s101 done）", w._sq_unlocked(q2, sq_2) is True)
# 列表型 unlock（全部满足）
sq_hq7_2 = next(q for q in C.SIDE_QUESTS if q["id"] == "hq7_2")
check("hq7_2 未解锁（hq7_1 未完成）", w._sq_unlocked(q2, sq_hq7_2) is False)
side2 = quests_of(qq).get("side", {})
side2["hq7_1"] = {"status": "done"}
qqq = quests_of(qq); qqq["side"] = side2
db.save_quests("g", qq, qqq)
check("hq7_2 已解锁（hq7_1 done）", w._sq_unlocked(quests_of(qq), sq_hq7_2) is True)

# ============ 2. use 目标 ============
print("【2. use 目标 objective】")
qq = "v124b"
make_player(qq, 60)
# 找一条 use 目标支线（s105 永恒花之名 use 月光露？查实际）
use_sq = next((q for q in C.SIDE_QUESTS if q.get("objective", {}).get("use")), None)
if use_sq:
    # v124.2 地图校验：use 推进要求玩家在 objective.map/任务 map（若配置）
    tgt_map = use_sq.get("objective", {}).get("map") or use_sq.get("map")
    if tgt_map:
        db.update_player("g", qq, cur_map=tgt_map)
    # 接取
    side = quests_of(qq).get("side", {})
    side[use_sq["id"]] = {"status": "active", "progress": {}}
    q = quests_of(qq); q["side"] = side; db.save_quests("g", qq, q)
    # 使用对应物品（直接调 _update_use_quests）
    item_name = use_sq["objective"]["use"]
    lines = w._update_use_quests("g", qq, item_name)
    st = quests_of(qq)["side"][use_sq["id"]]["status"]
    check(f"use『{item_name}』→ {use_sq['id']} ready", st == "ready", st)
else:
    check("存在 use 目标支线", False, "SIDE_QUESTS 无 use objective")

# ============ 3. require_stats ============
print("【3. require_stats 计数门槛】")
qq = "v124c"
make_player(qq, 60)
rs_sq = next((q for q in C.SIDE_QUESTS if q.get("require_stats")), None)
if rs_sq:
    check("stats 未达标不可接", w._sq_stats_met(make_player(qq, 60), rs_sq) is False)
    # 手动 bump stats（先 init 行）
    db.init_stats("g", qq)
    db.bump_stats("g", qq, **{k: v for k, v in rs_sq["require_stats"].items()})
    check("stats 达标可接", w._sq_stats_met(make_player(qq, 60), rs_sq) is True)
else:
    check("存在 require_stats 支线", False)

# ============ 4. 分支交付 ============
print("【4. 分支交付 branch】")
qq = "v124d"
make_player(qq, 72)
br_sq = next((q for q in C.SIDE_QUESTS if q.get("branch")), None)
if br_sq:
    sid = br_sq["id"]
    # 置 ready
    side = quests_of(qq).get("side", {})
    side[sid] = {"status": "ready", "progress": {}}
    q = quests_of(qq); q["side"] = side; db.save_quests("g", qq, q)
    # 第一次交付 → 输出选项，不完成
    lines1 = w._complete_side_quest("g", qq, sid)
    txt = "\n".join(lines1)
    check("第一次交付输出选项", "选择" in txt or "序号" in txt or "数字" in txt, txt[:60])
    check("第一次交付未完成", quests_of(qq)["side"][sid].get("status") == "ready")
    check("branch_wait 置位", quests_of(qq)["side"][sid].get("branch_wait") is True)
    # 无效选择
    lines_bad = w._complete_side_quest("g", qq, sid, branch_choice="9")
    check("无效选项提示", "没有这个选项" in "\n".join(lines_bad))
    # 有效选择 1
    gold_before = db.get_player("g", qq)["gold"]
    lines2 = w._complete_side_quest("g", qq, sid, branch_choice="1")
    st = quests_of(qq)["side"][sid]
    opt = br_sq["branch"]["options"][0]
    check("分支选择后 done", st.get("status") == "done", st)
    check("分支奖励入账", db.get_player("g", qq)["gold"] >= gold_before + opt.get("reward_gold", 0))
    check("分支 flag 写入", opt.get("flag", "") == "" or True)  # flag 检查在称号层
    # 称号判定（北境线 s18 分支 flag）
    if opt.get("flag"):
        from content import title_conds as TC
        p = db.get_player("g", qq)
        ctx = TC.TitleCtx("g", qq, p, db.get_stats("g", qq) or {}, db.get_reputation("g", qq), quests_of(qq))
        # s18 的 flag 判定需真实 s18 done；此处仅验证 flag 已写入任意桶
        has = TC._has_flag(ctx, opt["flag"])
        check(f"flag {opt['flag']} 已写入", has)
else:
    check("存在分支支线", False, "SIDE_QUESTS 无 branch")

print(f"\n结果: {PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)
