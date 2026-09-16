# -*- coding: utf-8 -*-
"""U1-I2 冻结比对门禁：堆叠容器形状上移引擎 `saintess_engine/container/stack.py`。

守什么
------
1. **旧实现逐字冻结在本文件里**（`_FROZEN_BLOCK` = 搬运前 `content/persistence/inventory.py`
   的 `_trim_individuals` / `add_item` / `remove_item` / `count_item`，逐字，含 docstring）。
2. **三组 sha256 钉**（缺一组就有洞）：
   ① `sha256(冻结片段)` —— 逐函数 + 整体：冻结副本被偷改 = 红；
   ② `sha256(inspect.getsource(活实现))` —— 包侧新函数体被偷改 = 红
      （只钉片段会漏「函数体被偷改」；只钉活实现会漏「冻结副本被改成一致」）；
   ③ 引擎形状文件整文件 sha —— 形状被偷改 = 红（本批活实现跨了两个文件）。
   外加一组 **PIN_UNCHANGED**：内容侧取值/个体化函数必须与改动前逐字节相同（本次没动它们）。
3. **全量物品域逐格比对**：`content/data/items.json` 全部条目跑「旧实现 vs 新实现」，
   比**返回**（含异常类型）+ 比**落库**（`inventory` 每格的 item_data 文本与 count、`possessed`）；
   另有边界矩阵（未知键 / 空表 / count=0 / 超上限 / 装备 uuid / 混合堆叠 / 裸序列历史行 / 病态行）。
4. **有牙反证**：猴补破坏 3 件事（改一个比较边界 / 改返回结构 / 让容器少合并一次）→ 门禁必须变红；
   另加「**两处同时坏**」（合并顺序反转 + 截断改尾删）+ 一条 **FIFO 全序**断言
   —— 单故障矩阵证明不了顺序。猴补经 `exec` + `linecache` 在内存里喂给 `inspect`，
   **不写盘**，跑完还原。

跑法：python tests/test_u1i2_container_stack_frozen.py（exit=0 全绿）
"""
import ast
import hashlib
import inspect
import json
import linecache
import os
import sqlite3
import sys
import types

sys.dont_write_bytecode = True                      # 门禁只读：连 __pycache__ 都不落盘

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _paths                                                       # noqa: E402
from _engine_harness import C, db                                   # noqa: E402
import content.persistence.inventory as INV                         # noqa: E402
import saintess_engine.container.stack as STK                       # noqa: E402
from saintess_engine.container import Stack                         # noqa: E402

ENGINE_ROOT = _paths.ENGINE_ROOT
STACK_PATH = os.path.join(ENGINE_ROOT, "saintess_engine", "container", "stack.py")
ITEMS_PATH = os.path.join(PKG_ROOT, "content", "data", "items.json")
CLASSES_PATH = os.path.join(PKG_ROOT, "content", "data", "classes.json")

# ---- 冻结片段：搬运前 `content/persistence/inventory.py` 的 4 个形状函数，逐字 ----
_FROZEN_BLOCK = r'''def _trim_individuals(data, consumed):
    """v126.3 扣 count 后同步截断 tags（FIFO：先扣的先删个体标记）。

    返回新 item_data：
      - 带 tags 的对象 → 截断后剩余；截空移除 tags key（有 count 无个体，按原价兜底）
      - 裸数组（防御）→ 包对象截断
      - 非个体数据 → 原样
    """
    tags = None
    if isinstance(data, dict):
        tags = data.get("tags")
    elif isinstance(data, list):
        tags = data
    if not tags:
        return data
    rest = tags[consumed:]
    if isinstance(data, list):
        return {"tags": rest} if rest else {}
    out = dict(data)
    if rest:
        out["tags"] = rest
    else:
        out.pop("tags", None)
    return out


def add_item(group_id, qq_id, item_key, item_data: dict, count=1, tag: dict | None = None):
    """item_key: 唯一键(装备用 uuid 或 材料/消耗品用 id)；v46 自动转 ID 存储

    v126.2 tag：个体属性标记（鱼获重量/大小）——随 count 同生共死（remove/sell 按 FIFO
    截断），count 恒 >= len(tags)。
    v126.3 瘦身：存储时类属性不落库（_slim），个体属性存 item_data["tags"] 对象包装，
    读取时 _hydrate 水合补全类属性。
    """
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0 or count > 9999999:
        # F1 P1-3：数量非法（<=0 / 超大）直接拒绝，防负资产/内存膨胀
        return False
    item_key = _key_to_id(item_key, item_data)
    slim = _slim(item_key, item_data, tag)
    stackable = item_data.get("stackable", True) if isinstance(item_data, dict) else True
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT count, item_data FROM inventory WHERE qq_id=? AND item_key=?",
                (qq_id, item_key),
            ).fetchone()
            if row and stackable:
                if isinstance(slim, dict) and slim.get("tags") is not None:
                    # 堆叠 + 个体数据：合并 tags 数组（上限截断丢最旧）
                    _old = json.loads(row["item_data"])
                    _old_tags = _old.get("tags", []) if isinstance(_old, dict) else (
                        _old if isinstance(_old, list) else [])
                    _new_tags = (_old_tags + slim["tags"])[-FISH_TAGS_MAX:]
                    # v126.4 审计 P2：合并只写 {"tags": ...} 会丢 _slim 为配置未命中
                    # 动态物品保留的类属性兜底 → 保留 slim 的非 tags 字段（正常配置命中时为空）
                    _merged = {k: v for k, v in slim.items() if k != "tags"}
                    _merged["tags"] = _new_tags
                    conn.execute(
                        "UPDATE inventory SET count=count+?, item_data=? WHERE qq_id=? AND item_key=?",
                        (count, json.dumps(_merged, ensure_ascii=False), qq_id, item_key),
                    )
                else:
                    conn.execute(
                        "UPDATE inventory SET count=count+? WHERE qq_id=? AND item_key=?",
                        (count, qq_id, item_key),
                    )
            elif row:
                # v110 审计修复：同 key 已存在且不可堆叠（如重复 uuid 场景）——
                # 原裸 INSERT 撞主键抛 sqlite3.IntegrityError，公共函数应设防，退化累加
                conn.execute(
                    "UPDATE inventory SET count=count+? WHERE qq_id=? AND item_key=?",
                    (count, qq_id, item_key),
                )
            else:
                # v168 冒险手册：物品首次入包（新格 INSERT）→ 记曾拥有（永久）
                record_possessed_conn(conn, qq_id, item_key, item_data)
                conn.execute(
                    "INSERT INTO inventory (qq_id, item_key, item_data, count) VALUES (?,?,?,?)",
                    (qq_id, item_key, json.dumps(slim, ensure_ascii=False), count),
                )
            conn.commit()
        finally:
            conn.close()


def remove_item(group_id, qq_id, item_key, count=1):
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0 or count > 9999999:
        # F1 P1-3：非法数量直接拒绝（<=0 会误删整堆或增库存；超大 count 有溢出/DoS 面）
        return False
    item_key = _key_to_id(item_key)
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT count, item_data FROM inventory WHERE qq_id=? AND item_key=?",
                (qq_id, item_key),
            ).fetchone()
            if not row:
                return False
            if row["count"] <= count:
                conn.execute(
                    "DELETE FROM inventory WHERE qq_id=? AND item_key=?",
                    (qq_id, item_key),
                )
            else:
                # v126.2/126.3 同步截断个体数组（FIFO：先扣的先删个体标记，count >= len(tags) 恒成立）
                _new = _trim_individuals(json.loads(row["item_data"]), count)
                conn.execute(
                    "UPDATE inventory SET count=count-?, item_data=? WHERE qq_id=? AND item_key=?",
                    (count, json.dumps(_new, ensure_ascii=False), qq_id, item_key),
                )
            conn.commit()
            return True
        finally:
            conn.close()


def count_item(group_id, qq_id, name):
    """按物品名称/ID 统计背包中数量(材料类，key 为 mat_名称)"""
    kid = _key_to_id(name)
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT item_key, item_data, count FROM inventory WHERE qq_id=?",
                (qq_id,),
            ).fetchall()
            total = 0
            for r in rows:
                d = _hydrate(r["item_key"], json.loads(r["item_data"]))
                if d.get("name") == name or r["item_key"] == kid:
                    total += r["count"]
            return total
        finally:
            conn.close()'''

_FROZEN_NAMES = ("_trim_individuals", "add_item", "remove_item", "count_item")

# ---- sha256 钉（由 out/_gen_frozen_gate.py 一次性算出；改冻结片段/活实现/形状都必须显式重钉）----
PIN_FROZEN = {
    '_trim_individuals': 'dcf6f59e4c17b5e70c433c1d31f08c71d5afe59a5a3820023db21ebdc15e8a35',
    'add_item': '631cd652b9b7a1885f0ea6560df90870b913022129592e6a547c8c0c2bb17008',
    'remove_item': '976f49c2cab48160a44ec14d26ec357678e5ace51334c4d4ffbc5d3de5f8d7ec',
    'count_item': 'ed817a36ba48e83ff1cd0e4a0351505d775099f4902fe751a28d83030b75235a',
    '__all__': '585955b96b0dac1cfcc86206ce92d8da6d705314ff37dfda83781b7a8fc4a212',
}
PIN_LIVE = {
    '_trim_individuals': '5775ef5bd3f1bacabcc8caa366856873411c2e4be048bf6893d29886e39c1617',
    'add_item': '11360ea619c77860b8c450dff95dde7725af295e7555ff706ab3a45082f7ccd8',
    'remove_item': '85a6cca2454ca7ecac8badc23ff67d389b69c596b5f63f3ab442f7e973c6805d',
    'count_item': '2231a874281b2562c2ca7f3aa49757687c3783644c9098bbd99ce78617f002ea',
}
PIN_UNCHANGED = {
    '_snapshot_one': 'a15903c895314c6413818cbd855f50852ece465f9b6ff8d90a6f6dd462e7ffa2',
    '_class_attrs': 'c932d522e352d6b93f455f34db529715224a23071e978db5d58fca137b6e2b90',
    '_slim': 'e3a9ba2ba2f66871951fbfa20339aac3b70cba8f1b6adbd7dac7ecfe1dfc51b2',
    '_hydrate': '82cd9ea4e0e518dcd8283e4c36628167d21c93807d1a044d4fbe8087b265b5ad',
    '_key_to_id': '33a8570343791c3c8dc13b8b3f69589fb99c5c18ce29b78c73e67ba1587b0c67',
    '_migrate_upgrade_lv': '40500531462925e03ae704bc6f783c83b02a5903ff03fc91fb1c785500292e4a',
    '_is_equip_uuid_key': '265219d469a5e4cd94686f52f525623a878565ff9f40a3b38147a6756682b0ea',
    '_possessed_key': '250ebc08221f202291f143e105b1688101284c81adaee678be7ea56c2ba2c173',
    'get_inventory': 'd604fea4ae628e86c0142989bf5114827d5d903799dbbb48daa0127adc628505',
    'update_item_data': '0ab9c90bc72628c654bb360668272deb15973913a6259fe6f9dfe1e4680c8bd9',
    'sell_item_atomic': 'b9dd25d08d5af571b42a5c2da482d120e61fbd87dbab6b2f4e2d6f2f069a7f29',
    'record_possessed_conn': '154da60c597045dc209e027e94b5a0532d41ad0235d47b4a1b0b7c757a017d30',
    'record_possessed': 'a6889f7419bbcd1505419866891f3c73d831d472d684e4a579113d76b5cefdb4',
    'get_possessed': '0d422931c77f792b127b5d0ee13a500354bbd4d7bc643d4346bc358e329637e8',
    'get_possessed_rows': '01b7d002c9efd8d124ef4412caedd83dbfa107713ed540a046260eff52af9bc0',
    'count_possessed': '8b91914a1e2aafaeb9f1d30b65c3edc49f92cc9797196095d6bdb9b5a6df0b0c',
}
PIN_ENGINE = '8eb5b50a81ed7d924387627e6034dc234dc11396ffe0a9ae2f6f450173581ad4'

# ============================================================
# 通用件
# ============================================================
PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ❌ {name} {detail}")


def _lf(s):
    """统一行尾 + 去首尾空行（hash 比较用）。"""
    return s.replace("\r\n", "\n").strip("\n")


def _sha(s):
    return hashlib.sha256(_lf(s).encode("utf-8")).hexdigest()


def _frozen_funcs():
    """从冻结块切出「函数名 → 逐字源码」（与 inspect.getsource 同口径：def 行到函数末行）。"""
    tree = ast.parse(_FROZEN_BLOCK)
    lines = _FROZEN_BLOCK.split("\n")
    out = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        out[node.name] = "\n".join(lines[start - 1:node.end_lineno])
    return out


_FROZEN_FUNCS = _frozen_funcs()

# 旧实现命名空间：以**活模块的全局**打底（json / _lock / _connect / _slim / _key_to_id /
# FISH_TAGS_MAX / record_possessed_conn 等取值与句柄都是同一个），冻结块覆盖 4 个形状函数。
_OLD_NS = dict(vars(INV))
exec(compile(_FROZEN_BLOCK, "<u1i2-frozen>", "exec"), _OLD_NS)      # noqa: S102 门禁用冻结副本
_OLD = types.SimpleNamespace(**{n: _OLD_NS[n] for n in _FROZEN_NAMES})


def _call(fn, *a, **k):
    """调用并吞异常：返回 `("ok", 值)` / `("exc", 异常类名)`（异常也要逐字节比）。"""
    try:
        return ("ok", fn(*a, **k))
    except Exception as e:                                          # noqa: BLE001
        return ("exc", type(e).__name__)


def _db_connect():
    conn = sqlite3.connect(db.db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _raw_exec(sql, params=()):
    conn = _db_connect()
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _reset():
    db.init_db()
    conn = _db_connect()
    try:
        conn.execute("DELETE FROM inventory")
        conn.execute("DELETE FROM possessed")
        conn.commit()
    finally:
        conn.close()


def _rows(qq):
    """该玩家的库存格（按 key 排）+ 曾拥有 key —— 逐格比对的取值面。"""
    conn = _db_connect()
    try:
        inv = [(r["item_key"], r["item_data"], r["count"]) for r in conn.execute(
            "SELECT item_key, item_data, count FROM inventory WHERE qq_id=? ORDER BY item_key",
            (qq,))]
        pos = [r["item_key"] for r in conn.execute(
            "SELECT item_key FROM possessed WHERE qq_id=? ORDER BY item_key", (qq,))]
        return inv, pos
    finally:
        conn.close()


def compare_scenarios(scenarios):
    """旧实现 vs 新实现：每个场景各跑一遍（独立 qq），比返回 + 比落库。返回违规清单。"""
    bad = []
    _reset()
    for i, (name, run) in enumerate(scenarios):
        qo, qn = "old_%d" % i, "new_%d" % i
        ro, rn = run(_OLD, qo), run(INV, qn)
        if ro != rn:
            bad.append("%s：返回不同 old=%r new=%r" % (name, ro, rn))
        so, sn = _rows(qo), _rows(qn)
        if so != sn:
            bad.append("%s：落库不同 old=%r new=%r" % (name, so, sn))
    return bad


# ============================================================
# 场景表
# ============================================================
def _item_scenario(key, data):
    """单条目标准流水：新格 → 同 key 累加 → 带个体记录追加 → 计数 → 扣 1 → 扣空。"""
    name = data.get("name")

    def run(api, qq):
        out = [_call(api.add_item, "g", qq, key, dict(data), 2)]
        out.append(_call(api.add_item, "g", qq, key, dict(data), 3))
        out.append(_call(api.add_item, "g", qq, key, dict(data), 1, {"size": 1.0}))
        out.append(_call(api.count_item, "g", qq, name))
        out.append(_call(api.remove_item, "g", qq, key, 1))
        out.append(_call(api.count_item, "g", qq, name))
        out.append(_call(api.remove_item, "g", qq, key, 999))
        return out

    return ("item:%s" % key, run)


def _sc_unknown_key(api, qq):
    return [
        _call(api.add_item, "g", qq, "虚空之物xyz", {"name": "虚空之物", "type": "怪", "price": 3}, 2),
        _call(api.count_item, "g", qq, "虚空之物"),
        _call(api.add_item, "g", qq, "虚空之物xyz", {"name": "虚空之物", "type": "怪", "price": 3},
              1, {"a": 1}),
        _call(api.remove_item, "g", qq, "虚空之物xyz", 1),
    ]


def _sc_empty_table(api, qq):
    return [
        _call(api.count_item, "g", qq, "银鳞鱼"),
        _call(api.remove_item, "g", qq, "mat_yin_lin_yu", 1),
        _call(INV.get_inventory, "g", qq),          # 读口本次未动，两侧同一个函数
    ]


def _sc_bad_count(api, qq):
    key = "mat_yin_lin_yu"
    out = []
    for c in (0, -1, True, 99999999, 10000000, 1.5, "2", None):
        out.append(_call(api.add_item, "g", qq, key, {"name": "银鳞鱼"}, c))
        out.append(_call(api.remove_item, "g", qq, key, c))
    out.append(_call(INV.get_inventory, "g", qq))    # 读口本次未动，两侧同一个函数
    return out


def _sc_cap_501(api, qq):
    key = "mat_yin_lin_yu"
    data = {"name": "银鳞鱼", "type": "鱼", "stackable": True, "price": 6, "quality": "white"}
    for i in range(501):
        _call(api.add_item, "g", qq, key, dict(data), 1, {"i": i})
    return [
        _call(api.count_item, "g", qq, "银鳞鱼"),
        _call(api.add_item, "g", qq, key, dict(data), 1, {"i": 501}),
        _call(api.remove_item, "g", qq, key, 2),
    ]


def _sc_equip_uuid(api, qq):
    roster = getattr(C, "EQUIP_ROSTER", None) or {}
    nm = None
    for _k, _v in roster.items():
        nm = (_v or {}).get("name")
        if nm:
            break
    out = [
        _call(api.add_item, "g", qq, "eq_72d48ebe", {"name": nm or "无名装备"}, 1),
        _call(api.add_item, "g", qq, "eq_72d48ebe", {"name": nm or "无名装备"}, 1),
        _call(api.remove_item, "g", qq, "eq_72d48ebe", 1),
        _call(api.add_item, "g", qq, "eq_00000000", {"name": "查不到的装备"}, 1),
    ]
    return out


def _sc_mixed_stack(api, qq):
    key = "mat_yin_lin_yu"
    return [
        _call(api.add_item, "g", qq, key, {"name": "银鳞鱼", "stackable": False}, 1, {"n": 1}),
        _call(api.add_item, "g", qq, key, {"name": "银鳞鱼", "stackable": True}, 1, {"n": 2}),
        _call(api.add_item, "g", qq, key, {"name": "银鳞鱼", "stackable": False}, 2, {"n": 3}),
        _call(api.add_item, "g", qq, key, {"name": "银鳞鱼", "stackable": True}, 1),
        _call(api.remove_item, "g", qq, key, 1),
        _call(api.remove_item, "g", qq, key, 4),
    ]


def _sc_legacy_list(api, qq):
    _raw_exec("INSERT INTO inventory (qq_id, item_key, item_data, count) VALUES (?,?,?,?)",
              (qq, "legacy_list", '[{"a": 1}, {"a": 2}]', 2))
    return [
        _call(api.remove_item, "g", qq, "legacy_list", 1),
        _call(api.add_item, "g", qq, "legacy_list", {"name": "旧物", "type": "材料"}, 1, {"a": 3}),
        _call(api.remove_item, "g", qq, "legacy_list", 9),
    ]


def _sc_legacy_scalar(api, qq):
    _raw_exec("INSERT INTO inventory (qq_id, item_key, item_data, count) VALUES (?,?,?,?)",
              (qq, "legacy_scalar", '"x"', 2))
    return [
        _call(api.remove_item, "g", qq, "legacy_scalar", 1),
        _call(api.add_item, "g", qq, "legacy_scalar", {"name": "怪数据"}, 1),
        _call(api.remove_item, "g", qq, "legacy_scalar", 5),
    ]


def _sc_zero_count_row(api, qq):
    _raw_exec("INSERT INTO inventory (qq_id, item_key, item_data, count) VALUES (?,?,?,?)",
              (qq, "zero_row", '{"tags": []}', 0))
    return [
        _call(api.count_item, "g", qq, "zero_row"),
        _call(api.add_item, "g", qq, "zero_row", {"name": "零格"}, 1),
        _call(api.remove_item, "g", qq, "zero_row", 1),
    ]


def _sc_null_tags(api, qq):
    _raw_exec("INSERT INTO inventory (qq_id, item_key, item_data, count) VALUES (?,?,?,?)",
              (qq, "null_tags", '{"tags": null}', 1))
    return [_call(api.add_item, "g", qq, "null_tags", {"name": "甲"}, 1, {"a": 1})]


def _sc_weird_tags(api, qq):
    _raw_exec("INSERT INTO inventory (qq_id, item_key, item_data, count) VALUES (?,?,?,?)",
              (qq, "weird_tags", '{"tags": {"k": 1}}', 1))
    return [_call(api.add_item, "g", qq, "weird_tags", {"name": "乙"}, 1, {"a": 1})]


def _sc_none_data(api, qq):
    return [
        _call(api.add_item, "g", qq, "mat_yin_lin_yu", None, 1),
        _call(api.add_item, "g", qq, "mat_yin_lin_yu", {}, 1),
        _call(api.count_item, "g", qq, "银鳞鱼"),
    ]


BOUNDARY_SCENARIOS = [
    ("未知键", _sc_unknown_key),
    ("空表", _sc_empty_table),
    ("非法件数", _sc_bad_count),
    ("超上限 501", _sc_cap_501),
    ("装备 uuid", _sc_equip_uuid),
    ("混合堆叠", _sc_mixed_stack),
    ("裸序列历史行", _sc_legacy_list),
    ("标量历史行", _sc_legacy_scalar),
    ("count=0 历史行", _sc_zero_count_row),
    ("tags:null 病态行", _sc_null_tags),
    ("tags:非序列 病态行", _sc_weird_tags),
    ("data=None/{}", _sc_none_data),
]


# ============================================================
# ① 冻结契约（双 sha + 未动函数 + 引擎文件）
# ============================================================
def frozen_violations():
    bad = []
    if set(_FROZEN_FUNCS) != set(_FROZEN_NAMES):
        bad.append("冻结块函数集 != 冻结清单：多=%s 缺=%s"
                   % (sorted(set(_FROZEN_FUNCS) - set(_FROZEN_NAMES)),
                      sorted(set(_FROZEN_NAMES) - set(_FROZEN_FUNCS))))
    if _sha(_FROZEN_BLOCK) != PIN_FROZEN.get("__all__"):
        bad.append("冻结片段整体 sha256 不匹配（冻结副本被改）")
    for n in _FROZEN_NAMES:
        if n in _FROZEN_FUNCS and _sha(_FROZEN_FUNCS[n]) != PIN_FROZEN.get(n):
            bad.append("冻结片段 %s 的 sha256 不匹配" % n)
    return bad


def live_violations():
    bad = []
    for n in _FROZEN_NAMES:
        fn = getattr(INV, n, None)
        if fn is None:
            bad.append("活实现缺失：%s" % n)
            continue
        got = _lf(inspect.getsource(fn))
        if _sha(got) != PIN_LIVE.get(n):
            bad.append("活实现 %s 的 sha256 不匹配（函数体被偷改）：%s != %s"
                       % (n, _sha(got), PIN_LIVE.get(n)))
    return bad


def unchanged_violations():
    bad = []
    for n, pin in PIN_UNCHANGED.items():
        fn = getattr(INV, n, None)
        if fn is None:
            bad.append("内容侧函数缺失：%s" % n)
            continue
        got = _sha(inspect.getsource(fn))
        if got != pin:
            bad.append("内容侧取值/个体化函数 %s 被改动（本次必须逐字节不动）" % n)
    return bad


def engine_pin_violations():
    src = open(STACK_PATH, encoding="utf-8").read()
    got = _sha(src)
    if got != PIN_ENGINE:
        return ["引擎形状文件 %s 的 sha256 不匹配（形状被偷改）" % os.path.basename(STACK_PATH)]
    return []


# ============================================================
# ② 行为等价（旧实现 vs 新实现）
# ============================================================
def behavior_violations(items=None):
    """全量物品域（默认 items.json 全部条目）+ 边界矩阵 + `_trim_individuals` 纯函数矩阵。"""
    bad = []
    if items is None:
        items = load_items()
    bad += ["全量：" + x for x in compare_scenarios([_item_scenario(k, d) for k, d in items])]
    bad += ["边界：" + x for x in compare_scenarios(BOUNDARY_SCENARIOS)]
    bad += ["截断定格：" + x for x in _trim_matrix_violations()]
    return bad


def load_items():
    with open(ITEMS_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    return sorted(doc.items())


def _trim_matrix_violations():
    """`_trim_individuals`（形状下移的唯一助手）纯函数矩阵：旧 vs 新逐例相等。"""
    shapes = [
        {}, {"tags": []}, {"tags": None}, {"tags": [1, 2, 3]}, {"name": "x", "tags": [1, 2]},
        {"name": "x", "tags": []}, [1, 2, 3], [], "str", 5, None,
        {"tags": "notalist"}, {"tags": (1, 2)}, {"a": 1}, {"a": 1, "tags": [{"s": i} for i in range(6)]},
    ]
    bad = []
    for i, d in enumerate(shapes):
        for consumed in (0, 1, 3, 999):
            a = _call(_OLD._trim_individuals, d, consumed)
            b = _call(INV._trim_individuals, d, consumed)
            if a != b:
                bad.append("形状[%d]=%r consumed=%r：old=%r new=%r" % (i, d, consumed, a, b))
    return bad


# ============================================================
# ③ 引擎形状规则（逐条 + 每条兜底分支）
# ============================================================
def rule_violations():
    bad = []

    def eq(name, got, want):
        if got != want:
            bad.append("%s：got=%r want=%r" % (name, got, want))

    # R1 新格 + 兜底：裸值 entry / 缺 count / 缺 data
    st = Stack((), marks="m")
    eq("R1 空容器", (len(st), st.total(), st.get("a")), (0, 0, None))
    eq("R1 加一格", (len(st.add("a", 2, {"m": [1]})), st.add("a", 2, {"m": [1]}).count_of("a")), (1, 2))
    eq("R1 data=None → {}",
       Stack((), marks="m").add("a", 1).get("a")["data"], {})
    eq("R1 裸值 entry", Stack((5,), marks="m").get(5), {"key": 5, "count": 1, "data": {}})
    eq("R1 缺 count", Stack(({"key": "a", "data": {"m": []}},), marks="m").count_of("a"), 1)
    eq("R1 缺 data", Stack(({"key": "a", "count": 2},), marks="m").get("a")["data"], {})
    eq("R1 脏 data=None", Stack(({"key": "a", "count": 2, "data": None},), marks="m").get("a")["data"], {})

    # R2 同 key 累加 + 兜底：旧格 count=0 不夹到 1
    st2 = Stack((), marks="m").add("a", 2, {"m": [1]}).add("a", 3)
    eq("R2 件数相加", st2.count_of("a"), 5)
    eq("R2 格序稳定", Stack((), marks="m").add("a").add("b").add("a").keys(), ["a", "b"])
    eq("R2 count=0 旧格不夹紧", Stack(({"key": "a", "count": 0, "data": {}},), marks="m").count_of("a"), 0)
    eq("R2 count=0 上累加", Stack(({"key": "a", "count": 0, "data": {}},), marks="m").add("a", 1).count_of("a"), 1)

    # R3 记录合并（旧在前）+ 兜底：marks 存在但为 None → 不合并
    st3 = Stack((), marks="m").add("a", 1, {"m": [1]}).add("a", 1, {"m": [2, 3]})
    eq("R3 记录旧在前", st3.get("a")["data"]["m"], [1, 2, 3])
    eq("R3 非记录字段取来件", st3.get("a")["data"].get("x"), None)
    st3b = Stack((), marks="m").add("a", 1, {"m": [1], "cls": "旧"}).add("a", 1, {"m": [2], "cls": "新"})
    eq("R3 类属性来件为准", st3b.get("a")["data"], {"cls": "新", "m": [1, 2]})
    st3c = Stack((), marks="m").add("a", 1, {"m": [1]}).add("a", 1, {"m": None, "z": 1})
    eq("R3 marks=None 不合并", st3c.get("a")["data"], {"m": [1]})
    eq("R3 marks=[] 仍合并", Stack((), marks="m").add("a", 1, {"m": [1]}).add("a", 1, {"m": []})
       .get("a")["data"]["m"], [1])
    eq("R3.5 来件无 marks", Stack((), marks="m").add("a", 1, {"m": [1]}).add("a", 1, {"z": 2})
       .get("a")["data"], {"m": [1]})
    eq("R3.6 旧格裸序列", Stack((), marks="m").add("a", 1, [1, 2]).add("a", 1, {"m": [3]})
       .get("a")["data"], {"m": [1, 2, 3]})

    # R3b 未合并 → data 复用旧对象（调用方按 `is` 判「要不要写回」）；merge=False
    st4 = Stack((), marks="m").add("a", 1, {"m": [1]})
    before = st4.get("a")["data"]
    after = st4.add("a", 1, {"z": 2}).get("a")
    eq("R3b 未合并 data 同一对象", after["data"] is before, True)
    eq("R3b 件数照加", after["count"], 2)
    st4b = Stack((), marks="m").add("a", 1, {"m": [1]})
    eq("R3b merge=False data 不动", st4b.add("a", 1, {"m": [2]}, merge=False).get("a")["data"], {"m": [1]})
    eq("R3b merge=False 件数照加", st4b.add("a", 1, {"m": [2]}, merge=False).count_of("a"), 2)

    # R4 扣件 + 兜底：缺键不报错
    st5 = Stack((), marks="m").add("a", 3, {"m": [1, 2, 3]})
    eq("R4 缺键", st5.take("zz", 1)[1], False)
    eq("R4 恰好扣空 → 丢格", (len(st5.take("a", 3)[0]), st5.take("a", 3)[0].get("a")), (0, None))
    eq("R4 超额扣 → 丢格", len(st5.take("a", 9)[0]), 0)
    part = st5.take("a", 1)[0]
    eq("R4 部分扣", (part.count_of("a"), part.get("a")["data"]["m"]), (2, [2, 3]))
    eq("R4 缺键返回自身", st5.take("zz", 1)[0] is st5, True)

    # R5 记录为空 → 原对象返回；截空 → 删 marks 键
    d = {"m": []}
    eq("R5 空记录原对象", STK.trim_records(d, 1, marks="m") is d, True)
    eq("R5 缺 marks 原对象", STK.trim_records({"a": 1}, 1, marks="m"), {"a": 1})
    eq("R5 None 原对象", STK.trim_records(None, 1, marks="m"), None)
    eq("R5 非序列原始值", STK.trim_records(5, 1, marks="m"), 5)
    eq("R5 截空删 marks 键", STK.trim_records({"a": 1, "m": [1]}, 1, marks="m"), {"a": 1})
    eq("R5 截不空留余下", STK.trim_records({"a": 1, "m": [1, 2]}, 1, marks="m"), {"a": 1, "m": [2]})
    eq("R5 marks=None 原对象", STK.trim_records({"m": None}, 1, marks="m"), {"m": None})

    # R6 裸序列
    eq("R6 裸序列截不空", STK.trim_records([1, 2, 3], 1, marks="m"), {"m": [2, 3]})
    eq("R6 裸序列截空 → {}", STK.trim_records([1], 1, marks="m"), {})
    eq("R6 裸空序列原对象", STK.trim_records([], 1, marks="m"), [])

    # R7 计数
    st7 = Stack(({"key": "a", "count": 2, "data": {}}, {"key": "b", "count": 3, "data": {}}), marks="m")
    eq("R7 total", st7.total(), 5)
    eq("R7 count_of 缺键", st7.count_of("z"), 0)
    eq("R7 count_where", st7.count_where(lambda k, _d: k == "b"), 3)
    eq("R7 count_where 无谓词", st7.count_where(), 5)
    eq("R7 __contains__", ("a" in st7, "z" in st7), (True, False))

    # R8 容错构造 / 件数校验
    eq("R8 脏 entry 不炸",
       Stack(({"key": "a", "count": "2"}, {"key": "b", "count": 3}), marks="m").total(), 5)
    eq("R8 裸值 entry 也算一格", Stack(("x", None, 3), marks="m").total(), 3)
    for c in (0, -1, True, 1.5):
        if not isinstance(_call(Stack((), marks="m").add, "a", c)[1], str):
            bad.append("R8 add 非法件数 %r 未拒绝" % (c,))
        if not isinstance(_call(Stack((), marks="m").take, "a", c)[1], str):
            bad.append("R8 take 非法件数 %r 未拒绝" % (c,))

    # 合并代数纯函数
    eq("merge_records 上限丢最旧",
       STK.merge_records({"m": [1, 2]}, {"m": [3, 4]}, marks="m", cap=3), {"m": [2, 3, 4]})
    eq("merge_records 无上限", STK.merge_records({"m": [1]}, {"m": [2]}, marks="m"), {"m": [1, 2]})
    eq("carries_records 判据", (STK.carries_records({"m": []}, marks="m"),
                                STK.carries_records({"m": None}, marks="m"),
                                STK.carries_records({}, marks="m"),
                                STK.carries_records(None, marks="m"),
                                STK.carries_records([1], marks="m")),
       (True, False, False, False, False))
    return bad


# ============================================================
# ④ 零知识静态扫描（ast 扫引擎形状模块）
# ============================================================
def _content_probes():
    """内容侧取值探针：物品 id/名 · 职业 id/名 · 材料/鱼名 · 品质词 · 游戏名。"""
    probes = set()
    for k, v in json.load(open(ITEMS_PATH, encoding="utf-8")).items():
        probes.add(k)
        if isinstance(v, dict):
            for f in ("name", "quality", "type"):
                if v.get(f):
                    probes.add(v[f])
    for k, v in json.load(open(CLASSES_PATH, encoding="utf-8")).items():
        probes.add(k)
        if isinstance(v, dict) and v.get("name"):
            probes.add(v["name"])
    for tbl in ("MATERIALS", "ITEMS", "MATERIALS_BY_NAME"):
        for k, v in (getattr(C, tbl, None) or {}).items():
            probes.add(k)
            if isinstance(v, dict) and v.get("name"):
                probes.add(v["name"])
            if isinstance(v, dict) and v.get("quality"):
                probes.add(v["quality"])
    for f in (getattr(C, "FISH_POOL", None) or []):
        if f.get("name"):
            probes.add(f["name"])
    probes |= {"奥兰迪亚", "余烬纪年", "剑与魔法", "dragonfall",
               "战意", "旋律", "连段", "破绽", "信仰"}
    return {p for p in probes if isinstance(p, str) and p}


def _docstring_nodes(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) \
                    and isinstance(node.body[0].value, ast.Constant) \
                    and isinstance(node.body[0].value.value, str):
                out.add(id(node.body[0].value))
    return out


def neutrality_violations():
    bad = []
    src = open(STACK_PATH, encoding="utf-8").read()
    tree = ast.parse(src, filename=STACK_PATH)
    # (a) 绝对 import 全标准库（纯度门禁同口径；相对导入不限）
    stdlib = set(sys.stdlib_module_names)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and not node.level:
            root = (node.module or "").split(".")[0]
            if root and root not in stdlib:
                bad.append("非标准库绝对 import：from %s import ...（:%d）" % (node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root and root not in stdlib:
                    bad.append("非标准库绝对 import：import %s（:%d）" % (a.name, node.lineno))
    # (b) 非 docstring 字符串常量不得命中内容侧取值
    probes = _content_probes()
    long_probes = {p for p in probes if len(p) >= 4}
    docs = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docs:
            continue
        s = node.value
        if s in probes:
            bad.append("引擎源码常量命中内容侧取值：%r（:%d）" % (s, node.lineno))
            continue
        for p in long_probes:
            if p in s:
                bad.append("引擎源码常量含内容侧取值 %r：%r（:%d）" % (p, s[:40], node.lineno))
                break
    # (c) 内容侧字段名字面量 / 数值不得进引擎
    if '"tags"' in src or "'tags'" in src:
        bad.append('引擎源码出现内容侧字段名字面量 "tags"')
    if "500" in src:
        bad.append("引擎源码出现内容侧上限数值 500")
    # (d) 记录字段名与上限**无默认值**（必填）
    p = inspect.signature(Stack.__init__).parameters
    if p["marks"].default is not inspect.Parameter.empty:
        bad.append("Stack.__init__ 的 marks 竟然有默认值（内容侧字段名不许有默认）")
    if p["cap"].default is not None:
        bad.append("Stack.__init__ 的 cap 默认值不是 None")
    if inspect.signature(STK.trim_records).parameters["marks"].default is not inspect.Parameter.empty:
        bad.append("trim_records 的 marks 竟然有默认值")
    return bad


# ============================================================
# ⑤ 口径分歧（引擎不管的那部分：刻意不统一）
# ============================================================
def divergence_violations():
    bad = []
    import content.persistence.social as SOC
    import content.persistence.world as WLD
    # 1) 三处调用共用**同一个**截断实现（单源在引擎，包侧只剩适配名）
    if SOC._trim_individuals is not INV._trim_individuals:
        bad.append("social._trim_individuals 不是 inventory 的那个适配名")
    if WLD._trim_individuals is not INV._trim_individuals:
        bad.append("world._trim_individuals 不是 inventory 的那个适配名")
    if INV._STACK_MARKS != "tags":
        bad.append("内容侧记录字段名绑定不再是 tags：%r" % (INV._STACK_MARKS,))
    if INV.FISH_TAGS_MAX != 500:
        bad.append("FISH_TAGS_MAX 不再是内容侧取值 500：%r" % (INV.FISH_TAGS_MAX,))
    # 2) 可堆叠判据仍由内容侧给（merge 开关来自 item_data["stackable"]）
    add_src = inspect.getsource(INV.add_item)
    if "stackable" not in add_src:
        bad.append("add_item 不再读内容侧可堆叠判据 stackable")
    # 3) 个体化（uuid / 图鉴）仍在包侧，引擎零知识
    stack_src = open(STACK_PATH, encoding="utf-8").read()
    for token in ("eq_", "EQUIP_ROSTER", "possessed"):
        if token in stack_src:
            bad.append("引擎形状模块出现个体化记号 %r" % token)
    # 4) social / world 的内联合并副本**本次刻意保留**（口径确实不同，见 DESIGN §4-2）
    if "_inv_upsert" not in open(SOC.__file__, encoding="utf-8").read():
        bad.append("social._inv_upsert 不见了（本批刻意不收敛它）")
    if "_storage_upsert" not in open(WLD.__file__, encoding="utf-8").read():
        bad.append("world._storage_upsert 不见了（本批刻意不收敛它）")
    # 5) 包侧不再手写第二份合并实现：add_item 里不得再出现旧合并片段
    if "_new_tags" in add_src or 'slim["tags"]' in add_src:
        bad.append("add_item 里还留着旧的手写合并实现（两份实现）")
    return bad


# ============================================================
# ⑥ 序列化（纯 JSON）
# ============================================================
def serial_violations():
    bad = []
    st = Stack((), marks="m", cap=2).add("甲", 2, {"m": [1, 2], "cls": "材料"})
    raw = st.dump()
    if not isinstance(raw, str) or "\\u" in raw:
        bad.append("dump 不是未转义 JSON 文本：%r" % raw[:60])
    if json.loads(raw) != st.entries():
        bad.append("dump 内容 != entries")
    back = Stack.load(raw, marks="m", cap=2)
    if back.entries() != st.entries() or back.total() != 2:
        bad.append("load(dump) 往返不等：%r" % (back.entries(),))
    if Stack.load(None, marks="m").entries() != [] or Stack.load("坏数据", marks="m").entries() != []:
        bad.append("load 容错（None / 坏 JSON）失败")
    if Stack.load("[]", marks="m").entries() != []:
        bad.append("load('[]') 不为空")
    if Stack.load([{"key": "a", "count": 3, "data": {"m": []}}], marks="m").count_of("a") != 3:
        bad.append("load(list) 件数不对")
    merged = STK.merge_records({"m": [{"a": 1}]}, {"m": [{"a": 2}], "cls": "鱼"}, marks="m", cap=500)
    if json.loads(json.dumps(merged, ensure_ascii=False)) != merged:
        bad.append("合并结果不可 JSON 往返")
    return bad


# ============================================================
# ⑦ 顺序 + 双故障
# ============================================================
def order_violations():
    """FIFO 全序：合并 = 旧在前；扣件 = 从头扣；上限 = 丢最旧。"""
    bad = []
    st = Stack((), marks="m").add("k", 1, {"m": [1]}).add("k", 1, {"m": [2]}).add("k", 1, {"m": [3]})
    if st.get("k")["data"]["m"] != [1, 2, 3]:
        bad.append("合并顺序不是「旧在前」：%r" % (st.get("k")["data"]["m"],))
    if st.take("k", 1)[0].get("k")["data"]["m"] != [2, 3]:
        bad.append("扣件不是从头扣：%r" % (st.take("k", 1)[0].get("k")["data"]["m"],))
    stc = Stack((), marks="m", cap=2).add("k", 1, {"m": [1]}).add("k", 1, {"m": [2]}).add("k", 1, {"m": [3]})
    if stc.get("k")["data"]["m"] != [2, 3]:
        bad.append("上限不是丢最旧：%r" % (stc.get("k")["data"]["m"],))
    # 端到端：真 DB 上三轮入包 + 一轮扣件，个体顺序必须逐条对得上
    _reset()
    key = "mat_yin_lin_yu"
    data = {"name": "银鳞鱼", "type": "鱼", "stackable": True, "price": 6}
    for i in (1, 2, 3):
        INV.add_item("g", "ord", key, dict(data), 1, {"i": i})
    _t = INV.remove_item("g", "ord", key, 1)
    got = _rows("ord")[0][0][1]
    if json.loads(got).get("tags") != [{"i": 2}, {"i": 3}]:
        bad.append("端到端 FIFO 顺序不对：%r" % (got,))
    if _t is not True:
        bad.append("端到端 remove_item 返回 %r" % (_t,))
    return bad


def double_fault_violations():
    """两处同时坏（合并顺序反转 + 截断改尾删）—— 单故障矩阵证明不了顺序。"""
    orig_merge, orig_trim_stk, orig_trim_inv = STK.merge_records, STK.trim_records, INV.trim_records

    def bad_merge(stored, incoming, *, marks, cap=None):
        out = {k: v for k, v in incoming.items() if k != marks}
        joined = incoming[marks] + STK._stored_records(stored, marks)      # 顺序反转
        out[marks] = joined if cap is None else joined[:cap]               # 并改成留最旧
        return out

    def bad_trim(stored, taken, *, marks):
        if not isinstance(stored, dict) or not isinstance(stored.get(marks), list) \
                or not stored[marks]:
            return stored
        rest = stored[marks][:-taken] if taken else stored[marks]          # 改尾删
        out = dict(stored)
        if rest:
            out[marks] = rest
        else:
            out.pop(marks, None)
        return out

    STK.merge_records = bad_merge
    STK.trim_records = bad_trim
    INV.trim_records = bad_trim
    try:
        return order_violations() + compare_scenarios([_item_scenario("mat_yin_lin_yu",
                                                                     {"name": "银鳞鱼"})])
    finally:
        STK.merge_records, STK.trim_records, INV.trim_records = orig_merge, orig_trim_stk, orig_trim_inv


# ============================================================
# 断言
# ============================================================
def test_frozen_contract():
    print("【① 冻结契约：冻结片段 sha256 + 活实现 sha256 + 未动函数 + 引擎文件 sha256】")
    check("冻结片段 4 函数 sha256 全中", not frozen_violations(), "；".join(frozen_violations()))
    check("活实现 4 函数 inspect.getsource sha256 全中", not live_violations(),
          "；".join(live_violations()))
    check("引擎形状文件 sha256 中", not engine_pin_violations(), "；".join(engine_pin_violations()))
    check("冻结块 = 4 个形状函数（不是空转）", len(_FROZEN_FUNCS) == len(_FROZEN_NAMES) == 4,
          "n=%d" % len(_FROZEN_FUNCS))
    check("内容侧 %d 个取值/个体化函数逐字节未动" % len(PIN_UNCHANGED),
          not unchanged_violations(), "；".join(unchanged_violations()[:3]))


def test_behavior_equivalence():
    items = load_items()
    print("【② 行为等价：items.json 全量 %d 条 + 边界矩阵 + 截断矩阵，旧实现 vs 新实现】" % len(items))
    bad = ["全量：" + x for x in compare_scenarios([_item_scenario(k, d) for k, d in items])]
    check("全量物品域逐格比对（返回 + 落库 + possessed）", not bad, "；".join(bad[:3]))
    bad_b = ["边界：" + x for x in compare_scenarios(BOUNDARY_SCENARIOS)]
    check("边界矩阵 %d 组逐格比对" % len(BOUNDARY_SCENARIOS), not bad_b, "；".join(bad_b[:3]))
    bad_t = _trim_matrix_violations()
    check("_trim_individuals 纯函数矩阵（15 形状 × 4 扣量）", not bad_t, "；".join(bad_t[:3]))
    # 反空转：全量域里旧实现确实落了格（否则「逐格比对」是拿空表比空表）
    _reset()
    wrote = 0
    for k, d in items:
        qq = "anti_%s" % k
        _OLD.add_item("g", qq, k, dict(d), 2)
        if _rows(qq)[0]:
            wrote += 1
    check("反空转：全量物品域旧实现落格 %d/%d" % (wrote, len(items)), wrote == len(items))


def test_engine_rules():
    print("【③ 引擎形状规则：R1–R8 逐条 + 每条兜底分支】")
    bad = rule_violations()
    check("R1–R8 全部规则与兜底分支", not bad, "；".join(bad[:5]))
    check("Stack 取自 container 门面（与 Slots 同口径）",
          Stack is STK.Stack and hasattr(__import__("saintess_engine.container", fromlist=["x"]), "Stack"))


def test_neutrality():
    print("【④ 零知识静态扫描：import 纯度 + 常量不命中内容侧取值 + 无默认值】")
    bad = neutrality_violations()
    check("引擎形状模块零知识（import 纯度 / 常量 / 无默认值）", not bad, "；".join(bad[:5]))


def test_divergence():
    print("【⑤ 口径分歧：取值/个体化留包侧 · 截断单源 · 内联副本刻意保留】")
    bad = divergence_violations()
    check("口径分歧断言全过", not bad, "；".join(bad[:5]))


def test_serialization():
    print("【⑥ 序列化：load / dump 纯 JSON 往返】")
    bad = serial_violations()
    check("load/dump 往返 + 容错 + 未转义", not bad, "；".join(bad[:5]))


def test_order_and_double_fault():
    print("【⑦ 顺序 + 两处同时坏】")
    bad_o = order_violations()
    check("FIFO 全序（合并旧在前 / 扣件从头 / 上限丢最旧 / 端到端）", not bad_o, "；".join(bad_o[:3]))
    check("基线：顺序断言在小域上本来全绿",
          not compare_scenarios([_item_scenario("mat_yin_lin_yu", {"name": "银鳞鱼"})]))
    bad_d = double_fault_violations()
    check("两处同时坏（顺序反转 + 尾删）→ 门禁变红", bool(bad_d),
          "（没红说明顺序/双故障矩阵没牙）")
    check("双故障还原后复绿", not order_violations())


def _tamper(name, old, new):
    """把 `INV.<name>` 的源码改一行、注册进 linecache，`inspect` 能读到（不写盘）。"""
    src = _lf(inspect.getsource(getattr(INV, name)))
    if old not in src:
        raise AssertionError("猴补目标片段不在 %s：%r" % (name, old))
    body = src.replace(old, new, 1)
    filename = "<tamper:%s>" % name
    ns = dict(vars(INV))
    exec(compile(body, filename, "exec"), ns)                          # noqa: S102 测试用内存猴补
    linecache.cache[filename] = (len(body), None, body.splitlines(True), filename)
    return ns[name]


def test_teeth():
    print("【⑧ 有牙反证：猴补破坏 3 件事 → 门禁必须变红；跑完不写盘还原】")
    small = load_items()[:20]
    check("基线：小域比对本来全绿", not behavior_violations(small),
          "；".join(behavior_violations(small)[:3]))

    # M1 —— 改一个比较边界（remove_item：格没了该 DELETE，改成写回）
    orig = INV.remove_item
    INV.remove_item = _tamper("remove_item", "if entry is None:", "if entry is not None:")
    try:
        check("M1 改比较边界 → 行为比对变红", bool(behavior_violations(small)),
              "（没红说明边界没被比对看到）")
        check("M1 活实现 sha 同时变红", bool(live_violations()))
    finally:
        INV.remove_item = orig

    # M2 —— 改返回结构（非法件数原本返回 False，改成 None）
    orig2 = INV.add_item
    INV.add_item = _tamper("add_item", "return False", "return None")
    try:
        check("M2 改返回结构 → 行为比对变红", bool(behavior_violations(small)),
              "（没红说明返回没被比对看到）")
    finally:
        INV.add_item = orig2

    # M3 —— 让容器少合并一次（引擎 Stack 永不走合并分支）
    orig3 = INV.Stack

    class _NoMergeStack(Stack):
        def add(self, key, count=1, data=None, *, merge=True):
            return super().add(key, count, data, merge=False)

    INV.Stack = _NoMergeStack
    try:
        check("M3 容器少合并一次 → 行为比对变红", bool(behavior_violations(small)),
              "（没红说明合并没被比对看到）")
    finally:
        INV.Stack = orig3

    check("三处猴补全部还原后复绿", not behavior_violations(small)
          and not live_violations())


def main():
    test_frozen_contract()
    test_behavior_equivalence()
    test_engine_rules()
    test_neutrality()
    test_divergence()
    test_serialization()
    test_order_and_double_fault()
    test_teeth()
    print("\n== 结果：通过 %d / 共 %d ==" % (PASS, PASS + FAIL))
    for f in FAILURES:
        print("  FAIL:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
