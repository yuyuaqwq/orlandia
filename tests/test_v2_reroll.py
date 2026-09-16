# -*- coding: utf-8 -*-
"""V2 批：新增指令『重铸 <装备名>』定向测试（判据 1–4 + 保底统计反证 + 现有附魔未动）。

这是**新增测试文件**（可整体撤回：删本文件即回到 272 条）。覆盖：

  【0】表与「金」的认定（`content/data/enchant.json::REROLL` + `_affix_q_label` 档位）
  【1】判据 1 端到端：紫装（有词条槽）→『重铸』→ 词条整体重掷 + 扣材料/金币 + `item_data.reroll.count`
  【2】判据 2 保底：count=3 → 再重铸必含 ≥1 条金；300 条链统计「首次出金轮次」分布
  【3】判据 3 槽满硬报错：词条槽越界 / 无词条槽 → 明确报错 + 材料金币未扣
  【4】判据 4 材料不足 / 金币不足 → 明确报错 + 无任何副作用
  【5】反证：现有『附魔』（确定性配方）产出/消耗/槽满文案**逐字未变**

运行：python tests/test_v2_reroll.py（exit=0 全绿）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import C, db, FakeEvent, run, clean_db, make_player  # noqa: E402
from _engine_harness import Main  # noqa: E402
import content.reroll as R  # noqa: E402
from content.economy_cmds import EconomyImpl  # noqa: E402

passed = failed = 0
G = "v2_g"
Q = "v2_q"
MAT_KEY = "mat_f08_liao_ya"
MAT_NAME = "魔狼獠牙"          # 含『獠牙』→ 命中 ENCHANT_RECIPES.atk 同族材料


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("✅ %s" % name)
    else:
        failed += 1
        print("❌ %s %s" % (name, str(detail)[:260]))


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    out = []
    async for r in getattr(m, handler_name)(ev):
        out.append(str(r))
    return "\n".join(out)


def item_of(gid, qid, key):
    for it in db.get_inventory(gid, qid):
        if it["key"] == key:
            return it["data"]
    return None


def setup(gold=100000, affixes=None, mats=2, lv=5, quality="purple", slot="weapon",
          reroll=None, name="紫霄试炼剑"):
    clean_db()
    make_player(G, Q, "重铸师", "战士", level=10)
    db.update_player(G, Q, gold=gold)
    data = {"name": name, "type": "装备", "slot": slot, "quality": quality, "lv": lv,
            "stats": {"atk": 10}, "affixes": list(affixes or []), "enchant": []}
    if reroll is not None:
        data["reroll"] = reroll
    db.add_item(G, Q, "eq_v2_test", data, 1)
    if mats:
        db.add_item(G, Q, MAT_KEY, {"name": MAT_NAME, "type": "材料"}, mats)
    return Main(None)


def gold_name():
    return C.QUALITY[R.gold_tier()]["name"]


def is_gold(aid):
    return R.is_gold_affix(aid)


# ============================================================ 【0】
def sec0_tables():
    print("【0】REROLL 表（数据表取值）+「金」的认定")
    check("PITY_ROUNDS == 3", R.pity_rounds() == 3, R.pity_rounds())
    check("GOLD_TIER == QUALITY_ORDER 末档 orange", R.gold_tier() == C.QUALITY_ORDER[-1],
          "%s vs %s" % (R.gold_tier(), C.QUALITY_ORDER[-1]))
    check("MATERIAL_COUNT == 1", R.material_count() == 1, R.material_count())
    check("金币阶梯 = 300×2^floor((lv-1)/20)（1/20/40/60/80 分档）",
          [R.gold_cost(x) for x in (1, 19, 20, 39, 40, 59, 60, 79, 80, 120)]
          == [300, 300, 600, 600, 1200, 1200, 2400, 2400, 4800, 4800],
          [R.gold_cost(x) for x in (1, 20, 40, 60, 80, 120)])
    check("词条槽上限 = 既有 AFFIX_COUNT（白0/绿1/蓝2/紫3/橙4）",
          [R.slot_cap(q) for q in ("white", "green", "blue", "purple", "orange", "x")]
          == [0, 1, 2, 3, 4, 0],
          [R.slot_cap(q) for q in ("white", "green", "blue", "purple", "orange", "x")])
    _all_gold = set(R.gold_pool(None))
    _wp = set(R.gold_pool("attack"))
    _ar = set(R.gold_pool("defense"))
    check("金档词条池 = 14 条 / 攻击 2 / 防御 12（qualities 口径，部位分流）",
          len(_all_gold) == 14 and len(_wp) == 2 and len(_ar) == 12
          and _all_gold == (_wp | _ar) and not (_wp & _ar),
          "all=%d atk=%d def=%d %s" % (len(_all_gold), len(_wp), len(_ar), sorted(_wp)))
    _pg = [a for a in C.AFFIX_POOL_BY_QUALITY["purple"] if is_gold(a)]
    check("紫池里有 7 条金（1 攻击 crit_charge / 6 防御）→ 出金不必只靠保底",
          len(_pg) == 7 and [a for a in _pg if C.AFFIXES[a]["kind"] == "attack"] == ["crit_charge"],
          _pg)
    _base_orange = [a for a in C.AFFIX_POOL_BY_QUALITY["purple"]
                    if EconomyImpl._affix_q_label(a) == gold_name()]
    check("对照：若按『基础档==传说』口径，紫池 0 条金（分布会退化成 100% 第 4 轮）",
          _base_orange == [], _base_orange)


# ============================================================ 【1】
async def sec1_e2e():
    print("【1】判据 1 端到端：紫装 →『重铸』→ 词条重掷 + 扣料扣金 + count 落库")
    m = setup(gold=100000, affixes=[])
    before = item_of(G, Q, "eq_v2_test")
    inv_before = {it["key"]: it["count"] for it in db.get_inventory(G, Q)}
    out = await cmd(m, "reroll", G, Q, "重铸 紫霄试炼剑")
    after = item_of(G, Q, "eq_v2_test")
    p = db.get_player(G, Q)
    inv_after = {it["key"]: it["count"] for it in db.get_inventory(G, Q)}
    print("   回复:", out.replace("\n", " ｜ "))
    print("   词条 before=%r after=%r" % (before.get("affixes"), after.get("affixes")))
    print("   金币 %s→%s ｜ 材料 %s→%s ｜ reroll=%r"
          % (100000, p["gold"], inv_before.get(MAT_KEY), inv_after.get(MAT_KEY), after.get("reroll")))
    check("① 词条被重掷：affixes 空 → 非空（count_for(purple)=3）",
          before.get("affixes") == [] and len(after.get("affixes") or []) == 3,
          after.get("affixes"))
    check("① 词条 id 全部 ∈ 紫色随机池（部位过滤后）",
          all(a in C.AFFIX_POOL_BY_QUALITY["purple"] and C.AFFIXES[a]["kind"] == "attack"
              for a in after["affixes"]), after["affixes"])
    check("① 金币按阶梯扣 300", p["gold"] == 100000 - 300, p["gold"])
    check("① 材料扣 1 件（魔狼獠牙 2→1）",
          inv_before.get(MAT_KEY) == 2 and inv_after.get(MAT_KEY) == 1, inv_after.get(MAT_KEY))
    check("① item_data.reroll.count 递增（0 → 0/1，出金才归零）",
          int((after.get("reroll") or {}).get("count", -1)) in (0, 1)
          and int((after.get("reroll") or {}).get("rounds", 0)) == 1,
          after.get("reroll"))
    check("① 回复含『重铸成功』+ 词条清单", "重铸成功" in out and "随机词条整体重掷" in out, out[:120])

    # 再重铸一次：计数必须前进（0→1 或 1→2/0）
    c1 = int((after.get("reroll") or {}).get("count", 0))
    out2 = await cmd(m, "reroll", G, Q, "重铸 紫霄试炼剑")
    after2 = item_of(G, Q, "eq_v2_test")
    c2 = int((after2.get("reroll") or {}).get("count", 0))
    check("① 第二轮可重铸（满 3/3 槽不阻塞整体重掷）且计数前进",
          int((after2.get("reroll") or {}).get("rounds", 0)) == 2 and (c2 == c1 + 1 or c2 == 0),
          "count %s→%s rounds=%s" % (c1, c2, (after2.get("reroll") or {}).get("rounds")))
    check("① 装备个体计数随装备走（写回 item_data，非玩家字段）",
          "reroll" in (after2 or {}) and "count" in after2["reroll"], after2.get("reroll"))


# ============================================================ 【2】
async def sec2_pity():
    print("【2】判据 2 保底：count=3 → 再重铸必出金 + 300 链统计")
    m = setup(gold=100000, affixes=[], reroll={"count": 3, "rounds": 3})
    out = await cmd(m, "reroll", G, Q, "重铸 紫霄试炼剑")
    after = item_of(G, Q, "eq_v2_test")
    _g = [a for a in (after.get("affixes") or []) if is_gold(a)]
    print("   回复:", out.replace("\n", " ｜ "))
    print("   前后词条: count=3 状态 →", after.get("affixes"))
    check("② count=3 再重铸 → 结果必含 ≥1 条金", bool(_g), after.get("affixes"))
    check("② 保底轮计数归零（出金即 count=0）",
          int(after["reroll"]["count"]) == 0, after.get("reroll"))
    check("② 回复点名本轮出金（自然出金或保底强制）",
          "保底触发" in out or "本轮出金" in out, out[:160])

    # ---- count=3 连续 30 次（每次新装备）：次次出金；并观察到「强制保底」路径 ----
    miss, forced_seen = 0, 0
    for _ in range(30):
        _m = setup(gold=100000, affixes=[], reroll={"count": 3, "rounds": 3})
        _out = await cmd(_m, "reroll", G, Q, "重铸 紫霄试炼剑")
        _d = item_of(G, Q, "eq_v2_test")
        if not any(is_gold(a) for a in (_d.get("affixes") or [])):
            miss += 1
        if "保底触发" in _out:
            forced_seen += 1
    print("   count=3 ×30 次：漏金 %d 次 ｜ 走强制保底路径 %d 次" % (miss, forced_seen))
    check("② count=3 连打 30 次 → 30/30 出金（0 漏）", miss == 0, miss)
    check("② 其中观察到「保底触发」强制路径（自然第 4 轮出金也存在，两者都算过）",
          forced_seen > 0, forced_seen)

    # ---- 统计：300 条链，逐轮 roll 直到出金，记录首次出金轮次（紫武器）----
    def chain_stats(quality, slot, kind, n=300):
        hist, forced_at, inf = {}, {}, 0
        for _ in range(n):
            streak, rnd = 0, 0
            while True:
                rnd += 1
                ids, hit, forced, streak = R.roll_reroll(
                    slot, 5, quality, streak, kind=kind)
                if forced:
                    forced_at[rnd] = forced_at.get(rnd, 0) + 1
                if hit:
                    hist[rnd] = hist.get(rnd, 0) + 1
                    break
                if rnd > 50:
                    inf += 1
                    break
        return hist, forced_at, inf

    hist_p, forced_p, inf_p = chain_stats("purple", "weapon", "attack")
    print("   紫武器 首次出金轮次分布（300 链）:", dict(sorted(hist_p.items())))
    print("   紫武器 保底触发轮次分布:", dict(sorted(forced_p.items())))
    check("② 统计（紫）：无链超过第 4 轮、无失控链", max(hist_p) <= 4 and inf_p == 0, hist_p)
    check("② 统计（紫）：第 1–4 轮都有（非「全无 / 100%」异常分布）",
          all(hist_p.get(r, 0) > 0 for r in (1, 2, 3, 4)), hist_p)
    check("② 统计（紫）：保底只在 streak≥3（第 4 轮）触发，不在 1–3 轮",
          bool(forced_p) and min(forced_p) >= 4, forced_p)
    check("② 统计（紫）：前 3 轮未出金的链**全部**在第 4 轮出金（保底保证）",
          hist_p.get(4, 0) == 300 - sum(hist_p.get(r, 0) for r in (1, 2, 3)), hist_p)

    hist_o, forced_o, inf_o = chain_stats("orange", "weapon", "attack")
    print("   橙武器 首次出金轮次分布（300 链）:", dict(sorted(hist_o.items())))
    print("   橙武器 保底触发轮次分布:", dict(sorted(forced_o.items())))
    check("② 统计（橙）：分布跨 1–4 轮且无链超 4", max(hist_o) <= 4 and inf_o == 0, hist_o)
    check("② 统计（橙）：前 3 轮未出金的链全部在第 4 轮出金；保底不是唯一来源（有自然第 4 轮）",
          hist_o.get(4, 0) == 300 - sum(hist_o.get(r, 0) for r in (1, 2, 3))
          and hist_o.get(4, 0) >= forced_o.get(4, 0) and forced_o.get(4, 0) > 0,
          (hist_o.get(4), forced_o.get(4)))

    # ---- 反证：去掉保底（streak 恒 0）→ 必须出现 >4 轮才出金的链 ----
    over4 = 0
    for _ in range(300):
        rnd = 0
        while rnd < 12:
            rnd += 1
            ids, hit, _f, _s = R.roll_reroll("weapon", 5, "purple", 0, kind="attack")
            if hit:
                break
        if rnd > 4:
            over4 += 1
    print("   反证（streak 恒 0 = 关掉保底）: 300 链里 %d 条 >4 轮才出金" % over4)
    check("② 反证：关掉保底后有链 >4 轮才出金（证明保底真的在起作用）", over4 > 0, over4)


# ============================================================ 【3】
async def sec3_slot_full():
    print("【3】判据 3 槽满硬报错：材料/金币未被扣")
    # 3a 词条槽越界（紫装上限 3，塞 4 条）
    m = setup(gold=100000, affixes=["bleed", "combo", "crit_up", "execute"])
    before = item_of(G, Q, "eq_v2_test")
    out = await cmd(m, "reroll", G, Q, "重铸 紫霄试炼剑")
    p = db.get_player(G, Q)
    inv = {it["key"]: it["count"] for it in db.get_inventory(G, Q)}
    after = item_of(G, Q, "eq_v2_test")
    print("   回复:", out)
    print("   金币 100000→%s ｜ 材料 2→%s ｜ reroll=%r" % (p["gold"], inv.get(MAT_KEY), after.get("reroll")))
    check("③ 越界槽满 → 明确报错『词条槽已满(4/3)』", "词条槽已满" in out and "4/3" in out, out[:160])
    check("③ 越界槽满 → 金币未扣", p["gold"] == 100000, p["gold"])
    check("③ 越界槽满 → 材料未扣", inv.get(MAT_KEY) == 2, inv.get(MAT_KEY))
    check("③ 越界槽满 → 词条/计数未动", after.get("affixes") == before.get("affixes")
          and "reroll" not in after, after.get("affixes"))

    # 3b 无词条槽（白装）
    m = setup(gold=100000, affixes=[], quality="white", name="白板木剑")
    out = await cmd(m, "reroll", G, Q, "重铸 白板木剑")
    p = db.get_player(G, Q)
    inv = {it["key"]: it["count"] for it in db.get_inventory(G, Q)}
    print("   回复:", out)
    check("③ 无词条槽 → 明确报错『没有词条槽』", "没有词条槽" in out, out[:160])
    check("③ 无词条槽 → 金币/材料未扣", p["gold"] == 100000 and inv.get(MAT_KEY) == 2,
          (p["gold"], inv.get(MAT_KEY)))

    # 3c 记录：正常 3/3 紫装当前实现允许重铸（作业书「槽满」字面读法与之冲突，见 LANDING）
    m = setup(gold=100000, affixes=["bleed", "combo", "crit_up"])
    out = await cmd(m, "reroll", G, Q, "重铸 紫霄试炼剑")
    print("   记录（3/3 紫装）:", out.replace("\n", " ｜ ")[:120])
    check("③ 记录：3/3 正常紫装可重铸（字面 `>=上限` 读法会让判据 1/2 不可达）",
          "重铸成功" in out, out[:120])


# ============================================================ 【4】
async def sec4_lack():
    print("【4】判据 4 材料不足 / 金币不足 → 明确报错 + 零副作用")
    m = setup(gold=100000, affixes=[], mats=0)
    before = item_of(G, Q, "eq_v2_test")
    out = await cmd(m, "reroll", G, Q, "重铸 紫霄试炼剑")
    p = db.get_player(G, Q)
    after = item_of(G, Q, "eq_v2_test")
    print("   回复:", out)
    check("④ 材料不足 → 明确报错", "没有重铸材料" in out, out[:160])
    check("④ 材料不足 → 金币未扣 / 词条未动 / 无 reroll 记录",
          p["gold"] == 100000 and after.get("affixes") == before.get("affixes")
          and "reroll" not in after, (p["gold"], after.get("affixes"), after.get("reroll")))

    m = setup(gold=100, affixes=[])
    before = item_of(G, Q, "eq_v2_test")
    out = await cmd(m, "reroll", G, Q, "重铸 紫霄试炼剑")
    p = db.get_player(G, Q)
    inv = {it["key"]: it["count"] for it in db.get_inventory(G, Q)}
    after = item_of(G, Q, "eq_v2_test")
    print("   回复:", out)
    check("④ 金币不足 → 明确报错", "重铸需要 300 金币" in out and "100" in out, out[:160])
    check("④ 金币不足 → 材料未扣 / 词条未动 / 无 reroll 记录",
          inv.get(MAT_KEY) == 2 and p["gold"] == 100 and after.get("affixes") == before.get("affixes")
          and "reroll" not in after, (inv.get(MAT_KEY), p["gold"], after.get("affixes")))

    m = setup(gold=100000, affixes=[])
    out = await cmd(m, "reroll", G, Q, "重铸")
    check("④ 缺参 → 用法提示（不消耗）", "重铸哪件装备" in out, out[:120])
    out = await cmd(m, "reroll", G, Q, "重铸 不存在的装备")
    check("④ 找不到装备 → 既有定位器报错", "没有叫" in out, out[:120])


# ============================================================ 【5】
async def sec5_enchant_untouched():
    print("【5】反证：现有『附魔』未被本批碰到（产出/消耗/文案）")
    clean_db()
    make_player(G, Q, "附魔师", "战士", level=10)
    db.update_player(G, Q, gold=100000, cur_map="oak_town", cur_subarea="oak_town_3")
    db.update_player(G, Q, apprentices=["enchant"])
    db.activate_prof(G, Q, "enchant")
    db.add_prof_exp(G, Q, "enchant", 20)          # Lv.2 门槛
    db.add_item(G, Q, "eq_v2_ench", {
        "name": "烈焰之刃", "type": "装备", "slot": "weapon", "quality": "blue", "lv": 5,
        "stats": {"atk": 10}, "affixes": [], "enchant": []})
    db.add_item(G, Q, MAT_KEY, {"name": MAT_NAME, "type": "材料"}, 3)
    m = Main(None)
    out = await cmd(m, "enchant", G, Q, "附魔 烈焰之刃 攻击")
    d = item_of(G, Q, "eq_v2_ench")
    p = db.get_player(G, Q)
    print("   回复:", out.replace("\n", " ｜ "))
    check("⑤『附魔』产出逐字未变：『🔮 附魔成功！…获得 攻击』",
          "🔮 附魔成功！【烈焰之刃】获得 攻击" in out, out[:200])
    _inv = {it["key"]: it["count"] for it in db.get_inventory(G, Q)}
    check("⑤『附魔』消耗逐字未变：材料 x1 + 500 金币（atk cost 表未动）",
          "消耗 魔狼獠牙 x1 + 500 金币" in out and _inv.get(MAT_KEY) == 2,
          (_inv.get(MAT_KEY), out[-90:]))
    check("⑤『附魔』写入 enchant 列表（stat 项），未被重铸字段污染",
          d.get("enchant") == [{"stat": "atk", "value": d["enchant"][0]["value"]}]
          and "reroll" not in d, d.get("enchant"))
    # 槽满文案（蓝装 1 槽）逐字未变
    out2 = await cmd(m, "enchant", G, Q, "附魔 烈焰之刃 防御")
    print("   槽满回复:", out2)
    check("⑤ 现有附魔槽满提示语逐字未变",
          "【烈焰之刃】的 1 个附魔槽已满！先『出售』旧装备，或等新装备吧～" in out2, out2[:200])


async def main():
    sec0_tables()
    await sec1_e2e()
    await sec2_pity()
    await sec3_slot_full()
    await sec4_lack()
    await sec5_enchant_untouched()
    print("\n== 结果：通过 %d / 共 %d ==" % (passed, passed + failed))
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
    print("全绿 ✅")


import asyncio  # noqa: E402

asyncio.run(main())
