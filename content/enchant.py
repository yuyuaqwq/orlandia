# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— 附魔数值（B13-L1 端口，2026-09-14）。

真源：游戏仓 `game/core/enchant.py`（46 行）**逐字端口**。宿主同名文件已改薄壳。

取件（★ B16-W11 收口 · 2026-09-14：`ENCHANT_*` 归包）
1. `from .affix import _affix_base_value` → **本线包内直取**（`content/affix.py`）。
2. `from .constants import PCT_STATS` → **包内读口** `from .tables import PCT_STATS`
   （`content/rules/panel_rules.json` → `content/tables.py`；与宿主 `core/constants.PCT_STATS` 逐值逐序相等）。
3. `ENCHANT_RECIPES` → 包内门面 `content/catalog_b143.py`（`enchant` 域，序 = 真源插入序）；
   `ENCHANT_MAX_VALUE` → 包内门面 `content/catalog_rules.py`（包内**无域** ⇒ 值随代码 dump，
   已登记 `NOT_YET_DOMAINED`，建域后改读 `content/data/enchant.json`）。
4. `from .stats import equip_stats` → 宿主**函数**句柄 `宿主面取件("core.stats", "equip_stats")`
   （`core/stats.py` 归 B13-L6；句柄属「函数名」类，按收口纪律不切）。

正文一字未改：只换「取值来源」（原 `_D.<名>` → 同名门面名）。
"""

# ============================================================
# 宿主替身口（`content/index.py` / `content/world_cmds.py` 同款：注入优先 → sys.modules →
# importlib；**绝不静默空跑**）
# ============================================================
from saintess_engine.wire import slot as _slot
_WIRE, bind_host = _slot()


# -*- coding: utf-8 -*-

from .affix import _affix_base_value          # B13-L1：本线包内直取
from .tables import PCT_STATS                  # 包内读口（与宿主 constants.PCT_STATS 逐值相等）

# ---- 包内门面（B16-W11：`ENCHANT_*` 归包）----
from .catalog_b143 import ENCHANT_RECIPES                    # `enchant` 域（序 = 真源插入序）
from .catalog_rules import ENCHANT_MAX_VALUE                 # 包内无域 → dump 字面量（NOT_YET_DOMAINED）


"""奥兰迪亚·余烬纪年数据层 - enchant.py"""
def enchant_value(slot: str, lv: int, stat: str, big: bool = False) -> int | float:
    """附魔数值：白板基础 * ratio；大成功 1.5x；crit/dodge 固定小值"""
    from .stats import equip_stats
    rec = ENCHANT_RECIPES.get(stat)
    if not rec:
        return 0
    if stat in PCT_STATS:
        v = rec["ratio"]
    else:
        base = equip_stats(slot, lv, "white").get(stat, 0)
        if base <= 0:
            base = _affix_base_value(slot, lv, stat)
        v = max(1, int(base * rec["ratio"]))
    if big:
        v = v * 1.5
        if stat in PCT_STATS:
            v = round(v, 3)
    if stat in ENCHANT_MAX_VALUE:
        v = min(v, ENCHANT_MAX_VALUE[stat])
    return v

def enchant_match_material(stat: str, items: list) -> str | None:
    """从背包物品里找第一个匹配该附魔系的材料名(无则 None)"""
    rec = ENCHANT_RECIPES.get(stat)
    if not rec:
        return None
    for it in items:
        d = it.get("data", {})
        # F2-3：材料判定放宽——gm/部分发放路径材料入包缺 type 字段（或 type=兽材，
        #   如余烬甲片），原按 type==\"材料\" 过滤导致背包有材料却报\"没有材料\"（report_11 P1-1）。
        #   改按材料 key 规范 mat_ 前缀兜底（全库材料 key 均 mat_ 开头，v48 ID 规范）。
        if d.get("type") != "材料" and not str(it.get("key", "")).startswith("mat_"):
            continue
        name = d.get("name", "")
        if any(kw in name for kw in rec["mats"]):
            return name
    return None

