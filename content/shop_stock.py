# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— shop_stock 核心域实现（B13-L5，2026-09-14）。

真源 = 宿主 `game/core/shop_stock.py`（原 228 行）；「宿主取件」对照：

| 真源写法 | 包内 | 依据 |
|---|---|---|
| `from ..data.shop_limit import SHOP_LIMIT`（`get_limit` 函数内） | 模块级 `SHOP_LIMIT` = 包内域读口 `shop_stock`（`content/data/shop_stock.json`） | 域 = 商品限购配置 35 条；对拍与宿主 `data.shop_limit.SHOP_LIMIT` **逐键相等**，`overnight/w1213_l5_probe.py` P2 |
| `from .. import db`（三个函数内，惰性） | 模块级 `db`（`content/_pkgref.py::DB`） | 正文里 `db.get_event_state(...)` 一字未改（抄 `content/world_cmds.py` 的替身形状）；**真源本来就把 db 放在函数体内**，本模块改成模块级惰性代理 = 同一个时机（属性访问时取） |
| —（模块无其它宿主依赖） | — | 时间/随机全部走 stdlib（`time`/`datetime`/`json`），无 DB 之外的双源风险 |

★ 2026-09-19（审计尾巴 #34）：上表原写 `db = _HostMod("db")` —— 那套手写替身口随 `_pkgref` 接入
已**全仓零调用点**，本次删净（只留 `bind_host` 形参位）。

库存份数 / 补货周期 / 售罄扣减这套机制走引擎 `ext_economy.shelf.Shelf`：本模块只给
「单格摆的是哪个商品、满额几份、两类周期多长」，引擎算到点与扣减；引擎簿记投影回原存档行
`shop_stock_{子区域}_{商品key}` 的 `{left, last_restock}`，全服共享的存储落点不变。

⚠️ 与真源语义完全一致的两点（照抄，不是新行为）：
  · `get_limit` 仍返回 `dict(SHOP_LIMIT.get(key) or {})`（**拷贝**）—— 调用方改返回值不会写脏域表；
  · `_now_ts()` / `_today()` 仍是模块级函数 —— `tests/test_v166_shop_limit.py:97` 用
    `mock.patch.object(SS, "_now_ts", …)` 打补丁，本模块与宿主壳**是同一个模块对象**
    （宿主壳只做模块别名），补丁打在实现本体的模块全局上，语义不变。

宿主侧：`game/core/shop_stock.py` 现在只剩「加载包 + 模块别名」薄壳，见那边头注。
"""
import datetime
import json
import time
from datetime import date

from ext_economy.shelf import Shelf

# ============================================================
# 宿主注入位（历史接口）—— ★ 2026-09-19 审计尾巴 #34
# ------------------------------------------------------------
# 本模块已**零宿主取件**：原文那套手写替身口（`_HOST_PKG` / `_HOST_PKG_FALLBACK` /
# `_INJECTED` / `_host_module` / `_host_attr` / `_HostMod`）在 `_pkgref`（包内惰性句柄）
# 接入后**全仓零调用点**（AST 复核：除注释外零引用），按「零调用点即删」删净；
# 只留 `bind_host` 这个扇出表（`content/facade.py::_BIND_SLOTS`）要求的形参位 ——
# 形状与前例 `content/events.py:59` 一致。
# ============================================================


def bind_host(**objs):
    """宿主注入位（历史接口）：本模块已**零宿主取件**，形参保留只为扇出表照旧调用。"""
    return None


from ._pkgref import DB as db
from . import texts as _T            # C 档 21a（2026-09-19）：文案表读口（本文件首次接入）
from ._domainio import read_domain as _read_domain

# ============================================================
# ② 包内域读口 —— 商店限购配置（域 `shop_stock`；真源 = `game/data/shop_limit.py:39 SHOP_LIMIT`，
#    导出器 = 游戏仓 `scripts/export_domains/shop_econ.py:derive_shop_stock`）
# ============================================================


SHOP_LIMIT: dict = _read_domain("shop_stock")

#: 每日周期（秒）：`restock_at`（HH:MM）折算成「锚点 + 一天 = 该时刻」的换货周期
_DAILY = 86400


def _now_ts() -> int:
    return int(time.time())

def _today() -> str:
    return date.today().isoformat()

def _load_state(db, key: str):
    raw = db.get_event_state(key)
    if not raw:
        return None
    try:
        st = json.loads(raw)
        return st if isinstance(st, dict) else None
    except (ValueError, TypeError):
        return None

def _save_state(db, key: str, st: dict):
    db.set_event_state(key, json.dumps(st, ensure_ascii=False))

# ================= 配置读取 =================

def get_limit(key: str) -> dict:
    """读商品限购配置（来自包内 `shop_stock` 域 = 真源 `data.shop_limit.SHOP_LIMIT`）。
    key 形如 'item:i_x' / 'mat:mat_x' / 'equip:eq_x' / 'weapon:武器名'。
    未配置 → 返回空 dict（不限购）。"""
    return dict(SHOP_LIMIT.get(key) or {})


# ================= 限量货架（店内共享） =================

def _stock_key(sa_id: str, key: str) -> str:
    """店内共享库存 key：shop_stock_{子区域}_{商品key}（带子区域=各店独立）"""
    return f"shop_stock_{sa_id}_{key}"

def _restock_period(cfg: dict):
    """固定补货周期（秒）：`restock_hours` × 3600；未配置 → None。"""
    hours = cfg.get("restock_hours")
    return int(float(hours) * 3600) if hours else None

def _daily_target(cfg: dict):
    """`restock_at`（HH:MM）→ 今日该时刻的整数秒；未配置 / 非法 → None。"""
    ra = cfg.get("restock_at")
    if not ra:
        return None
    try:
        hh, mm = str(ra).split(":")
        at = datetime.datetime.now().replace(hour=int(hh), minute=int(mm),
                                            second=0, microsecond=0)
    except (ValueError, OSError):
        return None
    return int(at.timestamp())

def _bucket(cfg: dict, key: str, left: int, last: int, now: int):
    """该商品的引擎货架 + 由存档行投影来的簿记（单格：摆的是该商品，满额 = `stock`）。

    · `restock_hours` → 补货周期；`restock_at`（HH:MM）→ 每日换货（锚点 + 一天 = 该时刻）。
    · `last` / 锚点晚于当前时钟时夹到 `now`：到点判据只可能「未到点」，形状也拒绝倒退的簿记。
    """
    period = _restock_period(cfg)
    target = _daily_target(cfg)
    restocked = min(int(last), now)
    rotated = restocked
    if target is not None:
        anchor = target if int(last) >= target else target - _DAILY
        rotated = min(anchor, now)
    book = {
        "size": 1,
        "rotated_at": rotated,
        "restocked_at": restocked,
        "slots": [{"slot": 0, "left": int(left), "stock": int(cfg["stock"]), "payload": key}],
    }
    shelf = Shelf(
        slots=1,
        clock=lambda: now,
        rotate_every=_DAILY if target is not None else None,
        restock_every=period,
        fill=lambda: [{"payload": key, "stock": int(cfg["stock"])}],
    )
    return shelf, {"shelf": book}

def _row(book: dict, prev: dict, last: int, now: int, keep: int) -> dict:
    """引擎簿记 → 存档行：剩余份数照抄；上次补货时刻只在本次真的换货/补货时前移。

    `keep` = 没到点时写回的「上次补货时刻」（存档行缺该字段时取当前时钟）。
    """
    moved = (book["rotated_at"] != prev["rotated_at"]
             or book["restocked_at"] != prev["restocked_at"])
    return {"left": int(book["slots"][0]["left"]), "last_restock": int(now) if moved else int(keep)}

def stock_state(sa_id: str, key: str, cfg: dict | None = None) -> dict:
    """读该店该商品共享库存状态；惰性初始化/补货后写回。
    返回 {left, max, last_restock}。未配置 stock → left=None（不限量）。"""
    cfg = cfg if cfg is not None else get_limit(key)
    max_stock = cfg.get("stock")
    if max_stock is None:
        return {"left": None, "max": None, "last_restock": _now_ts()}
    skey = _stock_key(sa_id, key)
    now = _now_ts()
    st = _load_state(db, skey)
    if st:
        left = int(st.get("left", int(max_stock)))
        last = int(st.get("last_restock", 0))
        keep = int(st["last_restock"]) if "last_restock" in st else now
    else:
        left, last, keep = int(max_stock), now, now
    shelf, state = _bucket(cfg, key, left, last, now)
    prev = state["shelf"]
    shelf.ensure(state)
    row = _row(state["shelf"], prev, last, now, keep)
    _save_state(db, skey, row)
    return {"left": row["left"], "max": int(max_stock), "last_restock": row["last_restock"]}

def _consume_shared(db, sa_id: str, key: str, cfg: dict, qty: int) -> bool:
    """原子扣店内共享库存 qty 件（先到先得）。不足返回 False。"""
    max_stock = cfg.get("stock")
    if max_stock is None:
        return True  # 不限量
    skey = _stock_key(sa_id, key)
    now = _now_ts()
    st = _load_state(db, skey)
    if st:
        left = int(st.get("left", 0))
        last = int(st.get("last_restock", 0))
        keep = int(st["last_restock"]) if "last_restock" in st else now
    else:
        left, last, keep = int(max_stock), now, now
    shelf, state = _bucket(cfg, key, left, last, now)
    prev = state["shelf"]
    ok = shelf.take(state, 0, qty)
    row = _row(state["shelf"], prev, last, now, keep)
    _save_state(db, skey, row)
    return ok

# ================= 个人每日限购 =================

def _day_key(group_id: str, qq_id: str, sa_id: str, key: str) -> str:
    """个人每日限购 key：shop_day_{gid}_{qid}_{sa}_{key}"""
    return f"shop_day_{group_id}_{qq_id}_{sa_id}_{key}"

def _day_bought(db, group_id: str, qq_id: str, sa_id: str, key: str) -> int:
    """查个人今日在该店该商品已购件数（跨天自动 0）。"""
    dk = _day_key(group_id, qq_id, sa_id, key)
    st = _load_state(db, dk)
    if not st or st.get("date") != _today():
        return 0
    return int(st.get("bought", 0))

def _bump_day(db, group_id: str, qq_id: str, sa_id: str, key: str, qty: int):
    """个人今日已购件数 +qty（跨天重置）。"""
    dk = _day_key(group_id, qq_id, sa_id, key)
    st = _load_state(db, dk)
    if not st or st.get("date") != _today():
        st = {"date": _today(), "bought": 0}
    st["bought"] = int(st.get("bought", 0)) + qty
    _save_state(db, dk, st)

# ================= 对外主入口 =================

def check_and_consume(group_id: str, qq_id: str, sa_id: str, key: str, qty: int) -> tuple:
    """购买前检查 + 原子扣减（店内共享库存 + 个人日限）。

    参数：
      sa_id  当前子区域（店铺）ID
      key    商品 key（'item:x'/'mat:x'/'equip:x'/'weapon:名'）
      qty    本次想买数量
    返回 (ok, reason, can_qty)：
      ok=True       可买（已扣库存+记日限），reason=''
      ok=False      不可买，reason 中文提示（'售罄'/'今日限购已达上限'等）
      can_qty       当前最多可买件数（qty 超限时的钳制值，供提示；不可买时=0）
    """
    cfg = get_limit(key)
    # 未配置任何限购 → 直接放行
    if not cfg:
        return True, "", qty

    per_day = cfg.get("per_day")
    stock = cfg.get("stock")
    # 计算可买量：min(日限余量, 库存余量, qty)
    day_left = None
    if per_day is not None:
        bought = _day_bought(db, group_id, qq_id, sa_id, key)
        day_left = max(0, int(per_day) - bought)
        if day_left <= 0:
            return False, _T.text("shop.limit_day_hit", per_day=per_day), 0
    stock_left = None
    if stock is not None:
        st = stock_state(sa_id, key, cfg)
        stock_left = st["left"]
        if stock_left is None:
            stock_left = qty
        if stock_left <= 0:
            return False, _T.static("shop.limit_stock_out"), 0

    # 可买量 = min(day_left, stock_left, qty)
    can = qty
    if day_left is not None:
        can = min(can, day_left)
    if stock_left is not None:
        can = min(can, stock_left)
    if can <= 0:
        return False, _T.static("shop.limit_temp"), 0
    if can < qty:
        # 整批购买语义：不足则不部分成交，给明确提示（与『购买 X 数量』显式报错风格一致）
        if day_left is not None and day_left < qty and (stock_left is None or stock_left >= qty):
            return False, _T.text("shop.limit_day_left", day_left=day_left), day_left
        if stock_left is not None and stock_left < qty:
            return False, _T.text("shop.limit_stock_left", stock_left=stock_left), stock_left
        return False, _T.static("shop.limit_qty_cap"), can

    # 扣共享库存
    if stock is not None:
        if not _consume_shared(db, sa_id, key, cfg, can):
            return False, _T.static("shop.limit_race"), 0
    # 记个人日限
    if per_day is not None:
        _bump_day(db, group_id, qq_id, sa_id, key, can)
    return True, "", can

# ================= 展示辅助 =================

def limit_label(sa_id: str, key: str) -> str:
    """商品行尾标注（如：『库存 3/5 · 今日限 1』），未配置返回 ''。"""
    cfg = get_limit(key)
    if not cfg:
        return ""
    parts = []
    if cfg.get("stock") is not None:
        try:
            st = stock_state(sa_id, key, cfg)
            left = st["left"] if st["left"] is not None else cfg["stock"]
            parts.append(_T.text("shop.limit_stock_ab", left=left, tot=cfg['stock']))
        except Exception:
            parts.append(_T.text("shop.limit_stock", tot=cfg['stock']))
    if cfg.get("per_day") is not None:
        parts.append(_T.text("shop.limit_day_tag", per_day=cfg['per_day']))
    return " · ".join(parts) if parts else ""
