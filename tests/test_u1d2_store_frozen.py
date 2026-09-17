# -*- coding: utf-8 -*-
"""U1-D2 冻结比对**门禁②**（存档块）：`persistence/{battle_state,stats,props_use}` + `worlds.py`
换引擎 `store/snapshots` + `store/counters` 形状。

跑法（工作区根；环境变量见 `BRIEF.md` §4）::

    PY="C:/Users/yuyu/AppData/Roaming/uv/tools/astrbot/Scripts/python.exe"
    "$PY" work/pkg/tests/_u1d2_store_gen.py --check
    "$PY" work/pkg/tests/test_u1d2_store_frozen.py

判据（`BRIEF.md` §3 = `U1-D2_BATCHES.md` §5）
-----------------------------------------
 [1] 23 段冻结文本 sha256 全等 `_PIN["frozen"]` + 活实现 `inspect.getsource` 全等 `_PIN["live"]`
     （`_PIN["live"] == "<deleted>"` = 该符号本批已删，另断言活模块里确实没有）；
     `phase == "landed"` 时再断言 C 栏「预期会变」段 `frozen != live`。
 [2] 网格 A（快照）：3 repo × 5 操作 × 5 owner 态 × 6 载荷形态 = **450 格**。
 [3] 网格 B（计数器）：19 列 × 3 增量 × 4 初值 = **228 格** + 19 非法名各 1 条 `ValueError`
     + 读 **57 格** + 归零 **38 格**。
 [4] 网格 C（TTL 边界）：`ttl ∈ {0,1,86399,86400,86401}` × 2 类型 × 3 出口 = **30 格**；
     `created_at` 4 边界 × 内存/DB 两层 = **8 格**（`cleanup_stale_instances` 旧↔新）。
 [5] 网格 D（复合键）：3 怪 × 3 owner × 4 初值 = **36 格**。
 [6] aux 指纹逐字节：`battle_state.state` · `stats` 行值 · `props_use.used` · `instance_world_*` ·
     `talk_*` / `wildmeta_*` / `timed_events_*` 原文 + 键格式 + schema 指纹。
 [7] 口径分歧 10 条各 ≥1 条断言。
 [8] 有牙反证 3 处（TTL 判定「永远不过期」/ `bump` 白名单放行任意列名 / `prepare` 不清 set）
     → 对应探针**必须变红**；另跑多故障 M3（两处同坏，各自变红）。
 [9] 只读断言：跑完全程 4 个源文件 sha256 不变。
[10] `persistence/world.py` / `persistence/quests.py` / `persistence/tables.json` sha256 前后一致。
[11] 计数校验：逐网格 `sum(比对次数) == 911`（防「循环没跑」的假绿）。

⚠ 「旧实现」= `_FROZEN_TEXT` 里的**成品字面量**（由 `tests/_u1d2_store_gen.py` 从 `base/pkg/**`
   逐行 `ast` 切片），`exec` 到独立命名空间跑 —— 不是「读代码觉得等价」。
⚠ 刻意**不依赖 pytest**：直接 `python <本文件>`，`sys.exit(1 if FAIL else 0)`。
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib
import inspect
import json
import os
import sqlite3
import sys
import tempfile

# ══════════════════════════════════════════════════════════════════════════════
# 0. 装配：包根 / 引擎根 / 宿主壳根（`_paths` 单点）+ 独立私有库
# ══════════════════════════════════════════════════════════════════════════════
_HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(_HERE)
WORK_ROOT = os.path.dirname(PKG_ROOT)
LANE_ROOT = os.path.dirname(WORK_ROOT)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# 2026-09-18 收尾修：原落点 `LANE_ROOT/out` 是旧「工作区布局」（`<lane>/work/pkg` 三层），
#   真仓布局下 LANE_ROOT = `C:\Users` ⇒ `C:\Users\out` 不存在 → sqlite connect 直接
#   `unable to open database file`（单跑必崩；改前基线同样红，非本次修复引入）。
#   私有库改落系统临时目录下自建子目录（不写包目录、不进 git）。
_DB_DIR = os.path.join(tempfile.gettempdir(), "gwen_test_u1d2_L5")
os.makedirs(_DB_DIR, exist_ok=True)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_DB_DIR, "test_u1d2_L5.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
os.environ.setdefault("GWEN_FRAMEWORK_DIR", os.path.join(LANE_ROOT, "work", "eng"))
os.environ.setdefault("GWEN_HOST_DIR", os.path.join(LANE_ROOT, "work", "host"))
os.environ.setdefault("PYTHONUTF8", "1")
_shim = os.path.join(_HERE, "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

import _paths                                                             # noqa: E402,F401
import _engine_harness as H                                              # noqa: E402,F401

from saintess_engine.store import Column, DeclaredRepository, TableSpec   # noqa: E402
from saintess_engine.store.snapshots import (                             # noqa: E402
    SnapshotSpec, SnapshotRepo, declare_snapshot)
from saintess_engine.store.counters import (                              # noqa: E402
    CounterSpec, Counters, declare_counters)

from content.persistence import handles as _HND                          # noqa: E402
from content.persistence import world as PW                              # noqa: E402
from content.persistence import battle_state as BS                       # noqa: E402
from content.persistence import stats as ST                              # noqa: E402
from content.persistence import props_use as PU                          # noqa: E402
from content import worlds as W                                          # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} {detail}")
        print(f"  ❌ {name} {detail}")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


# >>> _u1d2_store_gen (auto) >>>

# ⚠ 本块由 `tests/_u1d2_store_gen.py` 生成 —— 手工改动 = 门禁失去安全网。
# 冻结侧读 `base/pkg/**`（改动前基线）；`_PIN["live"]` 由 --emit-live 重生成。

_FROZEN_TEXT = {
    'content/persistence/battle_state.py::_json_ready': 'def _json_ready(obj):\n    """v116 兜底：把 state 里可能残留的 Python set（如 phase BOSS 的 _phase_warned）\n    递归深转成 list，保证 json.dumps 序列化不再抛 TypeError；其余类型原样返回。"""\n    if isinstance(obj, set):\n        return [_json_ready(x) for x in obj]\n    if isinstance(obj, dict):\n        return {k: _json_ready(v) for k, v in obj.items()}\n    if isinstance(obj, (list, tuple)):\n        return [_json_ready(x) for x in obj]\n    return obj\n',
    'content/persistence/battle_state.py::_monster_display_name': 'def _monster_display_name(state):\n    """I0-B8：monster 列展示宿主昵称——多对多阵列优先取 enemies[0]（阵列压缩换位后的实际首单位），\n    无 enemies 时回落单怪 enemy 名。N5b4-3：saintess_engine 存档无顶层 enemies/enemy（存 sides）——\n    取 enemy side 首个存活 actor 名（展示宿主昵称用，不影响战斗数据）。"""\n    enemies = state.get("enemies")\n    if isinstance(enemies, list) and enemies:\n        return enemies[0].get("name", "") or ""\n    enemy = state.get("enemy") or {}\n    if enemy:\n        return enemy.get("name", "") or ""\n    sides = state.get("sides") or {}\n    eacts = sides.get("enemy") or []\n    if eacts:\n        # 展示取首个存活 actor（战斗宿主 = 主目标；死亡不移除 → 过滤存活，兜底首 actor）\n        alive = [u for u in eacts if (u.get("hp") or 0) > 0]\n        pick = (alive[0] if alive else eacts[0]) or {}\n        return pick.get("name", "") or ""\n    return ""\n',
    'content/persistence/battle_state.py::save_battle': 'def save_battle(group_id, qq_id, state: dict):\n    """保存完整战斗上下文（v9：含 type/round/buffs/enemy 等）\n\n\n    兼容旧调用：若传入的是裸怪物 dict，自动包装为 v9 状态。\n    v94.1：续存时自动继承旧 state 的 stamina_charged 标记（b.to_state() 不含该字段，\n    否则战斗内第二击会重复扣体力）。\n    """\n    if "type" not in state:\n        state = {\n            # v152 时刻制：round 删除，now = 战斗绝对时刻\n            "type": "monster", "now": 0.0,\n            # v181 P3：敌方一律走 enemies 阵列（每怪自带 buffs/defending）；无共享 e_buffs/e_defending 键\n            "enemies": [state], "p_buffs": {},\n            "p_defending": False,\n        }\n    with _lock:\n        conn = _connect()\n        try:\n            old = conn.execute(\n                "SELECT state FROM battle_state WHERE qq_id=?", (qq_id,)\n            ).fetchone()\n            if old and state.get("stamina_charged") is None:\n                try:\n                    old_state = json.loads(old["state"])\n                    if old_state.get("stamina_charged"):\n                        state["stamina_charged"] = True\n                except (ValueError, TypeError):\n                    pass\n            conn.execute(\n                # I0-B8：monster 列存展示主目标昵称——多对多阵列（state.enemies）压缩换位后首单位\n                # 可能非原主目标，故优先取 enemies[0]，单怪回落 enemy 名；旧档遗留敌名仍可显示。\n                # A0-A1：写入前经 _json_ready 清洗残留 set（phase BOSS 旧档 _phase_warned），\n                # 避免 json.dumps 抛 TypeError 致存档崩溃。\n                "INSERT INTO battle_state (qq_id, monster, state, updated_at) VALUES (?,?,?,?) "\n                "ON CONFLICT(qq_id) DO UPDATE SET monster=excluded.monster, state=excluded.state, updated_at=excluded.updated_at",\n                (qq_id, _monster_display_name(state), json.dumps(_json_ready(state), ensure_ascii=False), int(clock())),\n            )\n            conn.commit()\n        finally:\n            conn.close()\n',
    'content/persistence/battle_state.py::get_battle': 'def get_battle(group_id, qq_id):\n    with _lock:\n        conn = _connect()\n        try:\n            row = conn.execute(\n                "SELECT monster, state, updated_at FROM battle_state WHERE qq_id=?",\n                (qq_id,),\n            ).fetchone()\n            if not row:\n                return None\n            # v104 M02 P2：超 24h 无活动的战斗记录回收（普通战斗此前永久保留；\n            # 表无 created_at 列，用 updated_at 判定更合理——战斗长时间无操作即视为废弃）\n            updated = row["updated_at"] or 0\n            if updated and clock() - updated > BATTLE_STALE_SEC:\n                state = json.loads(row["state"])\n                # v104 M04 P2：副本战斗行不静默删除——保留行并打 _expired 标记，\n                # 由命令层（instance.py _instance_expired_hint）给出"副本已过期"提示后清理；\n                # 本函数仍返回 None，战斗路由（_in_battle 等）不会把过期副本当战斗中。\n                # 普通战斗维持原行为：直接回收。\n                if state.get("type") == "instance":\n                    state["_expired"] = True\n                    conn.execute(\n                        "UPDATE battle_state SET state=? WHERE qq_id=?",\n                        (json.dumps(state, ensure_ascii=False), qq_id),\n                    )\n                    conn.commit()\n                    # v141 兜底（P0-3，2026-08-30 审计）：instance 行超 BATTLE_STALE_SEC\n                    # 只打 _expired 标记不销毁大陆 → 大陆实例泄漏（内存 + event_state 键）。\n                    # 命令层（instance.py）会补 30min 超时销毁；这里做 24h 过期兜底：\n                    # state 里带 world_id 且为 inst: 前缀 → 直接销毁大陆实例（幂等）。\n                    # 正常 instance 战斗（未过期）不碰；非 inst: 前缀（异常数据）不碰。\n                    try:\n                        _wid = state.get("world_id") or ""\n                        if isinstance(_wid, str) and _wid.startswith("inst:"):\n                            from ..worlds import destroy_instance_world as _diw\n                            _diw(_wid)\n                    except Exception:\n                        pass\n                    return None\n                conn.execute("DELETE FROM battle_state WHERE qq_id=?", (qq_id,))\n                conn.commit()\n                return None\n            state = json.loads(row["state"])\n            return {"state": state, "monster": state.get("enemy", {}), "name": row["monster"], "updated_at": row["updated_at"]}\n        finally:\n            conn.close()\n',
    'content/persistence/battle_state.py::get_battle_raw': 'def get_battle_raw(group_id, qq_id):\n    """读取 battle 行原始状态（不做 24h 过期回收/打标），供过期提示检测用。"""\n    with _lock:\n        conn = _connect()\n        try:\n            row = conn.execute(\n                "SELECT monster, state, updated_at FROM battle_state WHERE qq_id=?",\n                (qq_id,),\n            ).fetchone()\n            if not row:\n                return None\n            state = json.loads(row["state"])\n            return {"state": state, "monster": state.get("enemy", {}), "name": row["monster"], "updated_at": row["updated_at"]}\n        finally:\n            conn.close()\n',
    'content/persistence/battle_state.py::clear_battle': 'def clear_battle(group_id, qq_id):\n    with _lock:\n        conn = _connect()\n        try:\n            conn.execute(\n                "DELETE FROM battle_state WHERE qq_id=?", (qq_id,)\n            )\n            conn.commit()\n        finally:\n            conn.close()\n',
    'content/persistence/stats.py::init_stats': 'def init_stats(group_id, qq_id):\n    with _lock:\n        conn = _connect()\n        try:\n            conn.execute(\n                "INSERT OR IGNORE INTO stats (qq_id) VALUES (?)", (qq_id,)\n            )\n            conn.commit()\n        finally:\n            conn.close()\n',
    'content/persistence/stats.py::bump_stats': 'def bump_stats(group_id, qq_id, **fields):\n    bad = [k for k in fields if k not in STAT_FIELDS]\n    if bad:  # B2 加固（2026-08-10）：动态列名前白名单校验\n        raise ValueError(f"bump_stats 非法字段: {bad}（不在 stats 表白名单）")\n    with _lock:\n        conn = _connect()\n        try:\n            sets = ", ".join(f"{k}={k}+?" for k in fields)\n            conn.execute(\n                f"UPDATE stats SET {sets} WHERE qq_id=?",\n                (*fields.values(), qq_id),\n            )\n            conn.commit()\n        finally:\n            conn.close()\n',
    'content/persistence/stats.py::get_stats': 'def get_stats(group_id, qq_id):\n    with _lock:\n        conn = _connect()\n        try:\n            row = conn.execute(\n                "SELECT * FROM stats WHERE qq_id=?", (qq_id,)\n            ).fetchone()\n            return dict(row) if row else {}\n        finally:\n            conn.close()\n',
    'content/persistence/stats.py::set_achievement': 'def set_achievement(group_id, qq_id, ach_key, progress, claimed=0):\n    with _lock:\n        conn = _connect()\n        try:\n            conn.execute(\n                "INSERT INTO achievements (qq_id, ach_key, progress, claimed) VALUES (?,?,?,?) "\n                "ON CONFLICT(qq_id, ach_key) DO UPDATE SET progress=excluded.progress, claimed=excluded.claimed",\n                (qq_id, ach_key, progress, claimed),\n            )\n            conn.commit()\n        finally:\n            conn.close()\n',
    'content/persistence/stats.py::get_achievements': 'def get_achievements(group_id, qq_id):\n    with _lock:\n        conn = _connect()\n        try:\n            rows = conn.execute(\n                "SELECT * FROM achievements WHERE qq_id=?", (qq_id,)\n            ).fetchall()\n            return [dict(r) for r in rows]\n        finally:\n            conn.close()\n',
    'content/persistence/props_use.py::get_props_use': 'def get_props_use(qq_id):\n    """返回该玩家的 {元素key: 日期} 使用记录(无则 {})。\n    v105 M23 P3-8：记录按 qq_id 全局（玩家数据全局化），原 group_id 参数完全未用，已移除。"""\n    with _lock:\n        conn = _connect()\n        try:\n            row = conn.execute(\n                "SELECT used FROM props_use WHERE qq_id=?", (qq_id,)\n            ).fetchone()\n            if not row:\n                return {}\n            return json.loads(row["used"] or "{}")\n        finally:\n            conn.close()\n',
    'content/persistence/props_use.py::mark_props_use': 'def mark_props_use(qq_id, key, date):\n    """记录该元素今天已使用。"""\n    used = get_props_use(qq_id)\n    used[key] = date\n    with _lock:\n        conn = _connect()\n        try:\n            conn.execute(\n                "INSERT INTO props_use (qq_id, used) VALUES (?,?) "\n                "ON CONFLICT(qq_id) DO UPDATE SET used=excluded.used",\n                (qq_id, json.dumps(used, ensure_ascii=False)),\n            )\n            conn.commit()\n        finally:\n            conn.close()\n',
    'content/persistence/props_use.py::props_use_claim_atomic': 'def props_use_claim_atomic(qq_id, key, date):\n    """F1 P1-4：原子认领每日元素使用（防并发双请求重复生效）。\n\n    单事务内 读 used→判是否已用→写回；返回 True 表示本次是本玩家第一个把该元素\n    记为今天已用（调用方据此发放奖励），False 表示今天已被拿走（并发后手/重复调用）。\n    """\n    with atomic() as conn:\n        row = conn.execute(\n            "SELECT used FROM props_use WHERE qq_id=?", (qq_id,)\n        ).fetchone()\n        used = {}\n        if row and row["used"]:\n            try:\n                used = json.loads(row["used"] or "{}")\n                if not isinstance(used, dict):\n                    used = {}\n            except (ValueError, TypeError):\n                used = {}\n        if used.get(key) == date:\n            return False\n        used[key] = date\n        conn.execute(\n            "INSERT INTO props_use (qq_id, used) VALUES (?,?) "\n            "ON CONFLICT(qq_id) DO UPDATE SET used=excluded.used",\n            (qq_id, json.dumps(used, ensure_ascii=False)),\n        )\n        return True\n',
    'content/worlds.py::get_instance_world': 'def get_instance_world(world_id: str) -> Optional[dict]:\n    """获取大陆实例。内存没有则尝试从 DB 惰性恢复。"""\n    if world_id not in instance_worlds:\n        _restore_from_db(world_id)\n    return instance_worlds.get(world_id)\n',
    'content/worlds.py::_restore_from_db': 'def _restore_from_db(world_id: str) -> None:\n    """重启后从 event_state 恢复大陆实例（惰性：首次访问才加载）。"""\n    try:\n        from .persistence.world import get_event_state\n        raw = get_event_state(f"{EVENT_STATE_PREFIX}{world_id}")\n        if raw:\n            data = json.loads(raw) if isinstance(raw, str) else raw\n            if isinstance(data, dict):\n                # P0-2（2026-08-30 审计）：老档/异常路径落库的 set 被 default=str 串化成\n                # 字符串 → 重启恢复成字符集合 → 调查点重复刷奖。恢复后对 st.investigated\n                # 做校验：str 尝试 ast.literal_eval 解析回 list，失败/非 list 重置为空 list。\n                _st = data.get("st")\n                if isinstance(_st, dict) and isinstance(_st.get("investigated"), str):\n                    try:\n                        import ast\n                        _parsed = ast.literal_eval(_st["investigated"])\n                        if not isinstance(_parsed, list):\n                            _parsed = []\n                    except Exception:\n                        _parsed = []\n                    _st["investigated"] = _parsed\n                instance_worlds[world_id] = data\n    except Exception:\n        # DB 不可用/损坏 → 当作不存在，调用方自行兜底\n        instance_worlds.pop(world_id, None)\n',
    'content/worlds.py::create_instance_world': 'def create_instance_world(\n    inst_id: str,\n    members: List[int],\n    boss: dict,\n    now: Optional[int] = None,\n    leader: Optional[int] = None,\n    st: Optional[dict] = None,\n    rooms: Optional[dict] = None,\n    resources_pool: Optional[dict] = None,\n) -> str:\n    """开本：克隆副本地图为独立大陆。返回 world_id \'inst:<uuid>\'。\n\n    参数：\n    - inst_id: 副本配置 id（inst_goblin_camp）\n    - members: 进本成员 qq_id 列表\n    - boss: 构建好的 Boss dict（血量已按人数缩放）\n    - now: 当前时间戳（缺省取 time.time()）\n    - leader: 队长 qq_id（缺省取 members[0]；仅展示，不承载状态）\n    - st: 副本战斗状态快照（_instance_build_state 产物）\n    - rooms / resources_pool: v137 副本地图化怪池/资源池\n    """\n    MAP_BY_ID = _cs.MAP_BY_ID            # B14-2 L8：包内空间门面（真源 `data.MAP_BY_ID`，逐值+键序 OK）\n    SUBAREAS = _cs.SUBAREAS              # B14-2 L8：包内空间门面（真源 `data.SUBAREAS`）\n    INSTANCES = _cs.INSTANCES            # B14-2 L8：包内空间门面（真源 `data.INSTANCES`）\n    world_id = f"inst:{uuid.uuid4().hex[:12]}"\n    map_id = inst_id[5:] if str(inst_id).startswith("inst_") else inst_id\n    inst = INSTANCES.get(inst_id, {})\n    _now = int(now if now is not None else time.time())\n    _leader = str(leader if leader is not None else members[0])\n\n    instance_worlds[world_id] = {\n        "name": inst.get("name", map_id),\n        "inst_id": inst_id,\n        "maps": {map_id: deepcopy(MAP_BY_ID.get(map_id, {}))},\n        "subareas": {map_id: deepcopy(SUBAREAS.get(map_id, []))},\n        "created_at": _now,\n        "leader": _leader,\n        "members": [str(m) for m in members],\n        "rooms": rooms or {},\n        "resources_pool": resources_pool or {},\n        "st": st,\n        "retreated": False,\n    }\n    _persist(world_id)\n    return world_id\n',
    'content/worlds.py::destroy_instance_world': 'def destroy_instance_world(world_id: str) -> None:\n    """退本/通关/失败/过期：销毁大陆实例。"""\n    instance_worlds.pop(world_id, None)\n    try:\n        from .persistence.world import delete_event_state\n        delete_event_state(f"{EVENT_STATE_PREFIX}{world_id}")\n    except Exception:\n        pass\n',
    'content/worlds.py::_json_ready': 'def _json_ready(obj):\n    """v116 兜底（store/battle_state 同构函数）：把 state 里可能残留的 Python set（如\n    phase BOSS 的 _phase_warned / instance st 的 investigated）递归深转成 list，保证\n    json.dumps 序列化不再抛 TypeError / 不再被 default=str 掩盖成字符串；其余类型原样返回。\n\n    P0-2（2026-08-30 审计）：worlds._persist 原先用 json.dumps(default=str) 兜底，\n    set 落库变成字符串，重启恢复成字符集合 → 调查点重复刷奖。本函数在写入前\n    显式清洗，与 store/battle_state.py:11-20 的 _json_ready 逻辑保持一致。\n    """\n    if isinstance(obj, set):\n        return [_json_ready(x) for x in obj]\n    if isinstance(obj, dict):\n        return {k: _json_ready(v) for k, v in obj.items()}\n    if isinstance(obj, (list, tuple)):\n        return [_json_ready(x) for x in obj]\n    return obj\n',
    'content/worlds.py::_persist': 'def _persist(world_id: str) -> None:\n    """落库 event_state（重启防丢）。只落非战斗核心字段（st 也落，可恢复）。"""\n    data = instance_worlds.get(world_id)\n    if data is None:\n        return\n    try:\n        from .persistence.world import set_event_state\n        set_event_state(f"{EVENT_STATE_PREFIX}{world_id}",\n                        json.dumps(_json_ready(data), ensure_ascii=False))\n    except Exception:\n        pass\n',
    'content/worlds.py::update_instance_world': 'def update_instance_world(world_id: str, **fields) -> None:\n    """更新大陆实例字段（房间/资源池/队伍快照等）并落库。\n\n    v141 审计（2026-08-30）：当前生产 0 消费（instance.py 直接改大陆 dict\n    字段后经 _instance_save → set_instance_st 落库）；保留作公共 API\n    （未来动态化/监控/运维可能按字段增量更新）。\n    """\n    data = instance_worlds.get(world_id)\n    if data is None:\n        return\n    for k, v in fields.items():\n        data[k] = v\n    _persist(world_id)\n',
    'content/worlds.py::cleanup_stale_instances': 'def cleanup_stale_instances(max_age_sec: int = 24 * 3600) -> int:\n    """惰性回收过期大陆实例（24h 无活动）。返回清理数量。\n\n    过期判定：created_at 距今超过 max_age_sec。两层清理：\n    1. 内存 instance_worlds dict 轻扫（超龄 → destroy_instance_world，同时删 DB 键）；\n    2. DB event_state 键扫描（key LIKE \'instance_world_%\'，读 JSON 取 created_at，\n       超龄则 delete_event_state）——覆盖进程重启后未惰性恢复的孤儿键\n       （内存已无、DB 残留），防 event_state 表只增不删。\n\n    注：store/world.py 的 _EVENT_STATE_PLAYER_PREFIXES 不扩——instance_world_ 键\n    无内嵌 qq_id 可提取，玩家活跃度清理机制不匹配，扫描逻辑内聚在本函数。\n\n    幂等（多实例/热重载安全）；轻量（仅一次 LIKE 查询 + 少量 JSON 解析），\n    挂任意指令入口（base.py _maint_gate）与启动兜底（main.py）均不阻塞主流程。\n    """\n    now = int(time.time())\n    cleaned = 0\n    # 1. 内存 dict 轻扫（destroy 同时删内存 + DB 键）\n    stale = []\n    for wid, data in instance_worlds.items():\n        created = int(data.get("created_at", 0) or 0)\n        if created and now - created > max_age_sec:\n            stale.append(wid)\n    for wid in stale:\n        destroy_instance_world(wid)\n    cleaned += len(stale)\n    # 2. DB event_state 孤儿键扫描（内存已无该 world_id 的 instance_world_* 键）\n    try:\n        from .persistence.handles import _connect\n        from .persistence.handles import _lock as _db_lock\n        from .persistence.world import delete_event_state\n        with _db_lock:\n            conn = _connect()\n            try:\n                rows = conn.execute(\n                    "SELECT key, value FROM event_state WHERE key LIKE ?",\n                    (EVENT_STATE_PREFIX + "%",),\n                ).fetchall()\n            finally:\n                conn.close()\n        for r in rows:\n            _k = r["key"]\n            _wid = _k[len(EVENT_STATE_PREFIX):]\n            if _wid in instance_worlds:\n                continue  # 内存仍存活（未超龄）——不碰，避免误删活跃大陆\n            _created = 0\n            try:\n                _data = json.loads(r["value"]) if isinstance(r["value"], str) else r["value"]\n                _created = int((_data or {}).get("created_at", 0) or 0)\n            except Exception:\n                _created = 0  # JSON 损坏无法判定年龄 → 保守不删\n            if _created and now - _created > max_age_sec:\n                try:\n                    delete_event_state(_k)\n                    cleaned += 1\n                except Exception:\n                    pass\n    except Exception:\n        pass\n    return cleaned\n',
    'content/worlds.py::resolve_map_for': 'def resolve_map_for(world_id: str, map_id: str) -> Optional[dict]:\n    """按世界解析地图（纯函数，供不持有 Position 的场景）。\n\n    副本大陆实例优先（克隆图）；实例已销毁/不存在 → 返回 None\n    （与原 C.MAP_BY_ID.get 语义区分：调用方需自行回退全局静态图）。\n    """\n    if world_id and world_id.startswith("inst:"):\n        data = get_instance_world(world_id)\n        if data is None:\n            return None\n        return data.get("maps", {}).get(map_id)\n    from . import catalog_space as _cs          # ★ B16-W11d：包内门面（原 `宿主面取件("data", …)`；\n    MAP_BY_ID = _cs.MAP_BY_ID                   #   删表后 `C.MAP_BY_ID` 同一对象 = 本门面，身份断言仍成立）\n    return MAP_BY_ID.get(map_id)\n',
}

_PIN = {
    'phase': 'landed',
    'frozen': {
        'content/persistence/battle_state.py::_json_ready': '31a957bcb740bb09128fd572c33250f4db96254e46664d233f5821f929c47635',
        'content/persistence/battle_state.py::_monster_display_name': '6dba7c5d03011e63b858b278069cd48d05b9de282819bbc5d7ae2119be7ebe58',
        'content/persistence/battle_state.py::save_battle': 'c8c94d2ffb5f7301c00f79d21bcbea17fc2f62a86dd8ecd5098fc25e4f5a6321',
        'content/persistence/battle_state.py::get_battle': 'f52c1f4e30a472f0788a2c88b1c9232f8a25c2f61cdefe594baf04a0a59075ea',
        'content/persistence/battle_state.py::get_battle_raw': '84e583dc300f423b7f01fd39b8019e8ac416acb4b11a4f9bb01b7422e5106507',
        'content/persistence/battle_state.py::clear_battle': '3fdf1ec108796178ff8638b0e42464e58e870c92ec8becb96005217ef1e35d36',
        'content/persistence/stats.py::init_stats': 'b07d28ba220580b604c6d0ddf85433e1dec319b2e2cebd7cefd374ec47e4097a',
        'content/persistence/stats.py::bump_stats': 'd754b42ddf3f3bcaeb4a7b8e46e3f994cd6c7c3304252725bcc6b5d1943e68da',
        'content/persistence/stats.py::get_stats': '6ac5a074b670aac29414079351aa39efba13f5c2c34b245389b4a106d57d71b2',
        'content/persistence/stats.py::set_achievement': 'cef8f7e2d063c8974153faf2caf49adc39ab45cd39228cf0c66ca268ee0ca305',
        'content/persistence/stats.py::get_achievements': '164a4d3d634e7665292c6d3abc8d125250f6a34be861e5cfe1b10dde819df37e',
        'content/persistence/props_use.py::get_props_use': '0b4f8d26e417d7183d61bc9eeca43935efb1feb354a1307ff1cb82979769d094',
        'content/persistence/props_use.py::mark_props_use': '8e22a4396794d4bd31175aa3ccccef7e951c5dde74ba0d013bd54db804c37b96',
        'content/persistence/props_use.py::props_use_claim_atomic': 'f11659f1b54848c26bdcb5c3bc903f41c3eea6348695989e3b88124d80900291',
        'content/worlds.py::get_instance_world': 'abfa3639859424ba87149776254ba7c6a24de34292aedd38c326c559bf0ec2cb',
        'content/worlds.py::_restore_from_db': '15e1133494870aa0d7e9bad89afd3090f1d0434116690e8012378aa343ed2cdc',
        'content/worlds.py::create_instance_world': '1085ebc18004e207fc9f9114bea6b1c82b67e08a23409d57b7c2084d7600195f',
        'content/worlds.py::destroy_instance_world': 'b44b3d4db6cdde2427dd462b115d8fd7e64e0a2aa97353ee18d96633f84d133b',
        'content/worlds.py::_json_ready': '99b170e37596ba818cc21ef15a73759b5a1d803a6ac97c0a27182c2d77352fa7',
        'content/worlds.py::_persist': 'f1b7da8e56bf5831b682f907a4126412bccdc33eeea6f8958d58b31c5623130c',
        'content/worlds.py::update_instance_world': '586e5b8580ea887a910e7c0a1be3448d0b07402b078cb9931cf2b809ec528cb4',
        'content/worlds.py::cleanup_stale_instances': '3f35723fbf693f4de9e52c6912f1876d8638b2ec3bf65192ed7211c74f0aba7f',
        'content/worlds.py::resolve_map_for': 'ce72a0fa44a6f19877aedf95bee5131e8b66988571c7c5c9bb65ea0dea7dcad9',
    },
    'live': {
        'content/persistence/battle_state.py::_json_ready': '<deleted>',
        'content/persistence/battle_state.py::_monster_display_name': '6dba7c5d03011e63b858b278069cd48d05b9de282819bbc5d7ae2119be7ebe58',
        'content/persistence/battle_state.py::save_battle': 'a856b0d9c423f7dc8ffa2a6e809bc84a8f76a7dbc7634555de5000820978fcb2',
        'content/persistence/battle_state.py::get_battle': 'b1379e6aaadfdc6b9759e36f23b843153103cdf38b40c7f6f0bb8219a0e52d3f',
        'content/persistence/battle_state.py::get_battle_raw': 'b895521b5e7241749d57cbac1ab3a60140a1644a33bcb4600d45017b912eab51',
        'content/persistence/battle_state.py::clear_battle': '6d99612e6ddf803104f2422ad16839f2221c5fa3c5f9d99487e55c8233e951c3',
        'content/persistence/stats.py::init_stats': '364f30e248506a174f5f10a2c65423ac2de30cfb505695072ee6a3d1c42b9468',
        'content/persistence/stats.py::bump_stats': 'ca0dac8526d50820dc532360b45fe7f3931390c7738914a75f8791f1438e868d',
        'content/persistence/stats.py::get_stats': '3632d85522ccd32bd7325df5d4146d3b792f8ec3346d3329c3ee654752bd4813',
        'content/persistence/stats.py::set_achievement': 'ea43e00a3bfda09b6e9ff5411e279ffe3bf8b18ac45fab53499f72e24e5b2e6c',
        'content/persistence/stats.py::get_achievements': '1c81f827399785a6dab8515f0d4cae79aab11b617fb97e38da27811a1405c400',
        'content/persistence/props_use.py::get_props_use': '2cc1f90dbf0b40ed7114630eecb19853f0e548d2013cc164b339cffa5bb22c0c',
        'content/persistence/props_use.py::mark_props_use': 'd61e1834c29eddde0459fc051f51b9e3f2c9bcbcede125a7e4c68f642fbb481d',
        'content/persistence/props_use.py::props_use_claim_atomic': 'c65b316b71ea28073feaf3c54d2ddcb3af393295c664e1e5c95e3eef7f92ba57',
        'content/worlds.py::get_instance_world': 'abfa3639859424ba87149776254ba7c6a24de34292aedd38c326c559bf0ec2cb',
        'content/worlds.py::_restore_from_db': '6a480c5fc5374fcc4d4d934f3c7f35a3a749258d0022c4e0b8e9c59ab18d81a5',
        'content/worlds.py::create_instance_world': '1085ebc18004e207fc9f9114bea6b1c82b67e08a23409d57b7c2084d7600195f',
        'content/worlds.py::destroy_instance_world': 'b44b3d4db6cdde2427dd462b115d8fd7e64e0a2aa97353ee18d96633f84d133b',
        'content/worlds.py::_json_ready': '<deleted>',
        'content/worlds.py::_persist': '6245e67303e2615ff2c13ef8b4c796d6354650ac1f8a99d196ed8b1c35f9f608',
        'content/worlds.py::update_instance_world': '586e5b8580ea887a910e7c0a1be3448d0b07402b078cb9931cf2b809ec528cb4',
        'content/worlds.py::cleanup_stale_instances': 'fb12f7ebbfdc32ad25f20871f11d60809bda2fbadf3b90f64082ed05eb19f383',
        'content/worlds.py::resolve_map_for': 'ce72a0fa44a6f19877aedf95bee5131e8b66988571c7c5c9bb65ea0dea7dcad9',
    },
    'aux': {
        'battle_state_monster': '野狗·头目',
        'battle_state_state': '{"type": "monster", "now": 0.0, "enemies": [{"name": "野狗·头目", "hp": 12}], "p_buffs": {}, "p_defending": false, "_warned": ["p1"]}',
        'battle_state_updated_at': '1700000000',
        'bestiary_row': '[{"kills": 2, "monster": "m_wolf", "name": "m_wolf"}]',
        'boss_dmg_key': 'boss_dmg_1001',
        'boss_dmg_read': '2.5',
        'daily_fortune_key': 'daily_fortune_g1_1001',
        'instance_world_raw': '{"name": "哥布林营地", "inst_id": "inst_goblin_camp", "maps": {"goblin_camp": {"id": "goblin_camp", "name": "哥布林营地", "lv": 15, "region": "南境·绿野", "chapter": 1, "area": "goblin", "area_name": "哥布林营地", "desc": "哥布林营地，传说中的危险之地，唯有勇者敢于踏入。\\n💡 输入『副本 哥布林营地』开启挑战（组队副本，等级/人数校验）", "type": "副本", "shop": false, "healer": false, "hidden": false, "monsters": [], "elite": null, "boss": null, "npcs": [], "dungeon": {"no_exit": true, "discovery_agro": 0.85, "boss_room": "goblin_camp_3", "on_clear": "victory"}, "subareas": [{"id": "goblin_camp_1", "name": "入口栅栏", "icon": "🚪", "desc": "歪斜的木栅栏围出营地外围，兽皮晾在栏上，篝火堆散落四周。守卫在缺口处探头张望，臭味与叫嚷声扑面而来。", "type": "副本", "lv": 15, "npcs": [], "monsters": [["m_goblin_guard", "哥布林守卫", "tank", 15, ["ms_dun_ji"], ["哥布林铁片"]], ["m_goblin_shaman", "哥布林萨满", "healer", 16, ["ms_zhi_liao", "ms_du_wu"], ["萨满图腾"]]], "elite": null, "boss": null, "funcs": ["instance"], "shop": false, "healer": false}, {"id": "goblin_camp_2", "name": "篝火营地", "icon": "🔥", "desc": "营地中央的篝火噼啪作响，酒桶堆在火边，狂战士围着火堆磨牙鼓噪。酋长的帐篷就矗立在火光尽头。", "type": "副本", "lv": 18, "npcs": [], "monsters": [["m_goblin_berserker", "哥布林狂战士", "dps", 18, ["ms_lian_zhan"], ["狂战士腰带"]]], "elite": ["e_goblin_berserker", "哥布林狂战士", "elite", 18, ["ms_kuang_bao", "ms_lian_zhan"], ["哥布林徽记"]], "boss": null, "funcs": ["instance"], "shop": false, "healer": false}, {"id": "goblin_camp_3", "name": "酋长帐篷", "icon": "👑", "desc": "兽骨装饰的帐篷深处，咕噜酋长坐在兽皮宝座上，身边堆满抢来的货物。皇冠歪戴，它正等着好好『招待』不速之客。", "type": "副本", "lv": 20, "npcs": [], "monsters": [], "elite": null, "boss": ["b_goblin_chief", "哥布林酋长·咕噜", "boss", 20, ["ms_lian_zhan", "ms_lve_duo_h_ling", "ms_zhao_huan", "ms_nu_hou"], ["咕噜皇冠"]], "funcs": ["instance"], "shop": false, "healer": false}]}}, "subareas": {"goblin_camp": [{"id": "goblin_camp_1", "name": "入口栅栏", "icon": "🚪", "desc": "歪斜的木栅栏围出营地外围，兽皮晾在栏上，篝火堆散落四周。守卫在缺口处探头张望，臭味与叫嚷声扑面而来。", "type": "副本", "lv": 15, "npcs": [], "monsters": [["m_goblin_guard", "哥布林守卫", "tank", 15, ["ms_dun_ji"], ["哥布林铁片"]], ["m_goblin_shaman", "哥布林萨满", "healer", 16, ["ms_zhi_liao", "ms_du_wu"], ["萨满图腾"]]], "elite": null, "boss": null, "funcs": ["instance"], "shop": false, "healer": false}, {"id": "goblin_camp_2", "name": "篝火营地", "icon": "🔥", "desc": "营地中央的篝火噼啪作响，酒桶堆在火边，狂战士围着火堆磨牙鼓噪。酋长的帐篷就矗立在火光尽头。", "type": "副本", "lv": 18, "npcs": [], "monsters": [["m_goblin_berserker", "哥布林狂战士", "dps", 18, ["ms_lian_zhan"], ["狂战士腰带"]]], "elite": ["e_goblin_berserker", "哥布林狂战士", "elite", 18, ["ms_kuang_bao", "ms_lian_zhan"], ["哥布林徽记"]], "boss": null, "funcs": ["instance"], "shop": false, "healer": false}, {"id": "goblin_camp_3", "name": "酋长帐篷", "icon": "👑", "desc": "兽骨装饰的帐篷深处，咕噜酋长坐在兽皮宝座上，身边堆满抢来的货物。皇冠歪戴，它正等着好好『招待』不速之客。", "type": "副本", "lv": 20, "npcs": [], "monsters": [], "elite": null, "boss": ["b_goblin_chief", "哥布林酋长·咕噜", "boss", 20, ["ms_lian_zhan", "ms_lve_duo_h_ling", "ms_zhao_huan", "ms_nu_hou"], ["咕噜皇冠"]], "funcs": ["instance"], "shop": false, "healer": false}]}, "created_at": 1700000000, "leader": "1001", "members": ["1001", "1002"], "rooms": {}, "resources_pool": {}, "st": {"investigated": ["a"]}, "retreated": false}',
        'item_view_mode_key': 'item_view_mode:1001',
        'move_mode_key': 'move_mode:1001',
        'prof_daily_key': 'prof_daily_1001_2026-01-01',
        'props_use_raw': '{"oak:1:chest": "2026-01-01"}',
        'schema_battle_state': 'e416e09df8a41912991616228ee560751e9272297e6f6d4e8886cfbae3e675b7',
        'schema_event_state': 'fbe7a34937e9ae7cba01374bc6533a676f7a5a4e516d27b95c72b62525c4274e',
        'schema_props_use': 'feea7ea929c9464f6514841a3a8ecef9a3e5e78511230b3512fb0b285e349aee',
        'schema_stats': '535676e0359321303c2e7b2931219cf393c78dce5b8d1e7649ac6be56f979267',
        'stats_row': '{"alchemy_count": 0, "boss_kills": 0, "catch_collect": 0, "chests_opened": 0, "cook_count": 0, "craft_count": 0, "day_date": "", "day_kills": 0, "deaths": 0, "elite_kills": 0, "enchant_count": 0, "enhance_count": 0, "fish_count": 5, "gather_count": 0, "inst_clears": 0, "kills": 1, "mine_count": 0, "party_count": 0, "qq_id": "1001", "visited_areas": 0, "world_events": 0}',
        'talk_flag_raw': '{"npc_mayor": ["pledged"]}',
        'talk_flags_key': 'talkflags_g1_1001',
        'talk_key': 'talk_g1_1001',
        'talk_state_raw': '{"npc": "npc_mayor", "node": "welcome"}',
        'timed_key': 'timed_events_1001',
        'timed_raw': '[{"key": "wild:w_old_trader", "type": "wild_npc", "data": {"npc_id": "w_old_trader", "map": "oak_plain"}, "expire": 1700003600}]',
        'wildmeta_key': 'wildmeta_g1_1001',
        'wildmeta_raw': '{"met": ["w_old_trader"], "miss": {"h_owl": 3}, "last": {"h_owl": 1700000000}}',
    },
    'segments': {
        'E': [
            'content/persistence/battle_state.py::_monster_display_name',
            'content/worlds.py::get_instance_world',
            'content/worlds.py::create_instance_world',
            'content/worlds.py::destroy_instance_world',
            'content/worlds.py::update_instance_world',
            'content/worlds.py::resolve_map_for',
        ],
        'C': [
            'content/persistence/battle_state.py::_json_ready',
            'content/persistence/battle_state.py::save_battle',
            'content/persistence/battle_state.py::get_battle',
            'content/persistence/battle_state.py::get_battle_raw',
            'content/persistence/battle_state.py::clear_battle',
            'content/persistence/stats.py::init_stats',
            'content/persistence/stats.py::bump_stats',
            'content/persistence/stats.py::get_stats',
            'content/persistence/stats.py::set_achievement',
            'content/persistence/stats.py::get_achievements',
            'content/persistence/props_use.py::get_props_use',
            'content/persistence/props_use.py::mark_props_use',
            'content/persistence/props_use.py::props_use_claim_atomic',
            'content/worlds.py::_restore_from_db',
            'content/worlds.py::_json_ready',
            'content/worlds.py::_persist',
            'content/worlds.py::cleanup_stale_instances',
        ],
    },
    'tier': {
        'content/persistence/battle_state.py::_json_ready': '甲',
        'content/persistence/battle_state.py::_monster_display_name': '甲',
        'content/persistence/battle_state.py::save_battle': '甲',
        'content/persistence/battle_state.py::get_battle': '甲',
        'content/persistence/battle_state.py::get_battle_raw': '甲',
        'content/persistence/battle_state.py::clear_battle': '甲',
        'content/persistence/stats.py::init_stats': '甲',
        'content/persistence/stats.py::bump_stats': '甲',
        'content/persistence/stats.py::get_stats': '甲',
        'content/persistence/stats.py::set_achievement': '甲',
        'content/persistence/stats.py::get_achievements': '甲',
        'content/persistence/props_use.py::get_props_use': '甲',
        'content/persistence/props_use.py::mark_props_use': '甲',
        'content/persistence/props_use.py::props_use_claim_atomic': '甲',
        'content/worlds.py::get_instance_world': '甲',
        'content/worlds.py::_restore_from_db': '甲',
        'content/worlds.py::create_instance_world': '甲',
        'content/worlds.py::destroy_instance_world': '甲',
        'content/worlds.py::_json_ready': '甲',
        'content/worlds.py::_persist': '甲',
        'content/worlds.py::update_instance_world': '甲',
        'content/worlds.py::cleanup_stale_instances': '甲',
        'content/worlds.py::resolve_map_for': '甲',
    },
}
# <<< _u1d2_store_gen (auto) <<<

# ══════════════════════════════════════════════════════════════════════════════
# 1. 私有库 / 伪时钟 / 猴补 / 旧实现命名空间
# ══════════════════════════════════════════════════════════════════════════════
FIXED_NOW = 1700000000
MAX_AGE = 24 * 3600

_CLOCK = {"ts": FIXED_NOW}


def _fake_clock():
    return _CLOCK["ts"]


class _TimeShim:
    """`worlds.py` 里 `time.time()` 的替身（`cleanup_stale_instances` 直读 `time.time`）。"""

    def time(self):
        return _CLOCK["ts"]


@contextlib.contextmanager
def _clock(ts):
    old = _HND._H["clock"]
    _HND._H["clock"] = _fake_clock
    saved = _CLOCK["ts"]
    _CLOCK["ts"] = ts
    try:
        yield
    finally:
        _HND._H["clock"] = old
        _CLOCK["ts"] = saved


class _Patch:
    """猴补上下文（进入记原值，退出原地还原；**不写盘**）。"""

    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value
        self.had = hasattr(obj, name)
        self.old = getattr(obj, name, None)

    def __enter__(self):
        setattr(self.obj, self.name, self.value)
        return self

    def __exit__(self, *exc):
        if self.had:
            setattr(self.obj, self.name, self.old)
        elif hasattr(self.obj, self.name):
            delattr(self.obj, self.name)
        return False


DB = _HND.get_db()
DB.init()

_TABLES = ("battle_state", "props_use", "event_state", "stats", "achievements", "bestiary")


def _clear(*tables):
    conn = DB.connect()
    try:
        for t in (tables or _TABLES):
            conn.execute("DELETE FROM %s" % t)
        conn.commit()
    finally:
        conn.close()


def _sql(text, args=()):
    conn = DB.connect()
    try:
        return conn.execute(text, args).fetchall()
    finally:
        conn.close()


def _safe_commit(conn):
    """提交（失败则回滚）—— 引擎写路径**不自己 commit**（事务边界交调用方）。"""
    try:
        conn.commit()
    except Exception:                                            # noqa: BLE001
        try:
            conn.rollback()
        except Exception:                                        # noqa: BLE001
            pass


def _one(text, args=()):
    rows = _sql(text, args)
    return rows[0] if rows else None


def _store_ready_ref(obj):
    """门禁自带的 set 清洗（= 原 `_json_ready` 口径；内容侧经 `prepare` 注入同一规则）。"""
    if isinstance(obj, set):
        return [_store_ready_ref(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _store_ready_ref(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_store_ready_ref(x) for x in obj]
    return obj


# ── 内容侧 repo 取件（landed 用内容的；baseline 用门禁本地等价声明）──────────────
SPEC_BS = SnapshotSpec("battle_state", owner="qq_id", blob="state", stamp="updated_at",
                       extra=(Column("monster", "TEXT", notnull=True),), pk=("qq_id",),
                       expired_key="_expired")
SPEC_PU = SnapshotSpec("props_use", owner="qq_id", blob="used")
SPEC_IW = SnapshotSpec("event_state", owner="key", blob="value",
                       stamp_key="created_at", expired_key="_expired")
SPEC_ST = CounterSpec("stats", owner="qq_id", fields=tuple(sorted(ST.STAT_FIELDS)))
SPEC_BI = CounterSpec("bestiary", owner="qq_id", fields=("kills",), subject="monster")


def _declared(table, pkcols, json_fields=()):
    return DeclaredRepository(
        DB, TableSpec(table, [Column(c, "TEXT", pk=True) for c in pkcols]),
        json_fields=json_fields)


class _KeepExtraRepo(DeclaredRepository):
    """快照 upsert 适配（见 `battle_state.py` 同名类）：`battle_state` 有 NOT NULL 的
    展示名列，而快照写路径（`put` / 过期打标）只带 owner + blob。写前把**既有行**的
    其余列合并回来；新建行仍须由调用方给全列。"""

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


SNAP_BS_LOCAL = declare_snapshot(DB, SPEC_BS, prepare=_store_ready_ref,
                                 repo=_KeepExtraRepo(
                                     DB, TableSpec("battle_state",
                                                   [Column("qq_id", "TEXT", pk=True)]),
                                     json_fields=("state",)))
SNAP_PU_LOCAL = declare_snapshot(DB, SPEC_PU,
                                 repo=_declared("props_use", ("qq_id",), ("used",)))
SNAP_IW_LOCAL = declare_snapshot(DB, SPEC_IW, prepare=_store_ready_ref,
                                 repo=_declared("event_state", ("key",), ("value",)))
CNT_ST_LOCAL = declare_counters(DB, SPEC_ST, repo=_declared("stats", ("qq_id",)))
CNT_BI_LOCAL = declare_counters(DB, SPEC_BI,
                                repo=_declared("bestiary", ("qq_id", "monster")))


def _snap_bs():
    fn = getattr(BS, "_snap", None)
    return fn() if fn is not None else SNAP_BS_LOCAL


def _snap_pu():
    fn = getattr(PU, "_snap", None)
    return fn() if fn is not None else SNAP_PU_LOCAL


def _snap_iw():
    fn = getattr(W, "_snap", None)
    return fn() if fn is not None else SNAP_IW_LOCAL


def _cnt_st():
    fn = getattr(ST, "_cnt", None)
    return fn() if fn is not None else CNT_ST_LOCAL


def _repo(kind):
    return {"bs": _snap_bs, "pu": _snap_pu, "iw": _snap_iw}[kind]()


_TABLE = {"bs": "battle_state", "pu": "props_use", "iw": "event_state"}

# ── 旧实现命名空间（exec 冻结字面量）──────────────────────────────────────────
_REL = {id(BS): "content/persistence/battle_state.py",
        id(ST): "content/persistence/stats.py",
        id(PU): "content/persistence/props_use.py",
        id(W): "content/worlds.py"}
_OLD = {}


def _old_ns(mod, symbols, *, private_mem=False):
    key = (id(mod), private_mem)
    if key in _OLD:
        return _OLD[key]
    ns = dict(vars(mod))
    if private_mem:
        ns["instance_worlds"] = {}
        ns["time"] = _TimeShim()
    rel = _REL[id(mod)]
    for sym in symbols:
        src = _FROZEN_TEXT["%s::%s" % (rel, sym)]
        exec(compile(src, "<frozen:%s:%s>" % (rel, sym), "exec"), ns)   # noqa: S102
    _OLD[key] = ns
    return ns


def _old_bs():
    return _old_ns(BS, ("_json_ready", "_monster_display_name", "save_battle",
                        "get_battle", "get_battle_raw", "clear_battle"))


def _old_st():
    return _old_ns(ST, ("init_stats", "bump_stats", "get_stats",
                        "set_achievement", "get_achievements"))


def _old_pu():
    return _old_ns(PU, ("get_props_use", "mark_props_use", "props_use_claim_atomic"))


def _old_w():
    return _old_ns(W, ("get_instance_world", "_restore_from_db", "create_instance_world",
                       "destroy_instance_world", "_json_ready", "_persist",
                       "update_instance_world", "cleanup_stale_instances", "resolve_map_for"),
                   private_mem=True)


# ══════════════════════════════════════════════════════════════════════════════
# 2. [1] 双 sha256 + E/C
# ══════════════════════════════════════════════════════════════════════════════
def _live_obj(relpath, symbol):
    modname = "content." + relpath.split("/", 1)[1][:-3].replace("/", ".")
    mod = importlib.import_module(modname)
    return getattr(mod, symbol, None)


def test_frozen_pins():
    print("【1. 双 sha256：23 段冻结文本 + 活实现 inspect.getsource】")
    keys = list(_PIN["frozen"])
    check("冻结段数 == 23（6+5+3+9）", len(keys) == 23, len(keys))
    bad = [k for k in keys if sha256(_FROZEN_TEXT[k]) != _PIN["frozen"][k]]
    check("冻结文本 sha256 全等 _PIN['frozen']（23 段）", not bad, bad[:4])

    live_bad = []
    deleted_bad = []
    for k in keys:
        relpath, symbol = k.split("::", 1)
        obj = _live_obj(relpath, symbol)
        got = "<deleted>" if obj is None else sha256(inspect.getsource(obj))
        if got != _PIN["live"][k]:
            live_bad.append((k, _PIN["live"][k][:12], got[:12]))
        if _PIN["live"][k] == "<deleted>" and obj is not None:
            deleted_bad.append(k)
    check("活实现 inspect.getsource sha256 全等 _PIN['live']（23 段）",
          not live_bad, live_bad[:4])
    check("`<deleted>` 段在活模块里确实没有", not deleted_bad, deleted_bad)

    seg = _PIN["segments"]
    chk_e = [k for k in seg["E"] if _PIN["frozen"][k] != _PIN["live"][k]]
    check("E 栏「预期不变」段 frozen == live（%d 段）" % len(seg["E"]), not chk_e, chk_e)
    if _PIN["phase"] == "landed":
        chk_c = [k for k in seg["C"] if _PIN["frozen"][k] == _PIN["live"][k]]
        check("C 栏「预期会变」段 frozen != live（%d 段）" % len(seg["C"]), not chk_c, chk_c)
        check("两份 `_json_ready` 已删（live == '<deleted>'）",
              all(_PIN["live"]["%s::_json_ready" % p] == "<deleted>"
                  for p in ("content/persistence/battle_state.py", "content/worlds.py")))
    else:
        check("baseline 档：跳过 C 栏不等式（实现未改）", True)
    check("档位 甲 23 / 乙 0 / 丙 0",
          set(_PIN["tier"].values()) == {"甲"}, sorted(set(_PIN["tier"].values())))


# ══════════════════════════════════════════════════════════════════════════════
# 3. [2] 网格 A（快照）—— 3 repo × 5 操作 × 5 owner 态 × 6 载荷形态 = 450
# ══════════════════════════════════════════════════════════════════════════════
CELL = {"A": 0, "B": 0, "C1": 0, "C2": 0, "D": 0, "E5": 0, "E6": 0, "E7": 0}
BAD = {}


def _cell(tag, name, ok, detail=""):
    CELL[tag] += 1
    if not ok:
        BAD.setdefault(tag, []).append("%s | %s" % (name, detail))


OWNER_STATES = ("missing", "fresh", "expiring_1s", "exact", "expired_1s")
FORMS = ("dict", "list", "set_residue", "nested", "bad_json", "empty")
_FORM_TEXT = {
    "dict": '{"type": "monster", "k": 1}',
    "list": "[1, 2, 3]",
    "set_residue": "\"{'a', 'b'}\"",
    "nested": '{"type": "monster", "d": {"x": [1, {"y": 2}]}}',
    "bad_json": "{oops",
    "empty": "{}",
}
_FORM_PAYLOAD = {
    "dict": {"type": "monster", "k": 1},
    "list": [1, 2, 3],
    "set_residue": {"type": "monster", "_warned": {"a", "b"}},
    "nested": {"type": "monster", "d": {"x": [1, {"y": 2}]}},
    "bad_json": {"type": "monster", "raw": "{oops"},
    "empty": {},
}


def _iw_text(form, stamp):
    text = _FORM_TEXT[form]
    try:
        p = json.loads(text)
    except Exception:                                            # noqa: BLE001
        return text
    if isinstance(p, dict):
        p["created_at"] = stamp
        return json.dumps(p, ensure_ascii=False)
    return text


def _seed(kind, owner, state, form, now, ttl_eff):
    _clear(_TABLE[kind])
    if state == "missing":
        return None
    off = {"fresh": 0, "expiring_1s": ttl_eff - 1, "exact": ttl_eff,
           "expired_1s": ttl_eff + 1}[state]
    stamp = now - off
    text = _FORM_TEXT[form]
    conn = DB.connect()
    try:
        if kind == "bs":
            conn.execute("INSERT INTO battle_state (qq_id, monster, state, updated_at) "
                         "VALUES (?,?,?,?)", (owner, "L5", text, stamp))
        elif kind == "pu":
            conn.execute("INSERT INTO props_use (qq_id, used) VALUES (?,?)", (owner, text))
        else:
            text = _iw_text(form, stamp)
            conn.execute("INSERT INTO event_state (key, value) VALUES (?,?)", (owner, text))
        conn.commit()
    finally:
        conn.close()
    return text


def _blob_text(kind, owner):
    col = {"bs": "state", "pu": "used", "iw": "value"}[kind]
    pk = {"bs": "qq_id", "pu": "qq_id", "iw": "key"}[kind]
    row = _one("SELECT %s AS b FROM %s WHERE %s=?" % (col, _TABLE[kind], pk), (owner,))
    return None if row is None else row["b"]


def _row_exists(kind, owner):
    pk = {"bs": "qq_id", "pu": "qq_id", "iw": "key"}[kind]
    return _one("SELECT 1 AS x FROM %s WHERE %s=?" % (_TABLE[kind], pk), (owner,)) is not None


def _raw_expected(text):
    if text is None:
        return None
    try:
        p = json.loads(text)
    except Exception:                                            # noqa: BLE001
        return None
    return p if isinstance(p, dict) else None


def _run_a_cell(kind, op, state, form, now, ttl, ttl_eff):
    repo = _repo(kind)
    owner = "L5A-%s-%s-%s-%s" % (kind, op, state, form)
    seed_text = _seed(kind, owner, state, form, now, ttl_eff)
    want_raw = _raw_expected(seed_text)
    existed = state != "missing"
    conn = DB.connect()
    calls = []
    try:
        if op == "put":
            payload = _FORM_PAYLOAD[form]
            prepare = getattr(repo, "prepare", None)
            puttable = (form != "list") and not (form == "set_residue" and prepare is None)
            err = None
            try:
                repo.put(conn, owner, payload,
                         **({"stamp": now} if kind in ("bs", "iw") else {}))
            except Exception as exc:                             # noqa: BLE001
                err = exc
            _safe_commit(conn)
            if puttable and kind == "bs" and state == "missing":
                # battle_state 有 NOT NULL 展示名列（monster）：blob-only `put` 建不出新行
                # （内容侧 `save_battle` 走全行 upsert；打标路径走 `_KeepExtraRepo` 合并既有行）
                ok = isinstance(err, sqlite3.IntegrityError) and not _row_exists(kind, owner)
                det = "err=%r" % (err,)
            elif puttable:
                body = dict(payload)
                if prepare is not None:
                    body = prepare(body)
                if kind == "iw":
                    body["created_at"] = now
                want_text = json.dumps(body, ensure_ascii=False)
                ok = (err is None and _blob_text(kind, owner) == want_text)
                det = "err=%r text=%r want=%r" % (err, _blob_text(kind, owner), want_text)
            else:
                ok = isinstance(err, TypeError)
                ok = ok and _blob_text(kind, owner) == seed_text
                det = "err=%r" % (err,)
        elif op == "raw":
            got = repo.raw(conn, owner)
            _safe_commit(conn)
            ok = (got == want_raw and _blob_text(kind, owner) == seed_text)
            det = "got=%r want=%r text=%r seed=%r" % (got, want_raw,
                                                      _blob_text(kind, owner), seed_text)
        elif op == "get":
            got = repo.get(conn, owner, now=now, ttl=ttl,
                           on_expire=lambda o, p: calls.append(o))
            _safe_commit(conn)
            if ttl is None or want_raw is None or state in ("fresh", "expiring_1s", "exact"):
                ok = (got == want_raw and _blob_text(kind, owner) == seed_text)
                det = "got=%r want=%r" % (got, want_raw)
            else:  # expired_1s + dict 载荷 → keep=None → on_expire + 删行
                ok = (got is None and _row_exists(kind, owner) is False
                      and len(calls) == 1)
                det = "got=%r calls=%d exists=%r" % (got, len(calls),
                                                     _row_exists(kind, owner))
        elif op == "drop":
            n = repo.drop(conn, owner)
            _safe_commit(conn)
            ok = (n == (1 if existed else 0)) and (_row_exists(kind, owner) is False)
            det = "n=%r existed=%r" % (n, existed)
        elif op == "sweep":
            if ttl is None:
                try:
                    repo.sweep(conn, now=now, ttl=ttl)
                    ok = False
                    det = "未抛 ValueError"
                except ValueError:
                    ok = True
                    det = ""
            else:
                got = repo.sweep(conn, now=now, ttl=ttl,
                                 on_expire=lambda o, p: calls.append(o))
                _safe_commit(conn)
                if want_raw is not None and state == "expired_1s":
                    ok = (got == [(owner, want_raw)] and _row_exists(kind, owner) is False)
                    det = "got=%r" % (got,)
                else:
                    ok = (got == [] and _blob_text(kind, owner) == seed_text)
                    det = "got=%r" % (got,)
        else:                                                    # pragma: no cover
            ok, det = False, "unknown op"
    finally:
        conn.close()
    _cell("A", "%s/%s/%s/%s" % (kind, op, state, form), ok, det)


def test_grid_a():
    print("【2. 网格 A（快照）：3 repo × 5 操作 × 5 owner 态 × 6 载荷形态】")
    now = FIXED_NOW
    for kind in ("bs", "pu", "iw"):
        ttl = None if kind == "pu" else MAX_AGE
        ttl_eff = 0 if ttl is None else ttl
        for op in ("put", "get", "raw", "drop", "sweep"):
            for state in OWNER_STATES:
                for form in FORMS:
                    _run_a_cell(kind, op, state, form, now, ttl, ttl_eff)
    bad = BAD.get("A", [])
    check("网格 A 逐格（450 格）全等", not bad, bad[:3])
    check("网格 A 实测格数 == 450", CELL["A"] == 450, CELL["A"])


# ══════════════════════════════════════════════════════════════════════════════
# 4. [3] 网格 B（计数器）
# ══════════════════════════════════════════════════════════════════════════════
STAT_COLS = tuple(sorted(ST.STAT_FIELDS))
_DELTAS = (1, 5, -1)
_INITS = ("missing", "0", "7", "bad")
_INIT_VAL = {"0": 0, "7": 7, "bad": "x"}


def _insert_stat(owner, col, value):
    conn = DB.connect()
    try:
        conn.execute("INSERT INTO stats (qq_id, %s) VALUES (?,?)" % col, (owner, value))
        conn.commit()
    finally:
        conn.close()


def test_grid_b():
    print("【3. 网格 B（计数器）：19 列 × 3 增量 × 4 初值 + 非法名 + 读 + 归零】")
    cnt = _cnt_st()
    owner = "L5B"
    # ① 228 格
    for col in STAT_COLS:
        for delta in _DELTAS:
            for init in _INITS:
                _clear("stats")
                if init != "missing":
                    _insert_stat(owner, col, _INIT_VAL[init])
                conn = DB.connect()
                try:
                    cnt.bump(conn, owner, **{col: delta})
                    conn.commit()
                    row = cnt.read(conn, owner)
                finally:
                    conn.close()
                if init == "missing":
                    ok, want = (row == {}), "{}"
                else:
                    base = _INIT_VAL[init]
                    base = base if isinstance(base, int) else 0
                    want = {"%s" % col: base + delta}
                    ok = (row.get(col) == base + delta)
                _cell("B", "bump/%s/%s/%s" % (col, delta, init), ok,
                      "row=%r want=%r" % (row, want))
    # ② 19 非法名 → ValueError
    for i in range(len(STAT_COLS)):
        _clear("stats")
        conn = DB.connect()
        try:
            cnt.bump(conn, owner, **{"bad_col_%02d" % i: 1})
            got = None
        except Exception as exc:                                 # noqa: BLE001
            got = exc
        finally:
            conn.close()
        _cell("B", "illegal/%02d" % i, isinstance(got, ValueError), "got=%r" % (got,))
    # ③ 读 57 格
    for col in STAT_COLS:
        for state in ("missing", "value", "zero"):
            _clear("stats")
            if state == "value":
                _insert_stat(owner, col, 7)
            elif state == "zero":
                conn = DB.connect()
                try:
                    conn.execute("INSERT INTO stats (qq_id) VALUES (?)", (owner,))
                    conn.commit()
                finally:
                    conn.close()
            conn = DB.connect()
            try:
                row = cnt.read(conn, owner)
            finally:
                conn.close()
            if state == "missing":
                ok, det = (row == {}), repr(row)
            elif state == "value":
                ok, det = (row.get(col) == 7), "row[%s]=%r" % (col, row.get(col))
            else:
                ok, det = (row.get(col) == 0), "row[%s]=%r" % (col, row.get(col))
            _cell("B", "read/%s/%s" % (col, state), ok, det)
    # ④ 归零 38 格
    for col in STAT_COLS:
        for mode in ("all", "one"):
            _clear("stats")
            sets = ", ".join("%s=7" % c for c in STAT_COLS)
            conn = DB.connect()
            try:
                conn.execute("INSERT INTO stats (qq_id) VALUES (?)", (owner,))
                conn.execute("UPDATE stats SET %s WHERE qq_id=?" % sets, (owner,))
                if mode == "all":
                    cnt.reset(conn, owner)
                else:
                    cnt.reset(conn, owner, fields=[col])
                conn.commit()
                row = cnt.read(conn, owner)
            finally:
                conn.close()
            if mode == "all":
                ok = all(row.get(c) == 0 for c in STAT_COLS)
            else:
                ok = (row.get(col) == 0
                      and all(row.get(c) == 7 for c in STAT_COLS if c != col))
            _cell("B", "reset/%s/%s" % (col, mode), ok, repr(row))
    bad = BAD.get("B", [])
    check("网格 B 逐格（228 增量 + 19 非法 + 57 读 + 38 归零 = 342）全等",
          not bad, bad[:3])
    check("网格 B 实测格数 == 342", CELL["B"] == 342, CELL["B"])


# ══════════════════════════════════════════════════════════════════════════════
# 5. [4] 网格 C（TTL 边界 + created_at 两层）
# ══════════════════════════════════════════════════════════════════════════════
TTLS = (0, 1, 86399, 86400, 86401)
EXITS = ("fresh", "delete", "mark")


def test_grid_c_ttl():
    print("【4a. 网格 C（TTL 边界）：5 ttl × 2 类型 × 3 出口】")
    now = FIXED_NOW
    for ttl in TTLS:
        for typ in ("monster", "instance"):
            for exit_kind in EXITS:
                owner = "L5C-%s-%s-%s" % (ttl, typ, exit_kind)
                off = ttl if exit_kind == "fresh" else ttl + 1
                stamp = now - off
                payload = {"type": typ, "world_id": "inst:abc" if typ == "instance" else ""}
                payload["created_at"] = stamp
                _clear("battle_state")
                conn = DB.connect()
                try:
                    conn.execute("INSERT INTO battle_state (qq_id, monster, state, updated_at) "
                                 "VALUES (?,?,?,?)",
                                 (owner, "L5", json.dumps(payload, ensure_ascii=False), stamp))
                    conn.commit()
                finally:
                    conn.close()
                calls = []
                keep = {"fresh": None,
                        "delete": (lambda o, p: False),
                        "mark": (lambda o, p: True)}[exit_kind]
                conn = DB.connect()
                try:
                    got = _snap_bs().get(conn, owner, now=now, ttl=ttl, keep=keep,
                                         on_expire=lambda o, p: calls.append(o))
                    _safe_commit(conn)
                finally:
                    conn.close()
                text = _blob_text("bs", owner)
                if exit_kind == "fresh":
                    ok = (got == payload and text == json.dumps(payload, ensure_ascii=False)
                          and not calls)
                    det = "got=%r calls=%d" % (got, len(calls))
                elif exit_kind == "delete":
                    ok = (got is None and text is None and len(calls) == 1)
                    det = "got=%r text=%r calls=%d" % (got, text, len(calls))
                else:
                    marked = dict(payload)
                    marked["_expired"] = True
                    ok = (got is None and len(calls) == 1
                          and _one("SELECT updated_at AS u FROM battle_state WHERE qq_id=?",
                                   (owner,))["u"] == stamp
                          and _blob_text("bs", owner) == json.dumps(marked, ensure_ascii=False))
                    det = "got=%r calls=%d text=%r" % (got, len(calls), text)
                _cell("C1", "%s/%s/%s" % (ttl, typ, exit_kind), ok, det)
    bad = BAD.get("C1", [])
    check("网格 C（TTL 30 格）全等", not bad, bad[:3])
    check("网格 C TTL 实测格数 == 30", CELL["C1"] == 30, CELL["C1"])


def _cleanup_case(side, layer, boundary, now, max_age):
    wid = "inst:%s%08d" % ("o" if side == "old" else "n", hash(boundary) % 10 ** 8)
    key = W.EVENT_STATE_PREFIX + wid
    _clear("event_state")
    created = {"zero": 0, "exact": now - max_age, "over": now - max_age - 1,
               "under": now - max_age + 1}[boundary]
    payload = {"name": "L5", "created_at": created}
    PW.set_event_state(key, json.dumps(payload, ensure_ascii=False))
    ns = _old_w() if side == "old" else None
    mem = ns["instance_worlds"] if ns is not None else W.instance_worlds
    saved = dict(mem)
    try:
        mem.clear()
        if layer == "memory":
            mem[wid] = dict(payload)
        with _Patch(W, "time", _TimeShim()):
            fn = ns["cleanup_stale_instances"] if ns is not None else W.cleanup_stale_instances
            n = fn(max_age)
        return (n, PW.get_event_state(key) is not None, wid in mem)
    finally:
        mem.clear()
        mem.update(saved)


def test_grid_c_created():
    print("【4b. 网格 C（created_at 4 边界 × 内存/DB 两层）：旧 ↔ 新】")
    now = FIXED_NOW
    for boundary in ("zero", "exact", "over", "under"):
        for layer in ("memory", "db"):
            old = _cleanup_case("old", layer, boundary, now, MAX_AGE)
            new = _cleanup_case("new", layer, boundary, now, MAX_AGE)
            _cell("C2", "%s/%s" % (boundary, layer), old == new,
                  "old=%r new=%r" % (old, new))
    bad = BAD.get("C2", [])
    check("网格 C（created_at 8 格）旧↔新全等", not bad, bad[:3])
    check("网格 C created_at 实测格数 == 8", CELL["C2"] == 8, CELL["C2"])


# ══════════════════════════════════════════════════════════════════════════════
# 6. [5] 网格 D（复合键）
# ══════════════════════════════════════════════════════════════════════════════
def test_grid_d():
    print("【5. 网格 D（复合键）：3 怪 × 3 owner × 4 初值】")
    monsters = ("m_wolf", "m_bat", "m_slime")
    for mon in monsters:
        for owner in ("d1", "d2", "d3"):
            for init in _INITS:
                _clear("bestiary")
                conn = DB.connect()
                try:
                    if init != "missing":
                        conn.execute("INSERT INTO bestiary (qq_id, monster, kills) VALUES (?,?,?)",
                                     (owner, mon, _INIT_VAL[init]))
                        conn.commit()
                    else:
                        # `Counters.bump` 是 `col=col+δ` 的 UPDATE（不建行）；建行是显式 `init`
                        # （与 `init_stats` 同口径，口径分歧 ⑧）—— 无行格先 `init`
                        CNT_BI_LOCAL.init(conn, owner, subject=mon)
                        conn.commit()
                    CNT_BI_LOCAL.bump(conn, owner, subject=mon, kills=1)
                    conn.commit()
                    row = CNT_BI_LOCAL.read(conn, owner, subject=mon)
                    # 同 owner 不同 subject 互不干扰
                    other = monsters[(monsters.index(mon) + 1) % 3]
                    if init == "missing":
                        CNT_BI_LOCAL.init(conn, owner, subject=other)
                        CNT_BI_LOCAL.bump(conn, owner, subject=other, kills=1)
                        conn.commit()
                    row2 = CNT_BI_LOCAL.read(conn, owner, subject=other)
                    row1_after = CNT_BI_LOCAL.read(conn, owner, subject=mon)
                finally:
                    conn.close()
                if init == "missing":
                    ok = (row.get("kills") == 1 and row2.get("kills") == 1
                          and row1_after.get("kills") == 1)
                else:
                    base = _INIT_VAL[init]
                    base = base if isinstance(base, int) else 0
                    ok = (row.get("kills") == base + 1)
                _cell("D", "%s/%s/%s" % (mon, owner, init), ok, repr(row))
    bad = BAD.get("D", [])
    check("网格 D（36 格）全等", not bad, bad[:3])
    check("网格 D 实测格数 == 36", CELL["D"] == 36, CELL["D"])


# ══════════════════════════════════════════════════════════════════════════════
# 7. [6] 网格 ⑤⑥⑦：JSON 文本 / 键格式 / KV 边界
# ══════════════════════════════════════════════════════════════════════════════
_PUT5 = ({"type": "monster", "k": 1},
         {"type": "monster", "d": {"x": [1, {"y": 2}]}},
         {"name": "余烬·游商", "note": "中文原样落库"},
         {},
         {"type": "instance", "world_id": "inst:x"})


def test_grid_json_keys_kv():
    print("【6. 网格 ⑤ JSON 文本 15 · ⑥ 键格式 10 · ⑦ KV 边界 20】")
    now = FIXED_NOW
    # ⑤ 15
    for kind in ("bs", "pu", "iw"):
        repo = _repo(kind)
        for i, payload in enumerate(_PUT5):
            _clear(_TABLE[kind])
            owner = "L5J-%s-%d" % (kind, i)
            conn = DB.connect()
            try:
                if kind == "bs":
                    # battle_state 有 NOT NULL 展示名列：blob-only `put` 只能更新既有行
                    conn.execute("INSERT INTO battle_state (qq_id, monster, state, updated_at) "
                                 "VALUES (?,?,?,?)", (owner, "seed", "{}", now))
                    conn.commit()
                repo.put(conn, owner, payload,
                         **({"stamp": now} if kind in ("bs", "iw") else {}))
                conn.commit()
            finally:
                conn.close()
            text = _blob_text(kind, owner)
            body = repo.prepare(payload) if getattr(repo, "prepare", None) else payload
            body = dict(body)
            if kind == "iw":
                body["created_at"] = now
            want = json.dumps(body, ensure_ascii=False)
            _cell("E5", "%s/%d" % (kind, i), text == want, "text=%r want=%r" % (text, want))
    # ⑥ 10 键格式
    from content import wild as WD
    from content import timed_events as TE
    keys = {
        "talk_key": PW.talk_state_key("g1", "1001"),
        "talk_flags_key": PW.talk_flags_key("g1", "1001"),
        "wildmeta_key": WD.WILD_META_KEY.format(gid="g1", qid="1001"),
        "timed_key": TE._PLAYER_KEY.format(qq_id="1001"),
        "instance_world_key": W.EVENT_STATE_PREFIX + "inst:abc",
        "boss_dmg_key": "boss_dmg_1001",
        "move_mode_key": "move_mode:1001",
        "item_view_mode_key": "item_view_mode:1001",
        "daily_fortune_key": "daily_fortune_g1_1001",
        "prof_daily_key": "prof_daily_1001_2026-01-01",
    }
    for name, val in keys.items():
        _cell("E6", name, isinstance(val, str) and bool(val), repr(val))
    # ⑦ 20 KV 边界（`str(value)` vs `json.dumps` 两口径）
    kv_forms = (None, "", "0", "not-json", 123)
    expect = {
        "get_event_state": {None: None, "": "", "0": "0", "not-json": "not-json", 123: "123"},
        "get_talk_state": {None: None, "": None, "0": 0, "not-json": None, 123: 123},
        "get_talk_flags": {None: [], "": [], "0": "<ATTRERR>", "not-json": [], 123: "<ATTRERR>"},
        "get_boss_dmg_mult": {None: 1.0, "": 1.0, "0": 0.0, "not-json": 1.0, 123: 123.0},
    }
    talk_key = keys["talk_key"]
    flags_key = keys["talk_flags_key"]
    for form in kv_forms:
        for api in ("get_talk_state", "get_talk_flags", "get_boss_dmg_mult", "get_event_state"):
            key = {"get_talk_state": talk_key, "get_talk_flags": flags_key,
                   "get_boss_dmg_mult": keys["boss_dmg_key"],
                   "get_event_state": "l5kv_1001"}[api]
            PW.set_event_state(key, form) if form is not None else PW.delete_event_state(key)
            try:
                if api == "get_talk_state":
                    got = PW.get_talk_state("g1", "1001")
                elif api == "get_talk_flags":
                    got = PW.get_talk_flags("g1", "1001", "npc")
                elif api == "get_boss_dmg_mult":
                    got = PW.get_boss_dmg_mult("1001")
                else:
                    got = PW.get_event_state("l5kv_1001")
                spec = expect[api][form]
                ok = (got == spec) if spec != "<ATTRERR>" else False
                det = "got=%r" % (got,)
            except AttributeError:
                ok = expect[api][form] == "<ATTRERR>"
                det = "AttributeError"
            except Exception as exc:                             # noqa: BLE001
                ok, det = False, "%s: %s" % (type(exc).__name__, exc)
            finally:
                PW.delete_event_state(key)
            _cell("E7", "%s/%r" % (api, form), ok, det)
    check("网格 ⑤ JSON 文本（15 格）逐字节", not BAD.get("E5"), BAD.get("E5", [])[:3])
    check("网格 ⑥ 键格式（10 格）", not BAD.get("E6"), BAD.get("E6", [])[:3])
    check("网格 ⑦ KV 边界（20 格）", not BAD.get("E7"), BAD.get("E7", [])[:3])
    check("⑤⑥⑦ 实测格数 == 15 / 10 / 20",
          (CELL["E5"], CELL["E6"], CELL["E7"]) == (15, 10, 20),
          (CELL["E5"], CELL["E6"], CELL["E7"]))


# ══════════════════════════════════════════════════════════════════════════════
# 8. [6] aux 指纹（旧实现产出；实现改完后必须逐字节不变）
# ══════════════════════════════════════════════════════════════════════════════
V9_STATE = {"type": "monster", "now": 0.0,
            "enemies": [{"name": "野狗·头目", "hp": 12}], "p_buffs": {},
            "p_defending": False, "_warned": {"p1"}}
_META = {"met": ["w_old_trader"], "miss": {"h_owl": 3}, "last": {"h_owl": 1700000000}}
_TIMED = [{"key": "wild:w_old_trader", "type": "wild_npc", "data": {"npc_id": "w_old_trader",
           "map": "oak_plain"}, "expire": 1700003600}]


def _aux_fingerprints() -> dict:
    out = {}
    with _clock(FIXED_NOW):
        _clear()
        # ④ battle_state 原文
        BS.save_battle("g1", "1001", dict(V9_STATE))
        row = _one("SELECT monster, state, updated_at FROM battle_state WHERE qq_id='1001'")
        out["battle_state_monster"] = row["monster"]
        out["battle_state_state"] = row["state"]
        out["battle_state_updated_at"] = str(row["updated_at"])
        # ⑤ stats 行值
        ST.init_stats("g1", "1001")
        ST.bump_stats("g1", "1001", kills=1, fish_count=5)
        out["stats_row"] = _jdump(ST.get_stats("g1", "1001"))
        # ⑥ props_use 原文
        PU.mark_props_use("1001", "oak:1:chest", "2026-01-01")
        out["props_use_raw"] = _blob_text("pu", "1001")
        # ⑦ instance_world 原文（world_id 归一化成占位符）
        wid = W.create_instance_world("inst_goblin_camp", [1001, 1002],
                                      {"name": "头目"}, now=FIXED_NOW,
                                      st={"investigated": {"a"}})
        raw = PW.get_event_state(W.EVENT_STATE_PREFIX + wid) or ""
        out["instance_world_raw"] = raw.replace(wid, "<wid>")
        W.destroy_instance_world(wid)
        # ⑧ talk_* 原文 + 键
        out["talk_key"] = PW.talk_state_key("g1", "1001")
        out["talk_flags_key"] = PW.talk_flags_key("g1", "1001")
        PW.set_talk_state("g1", "1001", "npc_mayor", "welcome")
        out["talk_state_raw"] = PW.get_event_state(out["talk_key"]) or ""
        PW.set_talk_flag("g1", "1001", "npc_mayor", "pledged")
        out["talk_flag_raw"] = PW.get_event_state(out["talk_flags_key"]) or ""
        PW.clear_talk_state("g1", "1001")
        PW.delete_event_state(out["talk_flags_key"])
        # ⑨ wildmeta_* / timed_events_* 原文 + 键
        from content import wild as WD
        from content import timed_events as TE
        out["wildmeta_key"] = WD.WILD_META_KEY.format(gid="g1", qid="1001")
        PW.set_event_state(out["wildmeta_key"], json.dumps(_META, ensure_ascii=False))
        out["wildmeta_raw"] = PW.get_event_state(out["wildmeta_key"]) or ""
        PW.delete_event_state(out["wildmeta_key"])
        out["timed_key"] = TE._PLAYER_KEY.format(qq_id="1001")
        PW.set_event_state(out["timed_key"], json.dumps(_TIMED, ensure_ascii=False))
        out["timed_raw"] = PW.get_event_state(out["timed_key"]) or ""
        PW.delete_event_state(out["timed_key"])
        # ⑩ 键格式（另 5 条）
        out["boss_dmg_key"] = "boss_dmg_1001"
        PW.set_event_state(out["boss_dmg_key"], "2.5")
        out["boss_dmg_read"] = str(PW.get_boss_dmg_mult("1001"))
        PW.delete_event_state(out["boss_dmg_key"])
        out["move_mode_key"] = "move_mode:1001"
        out["item_view_mode_key"] = "item_view_mode:1001"
        out["daily_fortune_key"] = "daily_fortune_g1_1001"
        out["prof_daily_key"] = "prof_daily_1001_2026-01-01"
        # ⑪ bestiary 行
        _clear("bestiary")
        PW.bump_bestiary("g1", "1001", "m_wolf", 2)
        out["bestiary_row"] = _jdump(PW.get_bestiary("g1", "1001"))
        # ⑰ 四张表的 schema 声明指纹（tables.json 原文）
        _clear()
        path = os.path.join(PKG_ROOT, "content", "persistence", "tables.json")
        with open(path, encoding="utf-8") as fh:
            tables = json.load(fh)["tables"]
        for t in tables:
            if t["name"] in ("battle_state", "stats", "props_use", "event_state"):
                out["schema_%s" % t["name"]] = sha256(_jdump(t))
    return out


def test_aux():
    print("【7. aux 指纹：存档文本 / 键格式 / schema（逐字节）】")
    got = _aux_fingerprints()
    if not _PIN["aux"]:
        check("_PIN['aux'] 已生成", False, "先跑 `_u1d2_store_gen.py --emit-aux`")
        return
    bad = [k for k in _PIN["aux"] if got.get(k) != _PIN["aux"][k]]
    check("aux 指纹 %d 条全等 _PIN['aux']" % len(_PIN["aux"]), not bad,
          [(k, str(_PIN["aux"][k])[:24], str(got.get(k))[:24]) for k in bad][:3])
    need = ("battle_state_state", "stats_row", "props_use_raw", "instance_world_raw",
            "talk_state_raw", "talk_flag_raw", "wildmeta_raw", "timed_raw")
    missing = [k for k in need if k not in _PIN["aux"]]
    check("判据 6 点名的 aux 项齐全", not missing, missing)


# ══════════════════════════════════════════════════════════════════════════════
# 9. [7] 口径分歧 10 条
# ══════════════════════════════════════════════════════════════════════════════
def test_divergences():
    print("【8. 口径分歧 B 存档块 10 条】")
    now = FIXED_NOW
    spec_bs = _snap_bs().spec
    spec_iw = _snap_iw().spec
    spec_pu = _snap_pu().spec
    # ① ttl 基准：列 vs 载荷键
    check("① battle_state 用 stamp 列 updated_at / 无 stamp_key",
          spec_bs.stamp == "updated_at" and spec_bs.stamp_key is None,
          "%r/%r" % (spec_bs.stamp, spec_bs.stamp_key))
    check("① instance_world 用载荷键 created_at / 无 stamp 列",
          spec_iw.stamp_key == "created_at" and spec_iw.stamp is None,
          "%r/%r" % (spec_iw.stamp, spec_iw.stamp_key))
    # ② 三出口 + ttl=None
    check("② props_use 无时间维度（ttl=None 即不过期门）",
          spec_pu.stamp is None and spec_pu.stamp_key is None,
          "%r/%r" % (spec_pu.stamp, spec_pu.stamp_key))
    _clear("battle_state")
    owner = "L5D2"
    conn = DB.connect()
    try:
        conn.execute("INSERT INTO battle_state (qq_id, monster, state, updated_at) VALUES (?,?,?,?)",
                     (owner, "L5", json.dumps({"type": "monster"}), now - MAX_AGE - 1))
        conn.commit()
        raw_before = _blob_text("bs", owner)
        got_none = _snap_bs().get(conn, owner, now=now, ttl=None)
        got_still = _snap_bs().get(conn, owner, now=now, ttl=None)
    finally:
        conn.close()
    check("② ttl=None → 不过期门（等价 raw）",
          got_none == {"type": "monster"} and got_still == {"type": "monster"}
          and _row_exists("bs", owner), "%r/%r" % (got_none, got_still))
    # ③ 打标不改 stamp
    _clear("battle_state")
    owner = "L5D3"
    stamp = now - MAX_AGE - 1
    payload = {"type": "instance", "world_id": "inst:zzz"}
    conn = DB.connect()
    try:
        conn.execute("INSERT INTO battle_state (qq_id, monster, state, updated_at) VALUES (?,?,?,?)",
                     (owner, "L5", json.dumps(payload), stamp))
        conn.commit()
    finally:
        conn.close()
    for _ in range(2):
        conn = DB.connect()
        try:
            _snap_bs().get(conn, owner, now=now, ttl=MAX_AGE,
                           keep=lambda o, p: True, on_expire=lambda o, p: None)
            _safe_commit(conn)
        finally:
            conn.close()
    row = _one("SELECT updated_at AS u, state AS s FROM battle_state WHERE qq_id=?", (owner,))
    check("③ 打标不改 updated_at（两次读仍过期）",
          row is not None and row["u"] == stamp and json.loads(row["s"]).get("_expired") is True,
          repr(row))
    check("③ 打标幂等（`_expired` 只写一次）",
          row is not None and json.loads(row["s"]).get("_expired") is True)
    # ④ str(value) vs json.dumps
    PW.set_event_state("l5d4", 123)
    a = PW.get_event_state("l5d4")
    PW.set_talk_state("g1", "1001", "npc", "node")
    b = PW.get_event_state(PW.talk_state_key("g1", "1001"))
    PW.delete_event_state("l5d4")
    PW.clear_talk_state("g1", "1001")
    check("④ set_event_state 走 str(value) / set_talk_state 走 json.dumps",
          a == "123" and b == '{"npc": "npc", "node": "node"}', "%r / %r" % (a, b))
    # ⑤ / ⑤b 日计数不归本模块；counters 不 import periodic
    def _imports(src):
        mods = []
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
        return mods

    cnt_mod = sys.modules["saintess_engine.store.counters"]
    with open(cnt_mod.__file__, encoding="utf-8") as fh:
        cnt_src = fh.read()
    check("⑤ day_date 不进 CounterSpec.fields（日计数归 periodic）",
          "day_date" not in _cnt_st().fields)
    check("⑤b store/counters.py 不 import periodic（避让判据）",
          not any("periodic" in m for m in _imports(cnt_src)),
          [m for m in _imports(cnt_src) if "periodic" in m])
    with open(W.__file__, encoding="utf-8") as fh:
        w_src2 = fh.read()
    check("⑤ worlds/stats/battle_state 均未 import periodic",
          not any("periodic" in m for m in _imports(w_src2)
                  + _imports(open(BS.__file__, encoding="utf-8").read())
                  + _imports(open(ST.__file__, encoding="utf-8").read())))
    # ⑥ 复合键 vs 一行多列
    check("⑥ stats 单键多列 / bestiary 复合键单列",
          _cnt_st().spec.subject is None and CNT_BI_LOCAL.spec.subject == "monster",
          "%r/%r" % (_cnt_st().spec.subject, CNT_BI_LOCAL.spec.subject))
    # ⑦ 白名单只在 kwargs 形态
    _clear("stats")
    conn = DB.connect()
    try:
        try:
            _cnt_st().bump(conn, "L5D7", nope=1)
            raised = False
        except ValueError:
            raised = True
    finally:
        conn.close()
    with open(PW.__file__, encoding="utf-8") as fh:
        pw_src = fh.read()
    fishing_src = pw_src.split("def bump_fishing", 1)[1].split("def get_fishing_total", 1)[0]
    check("⑦ Counters.bump 白名单 fail-closed", raised)
    check("⑦ bump_fishing 写死 SQL 无白名单（保持原样）",
          "total=total+?" in fishing_src and "ValueError" not in fishing_src)
    # ⑧ 无行读口径
    _clear("stats", "battle_state")
    conn = DB.connect()
    try:
        r1 = _cnt_st().read(conn, "L5D8")
        r2 = _snap_bs().raw(conn, "L5D8")
        r3 = _snap_bs().get(conn, "L5D8", now=now, ttl=MAX_AGE)
    finally:
        conn.close()
    check("⑧ 无行：Counters.read → {} / SnapshotRepo.raw|get → None",
          r1 == {} and r2 is None and r3 is None, "%r/%r/%r" % (r1, r2, r3))
    # ⑨ prepare 是转不是拒收；默认 None 不清
    _clear("battle_state", "props_use")
    conn = DB.connect()
    try:
        conn.execute("INSERT INTO battle_state (qq_id, monster, state, updated_at) "
                     "VALUES (?,?,?,?)", ("L5D9", "seed", "{}", now))
        conn.commit()
        _snap_bs().put(conn, "L5D9", {"_warned": {"a"}})
        conn.commit()
        converted = _snap_bs().raw(conn, "L5D9")
        try:
            _snap_pu().put(conn, "L5D9", {"_warned": {"a"}})
            raised = False
        except TypeError:
            raised = True
        conn.rollback()
    finally:
        conn.close()
    check("⑨ prepare 把 set 转 list（不是拒收）", converted == {"_warned": ["a"]}, repr(converted))
    check("⑨ 未注入 prepare（props_use）→ set 落库抛 TypeError", raised)
    # ⑩ sweep 只扫自己那张表；前缀扫描留在内容侧
    sig = inspect.signature(SnapshotRepo.sweep)
    with open(W.__file__, encoding="utf-8") as fh:
        w_src = fh.read()
    check("⑩ SnapshotRepo.sweep 无 prefix 参数（不扫 KV 前缀）",
          "prefix" not in sig.parameters, list(sig.parameters))
    check("⑩ worlds 第二层 DB 孤儿键前缀扫描逐字保留",
          "key LIKE ?" in w_src and "EVENT_STATE_PREFIX + \"%\"" in w_src
          and "_wid in instance_worlds" in w_src)


# ══════════════════════════════════════════════════════════════════════════════
# 10. [8] 有牙反证 3 处 + 多故障
# ══════════════════════════════════════════════════════════════════════════════
_posix_note = None


def _probe_ttl() -> bool:
    """探针：过期行是否被「永远不过期」放行（True = 红）。"""
    now = FIXED_NOW
    _clear("battle_state")
    owner = "L5P5"
    conn = DB.connect()
    try:
        conn.execute("INSERT INTO battle_state (qq_id, monster, state, updated_at) VALUES (?,?,?,?)",
                     (owner, "L5", json.dumps({"type": "monster"}), now - MAX_AGE - 1))
        conn.commit()
    finally:
        conn.close()
    conn = DB.connect()
    try:
        got = _snap_bs().get(conn, owner, now=now, ttl=MAX_AGE)
        _safe_commit(conn)
        exists = _row_exists("bs", owner)
    finally:
        conn.close()
    return not (got is None and exists is False)


def _probe_whitelist() -> bool:
    """探针：白名单外字段名是否被放行（True = 红）。

    未破坏 → `bump` 当场 `ValueError`（fail-closed）；绕过白名单 → 走到 SQL 才炸
    （`no such column`），两者都算「白名单没拦住」。
    """
    _clear("stats")
    conn = DB.connect()
    try:
        try:
            _cnt_st().bump(conn, "L5P6", nope=1)
            return True
        except ValueError:
            return False
        except Exception:                                        # noqa: BLE001
            return True
    finally:
        _safe_commit(conn)
        conn.close()


def _probe_prepare() -> bool:
    """探针：`put` 是否漏调 `prepare`（set 落库 → TypeError / 文本不等）（True = 红）。"""
    _clear("battle_state")
    conn = DB.connect()
    try:
        conn.execute("INSERT INTO battle_state (qq_id, monster, state, updated_at) "
                     "VALUES (?,?,?,?)", ("L5P7", "seed", "{}", FIXED_NOW))
        conn.commit()
        _snap_bs().put(conn, "L5P7", {"_warned": {"a"}})
        conn.commit()
        text = _blob_text("bs", "L5P7")
    except TypeError:
        return True
    finally:
        conn.close()
    return text != json.dumps({"_warned": ["a"]}, ensure_ascii=False)


_BREAK_TTL = lambda: _Patch(SnapshotRepo, "get", _broken_get)              # noqa: E731
_BREAK_WL = lambda: _Patch(Counters, "_whitelist", _broken_whitelist)      # noqa: E731
_BREAK_PREP = lambda: _Patch(SnapshotRepo, "put", _broken_put)             # noqa: E731


def _broken_get(self, conn, owner, *, now, ttl=None, keep=None, on_expire=None):
    return self.raw(conn, owner)


def _broken_whitelist(self, cols, what):
    return tuple(cols)


def _broken_put(self, conn, owner, payload, *, stamp=None):
    body = dict(payload)
    row = {self.spec.owner: owner}
    if stamp is not None and self.spec.stamp_key is not None:
        body[self.spec.stamp_key] = stamp
    if stamp is not None and self.spec.stamp is not None:
        row[self.spec.stamp] = stamp
    row[self.blob_col] = body
    self.repo.upsert(conn, row)


def test_teeth():
    print("【9. 有牙反证 3 处（预期变红 / 实测变红）】")
    cases = (("TTL 判定改「永远不过期」", _BREAK_TTL, _probe_ttl),
             ("`bump` 白名单放行任意列名", _BREAK_WL, _probe_whitelist),
             ("`prepare` 不清 set", _BREAK_PREP, _probe_prepare))
    for name, breaker, probe in cases:
        check("未破坏时 %s 探针为 False" % name, probe() is False)
    for name, breaker, probe in cases:
        with breaker():
            red = probe() is True
        check("破坏 %s → 实测变红（预期红）" % name, red,
              "探针仍绿 ⇒ 该断言没有牙")
        check("还原 %s → 探针回绿" % name, probe() is False)
    # 多故障 M3：两处同坏，各自变红
    with _BREAK_TTL(), _BREAK_WL():
        both = (_probe_ttl() is True, _probe_whitelist() is True)
        third = _probe_prepare() is False
    check("多故障 M3：TTL + 白名单同坏 → 两条各自变红", all(both), both)
    check("多故障 M3：第三处（prepare）仍绿（不是一个大探针管全部）", third)


# ══════════════════════════════════════════════════════════════════════════════
# 11. [9][10] 只读断言
# ══════════════════════════════════════════════════════════════════════════════
SRC_FILES = ("content/persistence/battle_state.py", "content/persistence/stats.py",
             "content/persistence/props_use.py", "content/worlds.py")
ZERO_FILES = ("content/persistence/world.py", "content/persistence/quests.py",
              "content/persistence/tables.json")


def _file_sha(relpath):
    with open(os.path.join(PKG_ROOT, *relpath.split("/")), encoding="utf-8") as fh:
        return sha256(fh.read())


def _snapshot_files(files):
    return {f: _file_sha(f) for f in files}


def _check_readonly(before):
    print("【10. 只读断言：4 源文件 + 3 零改动文件 sha256 前后一致】")
    after = _snapshot_files(tuple(before))
    bad = [f for f in before if before[f] != after[f]]
    check("跑完全程 %d 个文件零写盘（sha256 前后一致）" % len(before), not bad, bad)


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════
def main() -> int:
    global _posix_note
    files_before = _snapshot_files(SRC_FILES + ZERO_FILES)
    print("phase = %r · GWEN_GAME_DB = %s" % (_PIN["phase"], os.environ.get("GWEN_GAME_DB")))
    _posix_note = _PIN["phase"]
    test_frozen_pins()
    test_grid_a()
    test_grid_b()
    test_grid_c_ttl()
    test_grid_c_created()
    test_grid_d()
    test_grid_json_keys_kv()
    test_aux()
    test_divergences()
    test_teeth()
    _check_readonly(files_before)
    total = CELL["A"] + CELL["B"] + CELL["C1"] + CELL["C2"] + CELL["D"] \
        + CELL["E5"] + CELL["E6"] + CELL["E7"]
    check("计数校验：网格格数合计 == 911", total == 911, total)
    print("  网格实测：A=%d B=%d C1=%d C2=%d D=%d ⑤=%d ⑥=%d ⑦=%d 合计=%d"
          % (CELL["A"], CELL["B"], CELL["C1"], CELL["C2"], CELL["D"],
             CELL["E5"], CELL["E6"], CELL["E7"], total))
    print("=" * 72)
    print("结果：通过 %d / 共 %d" % (PASS, PASS + FAIL))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  ❌ %s" % f)
    print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
