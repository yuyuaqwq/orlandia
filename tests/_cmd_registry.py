# -*- coding: utf-8 -*-
"""测试共享：命令正则 / 声明的统一扫描（**唯一实现**）。

背景
----
原先有**三份**各自实现的「扫命令层装饰器拿正则」逻辑：
`test_v87_command_matrix.py` / `test_v59_newline_cmd.py` / `test_v104_commands_system.py`。
三份 = 装饰器写法一变就要改三处（2026-09-11 引入 `@declared("key")` 时就是这样）。

统一到这里后，形态变化只改本文件。**终态来源全解析**（★ P5F-REPOINT）：

* 正则 / `priority` —— 包内声明表 `content/data/commands.json`（声明是唯一真源）
* 键集             —— 包内**运行时注册表** `pkg.command_handlers()`（`content/cmds_*.py` 的
  `@register("<key>")`）∪ 平台例外键（`host/adapter_qq.py::PLATFORM_KEYS`：包内有声明、
  宿主层实现，包内无处理器）
* 宿主壳 `game/commands/*.py` 的 `@filter.regex(<字面量>)` / `@declared("<key>")` 扫描
  已随删壳批退役（那一层不存在了）

用法::

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _cmd_registry import pattern_map, patterns_with_meta, declared_usage

注意：本文件**不以 `test_` 开头**，不会被 `scripts/run_all_tests.py` 当测试跑。
"""
from __future__ import annotations

import ast
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(_HERE)
# ★ P5F-REPOINT: 原宿主壳 `game/commands` + `game/data/command_specs.json`（随删壳批消失）
#   → 包内真源 `content`（实现/登记目录）+
#     `content/data/commands.json`（声明真源，196 条）。删壳后此处仍有落点。
PKG_ROOT = PLUGIN_DIR
CMD_DIR = os.path.join(PKG_ROOT, "content")
SPEC_FILE = os.path.join(CMD_DIR, "data", "commands.json")
#: 正则/priority 的出处标签（`patterns_with_meta()` 第 3 元；原为命令模块文件名）
SPEC_LABEL = "content/data/commands.json"

import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配


def _combine(patterns):
    """多条正则合成一条 —— 用框架实现（单一真源）；框架不可用 → 本地等价兜底。"""
    pats = [p for p in (patterns or ()) if p]
    if not pats:
        return ""
    if len(pats) == 1:
        return pats[0]
    try:
        from saintess_engine.command import combine_patterns
        return combine_patterns(pats)
    except Exception:                                        # noqa: BLE001
        return "|".join("(?:%s)" % p for p in pats)


def load_specs() -> dict:
    """声明表原始 dict（缺失/损坏 → 空 dict）。"""
    try:
        with open(SPEC_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def declared_patterns() -> dict:
    """`{声明key: 正则}`（来自声明表）。"""
    return _declared_from(load_specs())


def _declared_from(specs) -> dict:
    """声明表 dict → `{key: 合并正则}`（`declared_patterns()` / `patterns_with_meta()` 共用）。"""
    out = {}
    for k, v in (specs or {}).items():
        pats = v.get("patterns", v.get("pattern")) if isinstance(v, dict) else v
        if isinstance(pats, str):
            pats = [pats]
        c = _combine(pats or [])
        if c:
            out[str(k)] = c
    return out


def _unwrap_handler(fn):
    """取回 `content/commands.py::register` 包住的真实现（lambda 默认参数里那层）。"""
    seen = 0
    while (callable(fn) and getattr(fn, "__name__", "") == "<lambda>"
           and fn.__defaults__ and seen < 3):
        nxt = fn.__defaults__[0]
        if not callable(nxt):
            break
        fn = nxt
        seen += 1
    return fn


def _runtime_handlers() -> dict:
    """包内**运行时命令处理器表** `{key: entry}`（引擎 `Package.command_handlers()`）。

    包物化走测试侧唯一驱动口 `_engine_harness`（`content/commands.py::COMMANDS`）。
    """
    from _engine_harness import harness
    return dict(harness().host.handlers or {})


def _platform_keys() -> tuple:
    """平台例外键（`_maint_gate` + 4 条转发型）：包内有声明、**宿主层实现**，包内无处理器。

    键名真源 = 宿主适配器（`host/registration.py` 同款「别抄第二份」口径）。
    """
    import _engine_harness                                     # noqa: F401  先导：置前 PLUGIN_DIR
    from host.adapter_qq import PLATFORM_KEYS
    return tuple(PLATFORM_KEYS)


def runtime_keys() -> set:
    """终态运行时命令面键集 = 包内处理器键 ∪ 平台例外键。"""
    return set(_runtime_handlers()) | set(_platform_keys())


def patterns_with_meta() -> dict:
    """`{声明key: (正则, priority, 出处)}`；终态真源 = 包内声明表 + 包内运行时注册表。

    ★ P5F-REPOINT: 原先 AST 扫宿主 `game/commands/*.py` 的 `@declared("<key>")`
    （宿主壳随删壳批消失）→ 改为：
      * 键集 = 包内**运行时注册表**（`pkg.command_handlers()` ∪ 平台例外键）；
      * 正则 / `priority` = 包内**声明表**（`content/data/commands.json`，唯一真源）。

    `MISSING`（fail-closed 可见，不静默丢）：运行时注册表里有、声明表里没有的 key
    （漏登记）与声明表里有、运行时注册表里没有的 key（死声明）都记在这里。
    """
    specs = load_specs()
    declared = _declared_from(specs)
    runtime = runtime_keys()
    del MISSING[:]
    for key in sorted(runtime - set(declared)):
        MISSING.append((key, key, "<runtime>"))         # 有处理器无声明（漏登记）
    for key in sorted(set(declared) - runtime):
        MISSING.append((key, key, "<declaration>"))     # 有声明无处理器（死声明）
    found = {}
    for key, pat in declared.items():
        entry = specs.get(key)
        prio = entry.get("priority") if isinstance(entry, dict) and "priority" in entry else None
        found[key] = (pat, prio, SPEC_LABEL)
    return found


# `@declared("key")` / `@register("key")` 有使用但声明表里没该 key 的收集表（测试断言应为空）
MISSING = []


def pattern_map() -> dict:
    """`{方法名: 正则}`（最常用形态）。"""
    return {n: p for n, (p, _prio, _f) in patterns_with_meta().items()}


def declared_usage() -> dict:
    """`{处理器名: 声明key}`（终态 = 包内**运行时注册表**；处理器名从取件解出）。

    ★ P5F-REPOINT: 原扫宿主壳 `game/commands/*.py` 的 `@declared("<key>")`（随删壳批消失）
    → 包内登记面 = `content/commands.py::COMMANDS`（`@register("<key>")` + 循环/别名登记
    两种写法都有，**AST 扫不全**），故直接读运行时注册表并按名反解处理器函数名。
    约定「声明 key ≡ 处理器名」；唯一历史异名 `register_()` → `"register"` 由本表保留映射。
    """
    out = {}
    for key, entry in sorted(_runtime_handlers().items()):
        fn = _unwrap_handler(entry.get("handler")) if isinstance(entry, dict) else None
        name = getattr(fn, "__name__", "") or ""
        out[name if name and name != "<lambda>" else key] = key
    for key in _platform_keys():        # 平台例外：宿主层实现，包内无处理器 → 名 ≡ key
        out.setdefault(key, key)
    return out
