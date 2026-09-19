# -*- coding: utf-8 -*-
"""包内社交·市场/摆摊域（`content/social_stall.py`）—— 真源 `game/commands/social.py` 的市场/摊位编排。

真源（游戏仓 `qqbot/data/plugins/dragonfall`，**只读**）
--------------------------------------------------------
| 真源 | 本文件搬什么 |
|---|---|
| `game/commands/social.py:36-60 market` | 群市场面板行（卖家名回调；tip/记账留命令层） |
| `game/commands/social.py:176-209 _stall_parse_args` | 摆卖/摆换参数解析（价格上下限/数量 1~999） |
| `game/commands/social.py:211-242 _stall_resolve` | 按背包序号/名称解析目标物品（精确→同名列表→模糊→无） |
| `game/commands/social.py:244-277 _stall_place` | 摆摊落位（数量校验 / 地图与铺面校验 / 原子上架） |
| `game/commands/social.py:338-342 _stall_label` | 摊位价格标签（`N 金币` / `🔄 换`） |
| `game/commands/social.py:346-383 stall_view` | 摊位面板两分支（指定玩家 / 当前地图） |
| `game/commands/social.py:98-157` | 「下架/购入」的目标选取与守卫（所有权/换摊/异地/金币） |

宿主耦合替身（**只改两类东西**：① 存储层 ② 读表口 —— 表都属宿主 `*_config`/数据面）
------------------------------------------------------------------------------
| 真源写法 | 包内写法 | 说明 |
|---|---|---|
| `from .. import db` + `db.xxx(...)` | 模块级 `db` = 惰性宿主代理 `_HostDB` | 正文 `db.xxx` 一行未改；注入优先 → 已加载宿主模块（**不 import**） |
| `MAP_BY_ID` / `HOUSE_LEVELS` / `ECON_CONFIG`（真源写法 `C.<名>`） | **包内门面直取**：`catalog_space`（`_cs`）/ `catalog_life`（`_cl`） | ★ **B14-2 L6**：切共享门面（`b14_catalog_gate.py` 逐值 + 键序相等）；`bind_host(maps=…, house_levels=…, econ=…)` 三个注入位**保留（宿主薄壳仍在传）但本域不再取用** |
| `QUALITY`（真源写法 `C.<名>`） | `bind_host(quality=…)` → `宿主面取件("QUALITY", …)` | **缺口**：包内无品质表域（B14-B/E 已登记）⇒ 仍走宿主句柄；缺注入且宿主无该名 → 抛（不静默空表） |

返回结构（与真源逐字一致）
--------------------------
`stall_parse_args(raw, is_sell)` → `(item_name, (price, count))` 或 `(None, err_msg)`；
`stall_resolve(inv, item_name)` → `(条目, None)` 或 `(None, err_msg)`；
`stall_place(...)` → `(True, (item_nm, cnt_s, map_name, tip))` 或 `(False, msg)`；
`stall_label(s)` → `str`；`market_*_lines(...)` / `stall_view_*_lines(...)` → `list[str]`；
`market_unsell_pick(items, mid, qq_id)` → `(ok, 条目, err)`；`market_buy_check(it, player)` → `(ok, err)`。

用法::

    from content import social_stall as SS
    SS.bind_host(db, quality=…)          # maps/house_levels/econ 注入位已不用（B14-2 L6）
    ok, res = SS.stall_place(group_id, qq_id, player, item_name, price, count)
"""
from __future__ import annotations

import re

# ★ B14-2 L6：数据表切包内门面（宿主 `game/data` 删掉后本域仍能活）
from . import catalog_life as _cl        # HOUSE_LEVELS / ECON_CONFIG
from . import catalog_space as _cs       # MAP_BY_ID
from . import reroll as _reroll          # 台账 §0 D4：绑定读口（保底产物不可交易）
from . import texts as _T            # C 档 20a（2026-09-19）：文案表读口（本文件首次接入）

# ============================================================
# ① 宿主替身口（存储层 / 宿主常量）—— 引擎 wire 形状
# ============================================================
from saintess_engine.wire import Wire

#: 注入句柄面（`bind_host()` 写；`None` = 没给）——槽名 = `bind_host` 形参名
_WIRE = Wire()

from ._hostref import make_bound_host  # 取件工厂单源（P0-3；常量本身不再被本文件引用）


def bind_host(db=None, maps=None, house_levels=None, quality=None, econ=None, store_social=None):
    """宿主替身注入（幂等；宿主薄壳在 import 期调用）。"""
    _WIRE.bind(db=db, maps=maps, house_levels=house_levels, quality=quality,
               econ=econ, store_social=store_social)


_bound_host = make_bound_host(_WIRE, "social_stall")


class _HostDB:
    """惰性宿主存储层代理（真源 `from .. import db`）——`db.xxx` 正文不动，属性访问时解析。"""

    def __getattr__(self, name):
        return getattr(_bound_host("db"), name)


db = _HostDB()


def MAP_BY_ID() -> dict:
    """★ B14-2 L6：包内门面直取（`maps` 注入值保留兼容、不再取用）。"""
    return _cs.MAP_BY_ID


def HOUSE_LEVELS() -> dict:
    """★ B14-2 L6：包内门面直取（`house_levels` 注入值保留兼容、不再取用）。"""
    return _cl.HOUSE_LEVELS


def QUALITY() -> dict:
    """装备品质色表 —— **缺口**（包内无域）：仍走宿主句柄。"""
    _q = _WIRE.handles().get("quality")   # 注入位优先（真源语义），B1：兜底切包内门面
    if _q is not None:
        return _q
    from .catalog_b143 import QUALITY as _cb_quality   # 与宿主 `C.QUALITY` 同对象（is）
    return _cb_quality


def ECON_CONFIG() -> dict:
    """★ B14-2 L6：包内门面直取（`econ` 注入值保留兼容、不再取用）。"""
    return _cl.ECON_CONFIG


# ============================================================
# ② 摆摊（真源 `social.py:159-432`）
# ============================================================

def stall_parse_args(raw: str, is_sell: bool):
    """解析摆卖/摆换参数。返回 (item_name, price, count) 或 (None, err_msg)。

    is_sell=True: 『摆卖 <物> <单价> [数量]』数字 = 单价[, 数量]
    is_sell=False: 『摆换 <物> [数量]』数字 = 数量（无单价）
    """
    econ = ECON_CONFIG()
    if not raw:
        if is_sell:
            return None, (_T.static("stall.fmt_sell"))
        return None, (_T.static("stall.fmt_pawn"))
    parts = re.split(r"[\s*]+", raw)
    item_name = parts[0]
    rest = parts[1:]
    price, count = 0, 1
    if rest:
        num_tokens = [t for t in rest if t.isdigit()]
        if not num_tokens:
            if is_sell:
                return None, _T.static("stall.err_price_nan")
            return None, _T.static("stall.err_count_nan")
        if is_sell:
            price = int(num_tokens[0])
            count = int(num_tokens[1]) if len(num_tokens) >= 2 else 1
        else:
            count = int(num_tokens[0])
        if price > 0:
            if price < econ["market_min_price"]:
                return None, _T.static("stall.err_price_min")
            if price > econ["market_price_cap"]:
                return None, _T.text("stall.err_price_cap", cap=econ['market_price_cap'])
        if count < 1 or count > 999:
            return None, _T.static("stall.err_count_range")
    return item_name, (price, count)


def stall_resolve(inv, item_name):
    """按背包序号/名称解析目标物品。返回 (inv 条目, None) 或 (None, 错误文案)。"""
    quality = QUALITY()
    if item_name.isdigit():
        idx = int(item_name)
        if idx < 1 or idx > len(inv):
            return None, _T.text("stall.no_index", idx=idx, n=len(inv))
        return inv[idx - 1], None
    # 按名：精确名优先，同名多件列出让玩家选（对齐『出售』）
    exact = [it for it in inv if it["data"].get("name") == item_name]
    if len(exact) == 1:
        return exact[0], None
    if len(exact) > 1:
        flines = [_T.text("stall.same_name", n=len(exact), name=item_name)]
        for i, it in enumerate(exact, 1):
            fd = it["data"]
            _q = quality[fd["quality"]] if fd.get("quality") and fd.get("slot") else None
            fname_s = f"{_q['color']}【{fd['name']}】" if _q else fd["name"]
            flines.append(f"  {i}. {fname_s} ×{it['count']}")
        return None, "\n".join(flines)
    fuzzy = [it for it in inv if item_name in it["data"].get("name", "")]
    if len(fuzzy) == 1:
        return fuzzy[0], None
    if len(fuzzy) > 1:
        flines = [_T.text("stall.fuzzy_name", n=len(fuzzy), name=item_name)]
        for i, it in enumerate(fuzzy, 1):
            fd = it["data"]
            _q = quality[fd["quality"]] if fd.get("quality") and fd.get("slot") else None
            fname_s = f"{_q['color']}【{fd['name']}】" if _q else fd["name"]
            flines.append(f"  {i}. {fname_s} ×{it['count']}")
        return None, "\n".join(flines)
    return None, _T.text("stall.no_item", name=item_name)


def stall_place(group_id, qq_id, player, item_name, price, count):
    """摆摊落位公共逻辑：解析物品→数量校验→地图/铺面校验→原子上架。

    返回 (True, (item_nm, cnt_s, map_name, tip)) 或 (False, msg)（与真源 `_stall_place` 逐字同）。
    """
    maps = MAP_BY_ID()
    house_levels = HOUSE_LEVELS()
    found, err = stall_resolve(db.get_inventory(group_id, qq_id), item_name)
    if not found:
        return False, err
    # 台账 §0 D4：绑定（重铸保底产物）→ 摆卖/摆换 fail-closed 拒绝
    if _reroll.is_bound(found["data"]):
        return False, _T.text("reroll.bound", name=found['data'].get('name', '?'))
    if count > (found["count"] or 1):
        return False, _T.text("stall.not_enough", name=found['data'].get('name','?'), have=found['count'], want=count)
    cur_map = player.get("cur_map", "")
    map_obj = maps.get(cur_map, {})
    if not map_obj and not cur_map.startswith("home_"):
        return False, _T.static("stall.no_map")
    if cur_map.startswith("home_"):
        map_name = _T.static("stall.home_map")
    else:
        map_name = map_obj.get("name", cur_map)
    old = [s for s in db.market_list_by_seller(group_id, qq_id) if s.get("map_id")]
    _home_stall = cur_map.startswith("home_")
    if _home_stall:
        dlv = int(player.get("deed_lv", 1) or 1)
        hl = house_levels.get(dlv, house_levels[1])
        slots = hl.get("stall_slots", 0)
        if slots <= 0:
            return False, _T.static("stall.home_no_slot")
        if len(old) >= slots:
            return False, _T.text("stall.home_full", n=len(old), slots=slots)
    _old_items = [] if _home_stall else [s for s in old]
    db.market_stall_sell_atomic(
        group_id, qq_id, found["key"], found["data"], price, cur_map, _old_items, count=count
    )
    tip = _T.text("stall.old_closed", n=len(old)) if (old and not _home_stall) else ""
    item_nm = found["data"].get("name", "?")
    cnt_s = f" ×{count}" if count > 1 else ""
    return True, (item_nm, cnt_s, map_name, tip)


def stall_label(s):
    """摊位价格标签：price>0 → 'N 金币'；price=0 → '🔄 换'(以物换物)"""
    price = s.get("price") or 0
    return _T.text("stall.label_price", price=price) if price > 0 else _T.static("stall.label_pawn")


# ============================================================
# ③ 面板行（真源 `market` / `stall_view`）
# ============================================================

def market_view_lines(items, page_items, page, pages, seller_lookup, seller_group_id):
    """群市场面板主体行（真源 `social.py:46-57`；`_tip`/`_record_list_state` 留命令层）。

    真源逐字：行首编号直接用 DB id（与『购入 <编号>』『下架 <编号>』解析同基准）。
    """
    lines = [_T.text("stall.mkt_title", page=page, pages=pages, n=len(items)), "━━━━━━━━━━━━"]
    for it in page_items:
        seller = seller_lookup(seller_group_id, it["seller"])
        sname = seller["name"] if seller else it["seller"]
        d = it["item_data"]
        lines.append(_T.text("stall.mkt_row", id=it['id'], name=d.get('name','?'), price=it['price'], seller=sname))
    lines.append("")
    if pages > 1 and page < pages:
        lines.append(_T.text("stall.mkt_next", page=page+1, pages=pages))
    return lines


def stall_view_player_lines(target, stalls):
    """『摊位 <玩家名>』面板行（真源 `social.py:364-368`）。"""
    maps = MAP_BY_ID()
    lines = [_T.text("stall.view_title_pl", name=target['name']), "━━━━━━━━━━━━"]
    for s in stalls:
        map_name = maps.get(s.get("map_id", ""), {}).get("name", "？")
        lines.append(_T.text("stall.view_row", id=s['id'], name=s['item_data'].get('name','?'), label=stall_label(s),
                         map=map_name))
    lines.append(_T.static("stall.view_tip_pl"))
    return lines


def stall_view_here_lines(cur_map, stalls, player_lookup, group_id):
    """『摊位』（无参）本地摊位面板行（真源 `social.py:377-382`）。"""
    maps = MAP_BY_ID()
    lines = [_T.text("stall.view_title_here", map=maps.get(cur_map, {}).get('name', '这里')), "━━━━━━━━━━━━"]
    for s in stalls:
        seller = player_lookup(group_id, s["seller"])
        sname = seller["name"] if seller else s["seller"]
        lines.append(f"#{s['id']} {s['item_data'].get('name','?')} ｜ {stall_label(s)} ｜ {sname}")
    lines.append(_T.static("stall.view_tip_here"))
    return lines


# ============================================================
# ④ 下架 / 购入 的选取与守卫（真源 `social.py:98-157`）
# ============================================================

def market_unsell_pick(items, mid, qq_id):
    """下架目标选取 + 所有权守卫。返回 (ok, 条目, err)（真源 `social.py:106-113` 逐字）。"""
    it = next((x for x in items if x["id"] == mid), None)
    if not it:
        return False, None, _T.static("stall.unsell_gone")
    if str(it["seller"]) != str(qq_id):
        return False, None, _T.static("stall.unsell_notmine")
    return True, it, None


def market_sell_place(group_id, qq_id, item_name, price):
    """上架落库：按名找背包物品 → 单事务原子上架。返回 (ok, 物品显示名, err)（真源 `social.py:78-93`）。"""
    inv = db.get_inventory(group_id, qq_id)
    found = None
    for it in inv:
        if it["data"].get("name") == item_name:
            found = (it["key"], it["data"])
            break
    if not found:
        return False, item_name, _T.text("stall.no_item", name=item_name)
    item_key, data = found
    # 台账 §0 D4：绑定（重铸保底产物）→ 上架 fail-closed 拒绝
    if _reroll.is_bound(data):
        return False, item_name, _T.text("reroll.bound", name=data.get('name', item_name))
    # v116 审计修复 H0-A2：原 market_add + remove_item 两次独立调用，崩溃会致
    # 物品复制/少货得金。改走 store.social.market_sell_atomic 单事务原子上架。
    # ★ REPOINT-PKG（2026-09-15，B4R B 组第 5 项）：兜底由宿主子模块 `game.store.social`
    #   改**包内直取** `content/persistence/social.py`（宿主那边是 `import *` 委托薄壳
    #   ⇒ 同一函数对象）；注入槽 `bind_host(store_social=…)` 原样保留。
    _store_social = _WIRE.handles().get("store_social")
    if _store_social is None:
        from .persistence import social as _store_social   # 包内直取（调用时取件，与旧口径同时机）
    if not _store_social.market_sell_atomic(group_id, qq_id, item_key, data, price):
        return False, item_name, _T.text("stall.no_item", name=item_name)
    return True, data["name"], None


def stall_exchange_check(it, player, qq_id, group_id, give_name):
    """换摊前置守卫（寄售品/异地/自己/出售中/背包无给物）。返回 (ok, 给物条目, err)。

    真源 `social.py:396-422` 逐字：先判摊位存在（命令层），再判寄售→异地→自己→出售中→背包。
    """
    maps = MAP_BY_ID()
    if not it.get("map_id"):
        return False, None, _T.static("stall.ex_consign")
    # 当面交换：双方必须同地图
    if player.get("cur_map", "") != it["map_id"]:
        map_name = maps.get(it["map_id"], {}).get("name", "那里")
        return False, None, (_T.text("stall.ex_far", name=it['item_data'].get('name','?'), map=map_name))
    if str(it["seller"]) == str(qq_id):
        return False, None, _T.static("stall.ex_self")
    if (it.get("price") or 0) > 0:
        return False, None, (_T.text("stall.ex_onsale", name=it['item_data'].get('name','?'), price=it['price'], id=it['id']))
    inv = db.get_inventory(group_id, qq_id)
    give = next((x for x in inv if x["data"].get("name") == give_name), None)
    if not give:
        return False, None, _T.text("stall.no_item", name=give_name)
    # 台账 §0 D4：重铸保底产物绑定 —— **交出侧** fail-closed
    # （与「摆换」挂出侧同一条 D4 规则：不可交易；挂出侧拦在 stall_place）
    if _reroll.is_bound(give["data"]):
        return False, None, _T.text("reroll.bound", name=give["data"].get("name", give_name))
    return True, give, None


def market_buy_check(it, player, qq_id):
    """购入前置守卫（自买/换摊/异地/金币）。返回 (ok, err)（真源 `social.py:134-151` 逐字）。

    - 自己买自己 → err；price<=0（换摊）→ err（指向『换』）；
    - 摊位货（有 map_id）需同地图；金币不足 → err。
    """
    maps = MAP_BY_ID()
    if str(it["seller"]) == str(qq_id):
        return False, _T.static("stall.buy_self")
    if (it.get("price") or 0) <= 0:
        return False, (_T.text("stall.buy_pawn", name=it['item_data'].get('name','?'), id=it['id']))
    # v66：摊位货必须当面买（摆摊在当前位置，需要同地图）
    if it.get("map_id"):
        if player.get("cur_map") != it["map_id"]:
            map_name = maps.get(it["map_id"], {}).get("name", "那里")
            return False, (_T.text("stall.buy_far", name=it['item_data'].get('name','?'), map=map_name))
    if player["gold"] < it["price"]:
        return False, _T.text("stall.buy_no_gold", price=it['price'])
    return True, None
