# -*- coding: utf-8 -*-
"""包内**宿主取件**单点（`content/_hostref.py`）—— 与 `content/_pkgref.py`（包内取件）配对。

为什么要它
----------
`重复实现审计_报告.md` **P0-3**：包内 **21 个文件**各写一份宿主包名常量（`HOST_PKG` /
`HOST_PKG_FALLBACK`，另 `profession.py` / `reward.py` 用 `_HOST_PKG` 私有名），
**10 个文件**各写一份 `_bound_host`（13 行近全同，只差报错前缀），
另有 `_host_mod` ×2（`bridge` / `class_sets`）与 `_wire_module` ×3
（`item_templates` / `party` / `persistence.handles`）。同形不同源 = 迟早分叉。
本模块把这三件事收成**一处**：常量只有一份；样板函数由**工厂**产出，各模块只声明自己的
`label`（报错前缀）与异常类 —— 措辞与取件时机**逐字不变**。

P0-5（`_drops` ×6）同住一处
-------------------------
`_drops()`（4 处，25~27 行）与 `_drops(name)`（2 处）的形状同样是取件样板：
「包内 `content.drops` 直取 → 宿主 `game.core.drops` **同对象兜底**（已加载优先 → importlib）
→ 点名报错」——兜底的半边正是本模块的宿主面 ⇒ 不另立模块，由本文件的两个工厂
`drops_module(label)` / `drops_ctor(label, ...)` 产出（旧版各文件的 `global _DROPS` 缓存
改由工厂闭包持有，行为等价）。

为什么是独立模块（而不是并进已自我声明为「包内取宿主面的唯一口」的 `content/cmds_env.py`）
--------------------------------------------------------------------------------------------
`cmds_env.py` 是**命令层**的宿主面单点（取 `env.state["shell"]`），import `saintess_engine.command`。
本模块却在 **EAGER 装配窗口**里被取件：`item_templates` / `persistence/*` 处在
`game/core/__init__.py → content.smith_stock → content.persistence` 那条链上
（见 `content/_pkgref.py` docstring 里那次实测炸栈）。
⇒ 与 `_pkgref` 同一条纪律：**只依赖标准库 + `saintess_engine.wire`**
（wire 自身只依赖 `types` / `typing`，见其模块头），可安全出现在任何 EAGER 窗口里。
命令层的 `cmds_env` 不是这个约束下的安全依赖，故不并。

口径（行为面 = 逐字保持，不改取件时机）
--------------------------------------
* `make_bound_host`（10 处）：注入句柄面（wire）→ `sys.modules` 已加载的宿主模块（**不 import**）
  → 点名报错。报错类各模块自报（多为 `WireMissing`；`flow/weekly_progress` 自持
  `HostInjectionMissing` 且构造器**不收** `name=` ⇒ `named=False`）。
* `make_host_mod`（2 处）：注入 → `sys.modules` → **importlib 兜底** → 点名报错。
* `make_wire_module`（3 处）：同 `make_host_mod`，但 `name` 为空 = 宿主包本身
  （旧 `item_templates` 版没有这条分支，实测其唯一调用点传的都是非空名 ⇒ 行为等价）。
* 一律**不在本模块另立措辞**：`label` 由调用方给（`"travel"` / `__name__` …），消息格式与原样一致。
"""
from __future__ import annotations

import importlib
import sys

from saintess_engine.wire import WireMissing

#: 宿主包名 —— 运行时（`main.py` 的模块路径 = `data.plugins.dragonfall`）
HOST_PKG = "data.plugins.dragonfall.game"
#: 测试/工具按 `game.xxx` 直接 import 时的兜底包名
HOST_PKG_FALLBACK = "game"

__all__ = ["HOST_PKG", "HOST_PKG_FALLBACK",
           "make_bound_host", "make_host_mod", "make_wire_module",
           "drops_module", "drops_ctor"]


def make_bound_host(wire, label, exc=WireMissing, named=True):
    """工厂：产出某模块专属的 `_bound_host(key, mod=None)`（**不 import 宿主模块树**）。

    `label`  = 报错前缀（各模块原文，如 `"travel"` / `"quests"`）
    `exc`    = 报错类；`named=True` 时额外传 `name=`（`WireMissing` 系列要求点名）
    """
    def _bound_host(key, mod=None):
        """取宿主件：注入句柄面（wire）优先 → 已加载的宿主模块（`sys.modules`，**不 import**）→ 点名报错。"""
        h = wire.handles()
        if key in h:
            return h[key]
        name = mod or key
        for prefix in (HOST_PKG, HOST_PKG_FALLBACK):
            m = sys.modules.get("%s.%s" % (prefix, name))
            if m is not None:
                return m
        msg = "%s：宿主模块 %s 不可用（未 bind_host 且未加载）—— 拒绝静默空跑" % (label, name)
        if named:
            raise exc(msg, name=name)
        raise exc(msg)
    return _bound_host


def make_host_mod(wire, label, exc=RuntimeError):
    """工厂：产出某模块专属的 `_host_mod(name)`（注入 → `sys.modules` → importlib 兜底）。"""
    def _host_mod(name):
        """取宿主子模块（注入优先 → `sys.modules` → importlib；**绝不静默空跑**）。"""
        m = wire.handles().get(name)
        if m is not None:
            return m
        for prefix in (HOST_PKG, HOST_PKG_FALLBACK):
            mod = sys.modules.get("%s.%s" % (prefix, name))
            if mod is not None:
                return mod
        last = None
        for prefix in (HOST_PKG, HOST_PKG_FALLBACK):
            try:
                return importlib.import_module("%s.%s" % (prefix, name))
            except Exception as err:                    # noqa: BLE001
                last = err
        raise exc("%s：宿主模块 %s 取不到（%s）——拒绝静默空跑" % (label, name, last))
    return _host_mod


def make_wire_module(wire, label, exc=RuntimeError, named=False):
    """工厂：产出某模块专属的 `_wire_module(name)`（`name` 为空 = 宿主包本身）。"""
    def _wire_module(name):
        """取宿主子模块（`name` 为空 = 宿主 `game` 包本身，真源 `from .. import X` 那一类）。"""
        if name in wire.handles():
            return wire.handle(name)
        for prefix in (HOST_PKG, HOST_PKG_FALLBACK):
            full = prefix if not name else "%s.%s" % (prefix, name)
            m = sys.modules.get(full)
            if m is not None:
                return m
        last = None
        for prefix in (HOST_PKG, HOST_PKG_FALLBACK):
            full = prefix if not name else "%s.%s" % (prefix, name)
            try:
                return importlib.import_module(full)
            except Exception as err:                    # noqa: BLE001
                last = err
        msg = "%s：宿主模块 %s 取不到（%s）——拒绝静默空跑" % (label, name, last)
        if named:
            raise exc(msg, name=name)
        raise exc(msg)
    return _wire_module


# ============================================================
# P0-5 · `_drops` 取件口工厂（6 处）
# ------------------------------------------------------------
# 形状 = 「包内 `content.drops` 直取 → 宿主同对象兜底（已加载优先 → importlib）→ 点名报错」，
# 兜底的半边正是本模块的宿主面，故与 P0-3 同住一处（不再另立模块）。
# ============================================================

def drops_module(label, pkg="content.drops"):
    """工厂：产出模块专属的 `_drops()` —— 缓存**闭合在工厂里**（旧版是各文件的 `global _DROPS`）。

    语义与旧样板逐字等价：包内 `pkg` 直取失败（`ImportError`）→ 宿主 `game.core.drops` 同对象兜底
    → 两侧都取不到则点名抛（失败**不**入缓存，下次调用照旧重试）。
    """
    state = {"mod": None}

    def _drops():
        """`core.drops` 取件口 —— **包内直取** `content/drops.py`；宿主同对象为过渡保险。"""
        if state["mod"] is None:
            try:
                state["mod"] = importlib.import_module(pkg)
            except ImportError:
                state["mod"] = _host_drops_module(label)
        return state["mod"]
    return _drops


def _host_drops_module(label):
    """宿主 `game.core.drops` 同对象兜底（已加载优先 → importlib → 点名抛）。"""
    for prefix in (HOST_PKG, HOST_PKG_FALLBACK):
        m = sys.modules.get("%s.core.drops" % prefix)
        if m is not None:
            return m
    last = None
    for prefix in (HOST_PKG, HOST_PKG_FALLBACK):
        try:
            return importlib.import_module("%s.core.drops" % prefix)
        except Exception as err:                        # noqa: BLE001
            last = err
    raise RuntimeError("%s：core.drops 取不到（%s）——拒绝静默空跑" % (label, last))


def drops_ctor(label, pkg="content.drops", cands=(".content", ".core.drops")):
    """工厂：产出模块专属的 `_drops(name)` —— 取 `pkg` 上的**构造器**；缺则按 `cands` 回退宿主面。

    回退候选顺序**逐字保持旧样**：按 `cands` 逐个「运行时包路径 → 测试路径」两两相邻展开
    （`(pkg.content, fb.content, pkg.core.drops, fb.core.drops)`），先查 `sys.modules` 且要求
    `hasattr(m, name)`，再 importlib 逐个试。
    """
    def _drops(name):
        """`game.core.drops` 的构造器（包内家 = `content/drops.py`；过渡期回退宿主面）。"""
        try:
            mod = importlib.import_module(pkg)
        except ImportError:
            mod = None
        if mod is not None:
            return getattr(mod, name)
        full_names = tuple(p + c for c in cands for p in (HOST_PKG, HOST_PKG_FALLBACK))
        for fn in full_names:
            m = sys.modules.get(fn)
            if m is not None and hasattr(m, name):
                return getattr(m, name)
        last = None
        for fn in full_names:
            try:
                return getattr(importlib.import_module(fn), name)
            except Exception as err:                    # noqa: BLE001
                last = err
        raise RuntimeError("%s：core.drops.%s 取不到（%s）——拒绝静默空跑" % (label, name, last))
    return _drops
