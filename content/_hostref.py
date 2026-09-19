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
           "make_bound_host", "make_host_mod", "make_wire_module"]


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
