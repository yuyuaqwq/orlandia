# -*- coding: utf-8 -*-
"""武器域动词（P2 试点 · 表 = `content/rules/mech_seq_weapon.json`）。

动词 = 内容侧对引擎 `acts` 机器提供的**动作原语**；命名按「操作」不按「动作名」，
能被多条机制复用（同名动词对本域所有机制可见）。

本批动词（2 个）
----------------
`ext_ratio_add`       扩展区按比例累加：`owner[area][group][key] += 事件实值 × scale`。
                      **无主 / 实值 ≤ 0 ⇒ 整臂不做**（**连两层容器都不建** —— 旧栈
                      `dmg <= 0` 提前 return 的可观测行为）。无文案（旧收池静默）。
`ext_pool_drain_pct`  扩展池按比例结算：池 > 0 时 `pay = max(1, int(pool × pct))` 直接扣
                      `owner["hp"]`（钳 0、不走 landing：不被盾/减伤二次拦截、不登记击杀）、
                      池回落 `max(0.0, pool - pay)`，再按声明的文案键出一行。
                      **无主 / 宿主已死 / 池 ≤ 0 ⇒ 不结算**（**但两层容器已被建出**）。

缺字段兜底（旧 Python 动作里写死的默认值，按契约 §「缺字段兜底 vs fail-closed」**保留为
动词参数默认值**；声明表只给 `default: null` 的取值链，不改变「缺字段 = 取默认」语义）
----------------------------------------------------------------------------------
`key`   → `"we_death_pool"`（旧 `params.get("pool_key") or "we_death_pool"`）
`scale` → `0.35`（旧 `float(params.get("pool_pct") or 0.35)`）
`pct`   → `0.10`（旧 `float(params.get("pay_pct") or 0.10)`）
`fetch` → `"dmg"`（旧 `ctx.get("dmg", 0)`）
`area` / `group` → `"ext"` / `"we_proc"`（旧动作里写死的两层容器名；改了就丢存档）
⇒ **不许改成「缺字段就报错」**：那是规则变更，不是换实现。

`or` 语义逐字保留：缺键 / `None` / `0` / `""` 一律落到上面那几个默认值（旧写法就是 `or`）。

事件实值怎么取（为什么取数不写在声明里）
----------------------------------------
`fire()` 注入的事件字典挂在**引擎对象属性** `battle._fire_ctx` 上（`Battle` 不是映射），
而 `field` 步链只能走映射 ⇒ 「battle → _fire_ctx → `<fetch>`」这一跳留在动词内，
声明只给 `fetch`（要取事件字典里的哪个键）。

跑法（装配期由 `seq_plans.load_plans()` 导入本模块 ⇒ 注册随 import 发生）：

    from .seq_plans import ACTS

    @ACTS.register("some_op")
    def _some_op(ctx, **kw):
        ...
        return None            # 返回值原样收进该步的结果（可作日志/断言用）
"""
from __future__ import annotations

from ext_combat.battle.actors import actor_alive

from .. import texts as _T                       # 文案表（键由声明给）
from .seq_plans import ACTS                      # 动词往这个表里注册

#: `pool_key` 缺省（= 旧 `we_procs.py:1118` / `:1135` 写死的值，逐字保留）
_DEFAULT_POOL_KEY = "we_death_pool"


def _fire_value(ctx, fetch, default=0):
    """事件字典取值：`battle._fire_ctx[fetch]`。

    `battle` 无 `_fire_ctx` ⇒ 空映射口径（= 旧 `getattr(battle, "_fire_ctx", None) or {}`）。
    """
    fire_ctx = getattr(ctx.get("battle"), "_fire_ctx", None) or {}
    return fire_ctx.get(fetch, default)


@ACTS.register("ext_ratio_add")
def _ext_ratio_add(ctx, owner=None, area="ext", group="we_proc", key=None,
                   fetch="dmg", scale=0.35, **kw):
    """扩展区按比例累加（**实值 ≤ 0 ⇒ 一步都不做**，容器不建）。返回 `None`（无文案）。"""
    owner = owner or ctx.get("caster")
    if owner is None:
        return None
    pool_key = key or _DEFAULT_POOL_KEY
    amount = float(_fire_value(ctx, fetch) or 0)
    if amount <= 0:
        return None                      # 无实伤不收池（护盾全吸收/免疫）
    factor = float(scale or 0.35)
    st = owner.setdefault(area, {}).setdefault(group, {})
    st[pool_key] = float(st.get(pool_key, 0) or 0) + amount * factor
    return None


@ACTS.register("ext_pool_drain_pct")
def _ext_pool_drain_pct(ctx, owner=None, area="ext", group="we_proc", key=None,
                        pct=0.10, log=None, **kw):
    """扩展池按比例结算（扣血 + 池衰减 + 一行文案）。

    * `pay = max(1, int(pool × pct))`：**池再小也扣 1**；`int()` 向零截断
    * 扣血是直接改 `owner["hp"]`（钳 0）—— 不走 landing（旧口径，见契约 §3.5）
    * 池写回 `max(0.0, pool - pay)`（float `0.0`，不是 `-3`）
    * `log` 必给（文案键；缺了就是声明写错了 —— 本动词没有兜底文案）
    * 返回值 `{"pay", "pool"}`（只作步结果/断言用，调用方不消费）
    """
    owner = owner or ctx.get("caster")
    if owner is None or not actor_alive(owner):
        return None
    pool_key = key or _DEFAULT_POOL_KEY
    st = owner.setdefault(area, {}).setdefault(group, {})
    pool = float(st.get(pool_key, 0) or 0)
    if pool <= 0:
        return None                      # 容器已建出（旧 `setdefault` 先于早退）
    pay_pct = float(pct or 0.10)
    pay = max(1, int(pool * pay_pct))
    owner["hp"] = max(0, int(owner.get("hp", 0) or 0) - pay)
    st[pool_key] = max(0.0, pool - pay)
    ctx.get("logs").append(_T.text(log, pay=pay, pool=st[pool_key]))
    return {"pay": pay, "pool": st[pool_key]}
