# -*- coding: utf-8 -*-
"""U1-D2 冻结比对**门禁③**（触发器主四件）：`equip.py` · `food_proc.py` · `team_procs.py` ·
`worldboss.py` 共 **12 段** —— 手写判重 + 手写追加 → 引擎 `battle/declarations` 声明编译器。

跑法（工作区根；环境变量见 `BRIEF.md` §4）::

    PY="C:/Users/yuyu/AppData/Roaming/uv/tools/astrbot/Scripts/python.exe"
    "$PY" work/pkg/tests/_u1d2_triggers_gen.py --check
    "$PY" work/pkg/tests/test_u1d2_triggers_frozen.py

判据（`design/U1-D2_BATCHES.md` §6 判据表 1–10；本文件逐条打原始输出）
----------------------------------------------------------------------
 [1] **12 段冻结文本 sha256 全等 `_PIN["frozen"]`** + **活实现 `inspect.getsource` sha256
     全等 `_PIN["live"]`**；`phase == "landed"` 时再断言 E 栏 `frozen == live`、C 栏
     `frozen != live`（§2.3）。
 [2] **全量网格**：82 武器 × 26 事件 + 76 词条 × 26 + 93 传说 × 26 + 19 食物 × 26 = **7,020 格**
     （旧实现 = `base/pkg` 切片 `exec` 出来的那一份，逐桶逐条比）；旧名映射 (12+5) 键 × 2
     文件 = **34 格**（映射目标 ∈ `EVENTS`；合计 **7,054 格** = 作业书标题口径）。另跑一遍
     `FROZEN_GATE.md` §5.3 的加细口径 (12+5) × 26 事件 × 2 = **884 格**作加强网格。
 [3] **幂等矩阵**：4 挂载入口 × 重复 {1,2,3} × 2 actor 态 = **24 格**（`equip` 非幂等单列）。
 [4] `apply_gm_dmg_mult` 返回 `bool` 语义逐字：挂上 `True` / 倍率=1.0 不挂 `False` /
     已挂且改回 1.0 → **撤回 + `False`**。
 [5] `_owner` 注入：`food_proc` 挂载期注入 + `fire()` 兜底注入；两条路径读 `params["_owner"]`
     得**同一对象**。
 [6] `equip` 的 `_EVENT_MAP` / `_UNKNOWN_EVENTS` / `_known_engine_events` 三名字仍在且语义不变
     （AST + 直取）。
 [7] 口径分歧 8 条各 ≥1 条断言（C 块 §6）。
 [8] 有牙反证 3 处（`key_of` 恒 None → 幂等失效 / `merge` 恒 append → 前插序丢 /
     事件名校验改抛异常 → 装配中断）→ 对应探针**必须变红**（逐处打印预期/实测）。
 [9] 只读断言：4 个源文件 + 4 张数据表 sha256 前后一致（全程零写盘）。
 [10] `apply_game_content` 六步顺序与幂等保险丝 `_content_applied` 未变（AST 逐条）。

⚠ 「旧实现」= `_FROZEN_TEXT` 里的**成品字面量**（由 `tests/_u1d2_triggers_gen.py` 从
   `base/pkg/**` 逐行 `ast` 切片），`exec` 到独立命名空间跑 —— 不是「读代码觉得等价」。
⚠ 刻意**不依赖 pytest**：直接 `python <本文件>`，`sys.exit(1 if FAIL else 0)`。
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import sys
import tempfile
import types

# ══════════════════════════════════════════════════════════════════════════════
# 0. 装配：包根 / 引擎根 / 宿主壳根 + 独立私有库 + shim_astrbot
# ══════════════════════════════════════════════════════════════════════════════
_HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(_HERE)
WORK_ROOT = os.path.dirname(PKG_ROOT)
LANE_ROOT = os.path.dirname(WORK_ROOT)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ★ 独立私有库（绝不碰生产 game_data.db）
# 2026-09-18 收尾修：原落点 `LANE_ROOT/out` 是旧「工作区布局」（`<lane>/work/pkg` 三层），
#   真仓布局下 LANE_ROOT = `C:\Users` ⇒ `C:\Users\out` 不存在 → sqlite connect 直接
#   `unable to open database file`（单跑必崩；改前基线同样红，非本次修复引入）。
#   私有库改落系统临时目录下自建子目录（不写包目录、不进 git）。
_DB_DIR = os.path.join(tempfile.gettempdir(), "gwen_test_u1d2_L6")
os.makedirs(_DB_DIR, exist_ok=True)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_DB_DIR, "test_u1d2_L6.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
os.environ.setdefault("GWEN_FRAMEWORK_DIR", os.path.join(LANE_ROOT, "work", "eng"))
os.environ.setdefault("GWEN_HOST_DIR", os.path.join(LANE_ROOT, "work", "host"))
_shim = os.path.join(_HERE, "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

import logging                                                          # noqa: E402

import _paths                                                           # noqa: E402,F401
import _engine_harness as H                                             # noqa: E402,F401

# 门禁只看「装配行为」：告警文本会刷屏（equip 的未知名告警 / 传说未实装告警）→ 静音。
# 静音**不改行为**：`_UNKNOWN_EVENTS` / `_UNSUPPORTED_LEGENDARY` 的去重追加照常发生。
logging.disable(logging.WARNING)

from content.mech import equip as EQ                                    # noqa: E402
from content.mech import food_proc as FP                                # noqa: E402
from content.mech import team_procs as TP                               # noqa: E402
from content.mech import worldboss as WB                                # noqa: E402
from saintess_engine.battle.declarations import Compiler, Declaration   # noqa: E402
from saintess_engine.battle.effects import register_action              # noqa: E402
from saintess_engine.battle.effect_triggers import EVENTS as EV, fire   # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pkg_file(relpath):
    return os.path.join(PKG_ROOT, *relpath.split("/"))


def _file_sha(relpath):
    with open(_pkg_file(relpath), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


READONLY_FILES = (
    "content/mech/equip.py", "content/mech/food_proc.py",
    "content/mech/team_procs.py", "content/mech/worldboss.py",
    "content/mech/we_data.py", "content/data/affixes.json",
    "content/data/legendary_effects.json", "content/data/food_effects.json",
)

# >>> _u1d2_triggers_gen (auto) >>>

# ⚠ 本块由 `tests/_u1d2_triggers_gen.py` 生成 —— 手工改动 = 门禁失去安全网。
# 冻结侧读 `base/pkg/**`（改动前基线）；`_PIN["live"]` 由 --emit-live 重生成。

_FROZEN_TEXT = {
    'content/mech/equip.py::_known_engine_events': 'def _known_engine_events() -> frozenset:\n    """引擎事件全集；**取不到就返回空集 = 不告警**（告警本身不允许成为新的故障点）。"""\n    try:\n        from saintess_engine.battle.effect_triggers import EVENTS as _E\n        return frozenset(_E)\n    except Exception:      # noqa: BLE001\n        return frozenset()\n',
    'content/mech/equip.py::map_event': 'def map_event(old_ev: str) -> tuple:\n    """旧事件 → saintess_engine 事件展开；不在表 = 假定已是 saintess_engine 原生事件名，同名直通\n    （dmg_calc/taken_calc/battle_start 等装配层可直接用 saintess_engine 事件名）。\n\n    ★ 2026-09-13 反静默失效：直通的名字若不在引擎 EVENTS 全集里，`fire()` 会静默忽略 →\n    触发器永不生效且无痕迹。此处**只告警不改行为**（仍直通返回，语义与改造前逐字一致），\n    未知名去重缓存（装配器每场战斗都装，不去重会刷屏）。\n    """\n    got = _EVENT_MAP.get(old_ev)\n    if got is not None:\n        return got\n    _known = _known_engine_events()\n    if _known and old_ev not in _known and old_ev not in _UNKNOWN_EVENTS:\n        _UNKNOWN_EVENTS.append(old_ev)\n        logging.getLogger(__name__).warning(\n            "装配层事件名 %r 不在引擎事件全集里（fire 会静默忽略 → 该触发器永不生效）", old_ev)\n    return (old_ev,)\n',
    'content/mech/equip.py::weapon_triggers': 'def weapon_triggers(actor: dict) -> dict:\n    """actor 全部已装备武器特效 → {saintess_engine事件: [效果 dict]}。\n\n    内部先把 key 翻译成 {old_event: [效果]}，再把 old_event 映射展开到\n    saintess_engine 事件（hit → attack_hit + skill_hit 双事件注册）。\n    """\n    out: dict = {}\n    for key in equipped_weapon_keys(actor):\n        raw = triggers_for_key(key, actor)\n        if not raw:\n            continue  # 未支持 key：静默跳过（范围外）\n        for old_ev, effs in raw.items():\n            for b2_ev in map_event(old_ev):\n                out.setdefault(b2_ev, []).extend(list(effs))\n    return out\n',
    'content/mech/equip.py::affix_triggers': 'def affix_triggers(actor: dict) -> dict:\n    """actor 全部已装备词条（事件型）→ {saintess_engine事件: [效果 dict]}。\n\n    - stat 型词条（生成时已折算进 item.stats）不产生 triggers（面板自动含）\n    - 事件型走翻译器 + 事件映射展开（hit → attack_hit + skill_hit）\n    - 资源型：R4 已装事件 gain 型 10 + boiling_blood；上限型 max_bonus 走\n      _apply_bonus_domains（actor.bonus cap/cost 分域容器，非事件——apply_to_actor 第\n      0 步；面板外部增幅 bonus.panel 由开战仪式播种，装配不动）；\n      m_affixtail 已装 regen 型 2（energy_tide/swift_tailwind turn_start 回能）+\n      purify（命中驱散）；D3 已装 3 条事件型词条（combo_recover/combo_ward/ember_brand\n      ——取舍见 overnight/d3-gap-fix.md）；其余 cond 修正型/职业机制词条翻译器未注册\n      → 静默跳过（缺口清单见模块头注释与 affixes.py）\n    """\n    out: dict = {}\n    for aid in equipped_affix_ids(actor):\n        raw = affix_triggers_for_key(aid, actor)\n        if not raw:\n            continue\n        for old_ev, effs in raw.items():\n            for b2_ev in map_event(old_ev):\n                out.setdefault(b2_ev, []).extend(list(effs))\n    return out\n',
    'content/mech/equip.py::apply_to_actor': 'def apply_to_actor(actor: dict) -> None:\n    """把装备特效+词条装配进 actor（幂等；命令层开战前调用）：\n    0. bonus 容器分域（v181.M-bonus：cap 上限词条 max_bonus → bonus.cap；\n       cost 消耗修正词条 energy_blade/arcane_focus/sigil_blessing → bonus.cost；\n       panel 外部增幅由开战仪式播种，此处不动）\n    1. 事件型效果 → actor["triggers"]（武器特效 + 词条事件型 + 传说专属特效合并）\n    2. 被动常驻型（proc_heal amp：受疗增幅）→ actor.state.heal_amp_pct（landing 折算）"""\n    if not actor:\n        return\n    install_ext_actions()\n    # 0) bonus 容器（cap/cost——先于渠道装配；覆盖写幂等，卸装后重装配回落）\n    try:\n        _apply_bonus_domains(actor)\n    except Exception:\n        pass  # 词条 bonus 装配异常不阻断其余（容错铁律）\n    # 1) 事件型（武器特效 + affix 词条 + 传说专属特效）\n    merged = weapon_triggers(actor)\n    try:\n        _afx = affix_triggers(actor)\n        for ev, effs in _afx.items():\n            merged.setdefault(ev, []).extend(effs)\n    except Exception:\n        pass  # 词条装配异常不阻断武器装配（容错）\n    try:\n        _leg = legendary_triggers(actor)\n        for ev, effs in _leg.items():\n            merged.setdefault(ev, []).extend(effs)\n    except Exception:\n        pass  # 传说专属装配异常不阻断其余（容错铁律）\n    tr = actor.setdefault("triggers", {})\n    for ev, effs in merged.items():\n        tr.setdefault(ev, []).extend(effs)\n    # 2) 被动常驻：heal amp（vital_band 等 proc_heal amp 4 key）→ effects["heal_amp_pct"] 条目\n    amp = 0.0\n    for key in equipped_weapon_keys(actor):\n        wd = _we_config(key, actor)\n        if (wd.get("family") == "proc_heal" and wd.get("heal_pct") is not None\n                and key in _HEAL_AMP_KEYS):\n            pct = float(wd.get("heal_pct") or 0)\n            if pct > 0:\n                amp = 1.0 - (1.0 - amp) * (1.0 - pct)  # 多件叠乘转加和\n    if amp > 0:\n        ef = actor.setdefault("effects", {})\n        entry = ef.get("heal_amp_pct")\n        if not isinstance(entry, dict):\n            entry = ef["heal_amp_pct"] = {}\n        cur_v = float((entry.get("value") or {}).get("amp", 0) or 0)\n        entry.setdefault("value", {})["amp"] = max(cur_v, amp)\n',
    'content/mech/food_proc.py::_map_event': 'def _map_event(old_ev: str) -> tuple:\n    """旧事件 → saintess_engine 事件；不在表 = 同名直通。"""\n    return _EVENT_MAP.get(old_ev, (old_ev,))\n',
    'content/mech/food_proc.py::food_trigger_decls': 'def food_trigger_decls(aid: str) -> dict:\n    """food aid → {old_event: [效果 dict]}；未知 aid → {}（防拼写漂移静默）。\n\n    声明全部复用 we_* 扩展动作（与 affix 词条同执行器）；参数带数值（读\n    FOOD_EFFECT_PARAMS），owner 由挂载函数注入。mode 语义对齐 equip_proc\n    同名词条翻译器（bleed/armor_break/element_*/combo/charge/pierce/counter/\n    execute 均已迁 affix 管线，此处只换数据源为 food 表）。\n    """\n    if aid == "lifesteal":\n        # 蛇羹：每次攻击回复伤害 8% 生命（we_extra_dmg lifesteal 分支 food_lifesteal 别名）\n        return {"hit": [{"type": "we_extra_dmg", "key": "food_lifesteal",\n                         "heal_pct": float(_fp("lifesteal", "pct", 0.08))}]}\n    if aid == "bleed":\n        # 烬火辣椒：20% 使目标流血（affix_bleed 声明 cap3 每刻5% 3刻——复用词条 DOT key）\n        return {"hit": [{"type": "we_affix_dot", "key": "food_bleed",\n                         "state_key": "affix_bleed",\n                         "chance": _chance_pct("bleed", "chance", 0.20),\n                         "stacks": int(_fp("bleed", "stacks", 3))}]}\n    if aid == "armor_break":\n        # 蘑菇汤：25% 降低目标防御 15%（2 刻）\n        return {"hit": [{"type": "we_affix_defdown", "key": "food_armor_break",\n                         "chance": _chance_pct("armor_break", "chance", 0.25),\n                         "pct": float(_fp("armor_break", "pct", 0.15)),\n                         "turns": int(_fp("armor_break", "turns", 2))}]}\n    if aid == "combo":\n        # 鹰蛋：15% 追加一次 50% 伤害（本击 dmg × pct）\n        return {"hit": [{"type": "we_affix_bonus", "key": "food_combo",\n                         "mode": "dmg_pct",\n                         "chance": _chance_pct("combo", "chance", 0.15),\n                         "pct": float(_fp("combo", "pct", 0.50)),\n                         "tag": "⚡", "name": "连击"}]}\n    if aid == "charge":\n        # 皇家烤肉：10% 追加 50% 伤害\n        return {"hit": [{"type": "we_affix_bonus", "key": "food_charge",\n                         "mode": "dmg_pct",\n                         "chance": _chance_pct("charge", "chance", 0.10),\n                         "pct": float(_fp("charge", "pct", 0.50)),\n                         "tag": "💪", "name": "蓄力爆发"}]}\n    if aid == "element_fire":\n        # 灰烬烤饼：攻击附加 5% 火属性伤害\n        return {"hit": [{"type": "we_affix_element", "key": "food_element_fire",\n                         "element": "fire", "pct": float(_fp("element_fire", "pct", 0.05)),\n                         "name": "火焰附加"}]}\n    if aid == "element_ice":\n        # 冰霜浆果：攻击附加 5% 冰属性伤害 + 减速\n        return {"hit": [{"type": "we_affix_element", "key": "food_element_ice",\n                         "element": "ice", "pct": float(_fp("element_ice", "pct", 0.05)),\n                         "name": "冰霜附加",\n                         "slow": float(_fp("element_ice", "slow", 0.10)),\n                         "slow_turns": int(_fp("element_ice", "slow_turns", 2))}]}\n    if aid == "pierce":\n        # 雪狼肉排：20% 无视防御追加伤害（60% 攻击）\n        return {"hit": [{"type": "we_affix_bonus", "key": "food_pierce",\n                         "mode": "atk_true",\n                         "chance": _chance_pct("pierce", "chance", 0.20),\n                         "atk_pct": float(_fp("pierce", "atk_pct", 0.60)),\n                         "tag": "🏹", "name": "贯穿"}]}\n    if aid == "static":\n        # 雷雨藤烤串：静电麻痹——攻击 20% 令敌方减速（2 刻，速度减半对齐旧 SPD_DOWN_MULT）\n        return {"hit": [{"type": "we_hit_slow", "key": "food_static",\n                         "chance": _chance_pct("static", "chance", 0.20),\n                         "slow": float(_fp("static", "slow_pct", 0.5)),\n                         "turns": int(_fp("static", "turns", 2))}]}\n    if aid == "aurora_guard":\n        # 极光花蜜：极光庇护——受击伤害 -15%（taken_calc 乘区，恒生效）\n        return {"taken_calc": [{"type": "we_taken_mult_cond", "key": "food_aurora_guard",\n                                "cond": "always",\n                                "mult": 1.0 - float(_fp("aurora_guard", "pct", 0.15))}]}\n    if aid == "counter":\n        # 狼肉干：20% 反击 60% 伤害（受击时，攻击方在 ctx.source）\n        return {"taken": [{"type": "we_affix_counter", "key": "food_counter",\n                           "chance": _chance_pct("counter", "chance", 0.20),\n                           "atk_pct": float(_fp("counter", "atk_pct", 0.60))}]}\n    if aid == "thorns":\n        # 鹿奶干酪：10% 反弹 30% 伤害（基于原始 dmg）\n        return {"taken": [{"type": "we_reflect", "key": "food_thorns",\n                           "chance": _chance_pct("thorns", "chance", 0.10),\n                           "reflect_pct": float(_fp("thorns", "pct", 0.30))}]}\n    if aid == "execute":\n        # 海盗炖鱼：<30% ×1.3（dmg_calc 乘区）\n        return {"dmg_calc": [{"type": "we_dmg_mult_cond", "key": "food_execute",\n                              "cond": "hp_target_lt",\n                              "threshold": float(_fp("execute", "hp_ratio", 0.30)),\n                              "mult": float(_fp("execute", "mult", 1.30)),\n                              "tag": "💀处决"}]}\n    if aid == "precise":\n        # 海鲜浓汤：本场 +10%（dmg_calc 乘区）\n        return {"dmg_calc": [{"type": "we_dmg_mult_cond", "key": "food_precise",\n                              "cond": "always",\n                              "mult": float(_fp("precise", "mult", 1.10)),\n                              "tag": "🎯精准"}]}\n    if aid == "dragon_tongue":\n        # 龙蛋煎饼：攻击叠龙语印记（effects["dragon_mark"] 层，每层 +2% 伤害上限 5）。\n        # 叠层走引擎原生 apply op=add（cap 查 EFFECT_RULES.dragon_mark）；\n        # 乘区 = stat_scale.dmg_mult 通用通道（同 rage）→ stats 折算 _state_dmg_mult\n        # → actions 伤害乘区自动消费，无需扩展动作。\n        return {"hit": [{"type": "apply", "key": "dragon_mark", "op": "add",\n                         "amount": 1, "on": "caster"}]}\n    # 未知/未迁 aid → 空（静默跳过；shield 特判在 battle_item_use 独立处理）\n    return {}\n',
    'content/mech/food_proc.py::food_period_decl': 'def food_period_decl(aid: str) -> Optional[dict]:\n    """周期恢复类 → effects 条目 period 声明（schedule 每刻跳，无 turns 战斗全程）。\n\n    返回 {"key": ..., "period": {...}} 或 None（非周期类）。对齐 hot: regen_hot\n    先例但无 turns 限时（旧效果料理回春 keep=True 常驻到战斗结束）。\n    """\n    spec = _PERIOD_FOOD.get(aid)\n    if not spec:\n        return None\n    key, pct_field, default_pct = spec\n    pct = float(_fp(aid, pct_field, default_pct))\n    period = {"dir": "heal", "interval": 1.0, pct_field: pct}\n    return {"key": key, "period": period}\n',
    'content/mech/food_proc.py::install_food_fx': 'def install_food_fx(actor: dict, aids: list, logs: list) -> None:\n    """把吃下的料理 aid 列表装配进 actor（幂等：重复 aid 不重复挂）。\n\n    - 命中/受击/乘区类 → actor["triggers"][事件]（we_* 扩展动作执行）\n    - 周期恢复类 → actor["effects"][key] period 声明（schedule 周期段消费）\n    - 未知 aid → 静默跳过（防拼写漂移；FOOD_EFFECT_NAMES 展示另管）\n    """\n    if not actor or not aids:\n        return\n    # ★ 端口差异（唯一一处「不照抄」）：真源在此**运行时**注册 `we_*` 扩展动作\n    #   （`from .battle_equip_proc import install_ext_actions`）。包内没有那个模块 ——\n    #   因为包内 `content/mech/equip.py` 的动作是 **import 期 `@register_action` 注册**的，\n    #   而 `content/apply.py` 已把七族列全（import 即注册）。所以这里**不是**静默 try/except，\n    #   而是显式声明「无需运行时注册」。想验证：`from content.mech import equip` 后\n    #   `saintess_engine.effects.ACTION_HANDLERS` 里就有 we_* 名词（见端口对拍门禁 §5）。\n    tr = actor.setdefault("triggers", {})\n    ef = actor.setdefault("effects", {})\n    for aid in aids:\n        raw = food_trigger_decls(aid)\n        for old_ev, effs in raw.items():\n            for b2_ev in _map_event(old_ev):\n                bucket = tr.setdefault(b2_ev, [])\n                for _e in effs:\n                    # 幂等：同 aid 同事件同 type 不重复挂（吃重复食物）\n                    _dup = any(\n                        isinstance(x, dict) and x.get("key") == _e.get("key")\n                        for x in bucket\n                    )\n                    if not _dup:\n                        bucket.append(dict(_e, _owner=actor))\n        pd = food_period_decl(aid)\n        if pd:\n            entry = ef.get(pd["key"])\n            if not isinstance(entry, dict):\n                entry = ef[pd["key"]] = {"stacks": 1}\n            entry["period"] = dict(pd["period"])  # 幂等重吃：覆盖同数值声明\n',
    'content/mech/team_procs.py::_mount': 'def _mount(owner, event: str, decl: dict) -> None:\n    """挂触发器（幂等：同 action+key 只留一条，重复施放只刷新态）。"""\n    lst = owner.setdefault("triggers", {}).setdefault(event, [])\n    for t in lst:\n        if (isinstance(t, dict) and t.get("action") == decl.get("action")\n                and t.get("key") == decl.get("key")):\n            t.update(decl)\n            return\n    lst.append(decl)\n',
    'content/mech/worldboss.py::wb_gm_dmg_mult': '@register_action("wb_gm_dmg_mult")\ndef wb_gm_dmg_mult(battle, caster, target, params, logs):\n    """taken_calc 承伤乘区 ×factor（worldboss GM 伤害倍率）。\n\n    引擎零知识：只读 params 的数字，不认「世界 Boss」这个概念。\n    factor 缺省/无效/等于 1.0 → 无此行为（不写 ctx.mult）。\n    """\n    ctx = getattr(battle, "_fire_ctx", None)\n    if ctx is None:\n        return\n    try:\n        f = float(params.get("factor", 1.0) or 1.0)\n    except (TypeError, ValueError):\n        return\n    if f == 1.0:\n        return\n    ctx["mult"] = float(ctx.get("mult", 1.0) or 1.0) * f\n',
    'content/mech/worldboss.py::apply_gm_dmg_mult': 'def apply_gm_dmg_mult(actor: dict, mult: float) -> bool:\n    """把 GM 世界 Boss 伤害倍率挂到 actor 的 taken_calc 乘区。\n\n    幂等（同 actor 重复调用只保留一条声明，值就地更新）；mult 无效或 =1.0 → 不挂并\n    返回 False。返回是否挂上。\n    """\n    if not isinstance(actor, dict):\n        return False\n    try:\n        m = float(mult or 1.0)\n    except (TypeError, ValueError):\n        return False\n    trig = actor.setdefault("triggers", {})\n    lst = trig.setdefault("taken_calc", [])\n    for e in lst:\n        if isinstance(e, dict) and e.get("action") == "wb_gm_dmg_mult":\n            if m == 1.0:\n                lst.remove(e)          # 倍率被 GM 改回 1 → 撤掉声明\n                return False\n            e["factor"] = m\n            return True\n    if m == 1.0:\n        return False\n    lst.append({"action": "wb_gm_dmg_mult", "factor": m})\n    return True\n',
}

_PIN = {
    'phase': 'landed',
    'frozen': {
        'content/mech/equip.py::_known_engine_events': 'cd81e2e7c9da6719d0f609a5afb6b5e3025afb90e6296abf96ff837edfbbfbbf',
        'content/mech/equip.py::map_event': '2bde3f8d58ec59f0075506e4cb387445c10594aaf0ac546e823364ea700bb2c8',
        'content/mech/equip.py::weapon_triggers': 'ff7199dca0852eff5d6a846da8807b8b6724b6b24c95cdb955d1e7e4ba3b6b2b',
        'content/mech/equip.py::affix_triggers': '477930b46af4857910759c2bb0168cf4a0b830083800bc45dc5cf25c8140f2cf',
        'content/mech/equip.py::apply_to_actor': '6d28f9d030d7acd4f0277e11b2e1d466cb6e4d3daa072b1946e15b35cc64d97f',
        'content/mech/food_proc.py::_map_event': 'f4c9be4e258dfc2acd9957c3dafb9a1c27d50229674bc443ffc612bb8f706fa5',
        'content/mech/food_proc.py::food_trigger_decls': '56e1e0d9f5da1fd66a7bc1bbfadff81e928f85153ac083a5ec95a7db26067a28',
        'content/mech/food_proc.py::food_period_decl': 'd56fa0cee9d05f18bce4e5bb3effda8deea313777c4ff30dedd2c2ce38e23a2e',
        'content/mech/food_proc.py::install_food_fx': '1f921216fc6943f0673934d043d2488577afecd84fbea0494c5736ba98ccc0b7',
        'content/mech/team_procs.py::_mount': '8e839245bc7f5329cc1aeb6ea58ac4602b07e2eb866b84c370dbe48ef1eee641',
        'content/mech/worldboss.py::wb_gm_dmg_mult': 'f8b2e9c6d2aed67b061c5c38db3fb01ec763e7f9ddf79f02b9e5550b71a5a470',
        'content/mech/worldboss.py::apply_gm_dmg_mult': '4e196fccd0836f0a30c02dcf01a0be16963ee4c24e508a784a0f2cc7f408e8d1',
    },
    'live': {
        'content/mech/equip.py::_known_engine_events': 'cd81e2e7c9da6719d0f609a5afb6b5e3025afb90e6296abf96ff837edfbbfbbf',
        'content/mech/equip.py::map_event': '2bde3f8d58ec59f0075506e4cb387445c10594aaf0ac546e823364ea700bb2c8',
        'content/mech/equip.py::weapon_triggers': 'c7b8de643ee404079e9968625592f3284906f06ed891e312b66dc8fbafe58b73',
        'content/mech/equip.py::affix_triggers': '1a152b6238fac998e023483a24d742124743fb92791b262d0de81d0a50970612',
        'content/mech/equip.py::apply_to_actor': 'b81f812ff884eb7c4ab19d793e46f02e35e97fa7e7ee348a64703d6c123ce6da',
        'content/mech/food_proc.py::_map_event': 'f4c9be4e258dfc2acd9957c3dafb9a1c27d50229674bc443ffc612bb8f706fa5',
        'content/mech/food_proc.py::food_trigger_decls': '56e1e0d9f5da1fd66a7bc1bbfadff81e928f85153ac083a5ec95a7db26067a28',
        'content/mech/food_proc.py::food_period_decl': 'd56fa0cee9d05f18bce4e5bb3effda8deea313777c4ff30dedd2c2ce38e23a2e',
        'content/mech/food_proc.py::install_food_fx': 'a211992e2fed5da9224d3eb43c3942f1c4f1f024e38c05017a5add40988f6326',
        'content/mech/team_procs.py::_mount': '866d76bf76b1cf33aa99bfa1ea6128314c7437a048dbbd7bce2470fe80beb7ad',
        'content/mech/worldboss.py::wb_gm_dmg_mult': 'f8b2e9c6d2aed67b061c5c38db3fb01ec763e7f9ddf79f02b9e5550b71a5a470',
        'content/mech/worldboss.py::apply_gm_dmg_mult': 'c8dfda4133cd93c68c9de461bf51b7e1008062932a209463b38ca97d5ef3ab98',
    },
    'aux': {
        'contract:content/apply.py': '28f97caa30ab3dcf689e7d91f935a08b3bcce45a56204ddee2d2789473bbd5f4',
        'data:content/data/affixes.json': '611a8d578e3b2cb7f9888e9215bc40dbbe92af81de404535a8494acee3710aee',
        'data:content/data/food_effects.json': '4888c26020b5fbb4d5abe2b0b497c6b7ce396d8850cd02f98a9b4353e7b76400',
        'data:content/data/legendary_effects.json': '4f5b2cf476b09880e49121acf186a72893164e56c03ea087946ac61bd79dd51a',
        'data:content/mech/we_data.py': '111ea69b3da481660ebc6ff2807a57935fbf53163ef02baba17f85a55c39d9fe',
        'engine:saintess_engine/battle/declarations.py': '7b0dcba4982af2477b1708ac651f8843385b37ee56d4a40a173a7a058ec099b9',
        'engine:saintess_engine/battle/effect_triggers.py': 'db1a4c7ab1d94799acb9f2c7383f552cc2dec6f10ba6489eb18dbdbdf98eeead',
        'src_base:content/mech/equip.py': '61c2e8e3b453c2f8fa50e3c67986a26ca59f9ecc11f34c79ca4b4e6224cbff18',
        'src_base:content/mech/food_proc.py': 'caca7c1116448006d298fa5fb94b13e4fd087c01c8b51d276a41c94eae7fe998',
        'src_base:content/mech/team_procs.py': '50d3f1e78ba263bb7a873066e4da1f34df4e995c6ee9aa2d7b6f02e61433bca4',
        'src_base:content/mech/worldboss.py': '59228a4ee297917cc7c98c1ea39054893ad9035069f4ff673e52fd4e9b11237e',
    },
    'segments': {
        'E': [
            'content/mech/equip.py::_known_engine_events',
            'content/mech/equip.py::map_event',
            'content/mech/food_proc.py::_map_event',
            'content/mech/food_proc.py::food_trigger_decls',
            'content/mech/food_proc.py::food_period_decl',
            'content/mech/worldboss.py::wb_gm_dmg_mult',
        ],
        'C': [
            'content/mech/equip.py::weapon_triggers',
            'content/mech/equip.py::affix_triggers',
            'content/mech/equip.py::apply_to_actor',
            'content/mech/food_proc.py::install_food_fx',
            'content/mech/team_procs.py::_mount',
            'content/mech/worldboss.py::apply_gm_dmg_mult',
        ],
    },
    'tier': {
        'content/mech/equip.py::_known_engine_events': '甲',
        'content/mech/equip.py::map_event': '甲',
        'content/mech/equip.py::weapon_triggers': '甲',
        'content/mech/equip.py::affix_triggers': '甲',
        'content/mech/equip.py::apply_to_actor': '甲',
        'content/mech/food_proc.py::_map_event': '甲',
        'content/mech/food_proc.py::food_trigger_decls': '甲',
        'content/mech/food_proc.py::food_period_decl': '甲',
        'content/mech/food_proc.py::install_food_fx': '甲',
        'content/mech/team_procs.py::_mount': '甲',
        'content/mech/worldboss.py::wb_gm_dmg_mult': '甲',
        'content/mech/worldboss.py::apply_gm_dmg_mult': '甲',
    },
}
# <<< _u1d2_triggers_gen (auto) <<<


# ══════════════════════════════════════════════════════════════════════════════
# 1. 冻结段清单 / 旧实现命名空间 / 猴补
# ══════════════════════════════════════════════════════════════════════════════
_KEYS = list(_FROZEN_TEXT)                        # 生成器写盘顺序 = SEGMENTS 顺序
_TIER = dict(_PIN.get("tier") or {})
PHASE = _PIN.get("phase")

_MODS = {
    "content/mech/equip.py": EQ,
    "content/mech/food_proc.py": FP,
    "content/mech/team_procs.py": TP,
    "content/mech/worldboss.py": WB,
}


def _build_old_ns(mod):
    """旧命名空间：活模块 globals（同对象）+ 属于本模块的冻结文本 exec 覆盖同名函数。

    冻结段里的自由名字（`map_event` / `_known_engine_events` / `_UNKNOWN_EVENTS` …）因此
    解析到 OLD ns —— 与旧实现当时的解析一致。
    """
    ns = dict(vars(mod))
    for key, text in _FROZEN_TEXT.items():
        rel = key.rsplit("::", 1)[0]
        if _MODS[rel] is mod:
            sym = key.split("::")[1]
            exec(compile(text, "<frozen:%s:%s>" % (rel, sym), "exec"), ns)   # noqa: S102
    return ns


OLD_EQ = _build_old_ns(EQ)
OLD_FP = _build_old_ns(FP)
OLD_TP = _build_old_ns(TP)
OLD_WB = _build_old_ns(WB)


class _Patch:
    """猴补上下文（进入记原值，退出原地还原；**不写盘**）。支持模块 / 类属性。"""

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


def _call(fn, *a, **k):
    """调用并把异常收敛成可比较的哨兵 dict（异常也必须逐格可比，不许吞成「相等」）。"""
    try:
        return fn(*a, **k)
    except Exception as exc:                                            # noqa: BLE001
        return {"__exc__": type(exc).__name__, "__msg__": str(exc)[:120]}


def _short(v):
    s = repr(v)
    return s if len(s) <= 120 else s[:117] + "..."


def _canon(obj, root, depth=0):
    """把「指向 root 自己」的引用（`_owner` 注入）折成哨兵 —— 否则旧/新 actor 对比无限递归。"""
    if obj is root:
        return "<self>"
    if depth > 24:
        return "<deep>"
    if isinstance(obj, dict):
        return {k: _canon(v, root, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canon(v, root, depth + 1) for v in obj]
    return obj


# ══════════════════════════════════════════════════════════════════════════════
# 2. 数据面夹具（82 / 76 / 93 / 19 条 · 26 事件）
# ══════════════════════════════════════════════════════════════════════════════
WE_KEYS = list(EQ._we_data())
AFFIX_KEYS = list(EQ._affix_data())
LEG_KEYS = list(EQ._legendary_data())
FOOD_KEYS = list(FP._food_params())
ENG_EVENTS = tuple(EV)

EXPECT_ROWS = 7020
EXPECT_OLDNAMES = 34          # 作业书 §3 判据 2 口径：(12 + 5) 键 × 2 文件
EXPECT_OLDNAMES_DEEP = 884    # FROZEN_GATE §5.3 口径（加强网格）：(12+5) × 26 事件 × 2
EXPECT_TOTAL = 7054           # 7,020 + 34（作业书标题「12 段 / 7,054 格」）
EXPECT_IDEM = 24

_MISM = {"rows": [], "oldnames": [], "idem": [], "period": []}


def _cell26(label, old, new, root_old=None, root_new=None):
    """一行表 × 26 事件：逐桶逐条比（含载荷 dict 逐键与序）。返回格数（恒 26）。"""
    if root_old is not None or root_new is not None:
        old = _canon(old, root_old) if root_old is not None else old
        new = _canon(new, root_new) if root_new is not None else new
    same = (old == new)
    for ev in EV:
        if same:
            continue
        if (isinstance(old, dict) and isinstance(new, dict)
                and "__exc__" not in old and "__exc__" not in new
                and (old.get(ev) or []) == (new.get(ev) or [])):
            continue
        _MISM["rows"].append((label, ev, _short(old), _short(new)))
    return len(EV)


def _grid_rows():
    """网格①：82 武器 + 76 词条 + 93 传说 + 19 食物，各 × 26 事件。"""
    n = 0
    for key in WE_KEYS:
        a = {"equipment": {"w": {"weapon_effect": key}}}
        n += _cell26("weapon:%s" % key,
                     _call(OLD_EQ["weapon_triggers"], a), _call(EQ.weapon_triggers, a))
    for aid in AFFIX_KEYS:
        a = {"equipment": {"w": {"affixes": [aid]}}}
        n += _cell26("affix:%s" % aid,
                     _call(OLD_EQ["affix_triggers"], a), _call(EQ.affix_triggers, a))
    for lid in LEG_KEYS:
        a = {"equipment": {"w": {"legendary": lid}}}
        n += _cell26("legendary:%s" % lid,
                     _call(OLD_EQ["legendary_triggers"], a), _call(EQ.legendary_triggers, a))
    for aid in FOOD_KEYS:
        ao, al = {"name": "u1d2-food-o"}, {"name": "u1d2-food-l"}
        _call(OLD_FP["install_food_fx"], ao, [aid], [])
        _call(FP.install_food_fx, al, [aid], [])
        n += _cell26("food:%s" % aid, ao.get("triggers") or {}, al.get("triggers") or {},
                     root_old=ao, root_new=al)
        # period 分支（不进 triggers）另比一次（不计入 7,020）
        if (ao.get("effects") or {}) != (al.get("effects") or {}):
            _MISM["period"].append(("food-effects:%s" % aid,
                                    _short(ao.get("effects")), _short(al.get("effects"))))
    return n


_OLDMAP_FILES = (
    ("equip", EQ, "map_event", OLD_EQ["map_event"]),
    ("food", FP, "_map_event", OLD_FP["_map_event"]),
)


def _oldmap_unknown(mod, K, tgts):
    """该旧名展开后的未知名清单（活实现接了引擎 → 用编译器 `validate`；红基线 → 直接比 EVENTS）。"""
    comp = getattr(mod, "_DECL", None)
    if comp is not None:
        return [u for u in comp.validate({K: [{}]}) if u not in EV]
    return [t for t in tgts if t not in EV]


def _grid_oldnames():
    """网格②（作业书 §3 判据 2 口径）：旧名映射 (12 + 5) 键 × 2 文件 = 34 格。

    每键 2 格：① 映射目标全在 `EVENTS`；② 该键展开的未知名清单为空。
    """
    n = 0
    for label, mod, _msym, oldmap in _OLDMAP_FILES:
        for K in list(getattr(mod, "_EVENT_MAP")):
            tgts = tuple(oldmap(K))
            n += 1
            if not all(t in EV for t in tgts):
                _MISM["oldnames"].append((label, K, "target", tgts))
            n += 1
            unk = _oldmap_unknown(mod, K, tgts)
            if unk:
                _MISM["oldnames"].append((label, K, "unknown", unk))
    return n


def _grid_oldnames_deep():
    """加强网格（`FROZEN_GATE.md` §5.3 口径）：旧名映射 (12 + 5) × 26 事件 × 2 = 884 格。"""
    n = 0
    for label, mod, _msym, oldmap in _OLDMAP_FILES:
        for K in list(getattr(mod, "_EVENT_MAP")):
            tgts = tuple(oldmap(K))
            known = all(t in EV for t in tgts)
            for E in EV:
                n += 1
                if not known:
                    _MISM["oldnames"].append((label, K, E, "target", tgts))
                n += 1
                unk = _oldmap_unknown(mod, K, tgts)
                if unk:
                    _MISM["oldnames"].append((label, K, E, "unknown", unk))
    return n


# ── 幂等矩阵夹具 ─────────────────────────────────────────────────────────────
WE_TRIG_KEY = None
for _k in WE_KEYS:
    _r = _call(EQ.triggers_for_key, _k)
    if isinstance(_r, dict) and _r:
        WE_TRIG_KEY = _k
        break
if WE_TRIG_KEY is None:
    raise SystemExit("夹具失败：82 条武器行里找不到一条有 triggers 的 key")


def _equip_actor(state):
    a = {"equipment": {"w": {"weapon_effect": WE_TRIG_KEY, "quality": "orange",
                             "affixes": [], "stats": {}}}}
    if state:
        a["triggers"] = {"attack_hit": [{"action": "pre_existing", "key": "pre"}]}
    return a


def _food_actor(state):
    a = {"name": "u1d2-food"}
    if state:
        a["triggers"] = {"attack_hit": [{"type": "we_extra_dmg", "key": "food_lifesteal",
                                         "heal_pct": 0.99}]}
    return a


def _team_actor(state):
    a = {}
    if state:
        a["triggers"] = {"skill_hit": [{"action": "team_probe", "key": "tk", "v": 99}]}
    return a


def _wb_actor(state):
    a = {}
    if state:
        a["triggers"] = {"taken_calc": [{"action": "wb_gm_dmg_mult", "factor": 0.5}]}
    return a


_ENTRIES = (
    ("equip.apply_to_actor", _equip_actor,
     lambda a: OLD_EQ["apply_to_actor"](a), lambda a: EQ.apply_to_actor(a), ()),
    ("food_proc.install_food_fx", _food_actor,
     lambda a: OLD_FP["install_food_fx"](a, ["lifesteal"], []),
     lambda a: FP.install_food_fx(a, ["lifesteal"], []), ()),
    ("team_procs._mount", _team_actor,
     lambda a: OLD_TP["_mount"](a, "skill_hit", {"action": "team_probe", "key": "tk", "v": 1}),
     lambda a: TP._mount(a, "skill_hit", {"action": "team_probe", "key": "tk", "v": 1}), ()),
    ("worldboss.apply_gm_dmg_mult", _wb_actor,
     lambda a: OLD_WB["apply_gm_dmg_mult"](a, 2.0), lambda a: WB.apply_gm_dmg_mult(a, 2.0), ()),
)


def _repeat(fn, actor, times):
    out = []
    for _ in range(times):
        out.append(_call(fn, actor))
    return out


def _grid_idem():
    """网格③：4 挂载入口 × 重复 {1,2,3} × 2 actor 态。"""
    n = 0
    for name, mk, old_fn, live_fn, _args in _ENTRIES:
        for state in (0, 1):
            for rep in (1, 2, 3):
                oa, la = mk(state), mk(state)
                orr = _repeat(old_fn, oa, rep)
                lrr = _repeat(live_fn, la, rep)
                n += 1
                if _canon(oa, oa) != _canon(la, la) or orr != lrr:
                    _MISM["idem"].append((name, state, rep, _short(_canon(oa, oa)),
                                          _short(_canon(la, la)),
                                          _short(orr), _short(lrr)))
    return n


class _IdemBreak:
    """关掉去重（`_key_of_entry` 恒 None）→ 幂等失效探针用。"""

    def __init__(self):
        self.p = _Patch(Compiler, "_key_of_entry", lambda self, kf, item: None)

    def __enter__(self):
        return self.p.__enter__()

    def __exit__(self, *exc):
        return self.p.__exit__(*exc)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 判据 1：双 sha256 + E/C 分类 + 分级
# ═══════════════════════════════════════════════════════════════════════════════
def test_frozen_pins():
    print("【1. 双 sha256：12 段冻结文本 + 活实现 inspect.getsource】")
    keys = list(_PIN["frozen"])
    check("冻结段数 == 12（equip 5 / food_proc 4 / team_procs 1 / worldboss 2）",
          len(keys) == 12, len(keys))
    check("门禁内键序 == 冻结文本键序", keys == list(_FROZEN_TEXT), keys[:3])
    bad = [k for k in keys if sha256(_FROZEN_TEXT[k]) != _PIN["frozen"][k]]
    check("冻结文本 sha256 全等 _PIN['frozen']（12 段）", not bad, bad[:4])

    live_bad = []
    for k in keys:
        rel, sym = k.split("::")
        obj = getattr(_MODS[rel], sym, None)
        got = "<deleted>" if obj is None else sha256(inspect.getsource(obj))
        if got != _PIN["live"][k]:
            live_bad.append((k, _PIN["live"][k][:12], got[:12]))
    check("活实现 inspect.getsource sha256 全等 _PIN['live']（12 段）", not live_bad, live_bad[:4])

    seg = _PIN["segments"]
    chkE = [k for k in seg["E"] if _PIN["frozen"][k] != _PIN["live"][k]]
    check("E 栏「预期不变」段 frozen == live（%d 段）" % len(seg["E"]), not chkE, chkE[:3])
    if PHASE == "landed":
        chkC = [k for k in seg["C"] if _PIN["frozen"][k] == _PIN["live"][k]]
        check("C 栏「预期会变」段 frozen != live（%d 段）" % len(seg["C"]), not chkC, chkC[:3])
        none_decl = [n for n, m in (("equip", EQ), ("food_proc", FP),
                                    ("team_procs", TP), ("worldboss", WB))
                     if not hasattr(m, "_DECL")]
        check("C 栏真接上：四个活模块都有引擎编译器实例 `_DECL`", not none_decl, none_decl)
        loops = {
            "equip.weapon_triggers": "setdefault(b2_ev" in inspect.getsource(EQ.weapon_triggers),
            "equip.affix_triggers": "setdefault(b2_ev" in inspect.getsource(EQ.affix_triggers),
            "food_proc.install_food_fx": "_dup = any(" in inspect.getsource(FP.install_food_fx),
            "team_procs._mount": "for t in lst:" in inspect.getsource(TP._mount),
            "worldboss.apply_gm_dmg_mult": "for e in lst:" in inspect.getsource(WB.apply_gm_dmg_mult),
        }
        leftover = sorted(k for k, v in loops.items() if v)
        check("C 栏真接上：手写判重循环已从 5 处活实现消失", not leftover, leftover)
    else:
        print("  ⓘ phase=%r：C 栏不等式/接上断言按「红基线」档暂不启用" % (PHASE,))

    tiers = {}
    for k in keys:
        tiers.setdefault(_TIER[k], []).append(k)
    got = (len(tiers.get("甲", [])), len(tiers.get("乙", [])), len(tiers.get("丙", [])))
    check("分级：甲 %d / 乙 %d / 丙 %d（期望 12 / 0 / 0）" % got, got == (12, 0, 0))
    check("12 段全部覆盖（冻结键 == 段清单）",
          set(_KEYS) == set(seg["E"]) | set(seg["C"]) and len(seg["E"]) == 6 and len(seg["C"]) == 6)


# ══════════════════════════════════════════════════════════════════════════════
# 4. 判据 2：全量网格 7,020 + 34 = 7,054（加强 884）
# ══════════════════════════════════════════════════════════════════════════════
def test_grids():
    print("【2. 全量网格：行表 × 事件全集 + 旧名映射】")
    check("输入面：82 武器 / 76 词条 / 93 传说 / 19 食物 / 引擎 26 事件",
          (len(WE_KEYS), len(AFFIX_KEYS), len(LEG_KEYS), len(FOOD_KEYS), len(EV))
          == (82, 76, 93, 19, 26),
          (len(WE_KEYS), len(AFFIX_KEYS), len(LEG_KEYS), len(FOOD_KEYS), len(EV)))

    n_rows = _grid_rows()
    print("     网格① 行表 × 26 事件：实测 %d 格（期望 %d）；不等 %d 处"
          % (n_rows, EXPECT_ROWS, len(_MISM["rows"])))
    check("网格① == 7,020 格（脚本实测）", n_rows == EXPECT_ROWS, n_rows)
    check("网格① 逐桶逐条全等（旧实现 exec ↔ 活实现）", not _MISM["rows"],
          _MISM["rows"][:4])
    check("食物 period 分支（不进 triggers）19 条逐字段全等", not _MISM["period"],
          _MISM["period"][:3])

    n_old = _grid_oldnames()
    print("     网格② 旧名映射 (12+5) 键 × 2 文件：实测 %d 格（期望 %d）；不等 %d 处"
          % (n_old, EXPECT_OLDNAMES, len(_MISM["oldnames"])))
    check("网格② == 34 格（脚本实测）", n_old == EXPECT_OLDNAMES, n_old)
    check("网格② 映射目标全在 EVENTS（未知名清单为空）", not _MISM["oldnames"],
          _MISM["oldnames"][:4])
    check("网格合计 == 7,054 格（7,020 + 34，作业书标题口径）",
          n_rows + n_old == EXPECT_TOTAL, n_rows + n_old)

    n_deep = _grid_oldnames_deep()
    print("     网格②′ 加强（FROZEN_GATE §5.3 口径）(12+5) × 26 事件 × 2：实测 %d 格"
          "（期望 %d）；累计不等 %d 处" % (n_deep, EXPECT_OLDNAMES_DEEP, len(_MISM["oldnames"])))
    check("网格②′ == 884 格（脚本实测）", n_deep == EXPECT_OLDNAMES_DEEP, n_deep)
    check("网格②′ 逐事件加强断言全等", not _MISM["oldnames"], _MISM["oldnames"][:4])


# ══════════════════════════════════════════════════════════════════════════════
# 5. 判据 3：幂等矩阵 24 格（equip 非幂等单列）
# ══════════════════════════════════════════════════════════════════════════════
def test_idem():
    print("【3. 幂等矩阵：4 挂载入口 × {1,2,3} × 2 actor 态】")
    n = _grid_idem()
    print("     实测 %d 格（期望 %d）；不等 %d 处" % (n, EXPECT_IDEM, len(_MISM["idem"])))
    check("幂等矩阵 == 24 格（脚本实测）", n == EXPECT_IDEM, n)
    check("24 格旧实现 ≡ 活实现（终态 + 返回值）", not _MISM["idem"], _MISM["idem"][:3])

    # 幂等三入口：桶长不随重复次数增长
    for name, mk, live_fn in (("food", _food_actor, lambda a: FP.install_food_fx(a, ["lifesteal"], [])),
                              ("team", _team_actor,
                               lambda a: TP._mount(a, "skill_hit", {"action": "team_probe",
                                                                    "key": "tk", "v": 1})),
                              ("wb", _wb_actor, lambda a: WB.apply_gm_dmg_mult(a, 2.0))):
        lens = []
        for rep in (1, 2, 3):
            a = mk(0)
            for _ in range(rep):
                live_fn(a)
            lens.append(sum(len(v) for v in (a.get("triggers") or {}).values()))
        check("幂等入口 %s：重复 1/2/3 次桶长不增长 %s" % (name, lens),
              lens[0] == lens[1] == lens[2], lens)

    # equip 非幂等单列：总条数随重复次数线性增长
    elens = []
    for rep in (1, 2, 3):
        a = _equip_actor(0)
        for _ in range(rep):
            EQ.apply_to_actor(a)
        elens.append(sum(len(v) for v in (a.get("triggers") or {}).values()))
    check("equip 非幂等单列：总条数随重复 1/2/3 线性增长 %s" % elens,
          elens[0] > 0 and elens[1] == 2 * elens[0] and elens[2] == 3 * elens[0], elens)


# ══════════════════════════════════════════════════════════════════════════════
# 6. 判据 4：apply_gm_dmg_mult 返回 bool 语义逐字
# ══════════════════════════════════════════════════════════════════════════════
def _wb_decls(actor):
    return [x for x in (((actor or {}).get("triggers") or {}).get("taken_calc") or [])
            if isinstance(x, dict) and x.get("action") == "wb_gm_dmg_mult"]


def test_gm_bool():
    print("【4. apply_gm_dmg_mult 返回 bool 语义（含「回落 1.0 → 撤回」）】")
    a = {}
    check("倍率 1.0：不挂 + False", WB.apply_gm_dmg_mult(a, 1.0) is False and not _wb_decls(a),
          _wb_decls(a))
    check("倍率 10：挂上 + True", WB.apply_gm_dmg_mult(a, 10.0) is True
          and _wb_decls(a)[0].get("factor") == 10.0, _wb_decls(a))
    check("已挂再改 3.0：仍 True 且只 1 条、值就地更新",
          WB.apply_gm_dmg_mult(a, 3.0) is True and len(_wb_decls(a)) == 1
          and _wb_decls(a)[0].get("factor") == 3.0, _wb_decls(a))
    check("已挂且改回 1.0：撤回 + False",
          WB.apply_gm_dmg_mult(a, 1.0) is False and not _wb_decls(a), _wb_decls(a))
    check("非法倍率 'abc'：False 且不挂", WB.apply_gm_dmg_mult(a, "abc") is False
          and not _wb_decls(a))
    check("非 dict actor：False（不抛）", WB.apply_gm_dmg_mult(None, 5.0) is False
          and WB.apply_gm_dmg_mult([], 5.0) is False)

    # 旧实现 ↔ 活实现：全序列（返回值 + actor 终态）逐格
    seq = (1.0, 10.0, 3.0, 1.0, "abc", 0.5, 0.5, 1.0)
    ao, al = {}, {}
    bad = []
    for i, m in enumerate(seq):
        ro = _call(OLD_WB["apply_gm_dmg_mult"], ao, m)
        rl = _call(WB.apply_gm_dmg_mult, al, m)
        if ro != rl or ao != al:
            bad.append((i, m, ro, rl, _short(ao), _short(al)))
    check("旧 ↔ 活：8 步序列返回值 + actor 终态逐格全等", not bad, bad[:3])


# ══════════════════════════════════════════════════════════════════════════════
# 7. 判据 5：_owner 双注入（挂载期 + fire() 兜底）
# ══════════════════════════════════════════════════════════════════════════════
_OWNER_SEEN = []


def test_owner():
    print("【5. _owner 双注入：挂载期 + fire() 兜底 → 同一对象】")
    actor = {"name": "u1d2-owner"}
    FP.install_food_fx(actor, ["lifesteal"], [])
    mounted = [e for v in (actor.get("triggers") or {}).values() for e in v
               if isinstance(e, dict)]
    check("挂载期注入：每条声明 `_owner is actor`（%d 条）" % len(mounted),
          bool(mounted) and all(e.get("_owner") is actor for e in mounted),
          [(e.get("key"), type(e.get("_owner")).__name__) for e in mounted][:3])

    from saintess_engine.battle.effects import register_action

    @register_action("u1d2_owner_probe")
    def _probe(battle, caster, target, params, logs):               # noqa: ANN001
        _OWNER_SEEN.append(params)

    _OWNER_SEEN.clear()
    keep = actor.get("triggers")
    actor["triggers"] = {"attack_hit": [{"type": "u1d2_owner_probe"}]}
    battle = types.SimpleNamespace(sides={"player": [actor]}, _fire_ctx=None)
    try:
        fire(battle, "attack_hit", {"actor": actor, "caster": actor, "target": actor}, [])
    finally:
        actor["triggers"] = keep
    check("fire() 兜底注入：动作读到 `params['_owner'] is actor`（1 次执行）",
          len(_OWNER_SEEN) == 1 and _OWNER_SEEN[0].get("_owner") is actor,
          [(p.get("_owner") is actor) for p in _OWNER_SEEN])
    check("两条路径拿到的是同一对象（挂载期写入的那条 `_owner`）",
          bool(mounted) and _OWNER_SEEN and _OWNER_SEEN[0].get("_owner") is mounted[0].get("_owner"))


# ══════════════════════════════════════════════════════════════════════════════
# 8. 判据 6：equip 三个名字仍在且语义不变（AST + 直取）
# ══════════════════════════════════════════════════════════════════════════════
def test_equip_names():
    print("【6. equip._EVENT_MAP / _UNKNOWN_EVENTS / _known_engine_events 三名字】")
    src = open(_pkg_file("content/mech/equip.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    assigns = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            assigns[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assigns[node.target.id] = node.value
    funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}

    # ★ D7（2026-09-17）「数据进表」读源重定向：`_EVENT_MAP` 已从本文件的模块级字面量搬进包内域
    #   `content/data/equip_event_map.json`（单一真源；代码只留 records 读口）。判据一字未改
    #   （12 键 + 目标全是引擎事件 tuple），只把「值从哪读」由源码字面量换成域文件。
    _dom = json.load(open(_pkg_file("content/data/equip_event_map.json"), encoding="utf-8"))
    check("AST：`_EVENT_MAP` 仍在端口顶层（读口），域文件 `EVENT_MAP` 段 12 键",
          "_EVENT_MAP" in assigns and len(_dom.get("EVENT_MAP") or {}) == 12,
          len(_dom.get("EVENT_MAP") or {}))
    check("AST：`_UNKNOWN_EVENTS` 是模块级 List 字面量",
          isinstance(assigns.get("_UNKNOWN_EVENTS"), ast.List))
    check("AST：`_known_engine_events` / `map_event` 是模块级函数",
          {"_known_engine_events", "map_event"} <= funcs,
          sorted({"_known_engine_events", "map_event"} - funcs))

    check("直取：`_EVENT_MAP` 12 键、值全是引擎事件 tuple",
          len(EQ._EVENT_MAP) == 12
          and all(isinstance(v, tuple) and all(t in EV for t in v)
                  for v in EQ._EVENT_MAP.values()))
    check("直取：`_UNKNOWN_EVENTS` 是 list", isinstance(EQ._UNKNOWN_EVENTS, list))
    check("语义：`_known_engine_events() == frozenset(EVENTS)`（26）",
          EQ._known_engine_events() == frozenset(EV), len(EQ._known_engine_events()))
    check("语义：`map_event('hit') == ('attack_hit', 'skill_hit')`（一拆二、元组序）",
          EQ.map_event("hit") == ("attack_hit", "skill_hit"), EQ.map_event("hit"))
    check("语义：`map_event('dot_taken') == ('dot_tick',)`", EQ.map_event("dot_taken") == ("dot_tick",))


# ══════════════════════════════════════════════════════════════════════════════
# 9. 判据 7：口径分歧 8 条（C 块 §6）
# ══════════════════════════════════════════════════════════════════════════════
def _eng(**kw):
    kw.setdefault("events", EV)
    return Compiler(**kw)


def test_divergences():
    print("【7. 口径分歧 8 条】")
    # ① 五种去重键
    keys = {
        "(action,key)": (lambda d: (d.get("action"), d.get("key")), 1),
        "key": (lambda d: d.get("key"), 1),
        "action": (lambda d: d.get("action"), 1),
        "type": (lambda d: d.get("type"), 1),
        "None": (None, 2),
    }
    for name, (kf, want) in keys.items():
        comp = _eng(key_of=kf)
        a = {}
        comp.mount(a, {"skill_hit": [{"action": "aa", "key": "kk", "type": "tt", "v": 1}]})
        comp.mount(a, {"skill_hit": [{"action": "aa", "key": "kk", "type": "tt", "v": 2}]})
        check("分歧① 去重键 %s：同声明挂两次桶长 == %d" % (name, want),
              len(a["triggers"]["skill_hit"]) == want, len(a["triggers"]["skill_hit"]))

    # ② 四种写策略
    comp = _eng(key_of=lambda d: d.get("key"))
    a = {}
    comp.mount(a, {"skill_hit": [{"key": "k", "v": 1}]}, merge="append")
    comp.mount(a, {"skill_hit": [{"key": "k", "v": 2}]}, merge="append")
    check("分歧② append：命中留旧再追加（桶长 2，尾部 v=2）",
          [e.get("v") for e in a["triggers"]["skill_hit"]] == [1, 2],
          a["triggers"]["skill_hit"])
    b = {}
    comp.mount(b, {"skill_hit": [{"key": "k", "v": 1}]}, merge="replace")
    comp.mount(b, {"skill_hit": [{"key": "k", "v": 2}]}, merge="replace")
    check("分歧② replace：命中原地浅盖（桶长 1，v=2）",
          len(b["triggers"]["skill_hit"]) == 1 and b["triggers"]["skill_hit"][0]["v"] == 2,
          b["triggers"]["skill_hit"])
    c = {}
    comp.mount(c, {"skill_hit": [{"key": "k1"}]}, merge="prepend")
    comp.mount(c, {"skill_hit": [{"key": "k2"}]}, merge="prepend")
    check("分歧② prepend：新条目在桶首（执行序）",
          [e.get("key") for e in c["triggers"]["skill_hit"]] == ["k2", "k1"],
          c["triggers"]["skill_hit"])
    d = {}
    comp.mount(d, {"skill_hit": [{"key": "k1"}, {"key": "k2"}]})
    n = comp.purge(d, event="skill_hit", match=lambda e: e.get("key") == "k1")
    check("分歧② purge：撤条目返回条数 1 且空桶键保留（空列表）",
          n == 1 and d["triggers"]["skill_hit"] == [{"key": "k2"}], (n, d["triggers"]))

    # ③ `_owner` 双注入（见判据 5）——此处补一条 setdefault 幂等
    e = {}
    comp2 = _eng(key_of=lambda x: x.get("key"), owner_key="_owner")
    comp2.mount(e, {"skill_hit": [{"key": "k", "v": 1}]}, owner="OWNER")
    comp2.mount(e, {"skill_hit": [{"key": "k", "v": 2}]}, owner="OTHER", merge="keep")
    check("分歧③ `_owner` setdefault 幂等：命中保留既有 owner",
          e["triggers"]["skill_hit"][0].get("_owner") == "OWNER",
          e["triggers"]["skill_hit"])

    # ④ 未知名：告警 + 放行（不抛）；fire() 静默忽略
    before = len(EQ._UNKNOWN_EVENTS)
    got = EQ.map_event("u1d2_bogus_event")
    check("分歧④ `equip.map_event` 未知名：直通返回 tuple 且登记（不抛）",
          got == ("u1d2_bogus_event",) and "u1d2_bogus_event" in EQ._UNKNOWN_EVENTS
          and len(EQ._UNKNOWN_EVENTS) >= before, (got, EQ._UNKNOWN_EVENTS[-2:]))
    seen = []

    @register_action("u1d2_unknown_probe")
    def _probe2(battle, caster, target, params, logs):               # noqa: ANN001
        seen.append(params)

    holder = {"triggers": {"u1d2_bogus_event": [{"type": "u1d2_unknown_probe"}]}}
    btl = types.SimpleNamespace(sides={"player": [holder]}, _fire_ctx=None)
    fire(btl, "u1d2_bogus_event", {"actor": holder}, [])
    check("分歧④ `fire()` 对未知事件静默忽略（零执行）", seen == [], seen)

    # ⑤ mapping 与 list 两输入形态等价
    cm = _eng(map_event=EQ.map_event)
    m1 = cm.compile({"hit": [{"action": "a1"}]})
    l1 = cm.compile([Declaration("attack_hit", {"action": "a1"}),
                     Declaration("skill_hit", {"action": "a1"})])
    check("分歧⑤ mapping 形态 == list(Declaration) 形态", m1 == l1, (m1, l1))
    l2 = cm.compile([{"event": "attack_hit", "action": "a1"}])
    check("分歧⑤ list(dict) 形态：event_key 直取（桶键 == attack_hit）",
          set(l2) == {"attack_hit"}, sorted(l2))

    # ⑥ compile 三层保序
    o1 = cm.compile({"hit": [{"action": "h1"}, {"action": "h2"}], "taken": [{"action": "t1"}]})
    o2 = cm.compile({"taken": [{"action": "t1"}], "hit": [{"action": "h1"}, {"action": "h2"}]})
    check("分歧⑥ 外层行表序：hit/taken 互换 → 桶键序随之改变",
          list(o1) == ["attack_hit", "skill_hit", "on_taken"]
          and list(o2) == ["on_taken", "attack_hit", "skill_hit"], (list(o1), list(o2)))
    check("分歧⑥ `map_event` 元组序：attack_hit 恒在 skill_hit 之前 + 桶内追加序保真",
          [p["action"] for p in o1["attack_hit"]] == ["h1", "h2"], o1["attack_hit"])

    # ⑦ equip 非幂等（key_of=None 逐字保留 extend 语义）
    a7 = _equip_actor(0)
    EQ.apply_to_actor(a7)
    n1 = sum(len(v) for v in (a7.get("triggers") or {}).values())
    EQ.apply_to_actor(a7)
    n2 = sum(len(v) for v in (a7.get("triggers") or {}).values())
    check("分歧⑦ equip.apply_to_actor 非幂等：再装配一次总条数翻倍（%d → %d）" % (n1, n2),
          n1 > 0 and n2 == 2 * n1, (n1, n2))

    # ⑧ worldboss bool 语义含「回落 1.0 → 撤回」（判据 4 已细判，此处一条汇总）
    a8 = {}
    check("分歧⑧ worldboss 挂上 True / 撤回 False（含回落 1.0）",
          WB.apply_gm_dmg_mult(a8, 2.0) is True
          and WB.apply_gm_dmg_mult(a8, 1.0) is False and not _wb_decls(a8))


# ══════════════════════════════════════════════════════════════════════════════
# 10. 判据 8：有牙反证 3 处（对应探针必须变红）
# ══════════════════════════════════════════════════════════════════════════════
def _probe_idem():
    """幂等探针（引擎契约 + 活接线各半）：关掉去重后桶长必须增长。"""
    out = []
    comp = Compiler(events=EV, key_of=lambda d: d.get("key"))
    a = {}
    comp.mount(a, {"attack_hit": [{"key": "k", "v": 1}]})
    comp.mount(a, {"attack_hit": [{"key": "k", "v": 2}]})
    out.append(("engine-key", [len(v) for v in a["triggers"].values()]))
    comp2 = Compiler(events=EV, key_of=lambda d: (d.get("action"), d.get("key")),
                     owner_key="_owner")
    b = {"name": "u1d2-probe2"}
    comp2.mount(b, {"attack_hit": [{"action": "aa", "key": "k"}]}, owner=b)
    comp2.mount(b, {"attack_hit": [{"action": "aa", "key": "k"}]}, owner=b)
    out.append(("engine-owner", [len(v) for v in b["triggers"].values()]))

    fa = {"name": "u1d2-probe"}
    FP.install_food_fx(fa, ["lifesteal"], [])
    FP.install_food_fx(fa, ["lifesteal"], [])
    out.append(("food", sorted(len(v) for v in (fa.get("triggers") or {}).values())))
    tb = {}
    dd = {"action": "team_probe", "key": "tk", "v": 1}
    TP._mount(tb, "skill_hit", dict(dd))
    TP._mount(tb, "skill_hit", dict(dd))
    out.append(("team", [len(v) for v in (tb.get("triggers") or {}).values()]))
    wc = {}
    WB.apply_gm_dmg_mult(wc, 2.0)
    WB.apply_gm_dmg_mult(wc, 2.0)
    out.append(("wb", [len(v) for v in (wc.get("triggers") or {}).values()]))
    e = _equip_actor(0)
    EQ.apply_to_actor(e)
    EQ.apply_to_actor(e)
    out.append(("equip", sum(len(v) for v in (e.get("triggers") or {}).values())))
    return out


def _probe_prepend():
    comp = Compiler(events=EV, key_of=lambda d: d.get("key"))
    a = {}
    comp.mount(a, {"skill_hit": [{"key": "first"}]}, merge="prepend")
    comp.mount(a, {"skill_hit": [{"key": "second"}]}, merge="prepend")
    return [p.get("key") for p in a["triggers"]["skill_hit"]]


def _probe_unknown():
    comp = getattr(EQ, "_DECL", None) or Compiler(events=EV, map_event=EQ.map_event)
    try:
        got = comp.compile({"u1d2_bogus_event": [{"action": "x"}]})
    except Exception as exc:                                            # noqa: BLE001
        return ("exc", type(exc).__name__)
    return ("ok", sorted(got), "u1d2_bogus_event" in EQ._UNKNOWN_EVENTS)


_PROBES = {"idem": _probe_idem, "prepend": _probe_prepend, "unknown": _probe_unknown}


def _break_key_none():
    return _Patch(Compiler, "_key_of_entry", lambda self, kf, item: None)


def _break_merge_append():
    return _Patch(Compiler, "_place",
                  lambda self, bucket, payload, front: bucket.append(payload))


def _break_unknown_raises():
    real = Compiler.compile

    def _c(self, rows, *, map_event=None, allow_unknown=False):
        out = real(self, rows, map_event=map_event, allow_unknown=allow_unknown)
        bad = [ev for ev in out if self.unknown_name(ev)]
        if bad:
            raise ValueError("未知名事件：%r" % (bad,))
        return out

    return _Patch(Compiler, "compile", _c)


_BREAKS = (
    ("去重键恒 None（key_of 失效 → 幂等失效）", _break_key_none, "idem"),
    ("merge 恒 append（前插序丢）", _break_merge_append, "prepend"),
    ("事件名校验改抛异常（装配中断）", _break_unknown_raises, "unknown"),
)


def test_teeth():
    print("【8. 有牙反证：破坏 3 处 → 对应探针必须变红（原地还原 + 全程零写盘）】")
    before = {f: _file_sha(f) for f in READONLY_FILES}
    base = {k: fn() for k, fn in _PROBES.items()}
    print("     未破坏基线：%s" % {k: _short(v) for k, v in base.items()})
    check("未破坏时三条探针基线已取到", all(base[k] is not None for k in base))

    for name, breaker, key in _BREAKS:
        with breaker():
            got = _PROBES[key]()
        red = (got != base[key])
        print("     破坏 `%s`：预期变红 / 实测 %s" % (name, "变红 ✅" if red else "仍绿 ❌"))
        check("破坏 `%s` → 对应探针必须变红（预期变红 / 实测变红）" % name, red,
              (base[key], got))
        check("还原 `%s` 后探针回绿" % name, _PROBES[key]() == base[key])
        others = [k for k in _PROBES if k != key]
        check("破坏 `%s` 时其余探针仍绿（各管一段，不是一个大探针）" % name,
              all(_PROBES[k]() == base[k] for k in others),
              [k for k in others if _PROBES[k]() != base[k]])

    print("  ── 多故障场景（两处同坏 + 第三处仍绿）──")
    with _break_key_none(), _break_merge_append():
        d1, d2, d3 = _PROBES["idem"](), _PROBES["prepend"](), _PROBES["unknown"]()
    check("两处同坏（去重键 + merge）：idem 与 prepend 各自变红，unknown 仍绿",
          d1 != base["idem"] and d2 != base["prepend"] and d3 == base["unknown"],
          (d1 != base["idem"], d2 != base["prepend"], d3 == base["unknown"]))

    after = {f: _file_sha(f) for f in READONLY_FILES}
    check("反证全程零写盘：8 个源文件/数据表 sha256 前后一致", before == after,
          [f for f in READONLY_FILES if before[f] != after[f]])


# ══════════════════════════════════════════════════════════════════════════════
# 11. 判据 9：只读（4 源文件 + 4 数据表）+ aux 指纹
# ══════════════════════════════════════════════════════════════════════════════
#: ★ D2（数据进表）：`content/mech/we_data.py` 是**有意改动**的文件 —— 内联 82 键字面量表已搬进
#: `content/data/weapon_effects.json`（域 `weapon_effects`）+ `content/data/text_specs.json`
#: （51 条文案），本文件只剩「域 + 文案表 → 表」的读口。因此它的**文件 sha** 不再等于
#: `_PIN['aux']` 的搬前值（`_PIN` 那一格保留作历史追溯）。判据不削弱：改成**值面**断言
#: 「活表 == base/pkg 搬前字面量表（键序 + repr(值) + type 名 逐名相等）」—— 比文件 sha 更准
#: （文件 sha 会被注释/排版带动，值面只认数据）。搬前值另有
#: `tests/test_package_mech_ports.py::FROZEN_TABLE['WEAPON_EFFECT_DATA']`（sha `aa9b344a…`）钉住。
_D2_MOVED_DATA = "data:content/mech/we_data.py"

#: ★ 2026-09-17 主线收尾：搬前字面量表的**值面** canonical sha256（键序 + 每格 `repr(值)` + type 名）。
#: 门禁原本直比 `base/pkg`（那是**线的工作区布局**）；真仓布局没有基线副本 ⇒ 不静默跳过、也不假绿，
#: 改判这个同源钉值（由交付线的 `base/pkg` 现算，语义与直比等价：只认数据，不认注释/排版）。
#: 2026-09-18 重采：we.* 六条「接线即炸」文案修复（残留 `int(float(wd.get(...)))` 表达式 → 槽位
#: `{pct}`/`{cap}` 化，含兰顿/冰脉的速度百分比同款）落到 `WEAPON_EFFECT_DATA` 的 7 处模板 ⇒ 值面
#: 随之变；差异经逐行 diff 核对**只**含这 7 处文案（无键序/类型/数值变化）。旧值 44fc53ce…。
_D2_BASE_VALUE_SHA = "2874519e80b26b731863b4f787a4892eda616c29652f6d68759f69e724d8beb8"


def _canon_we_sha(tbl) -> str:
    """值面 canonical sha256：键序 + 每格 (字段, repr(值), type 名)。"""
    import hashlib as _h
    import json as _j
    canon = {"order": list(tbl),
             "cells": [[k, [[f, repr(v), type(v).__name__] for f, v in tbl[k].items()]] for k in tbl]}
    return _h.sha256(_j.dumps(canon, ensure_ascii=False, sort_keys=False).encode("utf-8")).hexdigest()


def _we_value_diff() -> list:
    """D2：活侧读口的表 vs `base/pkg` 搬前字面量表（键序 + 值 + 类型，逐名相等）。"""
    base = os.path.join(LANE_ROOT, "base", "pkg", "content", "mech", "we_data.py")
    import content.mech.we_data as _W
    new = _W.WEAPON_EFFECT_DATA
    if not os.path.isfile(base):
        # 真仓布局：改判值面 canonical sha256（见 _D2_BASE_VALUE_SHA 的说明）
        got = _canon_we_sha(new)
        print("      （真仓布局：活表值面 canonical sha=%s；钉值 %s）" % (got[:16], _D2_BASE_VALUE_SHA[:16]))
        return [] if got == _D2_BASE_VALUE_SHA else [
            "真仓布局：活表 canonical sha=%s ≠ 搬前钉值 %s" % (got, _D2_BASE_VALUE_SHA)]
    ns: dict = {}
    with open(base, encoding="utf-8") as fh:
        exec(compile(fh.read(), base, "exec"), ns)              # noqa: S102
    old = ns["WEAPON_EFFECT_DATA"]
    import content.mech.we_data as _W
    new = _W.WEAPON_EFFECT_DATA
    out: list = []
    if list(old) != list(new):
        out.append("键序不同：base=%s live=%s" % (list(old)[:3], list(new)[:3]))
    for k in old:
        if k not in new:
            out.append("live 缺键 %r" % (k,))
            continue
        a = [(f, repr(v), type(v).__name__) for f, v in old[k].items()]
        b = [(f, repr(v), type(v).__name__) for f, v in new[k].items()]
        if a != b:
            out.append("%s 不等：base=%r live=%r" % (k, a, b))
    return out


def test_aux():
    print("【9. aux 指纹：4 张数据表 + 装配契约 + 引擎侧（读 base/pkg 基线）】")
    aux = _PIN.get("aux") or {}
    check("aux 指纹段数 == 11（4 数据 + 1 契约 + 4 源文件基线 + 2 引擎）",
          len(aux) == 11, sorted(aux))
    bad = [k for k, want in aux.items() if k.startswith("data:") and k != _D2_MOVED_DATA
           and want != _file_sha(k.split(":", 1)[1])]
    check("其余数据表实跑 sha256 == _PIN['aux']['data:*']（数据面零改动）", not bad, bad)
    badv = _we_value_diff()
    check("★ D2：we_data.py 活表 == base/pkg 搬前字面量表（键序/值/类型逐名相等，diff 空）",
          not badv, badv[:3])
    badc = [k for k, want in aux.items() if k.startswith("contract:")
            and want != _file_sha(k.split(":", 1)[1])]
    check("`content/apply.py` sha256 == aux（装配契约未被本线动过）", not badc, badc)
    bade = []
    for k, want in aux.items():
        if k.startswith("engine:"):
            rel = k.split(":", 1)[1]
            p = os.path.join(os.environ["GWEN_FRAMEWORK_DIR"], *rel.split("/"))
            got = hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.isfile(p) \
                else "<missing>"
            if got != want:
                bade.append((k, want[:12], got[:12]))
    check("引擎侧（effect_triggers / declarations）sha256 == aux（本线引擎零改动）",
          not bade, bade)


def _check_readonly(before):
    print("【10. 只读：跑完全程 4 源文件 + 4 数据表 sha256 前后一致】")
    after = {f: _file_sha(f) for f in READONLY_FILES}
    bad = [f for f in READONLY_FILES if before[f] != after[f]]
    check("跑完全程 %d 个文件 sha256 前后一致" % len(READONLY_FILES), not bad, bad)
    for f in READONLY_FILES:
        print("     %-38s %s" % (f, after[f]))


# ══════════════════════════════════════════════════════════════════════════════
# 12. 判据 10：apply_game_content 六步顺序 + 幂等保险丝
# ══════════════════════════════════════════════════════════════════════════════
def test_apply_contract():
    print("【11. 装配契约：六步顺序 + `_content_applied` 保险丝】")
    p = _pkg_file("content/apply.py")
    tree = ast.parse(open(p, encoding="utf-8").read())
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == "apply_game_content"), None)
    check("AST：`apply_game_content` 是模块级函数", fn is not None)
    steps, sub_mark, get_mark = [], False, False
    if fn is not None:
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "_step" and node.args \
                    and isinstance(node.args[0], ast.Constant):
                steps.append(node.args[0].value)
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Name) \
                    and node.slice.id == "_MARK":
                sub_mark = True        # actor[_MARK] = True（落标记）
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "get" and node.args \
                    and isinstance(node.args[0], ast.Name) \
                    and node.args[0].id == "_MARK":
                get_mark = True        # if actor.get(_MARK): return actor（保险丝）
    check("六步顺序 == [install, equip, mech, bar, cond, element, food]",
          steps == ["install", "equip", "mech", "bar", "cond", "element", "food"], steps)
    check("幂等保险丝两处仍在：`actor[_MARK] = True` 与 `if actor.get(_MARK)`",
          sub_mark and get_mark, (sub_mark, get_mark))

    mod_marks = [n.value.value for n in tree.body
                 if isinstance(n, ast.Assign) and len(n.targets) == 1
                 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "_MARK"
                 and isinstance(n.value, ast.Constant)]
    check("模块级 `_MARK == '_content_applied'`", mod_marks == ["_content_applied"], mod_marks)

    # 活探针：空 actor 直接返回（不落标记）+ 二次调用整链跳过
    from content import apply as APPLY
    check("活探针：`apply_game_content({})` 原样返回且不落标记",
          APPLY.apply_game_content({}) == {} and APPLY._MARK == "_content_applied")
    a = {"equipment": {}, "bonus": {"panel": {}, "cap": {}, "cost": {}}}
    APPLY.apply_game_content(a)
    first = set(a)
    APPLY.apply_game_content(a)
    check("活探针：二次调用整链跳过（键集合不变 + 标记在位）",
          set(a) == first and a.get(APPLY._MARK) is True, sorted(a))


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("==" * 36)
    print("U1-D2 冻结门禁③：触发器主四件（equip 5 / food_proc 4 / team_procs 1 / worldboss 2 = 12 段，甲 12）")
    print("==" * 36)
    print("phase = %r · GWEN_GAME_DB = %s" % (PHASE, os.environ.get("GWEN_GAME_DB")))
    print("冻结基线 = base/pkg 切片；活实现 = %s" % PKG_ROOT)
    before = {f: _file_sha(f) for f in READONLY_FILES}
    test_frozen_pins()
    test_grids()
    test_idem()
    test_gm_bool()
    test_owner()
    test_equip_names()
    test_divergences()
    test_teeth()
    test_aux()
    test_apply_contract()
    _check_readonly(before)
    print("\n" + "-" * 46)
    print("结果：通过 %d / 共 %d" % (PASS, PASS + FAIL))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  ❌", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
