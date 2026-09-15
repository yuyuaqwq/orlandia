# -*- coding: utf-8 -*-
"""N8 验收：saintess_engine 事件总线（effect_triggers.py）19 时机 fire() 插桩。

覆盖：
- battle_start：首动前整场一次（起手 buff/仪式）
- turn_start / act_begin / act_cast：行动周期事件
- skill_hit vs attack_hit：技能命中 / 普攻命中区分
- crit：暴击命中（命中子集）
- on_taken：受击后（自我强化）
- on_heal：治疗生效后
- on_kill / on_death：击杀者 / 死亡
- dot_tick：DOT 每跳
- on_act_consume / on_hit_consume：行动/出手消费点
- buff_expire：buff 到期钩子
- threshold：状态层数变化后
- phase/player_low/pv_broken：N9 上层 fire（声明全集，无引擎点位）

语义（DESIGN_effect_system_v2.md Part 3.3/4）：
- 效果源 = actor["triggers"] = {事件: [效果名词 dict, ...]}（引擎零知识）
- fire(ctx)：caster 缺省 = 声明者自己；target = 事件目标
- 名词效果经 EFFECT_ACTIONS 翻译成动词执行

跑法：python tests/test_battle_n8_events.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
TEST_DB = os.path.join(PLUGIN_DIR, "test_battle_n8.db")
os.environ.setdefault("GWEN_GAME_DB", TEST_DB)
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import Battle as BT_NEW, make_actor  # noqa: E402
from saintess_engine import config as _b2config  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from saintess_engine import actions as AC          # noqa: E402
from saintess_engine import effects as FX          # noqa: E402
from saintess_engine import landing as L           # noqa: E402
from saintess_engine import effect_triggers as TR  # noqa: E402
from saintess_engine.battle.actors import ActCtx          # noqa: E402
from saintess_engine.battle.schedule import _settle_time_effects as _ste  # noqa: E402

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


def mk_a(uid, side, hp=600, atk=30, **kw):
    base = dict(hp=hp, max_hp=hp, atk=atk, matk=10, mdef=5,
                spd=50, crit=0.05, level=10)
    base["def"] = 5
    base.update(kw)
    return make_actor(uid=uid, name=uid, side=side,
                      kind="player" if side == "player" else "monster",
                      human_controlled=(side == "player"), **base)


def new_battle(*actors):
    sides = {}
    for a in actors:
        sides.setdefault(a["side"], []).append(a)
    return BT_NEW(btype="monster", sides=sides)


def do_attack(b, a, t):
    return AC.do_attack(b, ActCtx(caster=a, action="attack", target=t))


def do_skill(b, a, t, info):
    return AC.do_skill(b, ActCtx(caster=a, action="skill", skill_name=info.get("name", "技"),
                                 info=info, target=t))


# 测试用技能（物理单段，走统一技能管道 → 非 basic → skill_hit）
TEST_SKILL = {"name": "测试斩", "kind": "物理", "exprs": ["atk*1.0"]}


def test_events_declared():
    print("【N8.0 事件全集声明 + 引擎点位分布】")
    check("EVENTS 26 个（19 效果时机 + 4 数值修正钩子 dot_calc + act_done + N5B5c interrupt"
          " + v181 time_advance 时钟推进）",
          len(TR.EVENTS) == 26, f"len={len(TR.EVENTS)}")
    for ev in ("battle_start", "turn_start", "act_begin", "act_cast",
               "skill_hit", "attack_hit", "crit", "on_taken", "on_heal",
               "on_kill", "on_death", "dot_tick", "on_act_consume",
               "on_hit_consume", "buff_expire", "threshold",
               "dmg_calc", "taken_calc", "heal_calc",  # N9.13/2e 数值修正钩子
               "phase", "player_low", "pv_broken",
               "time_advance"):                       # v181 时钟推进（挂敌身条结算）
        check(f"事件 {ev} 在全集", ev in TR.EVENTS)
    # 非全集事件静默忽略（防拼写漂移）
    b = new_battle(mk_a("a1", "player"), mk_a("e1", "enemy"))
    logs = []
    b._ensure_battle_started(logs)
    TR.fire(b, "not_a_real_event", {}, logs)
    check("未知事件静默空转", True)
    # logs=None（无日志容器上下文）空转安全
    TR.fire(b, "battle_start", {}, None)
    check("logs=None 空转安全", True)
    # 无效 event（空串）空转安全
    TR.fire(b, "", {}, logs)
    check("空事件名空转安全", True)


def test_battle_start_once():
    print("【N8.1 battle_start：首动前整场一次（起手 buff）】")
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=9999)
    p["triggers"] = {"battle_start": [{"type": "atk_up", "turns": 5}]}
    b = new_battle(p, m)
    check("构造后未触发（buffs 空）", "atk_up" not in ((p).get("effects") or {}))
    logs = []
    b.human_act("attack", None, actor=p, target=m)
    _au = ((p).get("effects") or {}).get("atk_up") or {}
    check("首动触发 → atk_up 挂上", "atk_up" in ((p).get("effects") or {}), f"buffs={((p).get('effects') or {})}")
    check("mult 快照 1.30", abs(float(_au.get("mult", 0)) - 1.30) < 1e-9, f"{_au}")
    logs2 = []
    b.human_act("attack", None, actor=p, target=m)
    check("二动不再重复 battle_start", b._started is True)
    # 序列化续战：from_state 不重触发（_started=True）
    b2 = BT_NEW.from_state(b.to_state())
    check("from_state 续战不重触发", b2._started is True)


def test_turn_begin_cast_cycle():
    print("【N8.2 turn_start / act_begin / act_cast 行动周期事件】")
    p = mk_a("p1", "player")
    p["hp"] = p["max_hp"] - 90  # 留缺口，观察每次行动回血
    m = mk_a("e1", "enemy", hp=9999)
    p["triggers"] = {
        "turn_start": [{"type": "heal", "value": 10, "on": "caster"}],
        "act_begin":  [{"type": "heal", "value": 20, "on": "caster"}],
        "act_cast":   [{"type": "heal", "value": 30, "on": "caster"}],
    }
    b = new_battle(p, m)
    # b.act() 直调：只 p 行动一次（不推 CTB → 怪不反击，净回血 = 三个时点之和）
    b.act(ActCtx(caster=p, action="attack", target=m))
    gained = 90 - (p["max_hp"] - p["hp"])
    check("一次行动触发三个时点（10+20+30）", gained == 60, f"回血 {gained}")

    # 被控制跳过时：turn_start 仍触发、act_begin/act_cast 不触发
    p2 = mk_a("p2", "player")
    p2["hp"] = p2["max_hp"] - 100
    m2 = mk_a("e2", "enemy", hp=9999)
    p2["effects"]["stun"] = {"stacks": 1, "expire": 9999.0, "mode": "skip"}
    p2["triggers"] = {
        "turn_start":      [{"type": "heal", "value": 10, "on": "caster"}],
        "act_begin":       [{"type": "heal", "value": 20, "on": "caster"}],
        "on_act_consume":  [{"type": "heal", "value": 5,  "on": "caster"}],
    }
    b2 = new_battle(p2, m2)
    b2.act(ActCtx(caster=p2, action="attack", target=m2))
    g2 = 100 - (p2["max_hp"] - p2["hp"])
    check("被晕：turn_start 10 + on_act_consume 5", g2 == 15, f"回血 {g2}")
    check("被晕：act_begin 不触发（stun 仍在？被消费删除）",
          "stun" not in ((p2).get("effects") or {}), f"buffs={((p2).get('effects') or {})}")


def test_skill_hit_vs_attack_hit():
    print("【N8.3 skill_hit vs attack_hit：技能/普攻命中区分】")
    # 普攻 → 只 attack_hit
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=9999)
    p["triggers"] = {
        "attack_hit": [{"type": "apply", "op": "add", "key": "n8_atk", "amount": 1, "on": "caster"}],
        "skill_hit":  [{"type": "apply", "op": "add", "key": "n8_sk", "amount": 1, "on": "caster"}],
    }
    b = new_battle(p, m)
    do_attack(b, p, m)
    check("普攻触发 attack_hit", stk(p, "n8_atk", 0) == 1, f"state={((p).get('effects') or {})}")
    check("普攻不触发 skill_hit", "n8_sk" not in ((p).get("effects") or {}), f"state={((p).get('effects') or {})}")
    # 技能 → 只 skill_hit（另开战斗避免叠层混淆）
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=9999)
    p2["triggers"] = {
        "attack_hit": [{"type": "apply", "op": "add", "key": "n8_atk", "amount": 1, "on": "caster"}],
        "skill_hit":  [{"type": "apply", "op": "add", "key": "n8_sk", "amount": 1, "on": "caster"}],
    }
    b2 = new_battle(p2, m2)
    do_skill(b2, p2, m2, TEST_SKILL)
    check("技能触发 skill_hit", stk(p2, "n8_sk", 0) == 1, f"state={((p2).get('effects') or {})}")
    check("技能不触发 attack_hit", "n8_atk" not in ((p2).get("effects") or {}), f"state={((p2).get('effects') or {})}")


def test_crit_event():
    print("【N8.4 crit：暴击命中（命中子集）】")
    p = mk_a("p1", "player", crit=1.0)  # 必暴
    m = mk_a("e1", "enemy", hp=9999)
    p["triggers"] = {
        "attack_hit": [{"type": "apply", "op": "add", "key": "n8_hit", "amount": 1, "on": "caster"}],
        "crit":       [{"type": "apply", "op": "add", "key": "n8_crit", "amount": 1, "on": "caster"}],
    }
    b = new_battle(p, m)
    do_attack(b, p, m)
    check("暴击普攻：attack_hit 与 crit 都触发",
          stk(p, "n8_hit", 0) == 1 and stk(p, "n8_crit", 0) == 1,
          f"state={((p).get('effects') or {})}")


def test_on_taken_self_shield():
    print("【N8.5 on_taken：受击后自我强化（护盾）】")
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy")
    m["triggers"] = {"on_taken": [{"type": "shield", "value": 50, "turns": 3, "on": "target"}]}
    b = new_battle(p, m)
    b._ensure_battle_started([])
    do_attack(b, p, m)
    _sh = (m["shields"] or {}).get("buff") or {}
    check("受击触发 → 护盾 50", int(_sh.get("value", 0)) == 50, f"shields={m['shields']}")
    check("护盾 expire_at 3 刻", _sh.get("expire_at") is not None)


def test_on_heal():
    print("【N8.6 on_heal：治疗生效后】")
    tgt = mk_a("t1", "player", hp=500)
    tgt["hp"] = 400
    tgt["triggers"] = {"on_heal": [{"type": "apply", "op": "add", "key": "n8_heal", "amount": 1, "on": "target"}]}
    b = new_battle(tgt, mk_a("e1", "enemy"))
    logs = []
    real = L.heal_actor(b, tgt, 30, logs)
    check("治疗 30 生效", real == 30, f"real={real}")
    check("on_heal 触发", stk(tgt, "n8_heal", 0) == 1, f"state={((tgt).get('effects') or {})}")
    # 满血时治疗 clamp → real=0 → on_heal 不广播
    tgt["hp"] = tgt["max_hp"]
    logs2 = []
    real2 = L.heal_actor(b, tgt, 30, logs2)
    check("满血治疗 real=0", real2 == 0, f"real={real2}")
    check("无效治疗不触发 on_heal", stk(tgt, "n8_heal", 0) == 1, f"state={((tgt).get('effects') or {})}")


def test_on_kill_and_on_death():
    print("【N8.7 on_kill（击杀者）/ on_death（死者自身效果）】")
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=50)
    p["triggers"] = {"on_kill": [{"type": "apply", "op": "add", "key": "n8_kill", "amount": 1, "on": "caster"}]}
    # on_death 主体=死者（fire 允许 dead subject 执行自身声明——死亡遗言类）
    m["triggers"] = {"on_death": [{"type": "apply", "op": "add", "key": "n8_dead", "amount": 1, "on": "caster"}]}
    b = new_battle(p, m)
    logs = []
    L.deal_damage(b, p, m, 999, logs)
    check("击杀触发 on_kill", stk(p, "n8_kill", 0) == 1, f"state={((p).get('effects') or {})}")
    check("敌人死亡", m["hp"] == 0)
    # on_death：死者自己的死亡效果执行（fire subject=dead 例外）
    check("on_death 死者声明执行", stk(m, "n8_dead", 0) == 1, f"state={((m).get('effects') or {})}")
    check("死者登记", len(b.killed_actors) >= 1)


def test_dot_tick():
    print("【N8.8 dot_tick：DOT 每跳】")
    e = mk_a("e1", "enemy", hp=1000)
    # 伤害按当前规则表推算（burn 0.5% + pct_cap 1% 上限；条目覆盖 3% → 压到 1%）
    from saintess_engine.battle.state_effects import state_def as _sd8
    _p8 = (_sd8("burn") or {}).get("period") or {}
    _c8 = float(_p8.get("pct_cap") or 0)
    _pct8 = min(0.03, _c8) if _c8 else 0.03
    _jump8 = int(1000 * _pct8 * 2)
    e["effects"]["burn"] = {"stacks": 2, "pct": 0.03}
    e["triggers"] = {"dot_tick": [{"type": "apply", "op": "add", "key": "n8_dot", "amount": 1, "on": "target"}]}
    b = new_battle(mk_a("p1", "player"), e)
    b._now = 0.0
    _ste(b, [])   # 登记 dot_next=1.0
    b._now = 1.5
    logs = []
    _ste(b, logs)
    check(f"burn 跳 1 次掉 {_jump8}", 1000 - e["hp"] == _jump8, f"hp={e['hp']}")
    check("dot_tick 每跳触发", stk(e, "n8_dot", 0) == 1, f"state={((e).get('effects') or {})}")


def test_buff_expire():
    print("【N8.9 buff_expire：buff 到期钩子】")
    a = mk_a("a1", "player", hp=500)
    a["hp"] = 400
    a["effects"]["n8_buf"] = {"stacks": 1, "expire": 1.0}
    a["triggers"] = {"buff_expire": [{"type": "heal", "value": 5, "on": "caster"}]}
    b = new_battle(a, mk_a("e1", "enemy"))
    b._now = 0.0
    _ste(b, [])
    check("未到期不删", "n8_buf" in ((a).get("effects") or {}))
    b._now = 2.0
    _ste(b, [])
    check("到点删除", "n8_buf" not in ((a).get("effects") or {}))
    check("buff_expire 触发回血 5", a["hp"] == 405, f"hp={a['hp']}")


def test_threshold():
    print("【N8.10 threshold：状态层数变化后】")
    a = mk_a("a1", "player", hp=500)
    a["hp"] = 400
    a["triggers"] = {"threshold": [{"type": "heal", "value": 5, "on": "caster"}]}
    b = new_battle(a, mk_a("e1", "enemy"))
    logs = []
    FX.apply_effects(b, a, a, [{"type": "apply", "op": "add", "key": "rage", "amount": 1}], logs)
    check("层数加上", stk(a, "rage", 0) == 1)
    check("threshold 触发回血 5", a["hp"] == 405, f"hp={a['hp']}")
    # state_set 置值也广播
    a["hp"] = 400
    logs2 = []
    FX.apply_effects(b, a, a, [{"type": "apply", "op": "set", "key": "rage", "amount": 2}], logs2)
    check("state_set 后 threshold 也触发", a["hp"] == 405, f"hp={a['hp']}")


def test_on_hit_consume():
    print("【N8.11 on_hit_consume：出手一次性 buff 消费点】")
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=9999)
    p["hp"] = p["max_hp"] - 50
    p["effects"]["next_atk_up"] = {"stacks": 1, "expire": 9999.0, "hit": {"dmg_mult": 1.5}}
    p["triggers"] = {"on_hit_consume": [{"type": "heal", "value": 5, "on": "caster"}]}
    b = new_battle(p, m)
    do_attack(b, p, m)
    check("一次性 buff 被消费", "next_atk_up" not in ((p).get("effects") or {}))
    check("on_hit_consume 触发回血 5", p["hp"] == p["max_hp"] - 45, f"hp={p['hp']}")


def test_trigger_serde_roundtrip():
    print("【N8.12 triggers 声明随 actor 序列化落盘/恢复】")
    p = mk_a("p1", "player")
    p["triggers"] = {"battle_start": [{"type": "atk_up", "turns": 5}]}
    m = mk_a("e1", "enemy", hp=9999)
    b = new_battle(p, m)
    st = b.to_state()
    b2 = BT_NEW.from_state(st)
    p2 = b2.sides["player"][0]
    check("triggers 落盘恢复", (p2.get("triggers") or {}).get("battle_start") ==
          [{"type": "atk_up", "turns": 5}], f"triggers={p2.get('triggers')}")



def stk(a, k, d=0):
    """V 系列：读效果叠层数 effects[key].stacks。"""
    e = (a or {}).get("effects") or {}
    ent = e.get(k)
    return int(ent.get("stacks", 0) or 0) if isinstance(ent, dict) else int(d)


def ent(a, k):
    """V 系列：读效果条目 dict effects[key]。"""
    e = (a or {}).get("effects") or {}
    return e.get(k) or {}


def main():
    print("=== N8 saintess_engine 事件总线测试 ===")
    test_events_declared()
    test_battle_start_once()
    test_turn_begin_cast_cycle()
    test_skill_hit_vs_attack_hit()
    test_crit_event()
    test_on_taken_self_shield()
    test_on_heal()
    test_on_kill_and_on_death()
    test_dot_tick()
    test_buff_expire()
    test_threshold()
    test_on_hit_consume()
    test_trigger_serde_roundtrip()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
