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
③ 键序声明 `content/data/key_order.json` 的键集合与域文件一致（增删条目必须同步声明）；
④ **带 `roster_id` 的配方**：`rec.lv` 必须 == `equip_roster[roster_id].lv`（#17 · 台账 §0 D12）。

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


def _roster_links(recipes):
    """带 roster_id 的配方 → [(配方 key, roster_id)]（roster_id 空串 = 不是名册产物）。"""
    out = []
    for k, v in recipes.items():
        if isinstance(v, dict):
            rid = (v.get("roster_id") or "").strip()
            if rid:
                out.append((k, rid))
    return out


def _lv_mismatches(recipes, roster):
    """带 roster_id 的配方 → [(配方 key, rid, rec.lv, roster.lv)]：lv 不一致 / 名册缺条目。

    D12 口径：产物走 `generate_roster_equip` ⇒ 实物等级取 `roster.lv`；
    `rec.lv` 只喂锻造门槛 / 图纸价 / 面板排序 ⇒ 是**派生副本**，逐条必须相等。
    """
    bad = []
    for k, rid in _roster_links(recipes):
        r = roster.get(rid)
        if not isinstance(r, dict) or r.get("lv") != recipes[k].get("lv"):
            bad.append((k, rid, recipes[k].get("lv"), (r or {}).get("lv")))
    return bad


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

    # ---------------- ④ 带 roster_id 的配方：等级 = 名册装备等级（#17 · 台账 §0 D12）----------------
    # 依据（实测 + 代码）：① `C.resolve("recipes", 名)` / 锻造入口都按配方表取 `rec.lv` 做**门槛**判定；
    #   ② 产物走 `generate_roster_equip(rid)`（`content/craft.py`）⇒ **实物 lv 取 `roster.lv`**；
    #   ③ `rec.lv` 另喂图纸价 / 面板排序 ⇒ 是**派生副本**，不是第二真源。
    # 曾实测 3 条错位（`72/72/85` vs `88/88/98`，`57027db` 已对齐）——本门禁守「不再漂回」。
    craft_d = load("craft.json")
    roster = load("equip_roster.json")
    check("equip_roster 域非空（%d 条）" % len(roster), len(roster) > 0)
    links = _roster_links(craft_d)
    check("craft：带 roster_id 的配方 %d / %d 条" % (len(links), len(craft_d)), len(links) > 0)
    dangling = [(k, rid) for k, rid in links if not isinstance(roster.get(rid), dict)]
    check("craft：roster_id 全部指向存在的名册装备（断链 %d）" % len(dangling), not dangling,
          "；".join("%s→%s" % (k, r) for k, r in dangling[:3]))
    bad = _lv_mismatches(craft_d, roster)
    check("craft：带 roster_id 的配方 lv 与名册逐条相等（一致 %d / 不一致 %d）"
          % (len(links) - len(bad), len(bad)), not bad,
          "；".join("%s(%s) rec.lv=%s vs roster.lv=%s" % t for t in bad[:3]))

    # 反证：把一条配方的 lv 改掉 ⇒ 判据必须报出来（否则本门禁是恒真的）
    probe = {k: dict(v) for k, v in craft_d.items()}
    k0, rid0 = links[0]
    probe[k0]["lv"] = int(probe[k0].get("lv") or 0) + 1
    cp = _lv_mismatches(probe, roster)
    check("反证：改一条 rec.lv ⇒ 判据必报（实测 %d 条 · 期望 1 条）" % len(cp),
          len(cp) == 1 and cp[0][0] == k0, str(cp[:2]))

    print("\n结果：通过 %d / 共 %d" % (PASS, PASS + FAIL))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("   ", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
