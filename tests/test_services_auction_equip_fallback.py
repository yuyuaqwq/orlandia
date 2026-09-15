# -*- coding: utf-8 -*-
"""`settle_auction` **「无 equip 兜底」分支常驻回归**（B4-QUEUE 口径：不覆盖的分支别只靠探针）。

背景（W1-A 反证实测）
--------------------
把 auction 的 C 句柄故意断到 `content.craft` 时，v104 / 文案门禁 / auction 定向测试
**都没有报红** ⇒ `settle_auction` 里那条
`equip = it.get("equip") or C.generate_equip(...)`（`content/auction.py:120`）的
**两条分支此前都没有常驻用例**。本文件把它钉成行为回归：

  A. `it["equip"]` 在位 → 必须**原样发放**那份存好的 equip（不许重新生成、不许改写字段）；
  B. `it` 无 `equip`（旧数据）→ **兜底生成**分支确实被走到，且生成器拿到的正是
     `(slot, lv, quality)` 这三个入参，发到背包里的就是生成器返回的那份对象；
  C. 兜底路径不许因生成器不可用而静默少发（宁红不软）。

判据是**行为**（发出去的装备内容 / 生成器入参 / 库存事实），不是「对象身份」。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import db, clean_db, make_player          # noqa: E402

import content.auction as auction                              # noqa: E402
import content.drops as drops                                  # noqa: E402

settle_auction = auction.settle_auction

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


#: 兜底生成器的调用记录（供判据 #3 用；替身是**透明转发**，不改变绑定与行为）
GEN_CALLS = []


class _BoundSpy(object):
    """`auction.C` 的透明替身：只把 `generate_equip` 包成「记录 + 转调原目标」。

    ★ 为什么用**代理**而不是直接给模块打补丁：`auction.C` 是 `PkgModule`（`__slots__` +
    `__getattr__` 惰性解析，**不能赋值属性**）。代理把「当前绑定目标」原样留着 ——
    绑定一旦被断（如断到 `content.craft`），转调也照样断，**替身不会替坏绑定兜底**。
    """

    def __init__(self, target):
        self._target = target
        self._prev = []                       # 支持嵌套（D 段要叠一层坏生成器）

    def __getattr__(self, name):
        return getattr(self._target, name)     # 其余属性原样透传（零行为改动）

    def generate_equip(self, *args, **kwargs):
        GEN_CALLS.append((tuple(args), dict(kwargs)))
        fn = self._prev[-1] if self._prev else getattr(self._target, "generate_equip")
        return fn(*args, **kwargs)

    def push(self, fn):
        self._prev.append(fn)

    def pop(self):
        self._prev.pop()


def _install_spy():
    """装透明代理，返回 `(spy, unspy)`；调用记录在模块级 `GEN_CALLS`。"""
    real_c = auction.C
    spy = _BoundSpy(real_c)
    auction.C = spy
    return spy, (lambda: setattr(auction, "C", real_c))


def _gen_calls():
    return list(GEN_CALLS)


def _reset_calls():
    del GEN_CALLS[:]


def _item(slot="weapon", lv=30, quality="purple", bids=None, equip_marker=None):
    it = {"id": 1, "name": "试炼之剑", "slot": slot, "lv": lv, "quality": quality,
          "stats": {}, "desc": "测试用", "base": 100, "buyout": 999999,
          "bids": dict(bids or {})}
    if equip_marker is not None:
        it["equip"] = equip_marker
    return it


def _cur(items):
    return {"etype": "auction", "ends_at": 4102444800, "data": {"items": items}}


def _one_inv(qid):
    inv = db.get_inventory("g1", qid)
    return inv[0] if inv else None


async def main():
    random.seed(20260915)          # 兜底分支真跑生成器：固定随机流，判据才可复现

    # 前置：兜底生成器必须在位（不在位 → 本文件的前提不成立，直接红，不许静默）
    check("P0 兜底生成器在位（content.drops.generate_equip 可调用）",
          callable(getattr(drops, "generate_equip", None)), type(drops).__name__)

    # =====================================================================
    print("【A. equip 在位 → 原样发放（覆盖短路分支，不许重新生成）】")
    clean_db()
    make_player("g1", "a1", "战士")
    stored = {"name": "存好的剑", "slot": "weapon", "quality": "purple", "lv": 30,
              "stats": {"atk": 777}, "price": 12345, "req": {}, "series": "s_probe"}
    spy, unspy = _install_spy()          # 透明代理：不换绑定目标，只记入参
    _reset_calls()
    try:
        lines = settle_auction(_cur([_item(bids={"a1": 500}, equip_marker=stored)]), "g1")
    finally:
        unspy()
    inv = _one_inv("a1")
    check("A1 拍卖结算报出赢家行", "拍得" in lines and "试炼之剑" in lines, lines[:120])
    check("A2 发到背包的就是存好的那份 equip（逐字段）",
          inv is not None and inv["data"].get("name") == stored["name"]
          and inv["data"].get("stats") == stored["stats"]
          and inv["data"].get("price") == stored["price"]
          and inv["data"].get("series") == stored["series"],
          inv)
    check("A3 短路分支下**未调用**兜底生成器（不是重新生成）",
          _gen_calls() == [], _gen_calls())

    # =====================================================================
    print("【B. 无 equip → 兜底分支（本用例的主目标：该分支此前无常驻覆盖）】")
    clean_db()
    make_player("g1", "b1", "战士")
    spy, unspy = _install_spy()
    _reset_calls()
    try:
        lines = settle_auction(_cur([_item(slot="armor", lv=42, quality="blue",
                                           bids={"b1": 700})]), "g1")
    finally:
        unspy()
    inv = _one_inv("b1")
    calls = _gen_calls()
    check("B1 兜底生成器被调用**恰一次**", len(calls) == 1, calls)
    check("B2 生成器入参 = (slot, lv, quality) 三个位置参，逐字来自拍卖条目",
          calls and calls[0][0] == ("armor", 42, "blue") and calls[0][1] == {}, calls)
    check("B3 发到背包的是**生成器返回的那份对象**（slot/lv/quality 结构对得上）",
          inv is not None and inv["data"].get("slot") == "armor"
          and inv["data"].get("lv") == 42
          and inv["data"].get("quality") == "blue"
          and isinstance(inv["data"].get("stats"), dict) and inv["data"]["stats"],
          inv)
    check("B4 生成物带真实名称（非空、非占位）",
          bool(str((inv or {}).get("data", {}).get("name") or "").strip()), inv)
    check("B5 结算文案仍正常（兜底不改变文案路径）", "拍得" in lines, lines[:120])

    # =====================================================================
    print("【C. 兜底 + 退还并存：同槽两件（一件有 equip、一件无）互不串味】")
    clean_db()
    make_player("g1", "c1", "战士")
    make_player("g1", "c2", "战士")
    marked = {"name": "存好的甲", "slot": "armor", "quality": "purple", "lv": 30,
              "stats": {"def": 555}, "price": 999, "req": {}, "series": "s_probe2"}
    spy, unspy = _install_spy()
    _reset_calls()
    try:
        lines = settle_auction(_cur([
            _item(slot="weapon", lv=10, quality="blue", bids={"c1": 300}),
            _item(slot="armor", lv=20, quality="purple", bids={"c1": 900},
                  equip_marker=marked),
        ]), "g1")
    finally:
        unspy()
    calls = _gen_calls()
    invs = db.get_inventory("g1", "c1")
    check("C1 只有无 equip 的那件走兜底（生成器恰一次）", len(calls) == 1, calls)
    check("C2 两件都发到同一赢家背包", len(invs) == 2, invs)
    check("C3 存好的那件未被兜底覆盖（stats 仍是标记值）",
          any(it["data"].get("stats") == marked["stats"] for it in invs), invs)
    check("C4 落槌价说明仍在", "系统回收" in lines, lines[:150])

    # =====================================================================
    print("【D. 兜底不许静默少发：生成器不可用时，宁可让它出声，也不许赢家空手、零日志】")
    clean_db()
    make_player("g1", "d1", "战士")
    spy, unspy = _install_spy()
    _reset_calls()

    def _boom(*a, **k):
        raise RuntimeError("生成器不可用（本用例故意）")

    spy.push(_boom)
    raised = None
    try:
        settle_auction(_cur([_item(slot="armor", lv=15, quality="blue",
                                   bids={"d1": 400})]), "g1")
    except Exception as exc:                                  # noqa: BLE001
        raised = exc
    finally:
        spy.pop()
        unspy()
    got = _one_inv("d1")
    check("D1 生成器坏掉时**出声**（异常浮出，不被 settle 吞成静默）",
          raised is not None, "无异常 → 静默降级")
    check("D2 也没有偷偷发一份「空装备」充数",
          got is None or bool(str(got["data"].get("name") or "").strip()), got)

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
