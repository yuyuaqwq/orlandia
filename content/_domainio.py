# -*- coding: utf-8 -*-
"""包内小工具单点（`content/_domainio.py`）—— 键型还原 / 序声明 / JSON 域读取 / 表形状 / 纯函数小工具。

为什么要它（`重复实现审计_报告.md` P0-4）
--------------------------------------
包内「读域小工具」按惯例**各自持一份**，其中这两族最整齐：

* `_int_keys` ×6（`tables.py` / `catalog_b143.py` / `catalog_items.py` /
  `catalog_life.py` / `catalog_rules.py` / `social_guild.py`）+ `config.py` 的同口径公共名
  `int_keys`（外部消费点 `crafting.py:29`）——**函数体逐字相同**，只有 docstring 措辞有别。
* `_order` ×4 逐字同体（`catalog_items.py` / `catalog_legacy.py` / `catalog_life.py` /
  `catalog_rules.py`）= 一行转发引擎装载口 `orders_of`。
* `_order` ×2域内变体（`catalog_quests.py` / `catalog_b143.py`）从**可重载全局** `_ORDERS`
  （placeholder 模式，重载后由 `_R.key_order.all()` 刷新）取条目 ——
  **取件源与装载口不是一回事** ⇒ 不并入 `order_of()`，只共用「形状校验」那一段
  （`require_key_order()`）。

**P0-4b（2026-09-19 续批）** —— 读口的余族同样收在这里：

* `_read_json` ×11（`mounts` / `player_cmds` / `mech/cond_procs` / `persistence/professions` /
  `flow/boss_script` / `flow/instance_gate` / `apply` / `loot` / `exploration` / `misc_cmds` /
  `mech/params`）—— **逐字同体**，只差「包内 `content/data/<name>` 拼接」还是「调用方给绝对路径」，
  ⇒ 拆成 `read_data_json(name, default, sub)`（8 处）与 `read_json(path, default)`（3 处）。
* `_read_domain` ×9（`talk_actions` / `shop_stock` / `smith_stock` / `instance_cmds` /
  `wild_king` / `world_cmds` / `achievements`）—— 全部同体（`_HERE/<sub>/<domain>.json`，坏则 `{}`）
  ⇒ `read_domain(domain, sub, default)`。
* `_read_domain` ×2 **fail-closed 变体**（`social_guild.py` 的 `guild.json` / `flow/weekly_progress.py`
  的 `weekly_quests.json`：硬编码单域 + 空表抛 `RuntimeError`）⇒ `read_data_json_strict()`。
* **未收的两处**：`content/dialogue.py` / `content/dialogue_conds.py` 的 `_read_domain` ——
  `tests/test_u1i4_dialogue_frozen.py` 把这两段源码逐段冻结（E 栏断言 `frozen == live`，
  缺符号直接 `KeyError`）且门禁自哈希 pinned ⇒ 该线收口后才能随冻结基准重采一并并入。

**P0-4d（2026-09-19 续批）** —— 表形状口同样收在这里：`num_sorted`（`catalog_b143` /
`catalog_items` 各一份，逐字同体）/ `ordered`（`catalog_b143` / `catalog_legacy` 的 `_ordered`，
报错文案由调用方绑定）/ `keyed_values`（`economy_cmds` / `panel` 的 `_domain_table`）/
`domain_section`（`mech/equip` / `mech/params`，逐字同体）/ `seq_rows`（`fishing` /
`catalog_life` / `catalog_quests` 三处内联「按 seq 还原插入序」）。

**P1-2 / P1-3（2026-09-19 同批）** —— 另两族**逐字相同**的包内纯函数小工具也收在这里：
`same_container`（`_same_container` ×11 中的 10 处；`catalog_quests` 那份因 `test_u1d2_quest_frozen.py`
的整文件 sha pin 未动）· `day_hash`（`daily_events` / `event_menu` / `time_weather` / `wild_king` 各一份，
`time_weather` 版多一行 docstring，一并采用）。

**W8（2026-09-20）—— 通用助手收进引擎**：上列 6 个**纯通用**口（零游戏知识、零内容包约定）
`read_json` / `int_keys` / `num_sorted` / `ordered` / `seq_rows` / `same_container` 已搬进
`saintess_engine/records/shapes.py`（行为逐字不变），本模块**只再导出**（42 个调用点零改动）；
`read_json` 同时消掉与引擎宿主装载口 `host/package.py` 的**重复实现**（改为同一份）。
仍留包内：`order_of` / `require_key_order`（吃 `key_order` 域这一内容包约定）·
`read_data_json` / `read_domain` / `read_data_json_strict` / `read_seq_domain` /
`keyed_values` / `domain_section`（吃包内落点 / 条目壳约定）· `day_hash`（内容侧的每日滚动口径）。

**有意未收**：`catalog_life` / `catalog_quests` 的 `_ordered`（序名由本模块解析 / 空序宽容 /
报错口径与前两处不同，硬合会改诊断措辞）；`dialogue.py` / `dialogue_conds.py` 的 `_main_quests`
（别线冻结门禁持有其字节）。

落点理由（与 `content/_pkgref.py` / `content/_hostref.py` 同一条纪律：**安全依赖面决定落点**）
----------------------------------------------------------------------------------
`tables.py` 在装配最早期被 import，且它派生的表遍布全包 ⇒ 本模块只允许依赖
**标准库 + `saintess_engine.records`**（`tables.py:38` 已在同一位置 import 它，是这条链上的
既有依赖），**不得** import 任何 `content.*` 子模块。故不并入 `content/index.py`
（那里带 `pypinyin` 与索引构建），也不并入 `config.py`（域读口，语义不同）。

行为口径：**逐字不变** —— 键型还原的「非整数键原样保留」、序声明的 raise 分支与消息措辞
（含 `%r` 与尾部提示）均按原样搬移，不做放宽。
"""
from __future__ import annotations

import json
import os

from saintess_engine.records import RecordsDeclarationError, orders_of, records_from_domain
# W8：6 个**纯通用**口搬进引擎 `records/shapes.py`，本模块只再导出（调用点零改动）——
from saintess_engine.records.shapes import (int_keys, num_sorted, ordered,  # noqa: F401
                                            read_json, same_container, seq_rows)

_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>


def order_of(name: str) -> list:
    """按名取包内序声明（引擎装载口 `orders_of`，落点由包内域声明派生）。"""
    return orders_of(_PKG_ROOT, name, domain="key_order")


def require_key_order(orders, name: str) -> list:
    """从**已加载**的 `key_order` 域条目表里取 `name` 的键序：缺条目 / 形状不对 → `raise`。

    给两处「从可重载全局 `_ORDERS` 取条目」的位点共用（`catalog_quests` / `catalog_b143`）。
    """
    ent = orders.get(name)
    keys = ent.get("keys") if isinstance(ent, dict) else None
    if not isinstance(keys, list) or not keys:
        raise ValueError(
            "key_order：读不到 %r 的键序声明（域缺该条目，或形状不是 {keys: [...]}）"
            "—— 序读不到就不许静默改成空表" % (name,))
    return keys


# ───────────────────────────────────────────────────────── 域读口（P0-4b：读 JSON / 读域文件）
_DATA_DIR = os.path.join(_HERE, "data")


def read_data_json(name: str, default=None, sub: str = "data"):
    """读包内 `content/<sub>/<name>`（`name` 带扩展名）—— 缺文件 / 坏 JSON → `default`，不抛。"""
    return read_json(os.path.join(_HERE, sub, name), default)


def read_domain(domain: str, sub: str = "data", default=None):
    """读包内 `content/<sub>/<domain>.json`（缺文件 / 坏 JSON → `default`，不抛）。

    缺省 `default=None` ⇒ 交回 `{}`（包内各原地读口的历史口径，逐字保留）。
    """
    return read_json(os.path.join(_HERE, sub, "%s.json" % domain),
                     {} if default is None else default)


def read_data_json_strict(name: str, label: str, hint: str) -> dict:
    """读包内 `content/data/<name>`，**fail-closed**：文件缺 → `OSError`；空表 / 顶层不是映射 → `RuntimeError`。

    给「空表 = 静默无内容」的单域读点用（`guild` / `weekly_quests`）：
    读不到就点名抛，绝不给空表。
    """
    path = os.path.join(_DATA_DIR, name)
    with open(path, encoding="utf-8") as f:
        tbl = json.load(f)
    if not isinstance(tbl, dict) or not tbl:
        raise RuntimeError("%s 域文件不可用（%s）—— 空表 = %s" % (label, path, hint))
    return tbl


def read_seq_domain(name: str, field=None, where: str = "") -> dict:
    """读包内「带 seq 的映射域」→ `{键: 条目}`，按 `seq` 还原源插入序（给了 field 就取单字段）。

    表体走引擎 records 读数口 `records_from_domain`（D-BATCH §5 许可的既有口）：
    域**声明缺项 / kind 无落点 / 文件不在盘上 / 声明与磁盘不符** → `RecordsDeclarationError`
    点名（**不静默空表**）；再叠本线自己的 fail-closed（D6 判据 4）：条目不是 dict / 缺 seq /
    seq 重复 / seq 不是 1..N 连续 / 取字段时条目没这个字段 → `raise` 点名。

    `where` = 调用方模块名，只用于错误消息前缀（各原地读口的措辞**逐字保留**）。
    """
    rec = records_from_domain(_PKG_ROOT, name)
    tbl = rec.all()
    if rec.missing or not tbl:
        raise RuntimeError("%s：域 %r 读不到（%s）—— 拒绝静默空表"
                           % (where, name, "；".join(rec.problems[:2]) or "空表"))
    rows: dict = {}
    for key, ent in tbl.items():
        if not isinstance(ent, dict):
            raise RuntimeError("%s：域 %s 条目 %r 不是 dict（是 %s）"
                               % (where, name, key, type(ent).__name__))
        seq = ent.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int):
            raise RuntimeError("%s：域 %s 条目 %r 缺 seq（= 源插入序）"
                               "—— 拒绝静默按字典序改序" % (where, name, key))
        if seq in rows:
            raise RuntimeError("%s：域 %s 的 seq=%r 重复 —— 拒绝静默取首个"
                               % (where, name, seq))
        rows[seq] = (key, ent)
    if sorted(rows) != list(range(1, len(rows) + 1)):
        raise RuntimeError("%s：域 %s 的 seq 不是 1..%d 连续整数 —— 拒绝按错序消费"
                           % (where, name, len(rows)))
    out: dict = {}
    for seq in sorted(rows):
        key, ent = rows[seq]
        if field is None:
            out[key] = {fk: fv for fk, fv in ent.items() if fk != "seq"}
        elif field in ent:
            out[key] = ent[field]
        else:
            raise RuntimeError("%s：域 %s 条目 %r 缺字段 %r —— 拒绝静默取空"
                               % (where, name, key, field))
    return out


# ───────────────────────────────────────────────────────── 表形状口（P0-4d：序 / 段 / 条目壳 / seq 还原）


def keyed_values(domain: str, *, keep_entries: bool = False) -> dict:
    """读包内域 `<domain>` 的**条目表** → 按名查值映射（fail-closed，不静默给空表）。

    域元数据唯一源 = 包内 `editor/domains.json`；落点由声明的 `kind` 派生（不手抄路径）。
    D5 各域的落盘形是编辑器口径的条目表 `{id: {"name": …, "value": …}}` ⇒ 缺省**只剥那一层壳**；
    `keep_entries=True` 返回原条目壳（需要 `name`/行序的读点用）。
    """
    rec = records_from_domain(_PKG_ROOT, domain)
    table = rec.all()
    if rec.missing or rec.problems or not isinstance(table, dict) or not table:
        raise RecordsDeclarationError(
            "D5 域 %r 读不到内容（空表/坏 JSON）：missing=%r problems=%r"
            % (domain, rec.missing, rec.problems[:3]))
    for k, e in table.items():
        if not isinstance(e, dict) or "value" not in e:
            raise RecordsDeclarationError(
                "D5 域 %r 的条目 %r 形状不是 {name, value}：%r" % (domain, k, e))
    return table if keep_entries else {k: e["value"] for k, e in table.items()}


def domain_section(domain: str, key: str) -> dict:
    """读包内域 `<domain>` 的 `<key>` 段（落点由 `editor/domains.json` 的 kind 派生）。

    ★ D7（2026-09-17）「数据进表」读口 —— 引擎 records（fail-closed）：
      域未声明 / kind 无落点 / 文件不在盘上 / 落点与声明不符 → `RecordsDeclarationError`；
      读不了 / 坏 JSON / 顶层不是映射 / 段缺 / 段不是非空映射 → 同样点名抛（**不静默给空表**）。
    """
    rec = records_from_domain(_PKG_ROOT, domain)
    section = rec.all().get(key)
    if not isinstance(section, dict) or not section:
        raise RecordsDeclarationError(
            "域 %r 读不到 %r 段（%s）：域文件缺 / 坏 JSON / 形状不符 → problems=%r"
            % (domain, key, rec.path, rec.problems))
    return section


# ───────────────────────────────────────────────────────── 纯函数小工具（P1-2 / P1-3 单源）


def day_hash(seed: int, salt: str = "") -> int:
    """日期哈希：全服一致、可查(roam/cycle/天气共用)"""
    h = seed * 2654435761 + (sum(ord(c) for c in salt) if salt else 0)
    return h & 0x7FFFFFFF
