# -*- coding: utf-8 -*-
"""v181 add_actor：引擎运行期 actor 注册公开 API 验证。

覆盖 docs/archive/REFACTOR_v181_GAP_CLOSURE_PLAN.md §2 选项 B 的 6 条验收：
1. append 语义（默认入 sides 尾部）
2. front 语义（插队首 = 前排挡刀位）
3. 新 actor 建 _skill_index（否则 auto_act 技能静默空放）
4. 新 actor 播种 ct（否则 CTB 排序异常）
5. 新 actor 真被 CTB 调度行动（auto_run 日志含其名）
6. 存档往返（to_state / from_state 后仍在）

跑法：python tests/test_battle_add_actor.py（w1 内）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_add_actor.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from ext_combat import Battle as B2, make_actor  # noqa: E402
from ext_combat.battle import schedule as SC  # noqa: E402
from ext_combat.battle import serialize as SER  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []

MON_SKILL = "ms_an_ying_dan"   # 暗影弹（MONSTER_SKILLS 内，name=暗影弹）


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_p(spd=10, hp=99999):
    return make_actor(uid="p1", name="玩家", side="player", kind="player",
                      human_controlled=True, class_name="cls_zhan_shi", level=20,
                      hp=hp, max_hp=hp, mp=300, max_mp=300,
                      atk=100, matk=50, spd=spd, crit=0.0,
                      equipment={}, skills=[], learned_skills=[],
                      race=None, evolve_path=0, class_tier=0, attributes={},
                      **{"def": 40, "mdef": 30})


def mk_e(uid="e1", name="怪", spd=10, hp=99999, skills=None):
    return make_actor(uid=uid, name=name, side="enemy", kind="monster",
                      hp=hp, max_hp=hp, atk=50, matk=20, spd=spd, crit=0.0,
                      level=20, exp=0, gold=0, skills=list(skills or []),
                      **{"def": 10, "mdef": 10})


def test_append_and_front():
    print("【1/2. 入队语义：默认 append 尾部 / front=True 插队首（挡刀位）】")
    p = mk_p()
    e1 = mk_e("e1", "旧怪")
    b = B2(btype="monster", sides={"player": [p], "enemy": [e1]})

    n1 = mk_e("e2", "新怪A")
    b.add_actor(n1, "enemy")
    lst = b.sides["enemy"]
    check("默认 append → 末位", lst[-1] is n1 and len(lst) == 2,
          f"len={len(lst)} last={lst[-1].get('name')}")

    n2 = mk_e("e3", "新怪B")
    b.add_actor(n2, "enemy", front=True)
    lst = b.sides["enemy"]
    check("front=True → 队首（存活序列第一名）", lst[0] is n2,
          f"first={lst[0].get('name')}")
    check("原有 actor 顺序不被打乱", [a.get("uid") for a in lst] == ["e3", "e1", "e2"],
          f"uids={[a.get('uid') for a in lst]}")

    # 敌方队首即玩家 AI 默认目标（挡刀语义）
    check("hostile_of 首位 = 新插入的挡刀单位",
          b.hostile_of("player")[0] is n2,
          f"first={b.hostile_of('player')[0].get('name')}")


def test_new_side_created():
    print("【补充. 目标 side 不存在时自动建（setdefault）】")
    p = mk_p()
    b = B2(btype="monster", sides={"player": [p]})
    n = mk_e("e9", "援军")
    b.add_actor(n, "enemy")
    check("side 不存在也能注册", b.sides_of("enemy") == [n],
          f"sides={list(b.sides.keys())}")


def test_skill_index_built():
    print("【3. 新 actor 建 _skill_index（否则 auto_act 技能静默空放）】")
    p = mk_p()
    e1 = mk_e("e1", "旧怪")
    b = B2(btype="monster", sides={"player": [p], "enemy": [e1]})

    n = mk_e("e2", "带技能怪", skills=[MON_SKILL])
    check("注册前索引为空", not n.get("_skill_index"), f"idx={n.get('_skill_index')}")
    b.add_actor(n, "enemy")
    idx = n.get("_skill_index") or {}
    check("注册后索引非空", bool(idx), f"idx={idx}")
    check("索引含技能 key 与中文名双路",
          MON_SKILL in idx and "暗影弹" in idx, f"keys={list(idx.keys())}")


def test_ct_seeded():
    print("【4. 新 actor 播种 ct（不播种则 CTB 排序异常）】")
    p = mk_p(spd=10)
    e1 = mk_e("e1", "旧怪", spd=10)
    b = B2(btype="monster", sides={"player": [p], "enemy": [e1]})

    n = make_actor(uid="e2", name="快援军", side="enemy", kind="monster",
                   hp=99999, max_hp=99999, atk=50, matk=20, spd=30, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 10, "mdef": 10})
    check("注册前 ct 未播种（make_actor 播种 0.0）", float(n.get("ct") or 0) <= 0,
          f"ct={n.get('ct')}")
    b.add_actor(n, "enemy")
    expect = SC.initial_ct(30)
    check("注册后 ct = initial_ct(spd)=1.291", abs(float(n.get("ct") or 0) - expect) < 1e-6,
          f"ct={n.get('ct')} expect={expect:.3f}")

    # 已有正 ct 不重播（幂等）
    pre = 7.5
    m = mk_e("e3", "已排程怪")
    m["ct"] = pre
    b.add_actor(m, "enemy")
    check("已有正 ct 不重播", abs(float(m["ct"]) - pre) < 1e-9, f"ct={m['ct']}")


def test_scheduled_by_ctb():
    print("【5. 新 actor 真被 CTB 调度行动（auto_run 日志含其名）】")
    p = mk_p(spd=1, hp=99999)
    e1 = mk_e("e1", "慢怪", spd=1, hp=99999)
    b = B2(btype="monster", sides={"player": [p], "enemy": [e1]})

    # 极快援军：ct 小 → 应抢在双方之前行动
    n = make_actor(uid="e2", name="疾风援军", side="enemy", kind="monster",
                   hp=99999, max_hp=99999, atk=50, matk=20, spd=200, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 10, "mdef": 10})
    b.add_actor(n, "enemy")
    check("援军 ct < 全场（快者先手）",
          float(n["ct"]) < float(p["ct"]) and float(n["ct"]) < float(e1["ct"]),
          f"n={n['ct']:.3f} p={p['ct']:.3f} e1={e1['ct']:.3f}")

    logs = []
    b.auto_run(logs, max_steps=4)
    check("日志出现援军名（证明被调度）",
          any("疾风援军" in str(x) for x in logs),
          f"logs={logs[:4]}")
    check("援军行动后 ct 被推进（离开初始播种值）",
          float(n.get("ct") or 0) != SC.initial_ct(200),
          f"ct={n.get('ct')}")


def test_serialize_roundtrip():
    print("【6. 存档往返（to_state / from_state 后新 actor 仍在）】")
    p = mk_p()
    e1 = mk_e("e1", "旧怪")
    b = B2(btype="monster", sides={"player": [p], "enemy": [e1]})
    n = mk_e("e2", "存档援军", skills=[MON_SKILL])
    b.add_actor(n, "enemy")

    st = SER.to_state(b)
    uids = [a.get("uid") for a in (st.get("sides", {}).get("enemy") or [])]
    check("to_state 含新 actor", "e2" in uids, f"uids={uids}")

    b2 = SER.from_state(st)
    uids2 = [a.get("uid") for a in b2.sides_of("enemy")]
    check("from_state 后新 actor 仍在", "e2" in uids2, f"uids={uids2}")
    # 恢复路径重建索引（Battle 构造跑 _index_skills 遍历全部 sides）
    a2 = next(a for a in b2.sides_of("enemy") if a.get("uid") == "e2")
    check("恢复后技能索引重建", MON_SKILL in (a2.get("_skill_index") or {}),
          f"idx={list((a2.get('_skill_index') or {}).keys())}")


def test_no_duplicate_side_reset():
    print("【补充. add_actor 不重置既有 sides（不误清场）】")
    p = mk_p()
    e1 = mk_e("e1", "旧怪")
    b = B2(btype="monster", sides={"player": [p], "enemy": [e1]})
    b.add_actor(mk_e("e2", "援军1"), "enemy")
    b.add_actor(mk_e("e3", "援军2"), "player")
    check("enemy 保留旧怪 + 1 援军", len(b.sides_of("enemy")) == 2,
          f"n={len(b.sides_of('enemy'))}")
    check("player 保留原玩家 + 1 援军", len(b.sides_of("player")) == 2,
          f"n={len(b.sides_of('player'))}")
    check("存活 actor 总数 = 4", len(b.alive_actors()) == 4,
          f"n={len(b.alive_actors())}")


if __name__ == "__main__":
    test_append_and_front()
    test_new_side_created()
    test_skill_index_built()
    test_ct_seeded()
    test_scheduled_by_ctb()
    test_serialize_roundtrip()
    test_no_duplicate_side_reset()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
