# -*- coding: utf-8 -*-
"""economy_lib —— 经济数值多阶段多维度模型（2026-09-02，鱼鱼拍板搭建）

参考 numeric_lib（战斗模型）的架构与原则：
  1. 分阶段（ECON_STAGES 6 段：E1 新手 → E6 毕业）
  2. 多维度（产出 / 装备成本 / 生活成本 / 材料供需 / 比率约束）
  3. 约束驱动：每阶段输出健康带检查，任何经济改动跑 economy_scan 验证
  4. 全部数据实读 game/data，不硬编码魔法数
  5. 自带门禁测试（tests/test_economy_toolkit.py）

用途：
  - 材料分阶段定价的依据（供给侧面额 vs 锻造需求）
  - 配方成本重算的验证（40~70% 健康带）
  - 掉落数量封顶的监控
  - 任何经济改动后的回归（economy_scan + check_health）
"""
from .env import setup_env  # noqa
from .constants import (
    ECON_STAGES, ECON_SAMPLE_LV, MATERIAL_PRICE_TIERS, DROP_N_CAP,
    BLUE_EQUIP_KILLS_MIN, BLUE_EQUIP_KILLS_MAX,
    ENHANCE9_MAX_BLUE_MULT, CRAFT_COST_RATIO_MIN, CRAFT_COST_RATIO_MAX,
    DROP_COUNT_NORMAL_MAX, DROP_COUNT_ELITE_MAX,
)
from .core import (
    per_kill_gold, drop_value, income_per_10_kills,
    equip_price, enhance_expected_cost, upgrade_full_cost,
    craft_cost, craft_cost_ratio, inn_cost,
    drop_count_sim, economy_row, economy_scan, check_health,
    profession_scan, shop_scan, heal_alignment_scan,
    instance_reward,
)
from .report import md_table, to_json, health_text

__all__ = [
    "setup_env", "ECON_STAGES", "ECON_SAMPLE_LV", "MATERIAL_PRICE_TIERS",
    "DROP_N_CAP", "BLUE_EQUIP_KILLS_MIN", "BLUE_EQUIP_KILLS_MAX",
    "ENHANCE9_MAX_BLUE_MULT", "CRAFT_COST_RATIO_MIN", "CRAFT_COST_RATIO_MAX",
    "DROP_COUNT_NORMAL_MAX", "DROP_COUNT_ELITE_MAX",
    "per_kill_gold", "drop_value", "income_per_10_kills",
    "equip_price", "enhance_expected_cost", "upgrade_full_cost",
    "craft_cost", "craft_cost_ratio", "inn_cost",
    "drop_count_sim", "economy_row", "economy_scan", "check_health",
    "profession_scan", "shop_scan", "heal_alignment_scan",
    "instance_reward",
    "md_table", "to_json", "health_text",
]
