# -*- coding: utf-8 -*-
"""U1-D2 冻结比对**门禁④**（触发器追加四件）：4 文件 / **9 段**冻结文本 + 双 sha256 + 144 格。

跑法（工作区根；环境变量见 `BRIEF.md` §4）::

    PY="C:/Users/yuyu/AppData/Roaming/uv/tools/astrbot/Scripts/python.exe"
    "$PY" work/pkg/tests/_u1d2_triggers_extra_gen.py --check
    "$PY" work/pkg/tests/test_u1d2_triggers_extra_frozen.py

判据（`design/U1-D2_BATCHES.md` §7 判据表 1–9 + `U1-D2_FROZEN_GATE.md` §5.4 的 144 格）
----------------------------------------------------------------------------------------
 [1] **9 段冻结文本 sha256 全等 `_PIN["frozen"]`** + **活实现 `inspect.getsource` sha256 全等
     `_PIN["live"]`**；`phase == "landed"` 时断言全 9 段（C 栏）`frozen != live`。
 [2] **144 格**（`FROZEN_GATE.md` §5.4，逐格脚本实测）：
     ① 幂等矩阵 4 入口 × {1,2,3} × 2 actor 态 = **24**
     ② `bar_procs` 前插序：1 × 5 桶初始长度 = **5**
     ③ `element_procs` 追加序：2 事件 × 2 标记态 = **4**
     ④ `class_mech` 六处去重键：6 处 × 3 重复 × 4 actor 态 = **72**
     ⑤ 动作体零改动：39 个 `@register_action` 的 `getsource` sha256 = **39**
     合计 **144**。每格都是「旧实现（`_FROZEN_TEXT` 成品字面量 `exec`）↔ 活实现」当场比。
 [3] **口径分歧** ≥1 条/条（`U1-D2_DESIGN.md` §4.3）：① 去重键多口径 · ② 写策略
     （prepend / append / keep / replace）· ⑤ 未知名只告警不抛（本线全写引擎原生名 → 零未知名）
     · ⑥ `compile` 保序（行表序 → 桶内序）。
 [4] **有牙反证** 3 处（前插改追加 / 元素顺序倒置 / `type` 去重改 `action`）→ 对应探针**必须变红**，
     还原后回绿；全程零写盘。
 [5] **只读断言**：跑完全程 4 个源文件 sha256 不变。
 [6] **aux ⑭**：39 个动作体哈希（改动前抓的自在 `_PIN["aux"]`，逐名比）。

⚠ 「旧实现」= `_FROZEN_TEXT` 里的**成品字面量**（由 `tests/_u1d2_triggers_extra_gen.py` 从
   `base/pkg/**` 逐行 `ast` 切片），`exec` 到独立命名空间跑 —— 不是「读代码觉得等价」。
⚠ 刻意**不依赖 pytest**：直接 `python <本文件>`，`sys.exit(1 if FAIL else 0)`。
⚠ 「动作体零改动」的口径修正见 `out/LANDING.md`：39 个 `@register_action` 里有 **2 个**
  （`class_stance_guard_enter` / `class_guard_stance_enter`）**含挂载点**，作业书 §2 要求改其挂载
  动作 ⇒ 其 `getsource` 必然变。本门禁因此断言：**37 个零改动逐字节不变** + 那 2 个用
  「锚点归一化」（挂载块前后文本逐字相等）证明**只换了挂载动作**。
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import inspect
import json
import os
import sys
import tempfile
import types

# ══════════════════════════════════════════════════════════════════════════════
# 0. 装配：包根 / 引擎根 / 宿主壳根（`_paths` 单点）+ 独立私有库 + shim_astrbot
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
_DB_DIR = os.path.join(tempfile.gettempdir(), "gwen_test_u1d2_L7")
os.makedirs(_DB_DIR, exist_ok=True)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_DB_DIR, "test_u1d2_L7.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
os.environ.setdefault("GWEN_FRAMEWORK_DIR", os.path.join(LANE_ROOT, "work", "eng"))
os.environ.setdefault("GWEN_HOST_DIR", os.path.join(LANE_ROOT, "work", "host"))
_shim = os.path.join(_HERE, "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

import _paths                                                             # noqa: E402
import _engine_harness as H                                              # noqa: E402

from content.mech import bar_procs as BP                                 # noqa: E402
from content.mech import cond_procs as CP                                # noqa: E402
from content.mech import element_procs as EP                             # noqa: E402
from content.mech import class_mech as CM                                # noqa: E402
from content import skills as CS                                         # noqa: E402
import saintess_engine.battle.declarations as DECL                       # noqa: E402
from saintess_engine.battle import effect_triggers as ET                 # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []
_COUNT = {"idempotent": 0, "prepend": 0, "element_order": 0, "class_sites": 0,
          "action_bodies": 0}
_COUNTING = True


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


def _bump(k):
    if _COUNTING:
        _COUNT[k] += 1


#: 读盘白名单（判据 [5]；全程零写盘）
READONLY_FILES = (
    "content/mech/bar_procs.py", "content/mech/cond_procs.py",
    "content/mech/element_procs.py", "content/mech/class_mech.py",
)

#: 本线实际改动的 4 个文件（真仓 cp 清单用）
CHANGED_FILES = READONLY_FILES

# >>> _u1d2_triggers_extra_gen (auto) >>>

# ⚠ 本块由 `tests/_u1d2_triggers_extra_gen.py` 生成 —— 手工改动 = 门禁失去安全网。
# 冻结侧读 `base/pkg/**`（改动前基线）；`_PIN["live"]` 由 --emit-live 重生成。

_FROZEN_TEXT = {
    'content/mech/bar_procs.py::apply_bar_procs': 'def apply_bar_procs(actor: dict) -> None:\n    """装配：扫 actor 已学技能 → 命中 BAR_INJECT_FIELDS 字段则挂 skill_hit 注入。\n\n    学什么挂什么，零噪音（未学推条技能的单位不挂，不产生空转触发器）。\n\n    ⚠️ 顺序契约：注入条目 **insert(0)** 排 skill_hit 首位——被动族同一事件的后置段\n    （如破绽·极 passive_bar_extend 延长免疫窗口）依赖「本次命中先推条并触发」，\n    排在注入之后才能读到触发后的免疫状态（旧 battle.py `_skill_hit_settle` 同序）。\n    """\n    cn = actor.get("class_name") or ""\n    names = actor.get("learned_skills") or []\n    if not cn or not names:\n        return\n    try:\n        from .element_data import BAR_INJECT_FIELDS\n    except Exception:\n        return\n    from ..apply import _SKILL_LOOKUP as _PKG_SKILLS\n    skill_info = _PKG_SKILLS.skill_info\n    trig = actor.setdefault("triggers", {})\n    for field, spec in (BAR_INJECT_FIELDS or {}).items():\n        key = (spec or {}).get("key") if isinstance(spec, dict) else ""\n        if not key:\n            continue\n        per_hit = bool((spec or {}).get("per_hit")) if isinstance(spec, dict) else False\n        found = False\n        for s in names:\n            try:\n                info = skill_info(cn, s)\n            except Exception:\n                info = None\n            if info and info.get(field):\n                found = True\n                break\n        if not found:\n            continue\n        lst = trig.setdefault("skill_hit", [])\n        if not any(isinstance(e, dict) and e.get("action") == "bar_gain"\n                   and e.get("key") == key for e in lst):\n            entry = {"action": "bar_gain", "key": key, "field": field}\n            if per_hit:\n                entry["per_hit"] = True\n            lst.insert(0, entry)\n',
    'content/mech/cond_procs.py::apply_cond_procs': 'def apply_cond_procs(actor: dict) -> None:\n    """装配：扫已学技能 → 存在带 cond 的技能才挂 dmg_calc/heal_calc 条件乘区。"""\n    cn = actor.get("class_name") or ""\n    names = actor.get("learned_skills") or []\n    if not cn or not names:\n        return\n    from saintess_engine.battle.formulas import skill_cond_mult\n    from ..apply import _SKILL_LOOKUP as _PKG_SKILLS, skill_level_of\n    skill_info = _PKG_SKILLS.skill_info\n    has_cond = False\n    for s in names:\n        try:\n            info = skill_info(cn, s)\n        except Exception:\n            info = None\n        if info and isinstance(info.get("cond"), dict):\n            has_cond = True\n            break\n    if not has_cond:\n        return\n    trig = actor.setdefault("triggers", {})\n    for ev in ("dmg_calc", "heal_calc"):\n        lst = trig.setdefault(ev, [])\n        if not any(isinstance(e, dict) and e.get("action") == "skill_cond_mult"\n                   for e in lst):\n            lst.append({"action": "skill_cond_mult"})\n',
    'content/mech/element_procs.py::apply_element_procs': 'def apply_element_procs(actor: dict) -> None:\n    """学了带 `element` / `element_from_main` / `element_switch` 的技能才挂元素机制。\n\n    挂载点：\n    - `dmg_calc` → `elem_reaction` + `elem_counter`（两轴乘区）\n    - `act_cast` → `elem_conv_apply`（元素转化的挂印改写，仅在学了元素流转时挂）\n    幂等：重复装配只留一条。\n    """\n    if not isinstance(actor, dict):\n        return\n    cn = actor.get("class_name") or ""\n    names = actor.get("learned_skills") or []\n    if not cn or not names:\n        return\n    from ..apply import _SKILL_LOOKUP as _PKG_SKILLS\n    skill_info = _PKG_SKILLS.skill_info\n    has_elem = has_switch = False\n    for s in names:\n        try:\n            info = skill_info(cn, s)\n        except Exception:\n            info = None\n        if not isinstance(info, dict):\n            continue\n        if info.get("element") or info.get("element_from_main"):\n            has_elem = True\n        if str(info.get("effect") or "") == "element_switch":\n            has_switch = True\n        if has_elem and has_switch:\n            break\n    if not has_elem and not has_switch:\n        return\n    trig = actor.setdefault("triggers", {})\n    if has_elem:\n        lst = trig.setdefault("dmg_calc", [])\n        # 顺序铁律：**克制先判、反应后算**——反应会清印（`clear: True`），\n        #   若反应先跑，克制判定（读目标印记/状态）就会因印记已被清而失效\n        #   （实测：冰打火印+雷印目标，反应先清雷印 → 冰克雷不触发）。\n        for act in ("elem_counter", "elem_reaction"):\n            if not any(isinstance(e, dict) and e.get("action") == act for e in lst):\n                lst.append({"action": act})\n    # 元素转化订阅：不仅学「元素流转」要挂——元素转化标记也可能来自其它来源\n    #   （装备/消耗品/后续机制），`elem_conv_apply` 无标记时零行为，故零成本常挂。\n    if has_elem or has_switch:\n        lst2 = trig.setdefault("act_cast", [])\n        if not any(isinstance(e, dict) and e.get("action") == "elem_conv_apply" for e in lst2):\n            lst2.append({"action": "elem_conv_apply"})\n',
    'content/mech/class_mech.py::_melody_ensure_tick': 'def _melody_ensure_tick(actor, kind: str) -> None:\n    """时钟驱动型减益旋律自安装订阅（首次唱响时挂，幂等——同破绽条\n    battle_bar_procs._ensure_tick 惯例，零噪音）：time_advance →\n    class_melody_dirge_tick（按节流周期对敌施控）。\n\n    面板类减益旋律（e_atk/e_spd/e_spd_hit/e_all）由驻留条目本身生效 → 不挂。\n    """\n    if _MELODY_ENEMY_AURA_MAP.get(kind) is not None:\n        return\n    lst = actor.setdefault("triggers", {}).setdefault("time_advance", [])\n    if not any(isinstance(e, dict) and e.get("action") == "class_melody_dirge_tick"\n               for e in lst):\n        lst.append({"action": "class_melody_dirge_tick"})\n',
    'content/mech/class_mech.py::class_stance_guard_enter': '@register_action("class_stance_guard_enter")\ndef class_stance_guard_enter(battle, caster, target, params, logs):\n    """增益技 effect=stance_guard（守护姿态 v153 铁誓线）：写守护姿态态 + 挂反击。\n\n    语义：守护姿态「受击反击 40%、每刻积攒 0.2 战意」——effects[stance_guard]\n    持续 turns 刻（技能 buff_turns）；反击 = on_taken trigger（class_stance_counter，\n    态在才反击 40%，防重复挂）；每刻 +0.2 战意需 tick 装配点标缺口。\n    """\n    actor = caster if caster is not None else target\n    if actor is None:\n        return\n    try:\n        from saintess_engine.battle import now_of\n        now = now_of(battle)\n    except Exception:\n        now = 0.0\n    turns = max(1, int(params.get("turns") or 0) or 8)\n    actor.setdefault("effects", {})["stance_guard"] = {\n        "stacks": 1, "expire": now + turns}\n    # 挂受击反击 trigger（幂等——同 key 不重复挂）\n    trig = actor.setdefault("triggers", {})\n    lst = trig.setdefault("on_taken", [])\n    if not any(isinstance(t, dict) and t.get("type") == "class_stance_counter"\n               for t in lst):\n        lst.append({"type": "class_stance_counter", "chance": 0.40,\n                    "atk_pct": 1.0, "label": "守护姿态"})\n    logs.append(f"🛡️ 进入守护姿态：受击反击 40%（{turns} 刻）！")\n',
    'content/mech/class_mech.py::class_guard_stance_enter': '@register_action("class_guard_stance_enter")\ndef class_guard_stance_enter(battle, caster, target, params, logs):\n    """增益技 effect=guard_stance（守御姿态 v153 L992）：写姿态态 + 挂受击减伤乘区。\n\n    语义（v153 L992）：「姿态：受伤 −25%，但推条值 −30%」\n    - 受伤 −25%：数值单源 = EFFECT_RULES[guard_stance].stat_scale.reduce——saintess_engine\n      伤害路径不消费 st["reduce"]（stats 只写、instance 仅展示），故装配时挂\n      taken_calc 乘区钩子（passive_taken_reduce has_effect 段；形态同 warrior\n      class_stance_guard_enter「写态 + 挂 trigger」）。\n    - ⚠️ 推条值 −30%：推条注入端（battle_bar_procs.bar_gain）直读技能 shaken_gain，\n      无按姿态的乘区通道 → 未落地（缺口）。\n    态持续 turns 刻（技能 buff_turns，经 actions._do_buff 注入 params.turns）。\n    """\n    owner = caster if isinstance(caster, dict) else target\n    if owner is None:\n        return\n    key = params.get("type") or ""\n    if not key:\n        return\n    try:\n        turns = int(params.get("turns") or 0)\n    except Exception:\n        turns = 0\n    if turns <= 0:\n        return  # 缺字段 = 无此行为（零默认值铁律）\n    from saintess_engine.battle.state_effects import state_def\n    cfg = state_def(key) or {}\n    reduce_v = float((cfg.get("stat_scale") or {}).get("reduce") or 0)\n    try:\n        from saintess_engine.battle import now_of\n        now = now_of(battle)\n    except Exception:\n        now = 0.0\n    owner.setdefault("effects", {})[key] = {"stacks": 1, "expire": now + turns}\n    if reduce_v > 0:\n        lst = owner.setdefault("triggers", {}).setdefault("taken_calc", [])\n        if not any(isinstance(t, dict)\n                   and (t.get("judge") or {}).get("key") == key for t in lst):\n            lst.append({"type": "passive_taken_reduce",\n                        "judge": {"kind": "has_effect", "key": key},\n                        "reduce": reduce_v, "label": cfg.get("name") or key})\n    logs.append(f"🪨 进入{cfg.get(\'name\') or key}：受伤 −{int(reduce_v * 100)}%（{turns} 刻）！")\n',
    'content/mech/class_mech.py::apply_class_channels': 'def apply_class_channels(actor: dict, rules: dict) -> None:\n    """EFFECT_RULES 资源条目 channels 声明 → actor.triggers 事件钩子（并入 apply_class_mech）。\n\n    对每个声明了 channels 的资源条目（归属职业 start_classes 命中才装——防白拿）：\n    时机名 → saintess_engine 事件 → 挂 class_res_channel_gain 生产动作（gain 值由声明给，\n    cap clamp 动作侧查 EFFECT_RULES）。未映射时机名静默跳过（版本漂移保护，同\n    affix 翻译器缺口词条行为）。装配器零资源 key 硬编码——渠道全由声明驱动。\n\n    渠道值形态：`时机: 2`（无条件简写）或 `时机: {"gain": 1, "when": [judge...]}`\n    （条件攒取——when 谓词在动作入口求值，见 _when_ok）。\n    """\n    if not actor:\n        return\n    cn = actor.get("class_name") or ""\n    trig = actor.setdefault("triggers", {})\n    for rk, rc in (rules or {}).items():\n        if not isinstance(rc, dict):\n            continue\n        ch = rc.get("channels")\n        if not isinstance(ch, dict) or not ch:\n            continue  # 无渠道声明 = 无此行为（零默认值铁律）\n        sc = rc.get("start_classes") or []\n        if sc and cn not in sc:\n            continue\n        name = rc.get("name") or rk\n        for chan, cv in ch.items():\n            # 渠道值两形态：简写 int/float = 无条件的 gain；dict = {gain, when[...]}（条件攒取）。\n            # 条件按渠道声明而非资源条目——同一资源不同来源条件不同（磐核：受击/每刻看姿态，\n            # 守线技能命中无条件）。\n            if isinstance(cv, dict):\n                gain = cv.get("gain")\n                when = cv.get("when")\n                per_dt = cv.get("per_dt")\n            else:\n                gain, when, per_dt = cv, None, None\n            if not chan or not isinstance(gain, (int, float)) or float(gain) <= 0:\n                continue\n            ev, extra = _CHANNEL_EVENTS.get(chan, (None, None))\n            if ev is None:\n                continue\n            d = {"type": "class_res_channel_gain", "res": rk, "gain": float(gain),\n                 "label": name, "icon": "✦"}\n            d.update(extra)\n            # 条件透传：动作入口按谓词求值（_when_ok）。无声明不写键（零默认值）。\n            if when:\n                d["when"] = when\n            # per_dt 透传（tick 渠道：gain 按事件 dt 缩放——见 class_res_channel_gain）\n            if per_dt:\n                d["per_dt"] = True\n            trig.setdefault(ev, []).append(d)\n',
    'content/mech/class_mech.py::apply_class_passives': 'def apply_class_passives(actor: dict) -> None:\n    """被动 proc 装配（v181.M-passive P1 插件样板）：扫已学 kind=被动 + passive.proc\n    → 查 PASSIVE_PROC 声明表 → 参数化挂 actor.triggers[event]。学什么挂什么防白拿；\n    表未声明 proc → 跳过（记缺口，不硬做）。\n    domain 域（不进 triggers 的静态修正）：cap → 写 actor.bonus.cap[key] += add\n    （资源上限被动：毒/猎印/魂标 cap——引擎 _cap_of 动态收敛已支持 bonus.cap）；\n    cost → 写 actor.bonus.cost（消耗折扣：mp_pct/mp_flat/res——引擎 _skill_pay_of 折算）。\n    """\n    if not actor:\n        return\n    cn = actor.get("class_name") or ""\n    names = actor.get("learned_skills") or []\n    if not cn or not names:\n        return\n    rules = _passive_proc_rules()\n    if not rules:\n        return\n    from ..apply import _SKILL_LOOKUP as _PKG_SKILLS\n    skill_info = _PKG_SKILLS.skill_info\n    trig = actor.setdefault("triggers", {})\n    _pending: dict = {}  # (event, agg) -> [(proc, entry)] 聚合族暂存（循环后归并单条）\n    for s in names:\n        try:\n            info = skill_info(cn, s)\n        except Exception:\n            info = None\n        if not info or info.get("kind") != "被动":\n            continue\n        p = info.get("passive") or {}\n        proc = p.get("proc") or ""\n        cfg = rules.get(proc)\n        if not isinstance(cfg, dict):\n            continue  # 表未声明 → 记缺口跳过（不硬做）\n        domain = cfg.get("domain") or ""\n        if domain == "cap":\n            # 资源上限被动：bonus.cap[key] += add（cap 修正容器，_cap_of 动态读）\n            key = cfg.get("cap_key") or proc\n            try:\n                add = int(p.get("add", cfg.get("add", 0)) or 0)\n            except Exception:\n                add = 0\n            if add > 0:\n                bonus = actor.setdefault("bonus", {})\n                bonus.setdefault("cap", {})[key] = \\\n                    int((bonus.get("cap") or {}).get(key, 0) or 0) + add\n            # 双通道声明（cap + event，如 soul_mark_cap/poison_cap_up 乘区段）→ 不 continue，fall through\n        if domain == "cost":\n            # 消耗折扣被动：bonus.cost（引擎 _skill_pay_of 折算）。mp_mult（如\n            # 奥术恒常 mp_mult 0.5 = 奥术技能耗蓝-50%）→ 有 cfg.when 判据则放 when\n            # 子条目（限定技能），无 when 才放顶层（无条件全技能）。\n            pct = float(p.get("mp_mult", 0) or 0)\n            when = cfg.get("when")\n            bonus = actor.setdefault("bonus", {})\n            _c = bonus.setdefault("cost", {})\n            if when:\n                _w = dict(when[0]) if isinstance(when, list) and when else {}\n                _w["mp_pct"] = float(_w.get("mp_pct", 0) or 0) + pct\n                _c.setdefault("when", []).append(_w)\n            elif pct > 0:\n                _c["mp_pct"] = float(_c.get("mp_pct", 0) or 0) + pct\n            # cost 域声明无 event → 下方 d.type 空自然 continue\n        d = {"type": cfg.get("action") or "", "judge": cfg.get("judge") or {}}\n        # cfg 声明表非结构字段并入（buff_key 等动作参数——domain 消费过的键除外）\n        for k, v in cfg.items():\n            if k in ("event", "action", "judge", "agg", "domain",\n                     "cap_key", "when", "add", "also"):\n                continue\n            d[k] = v\n        # 被动参数并入（mult 归一 mult/dmg_add/per_layer；label 用技能名）\n        for k, v in p.items():\n            if k in ("proc",):\n                continue\n            d[k] = v\n        d.setdefault("label", info.get("name") or proc)\n        # bar_field：被动自身携带的推条字段（如反震 shaken_gain: 3）→ 装配时解析成\n        # {key, gain}（字段 → bar key 映射 = BAR_INJECT_FIELDS；数值单源 = 技能数据字段，\n        # 不在被动 dict 重填）。缺字段/非正数 = 只做动作其余段（零默认值铁律）。\n        _bf = cfg.get("bar_field")\n        if _bf and not d.get("gain"):\n            try:\n                from .class_data import BAR_INJECT_FIELDS\n                _spec = (BAR_INJECT_FIELDS or {}).get(_bf) or {}\n                _bk = _spec.get("key")\n                _bg = int(info.get(_bf) or 0)\n                if _bk and _bg > 0:\n                    d["key"] = _bk\n                    d["gain"] = _bg\n            except Exception:\n                pass\n        if not d.get("type"):\n            continue\n        ev = cfg.get("event") or ""\n        if not ev:\n            continue\n        # 聚合族（agg：counter 等——多条目合成一条，旧挂点聚合语义）暂存，循环后归并\n        if cfg.get("agg"):\n            _pending.setdefault((ev, cfg.get("agg")), []).append((proc, d))\n        else:\n            trig.setdefault(ev, []).append(d)\n        # also 段：同被动第二条事件钩子（如坚城之姿 taken_calc 减伤 + turn_start 免晕）——\n        # 复用 d 的参数，覆盖 action/judge/额外字段\n        for _also in (cfg.get("also") or []):\n            if not isinstance(_also, dict):\n                continue\n            _d2 = dict(d)\n            _d2["type"] = _also.get("action") or d.get("type")\n            if _also.get("judge"):\n                _d2["judge"] = _also["judge"]\n            for _k in ("ctrl", "ctrl_any", "res", "left_key", "left_init",\n                       "cost_field", "buff_key"):\n                if _also.get(_k) is not None:\n                    _d2[_k] = _also[_k]\n            _ev2 = _also.get("event") or ev\n            if cfg.get("agg"):\n                _pending.setdefault((_ev2, cfg.get("agg")), []).append((proc, _d2))\n            else:\n                trig.setdefault(_ev2, []).append(_d2)\n        # 计数初始化（tenacity 每场 3 次：effects[left_key] = left_init——装配=开战时机）\n        _le = cfg.get("left_key")\n        if _le and cfg.get("left_init") is not None:\n            actor.setdefault("effects", {})[_le] = {"stacks": int(cfg.get("left_init")),\n                                                    "expire": None}\n    # ---- 族级聚合（旧 passive_procs 聚合族语义逐字：多条目 → 单条终值）----\n    for (ev, agg), entries in _pending.items():\n        merged = _merge_agg_entry(agg, entries)\n        if merged is not None:\n            trig.setdefault(ev, []).append(merged)\n',
    'content/mech/class_mech.py::apply_class_mech': 'def apply_class_mech(actor: dict) -> None:\n    """技能 mech 兑现装配（幂等；命令层开战仪式与 equip_proc 并列调用）。\n\n    对 actor 技能集里每个"声明过兑现"的 mech，按声明参数化挂事件钩子：\n    - dmg_calc（伤害前乘区修正）\n    - skill_hit（命中后清层）\n    mode=dmg_mult_clear_target 的条目装配时向效果 dict 写 owner=target（读/清\n    fire ctx 的 target effects）；dmg_mult_clear 缺省 owner=caster（finisher 兼容）。\n    """\n    if not actor:\n        return\n    LAST_ERRORS.clear()\n    try:\n        rules = _mech_cash_rules()\n        if not rules:\n            return\n        trig = actor.setdefault("triggers", {})\n        # v181.M-R2：start_full 资源开局满额（读 EFFECT_RULES 条目 start_full 声明，\n        # 源 core_resources.cls_you_xia v176（原表随 v181.M-R2c 退役，现单源 EFFECT_RULES energy.start_full）\n        # 游侠精力开局满——装配层初始化 effects 条目）\n        try:\n            _full_rules = _effect_rules()\n            _cn = actor.get("class_name") or ""\n            for _rk, _rc in (_full_rules or {}).items():\n                if not (isinstance(_rc, dict) and _rc.get("start_full")):\n                    continue\n                # 开局满额归属职业（start_classes 声明，空 = 不装配）——防非游侠白拿 energy\n                _sc = _rc.get("start_classes") or []\n                if _sc and _cn not in _sc:\n                    continue\n                _cap = int(_rc.get("cap", 0) or 0)\n                if _cap > 0:\n                    actor.setdefault("effects", {})[_rk] = {\n                        "stacks": _cap, "expire": 999999.0}\n        except Exception:\n            pass\n        # v181.M-R2d：职业资源攒取渠道（事件型）——EFFECT_RULES 条目 channels 声明 → 事件钩子。\n        # 核实结论（docs『M-R2d 渠道装配设计』§1）：现网仅牧师 faith 活 key 缺攒端（卸负消费 +\n        # 治疗/受击渠道），rage/cp/chi/element 技能域死 key 不接（EFFECT_RULES 条目注释标注）。\n        try:\n            apply_class_channels(actor, _effect_rules())\n        except Exception:\n            pass  # 渠道装配异常不阻断开战（容错铁律）\n        # v181 磐核：职业资源固有「每核减伤」（EFFECT_RULES[res].stat_scale.reduce 声明）\n        # → taken_calc 承伤乘区（passive_taken_reduce per_core 段）。原因：saintess_engine 伤害\n        # 路径只消费 taken_calc 乘区——stat_scale.reduce 仅由 stats 写入 st["reduce"]\n        # （无消费方，instance 仅展示）。数值单源 = 声明；归属过滤 = start_classes\n        # （**必须**声明 start_classes 才装配——无归属声明的通用效果键如 shield/melody_def\n        # 不接，防误加），零职业名硬编码。\n        try:\n            _cn_r = actor.get("class_name") or ""\n            for _rk, _rc in (_effect_rules() or {}).items():\n                if not isinstance(_rc, dict):\n                    continue\n                _per = float((_rc.get("stat_scale") or {}).get("reduce") or 0)\n                _sc_r = _rc.get("start_classes") or []\n                if _per <= 0 or not _sc_r or _cn_r not in _sc_r:\n                    continue\n                trig.setdefault("taken_calc", []).append(\n                    {"type": "passive_taken_reduce",\n                     "judge": {"kind": "per_core", "res": _rk},\n                     "per_core": _per, "label": _rc.get("name") or _rk})\n        except Exception:\n            pass  # 资源减伤装配异常不阻断开战（容错铁律）\n        # v181.M-R2e B2：牧师信仰负载制装配——faith 条目声明 load_tiers（有档位表才挂，\n        # 零默认值铁律）+ start_classes 归属过滤（非牧师不挂，防白拿 heal_calc 乘区）：\n        #   heal_calc  → 施法时按自身 faith 层查档位 heal_mult 乘入（档位乘区）\n        #   threshold  → 叠层到满 cap 的当次触发过载（清零 + 全队回复）\n        try:\n            _fc = (_effect_rules() or {}).get("faith") or {}\n            if isinstance(_fc.get("load_tiers"), list) and _fc.get("load_tiers"):\n                _fsc = _fc.get("start_classes") or []\n                _cn2 = actor.get("class_name") or ""\n                if not _fsc or _cn2 in _fsc:\n                    trig.setdefault("heal_calc", []).append(\n                        {"type": "class_faith_load_tier", "res": "faith"})\n                    trig.setdefault("threshold", []).append(\n                        {"type": "class_faith_overload", "res": "faith"})\n        except Exception:\n            pass  # 负载制装配异常不阻断开战（容错铁律）\n        # v181.M-melody：诗人旋律装配——class=cls_shi_ren 且学了 melody/melody_chant\n        # 系技能才挂 act_cast 触发器（学什么挂什么，零噪音；非诗人不挂）。\n        try:\n            _has_melody = any(\n                (info.get("mech") in ("melody", "melody_chant"))\n                for _s, info in _learned_mech_skills(actor))\n            if _has_melody:\n                _lst_mel = trig.setdefault("act_cast", [])\n                if not any(isinstance(e, dict) and e.get("type") == "class_melody_act"\n                           for e in _lst_mel):\n                    # ⚠️ 顺序契约：基础叠层排 act_cast 首位——被动族吟唱后置段\n                    # （二重唱 passive_melody_duet 读叠层后的强度）依赖先叠完基础层\n                    _lst_mel.insert(0, {"type": "class_melody_act"})\n        except Exception:\n            pass  # melody 装配异常不阻断开战（容错铁律）\n        # v181.M-passive P1：被动 proc 装配（扫已学 kind=被动 → PASSIVE_PROC 表挂 triggers）\n        try:\n            apply_class_passives(actor)\n        except Exception:\n            pass  # 被动装配异常不阻断开战（容错铁律）\n        # v181 破绽接线：挂敌身条注入装配（BAR_INJECT_FIELDS 声明表 → skill_hit 触发器）\n        try:\n            from .bar_procs import apply_bar_procs\n            apply_bar_procs(actor)\n        except ImportError as _e:\n            _note_error("bar_procs", _e)  # 包内缺件 → 不静默（见本块头注 ③）\n        except Exception:\n            pass  # 挂条装配异常不阻断开战（容错铁律）\n        # v181 cond 接线：技能条件倍率装配（info.cond → dmg_calc/heal_calc 乘区）\n        try:\n            from .cond_procs import apply_cond_procs\n            apply_cond_procs(actor)\n        except ImportError as _e:\n            _note_error("cond_procs", _e)  # 包内缺件 → 不静默（见本块头注 ③）\n        except Exception:\n            pass  # 条件乘区装配异常不阻断开战（容错铁律）\n        mechs = {info.get("mech") for _s, info in _learned_mech_skills(actor)}\n        for mech in mechs:\n            cash = rules.get(mech)\n            if not cash:\n                continue\n            mode = cash.get("mode") or ""\n            # owner 方向由 mode 推断（*_target → target，其余 caster）\n            owner = "target" if mode.endswith("_target") else "caster"\n            if mode.startswith("per_system_clear"):\n                # element_burst_3 元素裁决：每系独立乘区（per_system）\n                dm = {"action": "mech_cash_per_system_mult", "mech": mech,\n                      "key": cash.get("key") or mech,\n                      "per_system": cash.get("per_system") or 0.0,\n                      "label": cash.get("name") or mech}\n                for _k in ("layer_label", "unit", "icon"):\n                    if cash.get(_k):\n                        dm[_k] = cash[_k]\n                if owner == "target":\n                    dm["owner"] = "target"\n                trig.setdefault("dmg_calc", []).append(dm)\n                if cash.get("clear"):\n                    cl = {"action": "mech_cash_clear", "mech": mech,\n                          "key": cash.get("key") or mech}\n                    if owner == "target":\n                        cl["owner"] = "target"\n                    trig.setdefault("skill_hit", []).append(cl)\n                continue\n            if mode == "fury_enter":\n                # 血祭：施放时花 res 层战意 → 进入狂暴（mech_val = 消耗层，技能数据）\n                dm = {"action": "mech_cash_fury_enter", "mech": mech,\n                      "res": cash.get("res") or "zhan_yi",\n                      "mech_val_field": "mech_val",\n                      "label": cash.get("label") or cash.get("name") or mech}\n                if cash.get("icon"):\n                    dm["icon"] = cash["icon"]\n                trig.setdefault("act_cast", []).append(dm)\n                continue\n            if mode not in ("dmg_mult_clear", "dmg_mult_clear_target"):\n                continue\n            key = cash.get("key") or mech\n            _per = float(cash.get("per_layer") or 0.0)\n            # mech 升级（MECH_CASH.upgrade：学某 proc 被动 → 数值增强——链舞 finisher_up\n            # 使终结技每段 10%→16%。proc 挂在 kind=物理 主动技上，装配器不装配，这里查学到）\n            _up = cash.get("upgrade") or {}\n            if isinstance(_up, dict) and _up.get("proc") and _learned_proc(actor, _up["proc"]):\n                _per += float(_up.get("per_layer_add") or 0.0)\n            dm = {"action": "mech_cash_dmg_mult", "mech": mech, "key": key,\n                  "per_layer": _per,\n                  "label": cash.get("name") or mech}\n            for _k in ("layer_label", "unit", "icon"):\n                if cash.get(_k):\n                    dm[_k] = cash[_k]\n            if owner == "target":\n                dm["owner"] = "target"\n            trig.setdefault("dmg_calc", []).append(dm)\n            # 连段阈值必暴（cash.crit_at）：act_cast 写一次性出手态（先于伤害管线）\n            if cash.get("crit_at"):\n                trig.setdefault("act_cast", []).append(\n                    {"action": "mech_cash_finisher_crit", "mech": mech, "key": key,\n                     "crit_at": float(cash.get("crit_at") or 0),\n                     "hit_key": "finisher_crit_ready"})\n            if cash.get("clear"):\n                cl = {"action": "mech_cash_clear", "mech": mech, "key": key}\n                if owner == "target":\n                    cl["owner"] = "target"\n                if cash.get("clear_extra"):\n                    cl["clear_extra"] = cash["clear_extra"]\n                trig.setdefault("skill_hit", []).append(cl)\n    except Exception:\n        pass  # 技能机制装配异常不阻断开战（容错铁律）\n',
}

_PIN = {
    'phase': 'landed',
    'frozen': {
        'content/mech/bar_procs.py::apply_bar_procs': '3e1a13799f18a4f7d93ee52aaac8e2fffb2993fbe1fc273f1e79827e26782f30',
        'content/mech/cond_procs.py::apply_cond_procs': '341faa80d822131320bf81d6d8a840839b6c488f192221e2402759089f99f1dc',
        'content/mech/element_procs.py::apply_element_procs': '801a0fa4f61b1392157ed3e66284e020901e65fb390f49b85e27cf28508c87e7',
        'content/mech/class_mech.py::_melody_ensure_tick': 'cfe5068bd72fcfa520cb1425a1e8aa2164f9acddf0f8d531dfd9c7dec72c224b',
        'content/mech/class_mech.py::class_stance_guard_enter': 'e9f80aa38ef2261ac6d3c96dc000be53ff2755d2c6fc96f02092db53e5a8d2de',
        'content/mech/class_mech.py::class_guard_stance_enter': '8eea84e72f6f9b0598bdd64b4ced8fba77fae24e99d0faf3ed2615ffb53f130f',
        'content/mech/class_mech.py::apply_class_channels': '5eacb60626f7ea6c609352f8ce1a2f087708baca35fe69e43479d4dcf9e5edf1',
        'content/mech/class_mech.py::apply_class_passives': '5471cced46ea0e3984bf69b81938d0eee412b04f13168952f7c379b2434782ea',
        'content/mech/class_mech.py::apply_class_mech': 'd127924ba577d96d587565bd74532ac5399efb4873e4c95f2196bc208e1bc235',
    },
    'live': {
        'content/mech/bar_procs.py::apply_bar_procs': '1a4ce68537c8a250dc8ad7e467210c2e2671178de982499177cc9d25b8dad8a0',
        'content/mech/cond_procs.py::apply_cond_procs': '0767c02518cacd010d75f62900b383f97d2b76156370dd12e579cfe460855fa7',
        'content/mech/element_procs.py::apply_element_procs': 'd51efa7c3a34dd22a27791ebed50d29a3c98c68336bf5eff139b38a4e2aa2455',
        'content/mech/class_mech.py::_melody_ensure_tick': 'f9b42974c12e01e29b70e943a8fd7ce3aa659a33c7d676e0e2cb391d2c764af6',
        'content/mech/class_mech.py::class_stance_guard_enter': '516c6ba5f0985aa34dd57ed766c671056bf45b8c8d0f8069f8f5bb70ed0cf335',
        'content/mech/class_mech.py::class_guard_stance_enter': 'fff7fa3a792657c1b831425fcdb596301b1317187c89da27f683dfc3ed93530e',
        'content/mech/class_mech.py::apply_class_channels': '8955439388152e79adb8096643735347f410748c756dca63199716f7e15080b6',
        'content/mech/class_mech.py::apply_class_passives': '051d6d5c84382fdeca35718d4611d3d7181287b7b8d9c7d0822f7d97223883db',
        'content/mech/class_mech.py::apply_class_mech': '8f17bdd67ab2424856a09617181359289a6e36a065e2a7ddb8704b1456723298',
    },
    'aux': {
        'class_mech_action::class_faith_load_tier': 'c5aa3169a92dfbd2a4fe06c5b355634d9034c78d884b99fc5b4a6f370b82a913',
        'class_mech_action::class_faith_overload': 'fcfb04313cdeca887dd6a7e2852a64445b36784444e165446329457dee8800ab',
        'class_mech_action::class_guard_stance_enter': '8eea84e72f6f9b0598bdd64b4ced8fba77fae24e99d0faf3ed2615ffb53f130f',
        'class_mech_action::class_melody_act': 'a6270e3cdffe4e724b6270f15a24f47747044407577216eaaa54ab399db3c834',
        'class_mech_action::class_melody_dirge_tick': '5df292e9a4fdd8064b41cc6e7167a5d0fc1a10430e08ff55218b211a264ab6b5',
        'class_mech_action::class_res_channel_gain': '12d2f40c4f9452bd4308ec5ff2ce413f54fed6ca64947b275685694042c86695',
        'class_mech_action::class_shadow_dance_enter': '2291de751b7104ea16351f6f0c336a106c7bb3b666bdc04a5b0853f7bfc79da0',
        'class_mech_action::class_stance_counter': 'c5fcac4a15b9cbb774612e028cb4e27bcdf5af5a829cf814a3827facecfa93f7',
        'class_mech_action::class_stance_guard_enter': 'e9f80aa38ef2261ac6d3c96dc000be53ff2755d2c6fc96f02092db53e5a8d2de',
        'class_mech_action::mech_cash_clear': '0af618be891a0768e86b87afa51dbd9e177d021dd7f5343c7645025a1d601834',
        'class_mech_action::mech_cash_dmg_mult': 'f155b39088e3c225d378f25df18c4b4d8aa1eff7971f9acb1a2a1d9620b1ca33',
        'class_mech_action::mech_cash_finisher_crit': '6adb90d5cf6165cfef5ad64dbef0c466587d7d8b0ac205704ec772bb26e625a9',
        'class_mech_action::mech_cash_fury_enter': '1613fb0829cfaa2b42dda14bfd7ec88fb61da256dd3d4a9181ba02450809ec8a',
        'class_mech_action::mech_cash_per_system_mult': 'b6fd9289d6b7b211fb73967b0681173835a01eda052d1134206cb2dfbec59801',
        'class_mech_action::passive_bar_decay_half': 'eab2211255595320aacd6e299453e653e058a330550c6495ac534d1b7f3b1c0c',
        'class_mech_action::passive_bar_extend': '3bbeb7694bd93ba31bdccdef3f34c78011ab9ac04d18084a570b5237e7ffea52',
        'class_mech_action::passive_cc_break': '92835ef65de04ba69cc2084b4aa5a8ea01f32351a7361fe34fcf4b0f0975b205',
        'class_mech_action::passive_cc_clear': '4102d0bd99ca32d2f30bf34d44b2f3aae63e25a50325b04c05cf93ff8412be02',
        'class_mech_action::passive_cond_crit': 'e0cb6adb56f8799db75f7227be153be196f716a53b801f10d6c66c5d9e127266',
        'class_mech_action::passive_counter': '3917519b84c85f28ee356abfd48fb725c875fc6421f241a93c06d5eff9efb504',
        'class_mech_action::passive_ctrl_extend': '814e7c70f6a5a04e2e9e6a36dc0b853576f6f2d9789dd2e6294a0539dc97bdbf',
        'class_mech_action::passive_dmg_mult': '380361bd7b8f8d6dc05de5dd3088ea86a2cca6ae95c511d4cc9491a260aa1a7c',
        'class_mech_action::passive_dot_mult': '406f286bd6f2cceebfb7bf81da2567c715942ead94cc4c2639c6ab8493688afb',
        'class_mech_action::passive_element_core_crit': 'b2fc65c54542cc2816473c30aae312004dea5239f9c2b01c9b5b16282823dafa',
        'class_mech_action::passive_heal_overflow_shield': '1dc7670f8d4e02b199992cd2a29d4cf3a1ce7accde7637b0e505d52eabae05d5',
        'class_mech_action::passive_kill_gain': 'a38359bf83fb2d0b98c2d96e55f7e5e88fc16d21fbe4b36d4d14771fb2ff461f',
        'class_mech_action::passive_lian_duan_soft': '0867bd36250ac0e2038372f733063a64f67604b0dd0bc39847625910ade0abf2',
        'class_mech_action::passive_lifesteal_buff': 'bff07b2ef9ae782015da0c9d7d6fe40f978f325a296002c588ecee311eb507ae',
        'class_mech_action::passive_low_hp_core': '50db15e1ec1c8dbb8177fbb751d5cff27488ea653140ac2c3e3b147f44dc81df',
        'class_mech_action::passive_mark_enhance': '0a7c2d83b2a431f84803f6332bd5c30ee8711b884eae49ca90c13aad5fc865da',
        'class_mech_action::passive_melody_duet': 'e1ba9085c522e1a65173ec5843492195046cb0af77203b47c560beca5dcd4138',
        'class_mech_action::passive_overflow_shield': 'f56ecf259b94980164f1e3759fe44ba9f7adcce03472d64f570158b77148894e',
        'class_mech_action::passive_poison_spread': 'e2aaabbfac1be8abf039f5812a7c979ce940a038cc8756f1a59831d27d5609c4',
        'class_mech_action::passive_poison_weaken': 'c572f9aa4b6dc9ef915d19a0a97c3e27594347e147bf621e075295ac0e6869d3',
        'class_mech_action::passive_res_gain_turn': '4d76114c61a6eb3c224d2ffd3e8608dbf2c021a7d201cde880f5345444bb48d8',
        'class_mech_action::passive_revive_berserk': '8d05ed2f98cd97bb949db0349ad2f2fda3e9f0303d8ccf3c631ff64915ab89d1',
        'class_mech_action::passive_revive_guard': '4e8c79e42845fd3b564612fa69c7fe28885d6b9fbc754486750d1d8717145f3b',
        'class_mech_action::passive_shadow_buff': '75d6446c3dee1e07e218d68e6712ad500d2c04f2a5d93f7ea9f66880ea18bc54',
        'class_mech_action::passive_taken_reduce': '905b4be981614c769bfe86bbb54a21289345c72bc7c52a477ea67921d6e8c6af',
        'class_mech_actions': '06ddd060c33444c732a1ce596f44cd55f8f547efa090eafadb2226e12d94680b',
        'class_mech_actions_37': 'a0c19dde19c1d064ddd89363d0767fea3ba0375456e945b2b614df488bcc4dce',
    },
    'segments': {
        'E': [
        ],
        'C': [
            'content/mech/bar_procs.py::apply_bar_procs',
            'content/mech/cond_procs.py::apply_cond_procs',
            'content/mech/element_procs.py::apply_element_procs',
            'content/mech/class_mech.py::_melody_ensure_tick',
            'content/mech/class_mech.py::class_stance_guard_enter',
            'content/mech/class_mech.py::class_guard_stance_enter',
            'content/mech/class_mech.py::apply_class_channels',
            'content/mech/class_mech.py::apply_class_passives',
            'content/mech/class_mech.py::apply_class_mech',
        ],
    },
    'tier': {
        'content/mech/bar_procs.py::apply_bar_procs': '甲',
        'content/mech/cond_procs.py::apply_cond_procs': '甲',
        'content/mech/element_procs.py::apply_element_procs': '甲',
        'content/mech/class_mech.py::_melody_ensure_tick': '甲',
        'content/mech/class_mech.py::class_stance_guard_enter': '甲',
        'content/mech/class_mech.py::class_guard_stance_enter': '甲',
        'content/mech/class_mech.py::apply_class_channels': '甲',
        'content/mech/class_mech.py::apply_class_passives': '甲',
        'content/mech/class_mech.py::apply_class_mech': '甲',
    },
}
# <<< _u1d2_triggers_extra_gen (auto) <<<

_MODULES = {
    "content/mech/bar_procs.py": BP,
    "content/mech/cond_procs.py": CP,
    "content/mech/element_procs.py": EP,
    "content/mech/class_mech.py": CM,
}


def _key(relpath, symbol):
    return "%s::%s" % (relpath, symbol)


# ══════════════════════════════════════════════════════════════════════════════
# 1. 只读哈希 / 猴补
# ══════════════════════════════════════════════════════════════════════════════
def _pkg_file(relpath):
    return os.path.join(PKG_ROOT, *relpath.split("/"))


def _file_sha(relpath):
    with open(_pkg_file(relpath), encoding="utf-8") as fh:
        return sha256(fh.read())


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


@contextlib.contextmanager
def _patch_many(obj, **kw):
    with contextlib.ExitStack() as st:
        for k, v in kw.items():
            st.enter_context(_Patch(obj, k, v))
        yield obj


# ══════════════════════════════════════════════════════════════════════════════
# 2. 旧实现（frozen 文本 exec 到独立命名空间）
# ══════════════════════════════════════════════════════════════════════════════
def _noop_register(*_a, **_k):
    def _deco(fn):
        return fn
    return _deco


def _old_fn(relpath, symbol, *, register_noop=False):
    """把冻结段 `exec` 成**成品函数对象**（`ns` 独立，不碰活模块）。

    装饰器段（`class_stance_guard_enter` / `class_guard_stance_enter`）用 `register_noop=True`
    ——否则 `exec` 会拿冻结体**覆盖引擎动作注册表的同名登记**（副作用污染）。
    """
    mod = _MODULES[relpath]
    ns = dict(vars(mod))
    if register_noop:
        ns["register_action"] = _noop_register
    text = _FROZEN_TEXT[_key(relpath, symbol)]
    tag = "<frozen:%s>" % _key(relpath, symbol)
    exec(compile(text, tag, "exec"), ns)                                     # noqa: S102
    return ns[symbol]


def _live_fn(relpath, symbol):
    return getattr(_MODULES[relpath], symbol)


def _jsnap(actor):
    return json.dumps(actor, ensure_ascii=False, sort_keys=True)


def _deep(obj):
    return json.loads(json.dumps(obj))


# ══════════════════════════════════════════════════════════════════════════════
# 3. 合成注入面（去重键 / 写策略是本门的**被测对象**，故数据用合成表以便逐态控制）
# ══════════════════════════════════════════════════════════════════════════════
CN = "cls_l7"

SYNTH_SKILLS = {
    (CN, "sk_bar"): {"name": "推条", "shaken_gain": 3},
    (CN, "sk_cond"): {"name": "条件", "cond": {"type": "l7_cond"}},
    (CN, "sk_elem"): {"name": "元素", "element": "fire", "element_from_main": True},
    (CN, "sk_switch"): {"name": "流转", "effect": "element_switch"},
    (CN, "sk_mech_dmg"): {"name": "M1", "mech": "m_dmg"},
    (CN, "sk_mech_fury"): {"name": "M2", "mech": "m_fury"},
    (CN, "sk_mech_sys"): {"name": "M3", "mech": "m_sys"},
    (CN, "sk_melody"): {"name": "歌", "mech": "melody"},
    (CN, "sk_p_main"): {"name": "被1", "kind": "被动", "passive": {"proc": "p_main"}},
    (CN, "sk_p_also"): {"name": "被2", "kind": "被动", "passive": {"proc": "p_also"}},
    (CN, "sk_p_agg1"): {"name": "被3", "kind": "被动",
                        "passive": {"proc": "counter_chance", "chance": 0.35, "mult": 0.8}},
    (CN, "sk_p_agg2"): {"name": "被4", "kind": "被动",
                        "passive": {"proc": "counter_up", "chance_add": 0.1, "dmg_add": 0.2}},
}

SYNTH_MECH = {
    "m_dmg": {"name": "M1", "mode": "dmg_mult_clear", "key": "k1", "per_layer": 0.1,
              "clear": True, "crit_at": 4, "layer_label": "层", "unit": "层", "icon": "🔪"},
    "m_fury": {"name": "M2", "mode": "fury_enter", "res": "zhan_yi",
               "label": "血祭", "icon": "🔥"},
    "m_sys": {"name": "M3", "mode": "per_system_clear_target", "key": "k3", "per_system": 0.2,
              "clear": True, "layer_label": "印", "unit": "枚", "icon": "⚖️"},
}

SYNTH_EFFECT = {
    "energy": {"start_full": True, "cap": 10, "start_classes": [CN], "name": "精力"},
    "guard_core": {"stat_scale": {"reduce": 0.03}, "start_classes": [CN], "name": "磐核"},
    "faith": {"load_tiers": [{"heal_mult": 1.5}], "start_classes": [CN], "name": "信仰"},
    "chan_res": {"channels": {
        "skill_hit": 1,
        "taken": {"gain": 1, "when": [{"judge": {"kind": "has_effect", "key": "guard_stance"}}]},
        "tick": {"gain": 0.4, "per_dt": True}},
        "start_classes": [CN], "name": "渠"},
}

SYNTH_PROC = {
    "p_main": {"event": "on_taken", "action": "passive_taken_reduce",
               "judge": {"kind": "has_effect", "key": "guard_stance"}, "reduce": 0.1},
    "p_also": {"event": "act_cast", "action": "passive_cond_crit", "judge": {"kind": "res_ge"},
               "also": [{"event": "turn_start", "action": "passive_res_gain_turn"}]},
    "counter_chance": {"event": "skill_hit", "action": "passive_counter", "agg": "counter"},
    "counter_up": {"event": "skill_hit", "action": "passive_counter", "agg": "counter"},
}


def _synth_skill_info(cn, s):
    return SYNTH_SKILLS.get((cn, s))


@contextlib.contextmanager
def _SYNTH():
    """把四张合成表注入活模块（冻结段 `exec` 时也吃同一份 —— 两侧同注入面）。"""
    with _patch_many(
        CS, skill_info=_synth_skill_info,
    ), _patch_many(
        CM,
        _mech_cash_rules=lambda: SYNTH_MECH,
        _effect_rules=lambda: SYNTH_EFFECT,
        _passive_proc_rules=lambda: SYNTH_PROC,
    ):
        yield


def _battle():
    return types.SimpleNamespace(_now=10.0)


#: 四个挂载入口的基态 actor
_ENTRANCES = (
    ("apply_bar_procs", "content/mech/bar_procs.py", "apply_bar_procs",
     {"class_name": CN, "learned_skills": ["sk_bar"]}),
    ("apply_cond_procs", "content/mech/cond_procs.py", "apply_cond_procs",
     {"class_name": CN, "learned_skills": ["sk_cond"]}),
    ("apply_element_procs", "content/mech/element_procs.py", "apply_element_procs",
     {"class_name": CN, "learned_skills": ["sk_elem"]}),
    ("apply_class_mech", "content/mech/class_mech.py", "apply_class_mech",
     {"class_name": CN,
      "learned_skills": ["sk_mech_dmg", "sk_mech_sys", "sk_melody", "sk_p_main"]}),
)

_SKILL_ENV = "class_name"          # 合成 actor 只用 class_name + learned_skills


# ══════════════════════════════════════════════════════════════════════════════
# 4. ① 幂等矩阵：4 入口 × {1,2,3} × 2 actor 态 = 24 格
# ══════════════════════════════════════════════════════════════════════════════
def _probe_idempotent():
    bad = []
    with _SYNTH():
        for label, relpath, symbol, base in _ENTRANCES:
            for repeat in (1, 2, 3):
                for sidx in (0, 1):
                    seed = _deep(base)
                    if sidx == 1:
                        seed.setdefault("triggers", {}).setdefault(
                            "dmg_calc", []).append({"action": "l7_other", "key": "x"})
                    a_old, a_new = _deep(seed), _deep(seed)
                    f_old = _old_fn(relpath, symbol)
                    f_new = _live_fn(relpath, symbol)
                    for _ in range(repeat):
                        f_old(a_old)
                        f_new(a_new)
                    if _jsnap(a_old) != _jsnap(a_new):
                        bad.append((label, repeat, sidx, _jsnap(a_old), _jsnap(a_new)))
                    _bump("idempotent")
    return bad


# ══════════════════════════════════════════════════════════════════════════════
# 5. ② `bar_procs` 前插序（1 × 5 桶初始长度 = 5 格）+ ③ 元素追加序（2 × 2 = 4 格）
# ══════════════════════════════════════════════════════════════════════════════
_BAR_ENTRY = {"action": "bar_gain", "key": "shaken", "field": "shaken_gain", "per_hit": True}


def _probe_prepend():
    bad = []
    with _SYNTH():
        f_old = _old_fn("content/mech/bar_procs.py", "apply_bar_procs")
        f_new = _live_fn("content/mech/bar_procs.py", "apply_bar_procs")
        for n in range(5):
            seed = {"class_name": CN, "learned_skills": ["sk_bar"],
                    "triggers": {"skill_hit": [{"action": "l7_other", "key": "o%d" % i}
                                               for i in range(n)]}}
            a_old, a_new = _deep(seed), _deep(seed)
            f_old(a_old)
            f_new(a_new)
            b_old = a_old["triggers"]["skill_hit"]
            b_new = a_new["triggers"]["skill_hit"]
            if b_old != b_new:
                bad.append(("bar桶不等", n, b_old, b_new))
            if b_new[:1] != [_BAR_ENTRY]:
                bad.append(("新条目不在桶首", n, b_new[:2]))
            _bump("prepend")
    return bad


def _probe_element_order():
    bad = []
    states = (("has_elem", ["sk_elem"]), ("has_switch", ["sk_switch"]))
    with _SYNTH():
        f_old = _old_fn("content/mech/element_procs.py", "apply_element_procs")
        f_new = _live_fn("content/mech/element_procs.py", "apply_element_procs")
        for label, skills in states:
            for ev in ("dmg_calc", "act_cast"):
                seed = {"class_name": CN, "learned_skills": list(skills)}
                a_old, a_new = _deep(seed), _deep(seed)
                f_old(a_old)
                f_new(a_new)
                t_old = (a_old.get("triggers") or {}).get(ev)
                t_new = (a_new.get("triggers") or {}).get(ev)
                if t_old != t_new:
                    bad.append((label, ev, t_old, t_new))
                if label == "has_elem" and ev == "dmg_calc":
                    if [d.get("action") for d in (t_new or [])] != ["elem_counter",
                                                                     "elem_reaction"]:
                        bad.append(("元素追加序错", label, ev, t_new))
                if label == "has_elem" and ev == "act_cast":
                    if [d.get("action") for d in (t_new or [])] != ["elem_conv_apply"]:
                        bad.append(("转化订阅缺", label, ev, t_new))
                if label == "has_switch" and ev == "dmg_calc" and t_new not in (None, []):
                    bad.append(("仅转化不该挂 dmg_calc", label, ev, t_new))
                _bump("element_order")
    return bad


# ══════════════════════════════════════════════════════════════════════════════
# 6. ④ `class_mech` 六处去重键：6 处 × 3 重复 × 4 actor 态 = 72 格
# ══════════════════════════════════════════════════════════════════════════════
_MELODY_TICK = {"action": "class_melody_dirge_tick"}
_STANCE = {"type": "class_stance_counter", "chance": 0.40, "atk_pct": 1.0, "label": "守护姿态"}
_GUARD = {"type": "passive_taken_reduce",
          "judge": {"kind": "has_effect", "key": "guard_stance"},
          "reduce": 0.25, "label": "守护姿态"}
_CHAN = {"type": "class_res_channel_gain", "res": "chan_res", "gain": 1.0,
         "label": "渠", "icon": "✦"}

_PASS_SKILLS = ["sk_p_main", "sk_p_also", "sk_p_agg1", "sk_p_agg2"]
_MECH_SKILLS = ["sk_mech_dmg", "sk_mech_fury", "sk_mech_sys", "sk_melody"]


def _mk_melody(fn, actor):
    fn(actor, "atk")


def _mk_stance(fn, actor):
    fn(_battle(), actor, None, {"turns": 3}, [])


def _mk_guard(fn, actor):
    fn(_battle(), actor, None, {"type": "guard_stance", "turns": 3}, [])


def _mk_chan(fn, actor):
    fn(actor, {"chan_res": SYNTH_EFFECT["chan_res"]})


def _mk_pass(fn, actor):
    fn(actor)


def _mk_mech(fn, actor):
    fn(actor)


#: (标签, 文件, 符号, driver, s0, s1, s2 种子, s3 附带无关条目)
_SITES = (
    ("_melody_ensure_tick", "content/mech/class_mech.py", "_melody_ensure_tick", _mk_melody,
     {}, {"triggers": {}},
     {"triggers": {"time_advance": [_MELODY_TICK]}},
     {"triggers": {"time_advance": [{"action": "l7_other"}]}}),
    ("class_stance_guard_enter", "content/mech/class_mech.py", "class_stance_guard_enter",
     _mk_stance, {"class_name": CN}, {"class_name": CN, "triggers": {}},
     {"class_name": CN, "triggers": {"on_taken": [_STANCE]}},
     {"class_name": CN, "triggers": {"on_taken": [{"type": "l7_other"}]}}),
    ("class_guard_stance_enter", "content/mech/class_mech.py", "class_guard_stance_enter",
     _mk_guard, {"class_name": CN}, {"class_name": CN, "triggers": {}},
     {"class_name": CN, "triggers": {"taken_calc": [_GUARD]}},
     # ★ s3：同桶另一把**不同 judge.key** —— 现状按 judge.key 去重 ⇒ 应再挂一条；
     #   若落到 `(action,key)`（= (None,None)）口径 ⇒ 会 update 掉它 ⇒ 本格变红。
     {"class_name": CN, "triggers": {"taken_calc": [
         {"type": "passive_taken_reduce", "judge": {"kind": "has_effect", "key": "shield"},
          "reduce": 0.03, "label": "盾"}]}}),
    ("apply_class_channels", "content/mech/class_mech.py", "apply_class_channels", _mk_chan,
     {"class_name": CN}, {"class_name": CN, "triggers": {}},
     {"class_name": CN, "triggers": {"skill_hit": [_CHAN]}},
     {"class_name": CN, "triggers": {"skill_hit": [{"type": "l7_other"}]}}),
    ("apply_class_passives", "content/mech/class_mech.py", "apply_class_passives", _mk_pass,
     {"class_name": CN, "learned_skills": list(_PASS_SKILLS)},
     {"class_name": CN, "learned_skills": list(_PASS_SKILLS), "triggers": {}},
     None,
     {"class_name": CN, "learned_skills": list(_PASS_SKILLS),
      "triggers": {"on_taken": [{"type": "l7_other"}], "act_cast": [{"type": "l7_other"}],
                   "turn_start": [{"type": "l7_other"}], "skill_hit": [{"type": "l7_other"}]}}),
    ("apply_class_mech", "content/mech/class_mech.py", "apply_class_mech", _mk_mech,
     {"class_name": CN, "learned_skills": list(_MECH_SKILLS)},
     {"class_name": CN, "learned_skills": list(_MECH_SKILLS), "triggers": {}},
     None,
     {"class_name": CN, "learned_skills": list(_MECH_SKILLS),
      "triggers": {"dmg_calc": [{"action": "l7_other"}], "act_cast": [{"type": "l7_other"}],
                   "skill_hit": [{"action": "l7_other"}], "taken_calc": [{"type": "l7_other"}],
                   "heal_calc": [{"type": "l7_other"}], "threshold": [{"type": "l7_other"}]}}),
)


def _site_seed_from_live(driver, symbol):
    actor = {"class_name": CN, "learned_skills": list(
        _PASS_SKILLS if symbol == "apply_class_passives" else _MECH_SKILLS)}
    driver(_live_fn("content/mech/class_mech.py", symbol), actor)
    return actor


def _site_states(site):
    _lbl, _rp, sym, driver, s0, s1, s2, s3 = site
    if s2 is None:
        seed = _site_seed_from_live(driver, sym)        # 「已挂」态：跑一次活实现取成品
        s2 = _deep(seed)
        s3 = _deep(seed)
        for bucket in s3["triggers"].values():          # s3 = 已挂 + 每桶一条无关条目
            bucket.append({"type": "l7_extra"})
    return (s0, s1, s2, s3)


def _probe_class_sites():
    bad = []
    with _SYNTH():
        for site in _SITES:
            label, relpath, symbol = site[0], site[1], site[2]
            driver = site[3]
            states = _site_states(site)
            f_old = _old_fn(relpath, symbol, register_noop=symbol.startswith("class_"))
            f_new = _live_fn(relpath, symbol)
            for repeat in (1, 2, 3):
                for sidx, state in enumerate(states):
                    a_old, a_new = _deep(state), _deep(state)
                    for _ in range(repeat):
                        driver(f_old, a_old)
                        driver(f_new, a_new)
                    if _jsnap(a_old) != _jsnap(a_new):
                        bad.append((label, repeat, sidx, _jsnap(a_old), _jsnap(a_new)))
                    _bump("class_sites")
    return bad


# ══════════════════════════════════════════════════════════════════════════════
# 7. ⑤ 动作体零改动：39 个 `@register_action` 的 getsource sha256 = 39 格
# ══════════════════════════════════════════════════════════════════════════════
def _action_names():
    with open(CM.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                f = d.func if isinstance(d, ast.Call) else d
                if (getattr(f, "id", None) or getattr(f, "attr", None)) == "register_action":
                    out.append(node.name)
    return out


_ACTION_NAMES = _action_names()

#: 39 个动作里**含挂载点**、因而按作业书 §2 必须改其挂载动作的 2 个（见模块头注口径修正）
_MOUNT_ACTIONS = ("class_stance_guard_enter", "class_guard_stance_enter")

#: 「只换挂载动作」的锚点归一化：挂载块**前后文本必须逐字相等**
_NORM_ANCHORS = {
    "content/mech/class_mech.py::class_stance_guard_enter": (
        "    # 挂受击反击 trigger（幂等——同 key 不重复挂）\n",
        "    logs.append(f\"🛡️ 进入守护姿态",
    ),
    "content/mech/class_mech.py::class_guard_stance_enter": (
        "    if reduce_v > 0:\n",
        "    logs.append(f\"🪨 进入",
    ),
}


def _norm_around(text, pre, post):
    i = text.index(pre) + len(pre)
    j = text.index(post, i)
    return text[:i] + "<<MOUNT>>" + text[j:]


def _probe_action_bodies():
    """⑤ 39 格：37 个无挂载点的**逐字节不变**；2 个含挂载点的按 §2 **必须变**（landed 档）。"""
    bad = []
    landed = _PIN["phase"] == "landed"
    for name in _ACTION_NAMES:
        live_h = sha256(inspect.getsource(getattr(CM, name)))
        want = _PIN["aux"].get("class_mech_action::" + name)
        if name in _MOUNT_ACTIONS:
            if landed and live_h == want:
                bad.append(("含挂载点的动作体没变（§2 要求改挂载动作）", name))
        elif want is None or live_h != want:
            bad.append(("无挂载动作体被改（越界）", name, live_h, want))
        _bump("action_bodies")
    return bad


# ══════════════════════════════════════════════════════════════════════════════
# 8. [1] 双 sha256 + E/C 分类
# ══════════════════════════════════════════════════════════════════════════════
def test_frozen_pins():
    print("【1. 双 sha256：9 段冻结文本 + 活实现 inspect.getsource】")
    keys = list(_PIN["frozen"])
    check("冻结段数 == 9（bar 1 / cond 1 / element 1 / class_mech 6）", len(keys) == 9, len(keys))
    check("门禁内键序 == 冻结文本键序", keys == list(_FROZEN_TEXT), keys[:3])
    bad_frozen = [k for k in keys if sha256(_FROZEN_TEXT[k]) != _PIN["frozen"][k]]
    check("9 段冻结文本 sha256 全等 _PIN['frozen']（安全网未被改）", not bad_frozen, bad_frozen)
    check("档位计数：甲 9 / 乙 0 / 丙 0",
          [sum(1 for v in _PIN["tier"].values() if v == t) for t in ("甲", "乙", "丙")]
          == [9, 0, 0], _PIN["tier"])
    bad_live = []
    for key in keys:
        relpath, symbol = key.split("::")
        if sha256(inspect.getsource(_live_fn(relpath, symbol))) != _PIN["live"].get(key):
            bad_live.append(key)
    check("9 段活实现 sha256 全等 _PIN['live']", not bad_live, bad_live)
    if _PIN["phase"] == "landed":
        check("E 栏段数 == 0（§2.3 E 栏列 class_mech 6 段与本线 §2 冲突，见头注）",
              _PIN["segments"]["E"] == [], _PIN["segments"]["E"])
        c_bad = [k for k in _PIN["segments"]["C"] if _PIN["live"][k] == _PIN["frozen"][k]]
        check("C 栏 9 段 frozen != live（真接上了）", not c_bad, c_bad)
    else:
        check("phase != landed ⇒ C 栏不等式断言按设计不启用",
              _PIN["phase"] == "baseline", _PIN["phase"])


# ══════════════════════════════════════════════════════════════════════════════
# 9. [6] aux ⑭（39 个动作体哈希）
# ══════════════════════════════════════════════════════════════════════════════
def _aux_fingerprints():
    out = {}
    per = {}
    for name in _ACTION_NAMES:
        per[name] = sha256(inspect.getsource(getattr(CM, name)))
        out["class_mech_action::" + name] = per[name]
    out["class_mech_actions"] = sha256(
        "|".join("%s=%s" % (n, per[n]) for n in _ACTION_NAMES))
    others = [n for n in _ACTION_NAMES if n not in _MOUNT_ACTIONS]
    out["class_mech_actions_37"] = sha256(
        "|".join("%s=%s" % (n, per[n]) for n in others))
    return out


def test_aux():
    print("【6. aux ⑭：39 个 @register_action 动作体 getsource sha256】")
    now = _aux_fingerprints()
    landed = _PIN["phase"] == "landed"
    for k in sorted(_PIN["aux"]):
        name = k.split("::", 1)[1] if k.startswith("class_mech_action::") else None
        want_change = landed and (name in _MOUNT_ACTIONS or k == "class_mech_actions")
        got, want = now.get(k), _PIN["aux"][k]
        if want_change:
            check("aux[%s] 已按 §2 改变（该段另有 frozen/live 双 pin）" % k, got != want,
                  "%s == %s" % (str(got)[:48], str(want)[:48]))
        else:
            check("aux[%s] 全等 _PIN" % k, got == want,
                  "%r != %r" % (str(got)[:48], str(want)[:48]))
    check("aux 条数 == 41（39 动作体 + 2 条汇总）", len(_PIN["aux"]) == 41, len(_PIN["aux"]))
    # 37 个（无挂载点）必须逐字节不变；2 个（含挂载点）在 landed 档必须变
    changed = [n for n in _ACTION_NAMES
               if sha256(inspect.getsource(getattr(CM, n)))
               != _PIN["aux"].get("class_mech_action::" + n)]
    if landed:
        check("aux：改动的动作体恰好 == 2 个含挂载点的",
              sorted(changed) == sorted(_MOUNT_ACTIONS), changed)
    else:
        check("aux（baseline 档）：39 个动作体全未改动 == 改动前快照",
              changed == [], changed)


# ══════════════════════════════════════════════════════════════════════════════
# 10. [2] 144 格逐格比
# ══════════════════════════════════════════════════════════════════════════════
def test_probes():
    print("【2. 144 格：旧实现（冻结文本 exec）↔ 活实现 逐格比】")
    for label, fn in (("① 幂等矩阵 4×3×2", _probe_idempotent),
                      ("② bar 前插序 1×5", _probe_prepend),
                      ("③ 元素追加序 2×2", _probe_element_order),
                      ("④ class_mech 六处 6×3×4", _probe_class_sites),
                      ("⑤ 动作体 39", _probe_action_bodies)):
        bad = fn()
        check("网格 %s：旧 == 新 逐格" % label, not bad, bad[:2])
    print("  ── 计数校验（防「循环没跑」的假绿；§5.4 合计 144）──")
    exp = {"idempotent": 24, "prepend": 5, "element_order": 4, "class_sites": 72,
           "action_bodies": 39}
    for k in ("idempotent", "prepend", "element_order", "class_sites", "action_bodies"):
        check("格数 %s = %d == 预期 %d" % (k, _COUNT[k], exp[k]), _COUNT[k] == exp[k],
              (_COUNT[k], exp[k]))
    check("格数合计 == 144", sum(_COUNT.values()) == 144, sum(_COUNT.values()))


# ══════════════════════════════════════════════════════════════════════════════
# 11. [3] 口径分歧（本门禁覆盖的 4 条）
# ══════════════════════════════════════════════════════════════════════════════
def _mounted_events(actor):
    return sorted((actor.get("triggers") or {}).keys())


def test_divergences():
    print("【3. 口径分歧：① 去重键多口径 · ② 写策略 · ⑤ 零未知名 · ⑥ 保序】")
    with _SYNTH():
        # ① 去重键：(action,key) / action / type / judge.key / 无 —— 各 ≥1 条
        a = {"class_name": CN, "learned_skills": ["sk_bar"]}
        _live_fn("content/mech/bar_procs.py", "apply_bar_procs")(a)
        a2 = _deep(a)
        _live_fn("content/mech/bar_procs.py", "apply_bar_procs")(a2)
        check("① {action,key} 去重：bar 重复装配不增长",
              _jsnap(a) == _jsnap(a2), (a, a2))
        b = {"class_name": CN, "learned_skills": ["sk_cond"]}
        _live_fn("content/mech/cond_procs.py", "apply_cond_procs")(b)
        b2 = _deep(b)
        _live_fn("content/mech/cond_procs.py", "apply_cond_procs")(b2)
        check("① action 去重：cond 重复装配不增长", _jsnap(b) == _jsnap(b2))
        c = {"class_name": CN}
        _live_fn("content/mech/class_mech.py", "_melody_ensure_tick")(c, "atk")
        c2 = _deep(c)
        _live_fn("content/mech/class_mech.py", "_melody_ensure_tick")(c2, "atk")
        check("① (action,key) 去重：melody tick 重复装配不增长",
              len(c["triggers"]["time_advance"]) == 1
              and _jsnap(c) == _jsnap(c2), c)
        c3 = {"class_name": CN}
        _live_fn("content/mech/class_mech.py", "class_stance_guard_enter")(
            _battle(), c3, None, {"turns": 3}, [])
        c4 = _deep(c3)
        _live_fn("content/mech/class_mech.py", "class_stance_guard_enter")(
            _battle(), c4, None, {"turns": 3}, [])
        check("① type 去重：stance 重复装配不增长（type 与 action 两口径）",
              len(c3["triggers"]["on_taken"]) == 1 and _jsnap(c3) == _jsnap(c4),
              c3["triggers"]["on_taken"])
        d = {"class_name": CN, "triggers": {"taken_calc": [
            {"type": "passive_taken_reduce", "judge": {"kind": "has_effect", "key": "shield"}}]}}
        _live_fn("content/mech/class_mech.py", "class_guard_stance_enter")(
            _battle(), d, None, {"type": "guard_stance", "turns": 3}, [])
        check("① judge.key 去重：不同姿态键**并存**（两条）",
              len(d["triggers"]["taken_calc"]) == 2, d["triggers"]["taken_calc"])
        e = {"class_name": CN, "learned_skills": ["sk_p_main"],
             "triggers": {"skill_hit": [{"type": "l7_other"}], "on_taken": []}}
        _live_fn("content/mech/class_mech.py", "apply_class_passives")(e)
        check("① 无去重（key_of 取不到键）：passives 与既有条目并存",
              e["triggers"]["skill_hit"] == [{"type": "l7_other"}]
              and len(e["triggers"]["on_taken"]) == 1, e["triggers"])
        # ② 写策略：prepend / append / keep
        f = {"class_name": CN, "learned_skills": ["sk_bar"],
             "triggers": {"skill_hit": [{"action": "l7_other"}]}}
        _live_fn("content/mech/bar_procs.py", "apply_bar_procs")(f)
        check("② prepend：bar 新条目在桶首", f["triggers"]["skill_hit"][0] == _BAR_ENTRY, f)
        check("② append：其它条目仍在（未被打乱）",
              f["triggers"]["skill_hit"][1] == {"action": "l7_other"}, f)
        g = {"class_name": CN, "triggers": {"on_taken": [_STANCE]}}
        _live_fn("content/mech/class_mech.py", "class_stance_guard_enter")(
            _battle(), g, None, {"turns": 3}, [])
        check("② keep：已挂条目**内容逐字不动**且不新增",
              g["triggers"]["on_taken"] == [_STANCE], g["triggers"]["on_taken"])
        # ⑤ 零未知名（本线四处全写引擎原生名；未知名策略「告警 + 放行，不抛」由 L6 覆盖）
        with _SYNTH():
            probe = {"class_name": CN, "learned_skills": ["sk_bar", "sk_cond", "sk_elem"]}
            _live_fn("content/mech/bar_procs.py", "apply_bar_procs")(probe)
            _live_fn("content/mech/cond_procs.py", "apply_cond_procs")(probe)
            _live_fn("content/mech/element_procs.py", "apply_element_procs")(probe)
            unknown = sorted(set(_mounted_events(probe)) - set(ET.EVENTS))
            check("⑤ 本线挂载的事件名全在引擎 EVENTS 内（零未知名）", unknown == [], unknown)
        # ⑥ compile 保序：桶内序 = 载荷声明序
        h = {"class_name": CN, "learned_skills": ["sk_elem"]}
        _live_fn("content/mech/element_procs.py", "apply_element_procs")(h)
        acts = [x.get("action") for x in h["triggers"]["dmg_calc"]]
        check("⑥ 保序：elem_counter → elem_reaction（声明序 = 桶内序）",
              acts == ["elem_counter", "elem_reaction"], acts)


# ══════════════════════════════════════════════════════════════════════════════
# 12. [4] 有牙反证（3 处破坏 → 对应探针必须变红；原地还原，零写盘）
# ══════════════════════════════════════════════════════════════════════════════
_ORIG_MOUNT = DECL.Compiler.mount


def _break_prepend():
    """破坏 ① 前插改追加（猴补 `Compiler.mount`：`prepend` 当 `append`）。"""
    def _m(self, actor, rows, *, map_event=None, owner=None, merge=None):
        return _ORIG_MOUNT(self, actor, rows, map_event=map_event, owner=owner,
                           merge=("append" if merge == "prepend" else merge))
    return _Patch(DECL.Compiler, "mount", _m)


class _RevDecl:
    """破坏 ② 元素顺序倒置（`dmg_calc` 载荷表倒序后再挂）。"""

    def __init__(self, real):
        self._real = real

    def mount(self, actor, rows, **kw):
        return self._real.mount(
            actor, {ev: list(reversed(v)) for ev, v in rows.items()}, **kw)


def _break_element_order():
    return _Patch(EP, "_DECL", _RevDecl(EP._DECL))


def _break_type_dedup():
    """破坏 ③ `type` 去重改 `action`：把 `type` 口径的编译器换成 `action` 口径。"""
    return _Patch(CM, "_DECL_TYPE",
                  DECL.Compiler(events=ET.EVENTS, key_of=lambda d: d.get("action"),
                                owner_key=None))


def _probe_type_dedup():
    """只覆盖「type 去重」两处（stance 入口 + melody act_cast）的定向探针。"""
    bad = []
    with _SYNTH():
        for label, symbol, mk, seed in (
                ("class_stance_guard_enter", "class_stance_guard_enter", _mk_stance,
                 {"class_name": CN, "triggers": {"on_taken": []}}),
                ("apply_class_mech.melody", "apply_class_mech", _mk_mech,
                 {"class_name": CN, "learned_skills": list(_MECH_SKILLS),
                  "triggers": {"act_cast": [{"type": "class_melody_act"}]}})):
            f_old = _old_fn("content/mech/class_mech.py", symbol,
                            register_noop=symbol.startswith("class_"))
            f_new = _live_fn("content/mech/class_mech.py", symbol)
            a_old, a_new = _deep(seed), _deep(seed)
            for _ in range(3):
                mk(f_old, a_old)
                mk(f_new, a_new)
            if _jsnap(a_old) != _jsnap(a_new):
                bad.append((label, _jsnap(a_old), _jsnap(a_new)))
    return bad


_TEETH = (
    ("① 前插改追加（Compiler.mount 的 prepend → append）", _break_prepend, _probe_prepend),
    ("② 元素顺序倒置（dmg_calc 载荷表倒序）", _break_element_order, _probe_element_order),
    ("③ type 去重改 action（_DECL_TYPE → action 口径）", _break_type_dedup, _probe_type_dedup),
)


def test_teeth():
    global _COUNTING
    print("【4. 有牙反证：破坏 3 处 → 对应探针必须变红（原地还原）】")
    if _PIN["phase"] == "baseline":
        check("phase=baseline ⇒ 有牙反证按设计不启用（活实现尚未接引擎，无 `_DECL` 可破坏）",
              _PIN["phase"] == "baseline")
        return
    before = {f: _file_sha(f) for f in READONLY_FILES}
    _COUNTING = False
    for label, _b, probe in _TEETH:
        bad = probe()
        check("未破坏时 `%s` 对应探针为绿" % label, not bad, bad[:1])
    print("  ── 逐处破坏 / 还原 ──")
    for label, breaker, probe in _TEETH:
        with breaker():
            red = bool(probe())
        print("     破坏 `%s`：预期变红 / 实测 %s" % (label, "变红 ✅" if red else "仍绿 ❌"))
        check("破坏 `%s` → 探针必须变红（预期变红 / 实测变红）" % label, red is True)
        check("还原 `%s` 后探针回绿" % label, not probe())
    _COUNTING = True
    after = {f: _file_sha(f) for f in READONLY_FILES}
    check("反证全程零写盘（猴补原地还原）：源文件 sha256 前后一致", before == after,
          [f for f in READONLY_FILES if before[f] != after[f]])


# ══════════════════════════════════════════════════════════════════════════════
# 13. 「只换挂载动作」：2 个含挂载点的动作体锚点归一化（见模块头注）
# ══════════════════════════════════════════════════════════════════════════════
def test_mount_only():
    print("【5. 只换挂载动作：2 个含挂载点动作体的「挂载块前后逐字相等」】")
    import inspect as _inspect
    for k, (pre, post) in _NORM_ANCHORS.items():
        relpath, symbol = k.split("::")
        old = _FROZEN_TEXT[k]
        new = _inspect.getsource(getattr(CM, symbol))
        try:
            same = _norm_around(old, pre, post) == _norm_around(new, pre, post)
        except ValueError as exc:
            same = False
            print("     锚点缺失：%r" % (exc,))
        check("`%s`：挂载块前后文本逐字相等（只换挂载动作）" % symbol, same)


# ══════════════════════════════════════════════════════════════════════════════
# 14. [5] 只读断言
# ══════════════════════════════════════════════════════════════════════════════
def _check_readonly(before):
    print("【7. 只读：全程零写盘】")
    after = {f: _file_sha(f) for f in READONLY_FILES}
    bad = [f for f in READONLY_FILES if before[f] != after[f]]
    check("跑完全程 4 个源文件 sha256 前后一致", not bad, bad)
    for f in READONLY_FILES:
        print("     %-34s %s" % (f, after[f]))


def main() -> int:
    print("==" * 36)
    print("U1-D2 冻结门禁④：触发器追加四件（4 文件 / 9 段：甲 9 · 乙 0 · 丙 0；144 格）")
    print("==" * 36)
    print("phase = %r · GWEN_GAME_DB = %s" % (_PIN["phase"], os.environ.get("GWEN_GAME_DB")))
    before = {f: _file_sha(f) for f in READONLY_FILES}
    test_frozen_pins()
    test_aux()
    test_probes()
    test_divergences()
    test_teeth()
    test_mount_only()
    _check_readonly(before)
    print("\n%s\n结果：通过 %d / 共 %d" % ("-" * 46, PASS, PASS + FAIL))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  ❌", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
