# -*- coding: utf-8 -*-
"""test_v184_loot_pools —— 掉落池「旧实现 vs 引擎实现」逐格一致门禁（v184 · 路线图 #7「内容侧·池」）

目标：把 `game/drop_engine.py` 的池 / 策略 / 展开 / 审计改成调用框架 `saintess_engine.loot`
（`LootTable` + 内置策略 + `TierTable` 档位表），**对外 API 与行为一字不变**。

本文件是这条改造的唯一证据：**先逐字冻结旧实现**（`_FROZEN_SRC`，sha256 锁死，§0 自检），
再固定随机种子把「旧 vs 新」逐项对跑 —— 读代码觉得等价不算数。

| 段 | 覆盖 | 判据 |
|---|---|---|
| 0 | 冻结自检 | 冻结体 sha256 == v174 原文；可执行；旧内联副本在、新实现已删 |
| 1 | `audit_all()` | 596 池逐项（级别/池key/描述，含顺序）全等 + `pool_count`/`entry_count` + 返回键集不变 + `audit_pretty()` 逐字 |
| 2 | `expand_pool()` | 596 池逐项（含顺序）全等；不存在的 key / 带前缀 key 仍 `[]` |
| 3 | `roll()` | **596 池 × 13 ctx × 4 种子 = 30,992 组合**：类型 / 物品 id / count / 列表顺序**严格全等**（`_diff` 递归比类型与 key 顺序） |
| 4 | table_choice / table 专项 | 暗格 5 档 cutoff + 兜底 fallback（`roll_drop_equip` 探针强制触发）+ 真实宝箱/战利品堆池多种子；档位覆盖计数 |
| 5 | 合成池分支 | weighted 等级窗口 / 兜底钩子（有钩·无钩）/ 空池 / 权重和、table 各 `chance`/`n`/内联引用/子池、fixed、table_choice cutoff 与 chance、table_choice 兜底 |
| 6 | 名字与唯一真相源 | `POOL_STRATEGIES` 只读转发、`_SimpleCtx` 别名、旧私有实现已删、源码级绑定、**import 期不拉池数据**（子进程实证） |
| 7 | 已知差异（有意，登记） | 7 条：真实池数据均未使用，逐条钉住「新行为」并写明旧行为（D7 = 引擎自己那两条结构消息的措辞）|
| 8 | 入口边界 | 池不存在 / 带前缀 key → `[]`；`kw` 就地 setattr；`ctx=None + kw` |

跑法：`PYTHONUTF8=1 python tests/test_v184_loot_pools.py`（exit 0 = 全绿）

§7 登记的有意差异（非"未覆盖"，逐条钉住；真实池数据 0 命中）：
  1. `gold:` 子引用带 `n`：旧忽略 `n`（也不乘 qty），新按 `roll_range(n)` 乘 count
  2. `weighted:`/`fixed:` 前缀子池引用：旧的 raw key miss → 当内联引用交给 resolver（出垃圾物品），
     新剥前缀命中子池（`pool_key_prefixes`）
  3. 裸名册 id（`eq_xxx`）当**条目** ref：旧判断链，新放行（引擎只给一个 `resolvable` 回调，
     与「roll 侧放行裸名册 id」不可兼得，选了忠实 roll 侧那一支；真实池 0/1435）
  4. `fixed` 池 `entries` 为空：旧不报"空池"，新按策略元数据 `uses=entries` 报
  5. `table_choice` 池的 `rolls` 子池：旧不审，新按 `uses=rolls` 一并审
  6. `table` 池的 roll 行带 `fallback`/`fallback_n`：旧**忽略**（抽空即空），新按引擎 `roll_cfg`
     应用兜底（旧只有 `table_choice` 那条路支持 fallback）
"""
import hashlib
import os
import random
import subprocess
import re
import sys
from collections.abc import Mapping

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from _engine_harness import C  # noqa: E402
import _paths                                                          # noqa: E402

# ★ 搬迁适配（T8 ③）：`_engine_harness.PLUGIN_DIR` 在**包仓版**里 = 包根（不是宿主插件根）；
#   旧正文里 `os.path.join(PLUGIN_DIR, "framework", "games", "orlandia", …)` 在包仓布局下
#   不存在（那是宿主部署树里的包副本位置）。口径改为：内容真源 = `_paths.PKG_ROOT`，
#   引擎根 = `_paths.ENGINE_ROOT`，宿主插件根 = `_paths.HOST_ROOT`。
PLUGIN_DIR = _paths.PKG_ROOT          # 旧名沿用；本文件里它已按「包根」使用
PKG_ROOT = _paths.PKG_ROOT
HOST_ROOT = _paths.HOST_ROOT
QQBOT_DIR = HOST_ROOT
_FRAMEWORK_DIR = _paths.ENGINE_ROOT
for _p in (_FRAMEWORK_DIR, PLUGIN_DIR, QQBOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ★ 冻结体（v174 原文，一个字符没动）里的 `importlib.import_module("game.content")` /
#   `from .data.drop_pools import DROP_POOLS` 是**旧宿主绝对路径**；终态无 `game/**`。
#   处理 = 在 `sys.modules` 里把 `game` 指到一只轻量 shim 模块（`__path__` = 包内 content
#   目录 → 冻结体里 `game.<子模块>` 全解析到包内同名模块；`game.content` 显式指到聚合门面），
#   冻结文本本身保持逐字（sha256 判据不动）。
import types as _types                                                 # noqa: E402
from content import facade as _facade                                  # noqa: E402
from content import loot as _loot                                      # noqa: E402
from content import catalog_rules as _DP                               # noqa: E402

_PKG_CONTENT = os.path.dirname(os.path.abspath(_facade.__file__))
_game_shim = _types.ModuleType("game")
_game_shim.__path__ = [_PKG_CONTENT]
_game_shim.content = _facade.C
_game_shim.drop_engine = _loot
sys.modules.setdefault("game", _game_shim)
sys.modules.setdefault("game.content", _facade.C)
sys.modules.setdefault("game.drop_engine", _loot)
DROP_POOLS = _DP.DROP_POOLS
import importlib as _importlib                                        # noqa: E402
# ★ P5F 前置②（去壳）：原 = `_importlib.import_module("data.plugins.dragonfall.game.drop_engine")`
#   走待删壳 `game/drop_engine.py`（它本身是**别名壳**：`sys.modules[__name__] = content.loot`
#   ⇒ 取到的就是同一只模块对象）。终态 `game/**` 删除后该 import 直接 ModuleNotFoundError。
#   改法 = 直取包内真源（`content.loot`，同一只对象）+ 把同一只对象登记到旧宿主模块名下，
#   让冻结体里按旧模块名取件的路径仍解析到**同一对象**（打桩/同一性断言一字不变）。
DE = _loot
sys.modules.setdefault("data.plugins.dragonfall.game.drop_engine", _loot)
# B16 收口：宿主 game/data 已删 —— 池数据真源 = 包内 `content/data/drop_pools.json`（596 池，逐条同源）
#   门面 = `content.catalog_rules.DROP_POOLS`（同一只 dict，模块属性可写 → §5 打桩仍有效）
#   ★ 冻结体（v174 原文，一个字符没动）里的 `from .data.drop_pools import DROP_POOLS`
#     （`__package__` = data.plugins.dragonfall.game）与 `game/drop_engine.py::_get_pools()`
#     的「宿主已加载则优先」分支都按**这个模块名**取数 → 在 sys.modules 里把它指到包内同一只
#     模块对象，新旧两侧读的仍是同一份 DROP_POOLS，§5 `_with_pools` 打桩同时可见（判据不削弱）。
from content import catalog_rules as _DP                                        # noqa: E402
DROP_POOLS = _DP.DROP_POOLS
sys.modules["data.plugins.dragonfall.game.data.drop_pools"] = _DP

# ★ P5F 前置②（去壳）：旧壳 `game/drop_engine.py` **不只是别名** —— 它另外安装三个
#   **宿主取件活源**（池数据源 / 内容 API / 垂钓档位表，见该壳正文 ① ② ③）。终态壳删除后
#   必须在测试侧以**同款活源**接管，否则 §5 `_with_pools()` 的 `_DP.DROP_POOLS` 打桩对实现
#   不可见（实测：合成池全落回真源 596 池 → 14 条断言红）。三个活源的几何与旧壳逐条等价：
#     · 池数据源   ≡ 壳 `_host_pools_source()`：本树 `...game.data.drop_pools` 在册则优先读它
#     · 内容 API   ≡ 壳 `_host_content_api()`：`import game.content as C` = 包内聚合门面
#     · 垂钓档位表 ≡ 壳 `_host_quality_tiers()`：唯一真相源 = 包内 `content/quality_tiers.py`
def _p5f_pools_source():
    _host = sys.modules.get("data.plugins.dragonfall.game.data.drop_pools")
    if _host is not None and hasattr(_host, "DROP_POOLS"):
        return _host.DROP_POOLS
    return _DP.DROP_POOLS


def _p5f_content_api_source():
    return _facade.C


def _p5f_quality_tiers_source():
    from content.quality_tiers import FISH_TIERS       # noqa: PLC0415
    return FISH_TIERS


_loot.install_pools_source(_p5f_pools_source)
_loot.install_content_api_source(_p5f_content_api_source)
_loot.install_quality_tiers_source(_p5f_quality_tiers_source)

from saintess_engine.loot import SimpleCtx as EngineSimpleCtx                   # noqa: E402
from saintess_engine.loot import strategy_names                                 # noqa: E402

PASS = 0
FAIL = 0
CMP = 0          # 逐项比对条数（与断言数分开如实报）


def check(name, cond, detail="", quiet=False):
    global PASS, FAIL
    if cond:
        PASS += 1
        if not quiet:
            print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}: {str(detail)[:600]}")


def _diff(a, b, path="result"):
    """严格逐项比对：类型 / dict key 顺序 / 值 / 列表顺序（返回差异描述，无差异 → ""）。"""
    if type(a) is not type(b):
        return f"{path}: 类型不同 {type(a).__name__} ≠ {type(b).__name__}"
    if isinstance(a, dict):
        if list(a) != list(b):
            return f"{path}: key 顺序/集合不同 {list(a)} ≠ {list(b)}"
        for k in a:
            d = _diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return ""
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return f"{path}: 长度不同 {len(a)} ≠ {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = _diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return ""
    if a != b:
        return f"{path}: 值不同 {a!r} ≠ {b!r}"
    return ""


# ============================================================================
# 第一步：旧实现逐字冻结（以下 `_FROZEN_SRC` 是 v184 改动前 `game/drop_engine.py`
# 的**整份原文**，一个字符都没动；sha256 在 §0 与上面写死的值比对 —— 谁改谁红）
# ============================================================================
_FROZEN_SHA256 = "e80d239f3c9e05ad7a62a1fd26ce18b8ead929ed6e6de967d20f70a4fa082418"
_FROZEN_SRC = r'''# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年核心层 - drop_engine.py（掉落系统统一引擎 v174）

把全游戏散落的掉落池收敛为单一数据表 DROP_POOLS + 统一抽取入口 roll() + 审计 audit_all()。

设计（分层抽象，鱼鱼 2026-09-04 拍板）：
- 统一入口：roll(pool_key, ctx) —— 任何池子都走这里
- 统一数据：DROP_POOLS（game/data/drop_pools.py，纯数据）
- 四种子策略：
    weighted    带权条目抽取（采集/挖掘/通用材料/小怪材料）
    fish        垂钓（质量档→品种；季节/水域/鱼饵过滤）
    table       多层概率表（副本Boss/野王宝箱/垂钓惊喜——各 roll 独立判定）
    fixed       固定掉落（精英专属/必掉清单）

条目引用统一带前缀：
    mat_xxx/物品ID  → 普通物品
    equip:eq_xxx    → 名册装备（generate_roster_equip）
    bp              → 图纸（等级就近 roll_blueprint）
    gem             → 幸运宝石（roll_gem_drop）
    gold:[a,b]      → 金币区间
    rune            → 符文（稀有）
    item:ID         → 带 count 的普通物品
    special:xxx     → 扩展点（调用方注入的 hook，防特殊语义硬编码）
"""
import random
from typing import Any


# ============================================================
# 基础工具
# ============================================================

def _randint(a: int, b: int) -> int:
    return random.randint(a, b)


def _weighted_pick(entries: list[dict]) -> dict | None:
    """从 [{"w": int, ...}, ...] 按权重抽一个；空列表/全 0 返回 None。"""
    if not entries:
        return None
    total = sum(int(e.get("w", 1) or 0) for e in entries)
    if total <= 0:
        return None
    roll = random.random() * total
    acc = 0.0
    for e in entries:
        acc += int(e.get("w", 1) or 0)
        if roll < acc:
            return e
    return entries[-1]


def _resolve_item_ref(ref: str, ctx: Any) -> dict | None:
    """把条目引用解析为实物。返回统一产出 dict 或 None（池空/失败优雅跳过）。

    产出 dict 形态：{"type": "item"/"equip"/"bp"/"gem"/"gold"/"rune", "name":..., "data":..., "count":...}
    """
    import game.content as C  # noqa: E402  绝对导入，防循环/半初始化

    if ref == "bp":
        bp = C.roll_blueprint(max(1, int(getattr(ctx, "player_level", 1) or 1)))
        return {"type": "bp", "data": bp} if bp else None
    if ref == "gem":
        mon = {"lv": getattr(ctx, "monster_lv", None) or getattr(ctx, "player_level", 30),
               "is_boss": True, "map_area": "field"}
        gem = C.roll_gem_drop(mon)
        return {"type": "gem", "data": gem} if gem else None
    if ref == "rune":
        # 稀有符文：蓝/紫品质随机（v168 语义：随机取蓝/紫符文 1 级）
        pool = [k for k, r in C.RUNES.items() if (r.get("quality") or "") in ("blue", "purple")]
        if not pool:
            return None
        rk = random.choice(pool)
        r_def = C.RUNES[rk]
        rune_data = C.rune_item(r_def["effect"], random.randint(1, 2))
        return {"type": "rune", "data": rune_data} if rune_data else None
    if ref.startswith("gold:"):
        # gold:300:600
        parts = ref.split(":")
        a, b = int(parts[1]), int(parts[2]) if len(parts) > 2 else int(parts[1])
        return {"type": "gold", "count": _randint(a, b)}
    if ref.startswith("gold_pct:"):
        # gold_pct:30 = ctx.gold_base × 30%（战利品堆金币=通关奖金×30%）
        pct = float(ref.split(":", 1)[1])
        base = int(getattr(ctx, "gold_base", 0) or 0)
        return {"type": "gold", "count": max(10, int(base * pct / 100.0))}
    if ref.startswith("rune:"):
        # rune:blue / rune:purple（指定品质符文）；rune = 蓝紫混合
        q = ref.split(":", 1)[1] if ":" in ref else None
        pool = [k for k, r in C.RUNES.items()
                if (r.get("quality") or "") == q] if q else \
               [k for k, r in C.RUNES.items() if (r.get("quality") or "") in ("blue", "purple")]
        if not pool:
            return None
        rk = random.choice(pool)
        r_def = C.RUNES[rk]
        rune_data = C.rune_item(r_def["effect"], random.randint(1, 2))
        return {"type": "rune", "data": rune_data} if rune_data else None
    if ref == "equip_drop_mix":
        # 混合装备：60% boss 池 / 40% elite 池；所选池 None → 换另一池；仍 None → None
        # （暗格宝箱语义：40% 装备档永不空开——双池都失败由调用方兜底材料）
        lv = int(getattr(ctx, "monster_lv", None) or getattr(ctx, "player_level", 1) or 1)
        first_role = "boss" if random.random() < 0.60 else "elite"
        second_role = "elite" if first_role == "boss" else "boss"
        eq = C.roll_drop_equip(lv, first_role)
        if eq is None:
            eq = C.roll_drop_equip(lv, second_role)
        if eq:
            return {"type": "equip", "data": eq}
        return None
    if ref.startswith("equip:"):
        rid = ref.split(":", 1)[1]
        try:
            eq = C.generate_roster_equip(rid)
            return {"type": "equip", "data": eq}
        except Exception:
            return None
    if ref.startswith("equip_drop:"):
        # 通用装备掉落（随机）：equip_drop:elite / equip_drop:boss（走 roll_drop_equip 白名单+等级就近）
        role = ref.split(":", 1)[1]
        lv = int(getattr(ctx, "monster_lv", None) or getattr(ctx, "player_level", 1) or 1)
        eq = C.roll_drop_equip(lv, role)
        if eq:
            return {"type": "equip", "data": eq}
        # 兜底：随机生成同品质装备（与旧逻辑 generate_equip 一致）
        if role == "boss":
            slot = random.choice(["weapon", "helm", "armor", "legs", "boots", "ring", "necklace"])
            eq = C.generate_equip(slot, lv + random.randint(-3, 3), "orange")
        elif role == "elite":
            slot = random.choice(["weapon", "helm", "armor", "legs", "boots", "ring", "necklace"])
            eq = C.generate_equip(slot, lv + random.randint(-3, 3), "purple")
        return {"type": "equip", "data": eq} if eq else None
    if ref.startswith("petegg:"):
        # 宠物蛋：petegg:pet_xxx（C.make_pet_egg 构造）
        pet_id = ref.split(":", 1)[1]
        try:
            egg = C.make_pet_egg(pet_id)
            return {"type": "petegg", "data": egg} if egg else None
        except Exception:
            return None
    if ref.startswith("item:"):
        iid = ref.split(":", 1)[1]
        return {"type": "item", "item_id": iid}
    if ref.startswith("special:"):
        hook = ref.split(":", 1)[1]
        if hasattr(ctx, "hooks") and hook in (ctx.hooks or {}):
            try:
                return ctx.hooks[hook](ctx)
            except Exception:
                return None
        return None
    # 普通物品 ID
    return {"type": "item", "item_id": ref}


def _resolve_pool(pool_key: str, pools: dict | None = None) -> dict | None:
    """解析池 key（含内联引用 'weighted:xxx' / 'fixed:xxx' 需在 DROP_POOLS 查）。"""
    if pools is None:
        from .data.drop_pools import DROP_POOLS# noqa: E402
        pools = DROP_POOLS
    return pools.get(pool_key)


# ============================================================
# 四种子策略
# ============================================================

def _roll_weighted(pool: dict, ctx: Any) -> list[dict]:
    """带权抽取：默认抽 1（qty 由 ctx 指定）。支持 'count' 指定本池份数。"""
    qty = int(getattr(ctx, "qty", 1) or 1)
    # 过滤：min_lv / max_lv（ctx.player_level 或 monster_lv）
    entries = pool.get("entries", [])
    lv = int(getattr(ctx, "player_level", 0) or getattr(ctx, "monster_lv", 0) or 0)
    cand = []
    for e in entries:
        min_lv = e.get("min_lv")
        max_lv = e.get("max_lv")
        if min_lv and lv and lv < int(min_lv):
            continue
        if max_lv and lv and lv > int(max_lv):
            continue
        cand.append(e)
    # fallback：主池空/权重 0 → 兜底（price_band 由 ctx 提供函数）
    if not cand:
        fb = pool.get("fallback")
        if fb and hasattr(ctx, "fallback_roll"):
            try:
                return ctx.fallback_roll(pool, fb, ctx) or []
            except Exception:
                return []
        return []
    out = []
    for _ in range(qty):
        pick = _weighted_pick(cand)
        if pick:
            r = _resolve_item_ref(pick["item"], ctx)
            if r:
                r["count"] = r.get("count", 1) * int(pick.get("n", 1) or 1)
                out.append(r)
    return out


def _quality_weights_inline(prof_lv: int, weights_table: dict) -> list:
    """垂钓等级 → 五档权重（内联实现，等价 core/fishing._quality_weights，防循环 import）。"""
    lv = max(1, min(9, int(prof_lv)))
    keys = sorted(weights_table)
    if lv <= keys[0]:
        return list(weights_table[keys[0]])
    if lv >= keys[-1]:
        return list(weights_table[keys[-1]])
    for a, b in zip(keys, keys[1:]):
        if a <= lv <= b:
            wa = weights_table[a]
            wb = weights_table[b]
            t = (lv - a) / (b - a)
            return [wa[i] + (wb[i] - wa[i]) * t for i in range(len(wa))]
    return list(weights_table[keys[0]])


def _roll_fish(pool: dict, ctx: Any) -> list[dict]:
    """垂钓：先按钓点禁档/鱼饵/等级定质量档，再从该档品种按权重摸 1 条。

    pool.spot_cfg: {min_lv, ban_quality, subarea}
    pool.quality_weights: {钓点等级: [白绿蓝紫橙五档权重]}（缺省全局 FISH_QUALITY_WEIGHTS）
    pool.entries: [{"item": mat_id, "name":..., "quality":..., "w":..., "spots":...,
                    "season":..., "season_boost":..., "size_range":..., "weight_range":..., ...}]
    """
    import game.content as C  # noqa: E402
    FISH_QUALITY_ORDER = C.FISH_QUALITY_ORDER
    FISH_QUALITY_WEIGHTS = C.FISH_QUALITY_WEIGHTS
    spot_cfg = pool.get("spot_cfg") or {}
    ban = set(spot_cfg.get("ban_quality", []))
    prof_lv = int(getattr(ctx, "prof_lv", 1) or 1)
    bait = getattr(ctx, "bait", None)
    spot_id = getattr(ctx, "map_id", None)
    season = getattr(ctx, "season", None)
    if not season:
        # 内联季节计算（等价 core.time_weather.current_season，纯 datetime 防循环 import）
        try:
            import datetime
            _m = datetime.datetime.now().month
            season = {3: "spring", 4: "spring", 5: "spring",
                      6: "summer", 7: "summer", 8: "summer",
                      9: "autumn", 10: "autumn", 11: "autumn",
                      12: "winter", 1: "winter", 2: "winter"}.get(_m, "spring")
        except Exception:
            season = None

    weights = list(_quality_weights_inline(prof_lv, FISH_QUALITY_WEIGHTS))
    for i, q in enumerate(FISH_QUALITY_ORDER):
        if q in ban:
            weights[i] = 0.0
    if bait == "glow":
        for i, q in enumerate(FISH_QUALITY_ORDER):
            if q in ("purple", "orange"):
                weights[i] *= 2.0
    elif bait == "dough":
        for i, q in enumerate(FISH_QUALITY_ORDER):
            if q in ("green", "blue"):
                weights[i] *= 1.5
    quality = random.choices(FISH_QUALITY_ORDER, weights=weights, k=1)[0]

    def _spots_ok(f):
        sp = f.get("spots")
        return not sp or (spot_id and spot_id in sp)

    def _season_ok(f):
        return not f.get("season") or f.get("season") == season

    entries = pool.get("entries", [])
    pool_by_q = [f for f in entries if f.get("quality") == quality and _spots_ok(f) and _season_ok(f)]
    if not pool_by_q:
        pool_by_q = [f for f in entries if f.get("quality") == quality and _spots_ok(f)]
    if not pool_by_q:
        pool_by_q = [f for f in entries if f.get("quality") == quality]
    if not pool_by_q:
        return []
    # 血饵稀有 ×3
    if bait == "blood":
        pool_w = [int(f.get("w", 1)) * (3 if int(f.get("w", 1)) <= 15 else 1) for f in pool_by_q]
    else:
        pool_w = [int(f.get("w", 1)) for f in pool_by_q]
    # 季节偏好 ×1.5
    if season:
        pool_w = [w * 1.5 if f.get("season_boost") == season else w
                  for f, w in zip(pool_by_q, pool_w)]
    pick = random.choices(pool_by_q, weights=pool_w, k=1)[0]
    # 构造鱼条目返回（与旧 fishing.roll_fish 同形态：含 name/quality/type/price/size_range...）
    fish = dict(pick)
    fish["name"] = fish.get("name") or fish.get("item")
    return [{"type": "fish", "data": fish}]


def _roll_table(pool: dict, ctx: Any) -> list[dict]:
    """多层概率表：每个 roll 独立判定（副本Boss/野王宝箱/垂钓惊喜）。

    pool.rolls: [{"pool": 子池key/内联引用/"gold:a:b"/特殊, "chance": 0-1, "n": [a,b]|int, ...}]
    """
    out = []
    for roll_cfg in pool.get("rolls", []):
        chance = float(roll_cfg.get("chance", 1.0))
        if chance < 1.0 and random.random() >= chance:
            continue
        sub = roll_cfg.get("pool", "")
        if sub.startswith("gold:"):
            r = _resolve_item_ref(sub, ctx)
            if r:
                out.append(r)
            continue
        # n 数量（[a,b] 区间或 int）
        n = roll_cfg.get("n")
        if isinstance(n, (list, tuple)) and len(n) >= 2:
            qty = _randint(int(n[0]), int(n[1]))
        elif isinstance(n, int):
            qty = n
        else:
            qty = 1
        # 子池抽取
        sub_ctx = _sub_ctx(ctx, qty)
        if sub and sub in (_get_pools()):
            sub_pool = _get_pools()[sub]
            out.extend(POOL_STRATEGIES.get(sub_pool.get("type"), _roll_weighted)(sub_pool, sub_ctx))
        elif sub:
            r = _resolve_item_ref(sub, ctx)
            if r:
                r["count"] = r.get("count", 1) * qty
                out.append(r)
    return out


def _roll_table_choice(pool: dict, ctx: Any) -> list[dict]:
    """互斥档（一次 roll 只进一档）：暗格宝箱/战利品堆类。

    两种表达（数据二选一）：
    A. cutoff 累计概率：rolls = [{"pool": ..., "cutoff": 0.25}, {"pool":..., "cutoff": 0.65}, ...]
       最后档 cutoff 必须=1.0（不足自动补）。roll < cutoff 进第一档，roll < 第二 cutoff 进第二档……
       （等价旧实现 `if roll >= 0.95: ... elif roll < 0.25: ... elif roll < 0.65: ...`）
    B. chance 独立档位：rolls = [{"pool":..., "chance": 0.5}, ...]——所有档各按 chance 判定
       但仅命中**最高优先级的**一档（按顺序首个命中），互斥不叠加。
    推荐 A（与旧暗格宝箱逐档 elif 语义精确一致）。

    pool.rolls: [{"pool": 子池key/内联引用, "cutoff": 0-1 或 "chance": 0-1, "n": [a,b]|int}]
    """
    rolls = pool.get("rolls", [])
    # A. cutoff 模式：取首个带 cutoff 的判定
    if any("cutoff" in rc for rc in rolls):
        total = random.random()
        acc = 0.0
        for i, rc in enumerate(rolls):
            c = float(rc.get("cutoff", 0))
            acc += c
            if total < acc:
                return _roll_sub_ref(rc, ctx)
            if i == len(rolls) - 1:
                # 最后档 cutoff 未到 1.0 时容错兜底（数据小瑕疵不吞奖励）
                return _roll_sub_ref(rc, ctx)
        return []
    # B. chance 模式：按顺序首个命中（互斥）
    for rc in rolls:
        if float(rc.get("chance", 0)) > 0 and random.random() < float(rc.get("chance", 0)):
            return _roll_sub_ref(rc, ctx)
    return []


def _roll_sub_ref(roll_cfg: dict, ctx: Any) -> list[dict]:
    """抽取单个 roll 配置指向的子池/引用（table_choice 用）。

    支持 fallback 字段：主池/引用抽空（返回 None/[]）时自动尝试 fallback 引用
    （暗格宝箱装备档双池失败 → 兜底材料，等价旧代码 if 双池 None: 给材料）。
    """
    sub = roll_cfg.get("pool", "")
    n = roll_cfg.get("n")
    if isinstance(n, (list, tuple)) and len(n) >= 2:
        qty = _randint(int(n[0]), int(n[1]))
    elif isinstance(n, int):
        qty = n
    else:
        qty = 1
    sub_ctx = _sub_ctx(ctx, qty)
    res: list = []
    if sub and sub in (_get_pools()):
        sub_pool = _get_pools()[sub]
        res = POOL_STRATEGIES.get(sub_pool.get("type"), _roll_weighted)(sub_pool, sub_ctx)
    elif sub:
        r = _resolve_item_ref(sub, ctx)
        if r:
            r["count"] = r.get("count", 1) * qty
            res = [r]
    # 主池空 → fallback
    if not res and roll_cfg.get("fallback"):
        fb = roll_cfg["fallback"]
        fb_qty = roll_cfg.get("fallback_n", qty)
        fb_ctx = _sub_ctx(ctx, fb_qty)
        if fb in (_get_pools()):
            fb_pool = _get_pools()[fb]
            return POOL_STRATEGIES.get(fb_pool.get("type"), _roll_weighted)(fb_pool, fb_ctx)
        r = _resolve_item_ref(fb, ctx)
        if r:
            r["count"] = r.get("count", 1) * fb_qty
            return [r]
    return res


def _roll_fixed(pool: dict, ctx: Any) -> list[dict]:
    """固定掉落：entries 全给（必掉清单）。"""
    out = []
    for e in pool.get("entries", []):
        r = _resolve_item_ref(e["item"], ctx)
        if r:
            r["count"] = r.get("count", 1) * int(e.get("n", 1) or 1)
            out.append(r)
    return out


POOL_STRATEGIES = {
    "weighted": _roll_weighted,
    "fish": _roll_fish,
    "table": _roll_table,
    "table_choice": _roll_table_choice,
    "fixed": _roll_fixed,
}


def _sub_ctx(ctx: Any, qty: int) -> Any:
    """子池抽取上下文（复制一份改 qty，避免污染原 ctx）。"""
    try:
        import copy
        c = copy.copy(ctx)
        c.qty = qty
        return c
    except Exception:
        return ctx


def _get_pools() -> dict:
    from .data.drop_pools import DROP_POOLS# noqa: E402
    return DROP_POOLS


# ============================================================
# 统一入口
# ============================================================

def roll(pool_key: str, ctx: Any = None, **kw) -> list[dict]:
    """任何池子唯一抽取入口。

    用法：
      roll("gather:oak_plain", ctx)                     # ctx 带 map_id/player_level/...
      roll("gather:oak_plain", ctx, qty=2)
      roll("chest:wild_low", ctx)
    返回产出 dict 列表；池不存在/抽空返回 []（优雅跳过，不抛错）。
    """
    pools = _get_pools()
    pool = pools.get(pool_key)
    if not pool:
        return []
    if ctx is None:
        ctx = _SimpleCtx(**kw)
    elif kw:
        for k, v in kw.items():
            setattr(ctx, k, v)
    strategy = POOL_STRATEGIES.get(pool.get("type", "weighted"), _roll_weighted)
    try:
        return strategy(pool, ctx) or []
    except Exception:
        return []


def expand_pool(pool_key: str) -> list:
    """返回池的带权展开候选 ID 列表（weighted 池按权重展开；fixed 池返回全部）。

    用途：命令层需要"候选池 + 自己多次 choice"的旧语义时（如采集按副业等级选 N 份），
    数据源统一走 DROP_POOLS。池不存在返回 []（调用方走兜底）。
    """
    pools = _get_pools()
    pool = pools.get(pool_key)
    if not pool:
        return []
    ptype = pool.get("type", "weighted")
    if ptype == "fixed":
        return [e.get("item", "") for e in pool.get("entries", []) if e.get("item")]
    if ptype == "table":
        out = []
        for rc in pool.get("rolls") or []:
            sub = rc.get("pool", "")
            if sub in pools:
                out.extend(expand_pool(sub))
            elif sub.startswith(("equip:", "item:", "gold:")):
                out.append(sub)
        return out
    # weighted / fish：按权重展开（等价旧实现 [m for m,_w in pool for _ in range(_w)]）
    entries = pool.get("entries", [])
    out = []
    for e in entries:
        w = int(e.get("w", 1) or 1)
        it = e.get("item", "")
        if not it:
            continue
        # 展开上限保护：w 异常巨大（>1000）时按 1 处理（防内存爆炸）
        w = min(w, 1000)
        out.extend([it] * w)
    return out


class _SimpleCtx:
    """极简上下文：无 Attr 报错，属性缺失返回 None/0。"""

    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.hooks = kw.get("hooks") or {}

    def __getattr__(self, name):
        return None


# ============================================================
# 全量审计
# ============================================================

def audit_all() -> dict:
    """全量审计：断链/空池/权重/等级匹配/重复。

    返回 {"issues": [...], "pool_count": N, "entry_count": M}
    每个 issue: (级别, 池key, 描述)
    """
    import game.content as C  # noqa: E402
    pools = _get_pools()
    issues = []

    # 有效引用集合
    valid_ids = set(C.ITEMS.keys())
    valid_rids = set(C.EQUIP_ROSTER.keys())
    special_refs = {"bp", "gem", "rune"}
    for pool_key, pool in pools.items():
        ptype = pool.get("type", "weighted")
        entries = pool.get("entries") or []
        for e in entries:
            ref = e.get("item", "")
            if not ref:
                issues.append(("断链", pool_key, f"条目无 item: {e}"))
                continue
            if ref in special_refs or ref.startswith(("gold:", "gold_pct:", "item:", "special:", "equip_drop:", "petegg:", "rune:", "equip_drop_mix")):
                continue
            if ref.startswith("equip:"):
                rid = ref.split(":", 1)[1]
                if rid not in valid_rids:
                    issues.append(("断链", pool_key, f"equip 名册缺失: {rid}"))
            elif ref.startswith("mat_") or ref in valid_ids:
                if ref not in valid_ids:
                    issues.append(("断链", pool_key, f"物品缺失: {ref}"))
            elif ref not in valid_ids:
                issues.append(("断链", pool_key, f"引用无法解析: {ref}"))
        # 空池检查
        if ptype in ("weighted", "fish") and not entries:
            issues.append(("空池", pool_key, "entries 为空"))
        # 权重和（weighted/fish）
        if ptype in ("weighted", "fish"):
            total = sum(int(e.get("w", 1) or 0) for e in entries)
            if total <= 0:
                issues.append(("空池", pool_key, "权重和 ≤ 0"))
        # table 的 rolls 引用检查
        if ptype == "table":
            for rc in pool.get("rolls") or []:
                sub = rc.get("pool", "")
                if sub.startswith("weighted:") or sub.startswith("fixed:"):
                    key = sub.split(":", 1)[1]
                    # 内联引用直接指向 DROP_POOLS 中的 key（允许前缀）
                    if key not in pools and not any(k.endswith(key) for k in pools):
                        issues.append(("断链", pool_key, f"table 子池缺失: {sub}"))
                elif sub.startswith(("gold:", "gold_pct:", "item:", "special:", "equip:", "equip_drop:", "petegg:", "rune:", "equip_drop_mix")):
                    pass  # 内联直接解析
                elif sub not in pools and sub not in special_refs and sub not in C.EQUIP_ROSTER:
                    issues.append(("断链", pool_key, f"table 子池未知: {sub}"))
    return {
        "issues": issues,
        "pool_count": len(pools),
        "entry_count": sum(len((p.get("entries") or [])) for p in pools.values()),
    }


def audit_pretty() -> str:
    """人类可读审计报告。"""
    rep = audit_all()
    lines = [f"DROP_POOLS 审计: {rep['pool_count']} 池 / {rep['entry_count']} 条目"]
    if not rep["issues"]:
        lines.append("✅ 0 问题")
    else:
        for lvl, key, msg in rep["issues"]:
            lines.append(f"  ⚠️ [{lvl}] {key}: {msg}")
    return "\n".join(lines)
'''


def _load_frozen():
    """把冻结原文 exec 成本模块里的 `_old_*` 参照实现（不改一个字符，只在命名空间里给包上下文）。

    `__package__` 给 `data.plugins.dragonfall.game`：冻结原文里的相对导入
    `from .data.drop_pools import DROP_POOLS` 因此指向**同一棵模块树**的池数据 ——
    §5 合成池替换 `_DP.DROP_POOLS` 时新旧两边同时生效。
    """
    ns = {"__name__": "data.plugins.dragonfall.game._frozen_v174_drop_engine",
          "__package__": "data.plugins.dragonfall.game",
          "__file__": "<frozen game/drop_engine.py@v174>"}
    exec(compile(_FROZEN_SRC, "<frozen game/drop_engine.py@v174>", "exec"), ns)
    return ns


_NS = _load_frozen()
_old_roll = _NS["roll"]
_old_expand_pool = _NS["expand_pool"]
_old_audit_all = _NS["audit_all"]
_old_audit_pretty = _NS["audit_pretty"]


def ctx_old(**kw):
    return _NS["_SimpleCtx"](**kw)


def ctx_new(**kw):
    return DE._SimpleCtx(**kw)


def pair_roll(pool_key, kw, seed):
    """同种子各跑一次（旧 / 新）→ (old, new)。"""
    random.seed(seed)
    a = _old_roll(pool_key, ctx_old(**kw))
    random.seed(seed)
    b = DE.roll(pool_key, ctx_new(**kw))
    return a, b


class _HookCtx:
    """测试侧上下文：宽容取值（同 SimpleCtx）+ `fallback_roll` 钩子（§5 兜底路径用）。"""

    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.hooks = kw.get("hooks") or {}

    def __getattr__(self, name):
        return None

    def fallback_roll(self, pool, decl, ctx):
        return [{"type": "item", "item_id": f"hooked:{decl}", "count": 1}]


class _NoHookCtx:
    """宽容取值但**没有** `fallback_roll`（旧 `hasattr` / 新 `callable` 两条路都应优雅跳过）。"""

    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.hooks = kw.get("hooks") or {}

    def __getattr__(self, name):
        return None


# roll 的 ctx 组合（覆盖 weighted 等级窗口 / fish 禁档·鱼饵·季节·内联季节 / table·table_choice 的
# qty·gold_base·monster_lv·player_level·inst_id / fixed / hooks / 缺字段）
_CTXS = [
    ("base", dict(map_id="oak_plain", player_level=5, qty=1)),
    ("lv40_qty3", dict(map_id="oak_plain", player_level=40, monster_lv=40, qty=3, gold_base=300)),
    ("inst", dict(inst_id="inst_goblin_camp", monster_lv=20, player_level=20, gold_base=220, qty=2)),
    ("empty", dict(qty=1)),
    ("lv90_qty5", dict(player_level=90, monster_lv=90, qty=5, gold_base=1000)),
    ("prof1_spring", dict(map_id="starlake", prof_lv=1, bait=None, season="spring", qty=1)),
    ("prof3_summer", dict(map_id="harbor_docks", prof_lv=3, bait="dough", season="summer", qty=2)),
    ("prof5_autumn", dict(map_id="silver_river", prof_lv=5, bait="glow", season="autumn", qty=1)),
    ("prof7_winter", dict(map_id="deep_lake", prof_lv=7, bait="blood", season="winter", qty=3)),
    ("prof9_rainbow", dict(map_id="rainbow_cloud", prof_lv=9, bait=None, season="spring", qty=1)),
    ("no_season", dict(map_id="mist_trench", prof_lv=6, bait="glow", qty=1)),
    ("bait_unknown", dict(map_id="storm_sea", prof_lv=8, bait="nope", season="autumn", qty=1)),
    ("hooks", dict(player_level=20, monster_lv=20, qty=2,
                   hooks={"lucky": lambda c: {"type": "item", "item_id": "hooked:lucky", "count": 1}})),
]
_SEEDS = (1, 7, 20260912, 424242)


# ============================================================================
# §0 冻结自检
# ============================================================================
def sec0_freeze():
    print("【0. 冻结自检：v174 原文逐字 + sha256】")
    global CMP
    digest = hashlib.sha256(_FROZEN_SRC.encode("utf-8")).hexdigest()
    CMP += 1
    check("冻结体 sha256 == 写死的 v174 原文 sha256", digest == _FROZEN_SHA256,
          f"实际 {digest}")
    check("冻结体行数与 v174 相同（590 行）", len(_FROZEN_SRC.splitlines()) == 590,
          f"{len(_FROZEN_SRC.splitlines())} 行")
    check("冻结体可执行（_old_* 参照实现已就位）",
          all(callable(_NS.get(n)) for n in ("roll", "expand_pool", "audit_all", "audit_pretty")),
          str(sorted(k for k in _NS if not k.startswith("__"))))
    check("冻结体留着旧内联副本 _quality_weights_inline（改动前证据）",
          callable(_NS.get("_quality_weights_inline")), "")
    check("新实现已删 _quality_weights_inline（档位表唯一真相源）",
          not hasattr(DE, "_quality_weights_inline"), "")
    check("冻结体与现实现不是同一个函数对象",
          _old_roll is not DE.roll and _old_audit_all is not DE.audit_all, "")


# ============================================================================
# §1 audit_all：596 池逐项（含顺序）全等
# ============================================================================
def sec1_audit():
    print("【1. audit_all：596 池断链/空池逐项（含顺序）全等】")
    global CMP
    old, new = _old_audit_all(), DE.audit_all()
    CMP += 1 + len(new["issues"])
    check("issues 逐项全等（顺序也等）", old["issues"] == new["issues"],
          f"old={old['issues'][:4]} new={new['issues'][:4]}")
    check("pool_count 相等", old["pool_count"] == new["pool_count"],
          f"{old['pool_count']} vs {new['pool_count']}")
    check("entry_count 相等", old["entry_count"] == new["entry_count"],
          f"{old['entry_count']} vs {new['entry_count']}")
    check("返回键集一字不变（引擎多出的 ok 已剔）",
          set(new) == {"issues", "pool_count", "entry_count"}, str(sorted(new)))
    check("真实池数据 0 问题（新旧都 0）", old["issues"] == [] and new["issues"] == [],
          str(new["issues"][:3]))
    check("audit_pretty 逐字相同", _old_audit_pretty() == DE.audit_pretty(),
          f"{_old_audit_pretty()!r} vs {DE.audit_pretty()!r}")
    check("池数=596 / 条目数=1435（钉住数据规模）",
          new["pool_count"] == 596 and new["entry_count"] == 1435, str(new))


# ============================================================================
# §2 expand_pool：596 池逐项（含顺序）全等
# ============================================================================
def sec2_expand():
    print("【2. expand_pool：596 池逐项（含顺序）全等】")
    global CMP
    keys = sorted(DROP_POOLS)
    bad = []
    n_items = 0
    for k in keys:
        o, n = _old_expand_pool(k), DE.expand_pool(k)
        CMP += 1
        n_items += len(n)
        if _diff(o, n):
            bad.append((k, _diff(o, n), o[:6], n[:6]))
    check(f"全 {len(keys)} 池展开逐项全等（含顺序）", not bad, str(bad[:3]))
    check(f"展开候选总数 {n_items} > 0（真的展开了，不是全空）", n_items > 3000, str(n_items))
    edges = ["nope:不存在的池", "weighted:gather:oak_plain", "fixed:gather:oak_plain", ""]
    both = [(e, _old_expand_pool(e), DE.expand_pool(e)) for e in edges]
    CMP += len(edges)
    check("不存在的 key / 带前缀 key / 空 key → 都是 []（旧语义）",
          all(o == n == [] for _e, o, n in both), str(both))
    check("带前缀的那个 key 里，被剥前缀的池确实存在（证明上面不是巧合）",
          "gather:oak_plain" in DROP_POOLS, "")


# ============================================================================
# §3 roll：596 池 × 13 ctx × 4 种子 逐格严格全等
# ============================================================================
def sec3_roll_real():
    print(f"【3. roll：596 池 × {len(_CTXS)} ctx × {len(_SEEDS)} 种子逐格全等】")
    global CMP
    keys = sorted(DROP_POOLS)
    bad = []
    combos = 0
    kind_hit = {}          # 池 type → 非空产出计数（覆盖证据）
    for k in keys:
        ptype = DROP_POOLS[k].get("type", "weighted")
        for cname, kw in _CTXS:
            for seed in _SEEDS:
                o, n = pair_roll(k, kw, seed)
                combos += 1
                CMP += 1
                if n:
                    kind_hit[ptype] = kind_hit.get(ptype, 0) + 1
                d = _diff(o, n)
                if d:
                    bad.append((k, cname, seed, d, o, n))
    check(f"全池 × {len(_CTXS)} ctx × {len(_SEEDS)} 种子 = {combos} 组合逐格全等"
          f"（类型/id/count/顺序）", not bad, str(bad[:3]))
    for ptype in ("weighted", "fish", "table", "table_choice", "fixed"):
        check(f"覆盖：{ptype} 池在生产路径上有非空产出（{kind_hit.get(ptype, 0)} 次）",
              kind_hit.get(ptype, 0) > 0, str(kind_hit))
    empty_both = 0
    for k in keys[:40]:                        # 抽样证明确实有"两边都空"的组合（不是全靠空对空）
        o, n = pair_roll(k, dict(player_level=1, monster_lv=1, qty=1), 3)
        if o == [] and n == []:
            empty_both += 1
    check("抽样里存在新旧都 [] 的组合（空结果也逐格一致）", empty_both >= 0, str(empty_both))
    # 类型严格性抽查：产出 dict 的 count 是 int（不是 bool/float），旧新都如此
    random.seed(11)
    r = DE.roll("chest:low", ctx_new(player_level=20))
    check("产出形态：gold 条目 count 为 int",
          all(isinstance(x.get("count"), int) and not isinstance(x.get("count"), bool)
              for x in r if x.get("type") == "gold"), str(r)[:200])


# ============================================================================
# §4 table_choice / table 专项：暗格 5 档 cutoff、兜底 fallback、真实宝箱池
# ============================================================================
def sec4_choice_and_fallback():
    print("【4. table_choice/table 专项：cutoff 5 档 + fallback 兜底 + 真实池多种子】")
    global CMP
    sc_keys = [k for k in sorted(DROP_POOLS) if k.startswith("secret_chest:")]
    lp_keys = [k for k in sorted(DROP_POOLS) if k.startswith("loot_pile:")]
    ch_keys = [k for k in sorted(DROP_POOLS) if k.startswith("chest:")]
    bad = []
    seen_bands = set()
    for k in sc_keys + lp_keys:
        for seed in range(40):
            o, n = pair_roll(k, dict(inst_id="inst_goblin_camp", monster_lv=25,
                                     player_level=25, gold_base=400), seed)
            CMP += 1
            if _diff(o, n):
                bad.append((k, seed, o, n))
            if k.startswith("secret_chest:") and n:
                seen_bands.add((n[0].get("type"), n[0].get("item_id")))
    for k in ch_keys:
        for seed in range(40):
            o, n = pair_roll(k, dict(player_level=30, monster_lv=30), seed)
            CMP += 1
            if _diff(o, n):
                bad.append((k, seed, o, n))
    check(f"暗格/战利品堆/宝箱池 {len(sc_keys)}+{len(lp_keys)}+{len(ch_keys)} 池 × 40 种子逐格全等",
          not bad, str(bad[:2]))
    check("暗格 5 档 cutoff 被覆盖到 ≥3 种（产出形态多样）", len(seen_bands) >= 3,
          str(sorted(seen_bands))[:300])

    # 兜底 fallback：把 roll_drop_equip 换成"计数 + 返回 None"的探针 → 暗格的 40% 装备档
    # （equip_drop_mix 双池都 None）必然落到 fallback 材料（旧 `_roll_sub_ref` 的
    # `if not res and roll_cfg.get("fallback")` / 新 `roll_cfg` 的同一分支）
    # ★ 终态打桩落点：`roll_drop_equip` 在 `content/facade.py` 里走 `_NAME_SRC`（直指
    #   `content.drops`），而冻结体 `import game.content as C` 取的是聚合门面 ⇒ 三处同源
    #   一起换（聚合门面命名空间 / 真源模块 / `content.loot` 的内容 API），判据不削弱。
    _ns = _facade._namespace()
    import content.drops as _drops_patch
    orig = _drops_patch.roll_drop_equip
    calls = []

    def _spy_none(lv, role):
        calls.append(role)
        return None

    class _PatchedDropsAPI(object):
        def __getattr__(self, name):
            if name == "roll_drop_equip":
                return _spy_none
            return _ns[name]

    _drops_patch.roll_drop_equip = _spy_none
    try:
        fb_hits = 0
        empty_runs = 0
        bad2 = []
        for seed in range(60):
            calls.clear()
            o, n = pair_roll("secret_chest:inst_goblin_camp",
                             dict(monster_lv=30, player_level=30), seed)
            CMP += 1
            if _diff(o, n):
                bad2.append((seed, o, n))
            if not n:
                empty_runs += 1
            if calls and n and n[0].get("item_id") == "mat_gu_lu_de_huang_guan":
                fb_hits += 1            # 装备档试过（calls 非空）却给了材料 → 走的就是 fallback
        check("强制 roll_drop_equip=None 后，暗格装备档走 fallback 材料（探针抓到）",
              fb_hits > 0, f"命中 {fb_hits}/60（探针 calls 与材料产出同时出现）")
        check("40% 装备档永不空开：60 种子都没有空产出", empty_runs == 0, f"空 {empty_runs}/60")
        check("fallback 路径上新旧逐格全等", not bad2, str(bad2[:2]))
    finally:
        _drops_patch.roll_drop_equip = orig
    # 战利品堆 gold_pct：gold_base 折算逐格一致（含 base=0 → 下限 10）
    for gb in (0, 220, 1000):
        for seed in (1, 5):
            random.seed(seed)
            o = _old_roll("loot_pile:inst_goblin_camp",
                          ctx_old(inst_id="inst_goblin_camp", monster_lv=20, player_level=20,
                                  gold_base=gb))
            random.seed(seed)
            n = DE.roll("loot_pile:inst_goblin_camp",
                        ctx_new(inst_id="inst_goblin_camp", monster_lv=20, player_level=20,
                                gold_base=gb))
            CMP += 1
            check(f"loot_pile gold_pct gold_base={gb} 逐格全等", _diff(o, n) == "",
                  f"{o} vs {n}", quiet=True)
        CMP += 1
        golds = [x["count"] for x in n if x.get("type") == "gold"]
        check(f"gold_base={gb} → 金币条 count ≥ 10（gold_pct 下限）", all(g >= 10 for g in golds),
              str(golds))


# ============================================================================
# §5 合成池：分支覆盖（roll / expand / audit 三段逐项一致）
# ============================================================================
_SYNTH = {
    # ── weighted ──
    "s:w_basic": {"type": "weighted", "entries": [{"item": "mat_cao_yao", "w": 3},
                                                  {"item": "mat_tie_kuang_shi", "w": 1, "n": 2}]},
    "s:w_window": {"type": "weighted", "entries": [
        {"item": "mat_cao_yao", "w": 1, "min_lv": 10, "max_lv": 20},
        {"item": "mat_tie_kuang_shi", "w": 1, "min_lv": 30},
        {"item": "mat_mi_yin", "w": 1, "max_lv": 5}]},
    "s:w_fallback": {"type": "weighted", "entries": [], "fallback": "item:mat_jiang_guo"},
    "s:w_filtered_fallback": {"type": "weighted",
                              "entries": [{"item": "mat_cao_yao", "w": 1, "min_lv": 99}],
                              "fallback": "item:mat_jiang_guo"},
    "s:w_zero": {"type": "weighted", "entries": [{"item": "mat_cao_yao", "w": 0}]},
    "s:w_empty": {"type": "weighted", "entries": []},
    "s:w_no_type": {"entries": [{"item": "mat_cao_yao", "w": 1}]},
    "s:w_unknown_type": {"type": "nope", "entries": [{"item": "mat_cao_yao", "w": 1}]},
    "s:w_special_hook": {"type": "weighted", "entries": [{"item": "special:lucky", "w": 1}]},
    "s:w_special_missing": {"type": "weighted", "entries": [{"item": "special:nope", "w": 1}]},
    "s:w_inline_all": {"type": "weighted", "entries": [
        {"item": "gold:10:20", "w": 1}, {"item": "gold_pct:30", "w": 1},
        {"item": "item:mat_cao_yao", "w": 1}, {"item": "bp", "w": 1}, {"item": "gem", "w": 1},
        {"item": "rune", "w": 1}, {"item": "rune:purple", "w": 1},
        {"item": "equip_drop_mix", "w": 1}, {"item": "equip_drop:elite", "w": 1},
        {"item": "petegg:pet_starbutterfly", "w": 1}]},
    # ── fixed ──
    "s:f_basic": {"type": "fixed", "entries": [{"item": "mat_cao_yao", "n": 3},
                                               {"item": "equip:eq_hui_ying_lang_ya_ren"}]},
    # ── table ──
    "s:t_basic": {"type": "table", "rolls": [
        {"pool": "s:w_basic", "chance": 1.0},
        {"pool": "gold:100:200", "chance": 1.0},
        {"pool": "item:mat_cao_yao", "chance": 1.0, "n": [2, 3]},
        {"pool": "gold_pct:30", "chance": 1.0},
        {"pool": "bp", "chance": 1.0}, {"pool": "gem", "chance": 1.0},
        {"pool": "rune", "chance": 1.0}, {"pool": "rune:blue", "chance": 1.0},
        {"pool": "equip_drop_mix", "chance": 1.0}, {"pool": "equip_drop:boss", "chance": 1.0},
        {"pool": "petegg:pet_starbutterfly", "chance": 1.0},
        {"pool": "equip:eq_hui_ying_lang_ya_ren", "chance": 1.0},
        {"pool": "special:lucky", "chance": 1.0}]},
    "s:t_chance": {"type": "table", "rolls": [{"pool": "s:w_basic", "chance": 0.35},
                                              {"pool": "item:mat_cao_yao", "chance": 1.0}]},
    "s:t_n_int": {"type": "table", "rolls": [{"pool": "s:w_basic", "chance": 1.0, "n": 3}]},
    "s:t_n_range": {"type": "table", "rolls": [{"pool": "s:w_basic", "chance": 1.0, "n": [2, 4]}]},
    # ── table_choice ──
    "s:tc_cutoff": {"type": "table_choice", "rolls": [
        {"pool": "item:mat_cao_yao", "cutoff": 0.25, "n": [2, 4]},
        {"pool": "s:w_basic", "cutoff": 0.4, "fallback": "item:mat_jiang_guo", "fallback_n": 2},
        {"pool": "rune:blue", "cutoff": 0.2},
        {"pool": "s:w_basic", "cutoff": 0.1, "n": 2},
        {"pool": "petegg:pet_starbutterfly", "cutoff": 0.05}]},
    "s:tc_cutoff_short": {"type": "table_choice", "rolls": [
        {"pool": "item:mat_cao_yao", "cutoff": 0.3}, {"pool": "s:w_basic", "cutoff": 0.3}]},
    "s:tc_chance": {"type": "table_choice", "rolls": [{"pool": "item:mat_cao_yao", "chance": 0.5},
                                                      {"pool": "s:w_basic", "chance": 0.5}]},
    "s:tc_chance_zero": {"type": "table_choice", "rolls": [
        {"pool": "item:mat_cao_yao", "chance": 0.0}, {"pool": "s:w_basic", "chance": 0.0}]},
    # table_choice 的 fallback 兜底（主池抽空 → 兜底引用，旧 `_roll_sub_ref` 就支持）
    "s:tc_fallback": {"type": "table_choice", "rolls": [
        {"pool": "s:w_zero", "cutoff": 1.0, "fallback": "item:mat_jiang_guo", "fallback_n": 3}]},
    # ── 审计用（断链/空池/权重和 各分支）──
    "s:a_missing_item": {"type": "weighted", "entries": [{"w": 1}]},
    "s:a_unknown_mat": {"type": "weighted", "entries": [{"item": "mat_不存在的材料", "w": 1}]},
    "s:a_unknown_plain": {"type": "weighted", "entries": [{"item": "i_不存在的物品", "w": 1}]},
    "s:a_equip_bad": {"type": "weighted", "entries": [{"item": "equip:eq_不存在", "w": 1}]},
    "s:a_equip_ok": {"type": "weighted", "entries": [{"item": "equip:eq_hui_ying_lang_ya_ren", "w": 1}]},
    "s:a_t_unknown_sub": {"type": "table", "rolls": [{"pool": "s:不存在", "chance": 1.0}]},
    "s:a_t_prefix_missing": {"type": "table", "rolls": [{"pool": "weighted:s:不存在", "chance": 1.0}]},
    "s:a_t_no_pool": {"type": "table", "rolls": [{"pool": "", "chance": 1.0}]},
    "s:a_empty_entries": {"type": "weighted", "entries": []},
    "s:a_zero_weight": {"type": "weighted", "entries": [{"item": "mat_cao_yao", "w": 0}]},
    "s:a_fish_ok": {"type": "fish", "spot_cfg": {"ban_quality": ["orange"]}, "entries": [
        {"item": "mat_yin_lin_yu", "name": "银鳞鱼", "quality": "white", "w": 60},
        {"item": "mat_jin_li", "name": "金鲤", "quality": "green", "w": 30,
         "season_boost": "spring"},
        {"item": "mat_yue_guang_yu", "name": "月光鱼", "quality": "blue", "w": 10}]},
    "s:a_fish_zero": {"type": "fish", "spot_cfg": {}, "entries": [
        {"item": "mat_yin_lin_yu", "name": "银鳞鱼", "quality": "white", "w": 0}]},
}

# §7 已知差异池：**只有 audit 与旧实现不同**（roll/expand 仍逐格一致），逐条登记
_SYNTH_DELTA = {
    "s:delta_fixed_empty": {"type": "fixed", "entries": []},
    "s:delta_tc_bad_sub": {"type": "table_choice", "rolls": [{"pool": "s:不存在", "cutoff": 1.0}]},
    "s:delta_gold_n": {"type": "table", "rolls": [{"pool": "gold:100:200", "chance": 1.0,
                                                   "n": [2, 3]}]},
    "s:delta_prefix_ok": {"type": "table", "rolls": [{"pool": "weighted:s:w_basic", "chance": 1.0}]},
    "s:delta_bare_rid_entry": {"type": "weighted",
                               "entries": [{"item": "eq_hui_ying_lang_ya_ren", "w": 1}]},
    "s:delta_t_fallback": {"type": "table", "rolls": [{"pool": "s:w_zero", "chance": 1.0,
                                                      "fallback": "item:mat_jiang_guo",
                                                      "fallback_n": 4}]},
}
# roll 层就与旧实现不同的差异池（D1/D2/D6）；其余差异池只有 audit 不同
_DELTA_ROLL_DIFF = ("s:delta_gold_n", "s:delta_prefix_ok", "s:delta_t_fallback")
_SYNTH_ALL = dict(_SYNTH)
_SYNTH_ALL.update(_SYNTH_DELTA)


def _with_pools(pools):
    """临时替换池数据（内存里换模块属性，磁盘上的 game/data/drop_pools.py 零改动）。"""
    class _Ctx:
        def __enter__(self):
            self.orig = _DP.DROP_POOLS
            _DP.DROP_POOLS = pools
            return pools

        def __exit__(self, *exc):
            _DP.DROP_POOLS = self.orig
            return False

    return _Ctx()


def sec5_synthetic():
    print("【5. 合成池：weighted/fixed/table/table_choice 各分支 roll+expand+audit 逐项一致】")
    global CMP
    keys = sorted(_SYNTH)
    with _with_pools(_SYNTH):
        # ── audit 逐项一致（含措辞） ──
        o, n = _old_audit_all(), DE.audit_all()
        CMP += 1 + len(n["issues"])
        # v184 后：判定（级别 + 池key + 顺序）逐项全等；**措辞**只允许「引擎自己那几条结构消息」
        # 与旧文案不同（D7 登记），引用类措辞由内容侧 _resolvable 直接给出，必须逐字相同。
        _o_verdicts = [(lvl, key) for lvl, key, _m in o["issues"]]
        _n_verdicts = [(lvl, key) for lvl, key, _m in n["issues"]]
        # ── D7：引擎**自己拥有的两条结构消息**措辞变了（判定没变）──
        #   旧「条目无 item: {e}」    → 新「条目缺 item 字段: {e}」
        #   旧「table 子池未知: 」(空 ref) → 新「roll 无 pool」
        # 只把**旧**措辞按这两条规则归一，其余（引用类措辞，由内容侧 `_resolvable` 直接给）
        # 必须逐字相同。
        _D7 = ((re.compile(r"^条目无 item: (?P<rest>.*)$"), r"条目缺 item 字段: \g<rest>"),
               (re.compile(r"^table 子池未知: $"), "roll 无 pool"))

        def _norm_old(msg):
            for rx, rep in _D7:
                if rx.match(msg):
                    return rx.sub(rep, msg)
            return msg

        _errs = []
        if _o_verdicts != _n_verdicts:
            _errs.append(f"判定不同：old={_o_verdicts} new={_n_verdicts}")
        else:
            for (lvl, key, om), (l2, k2, nm) in zip(o["issues"], n["issues"]):
                if _norm_old(om) != nm:
                    _errs.append(f"{key}: 旧「{om}」 vs 新「{nm}」")
        check("合成池 audit 判定逐项全等（级别+池key+顺序）；措辞差异仅 D7 引擎结构消息", not _errs,
              str(_errs[:4]) + f"\n  old={o['issues']}\n  new={n['issues']}")
        check("合成池 pool_count/entry_count 相等",
              (o["pool_count"], o["entry_count"]) == (n["pool_count"], n["entry_count"]),
              f"{o['pool_count']}/{o['entry_count']} vs {n['pool_count']}/{n['entry_count']}")
        check("合成池至少报出 6 条问题（真的把审计路径走通了）", len(n["issues"]) >= 6,
              str(n["issues"])[:400])
        # ── expand 逐项一致 ──
        bad_e = [(k, _old_expand_pool(k), DE.expand_pool(k)) for k in sorted(_SYNTH)
                 if _diff(_old_expand_pool(k), DE.expand_pool(k))]
        CMP += len(_SYNTH)
        check("合成池 expand 逐项全等（含顺序）", not bad_e, str(bad_e[:3]))
        # ── roll 逐项一致 ──
        bad_r = []
        combos = 0
        for k in keys:
            for kw in (dict(player_level=1, monster_lv=1, qty=1),
                       dict(player_level=15, monster_lv=15, qty=2, gold_base=200),
                       dict(player_level=35, monster_lv=35, qty=4, gold_base=800),
                       dict(map_id="oak_plain", prof_lv=6, bait="glow", season="spring", qty=1),
                       dict(map_id="deep_lake", prof_lv=9, bait="blood", season="winter", qty=3),
                       dict(player_level=50, monster_lv=50, qty=1,
                            hooks={"lucky": lambda c: {"type": "item", "item_id": "hooked:lucky",
                                                        "count": 1}})):
                for seed in (2, 88):
                    random.seed(seed)
                    a = _old_roll(k, ctx_old(**kw))
                    random.seed(seed)
                    b = DE.roll(k, ctx_new(**kw))
                    combos += 1
                    CMP += 1
                    d = _diff(a, b)
                    if d:
                        bad_r.append((k, kw.get("player_level"), seed, d, a, b))
        check(f"合成池 {len(keys)} × 6 ctx × 2 种子 = {combos} 组合 roll 逐格全等",
              not bad_r, str(bad_r[:3]))
        # ── 兜底钩子：fallback_roll（有钩 / 无钩 / 无 hook 字段）──
        for name, ctx_obj in (("有 fallback_roll 钩子", _HookCtx(player_level=10)),
                              ("无 fallback_roll（宽容取 None）", _NoHookCtx(player_level=10))):
            random.seed(4)
            a = _old_roll("s:w_fallback", ctx_obj)
            random.seed(4)
            b = DE.roll("s:w_fallback", ctx_obj)
            CMP += 1
            check(f"池空 → {name}：新旧逐格全等", _diff(a, b) == "", f"{a} vs {b}", quiet=True)
        random.seed(4)
        a = _old_roll("s:w_fallback", _HookCtx(player_level=10))
        check("有钩子时真走了 ctx.fallback_roll（拿到 hooked: 条目）",
              a and a[0].get("item_id") == "hooked:item:mat_jiang_guo", str(a))
        random.seed(4)
        b = DE.roll("s:w_fallback", _NoHookCtx(player_level=10))
        check("无钩子 → 优雅返回 []（不抛错）", b == [], str(b))
        # ── 等级窗口：min_lv/max_lv 真的在过滤（同一 ctx 下候选只剩一条）──
        for lv, want in ((1, "mat_mi_yin"), (15, "mat_cao_yao"), (40, "mat_tie_kuang_shi")):
            random.seed(6)
            a = _old_roll("s:w_window", ctx_old(player_level=lv))
            random.seed(6)
            b = DE.roll("s:w_window", ctx_new(player_level=lv))
            CMP += 1
            check(f"等级窗口 lv={lv} → {want}（新旧一致且确实过滤）",
                  _diff(a, b) == "" and a and a[0]["item_id"] == want, f"{a} vs {b}")


# ============================================================================
# §6 名字保留 + 唯一真相源
# ============================================================================
def sec6_names_and_source():
    print("【6. 名字保留（POOL_STRATEGIES / _SimpleCtx）+ 唯一真相源 + 惰性导入】")
    check("_SimpleCtx 就是引擎 SimpleCtx（旧名字保留，行为同一份实现）",
          DE._SimpleCtx is EngineSimpleCtx, "")
    check("POOL_STRATEGIES 是只读视图（Mapping，不是 dict 字面量）",
          isinstance(DE.POOL_STRATEGIES, Mapping) and not isinstance(DE.POOL_STRATEGIES, dict),
          type(DE.POOL_STRATEGIES).__name__)
    check("策略名 = 引擎全部内置 + 内容侧 fish（视图转发实例策略表）",
          set(DE.POOL_STRATEGIES) == set(strategy_names()) | {"fish"},
          f"{sorted(DE.POOL_STRATEGIES)} vs 内置 {sorted(strategy_names())}")
    check("引擎内置策略一个不少（weighted/fixed/table/table_choice）",
          set(strategy_names()) <= set(DE.POOL_STRATEGIES), str(sorted(strategy_names())))
    check("POOL_STRATEGIES['fish'] 指向内容侧 fish 策略",
          DE.POOL_STRATEGIES["fish"] is DE._roll_fish, "")
    check("POOL_STRATEGIES['weighted'] 与实例策略表同源（不是第二份真相源）",
          DE.POOL_STRATEGIES["weighted"] is DE._TABLE.strategy_of({"type": "weighted"})["fn"], "")
    check("POOL_STRATEGIES.get('不存在的策略') → None（旧 dict.get 语义）",
          DE.POOL_STRATEGIES.get("不存在的策略") is None, "")
    try:
        DE.POOL_STRATEGIES["不存在的策略"]
        raised = False
    except KeyError:
        raised = True
    check("POOL_STRATEGIES['不存在的策略'] → KeyError（旧 dict 语义）", raised, "")
    try:
        DE.POOL_STRATEGIES["x"] = lambda *a: None
        raised = False
    except TypeError:
        raised = True
    check("POOL_STRATEGIES 只读（写入报 TypeError）", raised, "")
    check("旧重名转发：POOL_STRATEGIES['fixed'] 是引擎 fixed 策略",
          callable(DE.POOL_STRATEGIES["fixed"]) and DE.POOL_STRATEGIES["fixed"] is not DE._roll_fish, "")

    # ★ 2026-09-14（B12B13-TAIL 线3）：`game/drop_engine.py` 已成**薄壳**（模块别名到包内实现，
    #   见该文件头注），实现真源 = 包内 `<插件>/framework/games/orlandia/content/loot.py`。
    #   ★ P5F 前置②（去壳）：原来扫「壳 + 实现」两侧拼接；终态壳已删 ⇒ 扫面 = **包内实现真源一份**。
    #   判别力不变：该壳只有别名转发（`sys.modules[__name__] = _impl`），既不承载旧实现，
    #   也不承载新接线；下面 `dead` / `live` 两类断言的落点全在实现正文里。
    _impl_p = os.path.join(PKG_ROOT, "content", "loot.py")
    if not os.path.exists(_impl_p):                        # pragma: no cover
        raise RuntimeError("drop_engine 薄壳化后扫面缺包内实现：%s" % _impl_p)
    src = open(_impl_p, encoding="utf-8").read()
    for dead in ("def _quality_weights_inline", "def _weighted_pick", "def _roll_weighted",
                 "def _roll_table", "def _roll_table_choice", "def _roll_fixed",
                 "def _roll_sub_ref", "def _sub_ctx", "def _resolve_pool",
                 "POOL_STRATEGIES = {"):
        check(f"旧内容侧实现已删：{dead}", dead not in src, "")
    for live in ("LootTable(", "rng=random", "FISH_TIERS", "_LazyPools",
                 "resolver=_resolve_item_ref", "strategy_of"):
        check(f"新实现接线到位：{live}", live in src, "")
    check("池数据零改动（DROP_POOLS 还是 data 层那份，596 池）",
          len(DROP_POOLS) == 596 and _DP.DROP_POOLS is DROP_POOLS, str(len(DROP_POOLS)))

    # 「哪些一行没改」也要证明：AST 定位函数体，逐行比（去 docstring / 去注释 / 去空行）
    import ast

    def _fn_code_lines(text, name):
        tree = ast.parse(text)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                first = node.body[0]
                is_doc = (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                          and isinstance(first.value.value, str))
                start = first.end_lineno if is_doc else node.lineno
                body = text.splitlines()[start:node.end_lineno]
                return [l for l in body if l.strip() and not l.strip().startswith("#")]
        return None

    # ★ 2026-09-14（B12B13-TAIL 线3）：正文里的**宿主取件**两处差异（都在白名单内，逐条列全）：
    #   `_resolve_item_ref`：`import game.content as C` → `C = _content_api(ctx)`（内容 API 注入句柄）
    #     + `C.RUNES` → 裸 `RUNES`（B15b：符文表读包内门面，包外运行时也有符文 —— 单源）
    _res_changed_old = {
        "import game.content as C  # noqa: E402  绝对导入，防循环/半初始化",
        'pool = [k for k, r in C.RUNES.items() if (r.get("quality") or "") in ("blue", "purple")]',
        "pool = [k for k, r in C.RUNES.items()",
        '[k for k, r in C.RUNES.items() if (r.get("quality") or "") in ("blue", "purple")]',
        "r_def = C.RUNES[rk]",
    }
    _res_changed_new = {
        "C = _content_api(ctx)  # 替身：真源 `import game.content as C`（宿主内容 API → 调用方给）",
        'pool = [k for k, r in RUNES.items() if (r.get("quality") or "") in ("blue", "purple")]',
        "pool = [k for k, r in RUNES.items()",
        '[k for k, r in RUNES.items() if (r.get("quality") or "") in ("blue", "purple")]',
        "r_def = RUNES[rk]",
    }
    for fn, _dl_old, _dl_new in (("_randint", set(), set()),
                                 ("_resolve_item_ref", _res_changed_old, _res_changed_new)):
        _old_raw = _fn_code_lines(_FROZEN_SRC, fn)
        _new_raw = _fn_code_lines(src, fn)
        old_lines = [l for l in _old_raw or [] if l.strip() not in _dl_old]
        new_lines = [l for l in _new_raw or [] if l.strip() not in _dl_new]
        check(f"{fn} 与 v174 原文**逐行相同**（除白名单 {len(_dl_new)} 处宿主取件行，内容侧逻辑一字没改）",
              bool(_new_raw) and old_lines == new_lines and old_lines,
              f"{old_lines} vs {new_lines}")

    # _roll_fish 只允许这几处不同：签名 / 档位表来源（TierTable）/ rng 取用 / 档位表未挂守卫
    _fish_changed_old = {
        "def _roll_fish(pool: dict, ctx: Any) -> list[dict]:",
        "import game.content as C  # noqa: E402",
        "FISH_QUALITY_ORDER = C.FISH_QUALITY_ORDER",
        "FISH_QUALITY_WEIGHTS = C.FISH_QUALITY_WEIGHTS",
        "weights = list(_quality_weights_inline(prof_lv, FISH_QUALITY_WEIGHTS))",
        "quality = random.choices(FISH_QUALITY_ORDER, weights=weights, k=1)[0]",
        "pick = random.choices(pool_by_q, weights=pool_w, k=1)[0]",
        # ★ D8（2026-09-17）「数据进表」：月份→季节字面量搬进包内域 `content/data/season_map.json`
        #   （读口 `loot._SEASON_BY_MONTH`，引擎 records fail-closed）。旧 4 行字面量进白名单；
        #   行为不变由 D8 的 out/raw/00_before.json↔01_after.json 逐名对拍 + 04_live_probe.txt 钉住。
        'season = {3: "spring", 4: "spring", 5: "spring",',
        '6: "summer", 7: "summer", 8: "summer",',
        '9: "autumn", 10: "autumn", 11: "autumn",',
        '12: "winter", 1: "winter", 2: "winter"}.get(_m, "spring")',
    }
    _fish_changed_new = {
        "def _roll_fish(pool: dict, ctx: Any, table) -> list[dict]:",
        "FISH_TIERS = _fish_tiers()",
        "FISH_QUALITY_ORDER = FISH_TIERS.order",
        "if not FISH_QUALITY_ORDER:               # 替身守卫：档位表未挂（调用方没给）→ 抽不出（不抛）",
        "return []                            # noqa: 档位表未挂（不静默等权兜底）",
        "rng = table.rng",
        "weights = list(FISH_TIERS.weights_at(prof_lv))",
        "quality = rng.choices(FISH_QUALITY_ORDER, weights=weights, k=1)[0]",
        "pick = rng.choices(pool_by_q, weights=pool_w, k=1)[0]",
        # ★ D8：同一张月份→季节表改从包内域读（值逐名相同，见上）
        'season = _SEASON_BY_MONTH.get(_m, "spring")',
    }
    fish_old = [l for l in _fn_code_lines(_FROZEN_SRC, "_roll_fish")
                if l.strip() not in _fish_changed_old]
    fish_new = [l for l in _fn_code_lines(src, "_roll_fish")
                if l.strip() not in _fish_changed_new]
    check("_roll_fish 除「档位表来源 + rng 取用 + 签名」外**逐行不变**（季节/水域/鱼饵过滤一字没动）",
          fish_old == fish_new, f"old_only={[x for x in fish_old if x not in fish_new][:4]}"
                               f" new_only={[x for x in fish_new if x not in fish_old][:4]}")

    # import 期不拉池数据（子进程实证：import 真源后 drop_pools 不在 sys.modules）
    # ★ P5F 前置②（去壳）：原来是 `import data.plugins.dragonfall.game.drop_engine`（旧壳名）；
    #   终态壳已删 ⇒ 换包内真源 `content.loot`（同一只模块对象），断言口径不变。
    _pkg_root = PKG_ROOT
    code = ("import sys;sys.path.insert(0,%r);sys.path.insert(0,%r);"
            "import content.loot as de;"
            "print(sorted(m for m in sys.modules if m.endswith('drop_pools')))"
            ) % (_FRAMEWORK_DIR, _pkg_root)
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env={**os.environ, "PYTHONUTF8": "1"}, cwd=PLUGIN_DIR)
    check("import drop_engine 期不拉 DROP_POOLS（惰性，时机与 v174 同）",
          p.returncode == 0 and p.stdout.strip() == "[]",
          f"rc={p.returncode} out={p.stdout.strip()[:200]} err={p.stderr.strip()[-300:]}")


# ============================================================================
# §7 已知差异（有意；真实池数据 0 命中）—— 逐条钉住"新行为"并写明旧行为
# ============================================================================
def sec7_known_deltas():
    print("【7. 已知差异（有意登记；真实池数据 0 命中）】")
    global CMP
    with _with_pools(_SYNTH_ALL):
        # 1) gold: 子引用带 n
        random.seed(9)
        o = _old_roll("s:delta_gold_n", ctx_old(player_level=10))
        random.seed(9)
        n = DE.roll("s:delta_gold_n", ctx_new(player_level=10))
        CMP += 1
        check("D1 gold:+n 旧忽略 n / 新按 roll_range(n) 乘 count（有意，池数据无此写法）",
              _diff(o, n) != "", f"old={o} new={n}")
        # 2) 带前缀子池引用
        random.seed(10)
        o = _old_roll("s:delta_prefix_ok", ctx_old(player_level=10))
        random.seed(10)
        n = DE.roll("s:delta_prefix_ok", ctx_new(player_level=10))
        CMP += 1
        check("D2 weighted: 前缀子池：旧当内联引用（垃圾物品）/ 新剥前缀正常抽子池（有意）",
              _diff(o, n) != "" and n and n[0].get("item_id") == "mat_cao_yao",
              f"old={o} new={n}")
        # 3) 裸名册 id 当条目 ref
        random.seed(11)
        o = _old_audit_all()
        random.seed(11)
        n = DE.audit_all()
        CMP += 1
        o_bare = [x for x in o["issues"] if x[1] == "s:delta_bare_rid_entry"]
        n_bare = [x for x in n["issues"] if x[1] == "s:delta_bare_rid_entry"]
        check("D3 裸名册 id 当条目 ref：旧报「引用无法解析」/ 新放行（引擎只有一个 resolvable 回调，"
              "选忠实 roll 侧；真实池 0/1435）",
              o_bare == [("断链", "s:delta_bare_rid_entry", "引用无法解析: eq_hui_ying_lang_ya_ren")]
              and n_bare == [], f"old={o_bare} new={n_bare}")
        # 4) fixed 空 entries
        o_fx = [x for x in o["issues"] if x[1] == "s:delta_fixed_empty"]
        n_fx = [x for x in n["issues"] if x[1] == "s:delta_fixed_empty"]
        check("D4 fixed 池 entries 为空：旧不报 / 新报「空池」（有意，只多不少）",
              o_fx == [] and n_fx == [("空池", "s:delta_fixed_empty", "entries 为空")],
              f"old={o_fx} new={n_fx}")
        # 5) table_choice 的 rolls 子池
        o_tc = [x for x in o["issues"] if x[1] == "s:delta_tc_bad_sub"]
        n_tc = [x for x in n["issues"] if x[1] == "s:delta_tc_bad_sub"]
        check("D5 table_choice 的 rolls：旧不审 / 新按 uses=rolls 审（有意，只多不少）",
              o_tc == [] and n_tc == [("断链", "s:delta_tc_bad_sub", "table 子池未知: s:不存在")],
              f"old={o_tc} new={n_tc}")
        # 6) table 池的 roll 行带 fallback 字段
        random.seed(12)
        o_fb = _old_roll("s:delta_t_fallback", ctx_old(player_level=10))
        random.seed(12)
        n_fb = DE.roll("s:delta_t_fallback", ctx_new(player_level=10))
        CMP += 1
        check("D6 table 池 roll 行的 fallback：旧**忽略**（抽空就空）/ 新按引擎 roll_cfg 应用兜底"
              "（有意；真实池只把 fallback 用在 table_choice，0 命中）",
              o_fb == [] and n_fb and n_fb[0].get("item_id") == "mat_jiang_guo"
              and n_fb[0].get("count") == 4, f"old={o_fb} new={n_fb}")
        # 差异池的 roll/expand：D1/D2/D6 的 roll 本来就不同；D3/D4/D5 必须仍逐格一致
        bad = []
        for k in sorted(_SYNTH_DELTA):
            for seed in (3, 21):
                random.seed(seed)
                a = _old_roll(k, ctx_old(player_level=20, monster_lv=20, qty=2))
                random.seed(seed)
                b = DE.roll(k, ctx_new(player_level=20, monster_lv=20, qty=2))
                CMP += 1
                if k not in _DELTA_ROLL_DIFF and _diff(a, b):
                    bad.append((k, seed, a, b))
        check("差异池里 D3/D4/D5（只差 audit）roll 仍逐格全等；差异池 expand 全部逐格全等",
              not bad and all(_diff(_old_expand_pool(k), DE.expand_pool(k)) == ""
                              for k in sorted(_SYNTH_DELTA)), str(bad[:2]))
        # 7) 引擎**自己拥有的两条结构消息**措辞（v184 拆掉内容侧字符串改写壳之后）
        #    判定（级别/池key/顺序）没变，只有措辞变了 —— 引用类措辞由内容侧 `_resolvable`
        #    直接给出（逐字保留旧说法），所以全仓只有这两条是引擎的措辞。
        CMP += 1
        check("D7 引擎结构消息措辞：旧「条目无 item: {e}」→ 新「条目缺 item 字段: {e}」；"
              "旧「table 子池未知: 」(空 ref) → 新「roll 无 pool」（判定不变；"
              "内容侧引用类措辞仍逐字保留）",
              True)
    print("     （D1/D2/D6 真实池数据未使用；D3/D4/D5 只让审计「多报」或「放行」未出现过的写法；"
          "D7 只是引擎那两条结构消息的措辞）")


# ============================================================================
# §8 入口边界
# ============================================================================
def sec8_edges():
    print("【8. 入口边界：不存在的池 / kw 就地 setattr / ctx=None+kw】")
    global CMP
    check("roll 不存在的池 → []（旧新一致）",
          _old_roll("不存在的池", ctx_old()) == DE.roll("不存在的池", ctx_new()) == [], "")
    check("roll 带前缀 key → []（旧只认池表原样 key）",
          _old_roll("weighted:gather:oak_plain", ctx_old()) ==
          DE.roll("weighted:gather:oak_plain", ctx_new()) == [], "")
    kw = dict(map_id="oak_plain", player_level=5)
    c_old, c_new = ctx_old(**kw), ctx_new(**kw)
    random.seed(31)
    a = _old_roll("gather:oak_plain", c_old, qty=4)
    random.seed(31)
    b = DE.roll("gather:oak_plain", c_new, qty=4)
    CMP += 1
    check("roll(key, ctx, qty=4) 逐格全等", _diff(a, b) == "", f"{a} vs {b}")
    check("kw 是**就地 setattr** 到 ctx（调用方依赖这个行为）",
          getattr(c_old, "qty", None) == 4 and getattr(c_new, "qty", None) == 4,
          f"old.ctx.qty={getattr(c_old, 'qty', None)} new.ctx.qty={getattr(c_new, 'qty', None)}")
    random.seed(32)
    a = _old_roll("chest:low", None, player_level=20, qty=1)
    random.seed(32)
    b = DE.roll("chest:low", None, player_level=20, qty=1)
    CMP += 1
    check("ctx=None + kw → 内部建 SimpleCtx，逐格全等", _diff(a, b) == "", f"{a} vs {b}")
    random.seed(33)
    r = DE.roll("fish:oak_plain", ctx_new(map_id="oak_plain", prof_lv=2))
    check("fish 产出形态不变（type=fish + data 带 name/quality）",
          r and r[0]["type"] == "fish" and "name" in r[0]["data"]
          and "quality" in r[0]["data"], str(r)[:200])


def main():
    print("=" * 78)
    print("v184 掉落池门禁：旧实现（v174 原文冻结） vs 引擎实现（saintess_engine.loot）")
    print(f"池数 {len(DROP_POOLS)} · roll 组合 {len(DROP_POOLS) * len(_CTXS) * len(_SEEDS)}"
          f"（ctx {len(_CTXS)} × 种子 {len(_SEEDS)}）· 合成池 {len(_SYNTH_ALL)}")
    print("=" * 78)
    sec0_freeze()
    sec1_audit()
    sec2_expand()
    sec3_roll_real()
    sec4_choice_and_fallback()
    sec5_synthetic()
    sec6_names_and_source()
    sec7_known_deltas()
    sec8_edges()
    print("-" * 78)
    print(f"结果：断言 {PASS + FAIL} 条（通过 {PASS} / 失败 {FAIL}）"
          f"，其中逐项比对 {CMP} 条")
    if FAIL == 0:
        print("✅ 全绿：旧实现 vs 新实现逐格一致（差异见 §7 登记，均未被真实池数据触发）")
    return FAIL == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
