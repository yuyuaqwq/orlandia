# -*- coding: utf-8 -*-
"""N5b4-5E 验证：战斗级注入钩子（target_picker / on_event）。

引擎小扩展（零游戏知识）：
- target_picker(battle, actor) -> Optional[actor]：自动 actor 行动未指定 target 时
  先问外部"打谁"（副本仇恨/嘲讽注入点）；None 回落默认敌对目标。
- on_event(battle, evt_name, ctx, logs)：事件总线 fire 尾部通知外部观察者
  （命令层记账/团队技能广播/存活同步）。

跑法：python tests/test_battle_n5b4e_hooks.py
"""
import os
import sys
import tempfile

os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "game.db")
os.environ["GWEN_TEST_MODE"] = "1"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
sys.path.insert(0, _PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from content.persistence.handles import init_db  # noqa: E402
init_db()

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


def mk_player_actor(uid, hp=500):
    """战士 lv1 玩家 actor（面板聚合走 class）。"""
    from saintess_engine import make_actor
    return make_actor(uid=uid, name=uid, side="player", kind="player",
                      human_controlled=True, class_name="战士", level=1,
                      equipment={}, skills=[], learned_skills=[],
                      hp=hp, max_hp=hp)


def mk_auto_enemy(uid="e1", atk=12):
    """自动攻击怪 actor（无 class_name 直读字段）。"""
    from saintess_engine import make_actor
    return make_actor(uid=uid, name=uid, side="enemy", kind="monster",
                      human_controlled=False, auto_act={"act": {"type": "attack"}},
                      hp=1000, max_hp=1000, atk=atk, spd=50)


def test_target_picker():
    print("【N5b4-5E target_picker：自动怪打外部指定目标】")
    from saintess_engine import Battle as B2
    p1, p2 = mk_player_actor("p1"), mk_player_actor("p2")
    e = mk_auto_enemy()
    # picker 指定 p2（打"第二个人"——模拟仇恨选目标）
    b = B2("monster", sides={"player": [p1, p2], "enemy": [e]},
           target_picker=lambda battle, actor: battle.sides_of("player")[1])
    hp1, hp2 = p1.get("hp"), p2.get("hp")
    logs, ended = b.actor_auto(e)
    check("自动怪行动产生日志", bool(logs))
    check("p2 被选为目标掉血", p2.get("hp", 0) < hp2, f"p2 {hp2}->{p2.get('hp')}")
    check("p1 未被选中不掉血", p1.get("hp", 0) == hp1, f"p1 {hp1}->{p1.get('hp')}")


def test_target_picker_none_fallback():
    print("【N5b4-5E target_picker 返回 None → 回落默认目标】")
    from saintess_engine import Battle as B2
    p1, p2 = mk_player_actor("p1"), mk_player_actor("p2")
    e = mk_auto_enemy()
    b = B2("monster", sides={"player": [p1, p2], "enemy": [e]},
           target_picker=lambda battle, actor: None)  # 放弃决策
    hp1, hp2 = p1.get("hp"), p2.get("hp")
    logs, ended = b.actor_auto(e)
    # 默认 = hostile 首个存活 → p1
    check("回落默认打 p1", p1.get("hp", 0) < hp1, f"p1 {hp1}->{p1.get('hp')}")
    check("p2 不掉血", p2.get("hp", 0) == hp2, f"p2 {hp2}->{p2.get('hp')}")


def test_target_picker_dead_target_resolves():
    print("【N5b4-5E picker 目标已死 → 引擎不炸（落地按存活过滤）】")
    from saintess_engine import Battle as B2
    p1, p2 = mk_player_actor("p1"), mk_player_actor("p2")
    p2["hp"] = 0  # picker 指定的目标已死
    e = mk_auto_enemy()
    b = B2("monster", sides={"player": [p1, p2], "enemy": [e]},
           target_picker=lambda battle, actor: battle.sides_of("player")[1])
    hp1 = p1.get("hp")
    logs, ended = b.actor_auto(e)
    # 引擎落地对死者不重复结算；不崩即可（目标无效 → 无伤害或回落）
    check("目标已死场景不崩", isinstance(logs, list) and p1.get("hp", 0) <= hp1,
          f"logs={logs[:2]} p1={p1.get('hp')}")


def _mk_observer(seen):
    """记录 (evt, info.name 或 actor.uid) 的观察者。"""
    def _obs(battle, evt, ctx, logs):
        _name = ""
        _info = ctx.get("info") or {}
        if isinstance(_info, dict) and _info.get("name"):
            _name = _info["name"]
        elif isinstance(ctx.get("actor"), dict):
            _name = str(ctx["actor"].get("uid", "") or "")
        seen.append((evt, _name))
    return _obs


def test_on_event_observer():
    print("【N5b4-5E on_event：事件总线通知外部观察者】")
    from saintess_engine import Battle as B2
    p1 = mk_player_actor("p1", hp=800)
    e = mk_auto_enemy()
    seen = []
    b = B2("monster", sides={"player": [p1], "enemy": [e]},
           on_event=_mk_observer(seen))
    # 玩家普攻 → do_skill 内 act_cast（带 info）+ act 尾部 act_done
    logs, ended, who = b.human_act("attack", None, p1)
    evts = [s[0] for s in seen]
    check("观察者收到 act_cast", "act_cast" in evts, f"seen={evts}")
    check("观察者收到 act_done", "act_done" in evts, f"seen={evts}")
    check("act_cast ctx 带 info", any(s[0] == "act_cast" and s[1] for s in seen),
          f"seen={seen[:3]}")
    # 怪自动行动也通知（敌方段）
    seen.clear()
    logs, ended = b.actor_auto(e)
    evts2 = [s[0] for s in seen]
    check("自动怪行动也通知", "act_done" in evts2, f"seen={evts2}")


def test_on_event_error_isolated():
    print("【N5b4-5E on_event 异常不阻断战斗】")
    from saintess_engine import Battle as B2
    p1 = mk_player_actor("p1")
    e = mk_auto_enemy()

    def bad_obs(battle, evt, ctx, logs):
        raise RuntimeError("观察者炸了")

    b = B2("monster", sides={"player": [p1], "enemy": [e]}, on_event=bad_obs)
    hp = p1.get("hp")
    logs, ended, who = b.human_act("attack", None, p1)
    check("观察者异常不阻断", isinstance(logs, list))
    # 玩家普攻后怪还在/战斗正常
    check("战斗对象可用", getattr(b, "result", None) is None or b.result in (None,))
    # 不带观察者的对照也正常（回归）
    b2 = B2("monster", sides={"player": [mk_player_actor("p9")], "enemy": [mk_auto_enemy("e9")]})
    logs2, ended2, who2 = b2.human_act("attack", None, b2.sides_of("player")[0])
    check("无钩子战斗正常", isinstance(logs2, list))


def test_action_override_custom():
    """【N5b4-5a action_override：非引擎内置动作 → 外部回调执行+推ct】"""
    from saintess_engine import Battle as B2, make_actor
    # max_hp 留余量：+20 不被 clamp 挡住（mk_player_actor max=hp 会吃满回血）
    p1 = make_actor(uid="p1", name="p1", side="player", kind="player",
                    human_controlled=True, class_name="战士", level=1,
                    equipment={}, skills=[], learned_skills=[],
                    hp=700, max_hp=9999)
    # 静止怪（无 auto_act）——advance 不触发敌方行动，血量断言干净
    e = make_actor(uid="e1", name="e1", side="enemy", kind="monster",
                   human_controlled=False, hp=1000, max_hp=1000, spd=1)
    calls = []

    def ov(battle, action, actor, payload, target):
        if action == "use_item":
            calls.append(payload)
            if payload == "heal:20":
                actor["hp"] = min(actor.get("max_hp", 9999), (actor.get("hp", 0) or 0) + 20)
                return [f"💊 恢复 20 点生命！"], "defend"
            return ["道具无效果"], "attack"
        return None, None

    b = B2("monster", sides={"player": [p1], "enemy": [e]}, action_override=ov)
    logs, ended, who = b.human_act("use_item", "heal:20", p1)
    check("override 回调被调用", calls == ["heal:20"], str(calls))
    check("道具回血日志", any("恢复 20" in l for l in logs), str(logs[:2]))
    check("道具效果写回 actor hp>700", p1.get("hp", 0) > 700, f"hp={p1.get('hp')}")
    check("自定义动作推 ct（占刻）", p1.get("ct", 0) > 0, f"ct={p1.get('ct')}")


def test_action_override_unconsumed():
    print("【N5b4-5a action_override 未消费 → 回落未知行动提示】")
    from saintess_engine import Battle as B2
    p1 = mk_player_actor("p1")
    e = mk_auto_enemy(atk=1)
    b = B2("monster", sides={"player": [p1], "enemy": [e]},
           action_override=lambda battle, action, actor, payload, target: (None, None))
    ct_before = float(p1.get("ct", 0) or 0)
    logs, ended, who = b.human_act("weird_thing", None, p1)
    check("回落未知提示", any("未知" in l for l in logs), str(logs))
    # N10-B6b：初始 ct 已播种（>0）；未消费动作 = ct 保持初始值不推
    check("未消费不推 ct", abs(p1.get("ct", 0) - ct_before) < 1e-6, f"ct={p1.get('ct')} before={ct_before}")


def main():
    test_target_picker()
    test_target_picker_none_fallback()
    test_target_picker_dead_target_resolves()
    test_on_event_observer()
    test_on_event_error_isolated()
    test_action_override_custom()
    test_action_override_unconsumed()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    if FAILURES:
        for f in FAILURES:
            print(" -", f)
        sys.exit(1)


if __name__ == "__main__":
    # v181 flaky 修复：玩家真实面板含 ~3% 基础闪避（职业成长走 E.player_final_stats
    # 公式，actor["dodge"] 覆盖不了）——「回落默认打 p1」掉血断言偶发被闪避打成假红。
    import random as _r
    _r.seed(20260910)
    main()
