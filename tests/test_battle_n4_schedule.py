# -*- coding: utf-8 -*-
"""N4 验收：CTB 调度 + 自动行动 + 完整战斗闭环。

覆盖：
- 完整战斗 auto_run 能打到 victory/defeat（玩家 vs 怪）
- 行动序：速度快者先动（ct 推进正确）
- human_act 推进：玩家出手 → 自动 actor 行动 → 下一个决策点
- DOT：带 burn 状态的目标随时间跳伤害
- 逃跑 fled

跑法：python tests/test_battle_n4_schedule.py
"""
import os
import sys
import random
import math

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
TEST_DB = os.path.join(PLUGIN_DIR, "test_battle_n4.db")
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
from _engine_harness import human_land  # noqa: E402  T15 两段化：落地推进（一次出手 = 落地后返回）

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")



def stk(a, k, d=0):
    """V 系列：读效果叠层数 effects[key].stacks。"""
    e = (a or {}).get("effects") or {}
    ent = e.get(k)
    return int(ent.get("stacks", 0) or 0) if isinstance(ent, dict) else int(d)


def ent(a, k):
    """V 系列：读效果条目 dict effects[key]。"""
    e = (a or {}).get("effects") or {}
    return e.get(k) or {}


def mk_player(cls="战士", level=10, hp=None):
    st = player_final_stats(cls, level, {}, 0, {}, 1)
    p = make_actor(uid="p_q1", name="测试勇者", side="player", kind="player",
                   human_controlled=True, class_name=cls, level=level,
                   hp=hp if hp is not None else int(st["max_hp"]),
                   max_hp=int(st["max_hp"]),
                   mp=int(st["max_mp"]), max_mp=int(st["max_mp"]),
                   equipment={}, skills=[], learned_skills=[],
                   race=None, evolve_path=1, class_tier=0, attributes={},
                   **{k: st[k] for k in ("atk", "matk", "def", "mdef", "spd", "crit") if k in st})
    return p


def mk_monster(hp=200, atk=20, spd=5, name="野狼"):
    return make_actor(uid="e_0", name=name, side="enemy", kind="monster",
                      hp=hp, max_hp=hp, atk=atk, **{"def": 5},
                      matk=5, mdef=5, spd=spd, crit=0.05, level=5)


def test_full_battle_victory():
    print("【N4.1 完整战斗：玩家打赢（victory）】")
    p = mk_player("战士", 12)
    m = mk_monster(hp=150, atk=5)  # 怪很弱
    b = BT_NEW(btype="monster", sides={"player": [p], "enemy": [m]})
    logs = []
    b.auto_run(logs)
    check("战斗结束", b.result in ("victory", "defeat"))
    check("玩家胜利", b.result == "victory", f"result={b.result}")
    check("怪物死亡", m["hp"] <= 0)
    check("有行动日志", len(logs) > 3)


def test_full_battle_defeat():
    print("【N4.2 完整战斗：玩家被打死（defeat）】")
    p = mk_player("战士", 3)
    m = mk_monster(hp=2000, atk=60, spd=30, name="强敌")
    b = BT_NEW(btype="monster", sides={"player": [p], "enemy": [m]})
    logs = []
    b.auto_run(logs)
    check("玩家战败", b.result == "defeat", f"result={b.result}")
    check("玩家死亡", p["hp"] <= 0)


def test_speed_order():
    print("【N4.3 速度决定行动序：快怪先动】")
    # 怪 spd=30 vs 玩家 spd=5 → 怪第一动
    p = mk_player("战士", 10)
    m = mk_monster(hp=100000, atk=1, spd=30, name="快怪")
    b = BT_NEW(btype="monster", sides={"player": [p], "enemy": [m]})
    from saintess_engine import schedule as SC
    ct_p = SC.initial_ct(p["spd"])
    ct_m = SC.initial_ct(m["spd"])
    check("快怪初始 ct < 玩家", ct_m < ct_p, f"m={ct_m:.2f} p={ct_p:.2f}")


def test_human_act_advance():
    print("【N4.4 human_act 推进：玩家出手后自动怪会行动】")
    p = mk_player("战士", 10)
    m = mk_monster(hp=100000, atk=5, spd=3, name="慢怪")
    b = BT_NEW(btype="monster", sides={"player": [p], "enemy": [m]})
    hp0 = m["hp"]
    # 玩家出手普攻 → 应推进到怪物行动若干次
    logs, ended, who = human_land(b, "attack", None, p)
    dmg = hp0 - m["hp"]
    check("玩家普攻打到怪", dmg > 0, f"dmg={dmg}")
    check("推进后未结束（怪血厚）", not ended, f"ended={ended}")
    # 玩家 ct 已推进
    check("玩家 ct > 0", float(p.get("ct", 0)) > 0, f"ct={p.get('ct')}")
    check("now 推进 > 0", b._now > 0, f"now={b._now}")


def test_dot_tick():
    print("【N4.5 DOT：目标带 burn 状态随时间跳伤害】")
    p = mk_player("战士", 20)
    m = mk_monster(hp=10000, atk=1, spd=100, name="靶怪")
    # 挂 burn 3 层（state_add on=target）
    from saintess_engine import effects as FX
    FX.apply_effects(b := BT_NEW(btype="monster", sides={"player": [p], "enemy": [m]}),
                     p, m, [{"type": "apply", "op": "add", "key": "burn", "amount": 3, "on": "target"}], [])
    check("burn 3 层挂上", stk(m, "burn", 0) == 3)
    hp0 = m["hp"]
    logs = []
    b.auto_run(logs)
    check("时间推进后怪掉血", m["hp"] < hp0, f"hp {hp0} → {m['hp']}")


def test_flee():
    print("【N4.6 逃跑：fled 结束】")
    p = mk_player("战士", 10)
    m = mk_monster(hp=100000, atk=1)
    b = BT_NEW(btype="monster", sides={"player": [p], "enemy": [m]})
    logs, ended, who = human_land(b, "flee", None, p)
    check("逃跑结束", b.result == "fled", f"result={b.result}")


def test_real_data_spd0_player():
    """回归（2026-09-08 对拍发现）：真实玩家 actor 裸 spd=0（面板由 stats 聚合），
    _after_act 若用裸 spd=0 算行动耗时 → 玩家每次行动等 sqrt(50/1)≈7s，被怪碾压致死。
    修复：_after_act 用聚合面板 spd（与 next_ct 同口径）。"""
    print("【N4.7 回归：裸 spd=0 玩家（真实数据形态）auto_run 正常】")
    # 模拟 battle_bridge 产物：玩家 actor 裸 spd/atk/def=0，面板靠 class 聚合
    p = make_actor(uid="p_q1", name="裸奔勇者", side="player", kind="player",
                   human_controlled=True, class_name="战士", level=10,
                   hp=200, max_hp=200, mp=50, max_mp=50,
                   equipment={}, skills=[], learned_skills=[], race=None,
                   evolve_path=0, class_tier=0, attributes=None)
    check("裸 spd=0（真实形态）", p.get("spd") == 0, f"spd={p.get('spd')}")
    m = mk_monster(hp=165, atk=48, spd=14, name="野狼")  # 同级 dps 怪
    b = BT_NEW(btype="monster", sides={"player": [p], "enemy": [m]})
    logs = []
    b.auto_run(logs)
    check("战斗有结果", b.result in ("victory", "defeat"), f"result={b.result}")
    # 关键：玩家必须能行动多轮（不被 spd=0 卡死/碾压）——logs 数足量说明交替行动了
    check("行动轮次充足（>5 条日志）", len(logs) > 5, f"logs={len(logs)}")
    # 玩家至少出过手（怪掉血了）
    check("怪物被攻击过", m["hp"] < 165, f"m_hp={m['hp']}")


def test_time_effects_n72():
    """N7.2 时效收口：控制 skip/no_skill 消费 + buff/shield 到期删。"""
    print("【N4.8 N7.2 时效：控制消费 + buffs/shields 到期】")
    from saintess_engine.battle.schedule import _settle_time_effects
    p = make_actor(uid="p_p1", name="玩家", side="player", kind="player",
                   human_controlled=True, class_name="战士", level=10,
                   hp=1000, max_hp=1000, atk=50, mp=100, max_mp=100, spd=50,
                   equipment={}, class_tier=0, attributes={}, evolve_path=0,
                   race="人族")
    e = make_actor(uid="e_e1", name="怪", side="enemy", kind="monster",
                   hp=9999, max_hp=9999, atk=10, **{"def": 0}, spd=30, level=5,
                   skills=[], auto_act={"act": {"type": "attack"}})
    b = BT_NEW(btype="monster", sides={"player": [p], "enemy": [e]})
    # 1. mode=skip：被晕攻击跳过 + 清除
    p["effects"]["stun"] = {"stacks": 1, "expire": 99.0, "mode": "skip"}
    hp0 = e["hp"]
    logs, ended, who = human_land(b, "attack", None, p)
    check("被晕攻击被跳过（怪满血）", e["hp"] == hp0)
    check("stun 消费清除", "stun" not in ((p).get("effects") or {}))
    hp0 = e["hp"]
    human_land(b, "attack", None, p)
    check("清醒后攻击命中", e["hp"] < hp0, f"hp={e['hp']}")
    # 2. mode=no_skill：沉默技能转普攻（仍造成伤害），持续不消
    p["effects"]["silence"] = {"stacks": 1, "expire": 99.0, "mode": "no_skill"}
    hp0 = e["hp"]
    human_land(b, "skill", "猛击", p)
    check("沉默下技能仍造成伤害", e["hp"] < hp0, f"hp={e['hp']}")
    check("沉默持续未清除", "silence" in ((p).get("effects") or {}))
    # 3. shields 到期删
    e2 = make_actor(uid="e_e2", name="怪2", side="enemy", kind="monster",
                    hp=500, max_hp=500, atk=1, spd=10, level=1)
    b2 = BT_NEW(btype="monster", sides={"player": [p], "enemy": [e2]})
    e2["shields"]["test"] = {"value": 100, "expire_at": 3.0}
    b2._now = 2.0
    _settle_time_effects(b2, [])
    check("盾未到期仍在", "test" in e2["shields"])
    b2._now = 4.0
    _settle_time_effects(b2, [])
    check("盾到期删除", "test" not in e2["shields"])
    # 4. buffs 到期删
    p["effects"]["atk_up"] = {"stacks": 1, "expire": 3.0, "stat": "atk", "op": "mul", "mult": 1.30}
    b2._now = 2.0
    _settle_time_effects(b2, [])
    check("buff 未到期仍在", "atk_up" in ((p).get("effects") or {}))
    b2._now = 4.0
    _settle_time_effects(b2, [])
    check("buff 到期删除", "atk_up" not in ((p).get("effects") or {}))


    # 5. 过期控制：act 前 expire 已到点 → 自然消失不拦截
    p["effects"]["stun"] = {"stacks": 1, "expire": 1.0, "mode": "skip"}
    b2._now = 5.0
    hp0 = e2["hp"]
    human_land(b2, "attack", None, p)
    check("过期控制自然消失（不拦截）", "stun" not in ((p).get("effects") or {}))
    check("过期控制后正常攻击", e2["hp"] < hp0, f"hp={e2['hp']}")


def test_dot_interval_n74():
    """N7.4 DOT interval：绝对时刻跳、跨多刻补跳、同刻不重复。"""
    print("【N4.9 N7.4 DOT interval：按 interval 绝对时刻跳】")
    from saintess_engine.battle.schedule import _settle_time_effects as _ste
    e = make_actor(uid="e_dot", name="靶", side="enemy", kind="monster", hp=1000,
                   max_hp=1000, atk=1, spd=10, level=1)
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": [e]})
    # 本测试只验「跳刻/补跳节奏」，伤害值按**当前规则表**推算（2026-09-11 DOT 公式统一后
    #   burn = matk×0.6 + max_hp 0.5%，且 pct 受 pct_cap 单层上限约束），不写死数字：
    #   条目 pct 覆盖 3% → 被 pct_cap(1%) 压住 → 1000×0.01×2 层 = 20/跳
    from saintess_engine.battle.state_effects import state_def as _sd
    _per = (_sd("burn") or {}).get("period") or {}
    _cap = float(_per.get("pct_cap") or 0)
    _pct = min(0.03, _cap) if _cap else 0.03
    _jump = int(1000 * _pct * 2)
    e["effects"]["burn"] = {"stacks": 2, "pct": 0.03}
    b._now = 0.0
    _ste(b, [])
    hp0 = e["hp"]
    check("首跳延迟（0.0 不跳）", e["hp"] == hp0)
    check("dot_next 登记 1.0", abs(float(e["dot_next"].get("burn", 0)) - 1.0) < 1e-9)
    b._now = 1.5
    _ste(b, [])
    hp1 = e["hp"]
    check(f"1.5 跳 1 次（{_jump} 伤）", hp0 - hp1 == _jump, f"掉血 {hp0 - hp1}")
    b._now = 4.2
    _ste(b, [])
    hp2 = e["hp"]
    check(f"4.2 补跳 3 次（{_jump * 3} 伤）", hp1 - hp2 == _jump * 3, f"掉血 {hp1 - hp2}")
    check("dot_next 推进到 5.0", abs(float(e["dot_next"].get("burn", 0)) - 5.0) < 1e-9)
    hp3 = e["hp"]
    _ste(b, [])
    check("同刻重复 settle 不重复跳", e["hp"] == hp3)


def test_recover_second_segment_t14():
    """【N4.10 第二段（收招）耗时：内容侧供体 + 两段相加 + 零段逐位等值（T14）】

    引擎只做「两段相加」（`schedule.recover_time` / `recover_base_of`），
    形状与数值全在内容侧（`TIME_MODEL.recover` / `.recover_shape`）。
    本包现 `recover` 段全 0 ⇒ 行为与「只有一段」逐位相同；反证把 0.5 灌进去证明第二段是活的。
    """
    from saintess_engine.battle import schedule as _sch
    from saintess_engine.battle.stats import actor_spd as _aspd
    from content.mech import time_model as TM
    from content.mech import params as PR

    _recs = [TM.recover_base(k) for k in ("attack", "skill", "defend", "item")]
    check("recover 段读得到（4 个类别全 0 = 只有一段）", _recs == [0.0] * 4, str(_recs))
    check("未声明类别回落默认项", TM.recover_base("不存在的类别") == 0.0)
    check("供体转发（params.recover_model / recover_base）",
          PR.recover_model(50, 0.0) == 0.0 and PR.recover_base("skill") == 0.0)
    check("引擎第二段口可调（recover_time）", _sch.recover_time(50, 0.0) == 0.0)

    p = mk_player("战士", 12)
    b = BT_NEW("monster", sides={"player": [p], "enemy": [mk_monster(hp=99999, atk=1)]})
    now = float(b._now)
    p["ct"] = now
    spd = _aspd(b, p)
    _sch._after_act(b, p, "attack")
    check("★零段等值：ct - now 逐位等于第一段",
          p["ct"] == now + _sch.action_time(spd, _sch.action_base_of("attack")),
          f"ct={p['ct']} now={now} spd={spd}")

    # 反证（有牙）：临时把 recover 段改成非 0 ⇒ 第二段真的进 ct；recover_shape=flat ⇒ 不吃速度
    _orig = TM.time_model
    _cfg = dict(TM.time_model())
    try:
        _rec = dict(_cfg.get("recover") or {})
        _rec["attack"] = 0.5
        _m1 = dict(_cfg)
        _m1["recover"] = _rec
        TM.time_model = lambda: _m1
        check("反证：recover.attack=0.5 ⇒ 引擎读得到 0.5", _sch.recover_base_of("attack") == 0.5)
        p2 = mk_player("战士", 12)
        b2 = BT_NEW("monster", sides={"player": [p2], "enemy": [mk_monster(hp=99999, atk=1)]})
        now2 = float(b2._now)
        p2["ct"] = now2
        spd2 = _aspd(b2, p2)
        _sch._after_act(b2, p2, "attack")
        # 手算第二段（sqrt 形状：base × sqrt(spd_ref / spd)），不调被测函数
        _exp2 = 0.5 * math.sqrt(50.0 / max(float(spd2 or 0), 1.0))
        check("反证：ct = now + 第一段 + 第二段(0.5×sqrt(50/spd))",
              p2["ct"] == now2 + _sch.action_time(spd2, _sch.action_base_of("attack")) + _exp2,
              f"ct={p2['ct']} now={now2} spd={spd2} exp2={_exp2}")

        _m2 = dict(_cfg)
        _m2["recover"] = _rec
        _m2["recover_shape"] = "flat"
        TM.time_model = lambda: _m2
        check("recover_shape=flat ⇒ 收招不吃速度（spd=1 与 spd=200 同值）",
              TM.recover_time(1, 0.5) == TM.recover_time(200, 0.5) == 0.5)
    finally:
        TM.time_model = _orig
    check("还原后第二段归零（等值）", TM.recover_base("attack") == 0.0)


def main():
    print("=== N4 saintess_engine CTB 调度测试 ===")
    test_full_battle_victory()
    test_full_battle_defeat()
    test_speed_order()
    test_human_act_advance()
    test_dot_tick()
    test_flee()
    test_real_data_spd0_player()
    test_time_effects_n72()
    test_dot_interval_n74()
    test_recover_second_segment_t14()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
