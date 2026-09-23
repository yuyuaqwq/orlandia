# -*- coding: utf-8 -*-
# ==============================================================================
# 包内实现（唯一真源）—— 宿主同名文件 = 薄壳（指向本模块，见那边的头注）。
# 计时机制 = 引擎 `ext_life.timers.Timers`；本文件只留**本游戏的存储面**
# （`event_state` 单键 KV）与对外 API。
# ==============================================================================
"""奥兰迪亚·余烬纪年 core 层 — timed_events.py（v127.5 通用倒计时事件引擎）

把一切"限时存在 / 限时有效 / 到时触发"的玩家状态统一挂到懒计时引擎，
由任意玩家指令（_maint_gate 挂 refresh）惰性刷新，无后台定时器。

设计铁律：
- 数据驱动：新倒计时事件类型 = register_timed() + 各自读写封装，引擎零改动
- 懒计时：不跑定时器；读前 get_timed 校验 + 任意指令 refresh 物理清理
- 一致性：显示出口 + 查找出口都必须走 get_timed → 过期即不可见/不可找，
  不存在"过期还看得见"的窗口
- 存储：复用 event_state KV（一个玩家一个 key，内部 dict 多事件互不覆盖）
  key = timed_events_{qq_id}，value = JSON {"<type>:<sub>": {"type","data","expire"}}
- 纯核心：不碰 DB 以外 IO；存储经包内 `db` 替身（`content.persistence`）

=== 用法示例 ===

# 1. 注册事件类型（模块加载时一次）
register_timed("wild_npc", duration_sec=3600)   # 默认 60 分钟，可按 NPC 覆盖

# 2. 挂载/刷新一个事件（偶遇命中时）
expire = set_timed(group_id, qq_id, key="wild:w_old_trader",
                   type_key="wild_npc", data={"map": map_id})

# 3. 读取（显示/查找出口）——过期自动惰性清除返回 None
ev = get_timed(group_id, qq_id, key="wild:w_old_trader")
if ev:  # {"type","data","expire","remain"}
    ...

# 4. 删除（主动结束事件）
remove_timed(group_id, qq_id, key="wild:w_old_trader")

# 5. 强制刷新（挂 _maint_gate，任意玩家指令触发）
refresh_timed(group_id, qq_id)

# 6. 过期回调注册（可选）：on_expire(type_key)(group_id, qq_id, data) -> None
#    引擎在过期时调用，用于清状态（如对话会话作废）

【骨架归属】引擎的**机制**（类型注册表 / 惰性过期 /
「get / list / refresh 三条路径都触发 on_expire」）来自框架 `ext_life.timers.Timers`；
本文件只留**本游戏的存储适配与对外 API**：存储 key 格式、event_state 三件套、group_id 兼容签名。
"""
import json

from saintess_engine.clock import wall
from ext_life.timers import TimerStorageError, Timers

# ============================================================
# 宿主注入位（历史接口）—— ★ 2026-09-19 审计尾巴 #34
# ------------------------------------------------------------
# 本模块已**零宿主取件**：原文那套手写替身口（`_HOST_PKG` / `_HOST_PKG_FALLBACK` /
# `_INJECTED` / `_host_module` / `_host_attr` / `_HostMod`）在 `_pkgref`（包内惰性句柄）
# 接入后**全仓零调用点**（AST 复核：除注释外零引用），按「零调用点即删」删净；
# 只留 `bind_host` 这个扇出表（`content/facade.py::_BIND_SLOTS`）要求的形参位 ——
# 形状与前例 `content/events.py:59` 一致。
# ============================================================


def bind_host(**objs):
    """宿主注入位（历史接口）：本模块已**零宿主取件**，形参保留只为扇出表照旧调用。"""
    return None


from ._pkgref import DB as db

# 玩家事件存储 key 模板（按玩家全局，跨群共享——倒计时只属于玩家本人）
_PLAYER_KEY = "timed_events_{qq_id}"


# ---------------------------------------------------------------- 存储适配
class _EventStateStore(object):
    """`Timers` 的存储面：包内 event_state KV（扁平 键 → 文本）。

    * 值 = 事件表 `{事件 key: {"type","data","expire"}}` 的 JSON 文本；本适配层负责
      JSON 编解码，坏数据 → `TimerStorageError`（点名键），不静默当空。
    * 缺失 / 空串 → 视为「没有事件」。
    * 取件走本模块既有的惰性宿主替身 `db`（= `content.persistence`），不新增第二个存储出口。
    """

    __slots__ = ()

    def __getitem__(self, key):
        raw = db.get_event_state(key)
        if raw is None or raw == "":
            raise KeyError(key)
        try:
            events = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise TimerStorageError(
                "倒计时事件表取不出来（键 %r）：%s" % (key, exc)) from exc
        if not isinstance(events, dict):
            raise TimerStorageError(
                "倒计时事件表不是映射（键 %r）：%s" % (key, type(events).__name__))
        return events

    def __setitem__(self, key, events):
        db.set_event_state(key, json.dumps(events, ensure_ascii=False))

    def __delitem__(self, key):
        if key not in self:
            raise KeyError(key)
        db.delete_event_state(key)

    def __contains__(self, key):
        raw = db.get_event_state(key)
        return raw is not None and raw != ""

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __repr__(self):
        return "<content.timed_events 事件表存储面：event_state（timed_events_*）>"


_STORE = _EventStateStore()

# 引擎的 owner = 本游戏的 (group_id, qq_id)。用元组而非单值，是因为 on_expire
# 回调签名带 group_id（v127.5 起，如 wild_npc 过期要 db.clear_talk_state(group_id)）。
_timers = Timers(_STORE, clock=lambda: int(wall.now()),
                 key=lambda owner: _PLAYER_KEY.format(qq_id=owner[1]))


# ------------------------------------------------------------------ 对外 API
def register_timed(type_key: str, duration_sec: int | None = None,
                   on_expire=None) -> None:
    """注册/覆盖一个倒计时事件类型。duration_sec 默认秒数（set_timed 未传时用）。

    `on_expire(group_id, qq_id, data) -> None`：该类型的实例过期被清理时调用
    （get / list / refresh 三条路径都会走到，读路径不得绕过）。
    """
    if on_expire is None:
        _timers.register(type_key, duration=duration_sec)
        return

    def _adapted(owner, key, data):
        group_id, qq_id = owner
        return on_expire(group_id, qq_id, data)

    _timers.register(type_key, duration=duration_sec, on_expire=_adapted)


def set_timed(group_id: str, qq_id: str, key: str, type_key: str,
              data: dict | None = None,
              duration_sec: int | None = None) -> int:
    """挂载/刷新一个倒计时事件，返回 expire 时间戳。

    - 同 key 重复挂载 = 顶替刷新（新 expire）
    - 默认时长取类型注册值；未注册类型默认 60s（防御，正常都会 register）
    """
    return _timers.set((group_id, qq_id), key, type_key,
                       data=data, duration=duration_sec)


def get_timed(group_id: str, qq_id: str, key: str) -> dict | None:
    """读取单个事件：未过期返回 {type,data,expire,remain}；过期惰性清除返回 None。

    所有显示/查找出口都必须走这里 → 过期即不可见（惰性正确性核心）。
    过期清除前同样触发 on_expire（读路径不得绕过数据保全回调）。
    """
    return _timers.get((group_id, qq_id), key)


def remove_timed(group_id: str, qq_id: str, key: str) -> bool:
    """主动删除一个事件（返回是否删掉了）"""
    owner_key = _PLAYER_KEY.format(qq_id=qq_id)
    if key not in (_STORE.get(owner_key) or {}):
        return False
    _timers.remove((group_id, qq_id), key)
    return True


def list_timed(group_id: str, qq_id: str, type_key: str | None = None,
               data_match: dict | None = None) -> list:
    """列出未过期事件（可选按 type / data 过滤），顺带惰性清除过期项。

    data_match：data 子集匹配（如 {"map": "oak_plain"} → 只留在该图的事件）
    返回 [{"key","type","data","expire","remain"}, ...]
    """
    events = _timers.due((group_id, qq_id))
    if type_key is not None:
        events = [ev for ev in events if ev["type"] == type_key]
    if data_match:
        events = [ev for ev in events
                  if all(ev["data"].get(k) == v for k, v in data_match.items())]
    return events


def refresh_timed(group_id: str, qq_id: str) -> int:
    """惰性全量刷新：扫该玩家所有事件，过期的执行 on_expire 回调 + 物理删除。

    返回清理的过期事件数（供测试断言）。
    - on_expire(type_key)(group_id, qq_id, data)：清理副作用（如会话作废）
    - 无回调的过期事件仅物理删除（静默）
    """
    owner_key = _PLAYER_KEY.format(qq_id=qq_id)
    before = len(_STORE.get(owner_key) or {})
    _timers.refresh((group_id, qq_id))
    return before - len(_STORE.get(owner_key) or {})
