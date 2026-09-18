# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— **存档层 battle_state 域**（B17，2026-09-14）。

真源：宿主 `game/store/battle_state.py`（逐字端口：正文一字未改，**只动「取件」**）。
宿主 `game/store/battle_state.py` 现在只剩一层**委托薄壳**（`from content.persistence.battle_state import *`）。

| 真源写法 | 包内替身 | 为什么 |
|---|---|---|
| `from .connection import _connect, _lock[, atomic]` | `from .handles import ...` | 连接/锁/事务三个句柄由**注入面**给（宿主工厂注入 db_path） |
| `from .. import content as C` | `from .handles import C`（`C` 句柄） | 包内禁 import 宿主（I2）；宿主内容面走既有句柄约定 |
| 函数内 `from ..<宿主模块> import <名>` | `宿主面取件("…", "…")` / `宿主面多符号取件(...)` | 同位置、调用时解析（与真源「函数内惰性 import」同刻） |
| `time.time()` | `clock()` | 时钟是四个注入点之一（默认 = stdlib `time.time`，行为零变化） |

**注入面**：`content/persistence/handles.py`（`bind(db_path=…, clock=…, flush_log=…, lock=…)`）；
宿主装配点 = `game/store/store_factory.py`。纯包环境（编辑器）需注入自己的句柄 —— 见 B19/B20 接点。

★ U1-D2 L5（形状迁移）：快照读写改走引擎 `store/snapshots`（`SnapshotSpec`/`SnapshotRepo`）。
表结构仍由 `persistence/tables.json` 建（**一字节不动**），这里只把 `battle_state` 表装配成
「owner 键 → 单行 JSON 快照 + `updated_at` 时间戳 + 24h 惰性过期门」的形状：
`stamp="updated_at"`（口径分歧 ①：最后活动）、`keep=_keep_instance`（副本行留痕）、
`on_expire=_on_battle_expire`（`inst:` 前缀兜底销毁）。对外签名与返回**逐键逐值不变**。
"""
import json
import time

from saintess_engine.store import Column, DeclaredRepository, TableSpec
from saintess_engine.store.snapshots import SnapshotSpec, declare_snapshot

from .handles import _connect, _lock, clock, get_db

"""奥兰迪亚·余烬纪年存储层 - battle_state"""
# v104 M02 P2：普通战斗 24h 无活动自动回收（battle_state 永久残留泄漏；PVP 另有 5 分钟超时在 combat.py）
BATTLE_STALE_SEC = 24 * 3600

#: 快照形状（**形状在引擎、取值在这里**）：owner=qq_id / blob=state / stamp=updated_at /
#: 附加展示名列 monster（I0-B8）/ 过期标记键 _expired（副本行留痕用）。
_SNAP_SPEC = SnapshotSpec("battle_state", owner="qq_id", blob="state",
                          stamp="updated_at",
                          extra=(Column("monster", "TEXT", notnull=True),),
                          pk=("qq_id",), expired_key="_expired")
_SNAP = None


class _KeepExtraRepo(DeclaredRepository):
    """快照 upsert 适配：`battle_state` 有 NOT NULL 的展示名列（`monster`），而快照写路径
    （引擎的过期打标 `_mark_expired`）只带 owner + blob。这里在写前把**既有行**的其余列
    合并回来 —— 打标保留路径因此不丢展示名、也不违反 NOT NULL。

    新建行仍必须由调用方给全列：`save_battle` 走全行 upsert；blob-only 的 `put` 建不出
    battle_state 新行（NOT NULL 约束），这是表结构（`tables.json`，本批一字节不动）决定的。
    """

    def upsert(self, conn, data):
        missing = [c for c in self.columns(conn) if c not in data]
        if missing:
            row = self.get(conn, *[data[c] for c in self.pk])
            if row is not None:
                data = dict(data)
                for c in missing:
                    if c in row:
                        data[c] = row[c]
        super().upsert(conn, data)


def _store_ready(obj):
    """写入引擎快照前的 set 清洗（`prepare` 注入口；规则逐字 = 原 `_json_ready`）：
    把 state 里可能残留的 Python set（如 phase BOSS 的 `_phase_warned`）递归深转成 list，
    保证引擎侧的 `json.dumps` 序列化不再抛 TypeError；其余类型原样返回。"""
    if isinstance(obj, set):
        return [_store_ready(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _store_ready(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_store_ready(x) for x in obj]
    return obj


def _snap():
    """battle_state 快照仓储（表由 `tables.json` 建；此处只把既有表装配成引擎快照口）。"""
    global _SNAP
    if _SNAP is None:
        db = get_db()
        repo = _KeepExtraRepo(
            db, TableSpec("battle_state", [Column("qq_id", "TEXT", pk=True)]),
            json_fields=("state",))
        _SNAP = declare_snapshot(db, _SNAP_SPEC, prepare=_store_ready, repo=repo)
    return _SNAP


def _keep_instance(owner, payload):
    """过期也不删的判据（口径分歧 ②）：副本战斗行**留痕**，命令层给「副本已过期」提示后清理。"""
    return payload.get("type") == "instance"


def _on_battle_expire(owner, payload):
    """过期副本行的兜底销毁（v141 P0-3）：`world_id` 为 `inst:` 前缀才碰，异常吞（幂等）。"""
    try:
        _wid = payload.get("world_id") or ""
        if isinstance(_wid, str) and _wid.startswith("inst:"):
            from ..worlds import destroy_instance_world as _diw
            _diw(_wid)
    except Exception:
        pass


def _monster_display_name(state):
    """I0-B8：monster 列展示宿主昵称——多对多阵列优先取 enemies[0]（阵列压缩换位后的实际首单位），
    无 enemies 时回落单怪 enemy 名。N5b4-3：saintess_engine 存档无顶层 enemies/enemy（存 sides）——
    取 enemy side 首个存活 actor 名（展示宿主昵称用，不影响战斗数据）。"""
    enemies = state.get("enemies")
    if isinstance(enemies, list) and enemies:
        return enemies[0].get("name", "") or ""
    enemy = state.get("enemy") or {}
    if enemy:
        return enemy.get("name", "") or ""
    sides = state.get("sides") or {}
    eacts = sides.get("enemy") or []
    if eacts:
        # 展示取首个存活 actor（战斗宿主 = 主目标；死亡不移除 → 过滤存活，兜底首 actor）
        alive = [u for u in eacts if (u.get("hp") or 0) > 0]
        pick = (alive[0] if alive else eacts[0]) or {}
        return pick.get("name", "") or ""
    return ""


def save_battle(group_id, qq_id, state: dict):
    """保存完整战斗上下文（v9：含 type/round/buffs/enemy 等）


    兼容旧调用：若传入的是裸怪物 dict，自动包装为 v9 状态。
    v94.1：续存时自动继承旧 state 的 stamina_charged 标记（b.to_state() 不含该字段，
    否则战斗内第二击会重复扣体力）。
    """
    if "type" not in state:
        state = {
            # v152 时刻制：round 删除，now = 战斗绝对时刻
            "type": "monster", "now": 0.0,
            # v181 P3：敌方一律走 enemies 阵列（每怪自带 buffs/defending）；无共享 e_buffs/e_defending 键
            "enemies": [state], "p_buffs": {},
            "p_defending": False,
        }
    with _lock:
        conn = _connect()
        try:
            old = conn.execute(
                "SELECT state FROM battle_state WHERE qq_id=?", (qq_id,)
            ).fetchone()
            if old and state.get("stamina_charged") is None:
                try:
                    old_state = json.loads(old["state"])
                    if old_state.get("stamina_charged"):
                        state["stamina_charged"] = True
                except (ValueError, TypeError):
                    pass
            # I0-B8：monster 列存展示主目标昵称——多对多阵列（state.enemies）压缩换位后首单位
            # 可能非原主目标，故优先取 enemies[0]，单怪回落 enemy 名；旧档遗留敌名仍可显示。
            # A0-A1：写入前经 `_store_ready` 清洗残留 set（phase BOSS 旧档 _phase_warned），
            # 避免 json 序列化抛 TypeError 致存档崩溃；清洗规则由引擎 `prepare` 注入口承载。
            snap = _snap()
            body = snap.prepare(state) if snap.prepare is not None else state
            snap.repo.upsert(conn, {
                "qq_id": qq_id,
                "monster": _monster_display_name(state),
                "state": body,
                "updated_at": int(clock()),
            })
            conn.commit()
        finally:
            conn.close()

def get_battle(group_id, qq_id):
    with _lock:
        conn = _connect()
        try:
            # v104 M02 P2：超 24h 无活动的战斗记录回收（普通战斗此前永久保留；
            # 表无 created_at 列，用 updated_at 判定更合理——战斗长时间无操作即视为废弃）
            # v104 M04 P2：副本战斗行不静默删除——保留行并打 _expired 标记，
            # 由命令层（instance.py _instance_expired_hint）给出"副本已过期"提示后清理；
            # 本函数仍返回 None，战斗路由（_in_battle 等）不会把过期副本当战斗中。
            # 普通战斗维持原行为：直接回收。
            snap = _snap()
            state = snap.get(conn, qq_id, now=clock(), ttl=BATTLE_STALE_SEC,
                             keep=_keep_instance, on_expire=_on_battle_expire)
            if state is None:
                # 过期出口的内务（删行 / 打标）由引擎写出，提交仍由本函数掌握
                conn.commit()
                return None
            row = snap.repo.get(conn, qq_id)
            if not row:
                return None
            return {"state": state, "monster": state.get("enemy", {}), "name": row["monster"], "updated_at": row["updated_at"]}
        finally:
            conn.close()

def get_battle_raw(group_id, qq_id):
    """读取 battle 行原始状态（不做 24h 过期回收/打标），供过期提示检测用。"""
    with _lock:
        conn = _connect()
        try:
            snap = _snap()
            state = snap.raw(conn, qq_id)
            if state is None:
                return None
            row = snap.repo.get(conn, qq_id)
            return {"state": state, "monster": state.get("enemy", {}), "name": row["monster"], "updated_at": row["updated_at"]}
        finally:
            conn.close()

def clear_battle(group_id, qq_id):
    with _lock:
        conn = _connect()
        try:
            _snap().drop(conn, qq_id)
            conn.commit()
        finally:
            conn.close()



__all__ = [
    "json",
    "time",
    "_connect",
    "_lock",
    "BATTLE_STALE_SEC",
    "_store_ready",
    "_monster_display_name",
    "save_battle",
    "get_battle",
    "get_battle_raw",
    "clear_battle",
]
