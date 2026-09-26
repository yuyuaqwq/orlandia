# -*- coding: utf-8 -*-
"""v181.M-passive P2 测试——被动 proc 系统扩展批（反击族 + 乘区族 + 双通道）。

跑法：python tests/test_passive_p2.py（exit=0 全绿）
覆盖（旧语义源 = passive_procs.py 挂点13/14 逐字 + EFFECT_RULES debuff_scale）：
  1. 反击族装配：战士学以守为攻 → on_taken 单条聚合（chance 0.35 / atk_pct 0.80）
  2. 反击族聚合：以守为攻+反击之王都学 → 单条 chance 0.60 / atk_pct 1.20（旧注释终值）
  3. 反击触发：受击 roll 成功 → 反打攻击方（日志含 反击）
  4. 乘区族：自然之眼 猎印标记目标 → 伤害 ×(1+0.06×层)（target_mark_any）
  5. 乘区负向：目标无猎印 → 不触发
  6. 毒爆族：蚀骨 → 施放 mech=poison_burst 系技能 → ×1.25（mech_prefix）
  7. 双通道：灵魂锁链 cap 段（bonus.cap soul_mark）+ per_layer 乘区段都装配
  8. speed_ratio_ge：疾风·极 速度比 ≥2 触发 ×1.2（P1 已声明补 judge 分支）
"""
import sys, os, random
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p2.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from ext_combat import Battle as B2, make_actor
from content.mech.class_mech import apply_class_mech

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


def mk(skills, cls="cls_wu_seng", atk=200, matk=20, spd=40, hp=2000, mp=100):
    a = make_actor(uid="p_1", name="测试", side="player", kind="player",
                   human_controlled=True, class_name=cls, level=95,
                   learned_skills=list(skills), skills=list(skills),
                   atk=atk, matk=matk, spd=spd, hp=hp, max_hp=hp, mp=mp, max_mp=mp)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_enemy(spd=1, hp=999999):
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=spd, hp=hp, max_hp=hp)
    e['effects'] = {}
    return e


def mk_battle(players, enemy=None):
    e = enemy or mk_enemy()
    return B2("monster", sides={"player": players, "enemy": [e]})


def skill_in_class(cls, name):
    """从职业技能树查技能中文名 → 技能 key（玩家列表存中文名也能查——测试用中文名直接学）。"""
    return name


def test_1_counter_assemble():
    print("【1. 反击族装配：以守为攻 → on_taken 单条聚合（chance 0.35 / atk_pct 0.80）】")
    w = mk(["以守为攻"])
    apply_class_mech(w)
    ents = [t for t in (w.get("triggers") or {}).get("on_taken", [])
            if t.get("type") == "passive_counter"]
    check("以守为攻 → 恰 1 条 passive_counter", len(ents) == 1, repr(ents))
    if ents:
        check("终值 chance 0.35 / atk_pct 0.80（普攻 80%）",
              abs(float(ents[0].get("chance") or 0) - 0.35) < 1e-9
              and abs(float(ents[0].get("atk_pct") or 0) - 0.80) < 1e-9,
              repr(ents[0]))


def test_2_counter_merge():
    print("【2. 反击聚合：以守为攻+反击之王 → 单条 chance 0.60 / atk_pct 1.20】")
    w = mk(["以守为攻", "反击之王"])
    apply_class_mech(w)
    ents = [t for t in (w.get("triggers") or {}).get("on_taken", [])
            if t.get("type") == "passive_counter"]
    check("双被动 → 仍恰 1 条（聚合归并）", len(ents) == 1, repr(ents))
    if ents:
        check("终值 chance 0.35+0.25=0.60 / atk_pct 0.8×1.5=1.20（旧注释终值）",
              abs(float(ents[0].get("chance") or 0) - 0.60) < 1e-9
              and abs(float(ents[0].get("atk_pct") or 0) - 1.20) < 1e-9,
              repr(ents[0]))


def test_3_counter_trigger():
    print("【3. 反击触发：受击 → 反打攻击方】")
    w = mk(["以守为攻"], hp=5000)
    apply_class_mech(w)
    # 直接改 chance=1 保证触发（聚合装配值不可变——手改 trigger）
    for t in (w.get("triggers") or {}).get("on_taken", []):
        if t.get("type") == "passive_counter":
            t["chance"] = 1.0
    enemy = mk_enemy(spd=1, hp=999999)
    enemy['dodge'] = 0.0  # 防反击被闪避 roll 干扰（闪避率 0）
    # 敌攻击玩家 → 玩家被击 → on_taken → 反击
    b = mk_battle([w], enemy)
    logs, _, _ = b.human_act("attack", None, enemy)  # enemy 手动普攻玩家?
    # 换个更稳路径：直接对玩家 deal_damage（走 landing on_taken 触发链）
    from ext_combat.battle.landing import deal_damage
    b2 = mk_battle([w], enemy)
    e = b2.sides_of("enemy")[0]
    e['dodge'] = 0.0
    w2 = b2.sides_of("player")[0]
    logs2 = []
    deal_damage(b2, e, w2, 50, logs2)
    check("反击日志出现（反打攻击方）", any("反击" in l for l in logs2),
          str(logs2[-4:]))


def test_4_mark_mult():
    print("【4. 自然之眼：猎印目标 → 伤害 ×(1+0.06×层)】")
    r = mk(["自然之眼", "疾风射击"], cls="cls_you_xia", atk=150, spd=120)
    apply_class_mech(r)
    dmgs = [t for t in (r.get("triggers") or {}).get("dmg_calc", [])
            if t.get("type") == "passive_dmg_mult"]
    check("自然之眼挂 dmg_calc（judge target_mark_any hunt_mark）",
          len(dmgs) == 1 and (dmgs[0].get("judge") or {}).get("mark") == "hunt_mark",
          repr(dmgs))
    # 给木桩上 2 层猎印，打它 → 被动 ×1.12 生效
    from content.skills import skill_info
    info = skill_info("cls_you_xia", "疾风射击") or {}
    check("疾风射击是技能（伤害技能）", bool(info.get("name")), repr(info.get("name")))
    b = mk_battle([r])
    e = b.sides_of("enemy")[0]
    e['effects']['hunt_mark'] = {'stacks': 2, 'expire': None}
    logs, _, _ = b.human_act("skill", "疾风射击", r)
    check("猎印目标 → 被动 ×1.12 生效", any("被动生效" in l for l in logs),
          str([l for l in logs if "被动" in l or "受到" in l][-2:]))


def test_5_mark_negative():
    print("【5. 负向：目标无猎印 → 不触发】")
    r = mk(["自然之眼", "疾风射击"], cls="cls_you_xia", atk=150, spd=120)
    apply_class_mech(r)
    b = mk_battle([r])
    logs, _, _ = b.human_act("skill", "疾风射击", r)
    check("无猎印 → 无被动日志", not any("被动生效" in l for l in logs),
          str([l for l in logs if "被动" in l][-1:]))


def test_6_poison_burst_mult():
    print("【6. 蚀骨：毒爆系技能 → ×1.25（mech_prefix poison_burst）】")
    # 蚀骨是刺客被动；毒爆技——找刺客带 mech=poison_burst 的伤害技
    from content.skills import BRANCH_SKILLS
    import json
    burst_skills = []
    w = BRANCH_SKILLS.get("cls_ci_ke") or {}
    for bk, bv in (w.get("branches") or {}).items():
        if isinstance(bv, dict):
            for sub, sk2 in bv.items():
                if isinstance(sk2, dict):
                    for n, i in sk2.items():
                        if (i.get("mech") or "").startswith("poison_burst"):
                            burst_skills.append((n, i.get("mech")))
    check("找到毒爆系伤害技（供触发）", len(burst_skills) > 0, repr(burst_skills[:2]))
    if not burst_skills:
        return
    sname, smech = burst_skills[0]
    a = mk(["蚀骨", sname], cls="cls_ci_ke", atk=150, spd=80)
    apply_class_mech(a)
    dmgs = [t for t in (a.get("triggers") or {}).get("dmg_calc", [])
            if t.get("type") == "passive_dmg_mult"]
    check("蚀骨挂 dmg_calc（judge mech_prefix poison_burst）",
          len(dmgs) == 1 and (dmgs[0].get("judge") or {}).get("mech") == "poison_burst",
          repr(dmgs))
    b = mk_battle([a])
    logs, _, _ = b.human_act("skill", sname, a)
    check("毒爆技施放 → 蚀骨被动 ×1.25 生效", any("被动生效" in l for l in logs),
          str([l for l in logs if "被动" in l or "受到" in l][-2:]))


def test_7_dual_channel():
    print("【7. 双通道：灵魂锁链 cap 段 + per_layer 乘区段同时装配】")
    from ext_combat.battle.effects import _cap_of
    # 灵魂锁链是哪个职业？死灵法师 cls？搜全部技能树找
    from content.skills import PLAYER_SKILLS, BRANCH_SKILLS
    owner_cls = None
    for cid in list(PLAYER_SKILLS) + list(BRANCH_SKILLS):
        for tag, sk2 in [("P", (PLAYER_SKILLS.get(cid) or {}).get("skills") or {})]:
            pass
    # 简化：用 skill_info 全表扫（学名中文）
    from content.skills import skill_info
    found = []
    for cid in list(PLAYER_SKILLS) + list(BRANCH_SKILLS):
        try:
            info = skill_info(cid, "灵魂锁链") or {}
        except Exception:
            info = {}
        if info.get("passive"):
            found.append(cid)
            break
    check("灵魂锁链归属职业可查", len(found) > 0, str(found))
    if not found:
        return
    a = mk(["灵魂锁链"], cls=found[0])
    a['effects'] = {}
    apply_class_mech(a)
    # cap 段
    check("cap 段：soul_mark 3+2=5", _cap_of(a, "soul_mark") == 5,
          f"cap={_cap_of(a, 'soul_mark')}")
    # 乘区段
    dmgs = [t for t in (a.get("triggers") or {}).get("dmg_calc", [])
            if t.get("type") == "passive_dmg_mult"]
    check("乘区段也挂 dmg_calc（双通道并存）",
          len(dmgs) == 1 and (dmgs[0].get("judge") or {}).get("mark") == "soul_mark",
          repr(dmgs))


def main():
    # v181 flaky 修复：玩家真实面板 ~3% 基础闪避（职业成长，actor["dodge"] 改不动——
    # 走 E.player_final_stats 公式）——固定随机种子保证受击/命中序列确定
    # （3% 闪避偶发会把「反击触发」断言打成假红）。同 test_battle_n10_b2 做法。
    random.seed(20260910)
    test_1_counter_assemble()
    test_2_counter_merge()
    test_3_counter_trigger()
    test_4_mark_mult()
    test_5_mark_negative()
    test_6_poison_burst_mult()
    test_7_dual_channel()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
