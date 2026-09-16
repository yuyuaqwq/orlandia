# -*- coding: utf-8 -*-
"""包内战斗族命令（`content/cmds_combat.py`）—— 战斗域的**守卫声明 / 取参 / 回话组装**。

本模块现在只剩 7 条**真取参**命令
--------------------------------
`wish` / `attack` / `skill` / `honor_shop` / `battle_prefs_form` / `battle_prefs_finisher` /
`battle_prefs_arcane_field` —— 它们各自还要从**本条消息原文**里再切一段参数出来
（`env.arg_text(<命令词>)` / `text.split(<分参词>, 1)[1]`），不是「取参 + 调实现体」能表达的。

其余 8 条（`explore` / `wild_king_chest` / `trader_confirm` / `revive_confirm` / `defend` /
`flee` / `hunt_boss` / `battle_prefs_view`）由**声明式绑定**接管：
`content/data/commands.json` 的 `bind` 点名实现体（`content.combat_cmds:<名>`）+ 调用模式
（`messages`）+ 取参槽位。本地助手 `_shell` / `_Say` / `_event` / `_messages` 已删 ——
宿主取件口在 `content/cmds_env.py`，驱动/文本收集替身在引擎 `saintess_engine.command.binding`。

为什么本族走 `messages`（逐段回话）而不是 `run`
----------------------------------------------
实现体（`content/combat_cmds.py`，逐字搬包）是 **async generator**：
`async for _r in self._instance_router(...)` / `await self._broadcast(...)` —— 真的要 await，
不能用同步驱动。宿主侧 `_host_bridge.run_async` **逐段回话**（一条 = 一条消息），
**不做 `"\\n".join` 合并**，对齐改造前 `async for _r in _CC.<cmd>(...): yield _r` 的逐条语义
（含分支/异常提示行序）。

I2（包内不 import 宿主）
-----------------------
宿主面一律经注入句柄：`content/cmds_env.py::shell(env)` = 宿主壳对象。
实现体 `content/combat_cmds.py` 本来就把 `self` 当宿主取件口用 —— 本模块只把它从 `env` 取出来
传下去，**不改实现体的任何调用点**。
"""
from __future__ import annotations

from . import combat_cmds as _CC
from .cmds_env import event as _event, messages as _messages, shell as _shell
from .commands import bind


# ============================================================
# 取件口（env → 改造前命令体的实参）
# ============================================================
def _message_text(env) -> str:
    """本条消息原文（已 strip）= 改造前 `(event.get_message_str() or "").strip()`。"""
    return str(env.text or "")


# ============================================================
# 冒险族（许愿 / 荣誉兑换）+ 战斗族（攻击 / 技能）
# ============================================================
@bind("wish", guards=("hook:player",), params=("cmd=许愿",))
async def wish(env):
    """『许愿 [类型]』（旧宿主体：`opt = self._strip_cmd(event, "许愿").strip()`）。"""
    opt = env.arg_text("许愿")
    return await _messages(_CC.wish(_shell(env), _event(env),
                                    env.group_id, env.uid, env.player, opt))


# ============================================================
# 战斗族
# ============================================================
@bind("attack", guards=("hook:player",), params=("cmd=攻击",))
async def attack(env):
    """『攻击 [目标]』（旧宿主体：`target_arg = self._strip_cmd(event, "攻击").strip()`）。"""
    target_arg = env.arg_text("攻击")
    return await _messages(_CC.attack(_shell(env), _event(env),
                                      env.group_id, env.uid, env.player, target_arg))


@bind("skill", guards=("hook:player",), params=("cmd=技能",))
async def skill(env):
    """『技能 <名称/槽位> [目标]』（旧宿主体：`skill_name = self._strip_cmd(event, "技能")`）。"""
    skill_name = env.arg_text("技能")
    return await _messages(_CC.skill(_shell(env), _event(env),
                                     env.group_id, env.uid, env.player, skill_name))


@bind("honor_shop", guards=("hook:player",), params=("cmd=荣誉",))
async def honor_shop(env):
    """『荣誉 [兑换 <编号>]』（旧宿主体：`raw = self._strip_cmd(event, "荣誉").strip()`）。"""
    raw = env.arg_text("荣誉")
    return await _messages(_CC.honor_shop(_shell(env), _event(env),
                                          env.group_id, env.uid, env.player, raw))


# ============================================================
# v139 战前指令（双形态预设 / 终结阈值 / 奥术力场 / 查看）
# ============================================================
@bind("battle_prefs_form", guards=("hook:player",), params=("cmd=战前形态",))
async def battle_prefs_form(env):
    """『战前形态 [值]』（旧宿主体：`text.split("战前形态", 1)[1].strip()`，非该词 → ""）。"""
    text = _message_text(env)
    arg = text.split("战前形态", 1)[1].strip() if "战前形态" in text else ""
    return await _messages(_CC.battle_prefs_form(_shell(env), _event(env),
                                                 env.group_id, env.uid, env.player, arg))


@bind("battle_prefs_finisher", guards=("hook:player",), params=("cmd=战前阈值",))
async def battle_prefs_finisher(env):
    """『战前阈值 [值]』（旧宿主体：`text.split("战前阈值", 1)[1].strip()`，非该词 → ""）。"""
    text = _message_text(env)
    arg = text.split("战前阈值", 1)[1].strip() if "战前阈值" in text else ""
    return await _messages(_CC.battle_prefs_finisher(_shell(env), _event(env),
                                                     env.group_id, env.uid, env.player, arg))


@bind("battle_prefs_arcane_field", guards=("hook:player",), params=("cmd=战前力场",))
async def battle_prefs_arcane_field(env):
    """『战前力场 [盾/刃]』（旧宿主体：`text.split("战前力场", 1)[1].strip()`，非该词 → ""）。"""
    text = _message_text(env)
    arg = text.split("战前力场", 1)[1].strip() if "战前力场" in text else ""
    return await _messages(_CC.battle_prefs_arcane_field(_shell(env), _event(env),
                                                         env.group_id, env.uid, env.player, arg))
