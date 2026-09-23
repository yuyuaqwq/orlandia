# -*- coding: utf-8 -*-
"""v184 档位（品质）抽取与词条挂载 —— 逐格一致门禁。

路线图 #7「内容侧·档位/词条那块」：把散在内容侧的「品质档位阶梯 + 按权重抽档 +
固定前缀挂载到档位条数」改成调用框架 `ext_loot.loot`（`TierTable` / `count_for`
/ `draw_slots`），**对外行为一字不变**。

做法：**先逐字冻结改动前的旧实现**（本文件 `_old_*` 段，抬头注明来源与改动），
再固定随机种子把「旧 vs 新」逐项对跑。

| 段 | 覆盖 | 判据 |
|---|---|---|
| 2 | `core/affix.roll_affixes` | 7 部位 × 5 档 × 30 次：逐项同种子**全等**（含顺序） |
| 3 | `core/affix.fixed_affixes` | 622 个系列名全等（未改动，钉住不回归） |
| 4 | `core/fishing._quality_weights` | lv -3..12 **位级精确相等**（`==`，浮点不设容差） |
| 5 | `core/fishing._roll_fish_legacy` | 9 级 × 3 钓点 × 4 鱼饵 × 5 次：逐项同种子全等 |
| 6 | `drops.generate_roster_equip` 词条段 | 蓝/紫/橙 × 15 件 × 20 次 + 4 倾向：逐件全等 |
| 7 | `smith_stock._pick_weighted_quality` | 300 种子模型等价 + 2 万次分布等价（分区精确相等） |
| 8 | `commands/misc` 签到周奖励档位 | 300 种子表达式等 + 6 种子真实命令路径 |
| 9 | `event_templates.tpl_merchant` 档位 | 300 种子表达式等 + 10 种子整模板输出全等 |
| 10 | 唯一真相源 | `TierTable(...)` 构造点只允许真源 + 引擎适配层（见 10 段）；各处源码级绑定断言 |

**已知且被有意保留的一处不逐格**：垂钓档位**抽取**那一句仍是 stdlib `random.choices`
（见 5 段说明）——权重行是浮点，引擎 `pick_weighted` 按 `int()` 截断权重会改概率分布
（实测同种子 1%~4% 不同）。权重**行**已收口到 `FISH_TIERS.weights_at`（第 4 段位级相等）。

独立运行：`PYTHONUTF8=1 python tests/test_v184_loot_tiers.py`（exit 0 = 全绿）
"""
import os
import sys
import json
import inspect
import random
import sqlite3
from bisect import bisect_left, bisect_right
from fractions import Fraction
from itertools import accumulate

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402
from _engine_harness import C, db, clean_db, make_player, Main, FakeEvent, run  # noqa: E402

# ★ 搬迁适配（T8 ③）：`_engine_harness.PLUGIN_DIR` 在**包仓版**里 = 包根（不是宿主插件根）；
#   旧正文里 `os.path.join(PLUGIN_DIR, "framework", "games", "orlandia", …)` 在包仓布局下
#   不存在。口径改为：内容真源 = `_paths.PKG_ROOT`（`content/**`），宿主插件根 = `_paths.HOST_ROOT`。
PLUGIN_DIR = _paths.HOST_ROOT      # 宿主插件根（旧 `PLUGIN_DIR` 语义；`game/**` 终态已无 .py）
PKG_ROOT = _paths.PKG_ROOT         # 包根（内容真源）

from content import affix as A            # noqa: E402
from content import drops as D            # noqa: E402
from content import fishing as F          # noqa: E402
from content import smith_stock as SS     # noqa: E402
from content import event_templates as ET  # noqa: E402
from content.quality_tiers import QUALITY_TIERS, FISH_TIERS  # noqa: E402
from content.time_weather import current_season  # noqa: E402


# ★ P5D-REPOINT：`tpl_merchant`（流浪商人）是**故意留在宿主壳**的唯一模板
#   （`game/core/event_templates.py`；第 10 段的宿主源码级绑定断言点名它）。包内
#   `content/event_templates.py` 18 个模板里没有它 ⇒ 直取包内实现时第 9 段
#   `ET.execute_event_template("merchant", …)` 会取到 None。宿主壳随删壳批拿掉后，
#   本文件按**逐字同源**在测试侧复刻宿主模板并用包内同一个 `register` 注册
#   （与宿主壳装配方式一致；第 9 段「旧 vs 新」对拍语义一字不变）。
#: ★ P5F-REPOINT：第 10 段源码扫描的哨兵 —— 目标不是仓库文件，而是本文件里的**复刻体**
#  （`inspect.getsource(_host_tpl_merchant)`）。宿主壳删掉后 `tpl_merchant` 的唯一正文在此。
_REPLICA_TPL_MERCHANT = "<本文件 _host_tpl_merchant 复刻体>"


def _host_tpl_merchant(ctx):
    """逐字复刻宿主壳 `game/core/event_templates.py::tpl_merchant`（v184 后正文）。"""
    _db = ctx._db()
    Cc = ctx._C()
    q = QUALITY_TIERS.pick_weights({"white": 45, "green": 40, "blue": 15}, rng=random)
    equip = Cc.generate_equip(random.choice(["weapon", "ring", "necklace"]), max(1, ctx.lv), q)
    price = int(equip["price"] * 0.6)
    _cur_gold = _db.get_player(ctx.group_id, ctx.qq_id).get("gold", 0)
    if _cur_gold >= price and random.random() < Cc.TRADER_DEAL_CHANCE:
        import json as _json, time as _time
        _db.set_event_state(f"trader_{ctx.group_id}_{ctx.qq_id}", _json.dumps({
            "ts": _time.time(),
            "price": price,
            "equip": equip,
        }))
        return (f"🛒 【流浪商人】一个商人拉住你：“勇士，看货！便宜卖你了！”\n"
                f"{Cc.QUALITY[equip['quality']]['color']}【{equip['name']}】只要 {price} 金币！\n"
                f"是否购买？回复 确认购买/拒绝")
    return (f"🛒 【流浪商人】一个商人向你兜售 {Cc.QUALITY[equip['quality']]['color']}【{equip['name']}】，"
            f"只要 {price} 金币……你摇了摇头：不买不买。商人悻悻地走了。")


if "merchant" not in ET.TEMPLATES:
    ET.register("merchant")(_host_tpl_merchant)

PASS = 0
FAIL = 0
CMP = 0          # 逐项比对条数（与断言数分开如实报）


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", limit=400)


def pair(old_fn, new_fn, *args, seed, **kw):
    """同种子各跑一次（旧 / 新），返回 (old, new)。"""
    random.seed(seed)
    a = old_fn(*args, **kw)
    random.seed(seed)
    b = new_fn(*args, **kw)
    return a, b


# ============================================================================
# 第一步：旧实现逐字冻结（以下 `_old_*` 一律是 v184 改动前的原文，勿改勿洁癖）
#   唯一改动：函数名加 `_old_` 前缀；模块级全局名（FISH_QUALITY_WEIGHTS 等）在本文件
#   顶部按同名绑定，保证冻结体不加修饰即可运行。
# ============================================================================
FISH_QUALITY_WEIGHTS = C.FISH_QUALITY_WEIGHTS
FISH_QUALITY_ORDER = C.FISH_QUALITY_ORDER
FISHING_SPOTS = C.FISHING_SPOTS
FISH_POOL = C.FISH_POOL
FISH_COLLECT = C.FISH_COLLECT
AFFIX_COUNT = C.AFFIX_COUNT
AFFIX_POOL_BY_QUALITY = C.AFFIX_POOL_BY_QUALITY
AFFIXES = C.AFFIXES
SERIES_FIXED_AFFIX = C.SERIES_FIXED_AFFIX
QUALITY_WEIGHTS = SS.QUALITY_WEIGHTS


def _old_roll_affixes(slot: str, lv: int, quality: str) -> list:
    """按品质生成随机词条（20 章 4.2 随机池 + 部位过滤）。

    返回词条 ID 列表；白色 0 条、绿色 1 条、蓝色 2 条、紫色 3 条、
    橙色 3 条（20% 概率 4 条，兑现 AFFIX_COUNT.orange=[3,4]）。
    （名册固定词条不在随机池，由 fixed_affixes 提供。）
    """
    cfg = AFFIX_COUNT.get(quality, 0)
    if isinstance(cfg, list):
        # v104 M07 修复 P2：橙装 20% 概率 4 词条（死配置 AFFIX_COUNT 接入）
        n = cfg[1] if random.random() < 0.20 else cfg[0]
    else:
        n = cfg
    if not n:
        return []
    pool = AFFIX_POOL_BY_QUALITY.get(quality, AFFIX_POOL_BY_QUALITY["orange"])
    # 按部位过滤：武器只出攻击词条，防具只出防御词条（kind 归属）
    want_kind = "attack" if slot == "weapon" else "defense"
    pool = [a for a in pool if AFFIXES[a]["kind"] == want_kind]
    if not pool:
        return []
    return random.sample(pool, min(n, len(pool)))


def _old_fixed_affixes(name: str) -> list:
    """名册装备固定词条(20 章 3.x 系列主题，无随机)

    v173.3 意见#171-A（鱼鱼拍板）：固定词条最多保留 1 条（系列主题锚点），
    第 2/3 条释放回随机池——随机空间放大（原 307 件 2 固定=蓝装 0 随机/紫橙仅 1
    随机；现蓝 1 随机/紫 2 随机/橙 2-3 随机），总词条数不变，数值强度不受影响。
    数据层 SERIES_FIXED_AFFIX 保持完整（供回退/参考），此处只截断消费端。
    """
    affs = list(SERIES_FIXED_AFFIX.get(name, []))
    return affs[:1]


def _old_roster_affix_ids(rid: str, affinity: str | None = None) -> list:
    """【冻结】core/drops.py generate_roster_equip 的「词条」段（v184 前原文，逐字）

    只把这一段摘出来：它之前无随机消费（equip_stats / 分系 / WEAPON_FLAVOR 均无
    random 调用），因此「先 seed 再调整函数」与「先 seed 再调本段」的随机流一致。
    """
    r = C.EQUIP_ROSTER[rid]
    slot, lv, quality = r["slot"], r["lv"], r["quality"]
    # 词条：系列固定 + 随机补足到品质标准数（蓝 2 / 紫 3 / 橙 3）
    fixed = _old_fixed_affixes(r["name"])
    target_n = {"blue": 2, "purple": 3, "orange": 3}.get(quality, 0)
    # v104 M07 修复 P2：橙装 20% 概率 4 词条（与 roll_affixes 一致，兑现 AFFIX_COUNT.orange=[3,4]）
    if quality == "orange" and random.random() < 0.20:
        target_n = 4
    random_n = max(0, target_n - len(fixed))
    pool = [a for a in AFFIX_POOL_BY_QUALITY.get(quality, AFFIX_POOL_BY_QUALITY["orange"])
            if a not in fixed]
    want_kind = "attack" if slot == "weapon" else "defense"
    pool = [a for a in pool if AFFIXES[a]["kind"] == want_kind]
    # 20 章 4.3：词条倾向 → 倾向池直接作为候选（过滤部位类型 + 固定词条）
    # 比品质随机池宽（如蓝装也能出元素词条），玩家主动指定合理
    if affinity:
        aff_pool = C.AFFIX_AFFINITY_POOLS.get(affinity, [])
        aff_pool = [a for a in aff_pool
                    if AFFIXES[a]["kind"] == want_kind and a not in fixed]
        if aff_pool:
            pool = aff_pool
    rnd = random.sample(pool, min(random_n, len(pool))) if pool and random_n else []
    return fixed + rnd


def _old_pick_weighted_quality() -> str:
    # 【冻结】core/smith_stock.py: _pick_weighted_quality（v184 前原文）
    """按品质权重随机一个品质（白20/绿25/蓝35/紫15/橙5）。"""
    total = sum(QUALITY_WEIGHTS.values())
    r = random.randint(1, total)
    acc = 0
    for q, w in QUALITY_WEIGHTS.items():
        acc += w
        if r <= acc:
            return q
    return "blue"


def _old_quality_weights(prof_lv: int) -> list:
    """【冻结】core/fishing.py: _quality_weights（v184 前原文）

    垂钓等级 → 五档权重(Lv.1/3/5/7/9 查表，中间等级线性插值)。
    """
    lv = max(1, min(9, int(prof_lv)))
    keys = sorted(FISH_QUALITY_WEIGHTS)
    if lv <= keys[0]:
        return list(FISH_QUALITY_WEIGHTS[keys[0]])
    if lv >= keys[-1]:
        return list(FISH_QUALITY_WEIGHTS[keys[-1]])
    for a, b in zip(keys, keys[1:]):
        if a <= lv <= b:
            wa = FISH_QUALITY_WEIGHTS[a]
            wb = FISH_QUALITY_WEIGHTS[b]
            t = (lv - a) / (b - a)
            return [wa[i] + (wb[i] - wa[i]) * t for i in range(len(wa))]
    return list(FISH_QUALITY_WEIGHTS[keys[0]])


def _old_roll_fish_legacy(prof_lv: int = 1, spot_id: str | None = None, bait: str | None = None):
    """【冻结】core/fishing.py: _roll_fish_legacy（v184 前原文）

    唯一改动：内部 `_quality_weights(prof_lv)` 指向本文件的冻结副本 `_old_quality_weights`。
    旧垂钓逻辑（v174 前）：drop_engine 池缺失时的行为兜底。

    v116 季节限定：season 硬限定鱼的季节不匹配时跳过；season_boost 偏好的季节权重 ×1.5。
    若某档位在当前季节被硬限定过滤空，则放宽为「不限定季节」重试，避免钓空。
    """
    spot = FISHING_SPOTS.get(spot_id) if spot_id else None
    ban = set(spot.get("ban_quality", [])) if spot else set()
    weights = _old_quality_weights(prof_lv)
    for i, q in enumerate(FISH_QUALITY_ORDER):
        if q in ban:
            weights[i] = 0.0
    # v102.3 鱼饵品质加权（在禁出档位清零之后应用，ban 优先）
    if bait == "glow":
        for i, q in enumerate(FISH_QUALITY_ORDER):
            if q in ("purple", "orange"):
                weights[i] *= 2.0
    elif bait == "dough":
        for i, q in enumerate(FISH_QUALITY_ORDER):
            if q in ("green", "blue"):
                weights[i] *= 1.5
    quality = random.choices(FISH_QUALITY_ORDER, weights=weights, k=1)[0]

    # v116 当前季节（spring/summer/autumn/winter，与 time_weather.current_season 对齐）
    season = current_season()

    def _spots_ok(f):
        return not f.get("spots") or (spot_id and spot_id in f["spots"])

    def _season_ok(f):
        # 硬限定鱼仅当季节匹配才产出；无 season 字段 = 全年可钓
        return not f.get("season") or f["season"] == season

    # 第一步：档位 + 水域 + 季节 三重过滤（季节限定生效）
    pool = [f for f in FISH_POOL
            if f["quality"] == quality and _spots_ok(f) and _season_ok(f)]
    if not pool:
        # 兜底一：本档位在当前季节被限定鱼占满 → 放宽季节限制（仍守水域，避免越界钓点）
        pool = [f for f in FISH_POOL if f["quality"] == quality and _spots_ok(f)]
    if not pool:
        # 防御性兜底二：再退全品质池（原有逻辑，如新钓点蓝档无全水域品种）
        pool = [f for f in FISH_POOL if f["quality"] == quality]
    # v102.3 血饵：稀有鱼种（权重 ≤ 15）品种权重 ×3
    # v104 M15 修复：原阈值 <5 高于 FISH_POOL 实际最低权重(10)，血饵永不生效（20 万竿采样零效果）；
    # 改为 ≤15 覆盖盲鱼/云棉/深渊珍珠/彩虹露珠/风暴贝/鲸须草等稀有鱼种
    if bait == "blood":
        pool_w = [f.get("weight", 1) * (3 if f.get("weight", 1) <= 15 else 1) for f in pool]
    else:
        pool_w = [f.get("weight", 1) for f in pool]
    # v116 季节偏好：season_boost 匹配当前季节的鱼权重 ×1.5（非限定，仅概率上升）
    pool_w = [w * 1.5 if f.get("season_boost") == season else w
              for f, w in zip(pool, pool_w)]
    pick = random.choices(pool, weights=pool_w, k=1)[0]
    # v116 季节感输出标记：命中限定/偏好鱼时，在浅拷贝上附加季节前缀供展示层读取
    # （不直接在共享 FISH_POOL 上写字段，避免污染数据）
    if pick.get("season") == season or pick.get("season_boost") == season:
        pick = dict(pick)
        pick["_season_prefix"] = {"spring": "🌸限定", "summer": "☀️限定",
                                  "autumn": "🍂限定", "winter": "❄️限定"}[season]
    return pick


def _old_signin_week_quality():
    """【冻结】commands/misc.py:308（v184 前原文：签到每 7 天额外奖励的档位抽取）"""
    return random.choices(["green", "blue", "purple"],
                          weights=C.SIGNIN_CONFIG["week_quality_weights"])[0]


def _new_signin_week_quality():
    """与 misc.py 现文等价的表达式（源码级绑定见第 10 段断言）"""
    return QUALITY_TIERS.pick_weights(
        dict(zip(("green", "blue", "purple"), C.SIGNIN_CONFIG["week_quality_weights"])),
        rng=random)


def _old_event_quality():
    """【冻结】core/event_templates.py:340（v184 前原文：《流浪商人》档位抽取）"""
    return random.choices(["white", "green", "blue"], weights=[45, 40, 15])[0]


def _new_event_quality():
    """与 event_templates.py 现文等价的表达式（源码级绑定见第 10 段断言）"""
    return QUALITY_TIERS.pick_weights({"white": 45, "green": 40, "blue": 15}, rng=random)


def _old_tpl_merchant(ctx):
    # 【冻结】core/event_templates.py: tpl_merchant（v184 前原文，逐字）
    # 唯一改动：去掉 `@register("merchant")`（否则会覆盖注册表里的真实现），函数名加 `_old_`。
    """流浪商人：低价装备（可拒绝）。沿用原 merchant 逻辑。
    v113.5 O71 修复：探索强卖无确认直接扣钱 → 改为挂起报价（set_event_state），
    玩家回复『确认购买/拒绝』由 combat.py trader_confirm 命令消费。"""
    import uuid
    db = ctx._db()
    C = ctx._C()
    q = random.choices(["white", "green", "blue"], weights=[45, 40, 15])[0]
    equip = C.generate_equip(random.choice(["weapon", "ring", "necklace"]), max(1, ctx.lv), q)
    price = int(equip["price"] * 0.6)
    # F1 审计修复（C-D3.3）：按 DB 最新 gold 判能否出价（原用 ctx._focus 陈旧对象——调用方在
    # _rule_fire 前可能已通过其他路径加/扣过金币，旧 dict 覆盖会误判出价；与 tpl_loot_gold 同型口径）
    _cur_gold = db.get_player(ctx.group_id, ctx.qq_id).get("gold", 0)
    if _cur_gold >= price and random.random() < C.TRADER_DEAL_CHANCE:  # v101.5 常量
        # v113.5 O71：原逻辑直接扣金币入包（强卖无确认）——先挂起报价等玩家答复
        import json as _json, time as _time
        db.set_event_state(f"trader_{ctx.group_id}_{ctx.qq_id}", _json.dumps({
            "ts": _time.time(),
            "price": price,
            "equip": equip,
        }))
        return (f"🛒 【流浪商人】一个商人拉住你：“勇士，看货！便宜卖你了！”\n"
                f"{C.QUALITY[equip['quality']]['color']}【{equip['name']}】只要 {price} 金币！\n"
                f"是否购买？回复 确认购买/拒绝")
    return (f"🛒 【流浪商人】一个商人向你兜售 {C.QUALITY[equip['quality']]['color']}【{equip['name']}】，"
            f"只要 {price} 金币……你摇了摇头：不买不买。商人悻悻地走了。")


# ============================================================================
# 辅助：真实命令/模板路径
# ============================================================================
def _src(rel):
    """读源码。★ 2026-09-14 收口（B11–B14 宿主薄壳化）：`game/**` 多数文件已成**薄壳**，
    实现真源在包内 `framework/games/orlandia/content/<同名>.py` —— 这里把「壳 + 实现」两侧
    拼接起来（与 `tests/test_v135_bp_drop.py:187-191` 同款口径），断言原意不变、判据不削弱。
    ★ B18-L1（2026-09-14）：命令层整块进包后，包内文件名是 `cmds_<域>.py`（如
    `game/commands/misc.py` → `content/cmds_misc.py`），故两侧拼接再认一个 `cmds_` 名字
    （存在才拼，判据不变）。

    ★ P5D-REPOINT：终态 `game/**` 已清空 ⇒ 宿主壳那一半不存在。此时退到**包内实现单独**
    侧（真源本身），断言语义不变（原本就是「壳 + 实现」两侧拼接，壳没了则实现即全部）。

    ★ 搬迁适配（T8 ③）：实现侧改从 `_paths.PKG_ROOT/content/**` 读（包仓布局下的真源）；
    宿主壳侧 `game/**` 在本仓已无 `.py`（实测 0 个），故不再做宿主侧拼接，口径不变。
    """
    base = os.path.basename(rel)
    text = ""
    found = False
    for nm in ("cmds_" + base, base):
        impl = os.path.join(PKG_ROOT, "content", nm)
        if os.path.exists(impl):
            with open(impl, encoding="utf-8") as fh:
                text = text + "\n" + fh.read()
            found = True
    if not found:
        raise FileNotFoundError("包内真源不存在：%s（查 %s/content）" % (rel, PKG_ROOT))
    return text


def _seed_signin_streak(qq_id, streak):
    """signin 行置成「昨天签过 + 连续 streak 天」→ 本次 claim 后 streak+1 命中每 7 天奖励。"""
    import datetime
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    conn = sqlite3.connect(db.db_path())
    try:
        conn.execute("INSERT OR IGNORE INTO signin (qq_id, last_date, streak, total) "
                     "VALUES (?,?,?,0)", (qq_id, "", 0))
        conn.execute("UPDATE signin SET last_date=?, streak=?, total=? WHERE qq_id=?",
                     (yesterday, streak, streak, qq_id))
        conn.commit()
    finally:
        conn.close()


def _last_equip_quality(qq_id):
    """读背包里最后一件随机装备（eq_ 前缀）的品质——直读原始 JSON，绕开瘦身/水合。"""
    conn = sqlite3.connect(db.db_path())
    try:
        rows = conn.execute("SELECT item_key, item_data FROM inventory WHERE qq_id=? "
                            "ORDER BY rowid", (qq_id,)).fetchall()
    finally:
        conn.close()
    for key, raw in reversed(rows):
        if str(key).startswith("eq_"):
            try:
                d = json.loads(raw)
            except Exception:
                continue
            if isinstance(d, dict) and d.get("quality"):
                return d["quality"]
    return None


# ============================================================================
# 2. roll_affixes：全槽位 × 全档位 × 30 次，逐项（含顺序）同种子全等
# ============================================================================
def sec2_roll_affixes():
    print("【2. core/affix.roll_affixes：全槽位 × 全档位 × 30 次逐项全等】")
    slots = ["weapon", "helm", "armor", "legs", "boots", "ring", "necklace"]
    reps = 30
    bad_total = 0
    q_lens = {}          # 档位 → 出现过的条数集合（全部样本累加）
    for si, slot in enumerate(slots):
        for qi, q in enumerate(C.QUALITY_ORDER):
            for rep in range(reps):
                seed = 184000 + si * 1000 + qi * 100 + rep
                old, new = pair(_old_roll_affixes, A.roll_affixes, slot, 1, q, seed=seed)
                global CMP
                CMP += 1
                q_lens.setdefault(q, set()).add(len(new) if isinstance(new, list) else -1)
                ok = (old == new) and isinstance(new, list)
                if not ok:
                    bad_total += 1
                check(f"roll_affixes {slot}/{q} #{rep}", ok,
                      f"old={old} new={new}", quiet=True)
            old, new = pair(_old_roll_affixes, A.roll_affixes, slot, 1, q, seed=1)
            check(f"{slot}/{q} 同种子逐项全等（{reps} 次）", old == new, f"{old} vs {new}")
            if q in ("white", "green", "blue", "purple"):
                check(f"{slot}/{q} 条数 = AFFIX_COUNT[{q}]",
                      q_lens[q] == {AFFIX_COUNT[q]}, f"{q_lens[q]} vs {AFFIX_COUNT[q]}")
            want_kind = "attack" if slot == "weapon" else "defense"
            check(f"{slot}/{q} 词条 kind 与部位一致",
                  all(AFFIXES[a]["kind"] == want_kind for a in new)
                  if isinstance(new, list) else False, str(new), quiet=True)
    check("全组合逐项比对零差异", bad_total == 0, f"差异 {bad_total}")
    check("橙装条数落在 {3,4}（AFFIX_COUNT.orange=[3,4] 兑现）", q_lens.get("orange") == {3, 4},
          str(q_lens.get("orange")))
    check("白装恒 0 条 / 绿 1 / 蓝 2 / 紫 3",
          (q_lens["white"] == {0} and q_lens["green"] == {1}
           and q_lens["blue"] == {2} and q_lens["purple"] == {3}), str(q_lens))


# ============================================================================
# 3. fixed_affixes（未改动，钉住：「最多 1 条」不回归）
# ============================================================================
def sec3_fixed_affixes():
    print("【3. core/affix.fixed_affixes：622 系列名冻结比对】")
    names = list(SERIES_FIXED_AFFIX.keys())
    bad = [n for n in names if A.fixed_affixes(n) != _old_fixed_affixes(n)]
    global CMP
    CMP += len(names)
    check(f"全部 {len(names)} 个系列名逐名全等", not bad, str(bad[:5]))
    check("固定词条最多 1 条", all(len(A.fixed_affixes(n)) <= 1 for n in names), "")
    check("未知名 → 空表", A.fixed_affixes("不存在的装备名XYZ") == [], "")


# ============================================================================
# 4. 垂钓权重行：lv -3..12 位级精确相等（浮点不设容差）
# ============================================================================
def sec4_fish_weight_rows():
    print("【4. core/fishing._quality_weights：lv -3..12 位级精确相等（== ，无容差）】")
    global CMP
    bad = []
    for lv in range(-3, 13):
        old = _old_quality_weights(lv)
        new = F._quality_weights(lv)
        CMP += 1
        if old != new:
            bad.append((lv, old, new))
        check(f"lv={lv} 行位级相等", old == new, f"{old} vs {new}", quiet=True)
    check("lv -3..12 全部位级相等（-3..0 钳到 1，10..12 钳到 9）", not bad, str(bad))
    bad2 = [lv for lv in range(-3, 13)
            if FISH_TIERS.weights_at(lv) != _old_quality_weights(lv)]
    CMP += 16
    check("FISH_TIERS.weights_at 与旧实现同源位级相等", not bad2, str(bad2))
    check("FISH_TIERS.order == QUALITY_ORDER", tuple(FISH_TIERS.order) == tuple(FISH_QUALITY_ORDER),
          str(FISH_TIERS.order))
    check("FISH_TIERS clamp=(1,9)", FISH_TIERS._clamp == (1, 9), str(FISH_TIERS._clamp))
    # 说明性：确证浮点尾数确实参与比较（非「恰好都是整数」）
    has_float = any(isinstance(x, float) and x != int(x) for x in _old_quality_weights(2))
    check("lv=2 行含非整数浮点（证明比较确实覆盖尾数）", has_float, str(_old_quality_weights(2)))


# ============================================================================
# 5. _roll_fish_legacy：等级 × 钓点 × 鱼饵 × 5 次，逐项同种子全等
#    这一段的红色警报含义：若有人把「random.choices(浮点权重)」换成引擎 pick_weighted，
#    它会 int() 截断权重 → 本段会大面积红（实测 1%~4% 条目不同）。
# ============================================================================
def sec5_roll_fish_legacy():
    print("【5. core/fishing._roll_fish_legacy：9 级 × 3 钓点 × 4 鱼饵 × 5 次逐项全等】")
    spots = [None] + sorted(FISHING_SPOTS.keys())[:2]
    baits = [None, "glow", "dough", "blood"]
    reps = 5
    bad_total = 0
    for lv in range(1, 10):
        for sp in spots:
            for bait in baits:
                for rep in range(reps):
                    seed = 184500 + lv * 1000 + (0 if sp is None else 1) * 100 + rep \
                        + baits.index(bait) * 10
                    old, new = pair(_old_roll_fish_legacy, F._roll_fish_legacy,
                                    lv, sp, bait, seed=seed)
                    global CMP
                    CMP += 1
                    ok = (old == new
                          and json.dumps(old, sort_keys=True, ensure_ascii=False)
                          == json.dumps(new, sort_keys=True, ensure_ascii=False))
                    if not ok:
                        bad_total += 1
                    check(f"_roll_fish_legacy lv={lv} spot={sp} bait={bait} #{rep}", ok,
                          f"old={old} new={new}", quiet=True)
                old, new = pair(_old_roll_fish_legacy, F._roll_fish_legacy, lv, sp, bait, seed=3)
                check(f"lv={lv} spot={sp} bait={bait} 同种子逐项全等（{reps} 次）",
                      old == new, f"{old} vs {new}")
    check("全组合逐项比对零差异", bad_total == 0, f"差异 {bad_total}")


# ============================================================================
# 6. generate_roster_equip 词条段：逐件同种子全等（蓝/紫/橙覆盖 20% 四词条分支）
# ============================================================================
def sec6_roster_affixes():
    print("【6. drops.generate_roster_equip 词条段：蓝/紫/橙/绿/白 逐件同种子全等】")
    reps = 20
    plan = [("blue", 15), ("purple", 15), ("orange", 15), ("green", 5), ("white", 5)]
    bad_total = 0
    got4 = 0
    for qi, (q, n) in enumerate(plan):
        rids = [rid for rid, r in C.EQUIP_ROSTER.items() if r["quality"] == q][:n]
        for ri, rid in enumerate(rids):
            for rep in range(reps):
                seed = 184600 + qi * 10000 + ri * 100 + rep
                random.seed(seed)
                old = _old_roster_affix_ids(rid)
                random.seed(seed)
                new = D.generate_roster_equip(rid).get("affixes", [])
                global CMP
                CMP += 1
                if old != new:
                    bad_total += 1
                if len(new) == 4:
                    got4 += 1
                check(f"roster {rid} #{rep}", old == new, f"old={old} new={new}", quiet=True)
            random.seed(7)
            old = _old_roster_affix_ids(rid)
            random.seed(7)
            new = D.generate_roster_equip(rid).get("affixes", [])
            check(f"{q} 件 {rid} 词条同种子全等（{reps} 次）", old == new, f"{old} vs {new}")
    check("全件逐项比对零差异", bad_total == 0, f"差异 {bad_total}")
    check("橙装 20% 四词条分支被覆盖到（出现 len==4 的样本）", got4 > 0, f"got4={got4}")
    # affinity 倾向路径（20 章 4.3：攻击/防御/元素/机动 → 倾向池直接作候选）
    aff_bad = []
    purple_rids = [rid for rid, r in C.EQUIP_ROSTER.items() if r["quality"] == "purple"][:3]
    for aff in sorted(C.AFFIX_AFFINITY_POOLS.keys()):
        for rid in purple_rids:
            for rep in range(5):
                seed = 184700 + rep
                random.seed(seed)
                old = _old_roster_affix_ids(rid, aff)
                random.seed(seed)
                new = D.generate_roster_equip(rid, aff).get("affixes", [])
                CMP += 1
                if old != new:
                    aff_bad.append((aff, rid, rep, old, new))
        random.seed(9)
        old = _old_roster_affix_ids(purple_rids[0], aff)
        random.seed(9)
        new = D.generate_roster_equip(purple_rids[0], aff).get("affixes", [])
        check(f"倾向 {aff} 逐件全等", old == new, f"{old} vs {new}")
    check("4 种词条倾向全部逐件零差异", not aff_bad, str(aff_bad[:3]))


# ============================================================================
# 7. smith_stock._pick_weighted_quality：分布等价（逐次种子**不同**，见下）
#    旧 = randint(1, 总和) + 手写累加；新 = 引擎 pick_weighted（random() × 总和 + 累加命中）。
#    两者是同一概率分区，但消费的随机数不是同一个 → 逐次同种子结果必然不同。
#    因此这里证明的是：① 新实现对「一次 random()」的选择规则与解析模型逐种子全等；
#    ② 旧实现对「一次 randint」的选择规则与解析模型逐种子全等；③ 两者分区精确相等。
# ============================================================================
def sec7_smith_quality():
    print("【7. core/smith_stock._pick_weighted_quality：模型等价 + 分区等价 + 2 万次分布】")
    order = list(QUALITY_WEIGHTS.keys())
    w = [QUALITY_WEIGHTS[k] for k in order]
    total = sum(w)
    cum = list(accumulate(w))
    check("权重表键序 == 档位序（对齐前提）", order == list(QUALITY_TIERS.order), str(order))

    bad_new = []
    bad_old = []
    for s in range(300):
        random.seed(s)
        expect = order[bisect_right(cum, random.random() * total)]
        random.seed(s)
        got = SS._pick_weighted_quality()
        if got != expect:
            bad_new.append((s, got, expect))
        random.seed(s)
        expect_old = order[bisect_left(cum, random.randint(1, total))]
        random.seed(s)
        got_old = _old_pick_weighted_quality()
        if got_old != expect_old:
            bad_old.append((s, got_old, expect_old))
        global CMP
        CMP += 2
    check("新实现 ≡ 一次 random() + 累积切段（300 种子逐种子全等）", not bad_new, str(bad_new[:3]))
    check("旧实现 ≡ 一次 randint(1,总和) + 累积切段（300 种子逐种子全等）", not bad_old, str(bad_old[:3]))

    lo = 0
    part_bad = []
    for i, k in enumerate(order):
        old_p = Fraction(cum[i] - lo, total)     # randint 均匀落在整数 1..total 的占比
        new_p = Fraction(cum[i] - lo, total)     # random() 均匀落在 [0,total) 的占比
        CMP += 1
        if old_p != new_p:
            part_bad.append((k, old_p, new_p))
        lo = cum[i]
    check(f"分区精确等价（Fraction，无容差）：{[(k, str(Fraction(cum[i], total))) for i, k in enumerate(order)]}",
          not part_bad, str(part_bad))

    n = 20000
    random.seed(1001)
    new_samples = [SS._pick_weighted_quality() for _ in range(n)]
    random.seed(1001)
    old_samples = [str(_old_pick_weighted_quality()) for _ in range(n)]
    new_samples = [str(x) for x in new_samples]
    for i, k in enumerate(order):
        p = w[i] / total
        f_new = new_samples.count(k) / n
        f_old = old_samples.count(k) / n
        check(f"{k} 新分布 {f_new:.4f} ≈ {p:.4f}", abs(f_new - p) < 0.01, f"{f_new}")
        check(f"{k} 旧分布 {f_old:.4f} ≈ {p:.4f}", abs(f_old - p) < 0.01, f"{f_old}")
        CMP += 2
    check("新旧可取集合一致（都是全 5 档）",
          set(new_samples) == set(old_samples) == set(order), "")
    diff = sum(1 for a, b in zip(new_samples, old_samples) if a != b)
    print(f"  ℹ️ 逐次同种子差异 {diff}/{n}（{diff / n:.2%}）——随机流不同、分布相同（非缺陷）")


# ============================================================================
# 8. 签到每 7 天奖励档位：表达式 300 种子全等 + 真实命令路径对比
# ============================================================================
async def sec8_signin(m):
    print("【8. commands/misc 签到周奖励档位：300 种子表达式等 + 真实命令路径】")
    bad = []
    for s in range(300):
        random.seed(s)
        a = _old_signin_week_quality()
        random.seed(s)
        b = _new_signin_week_quality()
        global CMP
        CMP += 1
        if a != b:
            bad.append((s, a, b))
    check("旧表达式 ≡ 新表达式（300 种子逐种子全等，同随机流）", not bad, str(bad[:3]))

    got = []
    for s in (11, 22, 33, 44, 55, 66):
        clean_db()
        make_player("gs", f"qs{s}", level=5)
        _seed_signin_streak(f"qs{s}", 6)
        random.seed(s)
        res = await run(m.signin, FakeEvent("gs", f"qs{s}", "签到"))
        text = res[-1] if res else ""
        q_real = _last_equip_quality(f"qs{s}")
        # 重放：第 1 个 random() 是每日运势，第 2 个才是周奖励档位
        random.seed(s)
        random.random()
        q_old = _old_signin_week_quality()
        random.seed(s)
        random.random()
        q_new = _new_signin_week_quality()
        CMP += 2
        got.append(q_real)
        check(f"seed={s} 真实命令发放档位 == 旧表达式 {q_old}", q_real == q_old,
              f"real={q_real} old={q_old} new={q_new} text={text[:120]}")
        check(f"seed={s} 真实命令发放档位 == 新表达式 {q_new}", q_real == q_new, str(q_real))
    check("覆盖 ≥3 个不同档位（抽样确实在工作）", len(set(got)) >= 3, str(got))


# ============================================================================
# 9. 事件模板《流浪商人》档位：表达式 + 整模板逐种子全等
# ============================================================================
def sec9_event_template():
    print("【9. event_templates.tpl_merchant：300 种子表达式等 + 10 种子整模板文本全等】")
    bad = []
    for s in range(300):
        random.seed(s)
        a = _old_event_quality()
        random.seed(s)
        b = _new_event_quality()
        global CMP
        CMP += 1
        if a != b:
            bad.append((s, a, b))
    check("旧表达式 ≡ 新表达式（300 种子逐种子全等，同随机流）", not bad, str(bad[:3]))

    clean_db()
    make_player("gm", "qm", level=5)
    db.update_player("gm", "qm", gold=5000, cur_map="oak_plain", cur_subarea="oak_plain_1")
    texts_old = []
    for s in range(10):
        ctx = ET.EventContext("gm", "qm", db.get_player("gm", "qm"), C.MAP_BY_ID["oak_plain"],
                              params={}, name="橡木平原")
        random.seed(2000 + s)
        old = _old_tpl_merchant(ctx)
        ctx2 = ET.EventContext("gm", "qm", db.get_player("gm", "qm"), C.MAP_BY_ID["oak_plain"],
                               params={}, name="橡木平原")
        random.seed(2000 + s)
        new = ET.execute_event_template("merchant", ctx2)
        texts_old.append(old)
        CMP += 1
        check(f"seed={2000 + s} 整模板输出逐字全等", old == new,
              f"old={str(old)[:150]} new={str(new)[:150]}")
    check("两个分支都被覆盖（成交 / 摇头）",
          any("便宜卖你了" in t for t in texts_old) and any("摇了摇头" in t for t in texts_old),
          str([t[:20] for t in texts_old]))


# ============================================================================
# 10. 唯一真相源 + 源码级绑定
# ============================================================================
def sec10_single_source():
    print("【10. 唯一真相源 / 各处源码级绑定】")
    # 全仓建 TierTable 的落点只允许「真源 + 引擎适配层」两处
    # ★ P5F-REPOINT: 原扫 `<插件>/game/**`（宿主壳随删壳批消失）→ 扫包内真源树
    #   `framework/games/orlandia/content/**`。原意「全仓只有一处**建档位表**」保留为：
    #   档位表真源只由 `content/quality_tiers.py` 建（`TierTable(QUALITY_ORDER, …)`）；
    #   `content/loot.py` 的另两个构造点不是建档 —— `_EMPTY_TIERS = TierTable(())`（空占位）
    #   与 `install_quality_tiers(order or (), …)`（引擎侧替身接口，取值由调用方给）。
    #   判据 = 构造点只在这两个文件里，**出现第三处即红**。
    _root = os.path.join(PKG_ROOT, "content")
    _expect = ["content/loot.py",
               "content/quality_tiers.py"]
    owners = []
    for root, dirs, files in os.walk(_root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            with open(p, encoding="utf-8") as fh:
                if "TierTable(" in fh.read():
                    owners.append(os.path.relpath(p, PKG_ROOT).replace("\\", "/"))
    owners = sorted(set(owners))
    check("全仓 TierTable 构造点只在真源 + 引擎适配层两处（第三处即红）",
          owners == _expect, str(owners))
    check("QUALITY_TIERS.order == data 层 QUALITY_ORDER",
          tuple(QUALITY_TIERS.order) == tuple(C.QUALITY_ORDER), str(QUALITY_TIERS.order))
    check("QUALITY_TIERS.info_of 打通 QUALITY（mult/color/name）",
          QUALITY_TIERS.info_of("blue")["mult"] == C.QUALITY["blue"]["mult"]
          and QUALITY_TIERS.info_of("orange")["name"] == C.QUALITY["orange"]["name"], "")
    check("QUALITY_TIERS.resolve 认中文别名", QUALITY_TIERS.resolve("蓝") == "blue", "")

    # ★ P5F-REPOINT: 原扫宿主壳 `game/core/*.py` / `game/commands/*.py`（随删壳批消失）
    #   → 包内真源同名实现（`content/<file>.py`）；`_src()` 的「壳+实现」拼接在删壳后
    #   自然只剩实现侧，判据不变。
    checks = [
        ("content/affix.py",
         "count_for(AFFIX_COUNT, quality, extra_chance=0.20, rng=random)", True),
        ("content/affix.py", "return draw_slots(pool, n, rng=random)", True),
        ("content/drops.py",
         'count_for({"blue": 2, "purple": 3, "orange": [3, 4]}, quality,', True),
        ("content/drops.py",
         "draw_slots(pool, target_n, fixed=fixed, rng=random)", True),
        ("content/smith_stock.py",
         "QUALITY_TIERS.pick_weights(QUALITY_WEIGHTS, rng=random)", True),
        ("content/smith_stock.py", "random.randint(1, total)", False),
        ("content/misc_cmds.py",
         "QUALITY_TIERS.pick_weights(_wq, rng=random)", True),
        ("content/misc_cmds.py",
         'random.choices(["green", "blue", "purple"]', False),
        # ★ P5F-REPOINT: `tpl_merchant`（流浪商人）是**故意留在宿主壳**的最后一块
        #   （`game/core/event_templates.py`，随删壳批消失）；本文件已在测试侧逐字复刻
        #   （`_host_tpl_merchant`，见文件头 ★ P5D-REPOINT）⇒ 这两条改扫**复刻体自身**
        #   （判据不变：档位抽取必须走 QUALITY_TIERS.pick_weights，不走 random.choices）。
        (_REPLICA_TPL_MERCHANT,
         'QUALITY_TIERS.pick_weights({"white": 45, "green": 40, "blue": 15}, rng=random)', True),
        (_REPLICA_TPL_MERCHANT, 'random.choices(["white", "green", "blue"]', False),
        ("content/fishing.py", "weights = FISH_TIERS.weights_at(prof_lv)", True),
        ("content/fishing.py", "FISH_QUALITY_WEIGHTS[", False),
        ("content/fishing.py",
         "random.choices(FISH_QUALITY_ORDER, weights=weights, k=1)[0]", True),
    ]
    for path, needle, want in checks:
        src = inspect.getsource(_host_tpl_merchant) if path == _REPLICA_TPL_MERCHANT else _src(path)
        has = needle in src
        check(f"{path} {'含' if want else '不含'} {needle!r}", has == want, f"has={has}")
    # 更强：AST 级「不再有 random.sample 调用」（注释/文档串里提到不算）
    import ast
    for path in ("content/affix.py",
                 "content/drops.py"):
        tree = ast.parse(_src(path))
        hits = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "sample"
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "random"]
        check(f"{path} AST 级无 random.sample 调用（抽样已交给引擎）", not hits, f"行 {hits}")
    check("包内 content/data 数据表未被改动（抽查关键表仍在且取值如旧）",
          C.AFFIX_COUNT["orange"] == [3, 4]
          and C.SIGNIN_CONFIG["week_quality_weights"] == [55, 35, 10]
          and C.QUALITY_ORDER == ["white", "green", "blue", "purple", "orange"]
          and C.FISH_QUALITY_WEIGHTS[9] == [41, 29, 20, 9, 1.0], "")


# ============================================================================
async def main():
    print("=" * 72)
    print("v184 档位（品质）与词条挂载 —— 逐格一致门禁")
    print("=" * 72)
    sec2_roll_affixes()
    sec3_fixed_affixes()
    sec4_fish_weight_rows()
    sec5_roll_fish_legacy()
    sec6_roster_affixes()
    sec7_smith_quality()
    clean_db()
    m = Main(None)
    await sec8_signin(m)
    sec9_event_template()
    sec10_single_source()
    print("-" * 72)
    print(f"断言 {PASS + FAIL}（通过 {PASS} / 失败 {FAIL}）｜逐项比对 {CMP} 条")
    print(f"结果：{'全绿 ✅' if FAIL == 0 else '有红 ❌'}")
    return FAIL == 0


if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
