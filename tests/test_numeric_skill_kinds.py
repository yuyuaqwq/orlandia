# -*- coding: utf-8 -*-
"""v176 SkillKind 类型域测试：验证去魔法字符串重构的替代函数等价性。"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN = os.path.dirname(_HERE)
# 注意：kinds 是零依赖纯模块，直接按文件路径加载，避免触发 game 包 data 索引循环导入。
# P4 下沉（2026-09-13）：中文 kind 词表真源已从引擎搬到内容侧（原 `saintess_engine/kinds/__init__.py`）。
# ★ B16-W11d（2026-09-14）：`game/data/kinds.py` 随宿主数据层删除 → 路径改指**包内唯一真源**
#   `content/mech/kinds.py`（判据不变：仍是零依赖纯模块、逐字同源）。
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "kinds_standalone",
    os.path.join(_PLUGIN, "content", "mech", "kinds.py"))
_sk_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sk_mod)

SkillKind = _sk_mod.SkillKind
K_PHYS = _sk_mod.K_PHYS
K_MAGI = _sk_mod.K_MAGI
K_HEAL = _sk_mod.K_HEAL
K_TRUE = _sk_mod.K_TRUE
K_TAUNT = _sk_mod.K_TAUNT
K_BUFF = _sk_mod.K_BUFF
is_kind = _sk_mod.is_kind
is_damage_kind = _sk_mod.is_damage_kind
seg_of = _sk_mod.seg_of
lifesteal_channel_of = _sk_mod.lifesteal_channel_of

passed = failed = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")


def main():
    print("== v176 SkillKind 类型域测试 ==")
    # 精确匹配
    check("物理精确匹配", is_kind(K_PHYS, SkillKind.PHYS))
    check("魔法精确匹配", is_kind(K_MAGI, SkillKind.MAGI))
    check("治疗精确匹配", is_kind(K_HEAL, SkillKind.HEAL))
    check("元素魔法算魔法", is_kind("魔法·火", SkillKind.MAGI))
    check("元素魔法不算物理", not is_kind("魔法·火", SkillKind.PHYS))
    check("空 kind 不匹配", not is_kind("", SkillKind.PHYS))
    # 伤害类型判定
    check("物理是伤害", is_damage_kind(K_PHYS))
    check("魔法是伤害", is_damage_kind(K_MAGI))
    check("魔法·雷是伤害", is_damage_kind("魔法·雷"))
    check("真伤是伤害", is_damage_kind(K_TRUE))
    check("治疗不是伤害", not is_damage_kind(K_HEAL))
    check("增益不是伤害", not is_damage_kind(K_BUFF))
    check("嘲讽不是伤害", not is_damage_kind(K_TAUNT))
    check("被动不是伤害", not is_damage_kind("被动"))
    # seg 类型
    check("物理 seg=phys", seg_of(K_PHYS) == "phys")
    check("魔法 seg=magi", seg_of(K_MAGI) == "magi")
    check("元素魔法 seg=magi", seg_of("魔法·冰") == "magi")
    check("治疗 seg=magi", seg_of(K_HEAL) == "magi")
    check("真伤 seg=true", seg_of(K_TRUE) == "true")
    check("增益 seg=magi", seg_of(K_BUFF) == "magi")
    # 吸血通道
    check("物理吸血通道 phys", lifesteal_channel_of(K_PHYS) == "phys")
    check("魔法吸血通道 magi", lifesteal_channel_of(K_MAGI) == "magi")
    check("元素魔法吸血通道 magi", lifesteal_channel_of("魔法·火") == "magi")
    check("治疗无吸血通道", lifesteal_channel_of(K_HEAL) == "")
    # 枚举字符串兼容（旧 == 语义）
    check("K_PHYS == '物理'", K_PHYS == "物理")
    check("SkillKind.PHYS.value == '物理'", SkillKind.PHYS.value == "物理")

    print(f"\n===== 结果：通过 {passed} / {passed + failed} =====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
