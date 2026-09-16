# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— 存档层**表结构装载**。

表结构声明在 `content/persistence/tables.json`（表序 / 列序 / 类型 / 主键 / 非空 / 默认 /
`migrations`），本文件只做装载：`install(db)` 走引擎的
`saintess_engine.store.declare_file`，逐表 `declare` —— 建表语句与「老库缺列自愈」
迁移都由引擎从同一份声明派生，表结构不再在「首建」和「补列清单」两处各写一遍。

装配序 = `tables.json` 的表声明序；`identity_map(qq_id)` 索引在 `migrations` 里。
注册动作由宿主工厂 / 包内 `handles.get_db()` 调一次（幂等）。

`C_MAP_IDS` 是地图 id 集合的惰性缓存（`store` 层内部做集合运算用），与表结构无关，
按原样留在这里。
"""
from __future__ import annotations

import os

from saintess_engine.store import declare_file

from .handles import flush_log
# 内容聚合面取自**包内门面**（`content.facade` 零 import 依赖，EAGER 窗口安全）。
from ..facade import C  # noqa: F401

# 表结构声明文件（包内路径惯例：模块文件所在目录的上一级 + data/）。
_TABLES_JSON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tables.json")

# v135 装配期循环解除：connection 不再顶层依赖 content（data._assembly → core →
# smith_stock → db → store.connection → content 未完成初始化）。C_MAP_IDS 改为
# 惰性求值——首次访问时 content 必已完成装配（消费端都在命令层运行期）。
_C_MAP_IDS_CACHE = None


def _map_ids() -> set:
    global _C_MAP_IDS_CACHE
    if _C_MAP_IDS_CACHE is None:
        _C_MAP_IDS_CACHE = set(C.MAP_BY_ID.keys())
    return _C_MAP_IDS_CACHE


# 兼容旧引用（store 层内部使用 C_MAP_IDS 做集合运算）
C_MAP_IDS = _map_ids()


# ================= 建表注册（装载声明文件：建表 + 缺列自愈 + init）=================
def install(db):
    """把 `content/persistence/tables.json` 的表结构声明注册到**注入的连接骨架**上（宿主工厂调一次；幂等）。

    逐表 `declare`：引擎从同一份声明派生建表语句与补列迁移，并当场 `db.init()`
    （自带幂等；调用方随后的 `init_db()` 是重复无害）。
    """
    repos = declare_file(db, _TABLES_JSON)
    flush_log("persistence.schema：已声明 %d 张表（persistence/tables.json；db=%s）"
              % (len(repos), _db_path_of(db)))
    return db


def _db_path_of(db):
    return getattr(db, "path", "?")
