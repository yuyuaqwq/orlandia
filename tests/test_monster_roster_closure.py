# -*- coding: utf-8 -*-
"""怪物名册「按名/按 id 引用」闭合门禁（`monster_roster` 域）。

守两条**会静默断**的引用族（它们不是 key 引用，断链时引擎/审计都不会喊）：
  ① `instances` 的怪 id（`boss` / `stages[].monsters[]` / `stages[].elite`）→ 必须在名册**表键**里；
  ② `drop_pools` 的 `mon:<中文名>` / `elite:<中文名>` **池键**里的名字 → 必须能用名册
     `name` ∪ `name_variants` ∪ `aliases` 反查到 id。

为什么值得守：这两族在包里是「有落点但不校验」的关系 —— 名册里改名/删怪时，
掉落池与副本会**照旧跑**，只是那个怪永远刷不出来、那件掉落永远不掉（没有任何报错）。
本门禁把它们钉成断言：改名必须被抓住。

跑法：python tests/test_monster_roster_closure.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import json                                                    # noqa: E402

# ★ 2026-09-14 B14 开关：宿主 `game/data/*.py` 已删（74.7k 行）、导出器
#   `scripts/export_game_package.py` 随之退役（归档 `scripts/_retired/`）→
#   名册 / 副本 / 掉落池三份数据改读**包内域 JSON**（导出的残影即今日真源，
#   与旧 `derive_*()` 的返回同源同形状：名册 380 / 副本 27 / 掉落池 596）。
sys.path.insert(0, HERE)   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402  ← 包根/引擎根发现（GWEN_FRAMEWORK_DIR 优先）
PKG_DIR = _paths.PKG_ROOT


def _domain(name: str):
    """读包内域 JSON（`content/data/<域>.json`）—— 顶层形状与该域门面一致。"""
    with open(os.path.join(PKG_DIR, "content", "data", name + ".json"), encoding="utf-8") as f:
        return json.load(f)

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def monster_ids_from(value, out=None):
    """递归收集形如 `b_*` / `m_*` / `e_*` 的怪 id 串。"""
    out = out if out is not None else set()
    if isinstance(value, str):
        if re.match(r"^(b|m|e)_[a-z0-9_]+$", value):
            out.add(value)
    elif isinstance(value, dict):
        for v in value.values():
            monster_ids_from(v, out)
    elif isinstance(value, list):
        for v in value:
            monster_ids_from(v, out)
    return out


def names_of(roster):
    """名册 {id: entry} → 名字 → 一组 id（重名在这里自然表现为"一对多"）。"""
    idx = {}
    for key, e in roster.items():
        if not isinstance(e, dict):
            continue
        cands = [e.get("name")] + list(e.get("name_variants") or []) + list(e.get("aliases") or [])
        for nm in cands:
            if isinstance(nm, str) and nm:
                idx.setdefault(nm, set()).add(key)
    return idx


def main():
    print("== 怪物名册闭合门禁（instances 怪 id / drop_pools 按名池键）==")
    roster = _domain("monster_roster")
    inst = _domain("instances")
    pools = _domain("drop_pools")
    check("名册非空且键都是怪 id", bool(roster) and all(
        re.match(r"^(b|m|e)_[a-z0-9_]+$", k) for k in roster), f"n={len(roster)}")

    # ① instances 怪 id ⊆ 名册键
    ids = set()
    for k, v in inst.items():
        for f in ("boss", "boss_data", "stages", "minions"):
            if f in v:
                monster_ids_from(v[f], ids)
    missing_ids = sorted(i for i in ids if i not in roster)
    check(f"instances 的怪 id 全部在名册里（{len(ids)} 个不同 id）", not missing_ids,
          f"未命中 {len(missing_ids)}: {missing_ids[:5]}")

    # ② drop_pools 的 mon:/elite: 池键名字 ⊆ 名册名字
    idx = names_of(roster)
    pnames = sorted({k.split(":", 1)[1] for k in pools if k.startswith(("mon:", "elite:"))})
    missing_names = [n for n in pnames if n not in idx]
    check(f"drop_pools 按名池键的名字全部能反查到 id（{len(pnames)} 个名字）", not missing_names,
          f"未命中 {len(missing_names)}: {missing_names[:5]}")

    # ③ 重名（一个名字对多个 id）必须**如实暴露**而不是被静默选一个
    dup = {n: sorted(v) for n, v in idx.items() if len(v) > 1}
    check(f"重名如实落进 name_peers（实测 {len(dup)} 个）", len(dup) > 0, str(len(dup)))
    bad = []
    for n, idlist in dup.items():
        for i in idlist:
            e = roster.get(i) or {}
            peers = set(e.get("name_peers") or [])
            if not peers.issuperset(set(idlist) - {i}):
                bad.append((i, n, sorted(peers)))
    check("每个重名怪的 name_peers 列全了同名兄弟 id", not bad, str(bad[:3]))

    # ④ 「基准 vs 场景」不能丢：有 lv 的条目必须带 lv_rule；有冲突的必须带 lv_variants
    nolvrule = [k for k, e in roster.items() if isinstance(e, dict) and e.get("lv") is not None
                and not e.get("lv_rule")]
    check("给了 lv 的条目都带 lv_rule（基准规则不静默）", not nolvrule, str(nolvrule[:5]))
    conf = [k for k, e in roster.items()
            if isinstance(e, dict) and len({v.get("lv") for v in (e.get("lv_variants") or [])
                                            if isinstance(v, dict)}) > 1]
    withvar = [k for k, e in roster.items()
               if isinstance(e, dict) and (e.get("lv_variants") or [])]
    check(f"跨来源等级冲突的怪都保留了 lv_variants（冲突 {len(conf)} 个 / 带对照 {len(withvar)} 个）",
          set(conf) <= set(withvar), str(sorted(set(conf) - set(withvar))[:5]))

    print(f"\n===== 结果：通过 {PASS} / {PASS + FAIL} =====")
    for f in FAILURES:
        print("  ·", f)
    print(json.dumps({"roster": len(roster), "inst_ids": len(ids), "pool_names": len(pnames),
                      "dup_names": len(dup), "lv_conflicts": len(conf)}, ensure_ascii=False))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
