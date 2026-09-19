# -*- coding: utf-8 -*-
"""U1-I5 条件族**去双源**冻结比对门禁 —— 包内自建条件注册表 → 引擎 `conditions.Conditions`。

本门禁守 7 组（BRIEF §2.3 + §6.2）：

  A **双 sha256 冻结**：旧实现文本逐字冻在本文件里（`_FROZEN_SRC`，sha256 钉住）+
    活实现 `inspect.getsource` 的 sha256 钉住（5 谓词 / 动作各一枚）。
  B **谓词体逐字**：5 个谓词 `inspect.getsource` **去掉装饰器行后**与冻结旧实现**逐字节相等**
    ⇒ 「只换注册到哪、判定逻辑一字不改」不是靠读代码觉得等价，是逐字比出来的。
  C **注册表语义**：表载体 = 引擎 `Conditions` 实例 · 5 键 + 声明序 · 同 key 覆盖（后者胜、
    位置不动）· 未知键 `get→None` / `has→False` / `in→False` · 装饰器路与直接路同实现。
  D **逐键等价**：5 键 × 场景矩阵（含 `None` target / 缺失字段 / 空 cond / 未知键 /
    谓词抛错 / 边界）「旧判定 vs 新判定」逐格比对 —— 旧实现由本文件的冻结文本 `exec` 出来。
  E **口径分歧断言**：4 条故意差异**每条一条具名断言**（不是藏起来的）：键校验 fail-closed ·
    `[k]` 错误类型 · 动作对非法键改静默 · 不可哈希键「崩 → 不崩」。
  F **零知识静态扫描**：AST 扫 `content/**`（不 import）⇒ 5 个条件键的注册点**只有**
    `content/mech/cond_procs.py` 一处；该文件顶层 `Conditions()` 恰 1 处、无 dict 字面量注册表；
    数据侧 `cond_specs.json` 不得再定义这 5 键。
  G **有牙反证**：3 个单点装坏（改谓词临界判断 / 注册表少一个键 / 换掉重复注册语义）+
    1 个**双坏同现**（缺键 + 谓词坏）+ 报告**顺序断言**；每例都断言门禁**变红且点名**；
    跑完**不写盘**地还原（模块文件 sha 前后相等 + 复跑全绿）。

跑法：见 BRIEF §3.2（`GWEN_FRAMEWORK_DIR` / `GWEN_HOST_DIR` / `GWEN_GAME_DB` / `PYTHONUTF8=1`）。
"""
import ast
import hashlib
import inspect
import json
import os
import re
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_u1i5_cond.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _cfg  # noqa: E402,F401
from _engine_harness import boot as _eng_cfg  # noqa: E402
_eng_cfg()

from saintess_engine.conditions import Conditions, UnknownCondition  # noqa: E402
from content.mech import cond_procs as CP  # noqa: E402  直取包内真源（原 battle_cond_procs）

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


# ===========================================================================
# §A 冻结：旧实现（`base/pkg/content/mech/cond_procs.py:37-166`）逐字
# ===========================================================================
# 口径：**不改一字**（含空行 / 缩进 / 注释 / 文案）。它是本门禁的「旧判定」唯一真源 ——
#      与活实现比对时，旧侧不是「照记忆重写」，而是这段被 sha256 钉住的原文 exec 出来的。
_FROZEN_SRC = r'''# 敌方减益键（控制/属性降）；DOT/印记类走 effects 层数判定
_DEBUFF_KEYS = ("def_down", "spd_down", "mon_atk_down", "atk_down",
                "stun", "freeze", "silence")
_DOT_KEYS = ("poison", "burn", "bleed", "mark")
# 旋律增益系（咏叹调 desc「当前旋律为增益系时 ×1.3」）
_MELODY_BUFF_KINDS = ("atk", "def", "spd", "atk_matk", "all")

COND_PREDICATES: dict = {}


def register_cond(key):
    """条件类型注册（加类型 = 加一行；未注册 type 静默不生效）。"""
    def deco(fn):
        COND_PREDICATES[key] = fn
        return fn
    return deco


def _spd_of(battle, actor) -> float:
    if not isinstance(actor, dict):
        return 0.0
    try:
        from saintess_engine import stats as S
        st = S.actor_stats(battle, actor) or {}
        return float(st.get("spd", 0) or 0)
    except Exception:
        return float(actor.get("spd", 0) or 0)


@register_cond("player_first")
def _p_player_first(battle, actor, target, cond) -> bool:
    """先手：速度高于目标（v2.0）。"""
    return _spd_of(battle, actor) > _spd_of(battle, target)


@register_cond("enemy_debuff")
def _p_enemy_debuff(battle, actor, target, cond) -> bool:
    """敌方有减益（控制/属性降 + 目标级 DOT/印记层）。"""
    if not isinstance(target, dict):
        return False
    ef = target.get("effects") or {}
    if any(k in ef for k in _DEBUFF_KEYS):
        return True
    for k in _DOT_KEYS:
        e = ef.get(k)
        if isinstance(e, dict) and int(e.get("stacks", 0) or 0) > 0:
            return True
        if e:  # 无 stacks 结构的条目存在即算减益（控制型）
            return True
    deb = target.get("debuffs") or {}
    return any(int((deb.get(k) or {}).get("n", 0) or 0) > 0 for k in _DOT_KEYS)


@register_cond("enemy_broken")
def _p_enemy_broken(battle, actor, target, cond) -> bool:
    """敌方被破防/震慑中（破绽条触发态）——与 bar_trigger 后状态同源。

    条状态载体 = 目标 effects[BAR_STATE_PREFIX+shaken]；读取前先结算到当刻
    （衰减时间制：不结算会读到过期值）。
    """
    if not isinstance(target, dict):
        return False
    from saintess_engine.gauge import bar_settle, bar_effect_key
    _now = float(getattr(battle, "_now", 0.0) or 0.0)
    bar_settle(target, "shaken", _now)
    bs = (target.get("effects") or {}).get(bar_effect_key("shaken"))
    if not isinstance(bs, dict):
        return False
    return (int(bs.get("trigger_count", 0) or 0) > 0
            and float(bs.get("immune_until", 0.0) or 0.0) > _now)


@register_cond("melody_buff")
def _p_melody_buff(battle, actor, target, cond) -> bool:
    """施法者当前旋律为增益系（读 effects.melody_state.kind）。

    注意：旧 battle_conds 读 `battle._melody["kind"]`（旧引擎载体，saintess_engine 无写入方）；
    saintess_engine 真实载体 = 施法者 `effects["melody_state"]`（class_mech_proc.class_melody_act 写）。
    """
    if not isinstance(actor, dict):
        return False
    st = (actor.get("effects") or {}).get("melody_state") or {}
    return st.get("kind") in _MELODY_BUFF_KINDS


@register_cond("melody_stacks")
def _p_melody_stacks(battle, actor, target, cond) -> bool:
    """施法者旋律强度 ≥ stacks（旧读 `_melody["stack"]`，saintess_engine 实键为 `stacks`）。"""
    if not isinstance(actor, dict):
        return False
    st = (actor.get("effects") or {}).get("melody_state") or {}
    need = int(cond.get("stacks", 4) or 4)
    return int(st.get("stacks", 0) or 0) >= need


@register_action("skill_cond_mult")
def skill_cond_mult_act(battle, caster, target, params, logs):
    """dmg_calc / heal_calc：技能 cond 条件倍率 → 累乘 battle._fire_ctx["mult"]。"""
    ctx = getattr(battle, "_fire_ctx", None)
    if not isinstance(ctx, dict):
        return
    info = ctx.get("info") or {}
    cond = info.get("cond")
    if not isinstance(cond, dict):
        return  # 无字段 = 不启用
    fn = COND_PREDICATES.get(cond.get("type"))
    if fn is None:
        return  # 未注册类型：静默不生效（不给断言/不崩）
    actor = ctx.get("actor") or caster
    tgt = ctx.get("target")
    if tgt is None:
        tgt = target
    try:
        if not fn(battle, actor, tgt, cond):
            return
    except Exception:
        return  # 判定异常不阻断战斗
    try:
        from saintess_engine.battle.formulas import skill_cond_mult
        from ..apply import _SKILL_LOOKUP as _PKG_SKILLS, skill_level_of
        skill_info = _PKG_SKILLS.skill_info
        name = info.get("name") or ""
        lv = skill_level_of(actor, name) if (actor or {}).get("class_name") else 1
        mult = float(skill_cond_mult(cond, max(1, int(lv or 1)), info) or 1.0)
    except Exception:
        mult = float(cond.get("mult", 1.0) or 1.0)
    if mult == 1.0:
        return
    ctx["mult"] = float(ctx.get("mult", 1.0) or 1.0) * mult
    logs.append(f"✨ 条件达成【{cond.get('type')}】×{mult:g}")
'''

#: 冻结片段文本 sha256（改本文件的冻结块 = 立刻红）
#: 来源 = **改动前**的 `content/mech/cond_procs.py:37-166`（含行尾最后那个 `\n`）；
#: 落地前已离线实测：`base/pkg/content/mech/cond_procs.py:37-166 + "\n"` 与 `_FROZEN_SRC`
#: **逐字节相等**（4488 字节 / 130 行，LF 行尾）。
FROZEN_TEXT_SHA256 = "613371ee5c33c548e9ec62764c94229cb639cc0aced6e8b6f85da15c54c4551d"
#: 活实现 sha256 —— `inspect.getsource`（5 谓词按声明序拼接，含装饰器行）
LIVE_PREDS_SHA256 = "5a6da1cafabb335de47aaeddb5fccbee07df01e7e7857108dd30c224c9a43224"
#: 活实现 sha256 —— `inspect.getsource(skill_cond_mult_act)`（含装饰器行）
LIVE_ACTION_SHA256 = "ecdc36508b0d61b102db9e78d9336db08d5bb9a5f6fbd1874bf7f7f4a1c5fe29"

PRED_ORDER = ("player_first", "enemy_debuff", "enemy_broken", "melody_buff", "melody_stacks")
COND_KEYS = frozenset(PRED_ORDER)
#: 键 → 模块顶层函数名（冻结钉住的一个面：「注册的就是模块顶层那只函数」）
PRED_FN = {
    "player_first": "_p_player_first",
    "enemy_debuff": "_p_enemy_debuff",
    "enemy_broken": "_p_enemy_broken",
    "melody_buff": "_p_melody_buff",
    "melody_stacks": "_p_melody_stacks",
}
#: 引擎注册表在包内的实例名（本批新增的私有名 —— 单源审计要点名的对象）
LIVE_REGISTRY_NAME = "_CONDITIONS"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _strip_decorators(src: str) -> str:
    """去掉前导 `@deco(...)` 行 —— 只比函数体（本次唯一允许改动的就是装饰器调用的对象）。"""
    lines = src.splitlines()
    i = 0
    while i < len(lines) and lines[i].lstrip().startswith("@"):
        i += 1
    return "\n".join(lines[i:])


_FROZEN_TREE = ast.parse(_FROZEN_SRC, filename="<u1i5-frozen-old>")


def _frozen_src_of(fn_name: str):
    """从**冻结文本**里按 AST 取某个顶层函数的原文（含装饰器；`exec` 出来的函数取不到 source）。"""
    for node in _FROZEN_TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            seg = ast.get_source_segment(_FROZEN_SRC, node)
            if seg is not None:
                return seg
    return None


def _build_frozen():
    """把冻结的旧实现 exec 出来（旧注册表 / 旧谓词 / 旧动作）。

    `@register_action` 换成**只记录、不注册**的假装饰器 —— 绝不让旧动作进引擎注册表
    （否则 `EXPECT_ACTION_KEYS["cond_procs"]` 会被污染）。
    `__package__` / `__name__` 给成 `content.mech.*`，让动作里那句相对 import
    （`from ..apply import ...`）与活实现走**同一条**路径（不因 exec 而退化到 except 兜底）。
    """
    recorded = []

    def _fake_register_action(key):
        recorded.append(key)

        def _deco(fn):
            return fn
        return _deco

    ns = {
        "__name__": "content.mech._u1i5_frozen_old",
        "__package__": "content.mech",
        "register_action": _fake_register_action,
    }
    exec(compile(_FROZEN_SRC, "<u1i5-frozen-old>", "exec"), ns)
    ns["_RECORDED_ACTIONS"] = tuple(recorded)
    return ns


_FROZEN = _build_frozen()
_FROZEN_REG = _FROZEN["COND_PREDICATES"]


# ===========================================================================
# §B 冻结审计（每条返回 violations 列表；主流程与有牙反证共用同一批函数）
# ===========================================================================

def _live_preds_source():
    """5 谓词的活源码（按**模块顶层函数名**取 —— 与注册表内容解耦，sha 只随文件文本变）。"""
    return "\n".join(inspect.getsource(getattr(CP, PRED_FN[k])) for k in PRED_ORDER)


def audit_dual_sha():
    """A 组：双（三）sha256。"""
    v = []
    got = _sha(_FROZEN_SRC)
    if got != FROZEN_TEXT_SHA256:
        v.append("冻结片段文本 sha256 漂了：实测 %s / 记录 %s" % (got, FROZEN_TEXT_SHA256))
    got = _sha(_live_preds_source())
    if got != LIVE_PREDS_SHA256:
        v.append("活实现（5 谓词）sha256 漂了：实测 %s / 记录 %s" % (got, LIVE_PREDS_SHA256))
    got = _sha(inspect.getsource(CP.skill_cond_mult_act))
    if got != LIVE_ACTION_SHA256:
        v.append("活实现（动作）sha256 漂了：实测 %s / 记录 %s" % (got, LIVE_ACTION_SHA256))
    return v


def audit_predicate_bytes():
    """B 组：5 个谓词「去装饰器后」与冻结旧实现逐字节相等。"""
    v = []
    for k in PRED_ORDER:
        live_fn = CP.COND_PREDICATES.get(k)
        old_fn = _FROZEN_REG.get(k)
        if live_fn is None or old_fn is None:
            v.append("谓词 %s 在（新/旧）注册表里缺失" % k)
            continue
        live = _strip_decorators(inspect.getsource(live_fn))
        old_raw = _frozen_src_of(old_fn.__name__)
        if old_raw is None:
            v.append("冻结文本里找不到旧谓词 %s 的原文" % old_fn.__name__)
            continue
        old = _strip_decorators(old_raw)
        if live != old:
            v.append("谓词 %s 的函数体不再是旧实现的逐字节拷贝" % k)
    # 动作体：本次只许动「查表那几行」；判定/累乘/文案部分必须逐字节保留
    live_a = inspect.getsource(CP.skill_cond_mult_act)
    for needle in ('logs.append(f"✨ 条件达成【{cond.get(\'type\')}】×{mult:g}")',
                   'ctx["mult"] = float(ctx.get("mult", 1.0) or 1.0) * mult',
                   'except Exception:\n        return  # 判定异常不阻断战斗'):
        if needle not in live_a:
            v.append("动作里被冻结的字节丢了：%r" % needle[:48])
    return v


def audit_registry_shape(reg):
    """C 组：注册表载体与语义（键集 / 声明序 / 别名身份 / 未知键）。"""
    v = []
    if not isinstance(reg, Conditions):
        v.append("COND_PREDICATES 不是引擎 Conditions 实例：%r" % type(reg))
    if isinstance(reg, dict):
        v.append("COND_PREDICATES 仍是自建 dict（第二份实现没删干净）")
    if getattr(CP, "COND_PREDICATES", None) is not getattr(CP, LIVE_REGISTRY_NAME, None):
        v.append("COND_PREDICATES 不是 %s 的别名（被复制成了第二份）" % LIVE_REGISTRY_NAME)
    if CP.register_cond != getattr(CP, LIVE_REGISTRY_NAME).register:
        v.append("register_cond 不是引擎 Conditions.register 的别名")
    if list(reg.keys()) != list(PRED_ORDER):
        v.append("键集/声明序漂了：%r != %r" % (list(reg.keys()), list(PRED_ORDER)))
    if len(reg) != len(PRED_ORDER):
        v.append("注册表长度漂了：%d != %d" % (len(reg), len(PRED_ORDER)))
    for k in PRED_ORDER:
        fn = reg.get(k)
        if fn is None:
            v.append("键 %s 取不到判定函数" % k)
            continue
        if not callable(fn):
            v.append("键 %s 的判定函数不可调用" % k)
        if getattr(fn, "__module__", "") != "content.mech.cond_procs":
            v.append("键 %s 的判定函数来路不是本模块：%r" % (k, getattr(fn, "__module__", None)))
        mod_fn = getattr(CP, fn.__name__, None)
        if mod_fn is not fn:
            v.append("键 %s 注册的不是模块顶层那只函数（疑似复制）" % k)
    # 未知键三口径
    if reg.get("not_registered_yet") is not None:
        v.append("未知键 get 应为 None")
    if reg.has("not_registered_yet") is not False:
        v.append("未知键 has 应为 False")
    if "not_registered_yet" in reg:
        v.append("未知键 in 应为 False")
    extra = sorted(set(reg.keys()) - COND_KEYS)
    if extra:
        v.append("注册表里混进了非本族键：%r" % extra)
    if tuple(CP.__all__) != ("skill_cond_mult_act", "COND_PREDICATES", "register_cond",
                             "apply_cond_procs"):
        v.append("__all__ 对外名字面漂了：%r" % (CP.__all__,))
    return v


PROBE_KEY = "u1i5_dup_probe"
PROBE_DECO_KEY = "u1i5_dup_probe_deco"


def audit_dup_semantics(reg):
    """C 组：同 key 覆盖（后者胜 / 位置不动 / 不增项）+ 装饰器路与直接路同实现。"""
    v = []
    before_keys = list(reg.keys())
    before_len = len(reg)

    def _f1(*a):
        return 1

    def _f2(*a):
        return 2

    def _f3(*a):
        return 3

    try:
        reg.register(PROBE_KEY, _f1)
        if reg.get(PROBE_KEY) is not _f1:
            v.append("直接路 register(key, fn) 未生效")
        pos1 = reg.keys().index(PROBE_KEY)
        # 同 key 再注册 = 覆盖（后者胜）
        reg.register(PROBE_KEY, _f2)
        if reg.get(PROBE_KEY) is not _f2:
            v.append("同 key 再注册没有覆盖（重复注册语义变了）")
        if reg.keys().index(PROBE_KEY) != pos1:
            v.append("同 key 覆盖动了登记序（位置应从首次登记起算）")
        if len(reg) != before_len + 1:
            v.append("同 key 覆盖多出一个登记项：%d" % len(reg))
        # 装饰器路（`@reg.register(key)`）
        @reg.register(PROBE_DECO_KEY)
        def _probe_deco(*a):
            return 3

        if reg.get(PROBE_DECO_KEY) is not _probe_deco:
            v.append("装饰器路 register(key) 未生效 / 没返回原函数")
        if _probe_deco() != 3:
            v.append("装饰器路登记的不是原函数（返回值不可调用）")
    finally:
        reg.pop(PROBE_KEY, None)
        reg.pop(PROBE_DECO_KEY, None)
    if list(reg.keys()) != before_keys or len(reg) != before_len:
        v.append("探针键没清干净（注册表被本审计污染了）")
    return v


# ---------------------------------------------------------------------------
# D 组：场景矩阵（每个工厂**每次调用都出新对象** —— enemy_broken 会结算并改写 target）
# ---------------------------------------------------------------------------

class _B:
    """最小战斗替身：谓词只读 `battle._now`。"""

    def __init__(self, now=0.0):
        self._now = now


class _BNoClock:
    """没有 `_now` 的 battle（走 `getattr(battle, "_now", 0.0)` 兜底）。"""


def _A(**kw):
    return dict(kw)


def _FX(**kw):
    return {"effects": dict(kw)}


def build_scenarios():
    from saintess_engine.gauge import bar_effect_key
    bkey = bar_effect_key("shaken")
    out = []

    def add(key, label, factory):
        out.append((key, label, factory))

    # ---- player_first（_spd_of 双侧）----
    add("player_first", "速度占优", lambda: (_B(), _A(spd=30), _A(spd=5), {}))
    add("player_first", "速度劣势", lambda: (_B(), _A(spd=5), _A(spd=99), {}))
    add("player_first", "速度相等", lambda: (_B(), _A(spd=10), _A(spd=10), {}))
    add("player_first", "actor 非 dict(None)", lambda: (_B(), None, _A(spd=5), {}))
    add("player_first", "actor 非 dict(list)", lambda: (_B(), [], _A(spd=0), {}))
    add("player_first", "target 非 dict", lambda: (_B(), _A(spd=30), None, {}))
    add("player_first", "双方都缺 spd 字段", lambda: (_B(), _A(), _A(), {}))
    add("player_first", "spd 为 None", lambda: (_B(), _A(spd=None), _A(spd=-1), {}))

    # ---- enemy_debuff（减益键 / DOT 层 / 无 stacks 条目 / debuffs.n）----
    add("enemy_debuff", "target 非 dict", lambda: (_B(), _A(), None, {}))
    add("enemy_debuff", "空 target", lambda: (_B(), _A(), _A(), {}))
    add("enemy_debuff", "effects=None", lambda: (_B(), _A(), _A(effects=None), {}))
    add("enemy_debuff", "属性降 def_down", lambda: (_B(), _A(), _FX(def_down={}), {}))
    add("enemy_debuff", "控制 stun", lambda: (_B(), _A(), _FX(stun=1), {}))
    add("enemy_debuff", "DOT poison stacks=2", lambda: (_B(), _A(), _FX(poison={"stacks": 2}), {}))
    add("enemy_debuff", "DOT poison stacks=0", lambda: (_B(), _A(), _FX(poison={"stacks": 0}), {}))
    add("enemy_debuff", "DOT poison 空 dict（falsy）", lambda: (_B(), _A(), _FX(poison={}), {}))
    add("enemy_debuff", "DOT burn 非 dict 真值", lambda: (_B(), _A(), _FX(burn="x"), {}))
    add("enemy_debuff", "debuffs.poison n=3", lambda: (_B(), _A(), _A(debuffs={"poison": {"n": 3}}), {}))
    add("enemy_debuff", "debuffs.poison n=0", lambda: (_B(), _A(), _A(debuffs={"poison": {"n": 0}}), {}))
    add("enemy_debuff", "debuffs=None", lambda: (_B(), _A(), _A(debuffs=None), {}))

    # ---- enemy_broken（条状态：结算 + trigger_count + immune_until）----
    add("enemy_broken", "target 非 dict", lambda: (_B(), _A(), None, {}))
    add("enemy_broken", "无条状态", lambda: (_B(), _A(), _A(), {}))
    add("enemy_broken", "触发窗口内", lambda: (_B(0.0), _A(),
                                              _A(effects={bkey: {"trigger_count": 1, "immune_until": 2.0}}), {}))
    add("enemy_broken", "trigger_count=0", lambda: (_B(0.0), _A(),
                                                   _A(effects={bkey: {"trigger_count": 0, "immune_until": 2.0}}), {}))
    add("enemy_broken", "免疫已过期", lambda: (_B(1.0), _A(),
                                              _A(effects={bkey: {"trigger_count": 1, "immune_until": 0.5}}), {}))
    add("enemy_broken", "条状态非 dict", lambda: (_B(0.0), _A(), _A(effects={bkey: "x"}), {}))
    add("enemy_broken", "battle 无 _now（兜底 0.0）", lambda: (_BNoClock(), _A(),
                                                             _A(effects={bkey: {"trigger_count": 1,
                                                                                "immune_until": 1.0}}), {}))
    add("enemy_broken", "缺 immune_until 字段", lambda: (_B(0.0), _A(),
                                                        _A(effects={bkey: {"trigger_count": 1}}), {}))

    # ---- melody_buff（读 actor.effects.melody_state.kind）----
    add("melody_buff", "actor 非 dict", lambda: (_B(), None, _A(), {}))
    add("melody_buff", "无 melody_state", lambda: (_B(), _A(), _A(), {}))
    add("melody_buff", "effects=None", lambda: (_B(), _A(effects=None), _A(), {}))
    add("melody_buff", "kind=atk（增益系）", lambda: (_B(), _FX(melody_state={"kind": "atk"}), _A(), {}))
    add("melody_buff", "kind=all（增益系）", lambda: (_B(), _FX(melody_state={"kind": "all"}), _A(), {}))
    add("melody_buff", "kind=e_atk（挽歌系）", lambda: (_B(), _FX(melody_state={"kind": "e_atk"}), _A(), {}))
    add("melody_buff", "melody_state 为空", lambda: (_B(), _FX(melody_state={}), _A(), {}))
    add("melody_buff", "melody_state 非 dict", lambda: (_B(), _FX(melody_state="x"), _A(), {}))

    # ---- melody_stacks（cond.stacks 阈值 + 默认值）----
    add("melody_stacks", "actor 非 dict", lambda: (_B(), None, _A(), {"stacks": 1}))
    add("melody_stacks", "5 ≥ 4 → True", lambda: (_B(), _FX(melody_state={"stacks": 5}), _A(), {"stacks": 4}))
    add("melody_stacks", "3 < 4 → False", lambda: (_B(), _FX(melody_state={"stacks": 3}), _A(), {"stacks": 4}))
    add("melody_stacks", "cond 缺 stacks → 默认 4", lambda: (_B(), _FX(melody_state={"stacks": 4}), _A(), {}))
    add("melody_stacks", "stacks=None → 默认 4", lambda: (_B(), _FX(melody_state={"stacks": 4}), _A(),
                                                        {"stacks": None}))
    add("melody_stacks", "无 melody_state", lambda: (_B(), _A(), _A(), {"stacks": 1}))
    add("melody_stacks", "cond=None → 旧新同抛 AttributeError", lambda: (_B(),
                                                                        _FX(melody_state={"stacks": 9}), _A(), None))
    add("melody_stacks", "stacks 为字符串数字", lambda: (_B(), _FX(melody_state={"stacks": "5"}), _A(),
                                                       {"stacks": "4"}))
    return out


def _probe(fn, args):
    """把「返回值」与「异常类型」都收成可比形状。"""
    try:
        return ("ret", fn(*args))
    except Exception as e:                       # noqa: BLE001 门禁要看异常类型
        return ("raise", type(e).__name__)


def audit_key_equivalence(reg):
    """D 组：5 键 × 场景矩阵「旧判定 vs 新判定」逐格比对。"""
    v = []
    cells = 0
    for key, label, factory in build_scenarios():
        old_fn = _FROZEN_REG.get(key)
        new_fn = reg.get(key)
        if old_fn is None or new_fn is None:
            v.append("键 %s 在某一侧缺失（旧=%r 新=%r）" % (key, old_fn, new_fn))
            continue
        old = _probe(old_fn, factory())
        new = _probe(new_fn, factory())
        cells += 1
        if old != new:
            v.append("键 %s 场景「%s」不一致：旧=%r 新=%r" % (key, label, old, new))
    if cells < 40:
        v.append("场景矩阵疑似空转：只跑了 %d 格" % cells)
    return v


# ---------------------------------------------------------------------------
# D 组（动作级）：`skill_cond_mult_act` 旧 vs 新
# ---------------------------------------------------------------------------

def _fire(info, actor=None, target=None, mult=None, with_ctx=True, omit=()):
    ctx = {"info": info, "actor": actor, "target": target}
    if mult is not None:
        ctx["mult"] = mult
    for k in omit:
        ctx.pop(k, None)
    return ctx if with_ctx else None


def build_action_cases():
    """(标签, 造 case 的函数) —— 每格都出新对象。"""
    out = []

    def add(label, factory):
        out.append((label, factory))

    add("未注册 type", lambda: dict(fire=_fire({"name": "幽灵", "cond": {"type": "nope", "mult": 9.9}}),
                                    caster=_A(), target=_A()))
    add("空 cond dict", lambda: dict(fire=_fire({"name": "x", "cond": {}}), caster=_A(), target=_A()))
    add("cond 缺 type", lambda: dict(fire=_fire({"name": "x", "cond": {"mult": 1.3}}),
                                     caster=_A(), target=_A()))
    add("type=None", lambda: dict(fire=_fire({"name": "x", "cond": {"type": None, "mult": 1.3}}),
                                  caster=_A(), target=_A()))
    add("type=空串", lambda: dict(fire=_fire({"name": "x", "cond": {"type": "", "mult": 1.3}}),
                                  caster=_A(), target=_A()))
    add("type=数字(可哈希非串)", lambda: dict(fire=_fire({"name": "x", "cond": {"type": 7, "mult": 1.3}}),
                                              caster=_A(), target=_A()))
    add("cond 非 dict", lambda: dict(fire=_fire({"name": "x", "cond": "boom"}), caster=_A(), target=_A()))
    add("info 缺 cond", lambda: dict(fire=_fire({"name": "x"}), caster=_A(), target=_A()))
    add("info=None", lambda: dict(fire=_fire(None), caster=_A(), target=_A()))
    add("battle 无 _fire_ctx", lambda: dict(fire=None, caster=_A(), target=_A()))
    add("命中 player_first → ×1.3", lambda: dict(
        fire=_fire({"name": "冲锋", "cond": {"type": "player_first", "mult": 1.3}},
                   actor=_A(spd=30), target=_A(spd=5)), caster=_A(spd=1), target=_A(spd=1)))
    add("未命中 player_first", lambda: dict(
        fire=_fire({"name": "冲锋", "cond": {"type": "player_first", "mult": 1.3}},
                   actor=_A(spd=1), target=_A(spd=30)), caster=_A(), target=_A()))
    add("命中但 mult=1.0 → 不写不改不播报", lambda: dict(
        fire=_fire({"name": "冲锋", "cond": {"type": "player_first", "mult": 1.0}},
                   actor=_A(spd=30), target=_A(spd=5)), caster=_A(), target=_A()))
    add("预置 mult=2.0 → 累乘 2.6", lambda: dict(
        fire=_fire({"name": "冲锋", "cond": {"type": "player_first", "mult": 1.3}, "mult": 2.0},
                   actor=_A(spd=30), target=_A(spd=5)), caster=_A(), target=_A()))
    add("ctx 缺 target → 回退入参 target(_p_enemy_debuff)", lambda: dict(
        fire=_fire({"name": "狙击", "cond": {"type": "enemy_debuff", "mult": 1.3}},
                   actor=_A(), omit=("target",)),
        caster=_A(), target=_FX(def_down={})))
    add("ctx 缺 actor → 回退 caster", lambda: dict(
        fire=_fire({"name": "狙击", "cond": {"type": "enemy_debuff", "mult": 1.3}},
                   target=_FX(def_down={}), omit=("actor",)),
        caster=_A(), target=_A()))
    add("ctx.actor 为假值 → 回退 caster", lambda: dict(
        fire=_fire({"name": "狙击", "cond": {"type": "enemy_debuff", "mult": 1.3}},
                   actor=None, target=_FX(def_down={})),
        caster=_A(), target=_A()))
    add("melody_stacks 命中", lambda: dict(
        fire=_fire({"name": "天籁", "cond": {"type": "melody_stacks", "stacks": 4, "mult": 1.3}},
                   actor=_FX(melody_state={"stacks": 5}), target=_A()), caster=_A(), target=_A()))
    add("带 class_name 走技能等级段", lambda: dict(
        fire=_fire({"name": "侧踢", "cond": {"type": "player_first", "mult": 1.3}},
                   actor=_A(spd=30, class_name="cls_wu_seng"), target=_A(spd=5)),
        caster=_A(), target=_A()))
    return out


def _run_action(fn, case):
    logs = []
    b = _B()
    if case["fire"] is not None:
        b._fire_ctx = case["fire"]
    try:
        fn(b, case["caster"], case["target"], None, logs)
        out = ("ok", float((getattr(b, "_fire_ctx", {}) or {}).get("mult", 1.0) or 1.0))
    except Exception as e:                       # noqa: BLE001
        out = ("raise", type(e).__name__)
    return out + (tuple(logs),)


def audit_action_matrix(reg=None):
    """D 组（动作级）：旧动作 vs 新动作逐格比对（含兜底分支与日志文案）。"""
    v = []
    old_act = _FROZEN["skill_cond_mult_act"]
    new_act = CP.skill_cond_mult_act
    cells = 0
    for label, factory in build_action_cases():
        old = _run_action(old_act, factory())
        new = _run_action(new_act, factory())
        cells += 1
        if old != new:
            v.append("动作场景「%s」不一致：旧=%r 新=%r" % (label, old, new))
    if cells < 18:
        v.append("动作矩阵疑似空转：只跑了 %d 格" % cells)
    # 命中一格的**逐字**文案（冻结文案，不是「看着像」）
    logs = []
    b = _B()
    b._fire_ctx = {"info": {"name": "冲锋", "cond": {"type": "player_first", "mult": 1.3}},
                   "actor": {"spd": 30}, "target": {"spd": 5}}
    new_act(b, {}, {}, None, logs)
    if logs != ["✨ 条件达成【player_first】×1.3"]:
        v.append("命中日志文案漂了：%r" % (logs,))
    # 「键在但谓词抛错」：两本注册表各注册一只会抛的探针键
    boom = "u1i5_boom_probe"

    def _boom(*a):
        raise RuntimeError("判定炸了")

    try:
        reg.register(boom, _boom)
        _FROZEN_REG[boom] = _boom          # 旧侧是自建 dict：直接赋值（旧 API 的真实形状）
        case = dict(fire=_fire({"name": "x", "cond": {"type": boom, "mult": 1.3}}),
                    caster=_A(), target=_A())
        old = _run_action(old_act, case)
        new = _run_action(new_act, case)
        if old != new:
            v.append("「键在但谓词抛错」旧新不一致：旧=%r 新=%r" % (old, new))
        if new[0] != "ok" or new[1] != 1.0 or new[2]:
            v.append("谓词抛错应被吞掉（不写 mult / 不播报）：%r" % (new,))
    finally:
        reg.pop(boom, None)
        _FROZEN_REG.pop(boom, None)
    return v


# ---------------------------------------------------------------------------
# E 组：口径分歧断言（4 条，每条具名 —— 故意保留的差异必须被看见）
# ---------------------------------------------------------------------------

def audit_divergences(reg):
    v = []
    # 分歧①：键校验 fail-closed（引擎 `_check_key`）
    try:
        reg.register("", lambda *a: True)
        v.append("分歧①：空串键应被引擎拒（ValueError）")
    except ValueError:
        pass
    except Exception as e:                       # noqa: BLE001
        v.append("分歧①：空串键异常类型不是 ValueError：%r" % type(e).__name__)
    try:
        reg.register("   ", lambda *a: True)
        v.append("分歧①：空白串键应被引擎拒（ValueError）")
    except ValueError:
        pass
    except Exception as e:                       # noqa: BLE001
        v.append("分歧①：空白串键异常类型不是 ValueError：%r" % type(e).__name__)
    # 分歧④：缺键取值的错误类型（旧 dict → KeyError；新 → UnknownCondition）
    try:
        reg["not_registered_yet"]
        v.append("分歧④：未注册键 [] 应抛 UnknownCondition")
    except UnknownCondition as e:
        if not isinstance(e, LookupError):
            v.append("分歧④：UnknownCondition 不是 LookupError 子类")
    except Exception as e:                       # noqa: BLE001
        v.append("分歧④：未注册键 [] 抛的不是 UnknownCondition：%r" % type(e).__name__)
    # 分歧③：非法键（空串 / 不可哈希）在**动作**里一律静默
    for label, bad in (("空串", ""), ("不可哈希 list", []), ("不可哈希 dict", {"a": 1})):
        case = dict(fire=_fire({"name": "x", "cond": {"type": bad, "mult": 9.9}}),
                    caster=_A(), target=_A())
        new = _run_action(CP.skill_cond_mult_act, case)
        if new != ("ok", 1.0, ()):
            v.append("分歧③「%s」应静默（ok/1.0/无日志）：%r" % (label, new))
    # 分歧③ 的另一半：旧实现对不可哈希键**真的会崩**（差异必须是「崩 → 不崩」，不是「两边都静默」）
    old_u = _run_action(_FROZEN["skill_cond_mult_act"],
                        dict(fire=_fire({"name": "x", "cond": {"type": [], "mult": 9.9}}),
                             caster=_A(), target=_A()))
    if old_u != ("raise", "TypeError", ()):
        v.append("分歧③ 前提不成立：旧实现对不可哈希键应为 TypeError，实测 %r" % (old_u,))
    # 分歧②：谓词仍是内容侧 4 参（不是 1 参 ctx）—— 签名形状逐字钉住
    for k in PRED_ORDER:
        fn = reg.get(k)
        try:
            sig = list(inspect.signature(fn).parameters)
        except (TypeError, ValueError) as e:     # noqa: BLE001
            v.append("分歧②：谓词 %s 取不到签名：%r" % (k, e))
            continue
        if sig != ["battle", "actor", "target", "cond"]:
            v.append("分歧②：谓词 %s 签名被改（应保持内容侧 4 参）：%r" % (k, sig))
    # 视图/序列化面：键空间（= 数据侧 cond.type 的合法取值面）未变 —— 即无序列化改动
    if sorted(reg.keys()) != sorted(COND_KEYS):
        v.append("视图面：注册键空间漂了 —— 数据侧 schema/视图需要重估")
    return v


# ---------------------------------------------------------------------------
# F 组：零知识静态扫描（AST / JSON，不 import 被测模块）
# ---------------------------------------------------------------------------
REG_NAME_RE = re.compile(r"(?i).*(?:cond|conditions|predicates|checks|registry).*")
_REG_CALL_NAMES = ("register", "register_cond")
_LITERAL_REG_VALUES = (ast.Dict, ast.DictComp, ast.ListComp, ast.SetComp, ast.List, ast.Tuple)


def _content_root():
    """<pkg>/content（由活模块文件路径反推；不 import 任何东西）。"""
    mech = os.path.dirname(os.path.abspath(CP.__file__))
    return os.path.dirname(mech)


# 口径（为什么这么扫）：
#   · 「注册表」判据 = 顶层 `X = Conditions()`（引擎实例）；`X = _y` / 方法别名 = 再导出（不算第二份）。
#   · 「dict 字面量注册表」判据只对 **cond_procs.py** 断言（旧形态长回来 = 红）。包内别处确有
#     同名形状但不是本族注册表、也非本批范围，故不全局断言：`battle_cond_labels.py:27`
#     `COND_LABELS = {...}`（**文案表**，键 → lambda 出中文标签，不做判定）、
#     `hidden_cond.py:42 CONDITIONS = {}`（**另一个条件族**的注册表，不在本次范围）。
#   · 「键注册点」判据 = 任意深度、函数名为 `register`/`register_cond`、首参为 5 键之一**字面量**
#     的调用（覆盖 `@register_cond("k")` 装饰器路与 `X.register("k", fn)` 直接路）。
def audit_single_source_ast(content_root=None):
    """F 组：5 个条件键在包内**只有一处**注册点；cond_procs 顶层恰 1 个 `Conditions()`。"""
    v = []
    root = content_root or _content_root()
    pkg_root = os.path.dirname(root)
    defs = {}          # rel -> [lineno]  顶层 `X = Conditions()`
    literal_regs = {}  # rel -> [(name, lineno)]  顶层 dict 字面量「注册表」
    key_sites = {}     # rel -> set(keys)  注册调用里的字面量键

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in sorted(dirnames) if d != "__pycache__"]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, pkg_root).replace(os.sep, "/")
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
            for node in tree.body:
                tgt = None
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    tgt = node.targets[0]
                elif isinstance(node, ast.AnnAssign):
                    tgt = node.target
                if not isinstance(tgt, ast.Name) or not REG_NAME_RE.match(tgt.id):
                    continue
                val = node.value
                fname = getattr(val.func, "id", None) or getattr(val.func, "attr", None) \
                    if isinstance(val, ast.Call) else None
                if fname == "Conditions":
                    defs.setdefault(rel, []).append(node.lineno)
                elif isinstance(val, _LITERAL_REG_VALUES):
                    literal_regs.setdefault(rel, []).append((tgt.id, node.lineno))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                f2 = node.func
                nm = getattr(f2, "id", None) or getattr(f2, "attr", None)
                if nm not in _REG_CALL_NAMES:
                    continue
                a0 = node.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str) \
                        and a0.value in COND_KEYS:
                    key_sites.setdefault(rel, set()).add(a0.value)

    # ① 5 个键的注册点 = 只有 cond_procs 一处，且 5 个键齐
    sites = {rel: sorted(ks) for rel, ks in key_sites.items()}
    want_rel = "content/mech/cond_procs.py"
    if set(sites) != {want_rel}:
        v.append("5 个条件键的注册点不止一处（双源长回来了）：%r" % sites)
    elif sites[want_rel] != sorted(COND_KEYS):
        v.append("注册点键集不齐：%r" % (sites[want_rel],))
    # ② cond_procs 顶层 `Conditions()` 恰 1 处；mech/ 下不再有第二处
    if len(defs.get(want_rel, [])) != 1:
        v.append("%s 顶层 `Conditions()` 定义数 != 1：%r" % (want_rel, defs.get(want_rel)))
    mech_defs = {k: n for k, n in defs.items() if k.startswith("content/mech/")}
    if set(mech_defs) != {want_rel}:
        v.append("content/mech/ 下出现第二处条件注册表定义：%r" % mech_defs)
    # ③ cond_procs 顶层不得有 dict 字面量注册表（旧形态长回来 = 红）
    if literal_regs.get(want_rel):
        v.append("%s 顶层仍有 dict 字面量注册表：%r" % (want_rel, literal_regs[want_rel]))
    # ④ 非空转：包内确实有 4 处引擎条件注册表（dialogue / achievement / title / cond_procs）
    if len(defs) < 4:
        v.append("静态扫描疑似空转：全包只找到 %d 处 `Conditions()` 定义" % len(defs))
    for must in ("content/dialogue_conds.py", "content/achievement_conds.py", "content/title_conds.py"):
        if must not in defs:
            v.append("静态扫描漏了既有先例：%s" % must)
    # ⑤ 数据侧：cond_specs.json 不得再定义这 5 键（数据层第二源）
    spec_path = os.path.join(root, "data", "cond_specs.json")
    if os.path.isfile(spec_path):
        with open(spec_path, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            flat = set()
            for dom, items in raw.items():
                if isinstance(items, dict):
                    flat |= set(items)
                elif isinstance(items, list):
                    for it in items:
                        if isinstance(it, dict) and "key" in it:
                            flat.add(it["key"])
            hit = sorted(flat & COND_KEYS)
            if hit:
                v.append("cond_specs.json 又在定义本族键（数据层第二源）：%r" % hit)
    return v


# ===========================================================================
# 汇总：按固定顺序跑全部审计 → [(审计名, 违规串)]
# ===========================================================================
AUDIT_ORDER = ("dual_sha", "predicate_bytes", "registry_shape", "dup_semantics",
               "key_equivalence", "action_matrix", "divergences", "single_source")


def run_report(reg=None, content_root=None):
    reg = CP.COND_PREDICATES if reg is None else reg
    result = {
        "dual_sha": (lambda: audit_dual_sha()),
        "predicate_bytes": (lambda: audit_predicate_bytes()),
        "registry_shape": (lambda: audit_registry_shape(reg)),
        "dup_semantics": (lambda: audit_dup_semantics(reg)),
        "key_equivalence": (lambda: audit_key_equivalence(reg)),
        "action_matrix": (lambda: audit_action_matrix(reg)),
        "divergences": (lambda: audit_divergences(reg)),
        "single_source": (lambda: audit_single_source_ast(content_root)),
    }
    out = []
    for name in AUDIT_ORDER:
        for msg in result[name]():
            out.append((name, msg))
    return out


# ---------------------------------------------------------------------------
# 无盘还原辅助（注册表快照 / 回填，保声明序）
# ---------------------------------------------------------------------------
def _snapshot(reg):
    return [(k, reg.get(k)) for k in reg.keys()]


def _restore(reg, snap):
    for k in list(reg.keys()):
        reg.pop(k, None)
    for k, fn in snap:
        reg.register(k, fn)


def main():
    t_reg = CP.COND_PREDICATES
    print("=" * 74)
    print("U1-I5 条件族去双源 —— 冻结比对门禁（冻结旧实现 vs 引擎 Conditions 活实现）")
    print("=" * 74)

    # ---- 冻结前提 ----
    print("【0】冻结前提")
    check("冻结的旧注册表 exec 出 5 键（旧实现真跑起来了，不是死文本）",
          list(_FROZEN_REG.keys()) == list(PRED_ORDER), list(_FROZEN_REG.keys()))
    check("冻结的旧动作只 @register_action 了 1 个名（且未污染引擎注册表）",
          _FROZEN["_RECORDED_ACTIONS"] == ("skill_cond_mult",), _FROZEN["_RECORDED_ACTIONS"])

    # ---- 逐组断言（一次 run_report，按审计名分组）----
    labels = {
        "dual_sha": "【1】双 sha256：冻结片段文本 + inspect.getsource(活实现)",
        "predicate_bytes": "【2】5 个谓词函数体逐字节 == 冻结旧实现（只换注册到哪）",
        "registry_shape": "【3】注册表语义：引擎条件注册表 · 键集/声明序 · 别名身份 · 未知键",
        "dup_semantics": "【4】注册表语义：同 key 覆盖（后者胜/位置不动）+ 两路注册",
        "key_equivalence": "【5】逐键等价：5 键 × 场景矩阵 旧判定 vs 新判定 逐格",
        "action_matrix": "【6】动作级等价：skill_cond_mult_act 旧 vs 新 + 文案逐字",
        "divergences": "【7】口径分歧断言（4 条故意差异，逐条具名）",
        "single_source": "【8】零知识静态扫描：包内只剩一处条件注册表定义",
    }
    report = {n: [] for n in AUDIT_ORDER}
    for name, msg in run_report(t_reg):
        report[name].append(msg)
    for name in AUDIT_ORDER:
        print(labels[name])
        check("%s 组零违规" % name, not report[name], "；".join(report[name][:4]))

    all_v = [(n, m) for n in AUDIT_ORDER for m in report[n]]
    check("总门禁：8 组审计零违规", not all_v, "；".join(m for _, m in all_v[:6]))

    # ---- 有牙反证（每例都先还原再加下一处坏，保证是「单点坏」；T4 才是双坏）----
    print("\n【9】有牙反证（猴补 3 单坏 + 1 双坏；跑完不写盘还原）")
    src_path = os.path.abspath(CP.__file__)
    with open(src_path, encoding="utf-8") as f:
        disk_before = _sha(f.read())
    snap = _snapshot(t_reg)
    put_orig = Conditions._put
    teeth_ok = True

    def _broken_melody_stacks(battle, actor, target, cond):
        """T1/T4 用：把 `>= need` 偷偷改成 `>= need-1`（只动一格临界判断）。"""
        if not isinstance(actor, dict):
            return False
        st = (actor.get("effects") or {}).get("melody_state") or {}
        need = int(cond.get("stacks", 4) or 4)
        return int(st.get("stacks", 0) or 0) >= (need - 1)

    def _first_wins_put(self, key, fn):
        """T3 用：把「同 key 覆盖」换成「首登记者胜」。"""
        if not callable(fn):
            raise TypeError("判定函数必须可调用")
        if key not in self._fns:
            self._fns[key] = fn

    def _clean():
        return not run_report(t_reg)

    try:
        # --- T1：改一个谓词的临界判断 ---
        t_reg.register("melody_stacks", _broken_melody_stacks)
        v1 = run_report(t_reg)
        hit1 = [m for n, m in v1 if n == "key_equivalence"]
        ok1 = bool(hit1) and any("melody_stacks" in m for m in hit1)
        check("T1 改谓词临界判断 → key_equivalence 变红且点名 melody_stacks", ok1, v1[:2] or "没红")
        teeth_ok &= ok1
        _restore(t_reg, snap)

        # --- T2：让注册表少一个键 ---
        t_reg.pop("melody_buff", None)
        v2 = run_report(t_reg)
        hit2 = [m for n, m in v2 if n == "registry_shape"]
        ok2 = bool(hit2) and any("melody_buff" in m for m in hit2)
        check("T2 注册表少一个键 → registry_shape 变红且点名 melody_buff", ok2, v2[:2] or "没红")
        teeth_ok &= ok2
        _restore(t_reg, snap)

        # --- T3：换掉重复注册语义（首登记者胜）---
        Conditions._put = _first_wins_put
        try:
            v3 = run_report(t_reg)
        finally:
            Conditions._put = put_orig
        hit3 = [m for n, m in v3 if n == "dup_semantics"]
        ok3 = bool(hit3) and any("覆盖" in m for m in hit3)
        check("T3 换掉重复注册语义（首登记者胜）→ dup_semantics 变红且点名覆盖", ok3,
              v3[:2] or "没红")
        teeth_ok &= ok3
        _restore(t_reg, snap)

        # --- T4：两处同时坏（缺键 + 谓词坏）---
        t_reg.pop("melody_buff", None)
        t_reg.register("melody_stacks", _broken_melody_stacks)
        v4 = run_report(t_reg)
        names4 = [n for n, _ in v4]
        ok4a = bool([m for n, m in v4 if n == "registry_shape"]) \
            and bool([m for n, m in v4 if n == "key_equivalence"])
        check("T4 双坏同现 → 缺键与谓词坏**两处**都被点名", ok4a, v4[:3] or "没红")
        teeth_ok &= ok4a
        ok4b = (names4 == sorted(names4, key=AUDIT_ORDER.index)
                and "registry_shape" in names4 and "key_equivalence" in names4
                and names4.index("registry_shape") < names4.index("key_equivalence"))
        check("T4 顺序断言：报告顺序 == AUDIT_ORDER（registry_shape 先于 key_equivalence）",
              ok4b, names4)
        teeth_ok &= ok4b
        _restore(t_reg, snap)

        check("每例跑完即还原 → 复跑全绿（猴补无残留）", _clean(),
              "；".join(m for _, m in run_report(t_reg)[:4]))
    finally:
        Conditions._put = put_orig
        _restore(t_reg, snap)

    with open(src_path, encoding="utf-8") as f:
        disk_after = _sha(f.read())
    check("有牙反证未写盘（cond_procs.py 文件 sha 前后相等）", disk_before == disk_after,
          "%s != %s" % (disk_before, disk_after))
    leftover = run_report(t_reg)
    check("还原后复跑全绿（猴补无残留：键集/注册表/审计都回到干净态）",
          not leftover, "；".join(m for _, m in leftover[:4]))
    check("还原后键集与声明序 == 冻结序", list(t_reg.keys()) == list(PRED_ORDER),
          list(t_reg.keys()))
    if not teeth_ok:
        print("  ⚠️ 有牙反证未全部命中 —— 见上面红行")

    print("\n== 结果：通过 %d / 共 %d ==" % (PASS, PASS + FAIL))
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        return 1
    print("全绿 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
