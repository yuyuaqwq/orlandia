# -*- coding: utf-8 -*-
"""免锁直连读口 —— 「不占 store 锁」的小读点单源（`content/_dbread.py`）。

为什么有它
----------
`content/economy_cmds.py`（命令层）与 `content/stat_bonus.py`（属性层）原先各持一份
**逐字同体**的 `_visited_maps`：都是 `sqlite3.connect(HANDLES.db_path())` 直连读
`visited` 表，失败一律静默返回 `[]`。两份抄写会让「免锁直连的容错口径」分叉 ——
一边换成走锁 / 换查询，另一边不知道，称号判定就会在同一份数据上给出两种结果。

为什么直连、而不是走 store
--------------------------
这两处是**称号条件判定**的钩子（`content/title_conds.py` 的 `TitleCtx.hooks`），
每次算称号都调；走 store 的锁会在战斗结算热路径上造成无谓争用。容错是**刻意的**：
读不到就当「没探索过」，绝不因为一个只读小点让整轮称号判定失败（与 `props_use`
等免锁直连点同口径）。

取值口径**留在本模块**（单源）；调用方只拿结果、不做二次判断。
"""
from __future__ import annotations

from ._pkgref import HANDLES     # 包内库路径真源（惰性句柄；调用时才解析）


def visited_map_ids(group_id, qq_id):
    """已探索地图 id 列表（独立直连，**不占 store 锁**；读不到 → `[]`）。

    `group_id` 只为满足钩子签名（`TitleCtx.hook("visited_maps", group_id, qq_id)`）——
    玩家数据全局化后这张表只按 `qq_id` 查（与 `props_use` 同口径，参数保留不改行为）。
    """
    import sqlite3
    try:
        conn = sqlite3.connect(HANDLES.db_path())
        rows = conn.execute("SELECT map_id FROM visited WHERE qq_id=?", (qq_id,)).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []
