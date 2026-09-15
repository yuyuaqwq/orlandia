# -*- coding: utf-8 -*-
"""v181 缺口收尾（P20）：三条真空转被动——破绽感知 / 暗影之心 / 毒刃·共鸣。

三者在旧引擎均为 NO_OLD（无 handler），语义全从技能 desc + passive dict 推：
  shaken_decay_half  破绽感知（武僧）：破绽条衰减减半（desc −1.7/s → −0.85/s）
  lian_duan_soft     暗影之心（影舞者）：断连时只损失 lose 段（desc「而非减半」）
  poison_spread      毒刃·共鸣（毒刃者）：毒爆击杀目标时，毒层扩散至相邻敌人
时间/断连窗/连段 cap 权威 = docs/CLASS_MECHANICS_v153.md §五（1.5 刻未命中断连）/§六（每刻 −1.7）。

覆盖（各被动正反例 + 边界）：
  1. 装配：学什么挂什么（三条各挂对应事件）/ 未学零噪音
  2. 破绽感知：宿主自结算 + 半衰回补（净 −0.85/刻）；无被动对照组全衰 −1.7；无条不动作
  3. 暗影之心：命中记时刻 → 窗内不掉段 / 到窗掉 lose 段 / 掉段后重开窗；缺 lose、连段 0 不动作
  4. 毒刃·共鸣：毒爆击杀 → 前后邻居各得死者毒层数；非毒爆击杀 / 死者无毒 / 记录已清不扩散；
     列表边界（首/末位）/ 邻居已死不扩散 / 目标毒 cap clamp

跑法：python tests/test_v181_gap_tail.py（exit=0 全绿）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_v181_gap_tail.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor, effects as EFX  # noqa: E402
from saintess_engine.battle.effect_triggers import fire  # noqa: E402
from saintess_engine.gauge import bar_effect_key, bar_gain# noqa: E402
from content.mech import class_mech as CMP  # noqa: E402
from content.mech.bar_procs import _ensure_tick  # noqa: E402  ★ B18-REPOINT：直取包内实现本体

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ❌ {name} {detail}")


CLS_WU = "cls_wu_seng"
CLS_CI = "cls_ci_ke"


def mk_player(learned, cls=CLS_CI):
    return make_actor(uid="p1", name="刺客", side="player", kind="player",
                      human_controlled=True, class_name=cls, level=99,
                      hp=3000, max_hp=3000, mp=300, max_mp=300,
                      atk=100, matk=80, spd=20, crit=0.0,
                      equipment={}, skills=[], learned_skills=list(learned),
                      **{"def": 40, "mdef": 30})


def mk_enemy(uid="e1", hp=9999):
    e = make_actor(uid=uid, name=f"木桩-{uid}", side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=1, matk=1, spd=5, crit=0.0,
                   level=20, **{"def": 0, "mdef": 0})
    e["dodge"] = 0.0
    return e


def new_battle(p, enemies):
    return B2(btype="monster", sides={"player": [p], "enemy": list(enemies)})


def trigs(actor, ev, action):
    return [t for t in ((actor.get("triggers") or {}).get(ev) or [])
            if isinstance(t, dict) and (t.get("type") or t.get("action")) == action]


def st(actor, key):
    e = (actor.get("effects") or {}).get(key)
    return float(e.get("stacks", 0) or 0) if isinstance(e, dict) else 0.0


def bar_val(host, key="shaken"):
    return float(((host.get("effects") or {}).get(bar_effect_key(key)) or {}).get("val", 0.0) or 0.0)


def advance(b, dt):
    """真实时钟推进：schedule._advance_time（广播 time_advance，ctx dt/now）。"""
    from saintess_engine.battle.schedule import _advance_time
    logs = []
    _advance_time(b, dt, logs)
    return logs


# ============================================================
# 1. 装配
# ============================================================

def test_1_assembly():
    print("【1. 装配：学什么挂什么 / 未学零噪音】")
    p = mk_player(["钢拳", "破绽感知"], CLS_WU)
    CMP.apply_class_mech(p)
    t = trigs(p, "time_advance", "passive_bar_decay_half")
    check("破绽感知 → time_advance 挂 1 条", len(t) == 1, f"trigs={t}")
    check("条名由声明给（judge.bar=shaken）",
          t and (t[0].get("judge") or {}).get("bar") == "shaken", f"trigs={t}")
    check("label 来自技能名", t and t[0].get("label") == "破绽感知", f"trigs={t}")

    p2 = mk_player(["刺击", "暗影之心"], CLS_CI)
    CMP.apply_class_mech(p2)
    for ev in ("time_advance", "skill_hit", "attack_hit"):
        check(f"暗影之心 → {ev} 挂断连动作", len(trigs(p2, ev, "passive_lian_duan_soft")) == 1,
              f"trigs={trigs(p2, ev, 'passive_lian_duan_soft')}")
    lt = trigs(p2, "time_advance", "passive_lian_duan_soft")
    check("res/gap 由声明给（lian_duan / 1.5）",
          lt and lt[0].get("res") == "lian_duan" and abs(float(lt[0].get("gap") or 0) - 1.5) < 1e-9,
          f"trigs={lt}")
    check("lose 来自 passive dict（1）",
          lt and abs(float(lt[0].get("lose") or 0) - 1) < 1e-9, f"trigs={lt}")

    p3 = mk_player(["刺击", "毒刃·共鸣"], CLS_CI)
    CMP.apply_class_mech(p3)
    for ev in ("on_kill", "act_cast", "act_done"):
        check(f"毒刃·共鸣 → {ev} 挂扩散动作", len(trigs(p3, ev, "passive_poison_spread")) == 1,
              f"trigs={trigs(p3, ev, 'passive_poison_spread')}")
    kt = trigs(p3, "on_kill", "passive_poison_spread")
    check("扩散 key=poison（judge）", kt and (kt[0].get("judge") or {}).get("key") == "poison",
          f"trigs={kt}")
    check("毒爆限定前缀 mech_prefix=poison_burst",
          kt and kt[0].get("mech_prefix") == "poison_burst", f"trigs={kt}")

    # 反向：未学 → 零噪音（本批三条动作都不挂；武僧固有 guard_core 减伤段不属本批）
    _NEW_ACTS = ("passive_bar_decay_half", "passive_lian_duan_soft", "passive_poison_spread")
    for cls, learned in ((CLS_WU, ["钢拳"]), (CLS_CI, ["刺击"])):
        q = mk_player(learned, cls)
        CMP.apply_class_mech(q)
        tg = q.get("triggers") or {}
        acts = [x.get("type") for v in tg.values() for x in v
                if isinstance(x, dict) and x.get("type") in _NEW_ACTS]
        check(f"未学被动（{cls}）→ 本批零触发器", not acts, f"acts={acts}")


# ============================================================
# 2. 破绽感知（shaken_decay_half）
# ============================================================

def prep_bar(e, val=10.0):
    """宿主挂条 + 自安装时钟订阅（真实装配路径）。"""
    bar_gain(e, "shaken", val, [], now=0.0)
    _ensure_tick(e)


def test_2_shaken_decay_half():
    print("【2. 破绽感知：衰减减半（−1.7 → −0.85/刻）】")
    # 有被动：两刻推进 → 10 − 3.4 + 1.7 = 8.3
    p = mk_player(["钢拳", "破绽感知"], CLS_WU)
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = new_battle(p, [e])
    prep_bar(e, 10.0)
    logs = advance(b, 2.0)
    check("半衰：10 → 8.3（2 刻 × 0.85）",
          abs(bar_val(e) - 8.3) < 1e-9, f"val={bar_val(e)} logs={logs}")
    check("半衰日志（含技能名）",
          any("破绽衰减减半" in str(x) and "破绽感知" in str(x) for x in logs), f"logs={logs}")

    # 对照组（无被动）：宿主自带 bar_time_settle 全量衰减 → 10 − 3.4 = 6.6
    p2 = mk_player(["钢拳"], CLS_WU)
    CMP.apply_class_mech(p2)
    e2 = mk_enemy()
    b2 = new_battle(p2, [e2])
    prep_bar(e2, 10.0)
    advance(b2, 2.0)
    check("对照组无被动 → 全衰 10 → 6.6",
          abs(bar_val(e2) - 6.6) < 1e-9, f"val={bar_val(e2)}")

    # 边界：从未挂条 → 不动作不崩
    e3 = mk_enemy()
    b3 = new_battle(p, [e3])
    logs3 = advance(b3, 1.0)
    check("无条状态 → 不动作（零噪音）",
          not any("破绽衰减减半" in str(x) for x in logs3), f"logs={logs3}")

    # 边界：val=0 → 不回补（不产生负值/虚增）
    e4 = mk_enemy()
    b4 = new_battle(p, [e4])
    prep_bar(e4, 10.0)
    e4["effects"][bar_effect_key("shaken")]["val"] = 0.0
    advance(b4, 1.0)
    check("val=0 → 仍为 0（不回补）", bar_val(e4) == 0.0, f"val={bar_val(e4)}")

    # 边界：条被推满触发后（免疫窗口内）半衰照常按 val 计算，不越 max
    e5 = mk_enemy()
    b5 = new_battle(p, [e5])
    prep_bar(e5, 100.0)
    advance(b5, 1.0)
    check("半衰不超 max(125)", bar_val(e5) < 125.0, f"val={bar_val(e5)}")


# ============================================================
# 3. 暗影之心（lian_duan_soft）
# ============================================================

def test_3_lian_duan_soft():
    print("【3. 暗影之心：断连只损 lose 段（1.5 刻无命中）】")
    p = mk_player(["刺击", "暗影之心"], CLS_CI)
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = new_battle(p, [e])
    p.setdefault("effects", {})["lian_duan"] = {"stacks": 6, "expire": None}
    logs = []
    b._now = 1.0
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"mech": "lian_duan"}}, logs)
    rec = (p.get("effects") or {}).get("_lian_duan_last_hit") or {}
    check("命中记时刻（effects._lian_duan_last_hit.t = 1.0）",
          abs(float(rec.get("t", -1)) - 1.0) < 1e-9, f"rec={rec}")

    # 窗内（1.4 刻）→ 不掉段
    logs = []
    b._now = 2.4
    fire(b, "time_advance", {"dt": 1.4, "now": 2.4}, logs)
    check("1.4 刻未命中 → 连段守恒 6", st(p, "lian_duan") == 6, f"st={st(p,'lian_duan')}")

    # 到窗（1.5 刻）→ 掉 lose 段
    logs = []
    b._now = 2.5
    fire(b, "time_advance", {"dt": 0.1, "now": 2.5}, logs)
    check("1.5 刻未命中 → 连段 6 → 5（只损 1 段）",
          st(p, "lian_duan") == 5, f"st={st(p,'lian_duan')} logs={logs}")
    check("断连日志（含技能名）",
          any("断连只损" in str(x) and "暗影之心" in str(x) for x in logs), f"logs={logs}")
    check("断连后重开窗（记录更新到当刻）",
          abs(float(((p.get('effects') or {}).get('_lian_duan_last_hit') or {}).get('t', -1))
              - 2.5) < 1e-9,
          f"rec={(p.get('effects') or {}).get('_lian_duan_last_hit')}")

    # 下一刻（未再命中）→ 不再连续掉段
    b._now = 3.0
    fire(b, "time_advance", {"dt": 0.5, "now": 3.0}, [])
    check("重开窗后 0.5 刻 → 不再掉段", st(p, "lian_duan") == 5, f"st={st(p,'lian_duan')}")

    # 再次命中 → 窗重置（3.0 命中后 1.4 刻不掉）
    fire(b, "attack_hit", {"actor": p, "target": e, "info": {"_basic": True}}, [])
    b._now = 4.4
    fire(b, "time_advance", {"dt": 1.4, "now": 4.4}, [])
    check("普攻命中重置窗 → 1.4 刻不掉段", st(p, "lian_duan") == 5, f"st={st(p,'lian_duan')}")

    # 反例：连段 0 → 不动作
    p2 = mk_player(["刺击", "暗影之心"], CLS_CI)
    CMP.apply_class_mech(p2)
    e2 = mk_enemy()
    b2 = new_battle(p2, [e2])
    b2._now = 1.0
    fire(b2, "skill_hit", {"actor": p2, "target": e2, "info": {}}, [])
    b2._now = 3.0
    logs2 = []
    fire(b2, "time_advance", {"dt": 2.0, "now": 3.0}, logs2)
    check("连段 0 → 不动作（无日志）",
          st(p2, "lian_duan") == 0 and not any("断连只损" in str(x) for x in logs2),
          f"st={st(p2,'lian_duan')} logs={logs2}")

    # 反例：从未命中 → 无断连判据
    p3 = mk_player(["刺击", "暗影之心"], CLS_CI)
    CMP.apply_class_mech(p3)
    e3 = mk_enemy()
    b3 = new_battle(p3, [e3])
    p3.setdefault("effects", {})["lian_duan"] = {"stacks": 4, "expire": None}
    b3._now = 9.0
    fire(b3, "time_advance", {"dt": 9.0, "now": 9.0}, [])
    check("从未命中 → 不掉段（不臆造起点）", st(p3, "lian_duan") == 4, f"st={st(p3,'lian_duan')}")

    # 反例：缺 lose 字段 → 无此行为（零默认值）
    q = trigs(p, "time_advance", "passive_lian_duan_soft")[0]
    params = dict(q)
    params.pop("lose", None)
    params["_owner"] = p
    b._now = 20.0
    logs4 = []
    EFX.ACTION_HANDLERS["passive_lian_duan_soft"](b, p, e, params, logs4)
    check("缺 lose 字段 → 无此行为", st(p, "lian_duan") == 5, f"st={st(p,'lian_duan')}")

    # 缺口登记：基础断连段（无被动者 1.5 刻 → 减半）saintess_engine 无载体 → 不掉段
    p4 = mk_player(["刺击"], CLS_CI)
    CMP.apply_class_mech(p4)
    e4 = mk_enemy()
    b4 = new_battle(p4, [e4])
    p4.setdefault("effects", {})["lian_duan"] = {"stacks": 6, "expire": None}
    b4._now = 1.0
    fire(b4, "skill_hit", {"actor": p4, "target": e4, "info": {}}, [])
    b4._now = 5.0
    fire(b4, "time_advance", {"dt": 4.0, "now": 5.0}, [])
    check("未学被动 → 基础断连段无载体（缺口：不减半）",
          st(p4, "lian_duan") == 6, f"st={st(p4,'lian_duan')}")


# ============================================================
# 4. 毒刃·共鸣（poison_spread）
# ============================================================

def test_4_poison_spread():
    print("【4. 毒刃·共鸣：毒爆击杀 → 毒层扩散至相邻敌人】")
    p = mk_player(["刺击", "毒刃·共鸣"], CLS_CI)
    CMP.apply_class_mech(p)
    e1, e2, e3 = mk_enemy("e1"), mk_enemy("e2"), mk_enemy("e3")
    b = new_battle(p, [e1, e2, e3])
    e2.setdefault("effects", {})["poison"] = {"stacks": 4, "expire": None}
    logs = []
    fire(b, "act_cast", {"actor": p, "target": e2,
                         "info": {"mech": "poison_burst_finisher"}}, logs)
    check("act_cast 记录本次施放 mech",
          ((p.get("effects") or {}).get("_poison_spread_mech") or {}).get("mech")
          == "poison_burst_finisher",
          f"rec={(p.get('effects') or {}).get('_poison_spread_mech')}")
    fire(b, "on_kill", {"actor": p, "target": e2, "dmg": 999}, logs)
    check("前邻 e1 得毒 4 层", st(e1, "poison") == 4, f"e1={st(e1,'poison')}")
    check("后邻 e3 得毒 4 层", st(e3, "poison") == 4, f"e3={st(e3,'poison')}")
    check("扩散日志（含技能名/层数）",
          any("毒层扩散" in str(x) and "毒刃·共鸣" in str(x) for x in logs), f"logs={logs}")

    # 边界：列表首/末位死者（只有一侧邻居）
    f = mk_player(["刺击", "毒刃·共鸣"], CLS_CI)
    CMP.apply_class_mech(f)
    g1, g2 = mk_enemy("g1"), mk_enemy("g2")
    bg = new_battle(f, [g1, g2])
    g1.setdefault("effects", {})["poison"] = {"stacks": 3, "expire": None}
    fire(bg, "act_cast", {"actor": f, "target": g1, "info": {"mech": "poison_burst"}}, [])
    fire(bg, "on_kill", {"actor": f, "target": g1, "dmg": 1}, [])
    check("首位死者 → 只后邻得毒", st(g2, "poison") == 3, f"g2={st(g2,'poison')}")

    # 边界：邻居已死 → 跳过
    h = mk_player(["刺击", "毒刃·共鸣"], CLS_CI)
    CMP.apply_class_mech(h)
    k1, k2, k3 = mk_enemy("k1"), mk_enemy("k2"), mk_enemy("k3")
    bh = new_battle(h, [k1, k2, k3])
    k2.setdefault("effects", {})["poison"] = {"stacks": 2, "expire": None}
    k3["hp"] = 0
    fire(bh, "act_cast", {"actor": h, "target": k2, "info": {"mech": "poison_burst"}}, [])
    fire(bh, "on_kill", {"actor": h, "target": k2, "dmg": 1}, [])
    check("已死邻居 → 不扩散", st(k1, "poison") == 2 and st(k3, "poison") == 0,
          f"k1={st(k1,'poison')} k3={st(k3,'poison')}")

    # 边界：cap clamp（目标已有 4 层 + 死者 4 层 → 封顶 5）
    m = mk_player(["刺击", "毒刃·共鸣"], CLS_CI)
    CMP.apply_class_mech(m)
    n1, n2 = mk_enemy("n1"), mk_enemy("n2")
    bn = new_battle(m, [n1, n2])
    n2.setdefault("effects", {})["poison"] = {"stacks": 4, "expire": None}
    n1.setdefault("effects", {})["poison"] = {"stacks": 4, "expire": None}
    fire(bn, "act_cast", {"actor": m, "target": n2, "info": {"mech": "poison_burst"}}, [])
    fire(bn, "on_kill", {"actor": m, "target": n2, "dmg": 1}, [])
    check("目标毒 cap(5) clamp", st(n1, "poison") == 5, f"n1={st(n1,'poison')}")

    # 反例：非毒爆击杀（记录 mech 非 poison_burst 前缀）→ 不扩散
    p2 = mk_player(["刺击", "毒刃·共鸣"], CLS_CI)
    CMP.apply_class_mech(p2)
    a1, a2, a3 = mk_enemy("a1"), mk_enemy("a2"), mk_enemy("a3")
    b2 = new_battle(p2, [a1, a2, a3])
    a2.setdefault("effects", {})["poison"] = {"stacks": 3, "expire": None}
    logs2 = []
    fire(b2, "act_cast", {"actor": p2, "target": a2, "info": {"mech": "lian_duan"}}, logs2)
    fire(b2, "on_kill", {"actor": p2, "target": a2, "dmg": 1}, logs2)
    check("非毒爆击杀 → 不扩散",
          st(a1, "poison") == 0 and st(a3, "poison") == 0
          and not any("毒层扩散" in str(x) for x in logs2),
          f"a1={st(a1,'poison')} a3={st(a3,'poison')}")

    # 反例：死者无毒层 → 不扩散
    p3 = mk_player(["刺击", "毒刃·共鸣"], CLS_CI)
    CMP.apply_class_mech(p3)
    c1, c2, c3 = mk_enemy("c1"), mk_enemy("c2"), mk_enemy("c3")
    b3 = new_battle(p3, [c1, c2, c3])
    fire(b3, "act_cast", {"actor": p3, "target": c2, "info": {"mech": "poison_burst"}}, [])
    fire(b3, "on_kill", {"actor": p3, "target": c2, "dmg": 1}, [])
    check("死者无毒层 → 无此行为", st(c1, "poison") == 0 and st(c3, "poison") == 0,
          f"c1={st(c1,'poison')} c3={st(c3,'poison')}")

    # 反例：act_done 已清记录 → 之后的击杀（非本行动）不扩散
    p4 = mk_player(["刺击", "毒刃·共鸣"], CLS_CI)
    CMP.apply_class_mech(p4)
    d1, d2, d3 = mk_enemy("d1"), mk_enemy("d2"), mk_enemy("d3")
    b4 = new_battle(p4, [d1, d2, d3])
    d2.setdefault("effects", {})["poison"] = {"stacks": 3, "expire": None}
    fire(b4, "act_cast", {"actor": p4, "target": d2, "info": {"mech": "poison_burst"}}, [])
    fire(b4, "act_done", {"acted": p4}, [])
    check("act_done 清记录",
          not ((p4.get("effects") or {}).get("_poison_spread_mech")),
          f"rec={(p4.get('effects') or {}).get('_poison_spread_mech')}")
    fire(b4, "on_kill", {"actor": p4, "target": d2, "dmg": 1}, [])
    check("记录已清 → 不扩散", st(d1, "poison") == 0 and st(d3, "poison") == 0,
          f"d1={st(d1,'poison')} d3={st(d3,'poison')}")

    # 反例：非持有者击杀（旁观者无触发器）→ 不扩散
    p5 = mk_player(["刺击", "毒刃·共鸣"], CLS_CI)
    CMP.apply_class_mech(p5)
    e5a, e5b, e5c = mk_enemy("x1"), mk_enemy("x2"), mk_enemy("x3")
    b5 = new_battle(p5, [e5a, e5b, e5c])
    other = mk_player(["刺击"], CLS_CI)
    other["side"] = "player2"
    b5.sides["player2"] = [other]
    CMP.apply_class_mech(other)
    e5b.setdefault("effects", {})["poison"] = {"stacks": 3, "expire": None}
    fire(b5, "act_cast", {"actor": p5, "target": e5b, "info": {"mech": "poison_burst"}}, [])
    fire(b5, "on_kill", {"actor": other, "target": e5b, "dmg": 1}, [])
    check("他人击杀（主体过滤）→ 不扩散",
          st(e5a, "poison") == 0 and st(e5c, "poison") == 0,
          f"x1={st(e5a,'poison')} x3={st(e5c,'poison')}")


def main():
    test_1_assembly()
    test_2_shaken_decay_half()
    test_3_lian_duan_soft()
    test_4_poison_spread()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
