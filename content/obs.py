# -*- coding: utf-8 -*-
"""包内观测口 —— 包内拿 **LOG（文本日志）/ tlog（结构化流水）** 的**唯一取用口**。

★ 本文件 = 注入契约；取件机制 = 引擎 wire 形状（`saintess_engine.wire.Wire`）。
   本模块**不 import 宿主**（方向只有 内容 → 引擎/标准库），也不 import 包内其它模块 ——
   它只持有「注入进来的句柄」。

契约来源（逐条按**引擎真实代码**，不是设计稿）
--------------------------------------------------------------------------------
1. 引擎**没有** LOG 注入面：`saintess_engine/host/env.py:16-51` 的 `Env` 字段表里没有日志字段；
   引擎日志只有中性门面 `saintess_engine.log.get_logger(name, prefix=…)`
   （`saintess_engine/log/facade.py:72`，命名前缀**由调用方给**，不配置 = 标准库薄封装）。
   平台日志名 `"astrbot"` 硬编码在宿主 `game/log_setup.py:20-23`（`HOST_LOGGER` / `LOG`）
   ⇒ 包内不许硬编码平台名（`b2_impact.md` U5）⇒ **只能拿注入句柄**。
2. 引擎有 `Env.tlog`（`host/env.py:47` + `env.now_tlog` `:86-92`），但它接的是**适配器
   `on_tlog` 钩子**（`host/runtime.py:155-163` 与 `:217` 的 `tlog=self.tlog_write`），
   钩子不给 = 丢弃（`host/runtime.py:44` `"on_tlog": "丢弃（流水不落库）"`）。
   真源宿主**没有**实现该钩子（`grep -n on_tlog game/**/*.py` = 0 命中）⇒
   对游戏流水而言 `Env.tlog` 是「丢弃」；游戏流水的真源与出口是宿主 `game/tlog_setup.py`。
   `content/tlog_collect.py` 是**另一个东西**（战斗流水采集器 `BattleTLog`，靠引擎观察者通道），
   不提供 `kinds/enable/disable/enabled/tlog/emit` 控制面。
3. 流水「默认关」是宿主白纸黑字的契约：`game/tlog_setup.py:91-104`（`enabled()` / `tlog()` →
   None）+ `:107-124`（`emit()` 未启用直接返回 None，异常也不影响主流程）。

唯一路径 / 注入方 / 时机
------------------------
    包内一切 LOG / tlog 取用 → `content/obs.py`
    唯一注入口 = 本模块 `bind(log=…, tlog=…, host_pkg=…)`（写入内部 `Wire` 句柄面）
    注入方  = 宿主壳（`game/**`）在 **import 期**调用，与既有 `bind_host(...)` 同刻同形
              （实例：`game/reward.py:91` / `game/services/profession.py:57`
              / `game/services/player_event_bus.py:32` / `game/commands/talk_actions.py:42`）。
    测试里怎么给 = 直接 `obs.bind(log=<假 logger>, tlog=<假模块>)`（见 `tests/test_obs.py`）。

解析顺序（三级，**绝不 import 宿主**）
--------------------------------------
    ① `bind(...)` 注入的句柄（住内部 `Wire`；`Wire.handle` 缺 → `WireMissing`）
    ② `sys.modules` 里**已加载**的宿主模块（`data.plugins.dragonfall.game.log_setup` /
       `game.log_setup`，tlog 同理）—— 过渡期兜底（宿主侧**一个字节不动**，
       真源宿主必然已加载该模块），与既有包内替身 `_host_module()` 的 sys.modules 口径一致。
       ★ 这一级 **wire 形状没有对应物**（`Wire.handle` 只有「bind / 惰性」两态，不查 sys.modules）
       ⇒ 按铁律 4 原样保留在取值器里，不许硬塞。
    ③ fail-closed：抛 `WireMissing`（RuntimeError 子类；**点名 + 不静默降级**）。

fail-closed 语义（逐条，别搞混「装配缺陷」与「未启用」）
--------------------------------------------------------
    log()      ①/② 都取不到 → **抛 `WireMissing`（点名 `LOG`）**。**不退回 stdlib logger /
                不返回 None**：改个名字的 logger 是第二棵日志树 = 静默降级。
    emit()     句柄取不到 → **抛 `WireMissing`**（宿主没接上 = 装配缺陷）；
                句柄在、`tlog()` 返 None → **返回 None（零行为）**——这是契约（来源 3），
                不是降级；`emit` 内部异常照宿主口径吞掉（`game/tlog_setup.py:121-124`）。
    enabled()  句柄取不到 → 抛；句柄在 → 转发宿主判定。
"""
from __future__ import annotations

import sys
from typing import Any, Optional

from saintess_engine.wire import Wire, WireMissing

__all__ = ["bind", "log", "tlog", "enabled", "emit", "HOST_LOGGER_ATTR"]

#: 宿主 logger 的模块级属性名（`game/log_setup.py:23 LOG`）
HOST_LOGGER_ATTR = "LOG"

#: 宿主模块在 sys.modules 里的两个候选全名（与既有包内替身同口径：
#: `content/reward.py:44-45` / `content/talk_actions.py:75-76`：运行时包路径 + 测试路径）
from ._hostref import HOST_PKG, HOST_PKG_FALLBACK  # 宿主包名常量单源（P0-3）

#: 注入句柄面（引擎 wire 形状：`bind()` 写；取不到 → `WireMissing` 点名）
_WIRE = Wire()

#: `bind(host_pkg=…)` 的 sys.modules 兜底包名覆盖（`None` = 用 `HOST_PKG`）
_PKG_OVERRIDE: Optional[str] = None


def bind(log: Any = None, tlog: Any = None, host_pkg: Optional[str] = None) -> None:
    """注入唯一口（幂等；`None` 忽略，不覆盖已注入值 —— 与 `Wire.bind` 同口径）。

    log     : 文本日志门面（宿主 `game/log_setup.LOG`，或任何有 `.warning/.info/...` 的对象）
    tlog    : 流水句柄 —— 宿主 `game/tlog_setup` **模块**（推荐，控制面全给：`emit/enabled/tlog`）
              或任何有 `.emit(kind, actor=…, **fields)` 的对象
    host_pkg: 覆盖 sys.modules 兜底的宿主包名（缺省见 `HOST_PKG`；测试/换包时可给）
    """
    global _PKG_OVERRIDE
    if host_pkg:
        _PKG_OVERRIDE = str(host_pkg)
    _WIRE.bind(log=log, tlog=tlog)


def _loaded_host_module(name: str):
    """取**已加载**的宿主子模块（只查 `sys.modules`，**绝不 import 宿主模块树**）。"""
    pkgs = (HOST_PKG if _PKG_OVERRIDE is None else _PKG_OVERRIDE, HOST_PKG_FALLBACK)
    for prefix in pkgs:
        mod = sys.modules.get("%s.%s" % (prefix, name))
        if mod is not None:
            return mod
    return None


def _fail(what: str, name: str):
    """fail-closed：`WireMissing` 点名（RuntimeError 子类，既有 `except RuntimeError` 不变）。"""
    raise WireMissing(
        "content.obs：%s 取不到（未 bind() 且宿主模块 %s 未加载）—— 拒绝静默空跑" % (what, name),
        name=what)


def log():
    """取文本日志门面（唯一路径；取不到 → 抛，**不退回 stdlib logger**）。"""
    try:
        return _WIRE.log
    except WireMissing:
        pass
    mod = _loaded_host_module("log_setup")
    handle = getattr(mod, HOST_LOGGER_ATTR, None) if mod is not None else None
    if handle is None:
        _fail("LOG", "log_setup")
    return handle


def tlog():
    """取流水实例（唯一路径）。

    返回 `None` = **宿主契约里的「未启用」**（`game/tlog_setup.py:98-104`），零行为；
    **句柄本身取不到**（装配缺陷）→ 抛。
    """
    try:
        handle = _WIRE.tlog
    except WireMissing:
        handle = _loaded_host_module("tlog_setup")
        if handle is None:
            _fail("tlog 句柄", "tlog_setup")
    getter = getattr(handle, "tlog", None)
    return getter() if callable(getter) else handle


def enabled() -> bool:
    """流水是否启用（未接上句柄 → 抛；接上 → 转发宿主判定，见 `game/tlog_setup.py:91-95`）。"""
    try:
        handle = _WIRE.tlog
    except WireMissing:
        handle = _loaded_host_module("tlog_setup")
        if handle is None:
            _fail("tlog 句柄", "tlog_setup")
    fn = getattr(handle, "enabled", None)
    return bool(fn()) if callable(fn) else True


def emit(kind: str, actor: str = "", **fields):
    """埋点便捷口（与宿主 `game/tlog_setup.emit` 同签名同语义）。

    * 未接上句柄（装配缺陷）→ **抛 `WireMissing`**（不静默 no-op）
    * 已接上但未启用（`tlog()` 为 None）→ **返回 None**（契约零行为）
    * 写流水异常 → 吞掉返回 None（`game/tlog_setup.py:121-124`：流水异常绝不影响主流程）
    * 字段名与保留参数（`kind`/`actor`/`tags`）撞名时用 `fields={...}` 包一层
    """
    try:
        handle = _WIRE.tlog
    except WireMissing:
        handle = _loaded_host_module("tlog_setup")
        if handle is None:
            _fail("tlog 句柄", "tlog_setup")
    getter = getattr(handle, "tlog", None)
    tl = getter() if callable(getter) else handle
    if tl is None:
        return None
    try:
        return tl.emit(kind, actor=str(actor or ""), **fields)
    except Exception:                                            # noqa: BLE001
        return None
