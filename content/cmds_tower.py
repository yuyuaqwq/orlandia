# -*- coding: utf-8 -*-
"""包内爬塔命令（`content/cmds_tower.py`）—— 『爬塔』的守卫/取参/业务/**渲染**。

终态形状（B18 样板定形；真源 = `overnight/B18_TERMINAL_SHAPE.md` §1.2）：
* handler 签名 `fn(env) -> list[str]`，**直接返回已渲染行**（本命令全 f-string，不涉文案表 →
  字面量随业务一起进包，宿主 `game/commands/tower.py` 里已无任何渲染代码）。
* 取参走引擎 `Env`：`env.arg_text("爬塔")`（= 旧 `self._strip_cmd(event, "爬塔")` 同口径）。
* 分支：等级门槛 → 战斗中拦截 → 目标层解析（1..30、只能挑战已突破层的下一层）→ 每日上限
  → 同层幂等 → 塔层查询 → 塔卫构造 → **开战装配（宿主能力）** → 开战面板。

1. `build_monster` → **包内直取** `content/drops.py`（B2-C2 真搬：drops 8 个真函数已进包；
   调用点用函数内 import，与原 `_host_*("core.drops", …)` 的「调用时解析」同刻）。
2. 开战装配（`Battle` + `battle_bridge` + `db.save_battle` + 单进程锁 + 阵型面板 =
   「必须认识活人世界」）→ 宿主壳对象上的可选能力 `_open_tower_battle`，由桥接层经
   `content/cmds_env.py::shell(env)` 取（与 B18a 的 `ctx.cap("_open_tower_battle")` 同源；
   P2 后由引擎 Host 的能力口取代）。缺能力 → `None`（与真源 try/except 同效）。

行为逐字节不变；证据 = `overnight/W-B18-样板.md` 的 62 场景快照（sha256 改前 = 改后）。
"""
from __future__ import annotations

from .commands import register
from .flow import tower_progress as _TP
from .cmds_env import shell as _shell
from . import texts as _T          # 文案表（C 档 12）

_SEP = "━━━━━━━━━━━━"


def _tower_start(d: dict) -> str:
    """开战面板：7 行模板 + 战斗阵型面板插到第 4 行后（真源同款行序）。"""
    lines = [
        _T.text("tower.title", name=d['fl_name']),
        _T.text("tower.enter", floor=d['floor']),
        _T.text("tower.guard", name=d['guard_name'], lv=d['guard_lv'], suggest=d['suggest_lv']),
        _T.text("tower.desc", desc=d['desc']),
        f"{_SEP}",
        _T.text("tower.reward", exp=d['reward_exp'], gold=d['reward_gold']),
        _T.text("tower.actions", ),
    ]
    if d["panel"] is not None:
        lines.insert(4, d["panel"])
    return "\n".join(lines)


@register("tower_cmd", guards=("hook:player",), params=("cmd=爬塔",))
def tower_cmd(env) -> list:
    qq_id = env.uid
    group_id = env.group_id
    player = env.player
    lv = int(player.get("level") or 1)
    min_lv = int(getattr(_TP, "TRIAL_MIN_LV", 70) or 70)
    max_floor = int(getattr(_TP, "TRIAL_MAX_FLOOR", 30) or 30)
    daily_limit = int(getattr(_TP, "TRIAL_DAILY_LIMIT", 3) or 3)
    if lv < min_lv:
        return [_T.text("tower.lock_lv", need_lv=min_lv, need_lv_2=min_lv)]
    shell = _shell(env)
    if shell is not None and shell._in_any_battle(group_id, qq_id):
        return [_T.static("tower.in_battle")]
    st = _TP._tower_state(qq_id)
    today_cleared = [int(x) for x in (st.get("cleared_today") or [])]
    cur = int(st.get("cur") or 0)
    max_reached = cur
    # 『爬塔』默认目标：已突破最高层的下一层（线性推进；每日最多 3 个新层）
    raw_arg = env.arg_text("爬塔")               # = 旧 `self._strip_cmd(event, "爬塔")`
    if raw_arg.isdigit():
        floor = int(raw_arg)
        if floor < 1 or floor > max_floor:
            return [_T.text("tower.bad_floor", max_floor=max_floor, floor=floor, max_floor_2=max_floor)]
        if floor != max_reached + 1:
            return [_T.text("tower.locked", floor=floor, next_floor=max_reached + 1)]
    else:
        if max_reached >= max_floor:
            return [_T.static("tower.top")]
        floor = max_reached + 1
    # 每日上限：今日已通 >=3 → 拦截新层（已通层同层不可重刷：进度线性、防刷经验）
    if len(today_cleared) >= daily_limit:
        return [_T.text("tower.daily_limit", done_n=len(today_cleared), limit=daily_limit, cur=cur,
                    next_floor=cur + 1)]
    if floor in today_cleared:
        return [_T.text("tower.already_today", floor=floor, next_floor=max_reached + 1)]
    fd = _TP._floor_def(floor)
    if not fd:
        return [_T.static("tower.no_floor")]
    from .drops import build_monster as _build_monster   # B2-C2 包内直取（原宿主句柄；调用时解析）
    guard = _TP.build_tower_guard(floor, _build_monster)
    guard_name = guard.get("name", "塔卫")
    # 开战装配 = 宿主能力（本线不搬）：返回「插入到第 4 行后的阵型面板串」，无 → None
    open_battle = getattr(shell, "_open_tower_battle", None) if shell is not None else None
    panel_str = open_battle(group_id, qq_id, player, guard) if open_battle else None
    return [_tower_start({
        "fl_name": (fd.get("name") or f"第{floor}层"),
        "floor": floor,
        "guard_name": guard_name,
        "guard_lv": guard.get("lv"),
        "suggest_lv": fd.get("lv"),
        "desc": (fd.get("desc") or ""),
        "reward_exp": int(fd.get("reward_exp") or 0),
        "reward_gold": int(fd.get("reward_gold") or 0),
        "panel": panel_str,
    })]
