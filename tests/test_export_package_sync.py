#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""门禁：奥兰迪亚**包内数据冻结门禁**（★ 2026-09-14 B14 开关后）

跑法（系统 python 即可）：
    cd dragonfall && python tests/test_export_package_sync.py
退出码：0 = 全绿；1 = 有红（红行点名具体域 / 文件 / key）。

框架仓路径：默认 `C:/Users/yuyu/framework-engine`，可用 `$GWEN_FRAMEWORK_DIR` 覆盖。

═══════════════════════════════════════════════════════════════════════════
语义变更（2026-09-14，本文件头必须读完再改判据）
═══════════════════════════════════════════════════════════════════════════
旧版 = 「宿主真源 `game/data/*.py` → 包 JSON」的**同步门禁**：现场重新派生，再与仓库里已生成的
`content/data/*.json` 逐字节比对。

2026-09-14 **B14 开关**删掉了宿主 `game/data/*.py`（74,707 行 / 87 文件），单向导出器
`scripts/export_game_package.py` 与域插件 `scripts/export_domains/` **随之退役**
（归档 `scripts/_retired/`，语义账见其 `README.md`）→ **包内 `content/data|rules/*.json`
就是数据真源**，「现场重新派生」这件事不再存在。

于是本门禁改为**冻结门禁**：把必须恒定的事实写成断言（规模 / 形状 / 落盘规范 / 清单一致），
任何一条变了立刻红。**判据只加强不削弱** —— 旧版能抓的（少 key、字段丢失、条数漂移、
清单漂移、未声明域文件）现在照样抓，只是依据从「与真源对拍」变成「与冻结账对拍」。

═══════════════════════════════════════════════════════════════════════════
锁什么
═══════════════════════════════════════════════════════════════════════════
【1】items 域**冻结规模** = 900（合表后唯一物品数，**不是** 1704 = 900+598+206 —— 语义账见
     `scripts/_retired/README.md`）；key 匹配 `^[a-z][a-z0-9_]*$`。
【2】items 每条必填 `name`/`price`/`desc`（对齐 `schemas/item.schema.json` required）；
     price 非负；`quality` 有则必须 ∈ enum。
【3】逐条过**包内 schema**（`editor.packages.domain_status`；jsonschema 缺失时用框架校验器兜底）。
【4】清单 ↔ 文件：`game.json:domains` 声明的每个域都有数据文件（落点由域 `kind` 决定）；
     反向：`content/data|rules/` 下不存在未声明的孤儿文件。
【5】各域**冻结规模账**（值 = B14 收纳当刻实测：72 域 / 9125 条的那份账里的代表项）。
【6】**落盘规范**（编辑器保存自动满足；手改必须照此，否则每次保存都产生 diff 噪音）：
     UTF-8 无 BOM · LF 行尾 · `indent=2` · 末尾换行 · 外层键**升序**。
【7】包清单规范：`id`/`name`/`engine`/`entry`/`created`/`domains` 齐备；`id == "orlandia"`；
     `domains` 与包声明域、实际数据文件三方一致。
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ID = "orlandia"
sys.path.insert(0, HERE)   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402  ← 包根/引擎根发现（GWEN_FRAMEWORK_DIR 优先）
FW_ROOT = _paths.ENGINE_ROOT
PKG_DIR = _paths.PKG_ROOT
#: 「不是域表」的已登记辅助文件（`content/data|rules/` 下）：跳过孤儿扫描，**明示打印**，
#: 且不要求落盘规范（它们由各自机制维护）。第一条 = 文案规格表（P4′-B 后在包内，
#: 与 `texts` 域的数据文件 `texts.json`（导出投影）配对；真源/投影关系由
#: `tests/test_texts_specs_sync.py` 钉住）。
AUX_FILES = {"text_specs.json": "文案规格表（非域表；真源=包内，宿主那份是构建期镜像）",
             "tables.json": "存档表结构声明（非域表；包内真源，由引擎 `saintess_engine.store` 装载建表）"}

DATA_DIR = os.path.join(PKG_DIR, "content", "data")
RULES_DIR = os.path.join(PKG_DIR, "content", "rules")
MAN_PATH = os.path.join(PKG_DIR, "game.json")
ITEM_SCHEMA = os.path.join(PKG_DIR, "schemas", "item.schema.json")

MAX_REPORT = 20                  # 每类差异最多打印多少行

# ---- 冻结账（B14 收纳当刻实测；改这里 = 改口径，必须同时改 scripts/_retired/README.md）----
EXPECT_ITEMS = 900               # 合表后唯一物品数（不是 1704）
EXPECT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
FROZEN_COUNTS = {
    "items": 900, "equip_roster": 687, "subareas": 628, "exploration": 628,
    "drop_pools": 596, "pois": 457, "npcs": 431, "craft": 426, "monster_roster": 380,
    "monsters": 330, "skills": 305, "skill_up": 305, "quests": 238, "texts": 233,
    "commands": 194, "events": 146, "monster_mods": 140, "maps": 121, "worlds": 121,
    "achievements": 119, "item_templates": 99, "effect_rules": 85, "affixes": 76,
    "gather_pools": 68, "guild": 4, "instances": 27, "classes": 8, "races": 6,
    "pets": 16, "runes": 16, "passive_proc": 42, "dialogues": 39, "titles": 68,
}
# npcs 三表合表构成（旧版【12】的等价断言）
EXPECT_NPCS_SOURCES = {"town": 362, "wild": 47, "hidden": 22}
# items 的 quality 允许值**不在这里硬编**：从 `schemas/item.schema.json` 的 enum 读（单一真源）。
# 实测（2026-09-14）= ['blue', 'green', 'orange', 'purple', 'white']（品质色标，非英文品质名）。

PASS = 0
FAIL = 0
FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} {detail}")
        print(f"  ❌ {name} {detail}")
    return bool(cond)


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _pkg_module():
    """框架侧 `editor.packages`（域声明 / 落点 / 校验的唯一入口）。"""
    if os.path.abspath(FW_ROOT) not in sys.path:
        sys.path.insert(0, os.path.abspath(FW_ROOT))
    from editor import packages as PK      # noqa: PLC0415
    return PK


def main() -> int:
    print(f"框架仓 = {FW_ROOT}\n包     = {PKG_DIR}")
    print("（★ B14 开关后：包内 content/data|rules/*.json 即真源；导出器已退役 → 本门禁 = 冻结门禁）")
    if not os.path.isdir(PKG_DIR):
        print(f"❌ 包目录不存在：{PKG_DIR}")
        return 1
    PK = _pkg_module()

    # ---------------- 【7】包清单规范 ----------------
    print("\n【7】包清单（game.json）规范")
    man = PK.load_manifest(PKG_DIR)
    check("manifest 可读且为 dict", isinstance(man, dict) and bool(man), str(type(man)))
    for k in ("id", "name", "engine", "entry", "created", "domains"):
        check(f"manifest 有 {k} 字段", k in man, f"实际键={sorted(man)}")
    check(f"manifest.id == {PKG_ID!r}", man.get("id") == PKG_ID, repr(man.get("id")))
    declared = sorted(PK.declared_domain_ids(PKG_DIR))
    man_doms = sorted(man.get("domains") or [])
    check(f"manifest.domains == 包声明域（{len(declared)} 个）", declared == man_doms,
          f"清单独有 {sorted(set(man_doms) - set(declared))[:5]} / 声明独有 {sorted(set(declared) - set(man_doms))[:5]}")

    # ---------------- 【4】清单 ↔ 文件（双向） ----------------
    print("\n【4】清单 ↔ 数据文件（正反双向）")
    missing = []
    for d in declared:
        try:
            p = PK.domain_path(PKG_DIR, d)
        except KeyError as e:
            missing.append(f"{d}:{e}")
            continue
        if not os.path.isfile(p):
            missing.append(d)
    check(f"{len(declared)} 个声明域都有数据文件（落点由域 kind 决定）", not missing,
          f"缺 {missing[:MAX_REPORT]}")
    orphans = []
    aux_seen = []
    for sub, root in (("data", DATA_DIR), ("rules", RULES_DIR)):
        if not os.path.isdir(root):
            continue
        for fn in sorted(os.listdir(root)):
            if not fn.endswith(".json") or fn[:-5] in set(declared):
                continue
            if fn in AUX_FILES:
                aux_seen.append(f"content/{sub}/{fn}（{AUX_FILES[fn]}）")
                continue
            orphans.append(f"content/{sub}/{fn}")
    check("无孤儿域文件（data/rules 下每个 json 都已声明）", not orphans, f"孤儿 {orphans[:MAX_REPORT]}")
    print(f"  已登记辅助文件（非域表，跳过孤儿扫描）= {len(aux_seen)}：{aux_seen}")

    # ---------------- 【3】逐条过 schema + 非空 ----------------
    print("\n【3】逐域：条数 > 0 且逐条过 schema")
    empty, invalid = [], []
    counts = {}
    for d in declared:
        st = PK.domain_status(PKG_DIR, d)
        counts[d] = int(st.get("count", 0) or 0)
        if counts[d] == 0:
            empty.append(d)
        bad = list(st.get("invalid") or [])
        if bad or not st.get("ok"):
            invalid.append(f"{d}:{bad[:2]}")
    check(f"{len(declared)} 个域条数均 > 0（无静默空表）", not empty, f"空表 {empty[:MAX_REPORT]}")
    check(f"{len(declared)} 个域逐条校验 0 无效", not invalid, f"{invalid[:MAX_REPORT]}")
    print(f"  条目合计 = {sum(counts.values())}")

    # ---------------- 【5】冻结规模账 ----------------
    print("\n【5】冻结规模账（B14 收纳当刻实测）")
    for d, want in sorted(FROZEN_COUNTS.items()):
        got = counts.get(d, _read_json(os.path.join(DATA_DIR if os.path.isfile(
            os.path.join(DATA_DIR, d + ".json")) else RULES_DIR, d + ".json"), {}) or {})
        n = got if isinstance(got, int) else len(got)
        check(f"{d:<16} == {want}", n == want, f"实测 {n}")

    # ---------------- 【1】+【2】items 域专项 ----------------
    print("\n【1】items 域冻结规模 / key 形状")
    items = _read_json(os.path.join(DATA_DIR, "items.json"), {}) or {}
    check(f"items 条数 == {EXPECT_ITEMS}（合表后唯一物品，不是 1704）",
          len(items) == EXPECT_ITEMS, f"实测 {len(items)}")
    bad_keys = [k for k in items if not EXPECT_KEY_RE.match(k)]
    check("items 全部 key 匹配 ^[a-z][a-z0-9_]*$", not bad_keys, f"{bad_keys[:MAX_REPORT]}")

    print("\n【2】items 逐条字段（name/price/desc/quality）")
    q_enum = set(((((_read_json(ITEM_SCHEMA, {}) or {}).get("$defs") or {})
                   .get("item") or {}).get("properties") or {}).get("quality", {}).get("enum") or [])
    check("从 schemas/item.schema.json 读到 quality enum（非空）", bool(q_enum), f"实际={sorted(q_enum)}")
    miss_fields, bad_price, bad_q = [], [], []
    for k, v in items.items():
        if not isinstance(v, dict):
            miss_fields.append(f"{k}:非 dict")
            continue
        for f in ("name", "price", "desc"):
            if f not in v or v[f] in (None, ""):
                miss_fields.append(f"{k}:{f}")
        pr = v.get("price")
        if not isinstance(pr, (int, float)) or isinstance(pr, bool) or pr < 0:
            bad_price.append(f"{k}={pr!r}")
        q = v.get("quality")
        if q is not None and q not in q_enum:
            bad_q.append(f"{k}={q!r}")
    check("每条都有 name/price/desc", not miss_fields, f"{miss_fields[:MAX_REPORT]}")
    check("price 均为非负数", not bad_price, f"{bad_price[:MAX_REPORT]}")
    check("quality（有则）∈ schema enum", not bad_q, f"{bad_q[:MAX_REPORT]}")
    # schema 文件自身可用（缺了 → 上面【3】的校验就是空转）
    check("schemas/item.schema.json 存在", os.path.isfile(ITEM_SCHEMA), ITEM_SCHEMA)

    # ---------------- npcs 三表合表构成 ----------------
    print("\n【5b】npcs 域三表合表构成（town 362 + wild 47 + hidden 22 = 431）")
    npcs = _read_json(os.path.join(DATA_DIR, "npcs.json"), {}) or {}
    got_src: dict = {}
    for v in npcs.values():
        if isinstance(v, dict):
            got_src[str(v.get("source"))] = got_src.get(str(v.get("source")), 0) + 1
    check(f"npcs 条数 == {sum(EXPECT_NPCS_SOURCES.values())}", len(npcs) == sum(EXPECT_NPCS_SOURCES.values()),
          f"实测 {len(npcs)}")
    check("npcs source 分布 == 冻结账", {k: got_src.get(k, 0) for k in EXPECT_NPCS_SOURCES} == EXPECT_NPCS_SOURCES,
          f"实测 {got_src}")

    # ---------------- 【6】落盘规范 ----------------
    print("\n【6】落盘规范（UTF-8 无 BOM / LF / indent=2 / 末尾换行 / 外层键升序）")
    fmt_bad = []
    for sub in ("data", "rules"):
        root = os.path.join(PKG_DIR, "content", sub)
        if not os.path.isdir(root):
            continue
        for fn in sorted(os.listdir(root)):
            if not fn.endswith(".json"):
                continue
            p = os.path.join(root, fn)
            raw = open(p, "rb").read()
            probs = []
            if raw[:3] == b"\xef\xbb\xbf":
                probs.append("BOM")
            if b"\r\n" in raw:
                probs.append("CRLF")
            if not raw.endswith(b"\n"):
                probs.append("无末尾换行")
            try:
                obj = json.loads(raw.decode("utf-8-sig"))
            except ValueError:
                probs.append("JSON 坏")
                obj = None
            if isinstance(obj, dict):
                if list(obj) != sorted(obj):
                    probs.append("外层键非升序")
                if json.dumps(obj, ensure_ascii=False, indent=2) + "\n" != raw.decode("utf-8-sig"):
                    probs.append("非 indent=2 规范形")
            if probs:
                fmt_bad.append(f"content/{sub}/{fn}:{probs}")
    check("全部域文件满足落盘规范", not fmt_bad, f"{fmt_bad[:MAX_REPORT]}")

    # ---------------- 汇总 ----------------
    print(f"\n{'=' * 60}\n汇总：{PASS} 通过 / {FAIL} 失败")
    if FAILURES:
        print("红行：")
        for f in FAILURES:
            print("  ❌", f)
        print("\n修法：包内数据即真源 —— 改 `games/orlandia/content/<data|rules>/<域>.json`"
              "（或用编辑器 UI），别去改宿主 `game/data`（该目录已删）。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
