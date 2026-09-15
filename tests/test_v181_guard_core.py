# -*- coding: utf-8 -*-
"""v181 拳师「磐核」线测试——资源攒取 + 消耗兑现 + 磐石行者线 4 被动 + 守御姿态。

设计权威 = docs/CLASS_MECHANICS_v153.md L909-918（磐核定义）/ L985-1017（拳师 B 线技能表）。
声明源 = game/data/battle_rules.py（EFFECT_RULES guard_core/guard_stance、EFFECT_ACTIONS、
MECH_CASH guard_core_burst、PASSIVE_PROC core_*）；技能数据 = game/data/skills.py
（BRANCH_SKILLS["cls_wu_seng"]["磐石行者"]）。

★ 走真实契约：load_game_defaults（真声明表）+ apply_class_mech（真装配）+ fire()（真事件总线）。

覆盖：
  1. 声明表落地（EFFECT_RULES/EFFECT_ACTIONS/MECH_CASH/PASSIVE_PROC）
  2. 装配（真 cls_wu_seng 技能 → 三来源渠道 + 资源减伤 + 4 被动 + 守御姿态）= 归属过滤
  3. 三来源攒取：skill_hit +1（无条件）/ 姿态下受击 +1 / 非姿态受击不攒 / 姿态下每刻 +0.4（按 dt 缩放）
  4. cap 5 封顶 + 战斗内不衰减（无 period 声明）
  5. 消耗：guard_core_burst 清核 + ×(1+0.7n)（含小数核保真）
  6. 4 被动：core_full / core_reduce / core_last_stand / core_overflow 各正反例
  7. 守御姿态效果（受伤 −25% 乘区）
  8. 磐岩甲 res_cost（消耗 3 核 → 引擎前置拦截）

跑法：python tests/test_v181_guard_core.py（exit=0 全绿）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_v181_guard_core.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine import effects as EFX  # noqa: E402
from saintess_engine.battle.effect_triggers import fire  # noqa: E402
from content.mech import class_mech as CM  # noqa: E402
from content.mech.params import EFFECT_RULES, EFFECT_ACTIONS  # noqa: E402
from content.mech.class_data import MECH_CASH  # noqa: E402
# B16 收口：宿主 game/data 已删 —— PASSIVE_PROC 真源 = 包内 content/rules/passive_proc.json（42 条，逐值等）
from content.mech.class_mech import _passive_proc_rules  # noqa: E402
PASSIVE_PROC = _passive_proc_rules()
from content.skills import skill_info

PASS = 0
FAIL = 0
FAILURES = []

MONK = "cls_wu_seng"
OTHER = "cls_zhan_shi"
EPS = 1e-6


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ❌ {name} {detail}")


def near(a, b, tol=EPS):
    try:
        return abs(float(a) - float(b)) <= tol
    except Exception:
        return False


# ---------- actor / battle 构造 ----------

def mk_player(learned, cls=MONK, level=99, hp=3000, max_hp=3000):
    return make_actor(uid="p1", name="拳师", side="player", kind="player",
                      human_controlled=True, class_name=cls, level=level,
                      hp=hp, max_hp=max_hp, mp=300, max_mp=300,
                      atk=100, matk=50, spd=10, crit=0.0,
                      equipment={}, skills=[], learned_skills=list(learned),
                      race=None, evolve_path=0, class_tier=0, attributes={},
                      **{"def": 40, "mdef": 30})


def mk_enemy(hp=99999):
    e = make_actor(uid="e1", name="木桩怪", side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=1, matk=1, spd=5, crit=0.0,
                   level=20, **{"def": 0, "mdef": 0})
    e["dodge"] = 0.0
    return e


def mk(learned, cls=MONK):
    """建战斗 + 真装配的玩家（apply_class_mech = 渠道 + 被动 + mech 全链）。"""
    p = mk_player(learned, cls=cls)
    e = mk_enemy()
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    CM.apply_class_mech(p)
    return b, p, e


# ---------- 探针 ----------

def trigs(a, ev):
    return [t for t in ((a.get("triggers") or {}).get(ev) or []) if isinstance(t, dict)]


def find(a, ev, pred):
    for t in trigs(a, ev):
        if pred(t):
            return t
    return None


def st(a, key):
    e = (a.get("effects") or {}).get(key)
    return float(e.get("stacks", 0) or 0) if isinstance(e, dict) else 0.0


def set_st(a, key, v):
    a.setdefault("effects", {})[key] = {"stacks": v, "expire": None}


def enter_stance(a, on=True):
    ef = a.setdefault("effects", {})
    if on:
        ef["guard_stance"] = {"stacks": 1, "expire": 999.0}
    else:
        ef.pop("guard_stance", None)


def strip_base_reduce(a):
    """移除「磐核资源固有每核减伤」装配条目（label=磐核）——隔离单个被动贡献（base 另测）。

    注意：core_reduce（大地之肤）同为 per_core 形态，靠 label 区分（其 label=技能名）。
    """
    ct = (a.get("triggers") or {}).get("taken_calc") or []
    a["triggers"]["taken_calc"] = [
        t for t in ct
        if not (isinstance(t, dict)
                and (t.get("judge") or {}).get("kind") == "per_core"
                and (t.get("judge") or {}).get("res") == "guard_core"
                and t.get("label") == "磐核")]


def dmg_mult(b, actor, info=None, dmg=100, target=None):
    logs = []
    fire(b, "dmg_calc", {"actor": actor, "target": target or actor, "info": info or {},
                         "dmg": dmg, "mult": 1.0}, logs)
    return float((getattr(b, "_fire_ctx", {}) or {}).get("mult", 1.0) or 1.0)


def taken_mult(b, actor, dmg=100, source=None):
    logs = []
    fire(b, "taken_calc", {"actor": actor, "target": actor, "source": source,
                           "dmg": dmg, "mult": 1.0}, logs)
    return float((getattr(b, "_fire_ctx", {}) or {}).get("mult", 1.0) or 1.0)


def fire_ev(b, ev, ctx):
    logs = []
    fire(b, ev, ctx, logs)
    return logs


# ---------- 1. 声明表 ----------

def t1_declarations():
    print("【1. 声明表落地（v153 L909-918 / L985-1017）】")
    gc = EFFECT_RULES.get("guard_core") or {}
    check("EFFECT_RULES.guard_core 存在", bool(gc))
    check("name=磐核 / cap=5", gc.get("name") == "磐核" and gc.get("cap") == 5, str(gc)[:160])
    check("start_classes=[cls_wu_seng]（归属过滤声明）",
          gc.get("start_classes") == [MONK], str(gc.get("start_classes")))
    ch = gc.get("channels") or {}
    check("三来源渠道齐（skill_hit/taken/tick）",
          set(ch.keys()) == {"skill_hit", "taken", "tick"}, str(ch.keys()))
    check("skill_hit = 1（无条件简写）", ch.get("skill_hit") == 1, str(ch.get("skill_hit")))
    tk = ch.get("taken") or {}
    check("taken = {gain 1, when has_effect guard_stance}",
          tk.get("gain") == 1 and tk.get("when") == [{"judge": {"kind": "has_effect",
                                                              "key": "guard_stance"}}],
          str(tk))
    ti = ch.get("tick") or {}
    check("tick = {gain 0.4, per_dt True, 姿态门控}",
          near(ti.get("gain"), 0.4) and ti.get("per_dt") is True
          and (ti.get("when") or [{}])[0].get("judge") == {"kind": "has_effect",
                                                          "key": "guard_stance"},
          str(ti))
    check("guard_core 无 period（战斗中不衰减——v153 L916）", "period" not in gc, str(gc.keys()))
    st_cfg = EFFECT_RULES.get("guard_stance") or {}
    check("EFFECT_RULES.guard_stance 受伤 −25%（stat_scale.reduce）",
          near((st_cfg.get("stat_scale") or {}).get("reduce"), 0.25), str(st_cfg))
    check("EFFECT_ACTIONS.guard_stance → class_guard_stance_enter",
          EFFECT_ACTIONS.get("guard_stance") == [{"action": "class_guard_stance_enter"}],
          str(EFFECT_ACTIONS.get("guard_stance")))
    mb = MECH_CASH.get("guard_core_burst") or {}
    check("MECH_CASH.guard_core_burst（dmg_mult_clear / key guard_core / 0.7 / clear）",
          mb.get("mode") == "dmg_mult_clear" and mb.get("key") == "guard_core"
          and near(mb.get("per_layer"), 0.7) and mb.get("clear") is True, str(mb))
    for proc, ev, act in (("core_full", "taken_calc", "passive_taken_reduce"),
                          ("core_reduce", "taken_calc", "passive_taken_reduce"),
                          ("core_last_stand", "on_taken", "passive_low_hp_core"),
                          ("core_overflow", "taken_calc", "passive_overflow_shield")):
        c = PASSIVE_PROC.get(proc) or {}
        check(f"PASSIVE_PROC.{proc} = {ev}/{act}",
              c.get("event") == ev and c.get("action") == act, str(c)[:160])
    check("core_full 双通道（免控 also 段）", len(PASSIVE_PROC["core_full"].get("also") or []) == 3,
          str(PASSIVE_PROC["core_full"].get("also")))


# ---------- 2. 装配 + 归属过滤 ----------

def t2_assembly():
    print("【2. 装配（真技能 → 渠道/被动/mech）+ 归属过滤】")
    b, p, e = mk(["守御姿态", "磐岩释能", "磐石之躯", "大地之肤", "磐石之心", "不动如山"])
    g1 = find(p, "skill_hit", lambda t: t.get("res") == "guard_core")
    check("skill_hit 渠道装配（+1，无 when）",
          bool(g1) and near(g1.get("gain"), 1) and "when" not in g1, str(g1))
    g2 = find(p, "on_taken", lambda t: t.get("res") == "guard_core")
    check("on_taken 渠道装配（+1，姿态 when）",
          bool(g2) and near(g2.get("gain"), 1) and bool(g2.get("when")), str(g2))
    g3 = find(p, "time_advance", lambda t: t.get("res") == "guard_core")
    check("time_advance(tick) 渠道装配（+0.4，per_dt，姿态 when）",
          bool(g3) and near(g3.get("gain"), 0.4) and g3.get("per_dt") is True
          and bool(g3.get("when")), str(g3))
    pr = find(p, "taken_calc", lambda t: (t.get("judge") or {}).get("kind") == "per_core"
              and (t.get("judge") or {}).get("res") == "guard_core"
              and near(t.get("per_core"), 0.03))
    check("资源固有每核减伤装配（per_core 0.03 → taken_calc）", bool(pr), str(pr))
    check("core_full 减伤段装配（res_ge guard_core stacks=5 + reduce 0.20）",
          bool(find(p, "taken_calc", lambda t: (t.get("judge") or {}).get("kind") == "res_ge"
                    and (t.get("judge") or {}).get("res") == "guard_core"
                    and near(t.get("reduce"), 0.20))), str(trigs(p, "taken_calc"))[:200])
    check("core_full 免控段装配（turn_start ×3 ctrl）",
          len([t for t in trigs(p, "turn_start")
               if (t.get("type") or t.get("action")) == "passive_cc_clear"]) == 3,
          str(trigs(p, "turn_start")))
    check("core_last_stand 触发段装配（on_taken → passive_low_hp_core + used_key）",
          bool(find(p, "on_taken", lambda t: (t.get("type") or t.get("action")) == "passive_low_hp_core"
                    and t.get("used_key") == "_core_last_stand_used")),
          str(trigs(p, "on_taken")))
    check("core_last_stand 常驻段装配（taken_calc has_effect flag + reduce 0.40）",
          bool(find(p, "taken_calc", lambda t: (t.get("judge") or {}).get("kind") == "has_effect"
                    and (t.get("judge") or {}).get("key") == "_core_last_stand_used"
                    and near(t.get("reduce"), 0.40))), str(trigs(p, "taken_calc"))[:200])
    check("core_overflow 装配（shield_pct 0.80 / turns 3）",
          bool(find(p, "taken_calc", lambda t: (t.get("type") or t.get("action")) == "passive_overflow_shield"
                    and near(t.get("shield_pct"), 0.80) and t.get("turns") == 3)),
          str(trigs(p, "taken_calc"))[:200])
    dm = find(p, "dmg_calc", lambda t: (t.get("type") or t.get("action")) == "mech_cash_dmg_mult"
              and t.get("mech") == "guard_core_burst")
    check("guard_core_burst dmg_calc 乘区装配（per_layer 0.7）",
          bool(dm) and near(dm.get("per_layer"), 0.7), str(dm))
    check("guard_core_burst skill_hit 清层装配",
          bool(find(p, "skill_hit", lambda t: (t.get("type") or t.get("action")) == "mech_cash_clear"
                    and t.get("mech") == "guard_core_burst")), str(trigs(p, "skill_hit")))
    # 归属过滤：非拳师（同技能名）不装配
    b2, p2, e2 = mk(["守御姿态", "磐岩释能", "磐石之躯"], cls=OTHER)
    check("非拳师 → 无 guard_core 渠道（skill_hit/on_taken/time_advance）",
          find(p2, "skill_hit", lambda t: t.get("res") == "guard_core") is None
          and find(p2, "on_taken", lambda t: t.get("res") == "guard_core") is None
          and find(p2, "time_advance", lambda t: t.get("res") == "guard_core") is None,
          str(p2.get("triggers")))
    check("非拳师 → 无资源固有每核减伤条目",
          find(p2, "taken_calc", lambda t: (t.get("judge") or {}).get("kind") == "per_core"
               and (t.get("judge") or {}).get("res") == "guard_core") is None,
          str(trigs(p2, "taken_calc")))


# ---------- 3. 三来源攒取 ----------

def t3_sources():
    print("【3. 三来源攒取（v153 L913）】")
    b, p, e = mk(["守御姿态"])
    # ① 守线技能命中 +1（无条件——无需姿态）
    fire_ev(b, "skill_hit", {"actor": p, "target": e, "info": {}})
    check("无姿态：技能命中 +1（无条件）", near(st(p, "guard_core"), 1), f"{st(p,'guard_core')}")
    fire_ev(b, "skill_hit", {"actor": p, "target": e, "info": {}})
    check("连续命中再 +1", near(st(p, "guard_core"), 2), f"{st(p,'guard_core')}")
    # ② 姿态下受击 +1；非姿态受击不攒
    set_st(p, "guard_core", 0)
    fire_ev(b, "on_taken", {"actor": p, "target": p, "source": None, "dmg": 50})
    check("非姿态受击 → 不攒", near(st(p, "guard_core"), 0), f"{st(p,'guard_core')}")
    enter_stance(p)
    fire_ev(b, "on_taken", {"actor": p, "target": p, "source": None, "dmg": 50})
    check("姿态下受击 → +1", near(st(p, "guard_core"), 1), f"{st(p,'guard_core')}")
    # ③ 姿态下每刻 +0.4（按 dt 缩放）
    set_st(p, "guard_core", 0)
    fire_ev(b, "time_advance", {"dt": 1.0, "now": 0.0})
    check("姿态下每刻 dt=1.0 → +0.4", near(st(p, "guard_core"), 0.4), f"{st(p,'guard_core')}")
    fire_ev(b, "time_advance", {"dt": 0.5, "now": 0.5})
    check("dt=0.5 → +0.2（按 dt 缩放）", near(st(p, "guard_core"), 0.6), f"{st(p,'guard_core')}")
    fire_ev(b, "time_advance", {"dt": 2.0, "now": 2.5})
    check("dt=2.0 → +0.8（按 dt 缩放）", near(st(p, "guard_core"), 1.4), f"{st(p,'guard_core')}")
    enter_stance(p, False)
    fire_ev(b, "time_advance", {"dt": 1.0, "now": 3.5})
    check("无姿态每刻 → 不攒", near(st(p, "guard_core"), 1.4), f"{st(p,'guard_core')}")


# ---------- 4. cap + 不衰减 ----------

def t4_cap_no_decay():
    print("【4. cap 5 封顶 + 战斗内不衰减】")
    b, p, e = mk(["守御姿态"])
    enter_stance(p)
    for _ in range(16):
        fire_ev(b, "time_advance", {"dt": 1.0, "now": 0.0})
    check("每刻连攒 → cap 5 封顶", near(st(p, "guard_core"), 5), f"{st(p,'guard_core')}")
    fire_ev(b, "skill_hit", {"actor": p, "target": e, "info": {}})
    check("满核后技能命中仍不超 cap", near(st(p, "guard_core"), 5), f"{st(p,'guard_core')}")
    set_st(p, "guard_core", 3.4)
    for _ in range(20):
        fire_ev(b, "time_advance", {"dt": 1.0, "now": 0.0})
    check("无 period → 战斗内无衰减（3.4 + 每刻 → 5 而非衰减）",
          near(st(p, "guard_core"), 5), f"{st(p,'guard_core')}")


# ---------- 5. 消耗兑现 ----------

def t5_burst():
    print("【5. 磐核消耗兑现（guard_core_burst：×(1+0.7n) + 清层）】")
    b, p, e = mk(["磐岩释能"])
    info = {"mech": "guard_core_burst"}
    set_st(p, "guard_core", 0)
    check("0 核 → 无乘区（×1.0）", near(dmg_mult(b, p, info=info, target=e), 1.0),
          f"{dmg_mult(b, p, info=info, target=e)}")
    set_st(p, "guard_core", 3)
    check("3 核 → ×(1+0.7×3)=×3.10", near(dmg_mult(b, p, info=info, target=e), 3.10),
          f"{dmg_mult(b, p, info=info, target=e)}")
    set_st(p, "guard_core", 5)
    check("满 5 核 → ×4.50（v153 L917）", near(dmg_mult(b, p, info=info, target=e), 4.50),
          f"{dmg_mult(b, p, info=info, target=e)}")
    set_st(p, "guard_core", 3.4)
    check("小数核保真 → ×(1+0.7×3.4)=×3.38（int 截断会得 3.10）",
          near(dmg_mult(b, p, info=info, target=e), 3.38),
          f"{dmg_mult(b, p, info=info, target=e)}")
    check("非本 mech 技能不吃乘区（info.mech 不匹配）",
          near(dmg_mult(b, p, info={"mech": "other"}, target=e), 1.0),
          f"{dmg_mult(b, p, info={'mech': 'other'}, target=e)}")
    # 清层（skill_hit）
    set_st(p, "guard_core", 3)
    fire_ev(b, "skill_hit", {"actor": p, "target": e, "info": info})
    check("命中后磐核清零（消耗全部）", near(st(p, "guard_core"), 0), f"{st(p,'guard_core')}")


# ---------- 6. 被动 ----------

def t6_core_full():
    print("【6. 磐石之躯 core_full：满 5 → 减伤 +20% + 免控（v153 L1013）】")
    b, p, e = mk(["磐石之躯"])
    strip_base_reduce(p)
    set_st(p, "guard_core", 4)
    check("4 核（未满）→ 无减伤", near(taken_mult(b, p, source=e), 1.0),
          f"{taken_mult(b, p, source=e)}")
    set_st(p, "guard_core", 5)
    check("满 5 核 → 减伤 20%（×0.80）", near(taken_mult(b, p, source=e), 0.80),
          f"{taken_mult(b, p, source=e)}")
    # 免控段：turn_start 清 skip 控制
    p["effects"]["stun"] = {"mode": "skip", "expire": None}
    fire_ev(b, "turn_start", {"actor": p})
    check("满 5 核 → 眩晕被清（等效免控）", "stun" not in (p.get("effects") or {}),
          str(p.get("effects")))
    set_st(p, "guard_core", 4)
    p["effects"]["stun"] = {"mode": "skip", "expire": None}
    fire_ev(b, "turn_start", {"actor": p})
    check("未满 5 核 → 眩晕保留", isinstance((p.get("effects") or {}).get("stun"), dict),
          str(p.get("effects")))


def t7_core_reduce():
    print("【7. 大地之肤 core_reduce：每核额外减伤 +2%（v153 L1006，per_core）】")
    b, p, e = mk(["大地之肤"])
    strip_base_reduce(p)
    set_st(p, "guard_core", 0)
    check("0 核 → 无减伤", near(taken_mult(b, p, source=e), 1.0), f"{taken_mult(b, p, source=e)}")
    set_st(p, "guard_core", 3)
    check("3 核 → 减伤 6%（×0.94）", near(taken_mult(b, p, source=e), 0.94),
          f"{taken_mult(b, p, source=e)}")
    set_st(p, "guard_core", 3.5)
    check("小数核 3.5 → 减伤 7%（×0.93，float 保真）",
          near(taken_mult(b, p, source=e), 0.93), f"{taken_mult(b, p, source=e)}")


def t8_core_last_stand():
    print("【8. 不动如山 core_last_stand：生命 <30% → +3 核 + 减伤 40%（每场 1 次，v153 L1016）】")
    b, p, e = mk(["不动如山"])
    strip_base_reduce(p)
    p["hp"] = int(p["max_hp"] * 0.35)
    fire_ev(b, "on_taken", {"actor": p, "target": p, "source": e, "dmg": 10})
    check("生命 ≥30% → 不触发（无核）", near(st(p, "guard_core"), 0), f"{st(p,'guard_core')}")
    check("生命 ≥30% → 无减伤", near(taken_mult(b, p, source=e), 1.0), f"{taken_mult(b, p, source=e)}")
    p["hp"] = int(p["max_hp"] * 0.25)
    fire_ev(b, "on_taken", {"actor": p, "target": p, "source": e, "dmg": 10})
    check("生命 <30% → 获得 3 枚磐核", near(st(p, "guard_core"), 3), f"{st(p,'guard_core')}")
    check("触发后一次性 flag 置位",
          isinstance((p.get("effects") or {}).get("_core_last_stand_used"), dict),
          str(p.get("effects")))
    fire_ev(b, "on_taken", {"actor": p, "target": p, "source": e, "dmg": 10})
    check("每场 1 次：再受击不叠加（仍 3 核）", near(st(p, "guard_core"), 3), f"{st(p,'guard_core')}")
    check("触发后常驻减伤 40%（×0.60）", near(taken_mult(b, p, source=e), 0.60),
          f"{taken_mult(b, p, source=e)}")


def t9_core_overflow():
    print("【9. 磐石之心 core_overflow：磐核 ≥3 → 承伤转盾（v153 L1002）】")
    b, p, e = mk(["磐石之心"])
    strip_base_reduce(p)
    set_st(p, "guard_core", 2)
    fire_ev(b, "taken_calc", {"actor": p, "target": p, "source": e, "dmg": 200, "mult": 1.0})
    check("2 核（<3）→ 无护盾", not (p.get("shields") or {}), str(p.get("shields")))
    set_st(p, "guard_core", 3)
    fire_ev(b, "taken_calc", {"actor": p, "target": p, "source": e, "dmg": 200, "mult": 1.0})
    sh = (p.get("shields") or {}).get("guard_core_overflow") or {}
    check("3 核 → 承伤 ×0.80 转盾（200×0.8=160）", int(sh.get("value", 0) or 0) == 160,
          str(p.get("shields")))
    check("护盾有到期刻（turns 3）", sh.get("expire_at") is not None, str(sh))
    fire_ev(b, "taken_calc", {"actor": p, "target": p, "source": e, "dmg": 100, "mult": 1.0})
    sh2 = (p.get("shields") or {}).get("guard_core_overflow") or {}
    check("再承伤叠加护盾（160+80=240）", int(sh2.get("value", 0) or 0) == 240, str(sh2))


# ---------- 7. 守御姿态 ----------

def t10_stance():
    print("【10. 守御姿态效果（受伤 −25% → taken_calc 乘区，v153 L992）】")
    b, p, e = mk(["守御姿态"])
    logs = []
    EFX.apply_effects(b, p, p, [{"type": "guard_stance", "turns": 8}], logs)
    gs = (p.get("effects") or {}).get("guard_stance")
    check("施放守御姿态 → 态进（expire = now+8）",
          isinstance(gs, dict) and near(gs.get("expire"), 8.0), str(gs))
    check("态进日志", any("守御姿态" in str(x) for x in logs), str(logs))
    tg = find(p, "taken_calc", lambda t: (t.get("judge") or {}).get("kind") == "has_effect"
              and (t.get("judge") or {}).get("key") == "guard_stance")
    check("挂受击减伤乘区（has_effect guard_stance / reduce 0.25）",
          bool(tg) and near(tg.get("reduce"), 0.25), str(tg))
    check("姿态中受伤 −25%（×0.75）", near(taken_mult(b, p, source=e), 0.75),
          f"{taken_mult(b, p, source=e)}")
    # 幂等：再施放不重复挂
    EFX.apply_effects(b, p, p, [{"type": "guard_stance", "turns": 8}], logs)
    n = len([t for t in trigs(p, "taken_calc")
             if (t.get("judge") or {}).get("key") == "guard_stance"])
    check("重复施放不重复挂 trigger（幂等）", n == 1, f"n={n}")
    # 无 turns 字段 = 无此行为（零默认值）
    p2 = mk_player(["守御姿态"])
    b2 = B2(btype="monster", sides={"player": [p2], "enemy": [mk_enemy()]})
    CM.apply_class_mech(p2)
    EFX.apply_effects(b2, p2, p2, [{"type": "guard_stance"}], [])
    check("缺 turns 字段 → 不写态（零默认值）",
          "guard_stance" not in (p2.get("effects") or {}), str(p2.get("effects")))
    # 退态后减伤失效（模拟到期被引擎删除）
    (p.get("effects") or {}).pop("guard_stance", None)
    check("退态 → 减伤失效（×1.0）", near(taken_mult(b, p, source=e), 1.0),
          f"{taken_mult(b, p, source=e)}")


# ---------- 8. 磐岩甲 res_cost ----------

def t11_res_cost():
    print("【11. 磐岩甲：消耗 3 枚磐核（res_cost，v153 L1007）】")
    info = skill_info(MONK, "磐岩甲") or {}
    check("技能数据 res_cost = {guard_core: 3}",
          info.get("res_cost") == {"guard_core": 3}, str(info.get("res_cost")))
    from saintess_engine import actions as A
    b, p, e = mk(["磐岩甲"])
    set_st(p, "guard_core", 2)
    check("2 核 → 引擎前置拦截不可施放",
          A._skill_usable(b, p, info, []) is False, str(p.get("effects")))
    set_st(p, "guard_core", 3)
    check("3 核 → 可施放", A._skill_usable(b, p, info, []) is True)
    A._spend_skill_cost(p, info)
    check("施放后扣 3 核 → 0", near(st(p, "guard_core"), 0), f"{st(p,'guard_core')}")


# ---------- 9. 资源固有每核减伤 + 叠加 ----------

def t12_base_and_stack():
    print("【12. 资源固有每核减伤（v153 L915）+ 与大地之肤叠加】")
    b, p, e = mk(["守御姿态"])
    set_st(p, "guard_core", 0)
    check("0 核 → 无减伤", near(taken_mult(b, p, source=e), 1.0), f"{taken_mult(b, p, source=e)}")
    set_st(p, "guard_core", 2)
    check("2 核 → 基础减伤 6%（×0.94）", near(taken_mult(b, p, source=e), 0.94),
          f"{taken_mult(b, p, source=e)}")
    set_st(p, "guard_core", 5)
    check("满 5 核 → 基础减伤 15%（×0.85）", near(taken_mult(b, p, source=e), 0.85),
          f"{taken_mult(b, p, source=e)}")
    b2, p2, e2 = mk(["守御姿态", "大地之肤", "磐石之躯"])
    set_st(p2, "guard_core", 5)
    # 基础 15% + 大地之肤 10% + 磐石之躯 20% → 0.85 × 0.90 × 0.80
    check("满核叠加：基础15% × 大地之肤10% × 磐石之躯20% = ×0.612",
          near(taken_mult(b2, p2, source=e2), 0.85 * 0.90 * 0.80),
          f"{taken_mult(b2, p2, source=e2)}")


def main():
    t1_declarations()
    t2_assembly()
    t3_sources()
    t4_cap_no_decay()
    t5_burst()
    t6_core_full()
    t7_core_reduce()
    t8_core_last_stand()
    t9_core_overflow()
    t10_stance()
    t11_res_cost()
    t12_base_and_stack()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
