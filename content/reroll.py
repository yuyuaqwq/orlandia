# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— **重铸**（V2 批新增，唯一新增指令『重铸 <装备名>』的数值/规则面）。

本文件是 **新增件**：不动 `content/enchant.py`（附魔数值）/ `content/affix.py`（`roll_affixes`
公式）/ 现有『附魔』命令任何一个字。撤回 = 删本文件 + 删 `content/data/enchant.json` 的
`REROLL` 键 + 删 `content/economy_cmds.py::EconomyImpl.reroll` + 删声明表那条。

取值全在数据表（**不在 .py 写死**）
----------------------------------
`content/data/enchant.json` → `enchant` 组 → `REROLL`（读口 = `content/catalog_rules.py::REROLL`）：

    GOLD_TIER         "orange"       最高品质档（`QUALITY_ORDER` 末档 / `QUALITY_TIERS.order[-1]`）
    PITY_ROUNDS       3              连续 N 轮未出金 → 第 N+1 轮保底
    MATERIAL_COUNT    1              每次消耗同族材料件数
    COST_GOLD_LADDER  [{min_lv, gold}, …]   装备等级阶梯（取 min_lv ≤ lv 的最后一档）

三件事
------
1. `gold_cost(lv)`    —— 金币阶梯查表；
2. `slot_cap(quality)`—— 词条槽上限，**直接沿用既有品质词条条数表 `AFFIX_COUNT`**（列表档位取上界）；
3. `roll_reroll(…)`   —— 整体重掷：`roll_affixes`（既有公式，一字不改）+ 引擎计数保底
   `saintess_engine.loot.pity_force/pity_advance`；保底命中项从「金档词条池」抽（`draw_slots`）。

「金」的认定（作业书要求先在 LANDING 点名）
------------------------------------------
金 = **词条可出现的最高品质档 == `REROLL.GOLD_TIER`**（= `QUALITY_ORDER` 末档 `orange`／传说）。

代码证据：`content/data/affixes.json` 每条有 `qualities`（**适用品质档**，schema enum =
blue/purple/orange）；45 条缺该字段 → 由 `AFFIX_POOL_BY_QUALITY` 的**最低**含它的档推基础档
（池是嵌套的 blue ⊂ purple ⊂ orange，与既有 `_affix_q_label` 同一约定）。最高可达档 =
`max(QUALITY_ORDER.index(t))`；等于末档即「金」。实测：全表 14 条金（紫池 7 / 橙池 14）。

为什么用「最高可达档」而不是「基础档」：基础档口径下**紫装/蓝装的随机池里一条金都没有**
（qualities[0]==orange 的 7 条全在橙池），出金就只能靠保底 → 出金轮次分布退化成
「100% 落在第 4 轮」（实测 300/300）。「最高可达档」口径下紫武器池有 1 条金（`crit_charge`）、
橙武器池 2 条 → 第 1–3 轮有自然出金、第 4 轮是保底兜底，统计分布健康（见 LANDING §红榜）。

引擎零游戏知识（铁律 5）：保底「连续 N 次未中 → 下一次强制命中」是通用能力 → 进引擎
`saintess_engine/loot/pity.py`；**N 与「什么是金」留在包内**（本文件 + 数据表）。
"""
from __future__ import annotations

import random

from saintess_engine.loot import draw_slots, pity_advance, pity_force

from .affix import AFFIXES, roll_affixes
from .catalog_b143 import AFFIX_POOL_BY_QUALITY, QUALITY_ORDER
from .catalog_rules import AFFIX_COUNT, REROLL


def gold_tier() -> str:
    """「金」的档位 key（默认 `orange` = `QUALITY_ORDER` 末档）。"""
    return str((REROLL or {}).get("GOLD_TIER") or "orange")


def pity_rounds() -> int:
    """保底阈值：连续 N 轮未出金 → 第 N+1 轮保底。"""
    return int((REROLL or {}).get("PITY_ROUNDS") or 0)


def material_count() -> int:
    """每次重铸的材料件数。"""
    return int((REROLL or {}).get("MATERIAL_COUNT") or 0)


def gold_ladder() -> list:
    """金币阶梯（合法行：`{min_lv, gold}`）。"""
    rows = (REROLL or {}).get("COST_GOLD_LADDER") or []
    return [r for r in rows
            if isinstance(r, dict) and "min_lv" in r and "gold" in r]


def gold_cost(lv: int) -> int:
    """装备等级 → 重铸金币：阶梯表里 `min_lv <= lv` 的**最后一档**（表按 min_lv 升序）。"""
    out = 0
    for row in sorted(gold_ladder(), key=lambda r: int(r["min_lv"])):
        if int(lv or 1) >= int(row["min_lv"]):
            out = int(row["gold"])
    return out


def slot_cap(quality: str) -> int:
    """该品质的词条槽上限 —— **沿用既有 `AFFIX_COUNT`**（orange 是区间 → 取上界；未知档 0）。"""
    cfg = (AFFIX_COUNT or {}).get(quality, 0)
    if isinstance(cfg, (list, tuple)):
        return int(max(cfg)) if cfg else 0
    try:
        return int(cfg)
    except (TypeError, ValueError):
        return 0


def affix_tiers(aid: str) -> set:
    """词条**可出现的品质档集合**：显式 `qualities` 优先；缺该字段 → 由随机池归属取
    **最低**含它的档（池嵌套 blue ⊂ purple ⊂ orange ⇒ 最低档 = 该词条的基础档，
    与既有 `content/economy_cmds.py::EconomyImpl._affix_q_label` 同一约定）。查不到 → 空集。
    """
    qs = (AFFIXES.get(aid) or {}).get("qualities")
    if qs:
        return {str(q) for q in qs}
    for tier in ("blue", "purple", "orange"):
        if aid in AFFIX_POOL_BY_QUALITY.get(tier, []):
            return {tier}
    return set()


def is_gold_affix(aid: str) -> bool:
    """「金」= 该词条可出现的**最高档** == `REROLL.GOLD_TIER`（= `QUALITY_ORDER` 末档）。"""
    tiers = affix_tiers(aid)
    order = list(QUALITY_ORDER or ())
    want = gold_tier()
    if not tiers or want not in order:
        return False
    idx = [order.index(t) for t in tiers if t in order]
    return bool(idx) and max(idx) == order.index(want)

def mark_bound(d: dict) -> None:
    """保底触发 → 给该装备个体打**绑定**标记（台账 §0 D4：保底产物不可交易 / 不可出售）。

    落点 = `item_data.reroll.bound`（与轮次计数同一份记录 —— 随装备走，换人不丢；
    装备在背包 / 已装备两个位置写的是同一个 `data` 对象，命令层两条写回路径都带上它）。
    """
    if not isinstance(d, dict):
        return
    rec = d.get("reroll")
    if not isinstance(rec, dict):
        rec = {}
    rec["bound"] = True
    d["reroll"] = rec


def is_bound(d: dict) -> bool:
    """该装备是否**绑定**（= 吃过保底的重铸产物）—— 出售 / 上架 / 摆卖三条出口共用本读口。

    非映射 / 无记录 / 记录坏形状 → `False`（未绑定），不抛（出口守卫是热路径）。
    """
    rec = d.get("reroll") if isinstance(d, dict) else None
    return bool(isinstance(rec, dict) and rec.get("bound"))


def gold_pool(kind, is_gold=None) -> list:
    """金档词条池（按 `kind` = `attack`/`defense` 过滤）。

    池源 = `AFFIX_POOL_BY_QUALITY[GOLD_TIER]`（最高档随机池），再按 `is_gold`
    （默认 = 本模块 `is_gold_affix`）筛「金」—— 保底那一项因此**仍在该装备品质的池子里**
    （不跨品质硬塞）。
    """
    is_gold = is_gold or is_gold_affix
    out, seen = [], set()
    for aid in AFFIX_POOL_BY_QUALITY.get(gold_tier(), []):
        if aid in seen or not is_gold(aid):
            continue
        if kind and (AFFIXES.get(aid) or {}).get("kind") != kind:
            continue
        seen.add(aid)
        out.append(aid)
    return out


def roll_reroll(slot, lv, quality, streak, *, is_gold=None, kind=None):
    """整体重掷该装备的全部随机词条。

    返回 `(新词条 id 列表, 本轮是否出金, 是否保底强制, 新 streak)`：

    * 条数/池子 = 既有 `roll_affixes(slot, lv, quality)`（`count_for(AFFIX_COUNT, quality,
      extra_chance=0.20, rng=random)` + `draw_slots`）—— **不新增公式**；
    * 连续 `streak` 轮未出金且 `pity_force(streak, PITY_ROUNDS)` → **保底轮**：把新集合的
      第 1 条换成该品质池里的金档词条（**等量替换**，总条数不变）；集合为空时补 1 条
      （理论上不可达：无词条槽的品质在命令层已被拒）。
    * `streak` 推进 = `pity_advance(streak, 出金)`（出金归零）。
    """
    is_gold = is_gold or is_gold_affix
    ids = list(roll_affixes(slot, lv, quality))
    hit = any(is_gold(a) for a in ids)
    forced = False
    if not hit and pity_force(streak, pity_rounds()):
        pool = [a for a in gold_pool(kind, is_gold) if a not in ids]
        if pool:
            chosen = draw_slots(pool, 1, rng=random)[0]
            if ids:
                ids[0] = chosen
            else:
                ids.append(chosen)
            hit = True
            forced = True
    return ids, hit, forced, pity_advance(streak, hit)
