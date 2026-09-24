#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P2 试点五动作「行为冻结基线」采集器（**只读** · 可重跑 · 逐字节可比）。

干什么
------
拿 P2 机制声明式化的 5 个试点动作，用**固定输入**调**当前实现（旧路径）**，把输出
（logs / 生效效果 effects / 面板数值 cap / 乘区通道 mult / 装配产物 triggers）确定性
序列化成基线 JSON。判据 = **同一输入重跑字节相同**（`--check`）。

五个试点动作（注册名 → 包内定义处）
    we_death_pool_pay     content/mech/we_procs.py:1129
    we_death_pool_add     content/mech/we_procs.py:1112
    mech_cash_dmg_mult    content/mech/class_mech.py:540
    passive_bar_extend    content/mech/class_mech.py:1106
    passive_low_hp_core   content/mech/class_mech.py:1669

跑法（Windows / git-bash；Python 路径 = 实测路径）
    PY="C:/Users/yuyu/AppData/Local/Programs/Python/Python312/python.exe"
    "$PY" _pilot5_baseline.py --emit      # 采集基线（写 _pilot5_baseline.json）
    "$PY" _pilot5_baseline.py --check     # 重跑对拍（行为段必须逐字节相同）
    "$PY" _pilot5_baseline.py --stdout    # 只打印规范 JSON，不写盘
    "$PY" _pilot5_baseline.py --list      # 列 case

判据口径（迁移前后怎么用）
--------------------------
* 基线文件 = 规范 JSON（`sort_keys=True` + LF + 尾换行），分三段：
    meta    运行环境（脚本版本 / 引擎根 / 包根 / python）
    source  5 个动作函数体的 `inspect.getsource` sha256（**源码指纹**，独立一段）
    cases   行为段：每条 case 的 输入 + 输出（logs/effects/ext/hp/mult/装配产物）
* `--check`：**cases 段逐字节相同 = 通过**；source 段变化只提示（换实现必然变），
  两段分开报，避免"源码变了"把"行为变了"埋掉。
* 反证：改一条 logs 文案 / 改一个 stacks 数值 / 改 ctx["mult"] 乘数 → `--check` 必红。

为什么不用 `tests/_paths.py` + `tests/_engine_harness.py`
--------------------------------------------------------
那条路径要 `<部署树>/host/shell.py`，本机 **不存在**（实测 `C:/Users/yuyu/host/shell.py`
not found ⇒ `_paths.find_host_root()` 直接 RuntimeError）。本脚本走**包自足入口**
`content/apply.py::install_engine()`（引擎配置 + 规则表 + 动作注册一次挂完），
只 import 包与引擎，**不碰宿主壳**，所以能跑。

边界（诚实标注，勿当已验）
--------------------------
1. 战斗实例走 `content/bridge.py::make_battle`（生产唯一出口，注入包内文案表）——
   gauge 族日志因此走**文案表**而不是引擎兜底模板，与生产同口径。
2. 本脚本**不做伤害管线**（不调 landing/settle）：这 5 个动作不改 `dmg`，只改
   `ctx["mult"]` / effects / ext / hp；伤害管线的暴击与浮动带 RNG，进来会让基线
   不可重跑。故冻结的是**乘区通道值**，不是最终伤害数字。
3. 只读：脚本不改 orlandia / framework-engine / 部署树，不跑任何 git 写操作；
   唯一落盘是 workspace 下的 `_pilot5_baseline.json`。
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys

SCRIPT_VERSION = "pilot5-baseline-1"

# ============================================================
# 0. 路径装配（包根 / 引擎根 / 扩展包根；不依赖宿主壳）
# ============================================================

# ★ 2026-09-24：本脚本已**搬进包仓**（`tests/_mech_seq_frozen.py`）当常驻门禁 ⇒ 根目录发现
#   改走仓内统一口径 `tests/_paths.py`（与其它门禁同一份）；环境变量仍可覆盖。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    import _paths as _P                                    # noqa: E402
    PKG_ROOT = os.environ.get("PILOT5_PKG") or _P.PKG_ROOT
    ENGINE_ROOT = os.environ.get("GWEN_FRAMEWORK_DIR") or _P.ENGINE_ROOT
except Exception:                                          # 独立跑且没有宿主壳时退回原口径
    PKG_ROOT = os.environ.get("PILOT5_PKG") or r"C:\Users\yuyu\orlandia"
    ENGINE_ROOT = os.environ.get("GWEN_FRAMEWORK_DIR") or r"C:\Users\yuyu\framework-engine"
BASELINE_PATH = os.path.join(_HERE, "_mech_seq_frozen.json")


def _bootstrap_paths() -> None:
    """把「扩展包根 / 引擎根 / 包根」无条件置前（口径同 tests/_paths.py，但不查宿主壳）。"""
    missing = [p for p in (PKG_ROOT, ENGINE_ROOT) if not os.path.isdir(p)]
    if missing:
        raise SystemExit("路径不存在：%s\n（可用 PILOT5_PKG / GWEN_FRAMEWORK_DIR 覆盖）"
                         % "、".join(missing))
    exts = os.path.join(ENGINE_ROOT, "extends")
    if not os.path.isdir(exts):
        raise SystemExit("引擎根下没有 extends/ 目录：%s" % exts)
    for p in (exts, ENGINE_ROOT, PKG_ROOT):
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


_bootstrap_paths()

from content import apply as APP                      # noqa: E402
from content import bridge as BRIDGE                  # noqa: E402
from content import texts as _T                       # noqa: E402
from content import skills as _SKILLS                 # noqa: E402
from content.mech import class_mech as CM             # noqa: E402
from content.mech import equip as EQ                  # noqa: E402
from content.mech import we_procs as WE               # noqa: E402
from ext_combat import make_actor                     # noqa: E402
from ext_combat.battle.effects import ACTION_HANDLERS, cap_of   # noqa: E402
from ext_combat.battle.effect_triggers import fire    # noqa: E402
from ext_combat.gauge import bar_effect_key, bar_gain, bar_trigger   # noqa: E402

APP.install_engine()      # 引擎配置 + 规则表（EFFECT_RULES/EFFECT_ACTIONS）+ 动作注册

# ============================================================
# 1. 五个试点动作（注册名 → 函数对象）
# ============================================================

ACTIONS = {
    "we_death_pool_add": WE.we_death_pool_add,
    "we_death_pool_pay": WE.we_death_pool_pay,
    "mech_cash_dmg_mult": CM.mech_cash_dmg_mult,
    "passive_bar_extend": CM.passive_bar_extend,
    "passive_low_hp_core": CM.passive_low_hp_core,
}

#: 仓内既有冻结门禁的 `_PIN["aux"]`（tests/test_u1d2_triggers_extra_frozen.py:176/181/194）——
#: 用来**对拍本脚本的指纹口径**（不一致 = 口径漂了或源码变了，必须当场看见）。
REPO_PINS = {
    "mech_cash_dmg_mult": "7f8a949f749d0137eacf92da87bca1aacfd298b15653298fc552577aa0e3f81a",
    "passive_bar_extend": "99743f0f24582f9dfd2be50f2f2046ba2140fafc4b48656196441cc3172a24d4",
    "passive_low_hp_core": "fa19058e254b335bfb27031cd793e48f7351c8af28f2d239ea1e250e35bba7db",
}


def source_fingerprints() -> dict:
    """5 个动作函数体的 `inspect.getsource` sha256（口径 = 仓内冻结门禁同款）。"""
    return {n: hashlib.sha256(inspect.getsource(f).encode("utf-8")).hexdigest()
            for n, f in sorted(ACTIONS.items())}


# ============================================================
# 2. 确定性序列化
# ============================================================

def _j(v):
    """可 JSON 化 + 确定（无对象地址、无 NaN 字面量、tuple→list、set→排序表）。"""
    if v is None or isinstance(v, (str, bool)):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v != v:
            return "<nan>"
        if v == float("inf"):
            return "<inf>"
        if v == float("-inf"):
            return "<-inf>"
        return v
    if isinstance(v, (list, tuple)):
        return [_j(x) for x in v]
    if isinstance(v, (set, frozenset)):
        return sorted(repr(x) for x in v)
    if isinstance(v, dict):
        return {str(k): _j(x) for k, x in v.items()}
    return "<%s>" % type(v).__name__


def canon(obj) -> str:
    """规范 JSON 文本（sort_keys + 缩进 2 + LF + 尾换行）。"""
    return json.dumps(_j(obj), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


# ============================================================
# 3. 桩（固定输入）
# ============================================================

def mk_actor(uid, side, **kw):
    """同 tests 的桩口径（面板显式给，不靠随机）。"""
    base = dict(level=60, hp=1000, max_hp=1000, mp=100, max_mp=100,
                atk=100, matk=50, spd=20, crit=0.0, **{"def": 20, "mdef": 20})
    base.update(kw)
    kind = "player" if side == "player" else "monster"
    return make_actor(uid=uid, name=uid, side=side, kind=kind,
                      human_controlled=(side == "player"), **base)


def mk_battle(*actors):
    """生产口径的战斗实例（`content/bridge.make_battle` 注入包内文案表）。"""
    sides = {}
    for a in actors:
        sides.setdefault(a["side"], []).append(a)
    return BRIDGE.make_battle("monster", sides=sides)


def mk_cash_actor(learned, cls="cls_ci_ke"):
    """学什么挂什么：装配后返回 actor（triggers 由 apply_class_mech 写）。"""
    a = mk_actor("p1", "player", class_name=cls, level=95, hp=3000, max_hp=3000,
                 mp=300, max_mp=300, atk=200, matk=80, spd=80, crit=0.0,
                 skills=[], learned_skills=list(learned), **{"def": 40, "mdef": 30})
    a["effects"] = {}
    CM.apply_class_mech(a)
    return a


def mk_wooden(hp=99999, uid="e1"):
    e = mk_actor(uid, "enemy", hp=hp, max_hp=hp, atk=1, matk=1, spd=5,
                 **{"def": 0, "mdef": 0})
    e["dodge"] = 0.0
    return e


def st(a):
    """actor 可变状态快照（**存在才记** —— 「键没被建出来」本身是行为）。"""
    out = {"hp": a.get("hp"), "max_hp": a.get("max_hp")}
    for k in ("effects", "ext", "shields"):
        if k in a:
            out[k] = _j(a[k])
    return out


def trig_of(a, event, action):
    """装配产物：某 actor 某事件上 action == 目标 的条目（逐条原样）。"""
    return [dict(x) for x in ((a.get("triggers") or {}).get(event) or [])
            if isinstance(x, dict) and (x.get("type") or x.get("action")) == action]


def bar_host(key="shaken", trigger_count=1, immune_until=12.0, val=0.0, now=10.0, uid="e_bar"):
    """造一个「刚触发过 / 已在免疫窗口」的条宿主（破绽·极 的判定输入）。"""
    a = mk_wooden(uid=uid)
    a.setdefault("effects", {})[bar_effect_key(key)] = {
        "val": val, "threshold": 50, "trigger_count": trigger_count,
        "immune_until": immune_until, "_at": now}
    return a


# ============================================================
# 4. case 注册表
# ============================================================

_CASES = []


def case(cid, group, desc):
    def deco(fn):
        _CASES.append((cid, group, desc, fn))
        return fn
    return deco


# ------------------------------------------------------------
# A 组：装配产物（参数从哪来 —— 表/数据 → params 的落地形状）
# ------------------------------------------------------------

@case("A1_mech_cash_dmg_mult_装配", "A-装配", "cls_ci_ke 学「终结·割喉」→ dmg_calc 参数（基础 per_layer 0.10）")
def c_A1():
    a = mk_cash_actor(["终结·割喉"])
    return {"input": {"class_name": "cls_ci_ke", "learned_skills": ["终结·割喉"]},
            "output": {"dmg_calc_mech_cash_dmg_mult": trig_of(a, "dmg_calc", "mech_cash_dmg_mult"),
                       "skill_hit_mech_cash_clear": trig_of(a, "skill_hit", "mech_cash_clear")}}


@case("A2_mech_cash_dmg_mult_装配_链舞升级", "A-装配", "再学「链舞」(passive.proc=finisher_up) → per_layer 0.10→0.16")
def c_A2():
    a = mk_cash_actor(["终结·割喉", "链舞"])
    return {"input": {"class_name": "cls_ci_ke", "learned_skills": ["终结·割喉", "链舞"]},
            "output": {"dmg_calc_mech_cash_dmg_mult": trig_of(a, "dmg_calc", "mech_cash_dmg_mult")}}


@case("A3_passive_bar_extend_装配", "A-装配", "学「钢拳/气力之心/破绽·极」→ skill_hit 延长段 + 注入顺序（bar_gain 首位）")
def c_A3():
    a = mk_cash_actor(["钢拳", "气力之心", "破绽·极"], cls="cls_wu_seng")
    sh = [(_j(x)) for x in ((a.get("triggers") or {}).get("skill_hit") or []) if isinstance(x, dict)]
    return {"input": {"class_name": "cls_wu_seng",
                      "learned_skills": ["钢拳", "气力之心", "破绽·极"]},
            "output": {"skill_hit_全部（顺序契约：bar_gain 首位）": sh,
                       "skill_hit_passive_bar_extend": trig_of(a, "skill_hit", "passive_bar_extend"),
                       "dmg_calc_passive_dmg_mult": trig_of(a, "dmg_calc", "passive_dmg_mult")}}


@case("A4_passive_low_hp_core_装配", "A-装配", "学「不动如山」→ on_taken 补核段 + also 段（taken_calc 减伤）")
def c_A4():
    a = mk_cash_actor(["不动如山"], cls="cls_wu_seng")
    return {"input": {"class_name": "cls_wu_seng", "learned_skills": ["不动如山"]},
            "output": {"on_taken_passive_low_hp_core": trig_of(a, "on_taken", "passive_low_hp_core"),
                       "taken_calc_passive_taken_reduce": trig_of(a, "taken_calc", "passive_taken_reduce")}}


@case("A5_we_death_pool_装配", "A-装配", "装备 death_dance → on_taken 收池段 + turn_start 结算段")
def c_A5():
    a = mk_actor("p1", "player", equipment={"armor": {"weapon_effect": "death_dance", "we_data": None}})
    EQ.apply_to_actor(a)
    return {"input": {"equipment": {"armor": {"weapon_effect": "death_dance", "we_data": None}}},
            "output": {"on_taken": trig_of(a, "on_taken", "we_death_pool_add"),
                       "turn_start": trig_of(a, "turn_start", "we_death_pool_pay")}}


# ------------------------------------------------------------
# B 组：动作直调（固定输入 → 输出）
# ------------------------------------------------------------

def _cash_case(desc, params, ctx_extra=None, effects=None, e_effects=None):
    """mech_cash_dmg_mult 的公共壳：造 battle + 固定 _fire_ctx + 直调。"""
    p = mk_actor("p1", "player", hp=3000, max_hp=3000)
    e = mk_wooden()
    b = mk_battle(p, e)
    if effects:
        p["effects"] = dict(effects)
    if e_effects:
        e["effects"] = dict(e_effects)
    ctx = {"actor": p, "target": e, "dmg": 100, "info": {"mech": "finisher"},
           "mult": 1.0, "tags": []}
    if ctx_extra:
        ctx.update(ctx_extra)
    b._fire_ctx = ctx
    logs = []
    CM.mech_cash_dmg_mult(b, p, e, params, logs)
    return {"params": params,
            "input": {"ctx": _j({k: v for k, v in ctx.items() if k != "actor"}),
                      "actor.effects": _j(p.get("effects")), "target.effects": _j(e.get("effects"))},
            "output": {"ctx_mult": ctx.get("mult"), "ctx_tags": _j(ctx.get("tags")),
                       "logs": list(logs), "actor": st(p), "target": st(e)}}


@case("B1_1_mech_cash_dmg_mult_命中", "B-直调", "info.mech=finisher；连段 5 层 → mult ×1.5")
def c_B1_1():
    return _cash_case("命中", {"action": "mech_cash_dmg_mult", "mech": "finisher", "key": "lian_duan",
                               "per_layer": 0.10, "label": "终结技"},
                      effects={"lian_duan": {"stacks": 5, "expire": None}})


@case("B1_2_mech_cash_dmg_mult_mech不匹配", "B-直调", "info.mech != params.mech → 零效果零日志")
def c_B1_2():
    return _cash_case("mech 不匹配",
                      {"action": "mech_cash_dmg_mult", "mech": "finisher", "key": "lian_duan",
                       "per_layer": 0.10, "label": "终结技"},
                      ctx_extra={"info": {"mech": "other"}},
                      effects={"lian_duan": {"stacks": 5}})


@case("B1_3_mech_cash_dmg_mult_零层", "B-直调", "层数 0 → mult ×1.00（**仍打日志**）")
def c_B1_3():
    return _cash_case("零层", {"action": "mech_cash_dmg_mult", "mech": "finisher", "key": "lian_duan",
                               "per_layer": 0.10, "label": "终结技"}, effects={})


@case("B1_4_mech_cash_dmg_mult_per_stack覆盖", "B-直调", "info.per_stack（链舞级覆盖）压过 params.per_layer")
def c_B1_4():
    return _cash_case("per_stack 覆盖",
                      {"action": "mech_cash_dmg_mult", "mech": "finisher", "key": "lian_duan",
                       "per_layer": 0.10, "label": "终结技"},
                      ctx_extra={"info": {"mech": "finisher", "per_stack": 0.06}},
                      effects={"lian_duan": {"stacks": 5}})


@case("B1_5_mech_cash_dmg_mult_owner_target", "B-直调", "owner=target → 读 ctx.target 的叠层")
def c_B1_5():
    p = mk_actor("p1", "player")
    e = mk_wooden()
    b = mk_battle(p, e)
    e["effects"] = {"hunt_mark": {"stacks": 2}}
    p["effects"] = {}
    ctx = {"actor": p, "target": e, "dmg": 100, "info": {"mech": "hunt"}, "mult": 1.0}
    b._fire_ctx = ctx
    params = {"action": "mech_cash_dmg_mult", "mech": "hunt", "key": "hunt_mark",
              "per_layer": 0.5, "label": "猎印", "owner": "target"}
    logs = []
    CM.mech_cash_dmg_mult(b, p, e, params, logs)
    return {"params": params,
            "input": {"ctx.info.mech": "hunt", "ctx.mult": 1.0,
                      "actor.effects": _j(p.get("effects")), "target.effects": _j(e.get("effects"))},
            "output": {"ctx_mult": ctx.get("mult"), "logs": list(logs),
                                        "actor": st(p), "target": st(e)}}


@case("B1_6_mech_cash_dmg_mult_key为列表", "B-直调", "key=[a,b] → 层求和 3.5；layer_label 缺省 = '、'.join(key)")
def c_B1_6():
    return _cash_case("key 列表",
                      {"action": "mech_cash_dmg_mult", "mech": "multi", "key": ["a", "b"],
                       "per_layer": 0.10, "label": "多印"},
                      ctx_extra={"info": {"mech": "multi"}},
                      effects={"a": {"stacks": 1.5}, "b": {"stacks": 2.0}})


@case("B1_7_mech_cash_dmg_mult_累乘已有mult", "B-直调", "ctx.mult 已有 2.0 → 2.0×1.5=3.0")
def c_B1_7():
    return _cash_case("累乘", {"action": "mech_cash_dmg_mult", "mech": "finisher", "key": "lian_duan",
                               "per_layer": 0.10, "label": "终结技"},
                      ctx_extra={"mult": 2.0}, effects={"lian_duan": {"stacks": 5}})


@case("B1_8_mech_cash_dmg_mult_小数层", "B-直调", "小数层 3.4（v181 保真）→ 1+0.1×3.4=1.34")
def c_B1_8():
    return _cash_case("小数层", {"action": "mech_cash_dmg_mult", "mech": "finisher", "key": "lian_duan",
                                 "per_layer": 0.10, "label": "终结技"},
                      effects={"lian_duan": {"stacks": 3.4}})


@case("B1_9_mech_cash_dmg_mult_ctx无info", "B-直调", "ctx 里没有 info 键 → info={} → mech 不等 → return")
def c_B1_9():
    p = mk_actor("p1", "player", hp=3000, max_hp=3000)
    e = mk_wooden()
    b = mk_battle(p, e)
    p["effects"] = {"lian_duan": {"stacks": 5}}
    ctx = {"actor": p, "target": e, "dmg": 100, "mult": 1.0}
    b._fire_ctx = ctx
    params = {"action": "mech_cash_dmg_mult", "mech": "finisher", "key": "lian_duan",
              "per_layer": 0.10, "label": "终结技"}
    logs = []
    CM.mech_cash_dmg_mult(b, p, e, params, logs)
    return {"params": params, "input": {"ctx 无 info 键": True, "actor.effects": _j(p["effects"])},
            "output": {"ctx_mult": ctx.get("mult"), "logs": list(logs), "actor": st(p)}}


def _extend_case(desc, params, host_kw=None, ctx_target=None, now=10.0, host=None):
    """passive_bar_extend 公共壳。"""
    p = mk_cash_actor([])
    host = host if host is not None else bar_host(**(host_kw or {}))
    e = ctx_target if ctx_target is not None else host
    b = mk_battle(p, host)
    if now is not None:
        b._now = now
    ctx = {"target": e}
    b._fire_ctx = ctx
    logs = []
    CM.passive_bar_extend(b, p, host, params, logs)
    return {"params": params,
            "input": {"now": now, "位置参数 target": host.get("uid"),
                      "ctx.target": e.get("uid"),
                      "host.effects": _j((host.get("effects") or {}).get(bar_effect_key("shaken")))},
            "output": {"logs": list(logs),
                       "bar_ctx_target": st(e).get("effects", {}).get(bar_effect_key("shaken")),
                       "bar_pos_arg": st(host).get("effects", {}).get(bar_effect_key("shaken"))}}


@case("B2_1_passive_bar_extend_窗口内", "B-直调", "trigger_count=1 且 immune_until(12) > now(10) → +1 刻")
def c_B2_1():
    return _extend_case("窗口内", {"judge": {"bar": "shaken"}, "extend": 1, "label": "破绽·极"})


@case("B2_2_passive_bar_extend_未触发", "B-直调", "trigger_count=0 → 零效果零日志")
def c_B2_2():
    return _extend_case("未触发", {"judge": {"bar": "shaken"}, "extend": 1, "label": "破绽·极"},
                        host_kw={"trigger_count": 0, "immune_until": 0.0})


@case("B2_3_passive_bar_extend_窗口已过期", "B-直调", "immune_until == now → `<= now` 直接 return")
def c_B2_3():
    return _extend_case("窗口过期", {"judge": {"bar": "shaken"}, "extend": 1, "label": "破绽·极"},
                        host_kw={"immune_until": 10.0, "now": 10.0}, now=10.0)


@case("B2_4_passive_bar_extend_extend缺字段", "B-直调", "params.extend 缺 → ext=0 → return（缺字段=无此行为）")
def c_B2_4():
    return _extend_case("extend 缺", {"judge": {"bar": "shaken"}, "label": "破绽·极"})


@case("B2_5_passive_bar_extend_bar缺字段", "B-直调", "judge.bar 与 params.bar 都缺 → return")
def c_B2_5():
    return _extend_case("bar 缺", {"extend": 1, "label": "破绽·极"})


@case("B2_6_passive_bar_extend_宿主取ctx_target", "B-直调", "host 优先 ctx.target（位置参数 target 无条 → 不动）")
def c_B2_6():
    p = mk_cash_actor([])
    with_bar = bar_host(uid="e_ctx")
    without = mk_wooden(uid="e_pos")
    b = mk_battle(p, with_bar, without)
    b._now = 10.0
    ctx = {"target": with_bar}
    b._fire_ctx = ctx
    params = {"judge": {"bar": "shaken"}, "extend": 2, "label": "破绽·极"}
    logs = []
    CM.passive_bar_extend(b, p, without, params, logs)   # 位置参数是「无条」的那个
    return {"params": params,
            "input": {"now": 10.0, "ctx.target": with_bar.get("uid"),
                      "位置参数 target": without.get("uid"),
                      "host.effects": _j((with_bar.get("effects") or {}).get(bar_effect_key("shaken")))},
            "output": {
        "logs": list(logs),
        "ctx_target_effects": st(with_bar).get("effects"),
        "pos_arg_effects": st(without).get("effects")}}


@case("B2_7_passive_bar_extend_无条状态", "B-直调", "宿主 effects 里没有该条 → return")
def c_B2_7():
    p = mk_cash_actor([])
    plain = mk_wooden(uid="e_plain")
    b = mk_battle(p, plain)
    b._now = 10.0
    ctx = {"target": plain}
    b._fire_ctx = ctx
    params = {"judge": {"bar": "shaken"}, "extend": 1, "label": "破绽·极"}
    logs = []
    CM.passive_bar_extend(b, p, plain, params, logs)
    return {"params": params, "input": {"now": 10.0, "host.effects": _j(plain.get("effects")),
                                       "注": "从未挂过条"},
            "output": {"logs": list(logs), "host": st(plain)}}


@case("B2_8_passive_bar_extend_extend非数值", "B-直调", "extend='abc' → except → ext=0.0 → return")
def c_B2_8():
    return _extend_case("extend 非数值", {"judge": {"bar": "shaken"}, "extend": "abc", "label": "破绽·极"})


@case("B2_9_passive_bar_extend_小数刻", "B-直调", "extend=1.5 → 窗口 +1.5；**日志 int(ext) 截断成 1**")
def c_B2_9():
    return _extend_case("小数刻", {"judge": {"bar": "shaken"}, "extend": 1.5, "label": "破绽·极"})


@case("B2_10_passive_bar_extend_bar走params", "B-直调", "judge.bar 缺、params.bar 在位 → 走回落分支，照常延长")
def c_B2_10():
    return _extend_case("bar 回落 params", {"bar": "shaken", "extend": 1, "label": "破绽·极"})


#: 缺省哨兵（区分「没传」与「显式传 None」）
_UNSET = object()


def _add_case(desc, dmg, params=None, ctx=None, ext=None, caster=_UNSET, with_ctx=True):
    """we_death_pool_add 公共壳。"""
    p = mk_actor("p1", "player")
    e = mk_wooden()
    b = mk_battle(p, e)
    # make_actor 会播种 ext={} —— 先摘掉，让「容器是否被建出」成为可观测行为
    if ext is not None:
        p["ext"] = _j(ext)
    else:
        p.pop("ext", None)
    if with_ctx:
        b._fire_ctx = {"dmg": dmg} if ctx is None else ctx
    params = params if params is not None else {"pool_key": "we_death_pool", "pool_pct": 0.35}
    logs = []
    who = p if caster is _UNSET else caster
    WE.we_death_pool_add(b, who, p, params, logs)
    return {"params": params, "input": {"dmg": dmg, "ext 起始": ext},
            "output": {"logs": list(logs), "actor": st(p)}}


@case("B4_1_we_death_pool_add_收35%", "B-直调", "dmg=100 → 池 35.0（静默，无日志）")
def c_B4_1():
    return _add_case("收池", 100)


@case("B4_2_we_death_pool_add_累加", "B-直调", "已有 35.0，再受 200 → 105.0")
def c_B4_2():
    p = mk_actor("p1", "player")
    e = mk_wooden()
    b = mk_battle(p, e)
    p["ext"] = {"we_proc": {"we_death_pool": 35.0}}
    logs = []
    for dmg in (200,):
        b._fire_ctx = {"dmg": dmg}
        WE.we_death_pool_add(b, p, p, {"pool_key": "we_death_pool", "pool_pct": 0.35}, logs)
    return {"input": {"dmg": [200], "起始池": 35.0}, "output": {"logs": list(logs), "actor": st(p)}}


@case("B4_3_we_death_pool_add_dmg为0", "B-直调", "dmg=0 → 提前 return：**连 ext 容器都不建**")
def c_B4_3():
    r = _add_case("dmg 0", 0)
    return r


@case("B4_4_we_death_pool_add_dmg为负", "B-直调", "dmg=-50 → return（无实伤不收池）")
def c_B4_4():
    return _add_case("dmg 负", -50)


@case("B4_5_we_death_pool_add_缺pool_pct", "B-直调", "pool_pct 缺 → 缺省 0.35")
def c_B4_5():
    return _add_case("缺 pool_pct", 100, params={"pool_key": "we_death_pool"})


@case("B4_6_we_death_pool_add_ctx无dmg", "B-直调", "_fire_ctx 无 dmg → 0 → return")
def c_B4_6():
    return _add_case("ctx 无 dmg", None, ctx={})


@case("B4_7_we_death_pool_add_无fire_ctx", "B-直调", "battle 无 _fire_ctx → 0 → return")
def c_B4_7():
    return _add_case("无 _fire_ctx", None, with_ctx=False)


@case("B4_8_we_death_pool_add_owner与caster均空", "B-直调", "params 无 _owner 且 caster=None → return")
def c_B4_8():
    return _add_case("owner None", 100, caster=None,
                     params={"pool_key": "we_death_pool", "pool_pct": 0.35})


@case("B4_9_we_death_pool_add_pool_key缺省", "B-直调", "pool_key 缺 → 'we_death_pool'")
def c_B4_9():
    return _add_case("缺 pool_key", 100, params={"pool_pct": 0.35})


@case("B4_10_we_death_pool_add_dmg为字符串", "B-直调", "dmg='100' → float() 容错 → 35.0")
def c_B4_10():
    return _add_case("dmg 字符串", "100")


@case("B4_11_we_death_pool_add_宿主已死", "B-直调", "owner.hp=0 **仍收池**（add 不判存活，与 pay 不同）")
def c_B4_11():
    p = mk_actor("p1", "player", hp=0, max_hp=1000)
    e = mk_wooden()
    b = mk_battle(p, e)
    p.pop("ext", None)
    b._fire_ctx = {"dmg": 100}
    params = {"pool_key": "we_death_pool", "pool_pct": 0.35}
    logs = []
    WE.we_death_pool_add(b, p, p, params, logs)
    return {"params": params, "input": {"owner.hp": 0, "dmg": 100},
            "output": {"logs": list(logs), "actor": st(p)}}


def _pay_case(desc, pool=None, hp=1000, params=None, present=True, alive=True):
    """we_death_pool_pay 公共壳。"""
    p = mk_actor("p1", "player", hp=hp, max_hp=1000)
    e = mk_wooden()
    b = mk_battle(p, e)
    if present:
        p["ext"] = {"we_proc": {}} if pool is None else {"we_proc": {"we_death_pool": pool}}
    else:
        p.pop("ext", None)
    if not alive:
        p["hp"] = 0
    params = params if params is not None else {"pool_key": "we_death_pool", "pay_pct": 0.10}
    logs = []
    WE.we_death_pool_pay(b, p, p, params, logs)
    return {"params": params, "input": {"pool": pool, "hp": hp, "ext_present": present},
            "output": {"logs": list(logs), "actor": st(p)}}


@case("B5_1_we_death_pool_pay_结算10%", "B-直调", "池 35.0 → pay=max(1,int(3.5))=3，扣血、池 32.0")
def c_B5_1():
    return _pay_case("结算", pool=35.0)


@case("B5_2_we_death_pool_pay_不足1也扣1", "B-直调", "池 5.0 → pay=max(1,0)=1")
def c_B5_2():
    return _pay_case("保底 1", pool=5.0)


@case("B5_3_we_death_pool_pay_池为0", "B-直调", "池 0 → return（**但 ext.we_proc 容器已被建出**）")
def c_B5_3():
    return _pay_case("池 0", pool=0.0)


@case("B5_4_we_death_pool_pay_血量不足", "B-直调", "hp=2、pay=3 → hp 钳到 0（不登记击杀）")
def c_B5_4():
    return _pay_case("hp 不足", pool=35.0, hp=2)


@case("B5_5_we_death_pool_pay_已死", "B-直调", "hp=0（actor_alive False）→ return，池不动")
def c_B5_5():
    return _pay_case("已死", pool=35.0, alive=False)


@case("B5_6_we_death_pool_pay_无ext键", "B-直调", "actor 无 ext → setdefault 建容器 + 池 0 → return")
def c_B5_6():
    return _pay_case("无 ext", present=False)


@case("B5_7_we_death_pool_pay_池为字符串", "B-直调", "池 '35' → float 容错 → 扣 3、池 32.0")
def c_B5_7():
    return _pay_case("池字符串", pool="35")


@case("B5_8_we_death_pool_pay_pay_pct_1.5", "B-直调", "pay_pct=1.5 → pay=52 > 池 35 → 池钳 0.0")
def c_B5_8():
    return _pay_case("pay_pct 1.5", pool=35.0, params={"pool_key": "we_death_pool", "pay_pct": 1.5})


@case("B5_9_we_death_pool_pay_池为负", "B-直调", "池 -5 → `pool <= 0` → return（不扣血、不下溢）")
def c_B5_9():
    return _pay_case("池为负", pool=-5.0)


def _core_case(desc, params, hp=800, max_hp=3000, effects=None, via_ctx_actor=False):
    """passive_low_hp_core 公共壳。"""
    p = mk_actor("p1", "player", class_name="cls_wu_seng", level=99, hp=hp, max_hp=max_hp,
                 mp=300, max_mp=300, atk=100, matk=80, spd=20, crit=0.0, **{"def": 40, "mdef": 30})
    p["effects"] = dict(effects or {})
    e = mk_wooden()
    b = mk_battle(p, e)
    b._fire_ctx = {"actor": p} if via_ctx_actor else {}
    logs = []
    # via_ctx_actor：caster 留空，只有 ctx.actor 能救回 owner（冻结 owner 解析链）
    CM.passive_low_hp_core(b, None if via_ctx_actor else p, p, params, logs)
    res = params.get("res") or ""
    return {"params": params,
            "input": {"hp": hp, "max_hp": max_hp, "effects 起始": _j(effects or {}),
                      "caster": None if via_ctx_actor else p.get("uid"),
                      "ctx.actor": p.get("uid") if via_ctx_actor else None},
            "output": {"logs": list(logs), "actor": st(p),
                       "cap_of(res)": cap_of(p, res) if res else None}}


_CORE_PARAMS = {"res": "guard_core", "used_key": "_core_last_stand_used",
                "hp_lt": 0.3, "cores": 3, "label": "不动如山", "reduce": 0.4}


@case("B3_1_passive_low_hp_core_残血补核", "B-直调", "hp 800/3000 < 30% → +3 磐核（cap 5）+ 置一次性 flag")
def c_B3_1():
    return _core_case("残血", dict(_CORE_PARAMS))


@case("B3_2_passive_low_hp_core_每场一次", "B-直调", "used_key 已置位 → 二次调用零效果零日志")
def c_B3_2():
    return _core_case("已用过", dict(_CORE_PARAMS),
                      effects={"_core_last_stand_used": {"stacks": 1, "expire": None}})


@case("B3_3_passive_low_hp_core_未跌破", "B-直调", "hp 1000 ≥ int(3000×0.3)=900 → return")
def c_B3_3():
    return _core_case("未跌破", dict(_CORE_PARAMS), hp=1000)


@case("B3_4_passive_low_hp_core_缺cores", "B-直调", "cores 缺 → return（缺字段=无此行为）")
def c_B3_4():
    return _core_case("缺 cores", {"res": "guard_core", "used_key": "_core_last_stand_used",
                                   "hp_lt": 0.3, "label": "不动如山"})


@case("B3_5_passive_low_hp_core_cap钳制", "B-直调", "已有 4 枚 + 3 → 钳到 cap 5")
def c_B3_5():
    return _core_case("cap 钳制", dict(_CORE_PARAMS), effects={"guard_core": {"stacks": 4}})


@case("B3_6_passive_low_hp_core_小数cores", "B-直调", "cores=0.5 → norm_stack 保真 0.5（日志 cores:g）")
def c_B3_6():
    return _core_case("小数 cores", dict(_CORE_PARAMS, cores=0.5))


@case("B3_7a_passive_low_hp_core_阈值边界相等", "B-直调", "hp == int(max_hp×hp_lt)=900 → **不触发**（严格 <）")
def c_B3_7a():
    return _core_case("阈值相等", dict(_CORE_PARAMS), hp=900)


@case("B3_7b_passive_low_hp_core_阈值边界差1", "B-直调", "hp=899 → 触发")
def c_B3_7b():
    return _core_case("差 1 点", dict(_CORE_PARAMS), hp=899)


@case("B3_8_passive_low_hp_core_cap无声明", "B-直调", "res 无 EFFECT_RULES 行 → cap_of 兜底 999999")
def c_B3_8():
    return _core_case("cap 无声明", dict(_CORE_PARAMS, res="nonexist_res"))


@case("B3_9_passive_low_hp_core_owner全空", "B-直调", "params 无 _owner、ctx 无 actor、caster=None → return")
def c_B3_9():
    p = mk_actor("p1", "player", class_name="cls_wu_seng", hp=800, max_hp=3000)
    p["effects"] = {}
    e = mk_wooden()
    b = mk_battle(p, e)
    b._fire_ctx = {}
    logs = []
    CM.passive_low_hp_core(b, None, p, dict(_CORE_PARAMS), logs)
    return {"params": dict(_CORE_PARAMS),
            "input": {"caster": None, "ctx": {}, "hp": 800, "max_hp": 3000, "effects 起始": {}},
            "output": {"logs": list(logs), "actor": st(p)}}


@case("B3_10_passive_low_hp_core_owner取ctx_actor", "B-直调", "caster=None 但 ctx.actor 在位 → 正常补核")
def c_B3_10():
    return _core_case("owner 取 ctx.actor", dict(_CORE_PARAMS), via_ctx_actor=True)


# ------------------------------------------------------------
# C 组：fire() 集成（声明 → 引擎分发 → 动作；params 由装配层给）
# ------------------------------------------------------------

@case("C1_fire_dmg_calc", "C-集成", "fire(dmg_calc) → 终结技乘区（装配产物驱动，log 与 tags 顺序冻结）")
def c_C1():
    p = mk_cash_actor(["终结·割喉", "链舞"])
    e = mk_wooden()
    b = mk_battle(p, e)
    p["effects"]["lian_duan"] = {"stacks": 5, "expire": None}
    info = _SKILLS.skill_info("cls_ci_ke", "终结·割喉")
    logs = []
    ctx = {"actor": p, "target": e, "dmg": 100, "is_crit": False, "info": info, "mult": 1.0,
           "tags": []}
    fire(b, "dmg_calc", ctx, logs)
    return {"input": {"event": "dmg_calc", "info.mech": info.get("mech"),
                      "effects.lian_duan.stacks": 5},
            "output": {"ctx_mult": ctx.get("mult"), "ctx_tags": _j(ctx.get("tags")),
                       "logs": list(logs), "actor": st(p), "target": st(e)}}


@case("C2_fire_on_taken", "C-集成", "fire(on_taken) → 不动如山补核（真实受击事件，含渠道段顺序）")
def c_C2():
    p = mk_cash_actor(["不动如山"], cls="cls_wu_seng")
    p["hp"] = 800
    e = mk_wooden()
    b = mk_battle(p, e)
    logs = []
    ctx = {"actor": p, "target": p, "source": e, "dmg": 100, "real": 100}
    fire(b, "on_taken", ctx, logs)
    return {"input": {"event": "on_taken", "hp": 800, "max_hp": 3000, "dmg": 100},
            "output": {"logs": list(logs), "actor": st(p)},
            "on_taken_triggers": trig_of(p, "on_taken", "passive_low_hp_core")}


@case("C3_fire_skill_hit_顺序契约", "C-集成", "fire(skill_hit)：bar_gain 先推条触发 → passive_bar_extend 后延窗")
def c_C3():
    p = mk_cash_actor(["钢拳", "气力之心", "破绽·极"], cls="cls_wu_seng")
    e = mk_wooden()
    b = mk_battle(p, e)
    b._now = 10.0
    bar_gain(e, "shaken", 45.0, None, now=10.0)      # 45/50（未触发）
    be = (e.get("effects") or {}).get(bar_effect_key("shaken"))
    before = _j(be)
    info = _SKILLS.skill_info("cls_wu_seng", "钢拳")
    logs = []
    ctx = {"actor": p, "target": e, "caster": p, "dmg": 100, "info": info, "mult": 1.0}
    fire(b, "skill_hit", ctx, logs)
    after = _j((e.get("effects") or {}).get(bar_effect_key("shaken")))
    return {"input": {"event": "skill_hit", "shaken_gain": info.get("shaken_gain"),
                      "条起始 val": 45.0, "threshold": 50, "now": 10.0},
            "output": {"logs": list(logs), "条_前": before, "条_后": after,
                       "actor": st(p), "target": {"hp": e.get("hp")}},
            "skill_hit_triggers": [_j(x) for x in ((p.get("triggers") or {}).get("skill_hit") or [])
                                   if isinstance(x, dict)]}


@case("C4_fire_turn_start", "C-集成", "fire(turn_start) → 缓伤池结算 10%")
def c_C4():
    p = mk_actor("p1", "player", equipment={"armor": {"weapon_effect": "death_dance", "we_data": None}})
    EQ.apply_to_actor(p)
    e = mk_wooden()
    b = mk_battle(p, e)
    p["ext"] = {"we_proc": {"we_death_pool": 105.0}}
    logs = []
    ctx = {"actor": p}
    fire(b, "turn_start", ctx, logs)
    return {"input": {"event": "turn_start", "池": 105.0, "hp": 1000},
            "output": {"logs": list(logs), "actor": st(p)}}


@case("C5_fire_on_taken_收池", "C-集成", "fire(on_taken) → 缓伤池 +35%（静默收池）")
def c_C5():
    p = mk_actor("p1", "player", equipment={"armor": {"weapon_effect": "death_dance", "we_data": None}})
    EQ.apply_to_actor(p)
    e = mk_wooden()
    b = mk_battle(p, e)
    p["ext"] = {"we_proc": {"we_death_pool": 0.0}}
    logs = []
    ctx = {"actor": p, "target": p, "source": e, "dmg": 100, "real": 100}
    fire(b, "on_taken", ctx, logs)
    return {"input": {"event": "on_taken", "dmg": 100, "池起始": 0.0},
            "output": {"logs": list(logs), "actor": st(p)}}


# ------------------------------------------------------------
# D 组：注册面与指纹（自检）
# ------------------------------------------------------------

def registry_section() -> dict:
    """注册面：5 个名字都在引擎动词表里（声明表引用的动作必须真的在册）。"""
    out = {}
    for n, f in sorted(ACTIONS.items()):
        out[n] = {"registered": n in ACTION_HANDLERS,
                  "same_object": ACTION_HANDLERS.get(n) is f,
                  "module": getattr(f, "__module__", ""),
                  "qualname": getattr(f, "__qualname__", "")}
    return out


def build_report() -> dict:
    cases = []
    for cid, group, desc, fn in _CASES:
        r = fn()
        item = {"id": cid, "group": group, "desc": desc,
                "input": _j(r.get("input")), "output": _j(r.get("output"))}
        if r.get("params") is not None:
            item["params"] = _j(r.get("params"))
        cases.append(item)
    fps = source_fingerprints()
    return {
        "meta": {"script": SCRIPT_VERSION,
                 "pkg_root": PKG_ROOT,
                 "engine_root": ENGINE_ROOT,
                 "python": "%d.%d.%d" % sys.version_info[:3]},
        "source": {"fingerprints_sha256": fps,
                   "repo_pins_match": {k: (fps[k] == REPO_PINS[k]) for k in sorted(REPO_PINS)}},
        "registry": registry_section(),
        "cases": cases,
    }


# ============================================================
# 5. 入口
# ============================================================

def _cases_bytes(rep: dict) -> bytes:
    return canon(rep["cases"]).encode("utf-8")


def _source_bytes(rep: dict) -> bytes:
    return canon({"source": rep["source"], "registry": rep["registry"]}).encode("utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="P2 试点五动作行为冻结基线")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--emit", action="store_true", help="采集并写基线文件")
    g.add_argument("--check", action="store_true", help="重跑与基线对拍（行为段逐字节）")
    g.add_argument("--stdout", action="store_true", help="只打印规范 JSON，不写盘")
    g.add_argument("--list", action="store_true", help="列出 case")
    args = ap.parse_args(argv)

    if args.list:
        for cid, group, desc, _fn in _CASES:
            print("%-42s [%s] %s" % (cid, group, desc))
        return 0

    rep = build_report()

    # 口径自检：本脚本的源码指纹必须与仓内既有冻结门禁的 _PIN 一致
    bad_pin = [k for k, ok in rep["source"]["repo_pins_match"].items() if not ok]
    if bad_pin:
        print("!! 源码指纹与仓内 _PIN 不一致（tests/test_u1d2_triggers_extra_frozen.py）：%s"
              % "、".join(bad_pin), file=sys.stderr)

    if args.stdout:
        sys.stdout.write(canon(rep))
        return 0

    if args.emit:
        with open(BASELINE_PATH, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(canon(rep))
        print("基线已写：%s（%d 条 case）" % (BASELINE_PATH, len(rep["cases"])))
        print("源码指纹：" + "，".join("%s=%s" % (k, v[:12]) for k, v in
                                     sorted(rep["source"]["fingerprints_sha256"].items())))
        return 1 if bad_pin else 0

    if args.check:
        if not os.path.isfile(BASELINE_PATH):
            print("基线不存在：%s（先跑 --emit）" % BASELINE_PATH, file=sys.stderr)
            return 2
        old = json.load(open(BASELINE_PATH, encoding="utf-8"))
        old_b, new_b = _cases_bytes(old), _cases_bytes(rep)
        diff_ids = []
        if old_b != new_b:
            om = {c["id"]: c for c in old["cases"]}
            nm = {c["id"]: c for c in rep["cases"]}
            for cid in sorted(set(om) | set(nm)):
                if canon(om.get(cid)) != canon(nm.get(cid)):
                    diff_ids.append(cid)
        src_changed = _source_bytes(old) != _source_bytes(rep)
        print("case 数：基线 %d / 现跑 %d" % (len(old["cases"]), len(rep["cases"])))
        print("行为段（cases）：%s" % ("逐字节相同 ✅" if not diff_ids else "有差异 ❌"))
        if diff_ids:
            for cid in diff_ids:
                print("  · 差异 case：%s" % cid)
        print("指纹段（source/registry）：%s" % ("未变" if not src_changed else
                                              "已变（换实现属预期；行为段必须仍相同）"))
        if bad_pin:
            print("  ！仓内 _PIN 也不一致：%s" % "、".join(bad_pin))
        return 0 if (not diff_ids and not bad_pin) else 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
