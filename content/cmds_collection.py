# -*- coding: utf-8 -*-
"""包内收藏册命令（`content/cmds_collection.py`）—— 『收藏册』的守卫/取参/业务/**渲染**。

终态形状（B18 样板定形；真源 = `overnight/B18_TERMINAL_SHAPE.md` §1.2）：
* handler 签名 `fn(env) -> list[str]`，**直接返回已渲染行**（本命令全 f-string，不涉文案表 →
  字面量随业务一起进包，宿主 `game/commands/collection.py` 里已无任何渲染代码）。
* 取参走引擎 `Env`：`env.arg_text("收藏册")`（= 旧 `self._strip_cmd(event, "收藏册")` 同口径）。

数据口（包内直连・不再靠宿主注入）
----------------------------------
* 背包 / 图鉴读写 = 包内存档层 `content/persistence`（B17 归包；与宿主 `db.*` **同一批函数对象**）；
* 显示名索引 = 包内 `content/index.py::display`（与宿主 `C.display` 同一个函数）；
* 读表与收藏判定 = 包内 `content/collection.py`。

行为逐字节不变（含宝箱入包副作用）；证据 = `overnight/W-B18-样板.md` 的 62 场景快照
（sha256 改前 = 改后）。
"""
from __future__ import annotations

from . import collection as _LIB
from .commands import register
from . import texts as _T                # ★ C 档 33b（2026-09-19）：文案表读口（本文件首次接入）
from .index import display as _display
from .persistence import add_item, get_bestiary, get_event_state, get_inventory, set_event_state

_SEP = "━━━━━━━━━━━━"


def _inv_names(group_id, qq_id) -> set:
    """背包持有物品名集合（key 转 display 名）—— 真源 `CollectionCmds._inv_names` 逐行。"""
    names = set()
    try:
        for it in get_inventory(group_id, qq_id):
            nm = (it.get("data") or {}).get("name") or it.get("key")
            if nm:
                names.add(str(nm))
            if it.get("key"):
                names.add(str(it["key"]))
    except Exception:                                        # noqa: BLE001
        pass
    return names


def _bestiary_names(group_id, qq_id) -> set:
    """图鉴击杀怪物名集合（bestiary key → display 名）—— 真源 `_bestiary_names` 逐行。"""
    names = set()
    try:
        for r in get_bestiary("", qq_id):
            nm = _display("monsters", r["monster"])
            names.add(str(nm))
            names.add(str(r["monster"]))
    except Exception:                                        # noqa: BLE001
        pass
    return names


def _progress(group_id, qq_id, book) -> tuple:
    """`(已收集数, 总条目数)` —— 判定归包（`content.collection.book_progress`）。"""
    return _LIB.book_progress(book, _inv_names(group_id, qq_id),
                              _bestiary_names(group_id, qq_id))


def _reward_line(rw: dict) -> str:
    """满套奖励行：宝箱 / 称号 / 永久属性 —— 真源 `_book_detail` 尾部逐行。"""
    rw_txt = []
    if rw.get("chest"):
        rw_txt.append(_T.static("collect.reward_chest"))
    if rw.get("title"):
        rw_txt.append(_T.text("collect.reward_title", title=rw['title']))
    if rw.get("bonus"):
        rw_txt.append(_T.static("collect.reward_bonus") % "、".join(f"{k}+{v}" for k, v in rw["bonus"].items()))
    return _T.static("collect.reward_head") + "、".join(rw_txt)


@register("collection", guards=("hook:player",), params=("cmd=收藏册",))
def collection(env) -> list:
    """『收藏册 [套名]』/『收藏册 领取 [套名]』：总览 / 明细 / 满套领奖。"""
    group_id = env.group_id
    qq_id = env.uid
    raw_arg = env.arg_text("收藏册")             # = 旧 `self._strip_cmd(event, "收藏册")`
    books = _LIB.books()                         # 包内表（源列表序）
    if not books:
        return [_T.static("collect.no_data")]
    # 『收藏册 领取』：满套册领宝箱
    if raw_arg.startswith("领取"):
        return _claim(group_id, qq_id, raw_arg, books)
    # 指定册名
    if raw_arg:
        target = next((b for b in books if b["name"] in raw_arg or raw_arg in b["name"]), None)
        if not target:
            return [_T.text("collect.not_found", arg=raw_arg)]
        return _detail(group_id, qq_id, target)
    # 总览
    lines = [_T.static("collect.head"), _SEP]
    for b in books:
        got, total = _progress(group_id, qq_id, b)
        mark = "✅" if got == total else "⬜"
        lines.append(_T.text("collect.row", mark=mark, name=b['name'], got=got, total=total, name2=b['name']))
    lines.append("")
    lines.append(_T.static("collect.tip"))
    return lines


def _detail(group_id, qq_id, book) -> list:
    """单册明细面板 —— 真源 `CollectionCmds._book_detail` 逐行。"""
    inv = _inv_names(group_id, qq_id)
    best = _bestiary_names(group_id, qq_id)
    got, total = _LIB.book_progress(book, inv, best)
    rw = book.get("reward") or {}
    lines = [f"📖 【{book['name']}】{got}/{total}", book.get("desc", ""), _SEP]
    for e in _LIB.entries(book):
        ok = _LIB.entry_collected(e, inv, best)
        mark = "✅" if ok else "⬜"
        nm = e.get("name", "")
        hint = e.get("hint", "")
        lines.append(f"{mark} {nm}（{hint}）" if hint else f"{mark} {nm}")
    if got == total:
        lines.append(_T.static("collect.done"))
    if rw.get("chest") or rw.get("title") or rw.get("bonus"):
        lines.append(_reward_line(rw))
    return lines


def _claim(group_id, qq_id, raw_arg, books) -> list:
    """满套领取面板 —— 真源 `CollectionCmds._claim_book_reward` 逐行（含宝箱入包副作用）。

    审计修复 #3（2026-09-18）：加「已领取」幂等记账（event_state 键
    `collection_claimed_{book_id}_{qq_id}`，无 schema 变更）——此前领取路径无任何
    领取记录，集齐后每次『收藏册 领取』都再发一个宝箱（无限刷金币/图纸）。
    记账只在宝箱入包成功后落，发放失败可重试、不吞奖励。
    """
    name = raw_arg.replace("领取", "", 1).strip()
    if name:
        books = [b for b in books if b["name"] in name or name in b["name"]]
    if not books:
        return [_T.static("collect.claim_none")]
    lines = []
    for b in books:
        got, total = _progress(group_id, qq_id, b)
        if got < total:
            lines.append(_T.text("collect.claim_not_full", name=b['name'], got=got, total=total))
            continue
        rw = b.get("reward") or {}
        chest = rw.get("chest")
        if chest:
            _claimed_key = f"collection_claimed_{b.get('id') or b.get('name')}_{qq_id}"
            if get_event_state(_claimed_key):
                lines.append(_T.text("collect.claim_done", name=b['name']))
                continue
            try:
                idata = _LIB.item_info(chest)     # 包内 items 域（真源 C.ITEMS/C.MATERIALS）
                if idata is None:
                    idata = {"name": chest, "type": "消耗品", "stackable": True, "price": 0}
                add_item(group_id, qq_id, chest, idata, count=1)
                set_event_state(_claimed_key, "1")
                lines.append(_T.text("collect.claim_ok", name=b['name'], item=idata.get('name', chest)))
            except Exception:                            # noqa: BLE001
                lines.append(_T.text("collect.claim_fail", name=b['name']))
        else:
            lines.append(_T.text("collect.claim_nochest", name=b['name']))
    return lines
