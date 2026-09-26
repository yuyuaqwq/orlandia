# -*- coding: utf-8 -*-
"""v181.M-passive P9 测试——元素印记增强批（亲和/同调/元素之核）。

跑法：python tests/test_passive_p9.py（exit=0 全绿）
覆盖（desc 权威；元素挂印机制现网活——火球术 fire_mark 经 effects_from_skill）：
  1. 元素亲和：引爆后下次挂印 → 2 层（基础 1 + 亲和 1）
  2. 元素同调：连续两次同系施法 → 第二次挂印 2 层；插非元素技断连
  3. 元素之核：结算技时目标单系印记≥3 → crit buff 写入
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p9.db"))
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


def mk_mage(skills):
    a = make_actor(uid="p_1", name="法师", side="player", kind="player",
                   human_controlled=True, class_name="cls_fa_shi", level=95,
                   learned_skills=list(skills), skills=list(skills),
                   atk=50, matk=250, spd=60, hp=3000, max_hp=3000, mp=500, max_mp=500)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(m, e_hp=999999):
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=1, hp=e_hp, max_hp=e_hp)
    e['effects'] = {}
    e['dodge'] = 0.0
    return B2("monster", sides={"player": [m], "enemy": [e]})


def mark_of(e, key):
    en = (e.get("effects") or {}).get(key)
    return int(en.get("stacks", 0) or 0) if isinstance(en, dict) else 0


def test_1_affinity():
    print("【1. 元素亲和：引爆后挂印 → 2 层】")
    m = mk_mage(["元素亲和", "火球术", "元素迸发"])
    apply_class_mech(m)
    b = mk_battle(m)
    e = b.sides_of("enemy")[0]
    # 先给木桩 2 层火印（直接塞，模拟之前挂的）
    e['effects']['fire_mark'] = {'stacks': 2, 'expire': None}
    # 引爆（元素迸发：结算 target 全部印记）
    logs, _, _ = b.human_act("skill", "元素迸发", m)
    # 引爆后亲和置标记（effects._elem_affinity_ready）
    check("引爆后置待增强标记",
          (m.get("effects") or {}).get("_elem_affinity_ready") is not None,
          repr((m.get("effects") or {}).get("_elem_affinity_ready")))
    # 下次火球术 → 挂印 1+1=2
    logs2, _, _ = b.human_act("skill", "火球术", m)
    check("引爆后火球挂印 2 层（基础1+亲和1）", mark_of(e, "fire_mark") >= 2,
          f"fire_mark={mark_of(e, 'fire_mark')}")
    check("待增强标记已消费", (m.get("effects") or {}).get("_elem_affinity_ready") is None,
          "")
    # 再打一次（无标记）→ 只基础 1
    logs3, _, _ = b.human_act("skill", "火球术", m)
    check("无标记再挂只 +1", mark_of(e, "fire_mark") >= 3, "")  # 2+1


def test_2_sync():
    print("【2. 元素同调：连续同系第二次挂印 2 层；插他系断连】")
    m = mk_mage(["元素同调", "火球术"])
    apply_class_mech(m)
    b = mk_battle(m)
    e = b.sides_of("enemy")[0]
    logs, _, _ = b.human_act("skill", "火球术", m)
    check("第一次火球基础 1 层", mark_of(e, "fire_mark") == 1,
          f"fire_mark={mark_of(e, 'fire_mark')}")
    logs2, _, _ = b.human_act("skill", "火球术", m)
    check("第二次连续同系 → 挂印 2 层（1+1+1=3）", mark_of(e, "fire_mark") == 3,
          f"fire_mark={mark_of(e, 'fire_mark')}")
    # 非元素施法断连：游侠? 法师普攻（basic 无 mech）→ 清记录
    logs3, _, _ = b.human_act("attack", None, m)
    check("非元素施法断连", (m.get("effects") or {}).get("_elem_last_mark") is None,
          repr((m.get("effects") or {}).get("_elem_last_mark")))


def test_3_core():
    print("【3. 元素之核：结算技时目标单系印记≥3 → crit buff】")
    m = mk_mage(["元素之核", "元素迸发", "火球术"])
    apply_class_mech(m)
    b = mk_battle(m)
    e = b.sides_of("enemy")[0]
    e['effects']['fire_mark'] = {'stacks': 3, 'expire': None}  # 单系满 3
    logs, _, _ = b.human_act("skill", "元素迸发", m)
    cb = (m.get("effects") or {}).get("passive_crit_element_core")
    check("目标火印≥3 → crit buff（+0.20）",
          isinstance(cb, dict) and abs(float(cb.get("mult") or 0) - 0.20) < 1e-9,
          repr(cb))
    # 无印记/不足 3 → 不触发
    m2 = mk_mage(["元素之核", "元素迸发"])
    apply_class_mech(m2)
    b2 = mk_battle(m2)
    logs2, _, _ = b2.human_act("skill", "元素迸发", m2)
    check("无印记 → 无 buff",
          (m2.get("effects") or {}).get("passive_crit_element_core") is None, "")


def main():
    test_1_affinity()
    test_2_sync()
    test_3_core()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
