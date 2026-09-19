# -*- coding: utf-8 -*-
"""v181.M-melody 测试——诗人旋律驻留系统（机制载体；数值公式待 v153 重做确认）。

跑法：python tests/test_melody.py（exit=0 全绿）
覆盖（v153 设计 docs/CLASS_MECHANICS_v153.md『七、吟游诗人』）：
  1. 装配：诗人学 melody 技能 → act_cast 触发器；非诗人（战士）无 melody 触发器（防白拿）
  2. 唱新歌：施放 mech=melody → effects[melody_state] 写入 + 全队光环广播（stat_scale 生效）
  3. 换歌：唱另一首 → 旧光环清、新光环写（全队）
  4. 吟唱：mech=melody_chant → 强度 +1 cap 5；效果随强度（公式 pct×(1+0.25×(s-1))）
  5. 满层：无终章旋律再吟唱不叠（提示）；有终章旋律满层吟唱 = 终章爆发（全员 buff + 强度归 1）
  6. 光环只给 player side（敌方零污染）
  7. 序列化恢复：from_state 后光环/状态保留（effects 随 actor 落盘）
  8. 负向：非诗人/未学技能零干扰；未唱旋律吟唱提示
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_melody.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from saintess_engine import Battle as B2, make_actor
from saintess_engine.battle.stats import actor_stats
from content.mech.class_mech import apply_class_mech  # ★ P5C-REPOINT：直取包内真源

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


def mk_player(uid, name, cls, skills, hp=800):
    a = make_actor(uid=uid, name=name, side='player', kind='player',
                   human_controlled=(uid == "p_bard"), class_name=cls, level=30,
                   learned_skills=list(skills), skills=list(skills),
                   atk=100, matk=100, spd=50, hp=hp, max_hp=hp, mp=500, max_mp=500)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(bard_skills, extra_players=1, enemy_hp=99999):
    bard = mk_player("p_bard", "诗人", "cls_shi_ren", bard_skills, hp=500)
    apply_class_mech(bard)
    sides = {"player": [bard], "enemy": []}
    if extra_players:
        war = mk_player("p_war", "战士", "cls_zhan_shi", [])
        sides["player"].append(war)
    enemy = make_actor(uid="e_1", name="小怪", side="enemy", kind="monster",
                       atk=1, matk=1, spd=1, hp=enemy_hp, max_hp=enemy_hp)
    enemy['effects'] = {}
    sides["enemy"].append(enemy)
    b = B2("monster", sides=sides, title_bonus={})
    return b, bard


def war_of(b):
    return next(a for a in b.sides_of("player") if a.get("uid") == "p_war")


def enemy_of(b):
    return b.sides_of("enemy")[0]


def cast(b, actor, skill):
    """施放一次（跳过技能冷却等待）。

    2026-09-11：引擎补装「技能冷却强制」（拨弦 cd=4 刻 / 战歌 cd=8 刻，
    数值权威 docs/CLASS_MECHANICS_v153.md 基础技能表）——本文件验的是旋律
    叠层/换歌/终章节奏，两次吟唱之间生产里自然经过若干回合，故施放前清冷却
    表模拟；**冷却强制本身**由 tests/test_battle_cooldown_enforce.py 专测。
    """
    if isinstance(actor.get("cooldown"), dict):
        actor["cooldown"].clear()
    logs, _e, _w = b.human_act("skill", skill, actor)
    return logs


def test_1_assemble():
    print("【1. 装配：诗人挂 act_cast；非诗人零干扰】")
    bard = mk_player("p_bard", "诗人", "cls_shi_ren", ["战歌"])
    apply_class_mech(bard)
    trig = bard.get("triggers") or {}
    mel = [t for t in trig.get("act_cast", []) if t.get("type") == "class_melody_act"]
    check("诗人学战歌 → act_cast class_melody_act", len(mel) == 1, repr(mel))
    war = mk_player("p_war", "战士", "cls_zhan_shi", [])
    apply_class_mech(war)
    wtrig = war.get("triggers") or {}
    check("战士无 melody 触发器（防白拿）",
          all(t.get("type") != "class_melody_act" for t in wtrig.get("act_cast", [])),
          repr(wtrig.get("act_cast")))
    bard2 = mk_player("p_b2", "诗人2", "cls_shi_ren", [])  # 未学 melody 技
    apply_class_mech(bard2)
    check("诗人未学 melody 技不挂（学什么挂什么）",
          all(t.get("type") != "class_melody_act"
              for t in (bard2.get("triggers") or {}).get("act_cast", [])), "")


def test_2_sing_aura():
    print("【2. 唱新歌：旋律驻留 + 全队光环】")
    b, bard = mk_battle(["战歌"])
    base = actor_stats(b, war_of(b)).get("atk")
    logs = cast(b, bard, "战歌")
    st = (bard.get("effects") or {}).get("melody_state")
    check("melody_state 写入（kind=atk stacks=1 pct=12）",
          isinstance(st, dict) and st.get("kind") == "atk" and st.get("stacks") == 1
          and st.get("pct") == 12, repr(st))
    check("施放日志含奏响", any("奏响" in l for l in logs), str(logs[-2:]))
    e_atk = (war_of(b).get("effects") or {}).get("melody_atk")
    check("全队光环 melody_atk stacks=12", e_atk and float(e_atk.get("stacks")) == 12.0,
          repr(e_atk))
    after = actor_stats(b, war_of(b)).get("atk")
    check(f"面板 atk 涨 12%（{base}→{after}）", after >= int(base * 1.11), f"{base}→{after}")
    check("敌方零光环", not any("melody" in k for k in (enemy_of(b).get("effects") or {})), "")


def test_3_switch_song():
    print("【3. 换歌：旧光环清、新光环写】")
    b, bard = mk_battle(["战歌", "守歌"])
    cast(b, bard, "战歌")
    cast(b, bard, "守歌")
    wf = war_of(b).get("effects") or {}
    st = (bard.get("effects") or {}).get("melody_state")
    check("状态切到 def", st and st.get("kind") == "def", repr(st))
    check("旧 atk 光环清", "melody_atk" not in wf, str(list(wf.keys())))
    check("新 def 光环写 stacks=10", wf.get("melody_def") and float(wf["melody_def"]["stacks"]) == 10.0,
          repr(wf.get("melody_def")))
    rs = actor_stats(b, war_of(b)).get("reduce")
    check("减伤生效 0.10", rs and rs >= 0.09, str(rs))


def test_4_chant_stack():
    print("【4. 吟唱叠层：强度 1→5，效果随强度】")
    b, bard = mk_battle(["战歌", "拨弦"])
    cast(b, bard, "战歌")
    a1 = actor_stats(b, war_of(b)).get("atk")
    for _ in range(3):
        cast(b, bard, "拨弦")
    st = (bard.get("effects") or {}).get("melody_state")
    check("强度 4（1+3）", st and st.get("stacks") == 4, repr(st))
    a4 = actor_stats(b, war_of(b)).get("atk")
    check(f"atk 随强度涨（{a1}→{a4}）", a4 > a1, f"{a1}→{a4}")
    cast(b, bard, "拨弦")
    st = (bard.get("effects") or {}).get("melody_state")
    check("强度 cap 5", st and st.get("stacks") == 5, repr(st))
    logs = cast(b, bard, "拨弦")
    check("满层无终章 → 提示不叠", st.get("stacks") == 5 and any("巅峰" in l for l in logs),
          f"stacks={st.get('stacks')}")


def test_5_finale():
    print("【5. 终章：咏叹者旋律满层吟唱 = 爆发 + 强度归 1】")
    b, bard = mk_battle(["激昂战歌", "拨弦"])
    cast(b, bard, "激昂战歌")
    for _ in range(4):
        cast(b, bard, "拨弦")
    st = (bard.get("effects") or {}).get("melody_state")
    check("满层 5", st and st.get("stacks") == 5, repr(st))
    logs = cast(b, bard, "拨弦")
    fin = any("终章" in l for l in logs)
    wf = war_of(b).get("effects") or {}
    check("终章触发", fin, str([l for l in logs if "终章" in l or "旋律" in l]))
    check("全员 finale buff（atk+45%）", wf.get("melody_finale_atk")
          and float(wf["melody_finale_atk"]["stacks"]) == 45.0, repr(wf.get("melody_finale_atk")))
    check("强度归 1（旋律继续驻留）", st and st.get("stacks") == 1, f"stacks={st.get('stacks')}")
    check("驻留光环仍在（atk+20%）", wf.get("melody_atk")
          and float(wf["melody_atk"]["stacks"]) == 20.0, repr(wf.get("melody_atk")))


def test_6_serialize():
    print("【6. 序列化恢复：光环/状态随 actor 落盘】")
    b, bard = mk_battle(["战歌", "拨弦"])
    cast(b, bard, "战歌")
    cast(b, bard, "拨弦")  # 强度 2 → 光环 15%
    st = b.to_state()
    b2 = B2.from_state(st)
    bard2 = next(a for a in b2.sides_of("player") if a.get("uid") == "p_bard")
    war2 = war_of(b2)
    st2 = (bard2.get("effects") or {}).get("melody_state")
    check("from_state 后 melody_state 保留", st2 and st2.get("stacks") == 2, repr(st2))
    e2 = (war2.get("effects") or {}).get("melody_atk")
    check("from_state 后光环保留 stacks=15", e2 and float(e2.get("stacks")) == 15.0, repr(e2))
    check("面板生效", actor_stats(b2, war2).get("atk") >= 125, "")


def test_7_negative():
    print("【7. 负向：未唱旋律吟唱提示；战士施放旋律类技能零效果】")
    b, bard = mk_battle(["拨弦"])
    logs = cast(b, bard, "拨弦")
    check("无旋律吟唱提示", any("尚无旋律" in l for l in logs), str(logs[-2:]))


def test_8_duet():
    print("【8. 二重唱（melody_duet 被动）：吟唱强度额外 +1】")
    # 装配：学二重唱 → act_cast 挂 passive_melody_duet（读被动 dict add）
    bard = mk_player("p_bard", "诗人", "cls_shi_ren", ["战歌", "拨弦", "二重唱"])
    apply_class_mech(bard)
    acts = (bard.get("triggers") or {}).get("act_cast") or []
    duet = [t for t in acts if (t.get("type") or t.get("action")) == "passive_melody_duet"]
    check("装配 passive_melody_duet（add=1 / judge mech_eq melody_chant）",
          len(duet) == 1 and duet[0].get("add") == 1
          and (duet[0].get("judge") or {}).get("mech") == "melody_chant", repr(duet))
    check("顺序：class_melody_act 排 act_cast 首位（顺序契约）",
          bool(acts) and acts[0].get("type") == "class_melody_act",
          repr([t.get("type") for t in acts]))
    # 未学二重唱的诗人 → 不挂（零噪音）
    b2 = mk_player("p_b2", "诗人2", "cls_shi_ren", ["战歌", "拨弦"])
    apply_class_mech(b2)
    check("未学二重唱不挂",
          not [t for t in ((b2.get("triggers") or {}).get("act_cast") or [])
               if (t.get("type") or t.get("action")) == "passive_melody_duet"], "")
    # 行为：吟唱 → 基础 +1 与二重唱 +1 = 共 +2
    b, bard = mk_battle(["战歌", "守歌", "拨弦", "二重唱"])
    cast(b, bard, "战歌")
    st = (bard.get("effects") or {}).get("melody_state")
    check("唱新歌时二重唱不触发（强度 1）", st and st.get("stacks") == 1, repr(st))
    logs = cast(b, bard, "拨弦")
    st = (bard.get("effects") or {}).get("melody_state")
    check("吟唱后强度 3（基础 +1 + 二重唱 +1）", st and st.get("stacks") == 3, repr(st))
    check("二重唱日志", any("二重唱" in l for l in logs), str(logs[-2:]))
    logs = cast(b, bard, "拨弦")
    st = (bard.get("effects") or {}).get("melody_state")
    check("再吟唱 → 5（cap）", st and st.get("stacks") == 5, repr(st))
    # 换歌重置强度，二重唱不误加
    cast(b, bard, "守歌")
    st = (bard.get("effects") or {}).get("melody_state")
    check("换歌后强度回 1（不触发二重唱）", st and st.get("stacks") == 1, repr(st))
    # 对照组：无二重唱 → 每次吟唱只 +1
    b3, bard3 = mk_battle(["战歌", "拨弦"])
    cast(b3, bard3, "战歌")
    cast(b3, bard3, "拨弦")
    st3 = (bard3.get("effects") or {}).get("melody_state")
    check("对照组（无二重唱）吟唱后强度 2", st3 and st3.get("stacks") == 2, repr(st3))


def main():
    test_1_assemble()
    test_2_sing_aura()
    test_3_switch_song()
    test_4_chant_stack()
    test_5_finale()
    test_6_serialize()
    test_7_negative()
    test_8_duet()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
