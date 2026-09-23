# -*- coding: utf-8 -*-
"""v156 formula 通用公式层门禁测试——防公式引擎退化。

覆盖（N10 删旧精简：旧 Battle 容器消费段退役——技能/词条/怪技 formula
消费已由 saintess_engine 测试覆盖，见 test_battle_n2_skill 挥砍 exprs +
test_battle_n10_b4_element 火球 formula；本文件只留 E 层纯函数验证）：
1. resolve_formula 纯函数：混伤/物理职业魔法技/基础值+百分比/目标血百分比/纯固定值/chance/mult 乘区
2. 敌方技能 formula：resolve_formula 直调（怪技 formula 数据驱动）

运行：python tests/test_numeric_formula.py（exit=0 全绿）
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）

from ext_combat.battle.formulas import resolve_formula, calc_damage# noqa: E402

passed = failed = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")


def mk_stats():
    return {"atk": 100, "matk": 80, "max_hp": 500}


def test_resolve_formula_pure():
    print("【1. resolve_formula 纯函数】")
    st = mk_stats()
    # 混伤
    d, m = resolve_formula([{"stat": "atk", "mult": 1.3, "type": "phys"},
                            {"stat": "matk", "mult": 0.3, "type": "magi"}], st, 50, 50, variance=0)
    check("混伤 130%物+30%魔 magi 段分离", m == calc_damage(int(80 * 0.3), 50, variance=0),
          f"magi={m}")
    # 物理职业魔法技
    d2, m2 = resolve_formula([{"stat": "atk", "mult": 1.0, "type": "magi"}], st, 50, 50, variance=0)
    check("atk→magi 吃物攻算魔伤", d2 == calc_damage(100, 50, variance=0),
          f"d={d2}")
    # 基础值+百分比
    d3, _ = resolve_formula([{"stat": "atk", "mult": 1.2, "flat": 50, "type": "phys"}], st, 50, 50, variance=0)
    check("基础值+百分比 flat", d3 == calc_damage(int(100 * 1.2) + 50, 50, variance=0),
          f"d={d3}")
    # 目标血百分比真伤
    d4, _ = resolve_formula([{"stat": "max_hp", "mult": 0.05, "type": "true"}], st, 50, 50,
                            variance=0, target_max_hp=2000)
    check("5%目标血真伤", d4 == 100, f"d={d4}")
    # 纯固定值
    d5, _ = resolve_formula([{"stat": "flat", "flat": 100, "type": "true"}], st, 50, 50, variance=0)
    check("纯固定值真伤", d5 == 100, f"d={d5}")
    # chance 不触发
    random.seed(1)
    d6, _ = resolve_formula([{"stat": "atk", "mult": 1.0, "type": "phys", "chance": 0.0}],
                            st, 50, 50, variance=0)
    check("chance=0 不触发", d6 == 0, f"d={d6}")
    # mult 外部乘区
    d7, _ = resolve_formula([{"stat": "atk", "mult": 1.0, "type": "phys"}], st, 50, 50,
                            variance=0, mult=1.5)
    check("mult 外部乘区", d7 == calc_damage(int(100 * 1.5), 50, variance=0), f"d={d7}")


def test_enemy_formula():
    print("【2. 敌方技能 formula（resolve_formula 直调）】")
    from _engine_harness import C as _C  # noqa: F401  测试侧入口（装配引擎通道；本文件无 conftest）
    from content.catalog_quests import MONSTER_SKILLS
    MONSTER_SKILLS["ms_test_fml"] = {
        "kind": "魔法", "power": 1.0,
        "formula": [{"stat": "matk", "mult": 1.5, "type": "magi"}],
        "name": "测试怪技",
    }
    est = {"atk": 50, "matk": 60, "crit": 0.05, "def": 10, "mdef": 10, "spd": 10, "max_hp": 1000, "hp": 1000}
    pst = {"def": 20, "mdef": 20, "crit": 0.05, "max_hp": 1000, "max_mp": 500}
    dmg, _ = resolve_formula(MONSTER_SKILLS["ms_test_fml"]["formula"], est,
                             pst["def"], pst["mdef"], is_crit=False, variance=0)
    check("敌方 formula 生效", dmg > 0, f"dmg={dmg}")
    check("敌方 formula 伤害正确", dmg == calc_damage(int(60 * 1.5), 20, variance=0),
          f"dmg={dmg}")


if __name__ == "__main__":
    test_resolve_formula_pure()
    test_enemy_formula()
    print(f"\n===== 结果：通过 {passed} / 断言 {passed + failed} =====")
    sys.exit(1 if failed else 0)
