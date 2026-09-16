# -*- coding: utf-8 -*-
"""v181.G1 挽歌者「e_ 减益旋律」批测试——5 技能 + 2 被动（dirge_ctrl_up / dirge_debuff_dmg）。

设计权威 = docs/CLASS_MECHANICS_v153.md §七「吟游诗人 — 驻留旋律」B 线
（挽歌者 › 安魂歌者 › 镇魂挽者，L1106-1140）；落地范围 = docs/
docs/archive/REFACTOR_v181_GAP_CLOSURE_PLAN.md §3「挽歌 2 项」+ §4 步 4。
旧语义权威（死代码，只读对齐）= game/core/battle_mech.py `_melody_apply_e_buffs` /
`_m_melody_finale`（git 379a792^）+ game/core/passive_procs.py `dirge_debuffs` /
`dirge_ctrl_up` 两 handler。

范式（test_v181_channel_when 同款）：真实装配路径（apply_class_mech → triggers）
→ 取装配产物当 params → 直调动作（fire() 派发时正是把 trigger dict 逐条传动作，
_owner 由 fire 注入声明者自己）；另加 human_act 端到端集成与负向/防白拿。

覆盖：
 1. 数据落地：5 技能 melody/finale/pct 字段与 desc 数值一致（可追溯 v153）
 2. 装配：诗人学 e_ 旋律 → act_cast class_melody_act；两被动进 PASSIVE_PROC 落 triggers
 3. 驻留（敌方向）：5 技能逐条 → 敌方全体 effects 条目 + 面板下降；己方零污染
 4. 换歌跨方向：挽歌（敌）↔ 战歌（我）互清互写
 5. 终章·减益：镇魂歌/挽歌/终焉挽歌 → 敌方限时 debuff 数值 + 刻数
 6. 终章·控制：沉默之歌（silence 3 刻）/ 挽歌·沉（stun 3.5→3 刻）mode 正确
 7. dirge_ctrl_up：控制延 +1 刻（act_cast 终章路径 + skill_hit 路径 + 门 + 防白拿）
 8. dirge_debuff_dmg：负面种数乘区 min(per×n, cap) + 上限 + 零默认值
 9. 沉默之歌驻留：time_advance tick 封印（每 4 刻至多 1 次）+ 换歌停 tick
10. 集成：human_act 真实出手（推进时间/事件总线全通）
11. 负向：未学被动不挂；非施控技能不延长；缺字段零行为

跑法：python tests/test_v181_dirge.py（exit=0 全绿）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_v181_dirge.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor, effects as EFX  # noqa: E402
from saintess_engine.battle.stats import actor_stats  # noqa: E402
from saintess_engine.battle.effect_triggers import fire as bfire  # noqa: E402
from content.skills import skill_info
from content.mech import class_mech as CM  # noqa: E402  (import 即注册 39 动作)
from _engine_harness import boot as _eng_boot  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []

CLS = "cls_shi_ren"


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ❌ {name} {detail}")


# ---- 数据落地对照表（值全部来自 desc / v153 B 线表）----
#   技能 → (melody kind, finale token, melody_pct, melody_fin_pct, melody_fin_turns)
DIRGE_DATA = {
    "镇魂歌": ("e_spd", "e_spd", 15, 35, None),
    "挽歌": ("e_atk", "e_atk", 18, 40, None),
    "沉默之歌": ("e_silence", "silence", None, None, 3.0),
    "挽歌·沉": ("e_spd_hit", "stun", 20, None, 3.5),
    "终焉挽歌": ("e_all", "e_all", 25, 50, None),
}


def skill(name):
    return skill_info(CLS, name) or {}


def mk_player(uid, name, cls, skills, hp=800):
    a = make_actor(uid=uid, name=name, side='player', kind='player',
                   human_controlled=(uid == "p_bard"), class_name=cls, level=30,
                   learned_skills=list(skills), skills=list(skills),
                   atk=100, matk=100, spd=50, hp=hp, max_hp=hp, mp=500, max_mp=500)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(bard_skills, n_enemies=2, enemy_hp=99999):
    """诗人（诗人方）+ n 只怪（atk=100/spd=50 便于面板断言）。"""
    bard = mk_player("p_bard", "诗人", CLS, bard_skills, hp=800)
    CM.apply_class_mech(bard)
    sides = {"player": [bard], "enemy": []}
    for i in range(n_enemies):
        e = make_actor(uid=f"e_{i + 1}", name=f"怪{i + 1}", side="enemy", kind="monster",
                       atk=100, matk=100, spd=50, hp=enemy_hp, max_hp=enemy_hp,
                       **{"def": 80, "mdef": 60})
        e['effects'] = {}
        sides["enemy"].append(e)
    b = B2("monster", sides=sides, title_bonus={})
    return b, bard


def foes_of(b):
    return b.sides_of("enemy")


def trigs(actor, event):
    return (actor.get("triggers") or {}).get(event) or []


def call_action(b, action, params, caster, target=None):
    """按 fire() 契约直调动作（装配产物当 params；_owner = 声明者）。

    ★ P5D-REPOINT：原 `CM.install()`（宿主薄壳 `game/services/class_mech_proc.py::install`）
    在终态随宿主壳退役；其真源语义 = 「幂等注册动作」，而包内注册由
    `content/mech/class_mech.py` **import 期**完成（宿主薄壳自述「本函数保留为空委托」）。
    故此处改用测试侧等价装配口 `_engine_harness.boot`（幂等）—— 判据一条未动。
    """
    _eng_boot()
    h = EFX.ACTION_HANDLERS[action]
    logs = []
    h(b, caster, target, dict(params), logs)
    return logs


def sing(b, actor, name):
    """直调 class_melody_act 起手（等价 fire act_cast：ctx 注入 → 清形 → 摘除）。"""
    info = skill(name)
    b._fire_ctx = {"actor": actor, "info": info, "target": None}
    logs = call_action(b, "class_melody_act", {}, actor)
    return info, logs


def chant_finale(b, actor, name):
    """唱 → 直接顶满 5 层 → 再吟唱一次（触发终章）。全程不推进时间。"""
    sing(b, actor, name)
    st = (actor.get("effects") or {}).get("melody_state")
    if not isinstance(st, dict):
        return None, []
    st["stacks"] = 5
    b._fire_ctx = {"actor": actor, "info": {"mech": "melody_chant"}, "target": None}
    logs = call_action(b, "class_melody_act", {}, actor)
    return st, logs


def stk(actor, key):
    v = (actor.get("effects") or {}).get(key)
    return float(v.get("stacks", 0) or 0) if isinstance(v, dict) else None


# ============================================================
def test_1_data_fields():
    print("【1. 数据落地：5 技能 melody/finale 字段（可追溯 desc / v153）】")
    for name, (kind, fin, pct, fin_pct, fin_turns) in DIRGE_DATA.items():
        inf = skill(name)
        check(f"{name}：存在且 mech=melody", bool(inf) and inf.get("mech") == "melody", repr(inf)[:120])
        check(f"{name}：melody kind={kind}", inf.get("melody") == kind, repr(inf.get("melody")))
        check(f"{name}：finale={fin}", inf.get("finale") == fin, repr(inf.get("finale")))
        if pct is not None:
            check(f"{name}：melody_pct={pct}", inf.get("melody_pct") == pct, repr(inf.get("melody_pct")))
        if fin_pct is not None:
            check(f"{name}：melody_fin_pct={fin_pct}", inf.get("melody_fin_pct") == fin_pct,
                  repr(inf.get("melody_fin_pct")))
        if fin_turns is not None:
            check(f"{name}：melody_fin_turns={fin_turns}", inf.get("melody_fin_turns") == fin_turns,
                  repr(inf.get("melody_fin_turns")))
    # desc 数值可追溯核对（抽三条）
    check("镇魂歌 desc 含 速度 −15% / −35%",
          "速度 −15%" in skill("镇魂歌").get("desc", "") and "−35%" in skill("镇魂歌").get("desc", ""),
          skill("镇魂歌").get("desc", ""))
    check("挽歌 desc 含 攻击 −18% / −40%",
          "攻击 −18%" in skill("挽歌").get("desc", "") and "−40%" in skill("挽歌").get("desc", ""),
          skill("挽歌").get("desc", ""))
    check("终焉挽歌 desc 含 攻/速/命中 −25% / 全属性 −50%",
          "−25%" in skill("终焉挽歌").get("desc", "") and "−50%" in skill("终焉挽歌").get("desc", ""),
          skill("终焉挽歌").get("desc", ""))
    # 被动两条数据齐备（PASSIVE_PROC 声明的前置）
    pc = skill("镇魂安魂").get("passive") or {}
    check("镇魂安魂 passive={proc:dirge_ctrl_up, add:1}",
          pc.get("proc") == "dirge_ctrl_up" and pc.get("add") == 1, repr(pc))
    pd = skill("挽歌·极").get("passive") or {}
    check("挽歌·极 passive={proc:dirge_debuff_dmg, per_debuff:0.04, cap:0.40}",
          pd.get("proc") == "dirge_debuff_dmg" and pd.get("per_debuff") == 0.04
          and pd.get("cap") == 0.40, repr(pd))


def test_2_assemble():
    print("【2. 装配：e_ 旋律挂 act_cast；两被动进 triggers（学什么挂什么）】")
    bard = mk_player("p_bard", "诗人", CLS, list(DIRGE_DATA) + ["镇魂安魂", "挽歌·极", "拨弦"])
    CM.apply_class_mech(bard)
    mel = [t for t in trigs(bard, "act_cast") if (t.get("type") or t.get("action")) == "class_melody_act"]
    check("诗人学 e_ 旋律 → act_cast class_melody_act", len(mel) == 1, repr(mel))
    check("class_melody_act 排 act_cast 首位（顺序契约）",
          bool(trigs(bard, "act_cast")) and (trigs(bard, "act_cast")[0].get("type") == "class_melody_act"),
          repr([t.get("type") for t in trigs(bard, "act_cast")]))
    ext = [t for t in trigs(bard, "act_cast") if (t.get("type") or t.get("action")) == "passive_ctrl_extend"]
    check("dirge_ctrl_up → act_cast passive_ctrl_extend（add=1）",
          len(ext) == 1 and ext[0].get("add") == 1, repr(ext))
    ext_hit = [t for t in trigs(bard, "skill_hit") if (t.get("type") or t.get("action")) == "passive_ctrl_extend"]
    check("dirge_ctrl_up → also 挂 skill_hit（技能 mech2 控制路径）", len(ext_hit) == 1, repr(ext_hit))
    dm = [t for t in trigs(bard, "dmg_calc") if (t.get("type") or t.get("action")) == "passive_dmg_mult"]
    check("dirge_debuff_dmg → dmg_calc passive_dmg_mult",
          len(dm) == 1 and (dm[0].get("judge") or {}).get("kind") == "target_debuff_kinds", repr(dm))
    check("dirge_debuff_dmg 参数并入（per_debuff 0.04 / cap 0.40 / label 挽歌·极）",
          dm and dm[0].get("per_debuff") == 0.04 and dm[0].get("cap") == 0.40
          and dm[0].get("label") == "挽歌·极", repr(dm))
    # 未学 → 不挂（防白拿）
    b2 = mk_player("p_b2", "诗人2", CLS, ["挽歌"])
    CM.apply_class_mech(b2)
    check("未学镇魂安魂/挽歌·极 → 两被动零装配",
          not [t for t in trigs(b2, "act_cast") + trigs(b2, "skill_hit") + trigs(b2, "dmg_calc")
               if (t.get("type") or t.get("action")) in ("passive_ctrl_extend", "passive_dmg_mult")],
          repr(b2.get("triggers")))


def test_3_resident_enemy_aura():
    print("【3. 驻留（敌方向）：敌方全体挂 debuff + 面板下降；己方零污染】")
    cases = [
        ("镇魂歌", "melody_e_spd", 15, "spd"),
        ("挽歌", "melody_e_atk", 18, "atk"),
        ("挽歌·沉", "melody_e_spd_hit", 20, "spd"),
        ("终焉挽歌", "melody_e_all", 25, "atk"),
    ]
    for name, key, pct, stat in cases:
        b, bard = mk_battle([name])
        foes = foes_of(b)
        base = actor_stats(b, foes[0]).get(stat)
        info, logs = sing(b, bard, name)
        check(f"{name}：敌方 {key} stacks={pct}（层=目标 %）",
              stk(foes[0], key) == float(pct), repr(foes[0]["effects"].get(key)))
        check(f"{name}：敌方全体（{len(foes)} 个）都挂",
              all(isinstance((f.get("effects") or {}).get(key), dict) for f in foes), "")
        after = actor_stats(b, foes[0]).get(stat)
        check(f"{name}：敌方 {stat} 面板下降（{base}→{after}）", after < base, f"{base}→{after}")
        check(f"{name}：驻留条目常驻（expire=None）",
              (foes[0]["effects"][key] or {}).get("expire") is None,
              repr(foes[0]["effects"][key]))
        own = [k for k in (bard.get("effects") or {}) if str(k).startswith("melody_e")]
        check(f"{name}：己方零污染（无 melody_e_*）", not own, repr(own))
        check(f"{name}：驻留日志（敌方全体受挫）", any("敌方全体受挫" in x for x in logs),
              str(logs[-2:]))
    # 沉默之歌：无面板条目（周期封印走时钟 tick）
    b, bard = mk_battle(["沉默之歌"])
    sing(b, bard, "沉默之歌")
    st = (bard.get("effects") or {}).get("melody_state") or {}
    check("沉默之歌：melody_state.kind=e_silence", st.get("kind") == "e_silence", repr(st))
    check("沉默之歌：不写面板条目（e_silence → None）",
          not any(str(k).startswith("melody_e") for f in foes_of(b) for k in (f.get("effects") or {})),
          "")


def test_4_switch_song_direction():
    print("【4. 换歌跨方向：挽歌（敌）↔ 战歌（我）互清互写】")
    b, bard = mk_battle(["挽歌", "战歌"])
    foe = foes_of(b)[0]
    sing(b, bard, "挽歌")
    check("唱挽歌 → 敌方 melody_e_atk 在 / 己方无", "melody_e_atk" in (foe.get("effects") or {})
          and "melody_atk" not in (bard.get("effects") or {}), repr(foe.get("effects")))
    sing(b, bard, "战歌")
    check("换战歌 → 敌方旧减益清", "melody_e_atk" not in (foe.get("effects") or {}),
          repr(foe.get("effects")))
    check("换战歌 → 己方 melody_atk 写（stacks=12）", stk(bard, "melody_atk") == 12.0,
          repr((bard.get("effects") or {}).get("melody_atk")))
    sing(b, bard, "挽歌")
    check("换回挽歌 → 己方光环清 + 敌方减益回",
          "melody_atk" not in (bard.get("effects") or {}) and "melody_e_atk" in (foe.get("effects") or {}),
          f"own={list((bard.get('effects') or {}).keys())} foe={list((foe.get('effects') or {}).keys())}")


def test_5_finale_enemy_debuff():
    print("【5. 终章·减益：敌方限时 debuff 数值 + 刻数（expire=now+buff_turns）】")
    for name, key, pct, turns in (("镇魂歌", "melody_e_fin_spd", 35, 8),
                                  ("挽歌", "melody_e_fin_atk", 40, 8),
                                  ("终焉挽歌", "melody_e_fin_all", 50, 10)):
        b, bard = mk_battle([name])
        foe = foes_of(b)[0]
        st, logs = chant_finale(b, bard, name)
        check(f"{name}：终章日志", any("终章" in x for x in logs), str(logs[-2:]))
        ent = (foe.get("effects") or {}).get(key)
        check(f"{name}：敌方 {key} stacks={pct}", isinstance(ent, dict) and float(ent["stacks"]) == float(pct),
              repr(ent))
        check(f"{name}：刻数 = {turns} 刻（expire=now+{turns}）",
              isinstance(ent, dict) and abs(float(ent["expire"]) - (b._now + turns)) < 1e-6,
              f"expire={ent.get('expire') if isinstance(ent, dict) else None} now={b._now}")
        check(f"{name}：强度归 1（旋律继续驻留）", st.get("stacks") == 1, repr(st))
    # 终焉挽歌终章：全属性 −50%（驻留 −25% 与终章 −50% 乘算）
    b, bard = mk_battle(["终焉挽歌"])
    foe = foes_of(b)[0]
    chant_finale(b, bard, "终焉挽歌")
    stt = actor_stats(b, foe)
    check("终焉挽歌终章：atk 100 →37（驻留×0.75 × 终章×0.5，int 截断）",
          stt.get("atk") == 37, repr(stt.get("atk")))
    check("终焉挽歌终章：matk 100→50（−50%）", stt.get("matk") == 50, repr(stt.get("matk")))
    check("终焉挽歌终章：def 80→40（−50%）", stt.get("def") == 40, repr(stt.get("def")))


def test_6_finale_control():
    print("【6. 终章·控制：沉默之歌 silence 3.0 刻 / 挽歌·沉 stun 3.5→3 刻（mode 正确）】")
    b, bard = mk_battle(["沉默之歌"])
    foe = foes_of(b)[0]
    st, logs = chant_finale(b, bard, "沉默之歌")
    ent = (foe.get("effects") or {}).get("silence")
    check("沉默之歌终章：敌方全体 silence（mode=no_skill）",
          isinstance(ent, dict) and ent.get("mode") == "no_skill", repr(ent))
    check("沉默之歌终章：3.0 刻（engine int 化 3）",
          isinstance(ent, dict) and abs(float(ent["expire"]) - (b._now + 3)) < 1e-6,
          f"expire={ent.get('expire') if isinstance(ent, dict) else None} now={b._now}")
    check("沉默之歌终章：全体（2 个敌人都沉默）",
          all(isinstance((f.get("effects") or {}).get("silence"), dict) for f in foes_of(b)), "")
    b, bard = mk_battle(["挽歌·沉"])
    foe = foes_of(b)[0]
    st, logs = chant_finale(b, bard, "挽歌·沉")
    ent = (foe.get("effects") or {}).get("stun")
    check("挽歌·沉终章：敌方位身 stun（mode=skip）",
          isinstance(ent, dict) and ent.get("mode") == "skip", repr(ent))
    check("挽歌·沉终章：3.5 刻 → int 3（半刻引擎不支持）",
          isinstance(ent, dict) and abs(float(ent["expire"]) - (b._now + 3)) < 1e-6,
          f"expire={ent.get('expire') if isinstance(ent, dict) else None} now={b._now}")


def test_7_dirge_ctrl_up():
    print("【7. dirge_ctrl_up（镇魂安魂）：挽歌系控制时长 +1 刻】")
    # 对照：未学 → 沉默终章 3 刻
    b0, bard0 = mk_battle(["沉默之歌"])
    chant_finale(b0, bard0, "沉默之歌")
    ent0 = (foes_of(b0)[0].get("effects") or {}).get("silence")
    check("对照（未学镇魂安魂）：终章沉默 3 刻", abs(float(ent0["expire"]) - (b0._now + 3)) < 1e-6,
          repr(ent0))
    # 学 → 装配产物直调（act_cast 终章路径）
    b, bard = mk_battle(["沉默之歌", "镇魂安魂"])
    chant_finale(b, bard, "沉默之歌")
    foe = foes_of(b)[0]
    ent = (foe.get("effects") or {}).get("silence")
    p_ext = [t for t in trigs(bard, "act_cast") if (t.get("type") or t.get("action")) == "passive_ctrl_extend"][0]
    b._fire_ctx = {"actor": bard, "info": {"mech": "melody", "finale": "silence"}, "target": None}
    logs = call_action(b, "passive_ctrl_extend", p_ext, bard)
    check("终章沉默被延长至 4 刻（3+1）", abs(float(ent["expire"]) - (b._now + 4)) < 1e-6, repr(ent))
    check("延长日志（挽歌延长【silence】+1 刻）", any("挽歌延长" in x and "silence" in x for x in logs),
          str(logs))
    # skill_hit 路径：技能 mech2 控制（亡者挽歌 沉默 2 刻）→ +1 = 3 刻
    b2, bard2 = mk_battle(["挽歌", "镇魂安魂"], n_enemies=1)
    foe2 = foes_of(b2)[0]
    foe2.setdefault("effects", {})["silence"] = {"expire": b2._now + 2, "mode": "no_skill", "stacks": 1}
    b2._fire_ctx = {"actor": bard2, "info": {"mech2": "silence"}, "target": foe2}
    call_action(b2, "passive_ctrl_extend", p_ext, bard2, foe2)
    check("skill_hit 路径：mech2 沉默 2 刻 → 3 刻",
          abs(float(foe2["effects"]["silence"]["expire"]) - (b2._now + 3)) < 1e-6,
          repr(foe2["effects"]["silence"]))
    # 门：非施控技能不延长（info 无控制字段）
    foe2["effects"]["silence"] = {"expire": b2._now + 2, "mode": "no_skill", "stacks": 1}
    b2._fire_ctx = {"actor": bard2, "info": {"mech": "melody", "finale": "e_atk"}, "target": foe2}
    logs2 = call_action(b2, "passive_ctrl_extend", p_ext, bard2, foe2)
    check("门：非施控技能（finale=e_atk）不延长",
          abs(float(foe2["effects"]["silence"]["expire"]) - (b2._now + 2)) < 1e-6 and not logs2,
          repr(foe2["effects"]["silence"]))
    # 缺字段（add 缺失）= 无此行为（零默认值铁律）
    bad = dict(p_ext)
    bad.pop("add", None)
    foe2["effects"]["silence"] = {"expire": b2._now + 2, "mode": "no_skill", "stacks": 1}
    b2._fire_ctx = {"actor": bard2, "info": {"mech2": "silence"}, "target": foe2}
    call_action(b2, "passive_ctrl_extend", bad, bard2, foe2)
    check("零默认值：add 缺失 → 不延长",
          abs(float(foe2["effects"]["silence"]["expire"]) - (b2._now + 2)) < 1e-6,
          repr(foe2["effects"]["silence"]))


def test_8_dirge_debuff_dmg():
    print("【8. dirge_debuff_dmg（挽歌·极）：负面种数乘区 min(per×n, cap)】")
    bard = mk_player("p_bard", "诗人", CLS, ["挽歌·极"])
    CM.apply_class_mech(bard)
    dm = [t for t in trigs(bard, "dmg_calc") if (t.get("type") or t.get("action")) == "passive_dmg_mult"]
    check("装配 passive_dmg_mult（judge=target_debuff_kinds）",
          len(dm) == 1 and (dm[0].get("judge") or {}).get("kind") == "target_debuff_kinds", repr(dm))
    b, bard = mk_battle(["挽歌·极"], n_enemies=1)
    foe = foes_of(b)[0]

    def dmg_mult(neg_keys, params=None):
        foe["effects"] = {k: {"stacks": 1} for k in neg_keys}
        ctx = {"actor": bard, "target": foe, "info": {}, "dmg": 100, "mult": 1.0}
        b._fire_ctx = ctx
        call_action(b, "passive_dmg_mult", params if params is not None else dm[0], bard, foe)
        return float(ctx.get("mult", 1.0))

    NEG = ["spd_down", "stun", "silence", "poison", "curse", "hunt_mark",
           "soul_mark", "burn", "bleed", "corros", "reduce", "holy_weaken"]
    check("0 个负面 → ×1.00", abs(dmg_mult([]) - 1.0) < 1e-9, "")
    check("3 个负面 → ×1.12（3×0.04）", abs(dmg_mult(NEG[:3]) - 1.12) < 1e-9, "")
    check("5 个负面 → ×1.20（5×0.04）", abs(dmg_mult(NEG[:5]) - 1.20) < 1e-9, "")
    check("12 个负面 → 封顶 ×1.40（cap 0.40）", abs(dmg_mult(NEG) - 1.40) < 1e-9, "")
    # 增益条目不算负面（atk_up 无 negative / 非 on=target）
    check("增益条目不计入种数（atk_up + 3 负面 → ×1.12）",
          abs(dmg_mult(NEG[:3] + ["atk_up"]) - 1.12) < 1e-9, "")
    # 零默认值：缺 per_debuff / cap → 无此行为
    p_bad = dict(dm[0])
    p_bad.pop("per_debuff", None)
    check("零默认值：per_debuff 缺失 → ×1.00", abs(dmg_mult(NEG[:3], p_bad) - 1.0) < 1e-9, "")
    p_bad2 = dict(dm[0])
    p_bad2.pop("cap", None)
    check("零默认值：cap 缺失 → ×1.00", abs(dmg_mult(NEG[:3], p_bad2) - 1.0) < 1e-9, "")


def test_9_silence_tick():
    print("【9. 沉默之歌驻留：time_advance tick 封印（每 4 刻至多 1 次）】")
    b, bard = mk_battle(["沉默之歌", "战歌"], n_enemies=2)
    foe = foes_of(b)[0]
    sing(b, bard, "沉默之歌")
    st = (bard.get("effects") or {}).get("melody_state") or {}
    tick = [t for t in trigs(bard, "time_advance")
            if (t.get("action") or t.get("type")) == "class_melody_dirge_tick"]
    check("自安装 time_advance tick（首次唱响 e_silence）", len(tick) == 1, repr(trigs(bard, "time_advance")))
    # 首次 tick → 敌方全体封印 4 刻
    st["_silence_at"] = None
    for f in foes_of(b):
        f["effects"].pop("silence", None)
    bfire(b, "time_advance", {"dt": 4.0, "now": b._now}, [])
    ent = (foe.get("effects") or {}).get("silence")
    check("tick：敌方封印（mode=no_skill，4 刻）",
          isinstance(ent, dict) and ent.get("mode") == "no_skill"
          and abs(float(ent["expire"]) - (b._now + 4)) < 1e-6, repr(ent))
    check("tick：敌方全体（2 个）都封印",
          all(isinstance((f.get("effects") or {}).get("silence"), dict) for f in foes_of(b)), "")
    # 节流：<4 刻不重复
    b._now += 2.0
    for f in foes_of(b):
        f["effects"].pop("silence", None)
    bfire(b, "time_advance", {"dt": 2.0, "now": b._now}, [])
    check("节流：距上次 2 刻（<4）不再封印", "silence" not in (foe.get("effects") or {}),
          repr(foe.get("effects")))
    # ≥4 刻重新封印
    b._now += 3.0
    bfire(b, "time_advance", {"dt": 3.0, "now": b._now}, [])
    check("≥4 刻 → 再次封印（刷新 4 刻）",
          isinstance((foe.get("effects") or {}).get("silence"), dict), repr(foe.get("effects")))
    # 换歌 → kind 非 e_silence → 停 tick
    sing(b, bard, "战歌")
    for f in foes_of(b):
        f["effects"].pop("silence", None)
    b._now += 10.0
    bfire(b, "time_advance", {"dt": 10.0, "now": b._now}, [])
    check("换歌后 tick 不再封印（kind≠e_silence）", "silence" not in (foe.get("effects") or {}),
          repr(foe.get("effects")))
    # 面板类旋律不装 tick（零噪音）
    b2, bard2 = mk_battle(["挽歌"])
    sing(b2, bard2, "挽歌")
    check("面板类 e_ 旋律（e_atk）不装 tick", not [t for t in trigs(bard2, "time_advance")
                                                   if (t.get("action") or t.get("type")) == "class_melody_dirge_tick"],
          repr(trigs(bard2, "time_advance")))


def test_10_integration_human_act():
    print("【10. 集成：human_act 真实出手（事件总线/推进全通）】")
    b, bard = mk_battle(["镇魂歌", "挽歌·极"], n_enemies=1)
    foe = foes_of(b)[0]
    base_spd = actor_stats(b, foe).get("spd")
    logs, ended, _who = b.human_act("skill", "镇魂歌", bard)
    check("human_act 唱镇魂歌：敌方 spd 下降",
          actor_stats(b, foe).get("spd") < base_spd,
          f"{base_spd}→{actor_stats(b, foe).get('spd')}")
    st = (bard.get("effects") or {}).get("melody_state") or {}
    check("human_act：melody_state.kind=e_spd", st.get("kind") == "e_spd", repr(st))
    check("human_act：敌方 melody_e_spd 条目在", isinstance((foe.get("effects") or {}).get("melody_e_spd"), dict),
          repr(foe.get("effects")))
    check("human_act：日志含奏响/敌方全体受挫",
          any("奏响" in x for x in logs) and any("敌方全体受挫" in x for x in logs), str(logs[-3:]))


def test_11_negative():
    print("【11. 负向：非诗人零干扰 / 未学被动不挂 / 零默认值】")
    # 战士（非诗人）学同名技能 → skill_info 取不到 → 零触发器
    war = mk_player("p_war", "战士", "cls_zhan_shi", ["挽歌", "镇魂安魂", "挽歌·极"])
    CM.apply_class_mech(war)
    check("非诗人：无 class_melody_act / 无两被动",
          not [t for t in (war.get("triggers") or {}).get("act_cast", [])
               if (t.get("type") or t.get("action")) in ("class_melody_act", "passive_ctrl_extend")]
          and not [t for t in (war.get("triggers") or {}).get("dmg_calc", [])
                   if (t.get("type") or t.get("action")) == "passive_dmg_mult"],
          repr(war.get("triggers")))
    # 诗人未学任何旋律技 → 不挂 melody 触发器
    b3 = mk_player("p_b3", "诗人3", CLS, ["镇魂安魂", "挽歌·极"])
    CM.apply_class_mech(b3)
    check("未学旋律技 → 不挂 class_melody_act",
          not [t for t in (b3.get("triggers") or {}).get("act_cast", [])
               if (t.get("type") or t.get("action")) == "class_melody_act"], "")
    # 未知曲式 → 同旧行为（提示不落状态）
    b, bard = mk_battle(["挽歌"])
    b._fire_ctx = {"actor": bard, "info": {"mech": "melody", "melody": "no_such_kind",
                                           "name": "幽灵曲"}, "target": None}
    logs = call_action(b, "class_melody_act", {}, bard)
    check("未知曲式：提示且不落 melody_state",
          any("尚未谱成" in x for x in logs) and "melody_state" not in (bard.get("effects") or {}),
          str(logs))
    # 吟唱无旋律 → 提示（回归）
    b2, _bard2 = mk_battle(["挽歌"])
    b2._fire_ctx = {"actor": bard, "info": {"mech": "melody_chant"}, "target": None}
    logs2 = call_action(b2, "class_melody_act", {}, bard)
    check("未唱先吟 → 提示（回归）", any("尚无旋律" in x for x in logs2), str(logs2))


def main():
    test_1_data_fields()
    test_2_assemble()
    test_3_resident_enemy_aura()
    test_4_switch_song_direction()
    test_5_finale_enemy_debuff()
    test_6_finale_control()
    test_7_dirge_ctrl_up()
    test_8_dirge_debuff_dmg()
    test_9_silence_tick()
    test_10_integration_human_act()
    test_11_negative()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
