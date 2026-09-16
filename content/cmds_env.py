# -*- coding: utf-8 -*-
"""包侧**宿主取件适配**单点（`content/cmds_env.py`）—— 命令层与宿主之间的**一处**接口。

为什么收在一处
--------------
命令处理器不能 import 宿主（I2 铁律），宿主面（壳对象 / 平台事件 / 权限判定 …）只能经
引擎注入的 `Env` 取。原先 10 个 `cmds_*.py` 各写一份 `_shell`，`_Say` / `_event` /
`_messages` 也各抄一遍（同形不同源 = 迟早分叉）。现在只有本模块知道「宿主面藏在哪」：

    shell(env)      宿主壳对象（桥接层经 `env.state["shell"]` 注入）—— 包内取宿主面的唯一口
    shell_state(sh) 宿主壳对象 → `Env.state` 注入字典（**「键名 = shell」的唯一出处**）
    event(env)      实现体看到的「平台事件」= 引擎 `TextSink`（`plain_result` 收成一行）
    messages(agen)  async generator → `list[str]`（每条 = 一次 `yield` = 一条消息）

`event` / `messages` 只是引擎通用驱动件的包内再导出（`saintess_engine.command`）——
**通用归引擎、内容归包**：`TextSink`（文本收集替身）与 async generator 的收集循环是平台无关形状，
住在引擎；「壳对象从哪个键取」是本包的取件约定，住在这里。

声明式绑定（`content/data/commands.json` 的 `bind`）与本模块的分工
----------------------------------------------------------------
`bind` 只点名「实现体 + 调用模式 + 取参槽位」，调用帧是 ``handler(*lead(env), sink, *args)``；
`lead` 就是本模块的 `shell`（`content/commands.py::_bind_lead`），`sink` 由引擎按模式造。
"""
from __future__ import annotations

from saintess_engine.command import TextSink, collect_messages

__all__ = ["shell", "shell_state", "event", "messages"]


def shell(env):
    """宿主壳对象（桥接层经 `env.state["shell"]` 注入）——包内取宿主面的**唯一**口。"""
    return (env.state or {}).get("shell")


def shell_state(shell) -> dict:
    """宿主壳对象 → `Env.state` 注入字典（**「宿主面藏在哪个键」的唯一出处**）。

    生产者一侧（包内旧通道适配器 `content/cmds_base_rules.py::_LegacyShellEnv`）也走这里，
    于是「键名 = `shell`」在全包只有本模块写死过一次。
    """
    return {"shell": shell}


def event(env):
    """实现体看到的「平台事件」= **文本收集替身**（`plain_result` 落文本；其余代理真事件）。"""
    return TextSink(env.raw)


async def messages(agen) -> list:
    """async generator → `list[str]`（**每条 = 一次 `yield`** = 一条消息）。"""
    return await collect_messages(agen)
