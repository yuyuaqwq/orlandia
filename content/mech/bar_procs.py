# -*- coding: utf-8 -*-
"""《奥兰迪亚》敌身条族**装配器** —— bar_procs（P4-D2 搬运物；U1-I1 动词上移引擎）。

★ U1-I1（本次）：本族 4 个战斗动词 + 5 个模块级助手已**整块搬进引擎**
`saintess_engine/gauge/actions.py`（注册名不变：`bar_gain` / `bar_time_settle` /
`bar_phase_preserve` / `passive_reflect_bar`；`import saintess_engine` 即完成注册）。
本文件**只剩装配**：扫 actor 已学技能 → 命中 `BAR_INJECT_FIELDS` 字段则挂 `skill_hit` 注入。
**不留转发壳、不再导出同名动词** —— 引擎那份是唯一实现。

真源（搬运前身）：游戏仓 `C:/Users/yuyu/qqbot/data/plugins/dragonfall/game/services/battle_bar_procs.py`
      **`:203-244 apply_bar_procs`**（真源共 244 行）。本文件 = 该片段的逐字拷贝
      （函数体、数值、注释、文案一字未改；唯一改动 = 2 处 import 路径，见函数上方注）。

本族参数表
----------
· `BAR_INJECT_FIELDS`（技能字段 → bar key；真源 `game/data/battle_rules.py:742-744`）
  → 包内 `content/mech/element_data.py`（本批数据文件；**装配层读，引擎动词不读**）。
· `BAR_STATE_PREFIX`（真源 `:749`）**不在本文件重复** —— 包内已有同一张表
  （`content/mech/params.py:123`，同名同值 `"bar:"`；引擎经 `config.bar_prefix()` 取）。
· 条数值/阈值/衰减 = `MECH_CFG["enemy_bar"]`（`content/mech/class_data.py` 单源，切片已含 shaken）。
"""
from __future__ import annotations


# ============================================================
# 装配入口（P4-D2b 追加：真源 `battle_bar_procs.py:203-244 apply_bar_procs`）
#   逐字搬运，唯一改动 = 2 处 import 路径（其余函数体/数值/注释/文案一字未改）：
#     · 真源 `from ..data.battle_rules import BAR_INJECT_FIELDS`
#       → 包内 `from .element_data import BAR_INJECT_FIELDS`（同值同表；本族参数表宿主）
#     · 真源 `from ..content_rules.skills import skill_info`
#       → 包内 `from ..apply import _SKILL_LOOKUP as _PKG_SKILLS` +
#         `skill_info = _PKG_SKILLS.skill_info`
#       （包内没有 `content_rules/` 命名空间；技能表权威实现 = `content/apply.py:_SkillTable` 时代
#         已归 `content/skills.py`，`skill_info(class_name, skill_key)` 与游戏仓
#         `game/content_rules/skills.py:104` 同形，且同为**惰性 import**
#         （留在函数体内，不与 apply.py 形成导入环）。
# ★ U1-I1：动词块（原 `:38-202` 5 助手 + 4 动作）已整块上移引擎
#   `saintess_engine/gauge/actions.py`；本块**函数体一字未动**。
# ============================================================
def apply_bar_procs(actor: dict) -> None:
    """装配：扫 actor 已学技能 → 命中 BAR_INJECT_FIELDS 字段则挂 skill_hit 注入。

    学什么挂什么，零噪音（未学推条技能的单位不挂，不产生空转触发器）。

    ⚠️ 顺序契约：注入条目 **insert(0)** 排 skill_hit 首位——被动族同一事件的后置段
    （如破绽·极 passive_bar_extend 延长免疫窗口）依赖「本次命中先推条并触发」，
    排在注入之后才能读到触发后的免疫状态（旧 battle.py `_skill_hit_settle` 同序）。
    """
    cn = actor.get("class_name") or ""
    names = actor.get("learned_skills") or []
    if not cn or not names:
        return
    try:
        from .element_data import BAR_INJECT_FIELDS
    except Exception:
        return
    from ..apply import _SKILL_LOOKUP as _PKG_SKILLS
    skill_info = _PKG_SKILLS.skill_info
    trig = actor.setdefault("triggers", {})
    for field, spec in (BAR_INJECT_FIELDS or {}).items():
        key = (spec or {}).get("key") if isinstance(spec, dict) else ""
        if not key:
            continue
        per_hit = bool((spec or {}).get("per_hit")) if isinstance(spec, dict) else False
        found = False
        for s in names:
            try:
                info = skill_info(cn, s)
            except Exception:
                info = None
            if info and info.get(field):
                found = True
                break
        if not found:
            continue
        lst = trig.setdefault("skill_hit", [])
        if not any(isinstance(e, dict) and e.get("action") == "bar_gain"
                   and e.get("key") == key for e in lst):
            entry = {"action": "bar_gain", "key": key, "field": field}
            if per_hit:
                entry["per_hit"] = True
            lst.insert(0, entry)


__all__ = ["apply_bar_procs"]
