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
扩展包根  = 环境变量 `SAINTESS_EXTENDS`（`os.pathsep` 分隔）优先
            → 否则 = `<引擎根>/extends`（引擎 / 部署树的行内布局）
            → 目录不存在 → 跳过（**不是**错误：不带扩展包的仓布局没有这一层）
              ★ 口径与 `saintess_engine.package.default_ext_dirs()` 同源：这里是「装 `ext_*/`
                目录的那一层」；2026-09-24 起包内测试会直接 `from ext_combat import …`
                （引擎搬迁后 ext_* 就是那些形状的实现面）⇒ 搜索根必须进 `sys.path`，
                否则只能靠外部 PYTHONPATH 兜着（外部一漏就 16 个文件整片红）。

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
EXTS_ENV = "SAINTESS_EXTENDS"
_FRAMEWORK_CANDIDATES = ("../framework", "../..", "../framework-engine", "framework")
#:   `../..` 覆盖部署布局（<plugin>/framework/games/<pkg> → 祖父）与引擎仓布局。


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
                 "../framework-engine / ./framework。" % FRAMEWORK_ENV)
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


def find_ext_roots() -> list:
    """扩展包**搜索根**（装 `ext_*/` 目录的那一层，按优先级）：环境变量 → 引擎根行内 `extends`。

    与 `saintess_engine.package.default_ext_dirs()` 同一套口径（那边可选给 `exts=`）；
    这里只负责「把根摆到 `sys.path`」，不负责装载。
    """
    out: list = []
    for part in (os.environ.get(EXTS_ENV) or "").split(os.pathsep):
        part = part.strip()
        if part and os.path.isdir(part):
            out.append(os.path.abspath(part))
    inline = os.path.join(ENGINE_ROOT, "extends")
    if os.path.isdir(inline):
        out.append(inline)
    dedup: list = []
    for p in out:
        if p not in dedup:
            dedup.append(p)
    return dedup


EXT_ROOTS = find_ext_roots()

#: 包根优先（`content.*` 归包内真源）；其后引擎根（`saintess_engine`）、扩展包搜索根（`ext_*`）、
#: 宿主壳根（`host`）。★ T8（2026-09-16）起这份顺序就是 `sys.path` 的**前置段**（无条件置前）。
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
#: ★ T9（2026-09-24）：扩展包搜索根进同一段（`ext_*` 是搬迁后那些形状的实现面，
#:   包内测试直接 import 它们）——不再依赖外部 PYTHONPATH。
_PREPENDED = [TESTS_DIR, PKG_ROOT, ENGINE_ROOT] + EXT_ROOTS + [HOST_ROOT]
for _p in reversed(_PREPENDED):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

__all__ = ["TESTS_DIR", "PKG_ROOT", "ENGINE_ROOT", "HOST_ROOT", "EXT_ROOTS",
           "find_engine_root", "find_host_root", "find_ext_roots",
           "FRAMEWORK_ENV", "HOST_ENV", "EXTS_ENV"]
