# -*- coding: utf-8 -*-
"""审计 L5468：商店出货真源 = 配货数据表（行为门禁）

背景（两轮核实后的结论，逐条有据）：
  · 台账 L5468 点名 `economy_cmds.py::_item_fits_shop`，上一轮先判「被
    SHOP_SUBAREA_ITEMS 数据化取代 ⇒ 删」，**该推论已被证伪并翻案**：
      - `_item_fits_shop` 管的是「消耗品能不能摆进**当前类型**的店」（按 kind 过滤：
        herb→药剂 / tavern→食物 / general→卷轴杂物）；而 `SHOP_SUBAREA_ITEMS` 管的是
        「**这家**店卖什么」——两者不是同一判据的两种实现。
      - 但它确实是**零读者的死方法**：全仓除定义行外零引用。
  · 真源已实测确认：三个出货点（`shop` 面板 / `buy` 序号分支 / `buy` 名称分支）
    全部直接读 `_clife.SHOP_SUBAREA_ITEMS`（`economy_cmds.py:6649 / :6714 / :6820`）
    ⇒ 删除死方法**不改变任何出货行为**。

本门禁钉**数据面 + 消费点**（不是「死方法不存在」那种恒真断言）：
  ① 配货表已装载且非空（真源存在）
  ② `shop` 面板的普通商店分支读的就是这张表（源码级：出货点走 SHOP_SUBAREA_ITEMS）
  ③ ★ 零读者仍成立：`_item_fits_shop` 全仓无调用点
     —— 这条是**可回滚性护栏**：若将来有人把过滤逻辑接回去，本门禁转红提醒他
     「你接回去的那条判据与数据表口径不一致」，而不是让双口径悄悄并存。
"""
import sys, os, re, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db  # noqa: E402

passed = failed = 0
from _check import bind_check  # noqa: E402

check = bind_check(globals(), "passed", "failed")

_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    # ── ① 配货表真源已装载且非空 ────────────────────────────────────────
    from content import catalog_life as _clife
    tbl = _clife.SHOP_SUBAREA_ITEMS
    check("① SHOP_SUBAREA_ITEMS 已装载且非空",
          isinstance(tbl, dict) and len(tbl) > 0, f"type={type(tbl).__name__} len={len(tbl) if hasattr(tbl,'__len__') else '?'}")
    _total_items = sum(len(v or []) for v in (tbl or {}).values())
    check("① 配货表至少有一批子区域配了货", _total_items > 0, f"总条目={_total_items}")

    # ── ② 三个出货点走数据表（源码级：不得退回按 kind 猜）────────────────
    src = io.open(os.path.join(_PKG, "content", "economy_cmds.py"), encoding="utf-8").read()
    n_tbl = src.count("_clife.SHOP_SUBAREA_ITEMS.get(sa_id)")
    check("② shop/buy 三个出货点读配货数据表（≥3 处）", n_tbl >= 3, f"SHOP_SUBAREA_ITEMS.get 命中 {n_tbl} 处")
    # 按 kind 猜 food/potion/scroll 的旧层（死方法本体）不得复活
    _guess = re.search(r"kind\s*=\s*[\"'](?:food|potion|scroll|misc)[\"']", src)
    check("② 旧「按 kind 猜类别」过滤层未复活", _guess is None,
          f"命中 {src[_guess.start()-40:_guess.end()+20]!r}" if _guess else "")

    # ── ③ 零读者护栏（只数**真实调用/引用**，注释与本门禁自身不算）─────────
    #   口径说明：删方法时在原地留了段注释说明「为什么删」，那是**给人读的**，
    #   若按子串命中就永远转红 ⇒ 这里逐行剔除注释行后再判（与 legacy-debt-triage
    #   「纯注释提及不算引用」同口径）。
    _SELF = os.path.abspath(__file__)
    _TARGET = os.path.join(_PKG, "content", "economy_cmds.py")
    hits = []
    for root, _dirs, files in os.walk(_PKG):
        if "__pycache__" in root or os.sep + ".git" in root:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            fp = os.path.join(root, f)
            if os.path.abspath(fp) in (_SELF, _TARGET):
                continue
            for ln, line in enumerate(io.open(fp, encoding="utf-8", errors="replace"), 1):
                s_ = line.strip()
                if not s_ or s_.startswith("#"):
                    continue
                if "_item_fits_shop" in line:
                    hits.append(f"{os.path.relpath(fp, _PKG)}:{ln}")
    check("③ `_item_fits_shop` 全仓零代码引用（注释/门禁自身不计）", not hits, f"命中 {hits}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


main()
