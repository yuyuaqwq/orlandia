# -*- coding: utf-8 -*-
"""机制声明表的**装配与执行壳**（P2 试点 · 2026-09-24）。

形状在引擎 `saintess_engine.acts`（动词注册表 + 按序执行 + 装配期 fail-closed）；
本模块只做**这款游戏**的三件事：

  ① **ctx 形状**：`{"battle", "caster", "target", "params", "logs"}` —— 声明里的
     `field` 步链就按这个取（`{"field": [{"key": "params"}, {"key": "pool_pct"}]}`）。
  ② **动词注册**：各域自己的动词写在 `seq_verbs_<域>.py` 并注册进 `ACTS`
     （引擎侧不认识任何动词名 —— 名词表是内容）。
  ③ **表 + 编译**：`content/rules/mech_seq_<域>.json` → 装配期整表编译（任一条不合法即抛，
     不留到运行期）。

**触发点不变**：动作仍以原注册名（`@register_action("…")`）被 `fire()` 分发；本模块只把
「拿到 params 之后做什么」从函数体换成声明表 + 动词。

**执行口径**（与引擎形状一致）：`when` 为假 ⇒ 不执行、返回空列表；动词异常原样上抛
（外层 `apply_effects` 的既有吞异常行为不变 ⇒ 对玩家可见行为逐字节等价）。
"""
from __future__ import annotations

import io
import json
import os

from saintess_engine.acts import Acts, Plan, SpecError, UnknownVerb      # noqa: F401 转出

__all__ = ["ACTS", "PLANS", "ctx_of", "run", "load_plans", "TABLES"]

# 动词表（各域模块往里注册；对象共享 ⇒ 后续就地补动词即刻生效）
ACTS = Acts()

# 已编译的计划表：`动作注册名 → Plan`
PLANS: dict = {}

# 本批试点用到的表（域 → content/rules/<名>.json）
TABLES = ("mech_seq_weapon", "mech_seq_class")

# 域动词模块（装配期导入一次 ⇒ 触发注册）
_VERB_MODULES = ("seq_verbs_weapon", "seq_verbs_class")


def _content_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))    # …/content


def rules_dir() -> str:
    """`content/rules/`（表所在目录）。"""
    return os.path.join(_content_dir(), "rules")


def ctx_of(battle, caster, target, params, logs) -> dict:
    """把 `fire()` 给的那套实参收成 ctx（形状契约，见模块头注）。"""
    return {"battle": battle, "caster": caster, "target": target,
            "params": params, "logs": logs}


def run(action: str, battle, caster, target, params, logs) -> list:
    """执行 `action` 的声明序列；**未装配的动作当场 `KeyError`**（不静默跳过）。"""
    plan = PLANS[action]
    return plan.run(ctx_of(battle, caster, target, params, logs))


def load_plans(tables=None) -> dict:
    """装配期：先导入域动词模块（触发注册），再逐表编译。

    * 缺表文件 ⇒ 跳过（本批可以只装一半）
    * 任一条不合法（形状 / 未登记动词 / 节点编译失败）⇒ **整表不装**、异常上抛
    * 已编译的动作名重复 ⇒ 后者覆盖（与 `PLANS` 就地更新一致）
    """
    for mod in _VERB_MODULES:
        __import__(__name__.rsplit(".", 1)[0] + "." + mod, fromlist=["_"])
    out: dict = {}
    for name in (tables or TABLES):
        path = os.path.join(rules_dir(), name + ".json")
        if not os.path.exists(path):
            continue
        with io.open(path, encoding="utf-8") as fh:
            table = json.load(fh)
        out.update(ACTS.compile_table(table))
    PLANS.clear()
    PLANS.update(out)
    return out
