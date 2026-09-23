# -*- coding: utf-8 -*-
"""包内 **效果层**（`content/effects/`）—— 药水效果 + 场景触发（POI）的取件面。

★ 2026-09-24（B7a）：**场景触发（POI）半边已抽进扩展包** `extends/ext_effect/effects/`。
本文件仍作为包内效果层的**取件面**转出两者，调用方零改动：

| 模块 | 现在在哪 | 注册表 | 入口 |
|---|---|---|---|
| `poi_effects.py` | **扩展包** `ext_effect.effects.poi_effects`（B7a 搬入） | `POI_EFFECTS`（9 世界 + 7 副本 = 16 键） | `execute_poi(effect_name, ctx)`；`ctx = PoiContext(...)` |
| `potion_effects.py` | 仍在包内 `content/effects/potion_effects.py`（B7b 待搬） | `POTION_EFFECTS`（36 键） | `POTION_EFFECTS.get(effect)(battle, player, value)`（未注册 → `None`，调用方跳过） |

POI 那半边的注入面（B7a 起不再 import 包内门面/文案表，全部由调用方给）
------------------------------------------------------------------------------
1. `PoiContext(..., host=…)` —— **宿主写库替身**（真源 = 宿主 `game.db`）：
   `update_player(gid, qid, **fields)` / `add_item(gid, qid, iid, item, count=1)` /
   `set_event_state(k, v)` / `get_event_state(k)` / `set_talk_flag(gid, qid, flag, action)`。
2. `PoiContext(..., dom=…)` —— **内容域访问替身**（真源 = 宿主 `game.content` 薄聚合层 C
   + `game.data.pois` 文案池 + `game.core.instance_run` 名单视图）：
   `MATERIALS` / `CAMPFIRE_FOOD_POOL` / `HERB_POOL` / `pools(name)` / `resolve` /
   `display` / `roll_blueprint(lv)` / `generate_equip(slot, lv, quality)` /
   `living_members(st)` / `set_alive(st, key, value)`
   —— 实现 = 包内 `content/combat_cmds.py::_PoiDom`（单例 `_POI_DOM`）。
3. `PoiContext(..., text=…, static=…)` —— **文案渲染注入**（真源 = 包内 `content/texts.py`）。

方向：**内容 → 引擎/扩展包**。本层零 import 宿主仓；POI 半边还额外做到零 import 数据包。
"""
from __future__ import annotations

from ext_effect.effects.poi_effects import (POI_EFFECTS, PoiContext, execute_poi,
                                            register)
from .potion_effects import DEFAULTS as POTION_DEFAULTS, POTION_EFFECTS

__all__ = [
    "POI_EFFECTS", "PoiContext", "execute_poi", "register",
    "POTION_EFFECTS", "POTION_DEFAULTS",
]
