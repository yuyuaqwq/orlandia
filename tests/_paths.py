# -*- coding: utf-8 -*-
"""包内测试的路径装配 —— 包根 / 引擎根（发现 + 醒目报错）/ 宿主壳根。

本文件是 `pkg/tests/**` 里**唯一**做路径发现的地方；`conftest.py` 与
`_engine_harness.py` 都从这里取（迁入前这两处各自按「qqbot/ 根布局」硬拼路径，
包仓里那个布局不存在）。

口径
----
包根      = 本文件所在目录（`tests/`）的上一级
引擎根    = 环境变量 `GWEN_FRAMEWORK_DIR` 优先
            → 否则按候选位置发现（相对包根）：`../framework` · `../framework-engine` · `./framework`
            → 都找不到 → **醒目报错**（打印清楚缺什么、试过哪些候选），
              **不许静默 SKIP 装绿**
宿主壳根  = 环境变量 `GWEN_HOST_DIR` 优先
            → 否则 = 引擎根所在部署树的根（`<部署根>/host/shell.py`；宿主壳是包内测试的
              **平台驱动面**，见 `tests/_engine_harness.py`；`host/**` 属宿主仓，不在包仓内）
            → 都找不到 → **醒目报错**

只依赖标准库；导入本模块 = 「路径装配完成」（副作用仅 sys.path）。
"""
from __future__ import annotations

import os
import sys

#: `pkg/tests/`
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
#: 包仓根（`pkg/`）
PKG_ROOT = os.path.dirname(TESTS_DIR)

FRAMEWORK_ENV = "GWEN_FRAMEWORK_DIR"
HOST_ENV = "GWEN_HOST_DIR"
_FRAMEWORK_CANDIDATES = ("../framework", "../..", "../framework-engine", "framework")
#:   `../..` 覆盖两种真实布局：部署（`<plugin>/framework/games/<pkg>` → 祖父 = `<plugin>/framework`）
#:   与引擎仓（`<eng>/games/<pkg>` → 祖父 = 引擎根）。判据仍用 `_has_engine()`，不认空目录。


def _has_engine(root: str) -> bool:
    """引擎根判据：`<root>/saintess_engine/package.py` 在位（不认空目录/同名目录）。"""
    return os.path.isfile(os.path.join(root, "saintess_engine", "package.py"))


def _host_shell(root: str) -> str:
    """宿主壳路径（`<root>/host/shell.py`）。"""
    return os.path.join(root, "host", "shell.py")


def find_engine_root() -> str:
    """发现引擎根；找不到 → 抛 RuntimeError（醒目文本，绝不静默跳过）。"""
    tried = []
    env = (os.environ.get(FRAMEWORK_ENV) or "").strip()
    if env:
        tried.append(("%s=%s" % (FRAMEWORK_ENV, env), os.path.abspath(env)))
    for rel in _FRAMEWORK_CANDIDATES:
        tried.append((rel, os.path.abspath(os.path.join(PKG_ROOT, rel))))
    for label, root in tried:
        if _has_engine(root):
            return root
    lines = [
        "",
        "!" * 78,
        "!! 找不到引擎根（framework）：包内测试无法装配 —— 不静默跳过，直接失败。",
        "!! 包根            = %s" % PKG_ROOT,
        "!! 需求            = <引擎根>/saintess_engine/package.py",
        "!! 试过的候选位置：",
    ]
    for label, root in tried:
        lines.append("!!   - %-28s -> %s  [%s]"
                     % (label, root, "有" if os.path.isdir(root) else "无此目录"))
    lines.append("!! 修法：设 %s=<引擎框架仓根>，或把引擎仓放到包仓的 ../framework / "
                 "../.. （祖父，部署布局即 <plugin>/framework）/ ../framework-engine / ./framework。"
                 % FRAMEWORK_ENV)
    lines.append("!" * 78)
    raise RuntimeError("\n".join(lines))


def find_host_root(engine_root: str) -> str:
    """发现宿主壳根（含 `host/shell.py`）；找不到 → 抛 RuntimeError（醒目文本）。"""
    tried = []
    env = (os.environ.get(HOST_ENV) or "").strip()
    if env:
        tried.append(("%s=%s" % (HOST_ENV, env), os.path.abspath(env)))
    tried.append(("引擎根同部署树", os.path.dirname(os.path.abspath(engine_root))))
    for label, root in tried:
        if os.path.isfile(_host_shell(root)):
            return root
    lines = [
        "",
        "!" * 78,
        "!! 找不到宿主壳根（host/shell.py）：包内测试的平台驱动面缺失 —— 不静默跳过。",
        "!! 引擎根        = %s" % engine_root,
        "!! 试过的候选位置：",
    ]
    for label, root in tried:
        lines.append("!!   - %-24s -> %s  [%s]"
                     % (label, root, "有" if os.path.isdir(root) else "无此目录"))
    lines.append("!! 需求          = <候选根>/host/shell.py")
    lines.append("!! 口径          = 宿主壳 `host/**` 属宿主仓，默认与引擎仓同处一棵部署树"
                 "（<部署根>/framework + <部署根>/host）；换布局时设 %s。" % HOST_ENV)
    lines.append("!" * 78)
    raise RuntimeError("\n".join(lines))


ENGINE_ROOT = find_engine_root()
HOST_ROOT = find_host_root(ENGINE_ROOT)

#: 包根优先（`content.*` 归包内真源）；其后引擎根（`saintess_engine`）、宿主壳根（`host`）。
#:
#: ★ T8（2026-09-16）：**无条件置前**（原来是「不在 sys.path 才 insert」）。
#:   翻车点（实测：部署布局下 `test_v1302e_setview.py` 报
#:   `ModuleNotFoundError: No module named 'host.shell'`）：
#:   全量跑器为宿主自留件把 `<plugin>` 与 `<plugin>/framework` 摆进了 PYTHONPATH
#:   ⇒ 这两个根「已在 sys.path」⇒ 旧写法跳过 insert ⇒ 它们留在 PYTHONPATH 的原位置，
#:   而测试自己又 `sys.path.insert(0, os.path.abspath("."))`（cwd = 工作区根）
#:   ⇒ 工作区根排在 `<plugin>` 前面 ⇒ `import host` 命中 `<ws>/host/__init__.py`
#:   （= 宿主仓目录本身，是个包）而不是 `<plugin>/host/`（真宿主壳）⇒ `host.shell` 不存在。
#:   与 `_engine_harness.py` 的 R4 修复同一课：**路径装配点必须把四个根无条件摆到最前**。
for _p in (HOST_ROOT, ENGINE_ROOT, PKG_ROOT, TESTS_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

__all__ = ["TESTS_DIR", "PKG_ROOT", "ENGINE_ROOT", "HOST_ROOT",
           "find_engine_root", "find_host_root", "FRAMEWORK_ENV", "HOST_ENV"]
