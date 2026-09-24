# -*- coding: utf-8 -*-
"""职业/被动域动词（P2 试点 · 表 = `content/rules/mech_seq_class.json`）。

动词 = 内容侧对引擎 `acts` 机器提供的**动作原语**；命名按「操作」不按「动作名」，
能被多条机制复用（同名动词对本域所有机制可见）。

总线协议（步骤之间怎么传值）
----------------------------
`seq_plans.run()` **每次调用新建** ctx（`ctx_of`），而 `acts.Plan.run` 把同一个 ctx
交给每一步 ⇒ 本域用 ctx 的私有槽 `"_w"`（dict）当**步骤间传值总线**：

    `into` / `*_into`      = **写**哪个槽
    `of` / `*_of`          = **读**哪个槽（`of` 不带后缀 = 主宿主槽）
    其余实参                = **值**（声明节点现取，如 `{"field":[{"key":"params"},{"key":"key","default":null}]}`）

槽只活在本次调用内：不落盘、不进 `battle._fire_ctx`、不跨动作泄漏。
缺槽读 = `KeyError`（内部交接出错要当场看见，不给静默兜底）。

两条口径（与旧实现逐字对齐，别"顺手优化"）
--------------------------------------------
* 声明取 `params` 一律带 `"default": null` —— `field` 步**不给 default 就是下标**
  （缺键抛 `KeyError`），而旧实现是 `params.get(k)`（缺键给 None）。这不是风格，是行为。
* 动词按「原实现里的那一步操作」切：读一次值 / 判一道闸 / 写一处状态 / 出一条文案。
  多道闸用 `stop_if`（引擎口径：`when` 为假 ⇒ 不执行、返回空列表，与旧实现的
  `if …: return` 同义）。**动词只做那一步**，不提前算、不推迟算（异常发生的先后也是行为）。

跑法（装配期由 `seq_plans.load_plans()` 导入本模块 ⇒ 注册随 import 发生）：

    from .seq_plans import ACTS

    @ACTS.register("some_op")
    def _some_op(ctx, **kw):
        ...
        return None            # 返回值原样收进该步的结果（可作日志/断言用）
"""
from __future__ import annotations

# 复用本族既有助手（**单源**，不在动词里重写第二份叠层/宿主口径）
from .class_mech import _holder, _key_list, _stacks_float
from .seq_plans import ACTS      # noqa: F401  动词往这个表里注册
from .. import texts as _T

#: 步骤间传值槽（本次调用的工作区；`run()` 每次调用新建 ctx ⇒ 无跨调用残留）
BUS = "_w"


def _slot(ctx: dict) -> dict:
    """取本次调用的传值槽（首次访问即建出）。"""
    return ctx.setdefault(BUS, {})


# ============================================================
# 环境取值（谁读 battle 私有槽，都从这里走）
# ============================================================

@ACTS.register("read_fire_ctx")
def _read_fire_ctx(ctx, into="fire", empty=False, **_):
    """读 `battle._fire_ctx` 进槽：逐字 `getattr(battle, "_fire_ctx", None)`。

    `empty=True` ⇒ 顺带 `or {}` 兜底（对应旧实现里 `… or {}` 那两处写法）。
    **不复制**该 dict —— 乘区钩子要原地改同一个对象（调用方读同一份）。
    """
    fire = getattr(ctx.get("battle"), "_fire_ctx", None)
    if empty:
        fire = fire or {}
    _slot(ctx)[into] = fire
    return fire


@ACTS.register("guard_mech_match")
def _guard_mech_match(ctx, of="fire", mech=None, into="ok", **_):
    """闸：fire ctx 的 `info.mech` == 声明 `mech`（`info` 缺键 → `{}`）。

    语义源 = `mech_cash_dmg_mult` 的 `ctx is None → return` +
    `info.get("mech") != params.get("mech") → return`（fire ctx 是 None ⇒ 不匹配）。
    """
    fire = _slot(ctx).get(of)
    ok = fire is not None and (fire.get("info") or {}).get("mech") == mech
    _slot(ctx)[into] = ok
    return ok


@ACTS.register("pick_effect_host")
def _pick_effect_host(ctx, of="fire", owner=None, into="host", **_):
    """owner 方向选宿主（`_holder` 口径）：`owner=="target"` → fire ctx 的 target 优先。"""
    host = _holder(owner, _slot(ctx).get(of), ctx.get("caster"), ctx.get("target"))
    _slot(ctx)[into] = host
    return host


@ACTS.register("sum_stacks_float")
def _sum_stacks_float(ctx, of="host", key=None, into="n", **_):
    """叠层求和（float 保真、多印记 key 各 `stacks` 相加）—— `_stacks_float` 逐字。

    宿主非 dict（如 None）⇒ `AttributeError` 上抛（与旧实现同一个异常类型）。
    """
    host = _slot(ctx).get(of)
    n = _stacks_float(host.get("effects"), key)
    _slot(ctx)[into] = n
    return n


@ACTS.register("fallback_join_keys")
def _fallback_join_keys(ctx, first=None, key=None, into="keys", **_):
    """层标签回落：`first or "、".join(_key_list(key))` —— **短路保持**（`first` 真值时不碰 key）。"""
    v = first or "、".join(_key_list(key))
    _slot(ctx)[into] = v
    return v


@ACTS.register("norm_slot")
def _norm_slot(ctx, of, into, **_):
    """槽值归一（`norm_stack`：整值落 int、小数留 6 位）后写进另一槽（日志槽位口径）。"""
    from ext_combat.battle.effects import norm_stack
    bus = _slot(ctx)
    bus[into] = norm_stack(bus[of])
    return bus[into]


# ============================================================
# 乘区 / 状态写入
# ============================================================

@ACTS.register("mul_channel_field")
def _mul_channel_field(ctx, of="fire", field="mult", per_layer=None, count_of="n",
                       into=None, **_):
    """乘区通道原地累乘：`槽of[field] = float(槽of.get(field, 1.0) or 1.0) × (1 + per × n)`。

    `n` = `count_of` 槽（float 保真）；`per` = `per_layer` 值（缺 → 0），被 fire ctx 的
    `info.per_stack` **覆盖**（`or` 语义：0/None 都算缺）。乘积因子写回 `into` 槽（日志用）。
    """
    bus = _slot(ctx)
    fire = bus[of]
    n = bus[count_of]
    per = float(per_layer or 0)
    per = float((fire.get("info") or {}).get("per_stack") or per)
    mult = 1.0 + per * n
    fire[field] = float(fire.get(field, 1.0) or 1.0) * mult
    if into:
        bus[into] = mult
    return mult


@ACTS.register("guard_actor_alive")
def _guard_actor_alive(ctx, owner=None, into="ok", owner_into=None, **_):
    """宿主存活闸：`None` 或已死 → 不通过（`actor_alive` = 引擎口径）。"""
    from ext_combat.battle.actors import actor_alive
    ok = not (owner is None or not actor_alive(owner))
    bus = _slot(ctx)
    bus[into] = ok
    if owner_into:
        bus[owner_into] = owner
    return ok


@ACTS.register("read_positive_params")
def _read_positive_params(ctx, keys=None, numbers=None, into="ok", **_):
    """标量参数闸：文本键非空 + 数值键 `float(x or 0)` > 0 才通过；读数写进**同名槽**。

    语义源 = `passive_low_hp_core` 的
    `res/used_key = params.get(k) or ""` + `hp_lt/cores = float(params.get(k) or 0)`
    + `if not res or not used_key or hp_lt <= 0 or cores <= 0: return`。
    数值 `float()` 非数值 ⇒ `ValueError` 上抛（不被吞），且**先于**那行 `if` 判空（同旧序）。
    """
    bus = _slot(ctx)
    ok = True
    for name, val in (keys or {}).items():
        bus[name] = val
        ok = ok and bool(val)
    num_items = list((numbers or {}).items())
    vals = [float(v or 0) for _, v in num_items]     # 归一顺序 = 声明序（hp_lt 先于 cores）
    for (name, _), v in zip(num_items, vals):
        bus[name] = v
    # 与旧实现同式：`… or hp_lt <= 0 or cores <= 0`（**不写成 `all(v > 0)`** ——
    # 对 NaN 两者不等价：`nan <= 0` 为假 ⇒ 旧实现放行）
    ok = ok and not any(v <= 0 for v in vals)
    bus[into] = ok
    return ok


@ACTS.register("guard_flag_unset")
def _guard_flag_unset(ctx, owner_of="owner", key_of="used_key", into="ok", **_):
    """一次性闸门：`effects[key]` 已是 dict → 不通过（每场 1 次的那种旗）。

    **此处会 `setdefault("effects", {})`** —— 与旧实现同序、同副作用（容器被建出是可观测的）。
    """
    bus = _slot(ctx)
    ef = bus[owner_of].setdefault("effects", {})
    ok = not isinstance(ef.get(bus[key_of]), dict)
    bus[into] = ok
    return ok


@ACTS.register("guard_hp_below")
def _guard_hp_below(ctx, owner_of="owner", lt_of="hp_lt", into="ok", **_):
    """低血阈值闸（**严格 <**）：`int(hp) >= int(max_hp × lt)` 即不通过。

    取整口径逐字：阈值先 `int()` 截断（3000×0.3=900.0 → 900 ⇒ hp=900 不触发、899 触发）；
    `max_hp` 缺/为 0 → `int(1)`（`owner.get("max_hp", 1) or 1`）。
    """
    bus = _slot(ctx)
    owner = bus[owner_of]
    mhp = int(owner.get("max_hp", 1) or 1)
    ok = int(owner.get("hp", 0) or 0) < int(mhp * bus[lt_of])
    bus[into] = ok
    return ok


@ACTS.register("add_stacks_clamped")
def _add_stacks_clamped(ctx, owner_of="owner", res_of="res", amount_of="cores",
                       into="n", norm_into=None, cap_into=None, **_):
    """加层 + cap 钳制：`max(0, min(cap_of(res), cur + amount))` → `norm_stack` 写回。

    顺序逐字：`cap_of` → 读 `cur`（条目非 dict 视 0）→ clamp → **条目不存在时新建 dict**
    → 写 `stacks`。cap 走引擎 `cap_of`（无声明 → 999999，**不许写死**）。
    """
    from ext_combat.battle.effects import cap_of, norm_stack
    bus = _slot(ctx)
    owner = bus[owner_of]
    res = bus[res_of]
    cap = cap_of(owner, res)
    ef = owner.setdefault("effects", {})
    entry = ef.get(res)
    cur = float(entry.get("stacks", 0) or 0) if isinstance(entry, dict) else 0.0
    n = max(0.0, min(float(cap), cur + bus[amount_of]))
    if not isinstance(entry, dict):
        entry = ef[res] = {}
    entry["stacks"] = norm_stack(n)
    bus[into] = n
    if norm_into:
        bus[norm_into] = norm_stack(n)
    if cap_into:
        bus[cap_into] = cap
    return n


@ACTS.register("set_flag_once")
def _set_flag_once(ctx, owner_of="owner", key_of="used_key", **_):
    """置一次性旗：`effects[key] = {"stacks": 1, "expire": None}`（形状即闸门口径）。"""
    bus = _slot(ctx)
    bus[owner_of].setdefault("effects", {})[bus[key_of]] = {"stacks": 1, "expire": None}
    return None


# ============================================================
# 呈现
# ============================================================

@ACTS.register("say")
def _say(ctx, slot, args=None, **_):
    """文案槽位 → 文案（**现取** ⇒ 热更生效）：`logs.append(_T.text(slot, **args))`。"""
    ctx["logs"].append(_T.text(slot, **(args or {})))
    return None


# ============================================================
# 敌身条窗口（挂敌身条族的可复用原语）
# ============================================================

@ACTS.register("read_bar_window")
def _read_bar_window(ctx, of="fire", bar="", ext=0, into="win", ok_into="ok",
                     ext_into=None, **_):
    """取宿主条状态并过四道门槛；过了才把条状态写进 `into` 槽。

    门槛顺序逐字：`bar`/`ext` 合法 → 宿主是 dict → 条状态是 dict → `trigger_count > 0`
    → `immune_until > _now`（**`<=` 算过期**）。
    宿主角 = fire ctx 的 `target` 优先，非 dict 回落位置参数 target。
    `ext` 的 `float()` 非数值 → `0.0`（旧实现 try/except 兜底），归一值写 `ext_into` 槽。
    """
    fire = _slot(ctx).get(of) or {}
    host = fire.get("target")
    if not isinstance(host, dict):
        host = ctx.get("target")
    try:
        ext = float(ext or 0)
    except Exception:                                    # noqa: BLE001  旧实现同款兜底
        ext = 0.0
    bus = _slot(ctx)
    bus[ok_into] = False
    if ext_into:
        bus[ext_into] = ext
    if not bar or ext <= 0 or not isinstance(host, dict):
        return None
    from ext_combat.gauge import bar_effect_key
    bs = (host.get("effects") or {}).get(bar_effect_key(bar))
    if not isinstance(bs, dict):
        return None
    if int(bs.get("trigger_count", 0) or 0) <= 0:
        return None
    _now = float(getattr(ctx.get("battle"), "_now", 0.0) or 0.0)
    if float(bs.get("immune_until", 0.0) or 0.0) <= _now:
        return None
    bus[into] = bs
    bus[ok_into] = True
    return bs


@ACTS.register("extend_bar_window")
def _extend_bar_window(ctx, of="win", ext_of="ext", int_into=None, **_):
    """免疫窗口 +ext 刻：**float 累加**（`+1.5` 保持 `13.5`）；只改 `immune_until`。

    日志槽位要的 `int(ext)`（截断）**在此刻**算 —— 与旧实现「先写窗口、后取 int」同序
    （`int()` 对异常值会抛，先后顺序是可观测的）。
    """
    bus = _slot(ctx)
    bs = bus[of]
    ext = bus[ext_of]
    bs["immune_until"] = float(bs.get("immune_until", 0.0) or 0.0) + ext
    if int_into:
        bus[int_into] = int(ext)
    return bs["immune_until"]
