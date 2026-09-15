# -*- coding: utf-8 -*-
"""economy_lib.core —— 经济模型核心计算（分阶段 × 多维度）

维度（每阶段一行 economy_row）：
  产出侧：怪金曲线 → 掉落价值 → 卖店回收 → 任务金币
  装备成本侧：蓝装推导价 / 强化期望 / 升级成本 / 锻造成本
  生活成本：住宿
  材料供需：掉落单种数量（供给）vs 配方需求（消耗）
  比率：蓝装≈几只怪 / 锻造成本占产物比 / 掉落数量

数据源全部实读 game/data + game/core，禁止硬编码魔法数（与 numeric_lib 同原则）。
"""
import statistics
import random
from .env import setup_env  # noqa
from .constants import (
    ECON_STAGES, DROP_VALUE_MULT, MATERIAL_SELL_RATE, MAIN_QUEST_GOLD_MULT,
    CRAFT_COST_RATIO_MIN, CRAFT_COST_RATIO_MAX,
    SHOP_HEALTH_BANDS, SHOP_LOW_TRIGGER, SHOP_HIGH_TRIGGER,
    SHOP_EXEMPT_KEYS,
)
# ★ P5E-DELETE（2026-09-15，删壳批）：取件口从待删宿主壳改到**包内真源**。
#   原三行 = `import game.content as D` / `from game.core import stats as S` /
#   `from game.core.drops import generate_roster_equip`（`game/**` 已整树删除，
#   全删态实测本文件 import 即 `ModuleNotFoundError: No module named 'game.content'`
#   ⇒ 数值门禁 4 个文件连坐红）。包内对应真源（对象同一，逐名可查）：
#     · D = `content.facade.C`（宿主聚合门面的包内等价物；`D.MAPS` / `D.SHOP_EQUIP` /
#       `D.EQUIP_ROSTER` / `D.MATERIALS` / `D.ITEMS` 与旧门面同源同值）
#     · S = `content.stats`（`game.core.stats` 的真源模块）
#     · generate_roster_equip = `content.drops`（`game.core.drops` 的真源模块）
#   数值口径、公式与断言**一条未变**（门禁只比数）。
from content.facade import C as D  # noqa: E402
from content import stats as S  # noqa: E402
from content.drops import generate_roster_equip  # noqa: E402

random.seed(20260902)


# ---------------- 副本通关奖励（v173 问题C，2026-09-03 鱼鱼拍板最小可用模型） ----------------
# 此前 22 本 gold/exp 手填无模型 → 通关金=同级野外 Boss 怪金 14-39%、exp=升级所需 5-10%，
# 全仓唯一无模型的产出维度。现按 32 章怪金/怪经模型锚定：
#   gold = monster_gold(inst_lv, 'boss') × INSTANCE_GOLD_MULT    （≈ 1/3 只同级野外 Boss 怪金）
#   exp  = monster_exp(inst_lv, 'boss')  × INSTANCE_EXP_MULT     （≈ 升级所需 4-24%，随成长曲线回落）
# 消费端：instance.py _instance_victory 逐字读 inst['gold']/inst['exp']（data 标定值），
# 战利品堆（30%）/ 隐藏暗格等子奖励自动跟随。数值门禁 tests/test_numeric_instance_reward.py。
INSTANCE_GOLD_MULT = 0.30
INSTANCE_EXP_MULT = 2.8


def instance_reward(lv: int) -> dict:
    """副本通关奖励模型：lv = 副本 inst.lv（≈同图小怪等级）。

    返回 {'gold': int, 'exp': int}——data/instances.py 各本 gold/exp 的标定源。
    """
    return {
        "gold": int(S.monster_gold(lv, "boss") * INSTANCE_GOLD_MULT),
        "exp": int(S.monster_exp(lv, "boss") * INSTANCE_EXP_MULT),
    }


# ---------------- 产出侧 ----------------
def per_kill_gold(lv: int, role: str = "dps") -> int:
    """单只普通怪金币（dps 口径，role 合法取 role）。"""
    if role not in S.MONSTER_GOLD_BASE:
        role = "dps"
    return S.monster_gold(lv, role)


def drop_value(lv: int) -> int:
    """掉落价值 = 怪金 × 1.5（v93 折算成材料）。"""
    return int(per_kill_gold(lv) * DROP_VALUE_MULT)


def income_per_10_kills(lv: int) -> int:
    """打 10 只普通怪 → 材料卖店回收（材料回收 0.9）。"""
    return int(drop_value(lv) * MATERIAL_SELL_RATE * 10)


# ---------------- 装备成本侧 ----------------
def _roster_prices(quality: str, lv: int, tolerance: int = 2) -> list:
    """名册中该品质 & 等级接近装备的推导价列表（确定性生成）。"""
    out = []
    for rid, r in D.EQUIP_ROSTER.items():
        if r.get("quality") == quality and abs(r.get("lv", 0) - lv) <= tolerance:
            try:
                out.append(generate_roster_equip(rid)["price"])
            except Exception:
                continue
    return out


def equip_price(lv: int, quality: str = "blue") -> int | None:
    """该等级蓝装（或指定品质）推导价中位。"""
    ps = _roster_prices(quality, lv)
    if not ps:
        # 放宽容差
        ps = _roster_prices(quality, lv, tolerance=5)
    return int(statistics.median(ps)) if ps else None


def enhance_expected_cost(target: int = 9) -> int:
    """强化到 target 的期望金币成本（成功率的倒数×cost 累加）。"""
    # 实读 ENHANCE_TABLE
    table = dict(D.ENHANCE_TABLE)
    total = 0
    for lv in range(1, target + 1):
        entry = table.get(lv, {})
        cost = entry.get("cost", 0)
        rate = entry.get("rate", 1.0)
        total += int(cost / max(rate, 0.01))
    return total


def upgrade_full_cost() -> int:
    """升级 0→10 总金币成本（UPGRADE_TABLE，v172 真等级化 cost 阶梯保留）。"""
    try:
        table = D.UPGRADE_TABLE
        # v172：真等级化后 upgrade_lv 从 0 起每次 +1，cost 取目标级阶梯
        # （旧实现把 0 级 cost 200 也算进 0→10，实为 0→1 的档位费）
        return sum(int(r.get("cost", 0)) for r in table.values() if isinstance(table, dict)) - int(table.get(0, {}).get("cost", 0))
    except Exception:
        return 0


def craft_cost(lv: int, quality: str = "blue") -> int | None:
    """本阶段一件蓝装锻造的材料+金币成本中位。"""
    costs = []
    for rid, rec in D.CRAFT_RECIPES.items():
        if rec.get("quality") != quality:
            continue
        if abs(rec.get("lv", 0) - lv) > 3:
            continue
        mats = rec.get("mats", {})
        if not mats:
            continue
        mc = sum(D.MATERIALS.get(m, {}).get("price", 0) * q for m, q in mats.items())
        costs.append(mc + rec.get("gold", 0))
    return int(statistics.median(costs)) if costs else None


def craft_cost_ratio(lv: int, quality: str = "blue") -> float | None:
    """锻造材料+金币成本 / 产物价 中位比率。"""
    prod = equip_price(lv, quality)
    cc = craft_cost(lv, quality)
    if not prod or not cc:
        return None
    return cc / prod


# ---------------- 生活成本 ----------------
def inn_cost(lv: int) -> int:
    """住宿费（econ_config 公式）。"""
    cfg = D.ECON_CONFIG
    if lv <= cfg.get("inn_cost_lv_cap", 15):
        return max(cfg.get("inn_cost_min_low", 30), lv * cfg.get("inn_cost_per_lv", 5))
    # Lv16+：向下取整到百
    raw = max(cfg.get("inn_cost_min_high", 100), lv * cfg.get("inn_cost_per_lv", 5) * cfg.get("inn_cost_high_mult", 2.0))
    return int(raw // 100 * 100)


# ---------------- 材料供需 ----------------
def _mat_sources() -> dict:
    """材料名 → 产出它的怪等级列表（从 MAPS 掉落池）。"""
    mat_src = {}
    mat_names = {v.get("name", k): k for k, v in D.MATERIALS.items()}
    for m in D.MAPS:
        for sub in m.get("subareas", []):
            for mon in sub.get("monsters", []):
                if len(mon) < 6:
                    continue
                for d in mon[5]:
                    if isinstance(d, str) and d in mat_names:
                        mat_src.setdefault(d, []).append(mon[3])
    return mat_src


def drop_count_sim(lv: int, role: str = "dps") -> dict:
    """单只怪材料掉落数量仿真（按 combat._handle_victory 同公式）。

    返回 {avg_count, max_count, per_mat: {材料名: 数量}}（取该等级附近怪配置均值）
    """
    mat_src = _mat_sources()
    mat_price = {v.get("name", k): v.get("price", 0) for k, v in D.MATERIALS.items()}
    rows = []
    for m in D.MAPS:
        for sub in m.get("subareas", []):
            for mon in sub.get("monsters", []):
                if len(mon) < 6:
                    continue
                if mon[2] != role or abs(mon[3] - lv) > 3:
                    continue
                drops = [d for d in mon[5] if isinstance(d, str) and d in mat_price]
                if not drops:
                    continue
                g = S.monster_gold(mon[3], role if role in S.MONSTER_GOLD_BASE else "dps")
                mv = int(g * 1.5)
                picks_n = 2 if role in ("elite", "boss") else 1
                per = mv / min(picks_n, len(drops))
                for d in drops:
                    p = mat_price[d]
                    if p <= 0:
                        continue
                    n = max(1, min(99, int(per / len(drops) / p)))
                    rows.append((n, d, p, mon[3], mon[1]))
    if not rows:
        return {"avg_count": None, "max_count": None, "samples": [], "role": role, "lv": lv}
    counts = [r[0] for r in rows]
    return {
        "avg_count": round(statistics.mean(counts), 1),
        "max_count": max(counts),
        "over_cap": sum(1 for c in counts if c > 4),
        "samples": sorted(rows, key=lambda x: -x[0])[:5],
        "role": role, "lv": lv,
    }


# ---------------- 主行 ----------------
def economy_row(stage_id: str, sample_lv: int) -> dict:
    """单阶段经济账本行。"""
    g = per_kill_gold(sample_lv)
    dv = drop_value(sample_lv)
    inc10 = income_per_10_kills(sample_lv)
    blue_p = equip_price(sample_lv, "blue")
    enh9 = enhance_expected_cost(9)
    upg = upgrade_full_cost()
    craft_c = craft_cost(sample_lv, "blue")
    craft_r = craft_cost_ratio(sample_lv, "blue")
    inn = inn_cost(sample_lv)
    dc = drop_count_sim(sample_lv, "dps")
    return {
        "stage": stage_id, "lv": sample_lv,
        "per_kill_gold": g, "drop_value": dv, "income_10_kills": inc10,
        "blue_price": blue_p,
        "blue_kills": round(blue_p / max(inc10 / 10, 1), 1) if blue_p else None,
        "enhance9_cost": enh9,
        "enhance9_blue_ratio": round(enh9 / blue_p, 2) if blue_p else None,
        "upgrade_full_cost": upg,
        "craft_cost": craft_c,
        "craft_cost_ratio": round(craft_r, 2) if craft_r else None,
        "inn_cost": inn,
        "drop_avg_count": dc["avg_count"],
        "drop_max_count": dc["max_count"],
        "drop_over_cap": dc.get("over_cap", 0),
        "drop_samples": dc.get("samples", []),
    }


def economy_scan() -> dict:
    """全阶段经济扫描。"""
    rows = [economy_row(sid, sample_lv) for sid, _, _, sample_lv, _ in ECON_STAGES]
    return {"stages": rows}


def check_health(row: dict) -> list:
    """对单行输出健康带违规清单。"""
    issues = []
    if row["blue_price"]:
        bk = row["blue_kills"]
        if bk is not None:
            if bk < 8:
                issues.append(f"蓝装≈{bk}只怪 < 8（太便宜）")
            elif bk > 20:
                issues.append(f"蓝装≈{bk}只怪 > 20（太贵）")
        er = row["enhance9_blue_ratio"]
        if er is not None and er > 3.0:
            issues.append(f"强化+9={er:.1f}×蓝装 > 3×")
    cr = row["craft_cost_ratio"]
    if cr is not None:
        if cr < CRAFT_COST_RATIO_MIN:
            issues.append(f"锻造成本占产物 {cr*100:.0f}% < 40%（材料无成本）")
        elif cr > CRAFT_COST_RATIO_MAX:
            issues.append(f"锻造成本占产物 {cr*100:.0f}% > 70%（亏本）")
    if row["drop_avg_count"] is not None and row["drop_avg_count"] > 4:
        issues.append(f"平均掉 {row['drop_avg_count']} 个/材料 > 4（数量膨胀）")
    if row["drop_max_count"] is not None and row["drop_max_count"] > 6:
        issues.append(f"最大掉 {row['drop_max_count']} 个（爆量）")
    return issues


# ---------------- 副业维度（炼金/烹饪 成本-价值检查） ----------------
def _key_price(k):
    """材料/物品 key → 现价"""
    if k in D.MATERIALS:
        return D.MATERIALS[k].get("price", 0)
    if k in D.ITEMS:
        return D.ITEMS[k].get("price", 0)
    return 0


def profession_scan() -> dict:
    """炼金/烹饪全配方成本 vs 产品价 扫描。

    返回 {alchemy: {total, broken:[...], overpriced:[...]},
          cooking: {...}}
    broken     = 材料成本 > 产品价×0.9（亏本做）
    overpriced = 成本 < 产品价×0.2（暴利，价虚高）
    """
    out = {}
    for sect, recipes in (("alchemy", D.ALCHEMY_RECIPES), ("cooking", D.COOKING_RECIPES)):
        total = 0
        broken, overpriced = [], []
        for k, rec in recipes.items():
            total += 1
            cost = sum(_key_price(m) * q for m, q in rec.get("cost", {}).items())
            prod_key = next(iter(rec.get("product", {})), None)
            prod_price = _key_price(prod_key) if prod_key else 0
            if prod_price <= 0:
                continue
            ratio = cost / prod_price
            if ratio > 0.9:
                broken.append({"name": rec.get("name", k), "min_lv": rec.get("min_lv"),
                               "cost": cost, "prod": prod_price, "ratio": round(ratio, 2)})
            elif ratio < 0.2:
                overpriced.append({"name": rec.get("name", k), "min_lv": rec.get("min_lv"),
                                   "cost": cost, "prod": prod_price, "ratio": round(ratio, 2)})
        out[sect] = {"total": total, "broken": broken, "overpriced": overpriced}
    return out


# ---------------- 商店商品价格维度（v166 新增，鱼鱼拍板模型驱动） ----------------
# 口径：商品价 ÷ 配货子区域城镇等级的单只怪含材料收入 = 折算只怪数
#   收入实读 economy_lib（per_kill_gold × 1.5 × 0.9 卖店回收）
# 健康带按类型（SHOP_HEALTH_BANDS），LOW/HIGH 有容差阈值防误报
def _town_sa_map() -> dict:
    """子区域 id → (城镇 map id, 城镇 lv)。实读 MAPS subareas。"""
    out = {}
    for m in D.MAPS:
        mid = m.get("id")
        lv = m.get("lv")
        for s in m.get("subareas", []):
            if isinstance(s, dict) and s.get("id"):
                out[s["id"]] = (mid, lv)
    return out


def _shop_classify(name: str, item: dict) -> str:
    """按物品名/字段语义分类为 SHOP_HEALTH_BANDS 的类型。"""
    nm = name or ""
    effect = str(item.get("effect") or "")
    desc = str(item.get("desc") or "")
    itype = item.get("type") or ""
    # 强化石/符石（养成锚，优先于材料）
    if any(k in nm for k in ("强化石", "符石", "精炼")):
        return "stone"
    # 钥匙/通行令/信物
    if any(k in nm for k in ("钥匙", "通行令", "信物", "试炼令", "徽章", "令")):
        return "key"
    # 卷轴
    if "卷轴" in nm:
        return "scroll"
    # 食物（food=True 优先——麦酒/烈酒/圣果等带 food 标记的归 food）
    if item.get("food"):
        return "food"
    # 战斗 buff（带 effect 字段的功能品：护盾/减伤/增益/治疗增幅等）
    #   —— 铁壁药膏(shield_big)、圣光药剂(heal_up)、龙鳞药剂(magic_resist)、
    #      力量/铁壁/疾风药剂、双倍金币符、复活羽毛、净化圣水类都归 buff
    if effect and not any(k in nm for k in ("药水",)):
        return "buff"
    # 直接回复 HP/MP 药水（回复 X% HP/MP 的 治疗/魔法 药水、生命灵液、绷带）
    if any(k in nm for k in ("药水", "灵液", "绷带", "解毒丹", "草药汁", "圣水", "药膏")):
        # 圣水（祝福圣水 80G 回复 25%HP）归 pot；但"圣光护符"之类不是
        return "pot"
    if any(k in nm for k in ("药剂", "符", "精华", "羽毛", "泪", "圣辉", "圣水")):
        # 名字含药剂但无 effect 的（多为直接回复/功能）→ 若无回复语义归 buff
        if "回复" in desc or "治疗" in desc or "恢复" in desc:
            return "pot"
        return "buff"
    # 材料类（矿石/兽材/草药/木材/织物/宝石/精华/鱼/杂物）
    if itype in ("矿石", "兽材", "草药", "木材", "织物", "宝石", "精华", "鱼", "杂物"):
        return "material"
    # 食物
    if any(k in nm for k in ("面包", "炖菜", "烤肉", "汉堡", "干酪", "麦酒", "朗姆", "烈酒", "苹果酒", "汤", "圣果", "蘑菇", "辣椒", "树蜜", "蜂蜜", "鱼饵", "鱼")):
        return "food"
    return "pot"


def _stage_of_lv(lv: int) -> str | None:
    """城镇等级 → 经济阶段（E1-E6）。实读 ECON_STAGES。"""
    for sid, _name, (lo, hi), _slv, _desc in ECON_STAGES:
        if lo <= lv <= hi:
            return sid
    return None


def shop_scan() -> dict:
    """商店商品价格分阶段扫描（v166 模型驱动，按 ECON_STAGES 分 E1-E6）。

    遍历 SHOP_SUBAREA_ITEMS + SHOP_SMITH_MATERIALS + SHOP_WEAPONS + SHOP_EQUIP，
    每个配货实例按「子区域城镇等级 → 经济阶段」归类；
    每个阶段用该阶段收入（drop_value × 卖店 0.9，采样级收入）折算只怪数，
    落该类型健康带 = 合理，超带 = LOW/HIGH（带容差）。

    判定分两类（对齐"死价格便利品"设计现实）：
      anchor_issues  = 商品首次出现阶段（最低级城 = 价格锚点）的偏离 → 必须修
                      （低级城卖高价 = 新手被宰 HIGH；商品在出生点就太便宜 LOW）
      stage_issues   = 高级阶段便利品延伸的偏离（死价格在高级城相对收入显便宜）
                      → 记 warning 不阻塞（设计上便利品对玩家友好；未来若分级定价再修）

    返回 {total, stages: {E1..E6: {rows, low, high}},
          anchor_issues, stage_issues, health}
    """
    sa_map = _town_sa_map()
    # 子区域 → 城镇收入（单只怪含材料）+ 阶段
    income_cache = {}

    def _town_meta(sa_id):
        if sa_id in income_cache:
            return income_cache[sa_id]
        t = sa_map.get(sa_id)
        if not t:
            income_cache[sa_id] = None
            return None
        mid, lv = t
        try:
            inc = drop_value(lv) * MATERIAL_SELL_RATE
            income_cache[sa_id] = (lv, _stage_of_lv(lv), round(inc, 1))
        except Exception:
            income_cache[sa_id] = None
        return income_cache[sa_id]

    rows = []
    # 1. 消耗品/材料配货（SHOP_SUBAREA_ITEMS）
    for sa_id, iids in D.SHOP_SUBAREA_ITEMS.items():
        meta = _town_meta(sa_id)
        if not meta:
            continue
        town_lv, stage, inc = meta
        for iid in iids:
            it = D.ITEMS.get(iid, {})
            price = it.get("price", 0)
            if not price:
                continue
            kind = _shop_classify(it.get("name", iid), it)
            rows.append({"sa": sa_id, "key": iid, "name": it.get("name", iid),
                         "town_lv": town_lv, "stage": stage,
                         "price": price, "kind": kind, "income": inc,
                         "kills": round(price / max(inc, 1), 3)})
    # 2. 铁匠铺材料（SHOP_SMITH_MATERIALS）
    for mid_, mids in getattr(D, "SHOP_SMITH_MATERIALS", {}).items():
        for sa_id, (tmid, lv) in sa_map.items():
            if tmid != mid_:
                continue
            meta = _town_meta(sa_id)
            if not meta:
                continue
            town_lv, stage, inc = meta
            for mat_id in mids:
                mt = D.MATERIALS.get(mat_id, {})
                price = mt.get("price", 0)
                if not price:
                    continue
                rows.append({"sa": sa_id, "key": mat_id, "name": mt.get("name", mat_id),
                             "town_lv": town_lv, "stage": stage,
                             "price": price, "kind": "material", "income": inc,
                             "kills": round(price / max(inc, 1), 3)})
            break  # 一个城镇只取一个 smith 子区域代表
    # 3. SHOP_WEAPONS（武器名册）
    for town_id, wlist in D.SHOP_WEAPONS.items():
        for sa_id, (tmid, lv) in sa_map.items():
            if tmid != town_id:
                continue
            meta = _town_meta(sa_id)
            if not meta:
                continue
            town_lv, stage, inc = meta
            for wname, wtype, wlv, wq in wlist:
                from content import stats as _S
                try:
                    stats_ = _S.equip_stats("weapon", wlv, wq)
                    base = int(_S.equip_value(stats_) * 3.5)
                    mult = {"white": 2.0, "green": 2.4, "blue": 3.0, "purple": 4.0, "orange": 5.5}.get(wq, 1.5)
                    price = int(base * mult)
                except Exception:
                    price = 0
                if not price:
                    continue
                rows.append({"sa": sa_id, "key": f"w:{town_id}:{wname}", "name": wname,
                             "town_lv": town_lv, "stage": stage,
                             "price": price, "kind": "equip", "income": inc,
                             "kills": round(price / max(inc, 1), 3)})
            break
    # 4. SHOP_EQUIP（名册装备）
    for town_id, rids in getattr(D, "SHOP_EQUIP", {}).items():
        for sa_id, (tmid, lv) in sa_map.items():
            if tmid != town_id:
                continue
            meta = _town_meta(sa_id)
            if not meta:
                continue
            town_lv, stage, inc = meta
            for rid in rids:
                rid_s = rid if isinstance(rid, str) else rid.get("rid", "")
                r = D.EQUIP_ROSTER.get(rid_s, {})
                if not r:
                    continue
                try:
                    from content.drops import generate_roster_equip
                    eq = generate_roster_equip(rid_s)
                    price = eq.get("price", 0)
                    if not price:
                        price = int(eq.get("stats", {}).get("atk", 0) * 30 + 100)
                except Exception:
                    price = 0
                if not price:
                    continue
                rows.append({"sa": sa_id, "key": f"e:{town_id}:{rid_s}", "name": r.get("name", rid_s),
                             "town_lv": town_lv, "stage": stage,
                             "price": price, "kind": "equip", "income": inc,
                             "kills": round(price / max(inc, 1), 3)})
            break

    # 逐条判带
    def _verdict(row):
        band = SHOP_HEALTH_BANDS.get(row["kind"])
        if not band:
            return None, band
        lo, hi = band
        k = row["kills"]
        if k < lo * SHOP_LOW_TRIGGER:
            return "LOW", band
        if k > hi * SHOP_HIGH_TRIGGER:
            return "HIGH", band
        return None, band

    # 商品首次出现阶段（最低 town_lv 的实例 = 锚点）
    first_stage = {}
    for row in rows:
        key0 = row["key"]
        if key0 not in first_stage or row["town_lv"] < first_stage[key0]["town_lv"]:
            first_stage[key0] = row

    # 分阶段桶 + 判定
    stages = {}
    for sid, _name, (lo, hi), _slv, _desc in ECON_STAGES:
        stages[sid] = {"rows": [], "low": [], "high": []}
    anchor_issues, stage_issues = [], []
    for row in rows:
        if row["key"] in SHOP_EXEMPT_KEYS:
            continue  # 豁免（容器锚等），不判带
        v, band = _verdict(row)
        if row["stage"] and row["stage"] in stages:
            stages[row["stage"]]["rows"].append(row)
            if v:
                entry = {**row, "band": f"{band[0]}~{band[1]}" if band else "", "verdict": v}
                if v == "LOW":
                    stages[row["stage"]]["low"].append(entry)
                else:
                    stages[row["stage"]]["high"].append(entry)
                # 锚点阶段判定 vs 便利品
                fs = first_stage.get(row["key"])
                if fs and row["sa"] == fs["sa"]:
                    anchor_issues.append(entry)
                elif v == "HIGH":
                    # 高级阶段卖贵同样阻塞（玩家被宰）
                    anchor_issues.append(entry)
                else:
                    stage_issues.append(entry)
    return {
        "total": len(rows),
        "stages": stages,
        "anchor_issues": anchor_issues,
        "stage_issues": stage_issues,
        "health": {"low_count": len(anchor_issues) + len(stage_issues),
                   "high_count": len([x for x in anchor_issues if x["verdict"] == "HIGH"]),
                   "must_fix": len(anchor_issues)},
    }


# ---------------- 回复道具对齐维度（v166 食物/药水性价比，2026-09-02 鱼鱼拍板模型驱动） ----------------
# 背景：食物同时给「战斗外回血 + 体力 + 战斗内 hot」，同价回复全面碾压药水（黑面包 10G 回 39%+20体力
#       vs 治疗药水(小) 10G 回 20%）。策划案分工：药水=战斗中瞬时，食物=战斗外恢复+体力+效果。
# 对齐判据：
#   1. 食物战斗外回复(heal) 应 ≤ 同价药水基准回复 × 1.0（食物还送体力/效果，纯回不该更高）
#   2. 食物战斗内 hot×turns 累计应 ≤ 战斗外 heal（战斗内持续只是小额，不能反超）
#   3. 药水本身按基准曲线检查（价格-回复拟合，异常点标记）
# 药水基准锚点（商店治疗药水链，价格→回复%）：(8,0.15),(10,0.2),(20,0.25),(30,0.4),(60,0.5),
#   (100,0.6),(180,0.8),(350,0.9),(500,1.0)——模型线性外推 + 同价取上界。

# 药水基准锚点（价格 → 回复百分比），实读商店在售治疗药水核心链
HEAL_ANCHORS = [
    (8, 0.15), (10, 0.20), (20, 0.25), (30, 0.40), (60, 0.50),
    (100, 0.60), (180, 0.80), (350, 0.90), (500, 1.00),
]


def _potion_baseline(price: int) -> float:
    """同价药水基准回复%（按锚点线性插值/外推，取不低于低档锚）。"""
    # 找最接近的两个锚点线性插值
    if price <= HEAL_ANCHORS[0][0]:
        return HEAL_ANCHORS[0][1]
    for i in range(len(HEAL_ANCHORS) - 1):
        p1, r1 = HEAL_ANCHORS[i]
        p2, r2 = HEAL_ANCHORS[i + 1]
        if p1 <= price <= p2:
            if p2 == p1:
                return r2
            return r1 + (r2 - r1) * (price - p1) / (p2 - p1)
    return HEAL_ANCHORS[-1][1] + (price - HEAL_ANCHORS[-1][0]) * 0.0004  # 高价缓慢外推


def _stamina_from_desc(desc: str) -> int:
    """从 desc 提取 'N 体力'。"""
    if not desc:
        return 0
    m = __import__("re").search(r"(\d+)\s*体力", desc)
    return int(m.group(1)) if m else 0


def heal_alignment_scan() -> dict:
    """全量回复道具（商店食物 + 烹饪产物 + 商店药水）性价比对齐扫描。

    每件道具算：
      - price / heal(战斗外回复) / hot_sum(hot×turns 战斗内累计) / stamina(体力)
      - baseline = 同价药水基准回复%
      - 判据1 food_heal_exceed = heal > baseline（食物战斗外回复超同价药水）
      - 判据2 hot_exceed = hot_sum > heal（战斗内持续反超战斗外总量）
    返回 {total, foods, potions, issues} 其中 issues = 越界道具清单（含目标建议值）。

    豁免（功能定位，非基础补给赛道，不参与对齐）：
      - i_holy_water 祝福圣水：教堂功能水（圣堂祝福），价格偏高但无害（玩家会选药水）
      - i_storm_chowder/i_glow_shark_soup：垂钓稀有料做的纯战斗汤（hot 定位合理）
      - i_emergency_salve 应急灵液：瞬发救命（cast 0.3 溢价，v166 已挪寒脊）
    """
    EXEMPT = {"i_holy_water", "i_storm_chowder", "i_glow_shark_soup", "i_emergency_salve"}
    items_all = {}
    for _sa, its in D.SHOP_SUBAREA_ITEMS.items():
        for iid in its:
            items_all.setdefault(iid, D.ITEMS.get(iid, {}))
    for _rk, r in getattr(D, "COOKING_RECIPES", {}).items():
        for pk in (r.get("product") or {}):
            items_all.setdefault(pk, D.ITEMS.get(pk, {}))

    def is_food(it):
        return bool(it.get("food") or it.get("hot") or it.get("stamina") is not None
                    or _stamina_from_desc(str(it.get("desc", ""))) > 0
                    or it.get("food_effect") or (it.get("effect") or "").endswith("_food"))

    foods, potions, issues = [], [], []
    for iid, it in items_all.items():
        if not it or not it.get("price"):
            continue
        if iid in EXEMPT:
            continue
        price = it["price"]
        heal = it.get("heal") or 0
        hot = it.get("hot") or 0
        turns = it.get("hot_turns") or 3
        hot_sum = hot * turns
        mana = it.get("mana") or 0
        stamina = it.get("stamina")
        if stamina is None:
            stamina = _stamina_from_desc(str(it.get("desc", "")))
        rec = {"key": iid, "name": it.get("name", iid), "price": price,
               "heal": heal, "hot": hot, "turns": turns, "hot_sum": round(hot_sum, 3),
               "stamina": stamina, "mana": mana,
               "baseline": round(_potion_baseline(price), 3)}
        if is_food(it):
            # 食物判据：只有回复类食物（heal>0 或 hot>0）需要对齐；纯体力/效果食物不参与回复对齐
            if heal > 0 or hot > 0:
                rec["food"] = True
                flag = None
                # 食物体力补偿：送体力本身就是额外价值，纯回复允许比同价药水略高
                #   （体力≥20 → 宽容 +15%；纯战斗食物无体力不宽容）
                stamina_bonus = 0.15 if stamina >= 20 else 0.0
                heal_cap = rec["baseline"] * (1.0 + stamina_bonus)
                # 判据1：heal 超同价药水（含体力补偿上限）
                if heal > heal_cap + 1e-9:
                    flag = f"战斗外回复 {heal*100:.0f}% > 同价药水基准×体力补偿 {heal_cap*100:.0f}%"
                # 判据2：hot 累计超 heal（战斗内持续反超战斗外总量）
                elif hot_sum > heal + 1e-9 and heal > 0:
                    flag = f"hot累计 {hot_sum*100:.0f}% > 战斗外 {heal*100:.0f}%"
                if flag:
                    rec["issue"] = flag
                    issues.append(rec)
            foods.append(rec)
        elif it.get("heal") or it.get("mana"):
            # 药水：检查是否显著低于基准（被价格曲线甩开）
            rec["food"] = False
            if heal > 0 and heal < rec["baseline"] * 0.5 - 1e-9:
                rec["issue"] = f"回复 {heal*100:.0f}% 仅同价药水基准 {rec['baseline']*100:.0f}% 的 50% 以下"
                issues.append(rec)
            potions.append(rec)
    return {
        "total": len(foods) + len(potions),
        "foods": foods,
        "potions": potions,
        "issues": issues,
        "health": {"food_count": len(foods), "potion_count": len(potions),
                   "issue_count": len(issues)},
    }
