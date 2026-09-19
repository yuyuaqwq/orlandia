# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— fishing 核心域实现（B13-L5，2026-09-14）。

真源 = 宿主 `game/core/fishing.py`（原 150 行）**逐字搬**：函数体一字未改，只换「宿主取件」。

| 真源写法 | 包内 | 依据 |
|---|---|---|
| `from ..data.fishing import FISHING_SPOTS` | 包内域读口 `fishing_spots`（`content/data/fishing_spots.json`，11 条） | 对拍与宿主 `FISHING_SPOTS` 逐键相等，`overnight/w1213_l5_probe.py` P4 |
| `from ..data.fishing import FISH_POOL` | 包内域读口 `fishing_pool`（30 条，导出期注入 `seq` = 源插入序）→ 模块级按 `seq` **还原成 list 并剥掉 `seq`** | 源是 list、插入序参与抽样（`_roll_fish_legacy` 的 `random.choices`）→ 必须保序；对拍重建列表与宿主 `FISH_POOL` 逐项相等（P4） |
| `from ..data.fishing import FISH_COLLECT` | `_HostAttr("data.fishing", "FISH_COLLECT")` | **缺口**：彩蛋收藏鱼 3 条**没有独立域**（导出器 `derive_fishing_pool` 只导 FISH_POOL） |
| `from ..data import FISH_QUALITY_ORDER` | `_HostAttr("data", "FISH_QUALITY_ORDER")` | **缺口**：`QUALITY_ORDER` 无同名域（BRIEF §5 对照表列明） |
| `from .quality_tiers import FISH_TIERS` | `_HostAttr("core.quality_tiers", "FISH_TIERS")` | `core/quality_tiers.py` 属 **B13-L1** 线（并行未落地）→ 按 SOP 走宿主句柄；正文 `FISH_TIERS.weights_at(…)` 一字未改（宿主源码级门禁指向本实现，见宿主壳头注） |
| `from .time_weather import current_season` | `_HostAttr("core.time_weather", "current_season")`（模块级可调用替身） | `core/time_weather.py` 属 **B13-L2** 线（并行未落地）→ 宿主句柄；**仍是模块级名字**，故 `tests/test_v116_fishing_season.py:31 F.current_season = …` 的打补丁语义不变（宿主壳 = 本模块别名，补丁打在实现本体的模块全局） |
| `from ..drop_engine import roll as _roll, _SimpleCtx`（`roll_fish` 函数内） | 同位置 `宿主面取件("drop_engine", …)` | **缺口**：`game/drop_engine.py`（476 行）是宿主根文件（B14 才动）；包内 `content/loot.py` 已是它的逐字端口，但垂钓档位表要**调用方 `install_quality_tiers`**，未装时 `_roll_fish` 守卫直接返回 `[]`（= 抽空）→ **现在切过去会改行为**，本线不切 |

宿主侧：`game/core/fishing.py` 现在只剩「加载包 + 模块别名 + 源码探针」薄壳，见那边头注。
"""
import os
import random
from saintess_engine.records import apply_replacements, placeholder, register_view, set_from_domains, update_in_place

# ============================================================
# ① 宿主替身口（注入优先 → sys.modules → importlib；**绝不静默空跑**）
#    抄 `content/world_cmds.py` 的同款写法（B9 线2 定的包内标准形状）
# ============================================================
from saintess_engine.wire import Wire
_WIRE = Wire()
_MOD = "fishing"


def bind_host(**objs):
    """宿主薄壳 import 期注入（幂等）——键 = 宿主面名。"""
    _WIRE.bind(**objs)


# ============================================================
# ② 包内域读口（域 `fishing_spots` / `fishing_pool`；导出器 = 游戏仓
#    `scripts/export_domains/b9_profession.py:derive_fishing_spots / derive_fishing_pool`）
# ============================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>

# 读表口 = 引擎 records 形状：**域元数据唯一源** = 包内 `editor/domains.json`
# （S2 ②：只声明「我要哪些域」，落点由声明的 `kind` 派生；缺项/缺文件即报错，不静默空表）
_R = set_from_domains(_PKG_ROOT, ("fishing_spots", "fishing_pool"))


FISHING_SPOTS = placeholder("FISHING_SPOTS")
FISH_POOL = placeholder("FISH_POOL")

from ._domainio import seq_rows, same_container as _same_container             # P0-4d 域读口单源

from .catalog_rules import FISH_COLLECT   # ★ B16-W11d：包内门面（无域 → dump）          # v101.25i6 别名：= QUALITY_ORDER
from .catalog_b143 import QUALITY_ORDER as FISH_QUALITY_ORDER   # ★ B16-W11d：真源 = `QUALITY_ORDER` 别名      # v184：垂钓档位/权重唯一真相源
# ★ P5E-DELETE（2026-09-15，删壳批）：下面两行原为宿主句柄
#   `_HostAttr("core.quality_tiers", "FISH_TIERS")` / `_HostAttr("core.time_weather", "current_season")`
#   —— 它们写在「B13-L1/L2 线并行未落地」时。**两线的包内真源如今都已在位**
#   （`content/quality_tiers.py::FISH_TIERS` 惰性档位表 · `content/time_weather.py::current_season`
#   逐字端口），宿主薄壳 `game/core/{quality_tiers,time_weather}.py` 随即被删。
#   本批按「真源已在包内 → 包内直取」（与 `content/world_cmds.py:80 from .time_weather import PERIOD_CN`
#   同款）改口径：**取值来源不动（同一份档位表 / 同一函数）、计算一字未改**，只把取件路径
#   从已删的宿主薄壳移到包内真源。断言强度不变；`tests/test_v116_fishing_season.py` 的
#   `F.current_season = lambda …` 打桩语义也不变（仍是**模块级同名对象**）。
from .quality_tiers import FISH_TIERS as FISH_TIERS
from .time_weather import current_season as current_season
from . import texts as _T       # C 档 PRE4-a（2026-09-19）：文案表读口（本文件首次接入）


def _quality_weights(prof_lv: int) -> list:
    """垂钓等级 → 五档权重(Lv.1/3/5/7/9 查表，中间等级线性插值)。

    v184：唯一真相源是 `core/quality_tiers.FISH_TIERS`（`weights_by_level=FISH_QUALITY_WEIGHTS`
    + `clamp=(1, 9)`）——插值逻辑（含浮点尾数）与旧实现位级一致，本函数保留为薄转发
    （`drop_engine` 那份内联副本也指向同一张表）。
    """
    return FISH_TIERS.weights_at(prof_lv)


def roll_fish(prof_lv: int = 1, spot_id: str | None = None, bait: str | None = None):
    """垂钓结果：返回 FISH_POOL 中的一项。

    prof_lv: 垂钓副业等级（1-9）
    spot_id: 钓点地图 ID（FISHING_SPOTS 的 key）；钓点禁出档位权重清零，
             品种限定水域（spots 字段）不满足时跳过。
    bait: v102.3 鱼饵加成（glow=紫橙×2 / dough=绿蓝×1.5 / blood=稀有鱼种×3）

    v174 统一抽象：内部走 drop_engine.roll("fish:{spot}")，数据源 DROP_POOLS。
    返回形态不变（FISH_POOL 条目 dict：name/quality/type/price/size_range/...）。
    """
    if spot_id:
        from .loot import roll as _roll
        from .loot import _SimpleCtx
        # 季节显式传入：让测试能 mock fishing.current_season（drop_engine 不自算）
        ctx = _SimpleCtx(map_id=spot_id, prof_lv=prof_lv, bait=bait, qty=1,
                         season=current_season())
        res = _roll(f"fish:{spot_id}", ctx)
        if res and res[0].get("type") == "fish":
            return res[0]["data"]
        # 池不存在/抽空 → 回退老逻辑（数据兜底，保持行为）
    return _roll_fish_legacy(prof_lv, spot_id, bait)


def _roll_fish_legacy(prof_lv: int = 1, spot_id: str | None = None, bait: str | None = None):
    """旧垂钓逻辑（v174 前）：drop_engine 池缺失时的行为兜底。

    v116 季节限定：season 硬限定鱼的季节不匹配时跳过；season_boost 偏好的季节权重 ×1.5。
    若某档位在当前季节被硬限定过滤空，则放宽为「不限定季节」重试，避免钓空。
    """
    spot = FISHING_SPOTS.get(spot_id) if spot_id else None
    ban = set(spot.get("ban_quality", [])) if spot else set()
    # v184：权重行问唯一真相源 FISH_TIERS（clamp 1..9 + 相邻档线性插值，位级同旧实现）
    weights = FISH_TIERS.weights_at(prof_lv)
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
    # v184：档位抽取本身仍用标准库 random.choices —— 垂钓权重行是**浮点**（插值 + 鱼饵倍率），
    # 引擎 pick_weighted 按 `int()` 截断权重（loot/pick.py 契约），换成它会改概率分布
    # （实测同种子结果 1%~4% 不同）→ 违反「对外行为一字不变」。权重**行**已收口到
    # FISH_TIERS.weights_at（唯一真相源），此处只保留「按行抽一档」这一句。
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
        pick["_season_prefix"] = {"spring": _T.static("fish.season_tag_spring"), "summer": _T.static("fish.season_tag_summer"),
                                  "autumn": _T.static("fish.season_tag_autumn"), "winter": _T.static("fish.season_tag_winter")}[season]
    return pick

def roll_fish_size_weight(fish: dict):
    """v126.1 鱼获随机波动：百分位均匀分布在品种 size_range/weight_range 区间内插值。

    返回 {"size": float(cm), "weight": float(kg)}（保留 1 位小数）；品种未配区间
    （老数据/测试桩）返回 None，调用方跳过入明细——出售按 1.0 原价，行为与旧版一致。
    v126.4 审计 P2：重量精度按量级自适应——低于 0.1kg 的品种（珍珠类 0.01-0.05kg）
    原 round(weight,1) 几乎 100% 舍入成 0.0（播报 0.0kg + 加权系数恒 0.5 失效），
    现 <0.1kg 保留 3 位小数（0.045），≥0.1kg 保留 1 位。
    """
    sr = fish.get("size_range")
    wr = fish.get("weight_range")
    if not sr or not wr or len(sr) < 2 or len(wr) < 2:
        return None
    size = sr[0] + (sr[1] - sr[0]) * random.random()
    weight = wr[0] + (wr[1] - wr[0]) * random.random()
    if weight < 0.1:
        return {"size": round(size, 1), "weight": round(weight, 3)}
    return {"size": round(size, 1), "weight": round(weight, 1)}

def roll_collect_fish(spot_id: str | None = None, is_night: bool = False):
    """彩蛋收藏鱼判定（16 章 4.x）：五档之外独立判定。

    概率升序判定（最稀有优先），命中即返回，最多 1 条。
    spot_id: 钓点地图 ID；is_night: 当前是否为夜晚（18 章时间系统）。
    """
    for cf in sorted(FISH_COLLECT, key=lambda x: x["chance"]):
        if cf.get("spots") and (spot_id not in cf["spots"]):
            continue
        if cf.get("time") == "night" and not is_night:
            continue
        if random.random() < cf["chance"]:
            return cf
    return None


def _rebuild_view() -> list:
    """重读本模块声明的域 → 重建模块级派生状态；返回非容器替换序列（见文件头 ★ 视图）。

    容器（dict / list / set）就地更新（身份不变、内容已新）；非容器（tuple / frozenset /
    数字 / 字符串）本模块换引用，并把 `(旧对象, 新对象)` 序列交引擎做别名回填。
    import 期（见文件尾）与每次重载走**同一条路径**：本函数是唯一构建处。
    """
    global FISHING_SPOTS, FISH_POOL

    # 旧对象：容器要就地更新、非容器要交代给引擎（全部先抓一遍，再重建）
    old = {
        'FISHING_SPOTS': None, 'FISH_POOL': None,
    }
    for _n in list(old):
        old[_n] = globals()[_n]

    FISHING_SPOTS = _R.fishing_spots.all()
    # 源是 list（插入序参与抽样）→ 域里带注入字段 `seq`（1 基）→ 这里按 seq 还原成 list 并剥掉 seq
    # （剥掉后每条的字段与字段序 = 源条目原样，逐项对拍见 w1213_l5_probe.py P4）
    FISH_POOL = seq_rows(_R.fishing_pool.all().values())

    # ============================================================
    # ③ 宿主取件（模块级名字与真源逐名相同；正文零改动）
    # ============================================================

    # 收敛：容器就地更新（身份不变）；非容器交引擎按身份回填
    out = []
    for name in old:
        before, new = old[name], globals()[name]
        if before is new:
            continue
        if isinstance(new, (dict, list, set)):
            if _same_container(before, new):
                update_in_place(before, new)   # 就地更新：消费方手头引用身份不变
                globals()[name] = before
            continue                           # 首次构建：全局已是新对象
        out.append((before, new))
    return out


register_view(_rebuild_view, order=100)
apply_replacements(_rebuild_view(), __package__)
