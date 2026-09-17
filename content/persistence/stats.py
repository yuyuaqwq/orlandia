# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— **存档层 stats 域**（B17，2026-09-14）。

真源：宿主 `game/store/stats.py`（逐字端口：正文一字未改，**只动「取件」**）。
宿主 `game/store/stats.py` 现在只剩一层**委托薄壳**（`from content.persistence.stats import *`）。

| 真源写法 | 包内替身 | 为什么 |
|---|---|---|
| `from .connection import _connect, _lock[, atomic]` | `from .handles import ...` | 连接/锁/事务三个句柄由**注入面**给（宿主工厂注入 db_path） |
| `from .. import content as C` | `from .handles import C`（`_HostMod("content")`） | 包内禁 import 宿主（I2）；宿主内容面走既有句柄约定 |
| 函数内 `from ..<宿主模块> import <名>` | `_host_attr("…", "…")` / `_host_attrs(...)` | 同位置、调用时解析（与真源「函数内惰性 import」同刻） |
| `time.time()` | `clock()` | 时钟是四个注入点之一（默认 = stdlib `time.time`，行为零变化） |

**注入面**：`content/persistence/handles.py`（`bind(db_path=…, clock=…, flush_log=…, lock=…)`）；
宿主装配点 = `game/store/store_factory.py`。纯包环境（编辑器）需注入自己的句柄 —— 见 B19/B20 接点。

★ U1-D2 L5（形状迁移）：命名计数改走引擎 `store/counters`（`CounterSpec`/`Counters`）。
`STAT_FIELDS` 就是 `CounterSpec.fields`（**白名单 fail-closed**，口径分歧 ⑦）；
`day_kills`/`day_date` 这对「日计数」**不进白名单**（口径分歧 ⑤：周期归零归 `periodic.PeriodCounter`）。
表结构仍由 `persistence/tables.json` 建（**一字节不动**）；对外签名与返回**逐键逐值不变**。
"""
from saintess_engine.store import Column, DeclaredRepository, TableSpec
from saintess_engine.store.counters import CounterSpec, declare_counters

from .handles import _connect, _lock, get_db

"""奥兰迪亚·余烬纪年存储层 - stats"""

# B2 加固（2026-08-10）：stats 表可 bump 列白名单（qq_id/day_date 为 TEXT 不参与 +1 不列入）。
STAT_FIELDS = {
    "kills", "elite_kills", "boss_kills", "deaths", "day_kills", "visited_areas",
    "inst_clears", "party_count", "fish_count", "gather_count", "mine_count",
    "cook_count", "alchemy_count", "craft_count", "enhance_count",
    "enchant_count", "world_events", "catch_collect", "chests_opened",
}

#: 计数器形状（**形状在引擎、取值在这里**）：`stats` = 单主键 + 一行多列（口径分歧 ⑥）。
_CNT_SPEC = CounterSpec("stats", owner="qq_id", fields=tuple(sorted(STAT_FIELDS)))
#: `achievements` = 复合主键 `(qq_id, ach_key)` + 计数格（与 bestiary 同形的另一处落点）。
_ACH_SPEC = CounterSpec("achievements", owner="qq_id",
                        fields=("progress", "claimed"), subject="ach_key")
_CNT = None
_CNT_ACH = None


def _cnt():
    """stats 计数器读写口（表由 `tables.json` 建；此处只把既有表装配成引擎形状）。"""
    global _CNT
    if _CNT is None:
        db = get_db()
        _CNT = declare_counters(
            db, _CNT_SPEC,
            repo=DeclaredRepository(db, TableSpec("stats", [Column("qq_id", "TEXT", pk=True)])))
    return _CNT


def _cnt_ach():
    """achievements 计数器读写口（复合键 `(qq_id, ach_key)`）。"""
    global _CNT_ACH
    if _CNT_ACH is None:
        db = get_db()
        _CNT_ACH = declare_counters(
            db, _ACH_SPEC,
            repo=DeclaredRepository(
                db, TableSpec("achievements",
                              [Column("qq_id", "TEXT", pk=True),
                               Column("ach_key", "TEXT", pk=True)])))
    return _CNT_ACH


def init_stats(group_id, qq_id):
    with _lock:
        conn = _connect()
        try:
            _cnt().init(conn, qq_id)
            conn.commit()
        finally:
            conn.close()

def bump_stats(group_id, qq_id, **fields):
    # B2 加固（2026-08-10）：动态列名前白名单校验（白名单 = `CounterSpec.fields`，
    # fail-closed 由引擎 `Counters.bump` 当场 `ValueError`；口径分歧 ⑦）
    with _lock:
        conn = _connect()
        try:
            _cnt().bump(conn, qq_id, **fields)
            conn.commit()
        finally:
            conn.close()

def get_stats(group_id, qq_id):
    with _lock:
        conn = _connect()
        try:
            return _cnt().read(conn, qq_id)
        finally:
            conn.close()

def set_achievement(group_id, qq_id, ach_key, progress, claimed=0):
    with _lock:
        conn = _connect()
        try:
            _cnt_ach().repo.upsert(conn, {
                "qq_id": qq_id, "ach_key": ach_key,
                "progress": progress, "claimed": claimed,
            })
            conn.commit()
        finally:
            conn.close()

def get_achievements(group_id, qq_id):
    with _lock:
        conn = _connect()
        try:
            return _cnt_ach().read_subject(conn, qq_id)
        finally:
            conn.close()



__all__ = [
    "_connect",
    "_lock",
    "STAT_FIELDS",
    "init_stats",
    "bump_stats",
    "get_stats",
    "set_achievement",
    "get_achievements",
]
