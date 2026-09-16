# -*- coding: utf-8 -*-
"""包内名字索引（`content/index.py`）—— 游戏仓 `game/core/index.py`（56 行）**逐字端口**（B13-L7）。

正文（`pinyin_id` / `build_index` / `resolve` / `display`）一字未改；本文件另管**索引归属**：

归属变化（B15-W1，2026-09-14）
------------------------------
* **改前**：`_INDEXES` 是**宿主装配产物** —— 宿主 `game/data/_assembly.py:179-278` 用宿主表建好，
  放在宿主 `game.data._INDEXES` 上；包内 `_indexes()` 反向去读宿主（`data` 句柄的 `_INDEXES`）
  ⇒ 删掉宿主 `game/data`，`resolve/display` 立刻死。
* **改后**：`_INDEXES` = **包内自建**（`content/index_build.py` 逐字端口那份构建逻辑，表来源 = 包内
  门面 / 域读口）；`_indexes()` 首次访问时构建一次，之后同一只字典（宿主 `_assembly` 的
  `build_index(...)` 调用也落在它上面 —— 写入语义与改前「包内写、宿主读同一只字典」等价）。
  **不再有「读宿主 data」的路径**。

兼容面（签名保持，取件面已收口）
--------------------------------
* `bind_host(...)`：保留（老调用方按老签名调不炸）。**索引构建完全不碰它** —— S3 探针实测
  `content/index_build.py::GAP_SOURCES` = `{'WEAPON_TYPES': 'domain:equipment', 'WT_CN':
  'facade:content.catalog_b143', 'QUALITY_CN': 'facade:content.catalog_b143'}`，17/17 张表
  全部来自包内；原 `_host_data()` 三级兜底的第 ③ 级（宿主 `game.data`）与
  宿主 `_INDEXES` 同一只子 dict 的兼容镜像（同名函数）**在终态都是死路** —— S3 已删
  （终态 `data` 句柄 = `content.catalog_legacy`，既无 3 张缺口表、也无 `_INDEXES`）。
  `index_build._gap_tables()` 仍保留 `_host_getter` 形参（缺省 `None` = 不启用该级）。
* `content/index_build.py::GAP_SOURCES` 记录每张缺口表的实际来源（探针/报告取证用）。

⚠️ `pypinyin` 是第三方纯计算库（无 IO/无宿主知识）—— 包内直接用，与宿主同源同版本。
"""
from __future__ import annotations

from pypinyin import lazy_pinyin

from saintess_engine.wire import Wire
_WIRE = Wire()

# 包内自建索引（`content/index_build.build_into` 的产物；模块级唯一一份）
_INDEXES: dict = {}
_BUILT = False


def bind_host(**objs):
    """宿主替身注入（幂等）——兼容注入口，保留旧签名不让老调用方 import 炸。

    **索引构建不依赖它**：17/17 张表全部来自包内（`content/index_build.py::GAP_SOURCES`
    实测 = `domain:equipment` / `facade:content.catalog_b143`，无 `host:*`）。
    """
    _WIRE.bind(**objs)


def _indexes() -> dict:
    """包内自建的名字索引（`content/index_build.build_into` 的产物）。

    首次访问触发构建（惰性：包 import 期不读任何域文件，也不会撞宿主半初始化）；
    构建恰好一次 —— `_BUILT` 先置位再进 `build_into`，故其内部的 `build_index(...)` 重入是安全的。
    """
    global _BUILT
    if not _BUILT:
        _BUILT = True
        from . import index_build as _index_build
        _index_build.build_into(_INDEXES)
    return _INDEXES


def pinyin_id(name: str) -> str:
    """中文名 → 拼音 id：狼皮 → lang_pi；保留字母/数字"""
    parts = []
    for ch in name:
        if '\u4e00' <= ch <= '\u9fff':
            parts.append(lazy_pinyin(ch)[0])
        elif ch.isalnum() or ch == '_':
            parts.append(ch.lower())
    return "_".join(parts)


def build_index(table_name: str, table: dict, prefix: str = "", name_field: str = None):
    """从表构建 名字↔id 双向索引。

    table: 内容表（key 即显示名，或 value[name_field] 为显示名）
    prefix: id 前缀（如 mat_ / sk_ / rec_），无则直接用 pinyin_id
    name_field: 若 value 是 dict 且含该字段，用 value[name_field] 做显示名；
                否则 key 本身即显示名。

    v48：若 key 已是 ID（不含中文）→ 直接用 key 作为 id，不再从名字重新生成
    （旧版会把 i_treatment_potion 这类 ID key 再转一次，产生 it_i___t... 畸形 ID）
    """
    n2i, i2n = {}, {}
    for k, v in table.items():
        if name_field and isinstance(v, dict) and v.get(name_field):
            nm = v[name_field]
        else:
            nm = k
        if not any('\u4e00' <= ch <= '\u9fff' for ch in str(k)):
            eid = k  # v48：key 已是 ID，直接采用
        else:
            eid = f"{prefix}{pinyin_id(nm)}" if prefix else pinyin_id(nm)
        # 冲突时 id 保持稳定：若已存在同名 id，追加后缀
        if eid in i2n and i2n[eid] != nm:
            eid = f"{eid}_{len(i2n) + 1}"
        n2i[nm] = eid
        i2n[eid] = nm
    _indexes()[table_name] = {"name_to_id": n2i, "id_to_name": i2n}


def resolve(table_name: str, name_or_id: str):
    """统一解析：输入名字或 id，都返回 id(找不到原样返回)"""
    idx = _indexes().get(table_name, {}).get("name_to_id", {})
    return idx.get(name_or_id, name_or_id)


def display(table_name: str, entity_id: str):
    """id → 显示名(找不到原样返回)"""
    idx = _indexes().get(table_name, {}).get("id_to_name", {})
    return idx.get(entity_id, entity_id)


__all__ = ["pinyin_id", "build_index", "resolve", "display", "bind_host", "_INDEXES", "_indexes"]
