# -*- coding: utf-8 -*-
"""v173.5 仇恨配置验证：不同行为仇恨倍率（router 账务 3.5）。

复用 router 测试 helper：
- 普攻/普通技能：仇恨 = 伤害 ×1（缺省 hate_mult）
- 盾卫士「盾击·誓」（hate_mult 4）：仇恨 = 伤害 ×4（contribution 仍按实际伤害）
- 嘲讽（effect=taunt）：仇恨 = 当前最高 ×3 + 100 + taunt_target 强制锁 3 帧 → 递减清除
- 治疗：仇恨 = 治疗量 ×0.8（v49 基础）

跑法：python tests/test_instance_hate.py
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_battle_n5b4_instance_router as T
from content.flow import instance_battle as IB
from _engine_harness import db

GID = T.GID


def mk_guard_st(qid, enemy_hp=200000):
    """战士（守线盾卫技能）单人副本 st。class_name 存 cls_zhan_shi（职业 ID）。"""
    st = T.mk_st([qid], enemy=T.mk_enemy(hp=enemy_hp, atk=1, spd=1, role="boss"))
    sn = st["players"][str(qid)]
    sn["class_name"] = "cls_zhan_shi"
    sn["level"] = 60
    st["players"][str(qid)] = T.mk_snap(qid, f"玩家{qid}", cls="cls_zhan_shi",
                                        level=60, learned=["盾击·誓", "嘲讽"])
    st["players"][str(qid)]["hp"] = 999999
    st["players"][str(qid)]["max_hp"] = 999999
    db.update_player(GID, qid, hp=999999, max_hp=999999)
    IB.build_battle(st)
    return st


def test_1_attack_hate():
    print("【1. 普攻：仇恨 = 伤害 ×1（缺省）】")
    st = mk_guard_st(90001)
    inst = T._Host()
    _hp0 = sum(int(u.get("hp", 0) or 0) for u in IB._enemies_of(st))
    T._sync_run(inst, st, 90001, "attack")
    _hp1 = sum(int(u.get("hp", 0) or 0) for u in IB._enemies_of(st))
    dealt = _hp0 - _hp1
    threat = (st.get("threat") or {}).get("90001", 0)
    T.check("普攻造成伤害", dealt > 0, f"dealt={dealt}")
    T.check("仇恨 = 伤害 ×1", threat == dealt, f"threat={threat} dealt={dealt}")


def test_2_hate_mult_skill():
    print("【2. 盾击·誓（hate_mult 4）：仇恨 = 伤害 ×4，贡献仍按实际】")
    st = mk_guard_st(90002)
    inst = T._Host()
    _hp0 = sum(int(u.get("hp", 0) or 0) for u in IB._enemies_of(st))
    T._sync_run(inst, st, 90002, "skill", "盾击·誓")
    _hp1 = sum(int(u.get("hp", 0) or 0) for u in IB._enemies_of(st))
    dealt = _hp0 - _hp1
    threat = (st.get("threat") or {}).get("90002", 0)
    contrib = (st.get("contribution") or {}).get("90002", 0)
    T.check("盾击造成伤害", dealt > 0, f"dealt={dealt}")
    T.check("仇恨 = 伤害 ×4", threat == dealt * 4,
            f"threat={threat} dealt={dealt} expect={dealt * 4}")
    T.check("贡献按实际伤害（不受倍率影响）", contrib == dealt,
            f"contrib={contrib} dealt={dealt}")


def test_3_taunt():
    print("【3. 嘲讽：仇恨 = 最高×3+100 + 强制锁 3 帧 → 递减清除】")
    st = mk_guard_st(90003)
    inst = T._Host()
    # 先普攻打点仇恨
    T._sync_run(inst, st, 90003, "attack")
    threat_before = (st.get("threat") or {}).get("90003", 0)
    _mx = threat_before
    # 放嘲讽
    msgs = T._sync_run(inst, st, 90003, "skill", "嘲讽")
    joined = "\n".join(msgs)
    threat_after = (st.get("threat") or {}).get("90003", 0)
    T.check("嘲讽演出", "嘲讽" in joined, joined[:120])
    T.check("taunt_target 设为自己", st.get("taunt_target") == "90003",
            str(st.get("taunt_target")))
    T.check("taunt_left=3（lock 帧）", st.get("taunt_left") == 3,
            str(st.get("taunt_left")))
    expect = int(_mx * 3 + 100)
    T.check(f"仇恨 = 最高×3+100（{_mx}→{expect}）", threat_after >= expect,
            f"after={threat_after} expect={expect}")
    # 递减：3 次行动帧后清强制
    for i in range(4):
        T._sync_run(inst, st, 90003, "defend")
    T.check("3 帧后 taunt_target 清除", not st.get("taunt_target"),
            str(st.get("taunt_target")))
    T.check("taunt_left 归零", st.get("taunt_left") == 0,
            str(st.get("taunt_left")))


def main():
    print("v173.5 仇恨配置验证")
    test_1_attack_hate()
    test_2_hate_mult_skill()
    test_3_taunt()
    print(f"\n结果：{T.PASS} 通过 / {T.FAIL} 失败")
    if T.FAILURES:
        for f in T.FAILURES:
            print(" -", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
