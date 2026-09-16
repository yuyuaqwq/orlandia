# -*- coding: utf-8 -*-
"""包内声明式条件表的**唯一读口**：`content/data/cond_specs.json`。

形状：`{"<族名>": {"<条目键>": <声明节点>, ...}, ...}`。
节点形状与算子表由引擎侧给（`saintess_engine.conditions.declarative`）——
本模块只管「读盘 + 按族取」，不解释节点、不认识任何字段名。

为什么单独一个文件：五个族（称号 / 成就 / 隐藏怪环境 / 对话 / 限定采集条件词）
分处五个模块，但共用**同一张**声明表；读盘只此一处，坏 JSON / 缺族都当场炸
（fail-closed：绝不静默返回空表，那会把「声明丢了」伪装成「判定不满足」）。
"""
from __future__ import annotations

import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cond_specs.json")

_CACHE = None


def _load_all() -> dict:
    global _CACHE
    if _CACHE is None:
        with open(_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        if not isinstance(doc, dict):
            raise ValueError("cond_specs.json 顶层必须是对象：%r" % (type(doc).__name__,))
        _CACHE = doc
    return _CACHE


def load(family: str) -> dict:
    """取一族的声明表；缺失 / 非对象 → 抛（fail-closed，不返回空表）。"""
    doc = _load_all()
    if family not in doc:
        raise KeyError("cond_specs.json 没有族 %r（已有：%r）" % (family, sorted(doc)))
    table = doc[family]
    if not isinstance(table, dict):
        raise ValueError("族 %r 必须是对象：%r" % (family, type(table).__name__))
    return table


def reload() -> None:
    """丢掉缓存，下次 `load()` 重新读盘（供重载/测试用）。"""
    global _CACHE
    _CACHE = None
