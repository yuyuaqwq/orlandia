# -*- coding: utf-8 -*-
"""L3 玩家事件总线集成验证（v181 L3-P4 验证网）——订阅方 + fire 链路行为固化。

跑法：python tests/test_l3_player_events.py（exit=0 全绿）
覆盖：
  A. field fire：主线击杀计数 + 每日 kill_any 逐只 + 返回行（quest 提示）
  B. field 公会：每场胜利 +1（guild_kill_progress 复用）+ 进度行
  C. kind 守卫：instance fire 不升级（副本不升级回血设计）；field fire 可升级
  D. instance fire：每日 kill_elite 推进（语义决策：任何击杀都算数）
  E. worldboss fire：每日 kill_boss 达标结算发奖
  F. 塔卫条件：monster id tower_ 前缀 → 塔层推进行（field）
  G. field 无公会/无任务玩家：fire 空行安全（零行不补空行）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, make_player  # ★ P5C-REPOINT：conftest 兼容面（同名同义）

from content.player_events import fire  # ★ P5C-REPOINT：直取包内真源（原 game.services.player_event_bus）
from content.player_events import ensure_registered as _ensure_registered  # ★ P5C-REPOINT：注册时机 = 原订阅方壳 import 时
_ensure_registered()                                        # 触发注册（幂等；原 player_event_subscribers import 副作用）
from content.social_guild import guild_create  # ★ P5C-REPOINT：直取包内真源（原 game.services.guild）

# ★ P5C-REPOINT：原宿主薄壳 `game/services/quests_flow.py` 的注入
#   `quests_svc = game.services.quests` 随 game/** 删除而消失。按 REPOINT_MAP §2，
#   `game.services.quests` 的真源 = `content.profession_quests`
#   （bump_daily_progress / settle_daily_quest / DAILY_META_KEYS）。补回该注入，
#   否则 `_sub_quests`（quest_kill_progress → _bump_daily_progress）会被总线当异常跳过。
from content import profession_quests as _profession_quests  # noqa: E402
from content import quests_flow as _quests_flow  # noqa: E402
_quests_flow.bind_host(quests_svc=_profession_quests)
from content.flow.tower_progress import _tower_state  # ★ B18-REPOINT：直取包内实现本体（宿主同名壳不再被测试引用）

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def _base_ctx(gid, qid, kind="field", killed=None, monster=None, meta=None, exp=0):
    p = db.get_player(gid, qid) or {}
    return {
        "kind": kind,
        "group_id": gid, "qq_id": qid,
        "player": p, "monster": monster or (killed[0] if killed else {}),
        "killed": killed or [],
        "side_effects": [],
        "meta": meta or {},
    }


def _save_quests(gid, qid, main=None, daily=None):
    q = db.get_quests(gid, qid) or {"main_quest": None, "main_status": "pending", "main_progress": {}, "daily": {}, "side": {}}
    if main is not None:
        q["main_quest"], q["main_status"] = main, "active"
    if daily is not None:
        q["daily"] = daily
    db.save_quests(gid, qid, q)
    return q


def _dly(key, obj, name="测试每日", reward_exp=400, reward_gold=150):
    # _date 必须今天（quest_kill_progress 内 expire_daily 非今日清空整组）
    return {key: {"objective": obj, "name": name, "progress": 0,
                  "reward_exp": reward_exp, "reward_gold": reward_gold},
            "_date": __import__("datetime").date.today().isoformat(),
            "_completed": 0, "_repeat": {}}


def tA_field_quest_kill():
    print("A. field fire：主线 + 每日 kill_any 逐只推进")
    clean_db()
    make_player("gA", "qA", "甲", "战士", level=5)
    _save_quests("gA", "qA", main="q1_3", daily=_dly("d0", {"kill_any": 5}))
    ctx = _base_ctx("gA", "qA", killed=[{"name": "野猪"}, {"name": "野狗"}, {"name": "野猪"}])
    lines = fire("battle_victory", ctx)
    q = db.get_quests("gA", "qA")
    check("主线击杀 野猪=2（2 只各计一次，前缀精确）", q["main_progress"].get("野猪") == 2, str(q.get("main_progress")))
    check("每日 kill_any +3", q["daily"]["d0"]["progress"] == 3, str(q["daily"]["d0"]))
    joined = "|".join(lines)
    check("返回行含主线进度（2 只逐只 1/5→2/5）", "📜 主线" in joined and "2/5" in joined, joined[:200])
    # 每日未达标静默无行（与野外一致：仅达标 settle 出完成行）
    check("行含空行分段（quest 段 blank=True）", "" in lines, repr(lines))


def tB_field_guild():
    print("B. field 公会：每场胜利 +1")
    clean_db()
    p = make_player("gB", "qB", "乙", "战士", level=30)
    ok, gid, err = guild_create("gB", "qB", p, "屠龙勇士")
    check("建会成功", ok, f"{ok} {err}")
    ctx = _base_ctx("gB", "qB", killed=[{"name": "野猪"}])
    lines = fire("battle_victory", ctx)
    tdate, tprog = db.guild_get_task(gid, "qB")
    check("公会进度 1/kill_task", tprog == 1, f"tprog={tprog}")
    joined = "|".join(lines)
    check("返回行含公会进度", "🎯 公会任务进度" in joined, joined[:200])


def tC_kind_levelup_guard():
    print("C. kind 守卫：levelup 订阅仅 field（副本/世界Boss 结算不主动升级）")
    clean_db()
    make_player("gC", "qC", "丙", "战士", level=5)
    from content.player_events import _sub_levelup  # ★ P5C-REPOINT
    ctx_i = _base_ctx("gC", "qC", kind="instance", killed=[{"name": "野猪"}], meta={"inst_id": "x"})
    check("instance 守卫返回 []", _sub_levelup(ctx_i) == [], repr(_sub_levelup(ctx_i)))
    ctx_w = _base_ctx("gC", "qC", kind="worldboss", killed=[{"name": "魔王", "is_boss": True}])
    check("worldboss 守卫返回 []", _sub_levelup(ctx_w) == [], repr(_sub_levelup(ctx_w)))
    # field 不守卫：走完整升级检查路径（返回 list；升级与否由 db exp 决定）
    ctx_f = _base_ctx("gC", "qC", killed=[{"name": "野猪"}])
    r = _sub_levelup(ctx_f)
    check("field 执行返回 list", isinstance(r, list), repr(r))


def tD_instance_daily_elite():
    print("D. instance fire：每日 kill_elite 推进（语义决策：任何击杀都算数）")
    clean_db()
    make_player("gD", "qD", "丁", "战士", level=20)
    _save_quests("gD", "qD", daily=_dly("d1", {"kill_elite": 3}))
    ctx = _base_ctx("gD", "qD", kind="instance",
                    killed=[{"name": "副本精英", "is_elite": True}, {"name": "爪牙", "is_minion": True}],
                    meta={"inst_id": "inst_001"})
    lines = fire("battle_victory", ctx)
    q = db.get_quests("gD", "qD")
    check("每日 kill_elite 精英 +1（爪牙不推）", q["daily"]["d1"]["progress"] == 1, str(q["daily"]))
    # 每日未达标静默无行（与野外一致）；行若有 = quests/guild 反应
    check("fire 不崩且返回 list", isinstance(lines, list), repr(lines)[:100])


def tE_worldboss_kill_boss():
    print("E. worldboss fire：每日 kill_boss 达标结算发奖")
    clean_db()
    p = make_player("gE", "qE", "戊", "战士", level=20)
    gold0 = p.get("gold", 0)
    _save_quests("gE", "qE", daily=_dly("d2", {"kill_boss": 1}))
    ctx = _base_ctx("gE", "qE", kind="worldboss",
                    killed=[{"name": "深渊魔王", "is_boss": True}], monster={"name": "深渊魔王", "is_boss": True})
    lines = fire("battle_victory", ctx)
    q = db.get_quests("gE", "qE")
    check("kill_boss 达标任务被移除", "d2" not in (q.get("daily") or {}), str(q.get("daily")))
    check("发奖金币到账", db.get_player("gE", "qE")["gold"] > gold0,
          f"gold {gold0}→{db.get_player('gE','qE')['gold']}")
    joined = "|".join(lines)
    check("返回行含每日完成", "📜 每日" in joined and "完成" in joined, joined[:200])


def tF_tower_guard_cond():
    print("F. 塔卫条件：monster id tower_ 前缀 → 塔层推进")
    clean_db()
    make_player("gF", "qF", "己", "战士", level=75)
    ctx = _base_ctx("gF", "qF", killed=[{"id": "tower_1", "name": "第一层守卫", "lv": 71}],
                    monster={"id": "tower_1", "name": "第一层守卫", "lv": 71})
    lines = fire("battle_victory", ctx)
    st = _tower_state("qF")
    check("塔状态 cur>=1", int(st.get("cur") or 0) >= 1, str(st))
    joined = "|".join(lines)
    check("返回行含塔层突破", "突破" in joined, joined[:200])


def tG_empty_safety():
    print("G. 无公会/无任务玩家 fire 安全（无 quest/guild 反应行）")
    clean_db()
    make_player("gG", "qG", "庚", "战士", level=10)
    ctx = _base_ctx("gG", "qG", killed=[{"name": "普通野怪"}])
    lines = fire("battle_victory", ctx)
    joined = "\n".join(lines)
    check("无公会/任务行（允许新号成就解锁行 🏆）",
          "🎯" not in joined and "📜" not in joined and "🎉" not in joined, joined[:200])


def main():
    print("== L3 玩家事件总线集成验证 ==")
    tA_field_quest_kill()
    tB_field_guild()
    tC_kind_levelup_guard()
    tD_instance_daily_elite()
    tE_worldboss_kill_boss()
    tF_tower_guard_cond()
    tG_empty_safety()
    print()
    if failed:
        print(f"失败 {failed} 项")
        sys.exit(1)
    print(f"全部通过 ✅（{passed} 断言）")


if __name__ == "__main__":
    main()
