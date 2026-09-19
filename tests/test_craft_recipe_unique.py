# -*- coding: utf-8 -*-
"""配方唯一性门禁：**同一张图纸 / 同一显示名**只许对应一条配方。

为什么需要（2026-09-20 实测）
-----------------------------
锻造与图纸面板都按「名字 → 配方」解析：
    `C.resolve("recipes", 名)`（图纸面板 bp 命令）· `craft.craft_recipe_search(名)`（锻造入口）
同一个显示名有多条配方时，命中哪条取决于**键序**（后写覆盖先写）⇒ 玩家实际能用哪条
**纯属 id 命名偶然**。实测 craft 域曾有 13 组这种数据（同一件装备两条配方，mats/gold 差
1.4~12 倍，其中 13 条永不可达 = 死数据），已按「仅删不可达那条（零行为变化）」清理，
本门禁守「一条装备一条配方」，防止复发。

判据（三族都查：craft / alchemy / cooking）
------------------------------------------
① **同图纸**（`blueprint` 非空）只许一条配方；
② **同显示名**（recipes 域 `display` 后的名字）只许一条配方；
③ 键序声明 `content/data/key_order.json` 的键集合与域文件一致（增删条目必须同步声明）。

跑法：`python tests/test_craft_recipe_unique.py`（退出码 0 = 全绿）。
"""
from __future__ import annotations

import collections
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _check import bind_check                                    # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list = []
check = bind_check(globals(), "PASS", "FAIL", "FAILURES")

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
DATA = os.path.join(PKG, "content", "data")

FAMILIES = {
    "craft": "craft.json",
    "alchemy": "alchemy.json",
    "cooking": "cooking.json",
}


def load(name):
    with io.open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    print("== 配方唯一性门禁（同图纸 / 同显示名 只许一条）==")
    key_order = load("key_order.json")

    for dom, fn in FAMILIES.items():
        path = os.path.join(DATA, fn)
        if not os.path.exists(path):
            check("域文件存在：%s" % fn, False, "缺文件")
            continue
        d = load(fn)
        check("%s 域非空（%d 条）" % (dom, len(d)), len(d) > 0)

        # ① 同图纸
        by_bp = collections.defaultdict(list)
        for k, v in d.items():
            if isinstance(v, dict) and (v.get("blueprint") or "").strip():
                by_bp[v["blueprint"]].append(k)
        dup_bp = {b: ks for b, ks in by_bp.items() if len(ks) > 1}
        check("%s：同图纸只对应一条配方（重复 %d 组）" % (dom, len(dup_bp)),
              not dup_bp, "；".join("%s→%s" % (b, ks) for b, ks in list(dup_bp.items())[:3]))

        # ② 同显示名
        by_name = collections.defaultdict(list)
        for k, v in d.items():
            if isinstance(v, dict):
                by_name[(v.get("name") or "").strip()].append(k)
        dup_name = {n: ks for n, ks in by_name.items() if n and len(ks) > 1}
        check("%s：同显示名只对应一条配方（重复 %d 组）" % (dom, len(dup_name)),
              not dup_name, "；".join("%s→%s" % (n, ks) for n, ks in list(dup_name.items())[:3]))

        # ③ 键序声明集合一致
        entry = key_order.get(dom)
        decl = entry.get("keys") if isinstance(entry, dict) else entry
        if isinstance(decl, list):
            miss = sorted(set(d) - set(decl))
            extra = sorted(set(decl) - set(d))
            check("%s：key_order 键集合与域一致（缺 %d / 多 %d）" % (dom, len(miss), len(extra)),
                  not miss and not extra,
                  "缺 %s 多 %s" % (miss[:3], extra[:3]))

    print("\n结果：通过 %d / 共 %d" % (PASS, PASS + FAIL))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("   ", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
