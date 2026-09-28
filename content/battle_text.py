# -*- coding: utf-8 -*-
"""战斗日志的**文案槽位注入**（R1 · 2026-09-28）—— 引擎侧 cue 迁移的**内容半边**。

引擎那一侧现在长什么样
------------------------------------------------------------------
    `ext_combat/battle/battle.py`：`Battle(..., text=None)`：**鸭子类型**，只要求
                                    `render_or(key, default, **slots)`。
    战斗日志的措辞真源 = **表现事件（cue）**：引擎 `_cue(battle, logs, "<cue 名>", {槽位})`
      → 订阅表（本包 `content/cues.py`，装配点 `content/apply.py`）
        → 引擎 `render_required`：**必须命中**（表里没有该 key ⇒ 抛 + 一行可读坏数据）
          → 本包这张表（cue 名 → texts 域的句子）。
    ⇒ **引擎侧已无任何兜底模板**（B2 起随迁移删净）：不挂订阅 = 每一行只出
      「⚠️ 这条表现没渲染出来（cue 装配/文案缺口，见诊断）」。**这就是本文件存在的原因。**

本模块管的两件事
------------------------------------------------------------------
* 声明面：cue 名 → texts 槽位名。**cue 名与槽位名同名**（同名即接口，不造映射表 ——
  映射表 = 双源温床）；名单**不抄第二份**：`cues.py::cue_names()` 在装配期现读引擎
  `CUE_NAMES` ⇒ 引擎加一条点位，本包的格子必须同批补一条（否则 `check_domain()` 点名抛）。
* 运行面：把 texts 域的句子取出来交给引擎（**本模块不造字、不写文案**）。

三条纪律
------------------------------------------------------------------
1. ⚠️ **渲染口绝不抛**：引擎把元素免疫 / 弱点 / 闪避包在 `try/except` 里（`landing.py`
   / `_roll_dodge`）—— 渲染口一抛，**免疫与闪避判定会被跳过、伤害照常落地**（结算被改）。
   所以本模块对任何输入都返回字符串：没声明过的 key / 槽位缺 / 模板坏 ⇒ 一律回字符串
   （宁可露机器键 + 探针报红）。配套：**装配期** `check_domain()` 做 fail-closed。
2. **声明就要全**：引擎侧 62 个点位全在册（`CUE_NAMES`）。「只声明一部分」那种半接线口径已废
   —— 未声明的那条 cue 每次触发只出一行坏数据，玩家看到的是英文机器键。
3. **不新增第二份文案真源**：值一律从 `content/data/text_specs.json`（文案唯一真源）现取。
"""
from __future__ import annotations

import contextlib
import json
import os

from saintess_engine.text import TextTable, safe_format

from .texts import table as _spec_table          # ★ 文案真源表（包内唯一装载口）

_CACHE: dict = {}


def slots() -> dict:
    """cue 名 → texts 槽位名。**名单从引擎现读**（`cues.py::cue_names`）——
    这里只给「同名即接口」的对应关系，不另抄一份 cue 名单。"""
    if "slots" not in _CACHE:
        from .cues import cue_names
        out = {}
        for n in cue_names():
            if not str(n).startswith("battle."):
                raise ValueError("cue 名形如 `battle.<模块>.<事件>`（照引擎 `CUE_NAMES` 逐字抄）：%r" % (n,))
            out[n] = n
        _CACHE["slots"] = out
    return dict(_CACHE["slots"])


def missing_slots() -> list:
    """声明了、但文案真源表里取不到（或值是空的）—— 装配期就要报出来的那一类。"""
    tbl = _spec_table()
    out = []
    for cue, key in sorted(slots().items()):
        # ★ 用 `get()`（纯查表）而不是 `render_or()`：后者会把这次「体检」记进
        #   真源表的 `requested` 账 ⇒ 污染 `unused()`（死文案自检会以为 62 格都被用过）。
        if not str(tbl.get(key) or "").strip():
            out.append((cue, key))
    return out


def check_slots() -> dict:
    """装配期 fail-closed：声明的槽位都得在文案真源里取得到。缺 ⇒ **当场抛并点名**。"""
    bad = missing_slots()
    if bad:
        raise KeyError(
            "cue 的文案格在文案真源（content/data/text_specs.json）里取不到：%s\n"
            "⇒ 引擎发这条 cue 时只会出一行坏数据；去文案真源按同名键补一格再重装"
            % " · ".join("%s→%s" % (c, k) for c, k in bad))
    return slots()


def table() -> TextTable:
    """引擎要的那张表（`render_or` / `__contains__` 鸭子类型）—— 进程内只建一次。

    表里就是**声明的那些**（cue 名 = 键）；引擎那条路要求**必须命中** ⇒ 缺格即报错。
    引擎 `TextTable` 自带 `missing()` / `unused()` 记账 ⇒ 探针靠它验
    「声明的 cue 真被引擎请求过」（防死槽位）。
    """
    if "table" not in _CACHE:
        src = _spec_table()
        entries = {}
        for cue, key in slots().items():
            val = src.get(key)                                  # 纯查表：不渲染、不记账
            if str(val or "").strip():
                entries[cue] = val
        _CACHE["table"] = TextTable(entries, name="orlandia.battle")
    return _CACHE["table"]


def battle_text() -> TextTable:
    """`Battle(text=…)` 的实参（语义名 —— 调用点不必知道它是 `TextTable`）。"""
    return table()


# ══════════════════════════════════════════════════════════════
# ★ 一次性遮挡：**自付血**那一笔的引擎通用伤害行
# ══════════════════════════════════════════════════════════════
#: 引擎那条**通用伤害行**的 cue 名（`landing.py::_apply_damage` 的 else 支）。
_ENGINE_DAMAGE_CUE = "battle.landing.damage"


class _QuietOnce:
    """`battle.text` 的**临时替身**：只顶掉一条 key，其余原样转发给真表。"""

    __slots__ = ("_t", "_armed")

    def __init__(self, table):
        self._t = table
        self._armed = True

    def render_or(self, key, default, /, **slots):
        if self._armed and key == _ENGINE_DAMAGE_CUE:
            self._armed = False
            return ""                 # 总线 `_render` 见到空串**直接不出行**
        if self._t is None:           # 没注入表 ⇒ 与 `render_or(None, …)` 同一条路
            return safe_format(default, slots)
        return self._t.render_or(key, default, **slots)

    def __contains__(self, key) -> bool:
        """★ 「表里有没有这一格」—— cue 那条路走 `render_required` / `text_hit`，
        它**问的就是这一句**。缺了它：每个 cue 都出一行坏数据（表现层静悄悄地全坏）。"""
        return self._t is not None and key in self._t

    def __getattr__(self, name):
        if self._t is None:
            raise AttributeError(name)
        return getattr(self._t, name)


@contextlib.contextmanager
def quiet_engine_damage(battle):
    """★ **这一调** `deal_damage` 里的引擎通用伤害行被顶掉（cue 路不出行）。

    总线在 ⇒ **两张一起换**（同一个替身，共用一个「一次性」开关），还原时两张一起还
    （cue 总线在 `Build` 那一刻抓走了表的引用，光换 `battle.text` 顶不掉）。
    总线不在（引擎树还没合 cue 形状 / 这场战斗没接 cue）⇒ 行为与接线前逐字相同。
    """
    _orig = getattr(battle, "text", None)
    _bus = getattr(battle, "cues", None)
    _bus_tbl = getattr(_bus, "table", None) if _bus is not None else None
    _guard = _QuietOnce(_orig)
    battle.text = _guard
    if _bus is not None:
        _bus.table = _guard
    try:
        yield
    finally:
        battle.text = _orig
        if _bus is not None:
            _bus.table = _bus_tbl
