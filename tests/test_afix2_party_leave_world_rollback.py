# -*- coding: utf-8 -*-
"""审计 L4574-#7：`content/party.py::party_leave_execute` 大陆回滚段 fail-closed 判据。

原实现：
    try:
        _p2 = player_hook(group_id, qq_id)
        _wid2 = (_p2 or {}).get("world_id") or ""
        if _wid2.startswith("inst:"):
            db.update_player(group_id, qq_id, world_id="mainland")
    except Exception:
        pass

**真实代价**（不是「少做一步清理」）：这一段存在的唯一理由就是
「回滚 world_id（**防卡副本图出不去**）」。`db.party_leave` 在它**之前**就返回了 True
⇒ 玩家已被移出队伍且命令已回「退队成功」；读档一抛就被 `pass` 吃掉 ⇒ 回滚**一次都不执行**
⇒ 玩家**永久留在 `inst:` 大陆**，零报错、提示是成功的。也就是这段静默吞掉的
恰恰是它自己声称要防的那件事。

**判无此人不是这条路径**（防止把 fail-closed 做成误伤）：`db.get_player` 查无此人返
`None`（不抛），`(_p2 or {})` 已经把它归一成「非副本大陆」⇒ 不写库。故本判据只钉
「真读失败 ⇒ 抛」，不碰「查无此人」那条正常路。

本判据只钉 fail-closed 语义（**不改判据迁就实现**）：
  ① 正常路逐字不变：在 inst: ⇒ 回滚 mainland / 主大陆 ⇒ 不写 / None ⇒ 不写
  ② player_hook 抛 ⇒ 抛（不得静默跳过回滚），原因为 `__cause__` 保住
  ③ 回滚已执行之后仍抛 ⇒ 不得被这段吞掉（异常来自哪一步要分得清）
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 路径装配**走仓内单源** tests/_paths.py（不自己拼 sys.path —— 那会造第二份路径真源）
import _paths  # noqa: E402,F401  导入即完成 sys.path 装配（引擎根 + extends）

import content.party as _P  # noqa: E402

passed = failed = 0
from _check import bind_check  # noqa: E402  断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")


class _DB(object):
    """最小 db 替身：只记本函数真正用到的那几个调用。"""

    def __init__(self, members=(), battle=None):
        self._members = list(members)
        self._battle = battle
        self.updated = []
        self.cleared = []

    def party_leave(self, gid, qq):
        return True

    def update_player(self, gid, qq, **kw):
        self.updated.append((gid, qq, kw))

    def clear_battle(self, gid, qq):
        self.cleared.append((gid, qq))

    def party_members(self, gid, qq):
        return list(self._members)

    def get_battle(self, gid, qq):
        return self._battle


def _call(db, hook, **kw):
    _P.db = db
    return _P.party_leave_execute("g1", "u1", False, player_hook=hook, **kw)


def _boom(gid, qq):
    raise KeyError("存档行读不到")


def main():
    # ---- 正常路（逐字不变，回归保护）----
    db = _DB(members=["u2"])
    left, ok, err = _call(db, lambda g, q: {"world_id": "inst:abc"})
    check("正常·人在副本大陆 ⇒ 回滚到 mainland", left is True
          and db.updated == [("g1", "u1", {"world_id": "mainland"})], repr(db.updated))

    db = _DB(members=["u2"])
    _call(db, lambda g, q: {"world_id": "mainland"})
    check("正常·主大陆 ⇒ 不写库", db.updated == [], repr(db.updated))

    db = _DB(members=["u2"])
    _call(db, lambda g, q: None)
    check("正常·查无此人（get_player 返 None）⇒ 不写库也不抛", db.updated == [], repr(db.updated))

    db = _DB(members=["u2"])
    _call(db, lambda g, q: {})
    check("正常·档里无 world_id ⇒ 不写库", db.updated == [], repr(db.updated))

    # ---- fail-closed 本体 ----
    db = _DB(members=["u2"])
    raised = None
    try:
        _call(db, _boom)
    except Exception as e:                                   # noqa: BLE001 —— 本就在验它抛
        raised = e
    check("读档失败 ⇒ 抛（不得静默跳过回滚）", raised is not None,
          "异常被 pass 吞掉 = 回滚一次都不执行、玩家永久留在 inst: 大陆")
    check("抛出的原因保留在 __cause__", raised is not None and isinstance(raised.__cause__, KeyError),
          repr(getattr(raised, "__cause__", None)))
    check("错误消息点名了后果（inst: 大陆）", raised is not None
          and "inst:" in str(raised), repr(raised))
    check("读档失败时未写库（没有半截状态）", db.updated == [], repr(db.updated))

    # ---- ③ 回滚已执行之后仍抛 ⇒ 不得被这段吞掉 ----
    class _DB2(_DB):
        def update_player(self, gid, qq, **kw):
            _DB.update_player(self, gid, qq, **kw)
            raise ValueError("回滚写入后崩")

    db = _DB2(members=["u2"])
    raised = None
    try:
        _call(db, lambda g, q: {"world_id": "inst:abc"})
    except Exception as e:                                   # noqa: BLE001
        raised = e
    check("回滚本身抛 ⇒ 同样上抛（分得清是哪一步炸的）", raised is not None, repr(raised))
    check("回滚写入已发生（异常发生在写之后，不是没跑）", db.updated == [("g1", "u1", {"world_id": "mainland"})],
          repr(db.updated))

    print("passed=%d failed=%d" % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
