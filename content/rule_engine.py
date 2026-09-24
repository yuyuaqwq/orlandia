# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— 行为彩蛋规则引擎（**规则数据 + 存储读口**半边）。

2026-09-24 B2b（抽包工程 B2 批第二步）：规则**触发形状**（条件判定 + 触发序列）已抽进
扩展包 —— `ext_achieve.rule`（`match_cond` / `fire`，七个句柄 `bind(...)` 注入）。
本模块只剩**这款游戏自己的四样东西**：

  ① 规则表     `RULES` / `_rules()` ← `catalog_b143.RULES`（真源 `content/rules/game_config.json`
               的 rules 组，20 条；W12 收口）
  ② 计数落库   `_counter_key` / `_get_counter` / `_set_counter`（存档面 `event_state`，键名带
               `rule_cnt_` 前缀 —— 怎么落库是存档侧的事，形状不管）
  ③ 时段语义   `_is_time`（白天 05-20 / 夜晚 20-05 / 深夜 23-05；v105 M23 P2-6 与
               time_weather.py 对齐 —— 钟点边界是玩法的设定）
  ④ 模板执行桥 `_fire_event`（`EventContext` + `execute_event_template`；场地名缺省「此地」）
  + 两个存档读口替身：`_count_item`（背包持有数）· `_talk_flag`（对白旗标）

对外面**一字未改**（消费者零改动）：

    content/combat_cmds.py:148   from .rule_engine import fire as _rule_fire
    content/settlement.py:118    from .rule_engine import fire
    content/facade.py:371        wire "rule_fire" → ("content.rule_engine", "fire")
    tests/test_v97_05_rule_engine.py   fire / _get_counter / `RE._is_time` 打桩

★ 注入的时段/计数句柄走**惰性转发 lambda**（`lambda span: _is_time(span)`）—— 打桩
`content.rule_engine._is_time` 依旧立刻生效（形状调用时才解析本模块全局），既有测试零改动。
"""

# ============================================================
# 宿主取件（P4′-W1-B 后 = **零**）
#   · 存档层 → 包内句柄 `content/_pkgref.py:DB`（B1/B2-C2 后不再走宿主）
#   · 事件模板 → 本模块 `_fire_event`（函数级 import `.event_templates`，调用时解析）
#   · 时段判定 `_is_time` → ★ **本模块全局直取**（P4′-W1-B 收口）：注入给形状时用
#     **惰性转发 lambda**，保证 `tests/test_v97_05_rule_engine.py` 对
#     `content.rule_engine._is_time` 的打桩仍然看得见。
# ============================================================
import sys   # noqa: F401  ★ 逐字端口保留：P4′-E 尺子的 `shells/同对象_转发面` 用例把
             #   包内模块的公开名面（`dir(P)`）也钉进快照 —— 删掉它会让该例 n_public_pkg
             #   5→4（非行为差异，但违反「对拍差异 = 0」）。已不再被本模块引用。

from ext_achieve.rule import bind as _bind
from ext_achieve.rule import fire as _shape_fire

from ._pkgref import DB as db


# ── ① 规则表（延迟导入，避免 data 层循环）──────────────────────────────────────
RULES = None


def _rules():
    global RULES
    if RULES is None:
        # W12 收口：真源 `from ..data.rules import RULES as _R` → 包内门面（域：rules/game_config.json）
        from .catalog_b143 import RULES as _R
        RULES = _R
    return RULES


def _db():
    return db


# ── ② 计数落库（存档面）───────────────────────────────────────────────────────
def _counter_key(group_id, qq_id, key):
    return f"rule_cnt_{key}_{group_id}_{qq_id}"


def _get_counter(group_id, qq_id, key) -> int:
    db = _db()
    try:
        return int(db.get_event_state(_counter_key(group_id, qq_id, key)) or 0)
    except Exception:
        return 0


def _set_counter(group_id, qq_id, key, val):
    _db().set_event_state(_counter_key(group_id, qq_id, key), str(val))


# ── ③ 时段语义（钟点边界是本玩法的设定）──────────────────────────────────────
def _is_time(span: str) -> bool:
    import datetime
    h = datetime.datetime.now().hour
    if span == "day":
        # v105 M23 P2-6：与 time_weather.py 口径对齐（白天 08-18 + 清晨 05-08 + 黄昏 18-20，
        # 即非夜晚时段；night = 20:00-5:00）。原 day 6-18 与 night 18-6 与『时间』面板观感冲突
        return 5 <= h < 20
    if span == "night":
        return h >= 20 or h < 5
    if span == "deep_night":
        return h >= 23 or h < 5
    return True


# ── ④ 存档读口（形状侧的两个取件点：持有物 / 对白旗标）────────────────────────
def _count_item(group_id, qq_id, item) -> int:
    return _db().count_item(group_id, qq_id, item)


def _talk_flag(group_id, qq_id, flag) -> bool:
    return _db().get_talk_flags(group_id, qq_id, flag)


def _fire_event(template, params, group_id, qq_id, player, cur_map, hooks):
    """执行 action 模板（形状把「该执行哪条模板 + 参数」交过来，上下文在本侧拼）。"""
    from .event_templates import EventContext, execute_event_template
    ctx = EventContext(group_id, qq_id, player, cur_map,
                       params=params,
                       name=(cur_map or {}).get("name", "此地"),
                       hooks=hooks or {})
    return execute_event_template(template, ctx)


# ── 装配（一次性；形状侧持有的是**同一份对象**，就地改规则表即刻生效）────────────
_bind(rules=lambda: _rules(),
      is_time=lambda span: _is_time(span),
      counter_get=lambda g, q, k: _get_counter(g, q, k),
      counter_set=lambda g, q, k, v: _set_counter(g, q, k, v),
      count_item=_count_item,
      talk_flag=_talk_flag,
      fire_event=_fire_event)


def fire(group_id, qq_id, player, cur_map, trigger, evt=None, hooks=None) -> str:
    """触发器入口（形状在 `ext_achieve.rule.fire`，本函数只做转发）。

    返回触发文本（同一 trigger 最多触发 1 条，按规则表顺序命中即止）；无命中返回 ""。
    """
    return _shape_fire(group_id, qq_id, player, cur_map, trigger, evt=evt, hooks=hooks)
