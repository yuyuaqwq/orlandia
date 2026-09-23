# -*- coding: utf-8 -*-
"""包内 **效果层**（`content/effects/`）—— 药水效果 + 场景触发（POI）的取件面。

★ 2026-09-24（B7a）：**场景触发（POI）半边已抽进扩展包** `extends/ext_effect/effects/`。
本文件仍作为包内效果层的**取件面**转出两者，调用方零改动：

| 模块 | 现在在哪 | 注册表 | 入口 |
|---|---|---|---|
| `poi_effects.py` | **扩展包** `ext_effect.effects.poi_effects`（B7a 搬入） | `POI_EFFECTS`（9 世界 + 7 副本 = 16 键） | `execute_poi(effect_name, ctx)`；`ctx = PoiContext(...)` |
| `potion_effects.py` | ★ **2026-09-24 B7b 已搬进扩展包** `ext_effect/effects/potion_effects.py`（模块级注入口 `bind(text/static/items/rules/neg_keys)`；本层只留取件面） | `POTION_EFFECTS`（36 键） | `POTION_EFFECTS.get(effect)(battle, player, value)`（未注册 → `None`，调用方跳过） |

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
from ext_effect.effects.potion_effects import (DEFAULTS as POTION_DEFAULTS,
                                               POTION_EFFECTS)


def bind_effects():
    """★ 2026-09-24 B7b：把**药水侧**的三样读口注入扩展包（装配期调用一次，幂等）。

    为什么要有这一步：药水半边正在/已经搬进 `ext_effect`，而扩展包**不许 import 数据包**
    ⇒ 它那三样读口（items 域 / EFFECT_RULES / 净化负面键清单）与文案渲染改由**数据包侧注入**。

    数据源与搬前**一字不换**：仍是包内那三份 JSON，仍走包内读口 `content/_domainio`；
    只是把「谁去读盘」从扩展包挪回数据包。三个 getter 是**惰性**的（首次使用时读一次并缓存）
    —— 与搬前 `_items_domain()` / `_effect_rules()` 的缓存语义逐字相同。

    装配点唯一：`content/apply.py::install_engine()`（引擎 `stack.install()` 时调）。
    """
    from .. import texts as _TS
    from .. import _domainio as _DIO
    from ext_effect.effects import potion_effects as _PE
    _PE.bind(text=_TS.text, static=_TS.static,
             items=lambda: _DIO.read_domain("items"),
             rules=lambda: _DIO.read_domain("effect_rules", sub="rules"),
             neg_keys=lambda: _DIO.read_domain("purify_neg_keys"))


__all__ = [
    "POI_EFFECTS", "PoiContext", "execute_poi", "register",
    "POTION_EFFECTS", "POTION_DEFAULTS", "bind_effects",
]
