# -*- coding: utf-8 -*-
"""N5b4-5a I2 验收：saintess_engine 道具翻译器（game/commands/battle_item_use.py）。

覆盖（对齐设计 docs/archive/REFACTOR_v181P4_N5B5a_use_item_design.md §2/§3）：
- heal 纯数字（半身人 race item_effect 加成）
- mana:N / hm:hp,mp 双恢复
- buff:k1,k2 → EFFECT_ACTIONS 查表（actor.buffs 结构化条目）
- hot:hp%,mp%,turns → effects["regen_hot"] period 声明（V 系列统一）
- special:next_atk_up（hit buff）/ cc_immune（纯状态）/ shield_big（盾动词）
- 机制型缺口（summon）→ (None, None) 不消费
- foodfx 落 actor["food_effects"] + shield 特判
- cast 尾缀解析（cast:N → 数字秒；无 → 1.0）
- 端到端：action_override 回调接线

跑法：python tests/test_battle_item_use.py
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

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_player(cls="战士", level=10, hp_ratio=0.5, mp_ratio=1.0, race=None):
    from content.panel import player_final_stats
    from saintess_engine import make_actor
    st = player_final_stats(cls, level, {}, 0, {}, 1)
    return make_actor(uid="p_q1", name="测试勇者", side="player", kind="player",
                      human_controlled=True, class_name=cls, level=level,
                      hp=int(st["max_hp"] * hp_ratio), max_hp=int(st["max_hp"]),
                      mp=int(st["max_mp"] * mp_ratio), max_mp=int(st["max_mp"]),
                      equipment={}, skills=[], learned_skills=[],
                      race=race, evolve_path=1, class_tier=0, attributes={},
                      **{k: st[k] for k in ("atk", "matk", "def", "mdef", "spd", "crit") if k in st})


def mk_battle(p):
    from saintess_engine import Battle
    e = {"uid": "e_0", "name": "木桩", "side": "enemy", "kind": "monster",
         "hp": 99999, "max_hp": 99999, "atk": 0, "def": 0, "matk": 0, "mdef": 0,
         "spd": 1, "crit": 0.0, "level": 1, "human_controlled": False,
         "buffs": {}, "shields": {}, "state": {}, "ct": 0.0}
    return Battle(btype="monster", sides={"player": [p], "enemy": [e]})


def test_heal_direct():
    print("【I2.1 heal 纯数字：绝对恢复 + 日志 + clamp】")
    from content.mech.item_use import translate
    p = mk_player(hp_ratio=0.5)
    b = mk_battle(p)
    hp0 = p["hp"]
    logs, cast, recover = translate(b, p, "123")
    check("回血 123", p["hp"] == min(p["max_hp"], hp0 + 123), f"{hp0}→{p['hp']}")
    check("有日志", any("恢复" in x for x in logs), str(logs))
    check("cast 默认 1.0", cast == 1.0, f"cast={cast}")
    # clamp
    logs, cast, recover = translate(b, p, "99999")
    check("clamp max_hp", p["hp"] == p["max_hp"], f"hp={p['hp']}")


def test_heal_race_bonus():
    print("【I2.2 heal 半身人(halfling) race item_effect +10%】")
    from content.mech.item_use import translate
    # 半身人 race_stats item_effect=0.10 → 123 → 135（clamp max_hp）
    p = mk_player(hp_ratio=0.3, race="halfling")
    b = mk_battle(p)
    hp0 = p["hp"]
    logs, cast, recover = translate(b, p, "123")
    expect = min(p["max_hp"], hp0 + int(123 * 1.1))
    check("加成后回血 135（clamp）", p["hp"] == expect,
          f"{p['hp']} vs {expect}")


def test_mana_hm():
    print("【I2.3 mana:N + hm:hp,mp（clamp 上限）】")
    from content.mech.item_use import translate
    p = mk_player(hp_ratio=0.5, mp_ratio=0.5)
    b = mk_battle(p)
    mp0 = p["mp"]
    logs, cast, recover = translate(b, p, "mana:60")
    expect = min(p["max_mp"], mp0 + 60)
    check("回蓝 60（clamp）", p["mp"] == expect, f"{mp0}→{p['mp']} (期望 {expect})")
    # hm 双恢复（新玩家避免 mana 已被 clamp 打满）
    p2 = mk_player(hp_ratio=0.5, mp_ratio=0.5)
    b2 = mk_battle(p2)
    hp0, mp0 = p2["hp"], p2["mp"]
    logs, cast, recover = translate(b2, p2, "hm:50,40")
    check("hm 回血 50", p2["hp"] == min(p2["max_hp"], hp0 + 50), f"{hp0}→{p2['hp']}")
    check("hm 回蓝 40", p2["mp"] == min(p2["max_mp"], mp0 + 40), f"{mp0}→{p2['mp']}")


def test_buff_effect_actions():
    print("【I2.4 buff:k → EFFECT_ACTIONS 查表（actor.buffs 结构化）】")
    from content.mech.item_use import translate
    p = mk_player(hp_ratio=1.0)
    b = mk_battle(p)
    logs, cast, recover = translate(b, p, "buff:atk_up")
    bf = (p.get("effects") or {}).get("atk_up")
    check("atk_up 挂上结构化条目", isinstance(bf, dict) and bf.get("stat") == "atk",
          f"bf={bf}")
    check("mult=1.30", bf is not None and abs(float(bf.get("mult", 0)) - 1.30) < 1e-9,
          f"mult={bf and bf.get('mult')}")
    check("expire=now+3", bf is not None and abs(float(bf.get("expire", 0)) - 3.0) < 1e-9,
          f"expire={bf and bf.get('expire')}")
    # 复合 buff（龙涎 buff:atk_up,def_up 语义）
    p2 = mk_player(hp_ratio=1.0)
    b2 = mk_battle(p2)
    logs, cast, recover = translate(b2, p2, "buff:atk_up,def_up")
    check("复合双 buff", "atk_up" in (p2.get("effects") or {}) and "def_up" in (p2.get("effects") or {}),
          f"keys={list(((p2).get('effects') or {}).keys())}")


def test_hot_container():
    print("【I2.5 hot → effects[\"regen_hot\"] period 声明（V 系列统一）】")
    from content.mech.item_use import translate
    p = mk_player(hp_ratio=0.5)
    b = mk_battle(p)
    logs, cast, recover = translate(b, p, "hot:0.05,0.10,3")
    entry = (p.get("effects") or {}).get("regen_hot") or {}
    per = entry.get("period") or {}
    check("regen_hot 条目挂上", bool(entry), f"entry={entry}")
    check("period dir=heal + 数值", per.get("dir") == "heal"
          and abs(per.get("heal_pct", 0) - 0.05) < 1e-9
          and abs(per.get("mana_pct", 0) - 0.10) < 1e-9
          and per.get("turns") == 3, f"period={per}")
    # 再次吃（刷新——V 系列 setdefault 覆盖语义；调度按新 period 结算）
    translate(b, p, "hot:0.02,0.05,2")
    per2 = ((p.get("effects") or {}).get("regen_hot") or {}).get("period") or {}
    check("再次食用刷新 period", abs(per2.get("heal_pct", 0) - 0.02) < 1e-9
          and per2.get("turns") == 2, f"period2={per2}")


def test_special_next_atk_up():
    print("【I2.6 special:next_atk_up → hit buff】")
    from content.mech.item_use import translate
    p = mk_player(hp_ratio=1.0)
    b = mk_battle(p)
    logs, cast, recover = translate(b, p, "special:next_atk_up")
    bf = (p.get("effects") or {}).get("next_atk_up")
    check("next_atk_up 挂上", isinstance(bf, dict), f"bf={bf}")
    check("hit dmg_mult", bf is not None and isinstance(bf.get("hit"), dict)
          and abs(float(bf["hit"].get("dmg_mult", 0)) - 1.5) < 1e-9,
          f"hit={bf and bf.get('hit')}")


def test_special_cc_immune():
    print("【I2.7 special:cc_immune → 纯状态 buff】")
    from content.mech.item_use import translate
    p = mk_player(hp_ratio=1.0)
    b = mk_battle(p)
    logs, cast, recover = translate(b, p, "special:cc_immune")
    check("cc_immune 挂上", "cc_immune" in (p.get("effects") or {}), f"effects={list(((p).get('effects') or {}))}")


def test_special_shield():
    print("【I2.8 special:shield_big → 盾动词（effect_data json 数值）】")
    from content.mech.item_use import translate
    p = mk_player(hp_ratio=0.5)
    b = mk_battle(p)
    mx = p["max_hp"]
    logs, cast, recover = translate(b, p, 'special:shield_big:{"pct":0.30}')
    sh = p["shields"].get("potion_shield")
    check("护盾挂上", isinstance(sh, dict) and sh.get("value", 0) > 0,
          f"sh={sh}")
    if sh:
        check("盾值 = 30%max", abs(int(sh.get("value", 0)) - int(mx * 0.30)) <= 1,
              f"value={sh.get('value')} expect={int(mx * 0.30)}")


def test_special_gap_none():
    print("【I2.9 机制型缺口（summon/trap）→ None 不消费】")
    from content.mech.item_use import translate
    p = mk_player(hp_ratio=1.0)
    b = mk_battle(p)
    r = translate(b, p, "special:summon")
    check("summon → None", r is None, f"r={r}")
    r = translate(b, p, "special:phoenix")
    check("phoenix → None", r is None, f"r={r}")


def test_foodfx():
    print("【I2.10 foodfx → food_effects 容器 + shield 特判】")
    from content.mech.item_use import translate
    p = mk_player(hp_ratio=1.0)
    b = mk_battle(p)
    logs, cast, recover = translate(b, p, "foodfx:regen,meditate")
    check("food_effects 落容器", sorted(p.get("food_effects", [])) == ["meditate", "regen"],
          f"fe={p.get('food_effects')}")
    check("播报日志", any("获得" in x for x in logs), str(logs))
    # shield 特判：圣餐面包立即给盾
    p2 = mk_player(hp_ratio=0.5)
    b2 = mk_battle(p2)
    logs, cast, recover = translate(b2, p2, "foodfx:shield")
    sh = p2["shields"].get("food_shield")
    check("foodfx shield 立即给盾", isinstance(sh, dict) and sh.get("value", 0) > 0,
          f"sh={sh}")
    check("shield 落容器", "shield" in p2.get("food_effects", []),
          f"fe={p2.get('food_effects')}")


def test_cast_suffix():
    print("【I2.11 cast 尾缀解析】")
    from content.mech.item_use import translate
    p = mk_player(hp_ratio=0.5)
    b = mk_battle(p)
    logs, cast, recover = translate(b, p, "123;cast:2.0")
    check("cast:N → 第一段数字秒（第二段缺省 0）", cast == 2.0 and recover == 0.0,
          f"cast={cast} rec={recover}")
    logs, cast, recover = translate(b, p, "123;recovery:0.5")
    check("recovery:N → 第二段数字秒（第一段走缺省 1.0）", cast == 1.0 and recover == 0.5,
          f"cast={cast} rec={recover}")
    # ★ T14：两段并存 —— 旧码「二选一」会静默吞掉 recovery，现在两段都取
    logs, cast, recover = translate(b, p, "123;cast:2.0;recovery:0.5")
    check("两段并存 → 两段都取", cast == 2.0 and recover == 0.5, f"cast={cast} rec={recover}")
    hp0 = p["hp"]
    logs, cast, recover = translate(b, p, "hot:0.1,0,3;cast:1.4")
    check("hot+cast 剥离", cast == 1.4 and ((p.get("effects") or {}).get("regen_hot") or {}).get("period", {}).get("turns") == 3,
          f"cast={cast} hot={(p.get('effects') or {}).get('regen_hot')}")


def test_override_end_to_end():
    print("【I2.12 端到端：action_override 接线翻译器（战斗内喝药）】")
    from saintess_engine import Battle
    from content.mech.item_use import translate as _tr
    p = mk_player(hp_ratio=0.4)
    e = {"uid": "e_0", "name": "木桩", "side": "enemy", "kind": "monster",
         "hp": 99999, "max_hp": 99999, "atk": 0, "def": 0, "matk": 0, "mdef": 0,
         "spd": 1, "crit": 0.0, "level": 1, "human_controlled": False,
         "buffs": {}, "shields": {}, "state": {}, "ct": 0.0}
    b = Battle(btype="monster", sides={"player": [p], "enemy": [e]},
               action_override=lambda battle, action, actor, payload, target: (
                   _tr(battle, actor, payload, target) if action == "use_item"
                   else (None, None, None)))
    hp0 = p["hp"]
    # 纯 heal payload = 数字（模板 tpl_heal 产物），非 "heal:50"
    logs, ended, who = b.human_act("use_item", "50", p)
    check("喝药回血", p["hp"] > hp0, f"{hp0}→{p['hp']}")
    check("占刻推 ct", p.get("ct", 0) > 0, f"ct={p.get('ct')}")
    check("有日志", bool(logs), str(logs))
    # 未覆盖 special → 不消费不推 ct（回调返回 None → 引擎回落未知提示）
    p2 = mk_player(hp_ratio=0.5)
    b2 = Battle(btype="monster", sides={"player": [p2], "enemy": [e]},
                action_override=lambda battle, action, actor, payload, target: (
                    _tr(battle, actor, payload, target) if action == "use_item"
                    else (None, None, None)))
    ct_before = float(p2.get("ct", 0) or 0)
    logs, ended, who = b2.human_act("use_item", "special:summon", p2)
    # N10-B6b：初始 ct 已播种（>0）；未消费动作 = ct 保持初始值不推
    check("缺口道具不推 ct", abs(p2.get("ct", 0) - ct_before) < 1e-6, f"ct={p2.get('ct')} before={ct_before}")
    check("回落未知提示", any("未知" in x or "无法" in x or "未迁移" in x for x in logs),
          str(logs))


def test_purify():
    print("【I5.1 purify：模板判定 + 翻译器清除（saintess_engine effects 负面）】")
    from saintess_engine import Battle
    from saintess_engine.battle.effects import apply_effects
    from content.mech.item_use import translate as _tr
    from content.item_templates import tpl_purify, ItemContext, _b2_has_purifiable
    # 玩家带负面（stun 控制 + sleep 不可净化 + atk_up 正面）
    p = mk_player(hp_ratio=0.9)
    e = {"uid": "e_0", "name": "木桩", "side": "enemy", "kind": "monster",
         "hp": 99999, "max_hp": 99999, "atk": 0, "def": 0, "matk": 0, "mdef": 0,
         "spd": 1, "crit": 0.0, "level": 1, "human_controlled": False,
         "effects": {}, "shields": {}, "ct": 0.0}
    b = Battle(btype="monster", sides={"player": [p], "enemy": [e]})
    apply_effects(b, p, p, [{"action": "apply", "key": "stun", "mode": "skip",
                             "on": "caster", "turns": 2}], [])
    apply_effects(b, p, p, [{"action": "apply", "key": "sleep", "mode": "skip",
                             "on": "caster", "turns": 2}], [])
    apply_effects(b, p, p, [{"action": "apply", "key": "atk_up", "on": "caster",
                             "turns": 3}], [])
    check("负面挂上（stun）", "stun" in (p.get("effects") or {}))
    # 模板判定：有可净化负面（stun）→ consume + payload=purify:1
    d = {"name": "净化卷轴"}
    ctx = ItemContext.__new__(ItemContext)
    ctx.battle = b.to_state()
    ctx.data = d
    ctx.group_id = "g"; ctx.qq_id = "q1"
    r = tpl_purify(ctx)
    check("模板判定有负面 → consume", r.consume is True, f"consume={r.consume} text={r.text}")
    check("payload=purify:1", r.payload == "purify:1", f"payload={r.payload}")
    # 视图判定（模板同款 helper）在清除前应识别到负面
    _bstate1 = b.to_state()
    check("_b2_has_purifiable 有负面判定 True", _b2_has_purifiable(_bstate1) is True)
    # 翻译器清除：stun 清、sleep 不可净化保留、atk_up 正面保留
    logs, cast, recover = _tr(b, p, "purify:1")
    ef = p.get("effects") or {}
    check("stun 被净化", "stun" not in ef, f"effects={list(ef)}")
    check("sleep 保留（不可净化）", "sleep" in ef, f"effects={list(ef)}")
    check("atk_up 保留（正面）", "atk_up" in ef, f"effects={list(ef)}")
    check("净化日志", any("净化" in x for x in logs), str(logs))
    # 无负面场景：模板判定 consume=False
    p2 = mk_player(hp_ratio=0.9)
    b2 = Battle(btype="monster", sides={"player": [p2], "enemy": [dict(e)]})
    ctx2 = ItemContext.__new__(ItemContext)
    ctx2.battle = b2.to_state()
    ctx2.data = d
    ctx2.group_id = "g"; ctx2.qq_id = "q1"
    r2 = tpl_purify(ctx2)
    check("无负面 → 不消耗", r2.consume is False, f"consume={r2.consume}")
    check("_b2_has_purifiable 无负面判定 False", _b2_has_purifiable(b2.to_state()) is False)


def main():
    print("=== I2 saintess_engine 道具翻译器测试 ===")
    test_heal_direct()
    test_heal_race_bonus()
    test_mana_hm()
    test_buff_effect_actions()
    test_hot_container()
    test_special_next_atk_up()
    test_special_cc_immune()
    test_special_shield()
    test_special_gap_none()
    test_foodfx()
    test_cast_suffix()
    test_override_end_to_end()
    test_purify()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
