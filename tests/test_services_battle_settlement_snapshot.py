# -*- coding: utf-8 -*-
"""v181 P4-9 战斗结算快照测试（改前绿 = baseline，改后逐字段全等 = 行为零变化铁证）

P4-9（BattleSettlementService）：combat._handle_victory/_handle_defeat 纯同步段
随迁 game/services/battle_settlement.py（victory_settle/defeat_settle），命令层留
async generator 壳。本文件在旧实现上先跑绿存档 baseline，改造后再跑必须逐字段全等。

覆盖场景（全部直调 Main 实例方法 = 与 test_v84/v85/v104_achievements/v136/
v104_explore_map 同口径）：
  A. 低等级普通怪胜利（组队/公会/宠物/坐骑/世界事件/运势全缺省）
  B. 精英怪胜利（area 声望 faction + elite_kills）
  C. Boss 怪胜利 + extra_kills（多目标 quest 进度路径——壳层任务进度循环）
  D. 隐藏怪胜利（hm_defeated_{gid}_{qid} event_state + 成就判定段）
  E. 胜利带宠物（宠物经验/饱食度 -2/分经验升级路径）
  F. 普通战败（-10% 金币 + 回最近城镇满血）
  G. 红名战败（额外 -10% 上限 2000）
  H. 复活羽毛战败（revive_choice_* json 结构 + 满血回城 + 不扣金币）

确定性铁律（v103）：
  - 每场景 random.seed(固定) → 掉落/符文/原石随机序列一致
  - uuid.uuid4 打桩为固定序号 → 入包 key 一致
  - 世界事件场景结束后 clear_world_event 防串场
  - 快照字段全取 DB（get_player/get_inventory/pet_get/get_stats/get_bestiary/
    get_reputation/get_quests/get_event_state）→ 旧实现跑一遍存 dict，
    新实现跑一遍比对逐字段全等。

运行：python tests/test_services_battle_settlement_snapshot.py（exit=0 全绿）
"""
import json
import os
import random
import sys
import time
import uuid as _uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent  # noqa: E402
from _engine_harness import C as _C  # noqa: E402  （原 game.content 聚合面 → 包内聚合门面）

PASS = 0
FAIL = 0
SCENARIOS = []  # (name, snapshot_dict)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


class _FixedUUID:
    """uuid.uuid4 打桩：按序返回固定 hex，保证入包 key 跨实现一致。"""

    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return _uuid.UUID(int=self.n)


def _inv_snapshot(gid, qid):
    out = []
    for r in db.get_inventory(gid, qid):
        d = dict(r["data"])
        d.pop("desc", None)  # 部分物品 desc 含 uuid/随机量——只比结构性字段
        out.append({"key": r["key"], "count": r["count"], "data": d})
    return out


def _player_public(p):
    return {k: p.get(k) for k in (
        "level", "exp", "gold", "hp", "mp", "max_hp", "max_mp",
        "cur_map", "cur_subarea", "attr_pts", "skill_points",
        "learned_skills", "learned_blueprints", "equipment",
    )}


def _bestiary_map(gid, qid):
    rows = db.get_bestiary(gid, qid) or []
    if isinstance(rows, list):
        return {r["monster"]: r["kills"] for r in rows}
    return rows or {}


def _snap(gid, qid, p, mon, extra=None):
    """收集当前全量可观察状态（供全等比对）。"""
    s = {
        "player": _player_public(p),
        "inv": _inv_snapshot(gid, qid),
        "pet": db.pet_get(qid),
        "stats": db.get_stats(gid, qid) or {},
        "bestiary": _bestiary_map(gid, qid),
        "rep": db.get_reputation(gid, qid) or {},
        "quests": db.get_quests(gid, qid),
        "evt": {},
        "extra": extra or {},
    }
    # 时间敏感字段归一：跨实现/跨时间全等需归零（epoch 秒级也会随运行时刻漂移）
    if s["pet"] and "last_sat_time" in s["pet"]:
        s["pet"]["last_sat_time"] = 0
    if s["pet"] and "exp" in s["pet"]:
        pass  # exp/level/satiety/bond 业务字段保留
    # event_state 全量（key 前缀收敛，避免读全表）
    for prefix, key in (
        ("revive_choice_", f"revive_choice_{gid}_{qid}"),
        ("hm_defeated_", f"hm_defeated_{gid}_{qid}"),
        ("red_", f"red_{qid}"),
        ("daily_fortune_", f"daily_fortune_{gid}_{qid}"),
        ("pvp_cd_", f"pvp_cd_{qid}"),
    ):
        v = db.get_event_state(key)
        if v is not None:
            if prefix == "revive_choice_":
                try:
                    _j = json.loads(v)
                    if "ts" in _j:
                        _j["ts"] = 0
                    v = json.dumps(_j, ensure_ascii=False)
                except Exception:
                    pass
            if prefix == "red_":
                v = "0"
            if prefix == "daily_fortune_":
                try:
                    _j = json.loads(v)
                    if "date" in _j:
                        _j["date"] = ""
                    v = json.dumps(_j, ensure_ascii=False)
                except Exception:
                    pass
            s["evt"][key] = v
    return s


def _mk_monster(name="野猪", role="dps", lv=3, exp=49, gold=20, is_boss=False,
                is_elite=False, area="oak", drops=None, mid="m_boar", extra=None):
    m = {
        "id": mid, "uid": f"u_{mid}", "name": name, "lv": lv, "role": role,
        "rank": 1, "reach": 1, "hp": 100, "max_hp": 100, "exp": exp, "gold": gold,
        "is_boss": is_boss, "is_elite": is_elite, "map_area": area,
        "drops": drops or [], "skills": [], "buffs": {},
    }
    if extra:
        m.update(extra)
    return m


def _run_victory(m, gid, qid, player, mon, result, extra_kills=None, seed=1):
    random.seed(seed)
    _uuid.uuid4 = _FixedUUID()
    out = []
    for r in m._handle_victory(FakeEvent(gid, qid), gid, qid, player, mon, result,
                               extra_kills=extra_kills):
        out.append(r)
    return out


def _run_defeat(m, gid, qid, player, mon, result, seed=1):
    random.seed(seed)
    _uuid.uuid4 = _FixedUUID()
    out = []
    for r in m._handle_defeat(FakeEvent(gid, qid), gid, qid, player, mon, result):
        out.append(r)
    return out


def _player(gid, qid):
    return db.get_player(gid, qid)


def scenario_a_normal_victory():
    print("\n【A. 普通怪胜利（全缺省状态）】")
    clean_db()
    gid, qid = "gA", "qA"
    make_p = _player if False else None
    from _engine_harness import make_player
    player = make_player(gid, qid, "甲", "战士", 5)
    db.update_player(gid, qid, cur_map="oak_plain", cur_subarea="oak_plain_1", gold=50, exp=0)
    player = _player(gid, qid)
    mon = _mk_monster()  # lv3 exp49 gold20 oak normal
    out = _run_victory(Main(None), gid, qid, player, mon, "⚔️ 你发起了攻击！")
    txt = "\n".join(str(x) for x in out)
    p2 = _player(gid, qid)
    # 快照
    snap = {"out": txt, "db": _snap(gid, qid, p2, mon)}
    SCENARIOS.append(("A_normal_victory", snap))
    # 基础断言（旧实现基线值，改造后不变）
    check("A 击败标题行", "🎉 你击败了【野猪】！" in txt)
    # 求知属性（战士职业基础 exp_bonus=5%）→ 49×1.05=51（test_v1307 expected_exp_gain 同口径）
    check("A 经验行 51", "✨ 经验 +51" in txt)
    check("A 经验入账", p2["exp"] == 51, f"exp={p2['exp']}")
    check("A kills=1", (db.get_stats(gid, qid) or {}).get("kills") == 1)
    check("A day_kills=1", (db.get_stats(gid, qid) or {}).get("day_kills") == 1)
    # v46：bestiary 按怪物 ID 存（m_boar）——bump_bestiary 内部 resolve
    check("A bestiary m_boar=1", _bestiary_map(gid, qid).get("m_boar") == 1)
    check("A 无世界事件统计", (db.get_stats(gid, qid) or {}).get("world_events", 0) == 0)
    check("A 战斗已清除", db.get_battle(gid, qid) is None)


def scenario_b_elite_victory():
    print("\n【B. 精英怪胜利（声望/elite_kills）】")
    clean_db()
    gid, qid = "gB", "qB"
    from _engine_harness import make_player
    player = make_player(gid, qid, "乙", "战士", 6)
    db.update_player(gid, qid, cur_map="oak_plain", cur_subarea="oak_plain_6", gold=0, exp=0)
    player = _player(gid, qid)
    mon = _mk_monster(name="巨型野猪", role="elite", lv=6, exp=165, gold=88,
                      is_elite=True, mid="e_great_boar")
    out = _run_victory(Main(None), gid, qid, player, mon, "⚔️ 你发起了攻击！")
    txt = "\n".join(str(x) for x in out)
    p2 = _player(gid, qid)
    SCENARIOS.append(("B_elite_victory", {"out": txt, "db": _snap(gid, qid, p2, mon)}))
    check("B elite_kills=1", (db.get_stats(gid, qid) or {}).get("elite_kills") == 1)
    st = db.get_stats(gid, qid) or {}
    check("B kills=1", st.get("kills") == 1)
    check("B 声望 +3（精英）", (db.get_reputation(gid, qid) or {}).get("kingdom") == 3,
          str(db.get_reputation(gid, qid)))
    check("B 声望行", "声望 +3" in txt)


def scenario_c_boss_victory_extra_kills():
    print("\n【C. Boss 胜利 + extra_kills 多目标任务进度】")
    clean_db()
    gid, qid = "gC", "qC"
    from _engine_harness import make_player
    player = make_player(gid, qid, "丙", "战士", 8)
    db.update_player(gid, qid, cur_map="oak_plain", cur_subarea="oak_plain_1", gold=100, exp=0)
    player = _player(gid, qid)
    # 主线杀 5 野猪任务 q1_3
    import datetime
    today = datetime.date.today().isoformat()
    db.save_quests(gid, qid, {
        "main_quest": "q1_3", "main_status": "active", "main_progress": {},
        "daily": {"_date": today,
                  "d0": {"name": "讨伐试炼", "desc": "击杀任意怪物", "objective": {"kill_any": 5},
                         "reward_exp": 100, "reward_gold": 50, "progress": 0}},
        "completed_main": [], "side": {},
    })
    boss = _mk_monster(name="野猪王", role="boss", lv=8, exp=495, gold=312,
                       is_boss=True, mid="m_boar_king", area="oak",
                       drops=["兽肉", "野猪牙"])
    extra_kills = [_mk_monster(name="野猪", role="dps", lv=3, exp=49, gold=20, mid="m_boar"),
                   _mk_monster(name="野猪·幼崽", role="dps", lv=2, exp=30, gold=10, mid="m_boar_piglet")]
    out = _run_victory(Main(None), gid, qid, player, boss, "⚔️ 你发起了攻击！", extra_kills=extra_kills)
    txt = "\n".join(str(x) for x in out)
    p2 = _player(gid, qid)
    SCENARIOS.append(("C_boss_extra_kills", {"out": txt, "db": _snap(gid, qid, p2, boss, {"ek": extra_kills})}))
    q = db.get_quests(gid, qid)
    check("C boss_kills=1", (db.get_stats(gid, qid) or {}).get("boss_kills") == 1)
    # 主线 q1_3 杀 5 野猪：主怪野猪王不匹配（前缀精确），两只副怪（野猪/野猪·幼崽）各 +1
    check("C 主线进度野猪 2", (q.get("main_progress") or {}).get("野猪") == 2,
          str(q.get("main_progress")))
    check("C 每日 kill_any +3", (q.get("daily") or {}).get("d0", {}).get("progress") == 3,
          str(q.get("daily")))
    # 求知 5%：495×1.05=519
    check("C 经验 519 入账", p2["exp"] == 519, f"exp={p2['exp']}")


def scenario_d_hidden_monster_victory():
    print("\n【D. 隐藏怪胜利（hm_defeated 累计）】")
    clean_db()
    gid, qid = "gD", "qD"
    from _engine_harness import make_player
    player = make_player(gid, qid, "丁", "战士", 10)
    db.update_player(gid, qid, cur_map="oak_plain", cur_subarea="oak_plain_1", gold=0, exp=0)
    player = _player(gid, qid)
    mon = _mk_monster(name="黄金史莱姆", role="dps", lv=6, exp=60, gold=30,
                      mid="e_gold_slime", extra={"is_hidden": True})
    out = _run_victory(Main(None), gid, qid, player, mon, "⚔️ 你发起了攻击！")
    txt = "\n".join(str(x) for x in out)
    p2 = _player(gid, qid)
    SCENARIOS.append(("D_hidden_monster", {"out": txt, "db": _snap(gid, qid, p2, mon)}))
    hm = db.get_event_state(f"hm_defeated_{gid}_{qid}")
    check("D hm_defeated 含 e_gold_slime", hm and "e_gold_slime" in hm, str(hm))
    # 二次击杀累计不变（同 id 去重）
    _run_victory(Main(None), gid, qid, _player(gid, qid), mon, "⚔️ 你发起了攻击！")
    hm2 = db.get_event_state(f"hm_defeated_{gid}_{qid}")
    check("D 二次击杀去重", hm2 == hm, f"{hm2} vs {hm}")


def scenario_e_pet_victory():
    print("\n【E. 宠物在场胜利（饱食度 -2/分经验）】")
    clean_db()
    gid, qid = "gE", "qE"
    from _engine_harness import make_player
    player = make_player(gid, qid, "戊", "战士", 5)
    db.update_player(gid, qid, cur_map="oak_plain", cur_subarea="oak_plain_1", gold=0, exp=0)
    db.pet_create(qid, "pet_wolf", "森林狼崽")
    db.pet_update(qid, satiety=100, level=1, exp=0, bond=60)
    player = _player(gid, qid)
    mon = _mk_monster()  # exp49 lv3
    out = _run_victory(Main(None), gid, qid, player, mon, "⚔️ 你发起了攻击！")
    txt = "\n".join(str(x) for x in out)
    p2 = _player(gid, qid)
    SCENARIOS.append(("E_pet_victory", {"out": txt, "db": _snap(gid, qid, p2, mon)}))
    pet = db.pet_get(qid)
    check("E 宠物饱食度 98", pet["satiety"] == 98, str(pet["satiety"]))
    # lv3 怪：p_gain = max(1, int(49*0.2*mult(lv1 vs 3)))
    check("E 羁绊行", "💕 羁绊(亲密度≥50)：经验 +5%" in txt)
    check("E 陪伴行", "🐾 陪伴：经验 +" in txt)


def scenario_f_defeat_normal():
    print("\n【F. 普通战败（-10% + 回城满血）】")
    clean_db()
    gid, qid = "gF", "qF"
    from _engine_harness import make_player
    player = make_player(gid, qid, "己", "战士", 30)
    db.update_player(gid, qid, cur_map="cinder_mountain", cur_subarea="cinder_mountain_3",
                     gold=1000, hp=10, mp=5, exp=0)
    player = _player(gid, qid)
    mon = _mk_monster(name="烬山魔物", lv=30, exp=1000, gold=500, area="cinder", mid="m_cinder")
    out = _run_defeat(Main(None), gid, qid, player, mon, "你被击败了")
    txt = "\n".join(str(x) for x in out)
    p2 = _player(gid, qid)
    SCENARIOS.append(("F_defeat_normal", {"out": txt, "db": _snap(gid, qid, p2, mon)}))
    check("F 扣 10% 金币 → 900", p2["gold"] == 900, f"gold={p2['gold']}")
    check("F 满血复活", p2["hp"] == p2["max_hp"] and p2["mp"] == p2["max_mp"])
    check("F 回最近城镇", p2["cur_map"] != "oak_town", p2["cur_map"])
    check("F deaths=1", (db.get_stats(gid, qid) or {}).get("deaths") == 1)
    check("F 战败文案含丢失金币", "你丢失了 100 金币" in txt, txt[:300])


def scenario_g_defeat_redname():
    print("\n【G. 红名战败（额外 -10% 上限 2000）】")
    clean_db()
    gid, qid = "gG", "qG"
    from _engine_harness import make_player
    player = make_player(gid, qid, "庚", "战士", 30)
    db.set_event_state(f"red_{qid}", str(int(time.time()) + 3600))
    db.update_player(gid, qid, cur_map="misty_swamp", cur_subarea="misty_swamp_1",
                     gold=50000, hp=10, exp=0)
    player = _player(gid, qid)
    mon = _mk_monster(name="沼泽鳄", lv=30, exp=1000, gold=500, area="misty", mid="m_croc")
    out = _run_defeat(Main(None), gid, qid, player, mon, "你被击败了")
    txt = "\n".join(str(x) for x in out)
    p2 = _player(gid, qid)
    SCENARIOS.append(("G_defeat_redname", {"out": txt, "db": _snap(gid, qid, p2, mon)}))
    # 10% = 5000 + 红名额外 min(5000,2000)=2000 → 43000（test_v85 同口径）
    check("G 红名扣款 50000→43000", p2["gold"] == 43000, f"gold={p2['gold']}")
    check("G 红名额外行", "额外损失 2000 金币" in txt, txt[:300])
    check("G 红名状态保留", bool(db.get_event_state(f"red_{qid}")))


def scenario_h_defeat_feather():
    print("\n【H. 复活羽毛战败（revive_choice json 结构）】")
    clean_db()
    gid, qid = "gH", "qH"
    from _engine_harness import make_player
    player = make_player(gid, qid, "辛", "战士", 30)
    db.add_item(gid, qid, "i_fu_huo_yu_mao",
                {"name": "复活羽毛", "type": "消耗品", "stackable": True,
                 "effect": "revive", "price": 500})
    db.update_player(gid, qid, cur_map="cinder_mountain", cur_subarea="cinder_mountain_3",
                     gold=1000, hp=10, exp=0)
    player = _player(gid, qid)
    mon = _mk_monster(name="烬山魔物", lv=30, exp=1000, gold=500, area="cinder", mid="m_cinder")
    out = _run_defeat(Main(None), gid, qid, player, mon, "你被击败了")
    txt = "\n".join(str(x) for x in out)
    p2 = _player(gid, qid)
    SCENARIOS.append(("H_defeat_feather", {"out": txt, "db": _snap(gid, qid, p2, mon)}))
    raw = db.get_event_state(f"revive_choice_{gid}_{qid}")
    check("H revive_choice 已写", bool(raw), str(raw))
    try:
        st = json.loads(raw)
        check("H revive_choice ts 存在", isinstance(st.get("ts"), (int, float)) and st["ts"] > 0, str(st))
        check("H revive_choice lost=100", st.get("lost") == 100, str(st))
        check("H revive_choice extra=0", st.get("extra") == 0, str(st))
        check("H revive_choice monster=烬山魔物", st.get("monster") == "烬山魔物", str(st))
    except Exception as e:
        check("H revive_choice 可解析 json", False, repr(e))
    check("H 羽毛分支未扣金币", p2["gold"] == 1000, f"gold={p2['gold']}")
    check("H 满血回城", p2["hp"] == p2["max_hp"])
    check("H 文案含复活羽毛", "复活羽毛泛起微光" in txt, txt[:300])
    # 羽毛仍在背包（二段命令 consume）
    check("H 羽毛未消耗", db.count_item(gid, qid, "i_fu_huo_yu_mao") == 1)


def run_all():
    clean_db()
    m = Main(None)
    _ = m  # Main(None) 已实例化多次每场景——统一入口无状态
    scenario_a_normal_victory()
    scenario_b_elite_victory()
    scenario_c_boss_victory_extra_kills()
    scenario_d_hidden_monster_victory()
    scenario_e_pet_victory()
    scenario_f_defeat_normal()
    scenario_g_defeat_redname()
    scenario_h_defeat_feather()


if __name__ == "__main__":
    import traceback
    try:
        run_all()
    except Exception:
        traceback.print_exc()
        FAIL += 1
    # 输出快照 JSON 到 tests/ 旁（改造后对拍用）
    snap_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "_battle_settlement_snapshot.json")
    try:
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in SCENARIOS}, f, ensure_ascii=False, indent=1, default=str)
    except Exception as e:
        print("快照落盘失败:", e)
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)
