# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— 存档层**注入面**（B17，2026-09-14）。

「宿主零逻辑」的落点：包内 `content/persistence/*` 只吃**注入句柄**，绝不 import 宿主模块；
宿主只负责「连接怎么来」—— 四个注入点：

| 句柄 | 谁给 | 包内怎么用 | 默认 |
|---|---|---|---|
| `db_path` | 宿主工厂（env `GWEN_GAME_DB` / 插件目录 `game_data.db`） | 建引擎 `Database(db_path, timeout=10)` | 无（未注入即抛，**拒绝静默空跑**） |
| `clock` | 宿主工厂（`time.time`） | 旧 `time.time()` 调用点全改 `clock()` | `time.time` |
| `flush_log` | 宿主工厂（日志 sink；默认静默） | 装配诊断（`schema.install`）单点 | no-op |
| `lock` | 引擎 `Database.lock`（RLock，可重入） | `_lock`（代理，`with _lock:` 逐语义等价） | 注入值 → 否则 Database 的 RLock |

注入方式 = 模块级 `bind(**handles)`（与包内既有 `bind_host` 约定同形，不另发明第三套）。
宿主面取件 = 引擎 wire 形状（`saintess_engine.wire`）：注入句柄面 = `_WIRE`（`bind_host` 写），
`宿主模块取件` / `宿主面取件` / `_wire_attrs` / `_HostMod` 只补 wire 管不到的两级
（`sys.modules` 已加载 → importlib）。

★ W2a 改指（2026-09-15）：`C` 不再指向**宿主** `game.content`，
改指**包内聚合门面** `content/facade.py::C`（`from ..facade import C`）。
等价性 = 探针逐名对象同一性（71 名 / 298 处，`out/probe/c_facade_identity.log` BAD=0）
+ 取件时机不变（两侧都是属性访问时解析）。`宿主模块取件` / `宿主面取件` / `_wire_attrs` /
`_HostMod` **保留**（`cmds_gm` / `persistence/players` / `persistence/battle_state` 仍在用）。
"""
from __future__ import annotations

import importlib
import sqlite3
import sys
import threading
import time as _time

# ★ W2a 改指：包内内容聚合门面（原 `C`（包内惰性门面句柄） → 宿主 `game.content`）。
#   `content.facade` 零 import 依赖（只 import importlib）⇒ 放在 import 期不会把 EAGER 窗口
#   拖进半初始化；`C.<名>` 的取件时机仍是**属性访问时**（facade.C 是惰性句柄），逐字同旧。
from ..facade import C  # noqa: F401

_DEFAULT_TIMEOUT = 10.0
_H = {"db_path": None, "clock": None, "flush_log": None, "lock": None, "db": None}


def bind(db_path=None, clock=None, flush_log=None, lock=None, db=None):
    """注入句柄（幂等；`None` = 不改）。返回本模块便于链式调用。"""
    for k, v in (("db_path", db_path), ("clock", clock), ("flush_log", flush_log),
                 ("lock", lock), ("db", db)):
        if v is not None:
            _H[k] = v
    return _H


def db_path():
    """库路径句柄（必须由宿主注入 —— 包不知道部署在哪）。"""
    p = _H["db_path"]
    if not p:
        raise RuntimeError("content.persistence：db_path 句柄未注入（宿主工厂 store_factory 负责注入）")
    return p


def clock():
    """时钟句柄 —— **当前时间戳**（`bind(clock=<零参可调用>)`；默认 stdlib `time.time`）。"""
    return (_H["clock"] or _time.time)()


def flush_log(msg):
    """日志 sink 句柄（默认静默 = 行为与改造前零差异）。"""
    fn = _H["flush_log"]
    if fn is not None:
        fn(msg)


def get_db():
    """引擎连接骨架（`saintess_engine.store.Database`）—— 按注入路径**惰性**建一次。"""
    db = _H["db"]
    if db is None:
        from saintess_engine.store import Database
        from . import schema
        db = Database(db_path(), timeout=_DEFAULT_TIMEOUT)
        schema.install(db)
        _H["db"] = db
    return db


def set_db(db):
    """测试/工具替换连接骨架（重置缓存；不注册 schema）。"""
    _H["db"] = db
    return db


def lock():
    """进程内单锁句柄（引擎 `Database.lock` = RLock；可被 `bind(lock=…)` 覆盖）。"""
    return _H["lock"] or get_db().lock


def connect():
    return get_db().connect()


def atomic():
    return get_db().atomic()


def init_db():
    return get_db().init()


class _LockProxy:
    """`_lock` 句柄代理：`with _lock:` / `acquire` / `release` 逐语义委托给真锁。"""

    def __enter__(self):
        return lock().__enter__()

    def __exit__(self, *exc):
        return lock().__exit__(*exc)

    def acquire(self, *a, **k):
        return lock().acquire(*a, **k)

    def release(self):
        return lock().release()

    def __getattr__(self, item):
        return getattr(lock(), item)


_lock = _LockProxy()


class _ConnProxy:
    """借出的连接包装：`close()` = **归还**（不真关），归还前回滚未提交事务。

    ★ 2026-09-18（实测驱动）：包内 116 处持久化调用点都是宿主逐字端口的
    「开连接 → 读写 → commit → close」短事务形态。SQLite 默认
    `journal_mode=DELETE` + `synchronous=FULL` ⇒ **每次 commit 都 fsync 落盘**
    （实测 6.9ms/次）：单个冻结门禁 18610 次 commit 花 128.5s、25998 次 connect
    再花 14.9s，合计占该测试 2/3 墙钟 —— 真实玩家每次捡物品/买卖/存取仓库同样
    在付这笔钱。改 WAL 后 commit 降到 0.32ms，但「每次开新连接」反而更贵
    （WAL 要 attach `-wal`/`-shm`，实测 3.4ms/次）⇒ 必须同时复用连接。

    等价性：SQLite 里「关闭一条带未提交事务的连接」= 回滚该事务；本代理 `close()`
    先在 `in_transaction` 时 `rollback()` 再归还 ⇒ **逐语义等价**（调用方一字不改）。
    线程隔离：连接只在本线程内复用（sqlite 默认 `check_same_thread=True`）。
    """

    __slots__ = ("_conn", "_free")

    def __init__(self, conn, free):
        self._conn = conn
        self._free = free

    def close(self):                        # 归还而非真关
        c = self._conn
        try:
            if c.in_transaction:
                c.rollback()
        except sqlite3.Error:
            pass
        self._free.append(c)

    def __getattr__(self, item):            # execute / commit / cursor / row_factory …
        return getattr(self._conn, item)

    def __enter__(self):                    # 与 sqlite3.Connection 同形（事务边界，不关连接）
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        return False


_POOL = threading.local()


def _connect():
    """取一条连接（**线程本地复用**）：语义同引擎 `connect()`，代价低一个数量级。

    调用方照常 `commit()` / `close()`，事务边界与原来完全一致
    （未提交即关闭 = 回滚）。连接归还后留在本线程池里复用。
    """
    free = getattr(_POOL, "free", None)
    if free is None:
        free = _POOL.free = []
    return _ConnProxy(free.pop() if free else connect(), free)


# ============================================================
# 宿主替身口（与包内既有约定同形：注入优先 → sys.modules → importlib；绝不静默空跑）
# ============================================================
from saintess_engine.wire import Wire, WireMissing

#: 宿主模块在 `sys.modules` 里的两个候选全名（运行时包路径 + 测试路径）
HOST_PKG = "data.plugins.dragonfall.game"
HOST_PKG_FALLBACK = "game"

#: 注入句柄面（引擎 wire 形状：`bind_host()` 写；`None` = 没给）
_WIRE = Wire()


def bind_host(**objs):
    """宿主薄壳 import 期注入（幂等）——键 = 宿主面名（`content` / `db`）。"""
    _WIRE.bind(**objs)


def _wire_module(name: str):
    if name in _WIRE.handles():
        return _WIRE.handle(name)
    for prefix in (HOST_PKG, HOST_PKG_FALLBACK):
        full = prefix if not name else "%s.%s" % (prefix, name)
        m = sys.modules.get(full)
        if m is not None:
            return m
    last = None
    for prefix in (HOST_PKG, HOST_PKG_FALLBACK):
        try:
            return importlib.import_module(prefix if not name else "%s.%s" % (prefix, name))
        except Exception as exc:                    # noqa: BLE001
            last = exc
    raise WireMissing("%s：宿主模块 %s 取不到（%s）——拒绝静默空跑" % (__name__, name, last),
                      name=name)


def _wire_attr(mod: str, attr: str):
    """宿主模块属性 —— 真源「函数内 `from ..<mod> import <attr>`」的同义替身（调用时解析）。"""
    m = _wire_module(mod)
    try:
        return getattr(m, attr)
    except AttributeError:
        for prefix in (HOST_PKG, HOST_PKG_FALLBACK):
            try:
                return importlib.import_module("%s.%s" % (
                    prefix if not mod else "%s.%s" % (prefix, mod), attr))
            except Exception:                       # noqa: BLE001
                continue
        raise


def _wire_attrs(mod: str, *attrs):
    """多符号版 `宿主面取件` —— 真源「`from ..<mod> import a, b, c`」的同位置一行替身。"""
    return tuple(_wire_attr(mod, a) for a in attrs)


class _HostMod:
    """宿主模块替身 ——`X.xxx` 正文一字未改，属性访问时解析。

    ★ W2a 起 `C` **不再**用本类（改指包内门面 `content/facade.py::C`）；本类保留是因为
    `content/cmds_gm.py` 仍 `from .persistence.handles import _HostMod`，且它是包内其他
    宿主面替身（如各模块自带的 `db` 句柄）的同形样板。
    """

    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        return getattr(_wire_module(self._name), attr)


#: 包内内容聚合门面句柄（真源 模块级 `from .. import content as C`）——见文件头「W2a 改指」。
#: `C` 已在本文件 import 期从 `..facade` 绑定（见顶部 import 注释）。
