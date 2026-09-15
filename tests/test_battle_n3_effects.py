# -*- coding: utf-8 -*-
"""N3 验收：saintess_engine 效果系统（effects.py）核心行为测试。

覆盖：
- debuff 叠层：burn/bleed/poison 写 target.debuffs（cap）
- 控制：stun/freeze/silence 写 target.buffs
- 资源叠层：zhan_yi/lian_duan/rage/chi 写 caster
- 攻击命中附加 mech 效果（挥砍 zhan_yi、带 burn 技能）
- 增益 effect 走单表（reduce/atk_up/shield_self/cleanse）

跑法：python tests/test_battle_n3_effects.py
"""
import os
import sys
import random

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
TEST_DB = os.path.join(PLUGIN_DIR, "test_battle_n3.db")
os.environ.setdefault("GWEN_GAME_DB", TEST_DB)
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from _engine_harness import C            # noqa: E402
from content.panel import player_final_stats
from saintess_engine import Battle as BT_NEW, make_actor  # noqa: E402
from saintess_engine import config as _b2config  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from saintess_engine import effects as FX    # noqa: E402
from saintess_engine import stats as S       # noqa: E402

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


def find_skill(cls_cn, name):
    for cls_id, cls in (C.PLAYER_SKILLS or {}).items():
        for sk, info in (cls.get("skills") or {}).items():
            if info.get("name") == name:
                return sk, info
    for cls_id, brs in (C.BRANCH_SKILLS or {}).items():
        for tier, branches in (brs.get("branches") or {}).items():
            for bname, skills in branches.items():
                for sk, info in skills.items():
                    if info.get("name") == name:
                        return sk, info
    return None, None



def stk(a, k, d=0):
    """V 系列：读效果叠层数 effects[key].stacks。"""
    e = (a or {}).get("effects") or {}
    ent = e.get(k)
    return int(ent.get("stacks", 0) or 0) if isinstance(ent, dict) else int(d)


def ent(a, k):
    """V 系列：读效果条目 dict effects[key]。"""
    e = (a or {}).get("effects") or {}
    return e.get(k) or {}


def make_actors(cls="战士", level=10, skill_keys=(), skill_names=()):
    st = player_final_stats(cls, level, {}, 0, {}, 1)
    p = make_actor(uid="p_q1", name="测试勇者", side="player", kind="player",
                   human_controlled=True, class_name=cls, level=level,
                   hp=99999, max_hp=int(st["max_hp"]), mp=int(st["max_mp"]), max_mp=int(st["max_mp"]),
                   equipment={}, skills=list(skill_keys), learned_skills=list(skill_names),
                   race=None, evolve_path=1, class_tier=0, attributes={},
                   **{k: st[k] for k in ("atk", "matk", "def", "mdef", "spd", "crit") if k in st})
    m = make_actor(uid="e_0", name="测试怪", side="enemy", kind="monster",
                   hp=100000, max_hp=100000, atk=10, **{"def": 5},
                   matk=5, mdef=5, spd=5, crit=0.05, level=5)
    return p, m, st


def test_debuff_stack():
    print("【N3.1 状态叠层：burn/bleed/poison（on=target）cap 与写入 state】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    caster = {"uid": "p", "name": "勇者", "effects": {}}
    target = {"uid": "e", "name": "怪", "effects": {}, "hp": 100, "max_hp": 100}
    logs = []
    # burn 叠 2 层（on=target → 写 target.state.burn）
    FX.apply_effects(b, caster, target,
                     [{"type": "apply", "op": "add", "key": "burn", "amount": 2, "on": "target"}], logs)
    check("burn 写入 target.state", stk(target, "burn", 0) == 2,
          f"target.effects={target.get('effects')}")
    check("caster.state 无 burn", "burn" not in ((caster).get("effects") or {}))
    # burn 再叠 4 层 → cap 5（查声明表）
    FX.apply_effects(b, caster, target,
                     [{"type": "apply", "op": "add", "key": "burn", "amount": 4, "on": "target"}], logs)
    check("burn cap 5", stk(target, "burn", 0) == 5, f"n={stk(target, 'burn', 0)}")
    # bleed 叠 3
    FX.apply_effects(b, caster, target,
                     [{"type": "apply", "op": "add", "key": "bleed", "amount": 3, "on": "target"}], logs)
    check("bleed 写入 state", stk(target, "bleed", 0) == 3)
    # 元素印记 on=target
    FX.apply_effects(b, caster, target,
                     [{"type": "apply", "op": "add", "key": "fire_mark", "amount": 2, "on": "target"}], logs)
    check("fire_mark 写入 state", stk(target, "fire_mark", 0) == 2)


def test_control():
    print("【N3.2 控制：stun/freeze/silence 写入 target.buffs】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    caster = {"uid": "p", "name": "勇者"}
    target = {"uid": "e", "name": "怪", "effects": {}}
    logs = []
    FX.apply_effects(b, caster, target, [{"type": "stun", "turns": 3}], logs)
    _st = ent(target, "stun") or {}
    check("stun 3 刻 快照 expire≈3 mode=skip",
          abs(float(_st.get("expire", 0)) - 3.0) < 1e-9 and _st.get("mode") == "skip",
          f"stun={_st}")
    FX.apply_effects(b, caster, target, [{"type": "freeze", "turns": 1}], logs)
    check("freeze 1 刻 快照", abs(float((ent(target, "freeze") or {}).get("expire", 0)) - 1.0) < 1e-9)
    FX.apply_effects(b, caster, target, [{"type": "silence", "turns": 2}], logs)
    _si = ent(target, "silence") or {}
    check("silence 2 刻 快照 mode=no_skill",
          abs(float(_si.get("expire", 0)) - 2.0) < 1e-9 and _si.get("mode") == "no_skill",
          f"silence={_si}")
    # Boss 控制减半
    boss = {"uid": "boss", "name": "Boss", "is_boss": True, "effects": {}}
    FX.apply_effects(b, caster, boss, [{"type": "stun", "turns": 4}], logs)
    check("Boss stun 减半 2 刻", abs(float((ent(boss, "stun") or {}).get("expire", 0)) - 2.0) < 1e-9,
          f"stun={ent(boss, 'stun')}")


def test_caster_stack():
    print("【N3.3 叠层：zhan_yi/rage/chi 写入 caster.state】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    caster = {"uid": "p", "name": "勇者", "effects": {}}
    logs = []
    FX.apply_effects(b, caster, None,
                     [{"type": "apply", "op": "add", "key": "zhan_yi", "amount": 3, "on": "caster"}], logs)
    check("zhan_yi 3 层", stk(caster, "zhan_yi", 0) == 3)
    FX.apply_effects(b, caster, None,
                     [{"type": "apply", "op": "add", "key": "zhan_yi", "amount": 9, "on": "caster"}], logs)
    check("zhan_yi cap 10", stk(caster, "zhan_yi", 0) == 10,
          f"n={stk(caster, 'zhan_yi', 0)}")
    FX.apply_effects(b, caster, None,
                     [{"type": "apply", "op": "add", "key": "rage", "amount": 4, "on": "caster"}], logs)
    check("rage 4", stk(caster, "rage", 0) == 4)
    FX.apply_effects(b, caster, None,
                     [{"type": "apply", "op": "add", "key": "chi", "amount": 5, "on": "caster"}], logs)
    check("chi 5", stk(caster, "chi", 0) == 5)
    # 不足消费拦截（state_spend 需足额）
    FX.apply_effects(b, caster, None,
                     [{"type": "consume", "key": "zhan_yi", "amount": 50, "on": "caster"}], logs)
    check("zhan_yi 消费不足保留 10", stk(caster, "zhan_yi", 0) == 10)
    FX.apply_effects(b, caster, None,
                     [{"type": "consume", "key": "zhan_yi", "amount": 4, "on": "caster"}], logs)
    check("zhan_yi 消费 4 → 6", stk(caster, "zhan_yi", 0) == 6,
          f"n={stk(caster, 'zhan_yi', 0)}")


def test_buff_effect_handler():
    print("【N3.4 增益 effect 单表：reduce/atk_all/shield_self/cleanse】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    caster = {"uid": "p", "name": "勇者", "effects": {},
              "shields": {}, "reduce_left": 0, "max_hp": 1000, "hp": 500}
    logs = []
    # reduce（mech_val=45 → 45%）——N7.1 形态：{expire, v}
    FX.apply_effects(b, caster, caster,
                     [{"type": "reduce", "turns": 8, "mech_val": 45, "info": {}}], logs)
    check("reduce buffs.v=0.45", abs(ent(caster, "reduce").get("v", 0) - 0.45) < 1e-9,
          f"reduce={ent(caster, 'reduce')}")
    check("reduce_left=8", caster.get("reduce_left") == 8)
    # atk_all → atk_up（N7.1 快照：{expire, stat, op, mult}）
    # ⚠️ 2026-09-11 行为变更：`*_all` 系列改为**团队面幅**（遍历同侧存活 actor）——
    #   此前只作用施法者自己（单人时代无感）。故本测试需把 caster 放进 sides 才有受益者。
    caster["effects"].clear()
    b.sides["player"] = [caster]
    FX.apply_effects(b, caster, caster, [{"type": "atk_all", "turns": 10}], logs)
    _au = ent(caster, "atk_up") or {}
    check("atk_all → atk_up stat=atk mult=1.30（团队面幅：含施法者）",
          _au.get("stat") == "atk" and abs(float(_au.get("mult", 0)) - 1.30) < 1e-9,
          f"atk_up={_au}")
    check("atk_up expire≈now+10", abs(float(_au.get("expire", 0)) - 10.0) < 1e-9,
          f"expire={_au.get('expire')}")
    # 团队面幅：不在 sides 里的施法者拿不到（无受益者 = 无行为）
    caster["effects"].clear()
    b.sides["player"] = []
    FX.apply_effects(b, caster, caster, [{"type": "atk_all", "turns": 10}], logs)
    check("无同侧 actor → atk_all 零行为（团队面幅语义）", not ent(caster, "atk_up"),
          f"atk_up={ent(caster, 'atk_up')}")
    b.sides["player"] = [caster]
    # shield_self
    FX.apply_effects(b, caster, caster,
                     [{"type": "shield_self", "mech_val": 300, "info": {"effect_val": 0}}], logs)
    check("shield_self 300", caster["shields"].get("buff", {}).get("value") == 300)
    # cleanse：先挂状态再净化（cleanse 清 state 减益键 + buffs 控制键）
    caster["effects"]["burn"] = {"stacks": 2}
    caster["effects"]["stun"] = {"stacks": 1}
    FX.apply_effects(b, caster, caster, [{"type": "cleanse", "turns": 0}], logs)
    check("cleanse 移除 burn", "burn" not in ((caster).get("effects") or {}))
    check("cleanse 移除 stun", "stun" not in ((caster).get("effects") or {}))


def test_mech_on_hit():
    print("【N3.5 攻击命中附加 mech：挥砍 zhan_yi / 带 mech 技能】")
    # 挥砍（mech=zhan_yi mech_val=1）→ 命中后 caster.state.zhan_yi+1
    sk, info = find_skill("战士", "挥砍")
    check("找到挥砍", sk is not None)
    p, m, st = make_actors("战士", 12, [sk], [info["name"]])
    b = BT_NEW(btype="monster", sides={"player": [p], "enemy": [m]})
    random.seed(1)
    b.human_act("skill", info["name"], p)
    zy = stk(p, "zhan_yi", 0)
    check("挥砍命中后 zhan_yi ≥1", zy >= 1, f"zhan_yi={zy}")
    # 找带 burn mech 的攻击技能（龙息之怒 burn）
    sk2, info2 = find_skill("战士", "龙息之怒")
    if sk2 and info2.get("mech") == "burn":
        p2, m2, st2 = make_actors("战士", 70, [sk2], [info2["name"]])
        b2 = BT_NEW(btype="monster", sides={"player": [p2], "enemy": [m2]})
        random.seed(3)
        b2.human_act("skill", info2["name"], p2)
        burn = stk(m2, "burn", 0)
        check("龙息之怒命中后目标 burn ≥1", burn >= 1, f"burn={burn}")
    else:
        print("  跳过：龙息之怒未找到（数据可能变动）")


def test_state_scale():
    print("【N3.6 声明折算：state_effects 表 stat_scale/dmg_mult 驱动面板与伤害】")
    # stat_scale：战意 5 层 → atk ×1.2
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    actor = make_actor(uid="e1", name="测试单位", side="enemy", kind="monster",
                       atk=100, **{"def": 5}, matk=10, mdef=5, spd=5, crit=0.05)
    st0 = S.actor_stats(b, actor)
    check("无 state atk=100", st0["atk"] == 100, f"atk={st0['atk']}")
    actor["effects"]["zhan_yi"] = {"stacks": 5}
    st1 = S.actor_stats(b, actor)
    check("战意 5 层 atk ×1.2 = 120", st1["atk"] == 120, f"atk={st1['atk']}")
    # dmg_mult：rage 3 层 → _state_dmg_mult 1.36
    actor["effects"]["rage"] = {"stacks": 3}
    st2 = S.actor_stats(b, actor)
    check("rage 3 层 _state_dmg_mult=1.36",
          abs(float(st2.get("_state_dmg_mult", 1.0)) - 1.36) < 1e-9,
          f"mult={st2.get('_state_dmg_mult')}")
    # 伤害消费：无 state 打怪 vs rage 3 层打怪（同 seed 差值比例 ~1.36）
    def hit_dmg(p_atk, state_rage):
        mon = make_actor(uid="e0", name="靶", side="enemy", kind="monster",
                         hp=100000, max_hp=100000, atk=10, **{"def": 0},
                         matk=5, mdef=0, spd=5, crit=0.05, level=1)
        p = make_actor(uid="p1", name="打手", side="player", kind="player",
                       human_controlled=True, class_name="战士", level=1,
                       hp=999, max_hp=999, mp=100, max_mp=100,
                       equipment={}, skills=[], learned_skills=[],
                       race=None, evolve_path=1, class_tier=0, attributes={},
                       atk=p_atk, matk=10, **{"def": 5}, mdef=5, spd=5, crit=0.0)
        if state_rage:
            p["effects"]["rage"] = {"stacks": state_rage}
        bb = BT_NEW(btype="monster", sides={"player": [p], "enemy": [mon]})
        random.seed(9)
        hp0 = mon["hp"]
        bb.human_act("attack", None, p)
        return hp0 - mon["hp"]
    d0 = hit_dmg(100, 0)
    d1 = hit_dmg(100, 3)
    check(f"普攻伤害 rage 3 层（{d1}）> 无层（{d0}）", d1 > d0, f"d0={d0} d1={d1}")


def test_buff_snapshot_scaling():
    print("【N3.7 N7.1 buff 快照折算：条目 mult/add 驱动面板，纯状态不折算】")
    # 纯怪（无 class_name → 直接读字段，避免职业公式干扰折算验证）
    actor = make_actor(uid="e1", name="折算靶", side="enemy", kind="monster",
                       atk=100, **{"def": 0}, matk=10, mdef=0, spd=50,
                       crit=0.05, max_hp=999, hp=999)
    b = BT_NEW(btype="monster", sides={"enemy": [actor], "player": []})
    st0 = S.actor_stats(b, actor)
    check("无 buff atk=100", st0["atk"] == 100, f"atk={st0['atk']}")
    # mul 快照：atk_up mult=1.30 → 100×1.30 = 130（不是旧"3刻×10%"逻辑）
    actor["effects"]["atk_up"] = {"stacks": 1, "expire": 10.0, "stat": "atk", "op": "mul", "mult": 1.30}
    st1 = S.actor_stats(b, actor)
    check("atk_up mul 快照 atk=130", st1["atk"] == 130, f"atk={st1['atk']}")
    # add 快照：crit_up mult=0.20 → crit +0.20
    actor["effects"]["crit_up"] = {"stacks": 1, "expire": 10.0, "stat": "crit", "op": "add", "mult": 0.20}
    st2 = S.actor_stats(b, actor)
    check("crit_up add 快照 crit+0.20",
          abs(float(st2.get("crit", 0)) - (float(st0.get("crit", 0)) + 0.20)) < 1e-9,
          f"crit={st2.get('crit')}")
    # 纯状态（无 stat）不折算：stun 挂上 atk 不变
    actor["effects"]["stun"] = {"stacks": 1, "expire": 1.0}
    st3 = S.actor_stats(b, actor)
    check("stun 纯状态不折算 atk", st3["atk"] == 130, f"atk={st3['atk']}")


def test_n72_more_branches():
    print("【N3.8 N7.2 补分支：纯状态 buff / 护盾叠厚 / 缺省盾值 / 过期控制】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    caster = {"uid": "p", "name": "勇者", "effects": {},
              "shields": {}, "reduce_left": 0, "max_hp": 1000, "hp": 500}
    logs = []
    # 纯状态 buff（无 stat）→ 只记 expire，不折算（cc_immune 走 buff 动词无 stat 参数）
    FX.apply_effects(b, caster, caster,
                     [{"type": "apply", "key": "cc_immune", "turns": 5}], logs)
    _ci = ent(caster, "cc_immune") or {}
    check("纯状态 buff 存 expire", isinstance(_ci, dict) and abs(float(_ci.get("expire", 0)) - 5.0) < 1e-9,
          f"cc_immune={_ci}")
    check("纯状态 buff 无 stat", "stat" not in _ci)
    # 护盾同源叠厚：两次 shield_self → value 累加
    caster["shields"].clear()
    FX.apply_effects(b, caster, caster,
                     [{"type": "shield_self", "value": 100, "turns": 3}], logs)
    FX.apply_effects(b, caster, caster,
                     [{"type": "shield_self", "value": 50, "turns": 5}], logs)
    _sh = caster["shields"].get("buff") or {}
    check("同源叠厚 value=150", int(_sh.get("value", 0)) == 150, f"sh={_sh}")
    check("expire 取 max≈5", abs(float(_sh.get("expire_at", 0)) - 5.0) < 1e-9, f"exp={_sh.get('expire_at')}")
    # 缺省盾值：value=0 且无 pct → max_hp×20%
    caster["shields"].clear()
    FX.apply_effects(b, caster, caster, [{"type": "shield_self", "turns": 3}], logs)
    check("缺省盾 max_hp×20% = 200", int((caster["shields"].get("buff") or {}).get("value", 0)) == 200,
          f"sh={caster['shields'].get('buff')}")


def test_on_hit_n73():
    print("【N3.9 N7.3 一次性 on_hit：next_atk_up 增伤 / stealth 必暴，出手消费】")
    import random as _r
    def mk_p(uid):
        return make_actor(uid=uid, name="勇者", side="player", kind="player", human_controlled=True,
                          class_name="战士", level=10, hp=1000, max_hp=1000, atk=100, mp=100,
                          max_mp=100, spd=50, equipment={}, class_tier=0, attributes={},
                          evolve_path=0, race="人族", crit=0.0, crit_dmg=1.0)
    def mk_e(uid):
        return make_actor(uid=uid, name="靶", side="enemy", kind="monster", hp=100000,
                          max_hp=100000, atk=10, **{"def": 0}, spd=10, level=5)
    # 写入：next_atk_up 名词 → 条目带 hit.dmg_mult=1.50
    b = BT_NEW(btype="monster", sides={"player": [mk_p("p1")], "enemy": [mk_e("e1")]})
    p = b.sides["player"][0]
    FX.apply_effects(b, p, p, [{"type": "next_atk_up", "turns": 3}], [])
    _n = ent(p, "next_atk_up") or {}
    check("next_atk_up 条目带 hit.dmg_mult=1.50",
          isinstance(_n.get("hit"), dict) and abs(float(_n["hit"].get("dmg_mult", 0)) - 1.50) < 1e-9,
          f"entry={_n}")
    # 出手消费：攻击后 buff 删 + 伤害增加
    hp0 = b.sides["enemy"][0]["hp"]
    b.human_act("attack", None, p)
    check("next_atk_up 出手消费删除", "next_atk_up" not in ((p).get("effects") or {}))
    # stealth 必暴：crit=0 面板下普攻 vs 潜行
    b2 = BT_NEW(btype="monster", sides={"player": [mk_p("p2")], "enemy": [mk_e("e2")]})
    p2 = b2.sides["player"][0]
    _r.seed(1)
    b2.human_act("attack", None, p2)
    plain = 100000 - b2.sides["enemy"][0]["hp"]
    b3 = BT_NEW(btype="monster", sides={"player": [mk_p("p3")], "enemy": [mk_e("e3")]})
    p3 = b3.sides["player"][0]
    FX.apply_effects(b3, p3, p3, [{"type": "stealth", "turns": 3}], [])
    _r.seed(1)
    b3.human_act("attack", None, p3)
    crit_d = 100000 - b3.sides["enemy"][0]["hp"]
    check("stealth 必暴伤害 > 普攻", crit_d > plain, f"{crit_d} vs {plain}")
    check("stealth 消费删除", "stealth" not in ((p3).get("effects") or {}))


def test_n75a_verbs():
    print("【N3.10 N7.5a 补动词：heal_pct/heal_self/stacks_set/interrupt + 承伤乘区】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    caster = {"uid": "p", "name": "勇者", "effects": {}, "shields": {},
              "hp": 100, "max_hp": 1000, "mp": 100}
    logs = []
    FX.apply_effects(b, caster, caster,
                     [{"type": "heal_pct", "on": "caster", "info": {"hp_pct": 0.15}}], logs)
    check("heal_pct 治 15% max_hp", caster["hp"] == 250, f"hp={caster['hp']}")
    caster["hp"] = 100
    FX.apply_effects(b, caster, caster, [{"type": "heal_self", "info": {"hp_pct": 0.15}}], logs)
    check("heal_self 治 15%", caster["hp"] == 250, f"hp={caster['hp']}")
    FX.apply_effects(b, caster, caster, [{"type": "stacks_set", "key": "charge", "amount": 3}], logs)
    check("stacks_set charge=3", stk(caster, "charge", 0) == 3)
    FX.apply_effects(b, caster, caster, [{"type": "stacks_set", "key": "charge", "amount": 5}], logs)
    check("stacks_set 覆盖 3→5", stk(caster, "charge", 0) == 5)
    tgt = {"uid": "e", "name": "Boss", "effects": {},
           "charging": {"skill": "蓄力斩"}, "hp": 500}
    FX.apply_effects(b, caster, tgt, [{"type": "interrupt"}], logs)
    check("interrupt 清 charging", tgt.get("charging") is None)
    # landing 承伤乘区（vulnerable 破绽直写 _dmg_taken_mult）
    e2 = {"uid": "e2", "name": "靶", "hp": 1000, "max_hp": 1000, "_dmg_taken_mult": 1.5}
    from saintess_engine.battle.landing import deal_damage
    deal_damage(b, {"uid": "s", "name": "打", "level": 10}, e2, 100, [])
    check("承伤×1.5 → 扣 150", 1000 - e2["hp"] == 150, f"扣血 {1000 - e2['hp']}")


def test_n75b_potion_aliases():
    print("【N3.11 N7.5b 药水纯属性别名：buff_atk/buff_crit/food 系 → BUFF_MULT 数值】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    actor = {"uid": "p", "name": "勇者", "effects": {}, "shields": {},
             "hp": 500, "max_hp": 1000, "atk": 100, "def": 0, "spd": 50,
             "crit": 0.05, "max_mp": 100, "mp": 100, "matk": 10, "mdef": 0}
    logs = []
    FX.apply_effects(b, actor, actor, [{"type": "buff_atk", "turns": 3}], logs)
    _au = ent(actor, "atk_up") or {}
    check("buff_atk → atk_up stat=atk mult=1.30",
          _au.get("stat") == "atk" and abs(float(_au.get("mult", 0)) - 1.30) < 1e-9, f"entry={_au}")
    st = S.actor_stats(b, actor)
    check("atk_up 面板折算 atk×1.30", abs(st["atk"] - int(100 * 1.30)) <= 1, f"atk={st['atk']}")
    FX.apply_effects(b, actor, actor, [{"type": "buff_crit", "turns": 3}], logs)
    _cu = ent(actor, "crit_up") or {}
    check("buff_crit → crit_up add 0.20",
          _cu.get("stat") == "crit" and _cu.get("op") == "add"
          and abs(float(_cu.get("mult", 0)) - 0.20) < 1e-9, f"entry={_cu}")
    FX.apply_effects(b, actor, actor, [{"type": "buff_atk_food", "turns": 3}], logs)
    _fu = ent(actor, "food_atk_up") or {}
    check("buff_atk_food → food_atk_up mult=1.10",
          abs(float(_fu.get("mult", 0)) - 1.10) < 1e-9, f"entry={_fu}")


def main():
    print("=== N3 saintess_engine 效果系统测试 ===")
    test_debuff_stack()
    test_control()
    test_caster_stack()
    test_buff_effect_handler()
    test_mech_on_hit()
    test_state_scale()
    test_buff_snapshot_scaling()
    test_n72_more_branches()
    test_on_hit_n73()
    test_n75a_verbs()
    test_n75b_potion_aliases()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        print("失败明细:")
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
