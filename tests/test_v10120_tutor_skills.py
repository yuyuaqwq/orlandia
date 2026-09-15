# -*- coding: utf-8 -*-
"""v101.20 职业导师专属技能（TUTOR_SKILLS）完整链路验证

覆盖：
  1. 专属技能未学会 → 『技能列表』不显示（保持神秘感）
  2. 『技能学习 <专属技能>』→ 拦截提示找导师（技能点学不到）
  3. 导师教学 action → 支付学费学会（TUTOR 技能可解析）
  4. 学会后 → 『技能列表』翻页可见（尾部，可升级）
  5. 战斗施放 TUTOR 技能 → 伤害正常（skill_info 查询链最后一环）
  6. 『技能升级』TUTOR 技能正常
  7. 职业技能（破甲斩/战吼）不受影响，仍可技能点学
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail).encode('utf-8', 'replace').decode('utf-8', 'replace')[:300]}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def join_mage(m):
    """注册法师 + 行会就职"""
    await cmd(m, "register", "g1", "w1", "注册 法师 小查 女")
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_1")
    await cmd(m, "find_npc", "g1", "w1", "找 行会")
    await cmd(m, "talk_choice", "g1", "w1", "2")  # 法师
    await cmd(m, "talk_choice", "g1", "w1", "1")  # 确定

async def main():
    clean_db()
    m = Main(None)
    await join_mage(m)
    p = db.get_player("g1", "w1")
    check("法师就职", p["class_name"] == "cls_fa_shi", p.get("class_name"))

    print("【1. 未学会专属技能不进技能列表】")
    out = await cmd(m, "skill", "g1", "w1", "技能 列表")
    check("第1页不含魔力脉冲", "魔力脉冲" not in out, out[:200])
    out4 = await cmd(m, "skill", "g1", "w1", "技能 列表 4")
    check("末页也不含", "魔力脉冲" not in out4, out4[:200])

    print("【2. 『技能学习』拦截导师专属】")
    db.update_player("g1", "w1", level=6, skill_points=10)
    out = await cmd(m, "skill_learn", "g1", "w1", "技能学习 魔力脉冲")
    check("拦截提示导师", "大法师·艾德琳" in out and "白鹿城" in out, out[:200])
    p = db.get_player("g1", "w1")
    check("未学会", "魔力脉冲" not in p["learned_skills"], str(p["learned_skills"]))
    check("技能点未扣", p["skill_points"] == 10, str(p["skill_points"]))

    print("【3. 导师教学学会】")
    db.update_player("g1", "w1", gold=5000, level=6)
    notices = m._apply_talk_action("g1", "w1", db.get_player("g1", "w1"), "npc_mage_tutor",
                                   {"tutor_skill": {"skill": "魔力脉冲", "cost": 800, "need_lv": 6}})
    check("支付学费提示", any("支付学费 800" in n for n in notices), str(notices)[:200])
    check("学会提示", any("学会了进阶技能『魔力脉冲』" in n for n in notices), str(notices)[:200])
    p = db.get_player("g1", "w1")
    check("learned 写入", "魔力脉冲" in p["learned_skills"], str(p["learned_skills"]))
    check("金币扣除", p["gold"] == 5000 - 800, str(p["gold"]))

    print("【3b. 走对话树 teach_ao_shu 教学（P0-2 回归）】")
    # 完整对话树驱动：注册法师 → 就职 → 白鹿城找法师导师 → 选『魔力脉冲』→ 选『请教我！』
    # → teach_ao_shu 节点 action tutor_skill 执行后技能学会（非直调 _apply_talk_action）
    await cmd(m, "register", "g1", "w2", "注册 法师 树徒 女")
    db.update_player("g1", "w2", cur_map="oak_town", cur_subarea="oak_town_1")
    await cmd(m, "find_npc", "g1", "w2", "找 行会")
    await cmd(m, "talk_choice", "g1", "w2", "2")  # 法师
    await cmd(m, "talk_choice", "g1", "w2", "1")  # 确定
    _p2 = db.get_player("g1", "w2")
    check("对话树法师就职", _p2["class_name"] == "cls_fa_shi", _p2.get("class_name"))
    db.update_player("g1", "w2", cur_map="white_deer", cur_subarea="white_deer_1",
                     level=30, gold=5000)
    out = await cmd(m, "find_npc", "g1", "w2", "找 大法师·艾德琳")
    check("对话树进入法师导师 welcome（含魔力脉冲菜单）",
          "魔法不是念咒" in out and "魔力脉冲" in out, out[:300])
    out = await cmd(m, "talk_choice", "g1", "w2", "1")  # → teach_ao_shu
    check("对话树进入 teach_ao_shu 节点", "魔力脉冲——把魔力压缩成一束光" in out, out[:250])
    out = await cmd(m, "talk_choice", "g1", "w2", "1")  # 『请教我！』→ action tutor_skill
    check("对话树教学学会魔力脉冲", "学会了进阶技能『魔力脉冲』" in out, out[:300])
    _p2 = db.get_player("g1", "w2")
    check("对话树技能写入 learned_skills", "魔力脉冲" in _p2["learned_skills"],
          str(_p2["learned_skills"]))
    check("对话树扣学费", _p2["gold"] == 5000 - 800, f"gold={_p2['gold']}")

    print("【4. 学会后技能列表可见】")
    out4 = await cmd(m, "skill", "g1", "w1", "技能 列表 4")
    check("末页显示魔力脉冲", "魔力脉冲" in out4 and "Lv.1/5" in out4, out4[:250])
    # 面板统计：已学 2/9（8 职业技能 + 1 专属）——v151 法师基础技能 8 个
    out = await cmd(m, "skill", "g1", "w1", "技能")
    check("面板统计含专属", "2/9" in out, out[:200])

    print("【5. 技能升级 + 战斗施放】")
    out = await cmd(m, "skill_upgrade", "g1", "w1", "技能升级 魔力脉冲")
    check("升级成功", "Lv.2" in out, out[:150])
    # saintess_engine 验证升级后专属技能真实打出伤害（N10 删旧：saintess_engine 施放语义）
    from saintess_engine import Battle as _B2
    from saintess_engine import make_actor as _mk2
    bp = db.get_player("g1", "w1")
    _st = _mk2(uid="p_q1", name=bp.get("name", "勇者"), side="player", kind="player",
               human_controlled=True, class_name=bp.get("class_name") or "cls_fa_shi",
               level=bp.get("level") or 1, hp=500, max_hp=500, mp=200, max_mp=200,
               atk=10, matk=50, spd=10, crit=0.0, equipment={}, skills=[],
               learned_skills=bp.get("learned_skills") or [], race=None, evolve_path=0,
               class_tier=0, attributes={}, **{"def": 5, "mdef": 5})
    _e = _mk2(uid="e_0", name="测试木桩", side="enemy", kind="monster", level=5,
              hp=200, max_hp=200, atk=10, matk=10, spd=5, crit=0.0,
              exp=0, gold=0, **{"def": 5, "mdef": 5})
    _b = _B2(btype="monster", sides={"player": [_st], "enemy": [_e]})
    _sk_id, _sk_info = None, None
    for _cid, _cd in (C.PLAYER_SKILLS or {}).items():
        for _sid, _sk in (_cd.get("skills") or {}).items():
            if str((_sk or {}).get("name")) == "魔力脉冲":
                _sk_id, _sk_info = _sid, dict(_sk)
    if not _sk_info:
        # 导师专属技能在 TUTOR_SKILLS（v101.20 职业导师）
        for _cid, _cd in (getattr(C, "TUTOR_SKILLS", None) or {}).items():
            for _sid, _sk in (_cd or {}).items():
                if isinstance(_sk, dict) and str(_sk.get("name")) == "魔力脉冲":
                    _sk_id, _sk_info = _sid, dict(_sk)
    if _sk_info:
        from saintess_engine.battle.actors import ActCtx
        _logs = []
        _b.act(ActCtx(caster=_st, action="skill", skill_name="魔力脉冲",
                      info=_sk_info, target=_e))
        check("战斗施放有伤害（saintess_engine）", int(_e.get("hp", 200)) < 200,
              f"hp={_e.get('hp')} logs={str(_logs)[:80]}")
    else:
        check("找到魔力脉冲技能数据", False, "skills 未找到")

    print("【6. 职业技能不受影响】")
    # 战士的破甲斩/战吼是职业技能（TUTOR 重名已删）→ 技能点可学
    clean_db()
    await cmd(m, "register", "g1", "w1", "注册 战士 小战 男")
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_1")
    await cmd(m, "find_npc", "g1", "w1", "找 行会")
    await cmd(m, "talk_choice", "g1", "w1", "1")  # 战士
    await cmd(m, "talk_choice", "g1", "w1", "1")
    db.update_player("g1", "w1", level=8, skill_points=20)
    out = await cmd(m, "skill_learn", "g1", "w1", "技能学习 破甲斩")
    check("破甲斩技能点可学", "学会了『破甲斩』" in out, out[:150])
    db.update_player("g1", "w1", level=16, skill_points=20)  # v153 战吼 lv 3→16
    out = await cmd(m, "skill_learn", "g1", "w1", "技能学习 战吼")
    check("战吼技能点可学", "学会了『战吼』" in out, out[:150])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
