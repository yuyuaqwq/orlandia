# -*- coding: utf-8 -*-
"""N01 模拟战斗助手 numeric_sim —— 供所有数值胜率类测试 import（不 import 任何测试文件）

用法：
    from numeric_sim import class_battle_matrix, player_panel, monster_of

    wins, avg_round = class_battle_matrix("战士", 11, {"str": 39}, {}, "dps", 16, seeds=8)
    # -> (8, 4.6)：8 场里胜 8 场，平均 4.6 回合

    st = player_panel("法师", 11, {"int": 39})          # player_final_stats 面板
    m  = monster_of("dps", 16)                           # C.build_monster 展开的怪 dict

实现口径（与生产命令层同源，不 mock 核心公式）：
  - 玩家：`player_final_stats` 面板 → `battle_bridge.prepare_player_for_battle`（开战仪式）
    → `battle_bridge.build_sides`（player_to_actor / enemies_to_actors）
  - 战斗：`saintess_engine` 的 `Battle`（B2）用 `human_act` 驱动，直到 `b.result` 非空
  - 固定种子序列 seed 0..N-1：每场先 `random.seed(seed)` 再建人开打（可复现）
  - GWEN_GAME_DB 用 setdefault 指向 tests/test_game_data.db（尊重测试脚本预置的私有库）

迁移记录（2026-09-12）
--------------------
本文件曾被误归档到 `_archive_unused/retired_old_engine_20260911/`（判"零引用"时漏了
`scripts/numeric_lib/*`、`scripts/numtool.py`、`gen_numeric_matrix.py` 这些活消费方），
且它引用的旧包装层 `game/battle.py`（`BT.Battle(btype=, enemy=, player=)` + `actor_turn`）
已随 v181.N10-C 删除。本轮两件都修：文件放回 + 循环迁到新引擎签名
（`B2("monster", sides=…)` + `human_act`），口径用旧基线数值复核（见文件末自检）。
"""
import os
import sys

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # dragonfall/
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_PLUGIN_DIR, "test_game_data.db"))

import random  # noqa: E402

from _engine_harness import C  # noqa: E402
from content.panel import player_final_stats  # noqa: E402
from content.bridge import (  # noqa: E402
    apply_battle_loadout, build_sides, prepare_player_for_battle,
)
from saintess_engine import Battle as B2  # noqa: E402

# 自由属性点：初始 DEFAULT_ATTR_PTS=9 + 每级 +3（升级结算，见 content_rules/panel.py），
# 11 级 = 9 + 10×3 = 39 点。任务卡 N01 明确用 39 点。
PLAYER_LV = 11
ATTR_PTS_TOTAL = C.DEFAULT_ATTR_PTS + (PLAYER_LV - 1) * 3  # 9 + 30 = 39

# 各职业代表技能（lv<=11 可学的攻击技能，use_skill=True 时使用；中文名，进 learned_skills）
REP_SKILL = {
    "战士": "猛击",     # 120% 物理
    "法师": "冰晶术",   # 105% 魔法
    "游侠": "瞄准射击",  # 140% 物理
    "牧师": "惩戒",     # 120% 魔法（lv10，单机唯一输出技）
    "刺客": "割裂",     # 115% 物理
    "拳师": "碎骨拳",   # 150% 物理
}

# 标准 39 点分配（职业主流加点，任务卡 N01）
STD_ATTR = {
    "战士": {"str": 39},
    "法师": {"int": 39},
    "游侠": {"agi": 39},
    "牧师": {"int": 39},
    "刺客": {"agi": 39},
    "拳师": {"str": 39},
}

_MAX_TURNS = 500  # 单场回合护栏（防极端情况死循环；正常对局远低于此）
_ACT_TICK = 1     # 1 刻 = 1 时刻 = 1 游戏秒（saintess_engine.battle.schedule）


def _tick_of(b) -> int:
    """回合数展示口径 = 行动轮次（旧包装层 `_tick_no()` = int(now / ACT_TICK) + 1 同式）。"""
    return int(b._now / _ACT_TICK) + 1


def player_panel(cls: str, lv: int = PLAYER_LV, attr: dict | None = None, equip: dict | None = None) -> dict:
    """玩家最终面板：player_final_stats(cls, lv, equip, tier=0, attr) 结果 dict。

    docstring 用法：st["max_hp"] / st["atk"] / st["matk"] / st["def"] / st["spd"] / st["crit"] ...
    """
    return player_final_stats(cls, lv, equip or {}, 0, attr if attr is not None else {})


def monster_of(role: str, lv: int) -> dict:
    """C.build_monster 展开一只怪：role ∈ tank/dps/caster/speedster/healer/boss/elite。

    返回带 hp/max_hp/atk/def/matk/mdef/spd/exp/gold... 的完整怪 dict（无掉落、无技能）。
    """
    mid = "m_sim_%s_%d" % (role, lv)
    return C.build_monster(
        (mid, "测试%s" % role, role, lv, [], []),
        {"id": mid, "name": "测试%s" % role, "area": "field", "lv": lv},
    )


def build_player(cls: str, lv: int, attr: dict, equip: dict | None, learned: list | None = None) -> dict:
    """玩家 DB dict（与命令层开战前同构）——面板值来自 player_final_stats。"""
    st = player_final_stats(cls, lv, equip, 0, attr)
    return {
        "class_name": cls, "level": lv, "class_tier": 0, "evolve_path": 0,
        "equipment": dict(equip or {}), "attributes": dict(attr),
        "learned_skills": list(learned or []),
        "hp": st["max_hp"], "mp": st["max_mp"], "max_hp": st["max_hp"], "max_mp": st["max_mp"],
        "race": "human", "title_bonus": None,
    }


def make_battle(player: dict, monster: dict):
    """按生产口径起一场战斗：开战仪式 → build_sides → 装配 → B2(sides=…)。

    装配序列与命令层同源（`combat._open_battle` / `tower` 调的是同一个
    `battle_bridge.apply_battle_loadout`）——**少了这一步胜率会假性偏低**。
    """
    prepare_player_for_battle(player, None, None)
    sides = build_sides(player, [dict(monster)])
    for _a in sides.get("player", []):
        apply_battle_loadout(_a, None)
    return B2("monster", sides=sides)


def class_battle_matrix(cls: str, lv: int, attr: dict, equip: dict | None,
                        monster_role: str, monster_lv: int,
                        seeds: int = 8, use_skill: bool = False) -> tuple[int, float]:
    """跨级胜率模拟：同一职业玩家 vs 同一只怪，固定种子跑 seeds 场。

    返回 (胜场数, 平均回合)。每场：random.seed(seed)（seed=0..seeds-1）→
    构造玩家（FRAMEWORK 模板，learned_skills 默认 []）→ B2 战斗 → 循环
    human_act 直到 b.result 为 victory/defeat（护栏 _MAX_TURNS 兜底）。

    use_skill=True：每回合按 REP_SKILL[cls] 施放代表技能（自动写入 learned_skills）；
    技能施放被拦截（蓝/资源/CD 未就绪）当回合自动转普攻。
    use_skill=False（默认）：纯普攻，基础战斗力对比。
    """
    equip = equip or {}
    assert cls in REP_SKILL, "未知职业: %s" % cls
    assert attr, "必须给属性点 dict（标准 39 点可查 STD_ATTR）"

    wins, rounds_sum = 0, 0
    m = monster_of(monster_role, monster_lv)  # 每格（怪）只建一次，与等级/角色完全确定
    for seed in range(max(1, int(seeds))):
        random.seed(seed)  # 固定种子序列 seed 0..N-1，可复现
        learned = [REP_SKILL[cls]] if use_skill else []
        player = build_player(cls, lv, attr, equip, learned)
        b = make_battle(player, m)
        skill_name = REP_SKILL[cls] if use_skill else None
        turns = 0
        while b.result is None and turns < _MAX_TURNS:
            # 技能拦截判据：未消耗行动（_p_acts 不变）且未分胜负 → 转普攻
            prev_acts = b._p_acts
            b.human_act("skill" if use_skill else "attack", skill_name, b.focus())
            if use_skill and b._p_acts == prev_acts and b.result is None:
                b.human_act("attack", None, b.focus())
            turns += 1
        if b.result == "victory":
            wins += 1
        rounds_sum += _tick_of(b)
    avg_round = rounds_sum / max(1, int(seeds))
    return wins, round(avg_round, 2)


if __name__ == "__main__":
    # 自检示例：直接 python tests/numeric_sim.py
    print("== numeric_sim 自检（11 级标准 39 点 × 普通 dps 怪，seeds=8 纯普攻）==")
    for cls, attr in STD_ATTR.items():
        w, ar = class_battle_matrix(cls, 11, attr, {}, "dps", 11)
        print("  %s 11v11 dps: %d/8 胜, 平均 %s 回合" % (cls, w, ar))
    print("== 旧基线复核（NUMERIC_TEST.md §失衡基线清单）==")
    w, _ = class_battle_matrix("刺客", 11, STD_ATTR["刺客"], {}, "dps", 22)
    print("  刺客全敏 11v22：%d/8（旧基线 0/8 全败）" % w)
