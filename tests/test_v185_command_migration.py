# -*- coding: utf-8 -*-
"""门禁：指令表单源化（路线图 #9 收尾后）—— 冻结比对 + 单源结构。

背景：命令正则原有两处来源（各文件 `@filter.regex(<字面量>)` + `_registry._LITERAL_REGEX`
手工镜像表），靠一个「表与装饰器 1:1」测试盯着。2026-09-12 把 195 条指令逐批搬进声明表
（`game/data/command_specs.json`）+ `@declared("key")`，镜像表已删除。

本门禁守两件事：
  一、**搬家只能搬家**：迁移开始前的有效表（`COMMAND_REGEX` 195 条）冻结在
      `tests/_command_table_freeze.json`（sha256 双锁），此后**逐字相等**。
  二、**单源结构**：有效表 == 声明表派生；镜像表 / 字面量装饰器都不复存在（防有人重新引入
      第二份正则）。将来若**有意**新增指令：只在声明表加声明 + `@declared("key")`，
      并显式更新冻结快照（否则本门禁按「凭空多出来的 key」报红）。

断言：
  A. 冻结比对：当前有效表 == 快照（键集合 + 每条正则逐字 + sha256）
  B. 单源结构：有效表键集 == 声明表键集；无 `_LITERAL_REGEX` / `OVERLAP_KEYS` 残留；
     命令层 AST 扫描零 `@filter.regex` 装饰器
  C. 没有任何 key 在迁移中丢失 / 凭空多出
  D. 比较器有牙（反证）：改一格 / 删一格 / 加一格 → 比对必须报红

跑法：python tests/test_v185_command_migration.py（exit=0 全绿）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths
PLUGIN_DIR = _paths.HOST_ROOT      # 宿主插件根（旧语义）
PKG_ROOT = _paths.PKG_ROOT         # 包根（内容真源）
ENGINE_ROOT = _paths.ENGINE_ROOT

import ast                                                # noqa: E402
import hashlib                                            # noqa: E402
import json                                               # noqa: E402

# ★ P5F-REPOINT: 原宿主壳 `game/commands`（含直载的 `_registry.py`）+ `game/data/command_specs.json`
#   （随删壳批消失）→ 包内真源 `<PKG_ROOT>/content`（命令层）
#   + `content/data/commands.json`（声明真源）。
CMD_DIR = os.path.join(PKG_ROOT, "content")
SPEC_FILE = os.path.join(CMD_DIR, "data", "commands.json")
SNAP_FILE = os.path.join(_paths.TESTS_DIR, "_command_table_freeze.json")

from _engine_harness import harness as _harness          # noqa: E402
from host.adapter_qq import PLATFORM_KEYS                # noqa: E402

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


def _combine_patterns(patterns):
    """多条正则合成一条（逐字 = 退役的宿主 `_registry._combine_patterns` / 引擎 `combine_patterns`）。"""
    pats = [p for p in (patterns or ()) if p]
    if not pats:
        return ""
    if len(pats) == 1:
        return pats[0]
    return "|".join("(?:%s)" % p for p in pats)


def load_command_table():
    """包内声明表 → 有效表 `{key: 合并正则}`（终态等价物 = 原 `_registry.COMMAND_REGEX`）。

    ★ P5F-REPOINT: 原 `importlib` 直载宿主 `game/commands/_registry.py`（随删壳批消失）
    → 就地按**同一口径**从包内声明表派生（派生保真 / 两份 combine 同语义由 2/3 段锁死）。
    """
    out = {}
    for k, v in load_specs().items():
        pats = v.get("patterns", v.get("pattern")) if isinstance(v, dict) else v
        if isinstance(pats, str):
            pats = [pats]
        c = _combine_patterns(pats or [])
        if c:
            out[str(k)] = c
    return out


def scan_command_literals():
    """AST 扫包内命令层：返回 `(regex_sites, mirror_names)`。

    * `regex_sites`   —— `@<ns>.regex(...)` 装饰器（第二份正则来源，应为空；docstring 示例不算）
    * `mirror_names`  —— 模块级 `_LITERAL_REGEX` / `OVERLAP_KEYS` 赋值（手工镜像表残留，应为空）
    """
    regex_sites, mirror_names = [], []
    for fn in sorted(os.listdir(CMD_DIR)):
        if not fn.endswith(".py") or fn.startswith("__"):
            continue
        with open(os.path.join(CMD_DIR, fn), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for _t in node.targets:
                    if isinstance(_t, ast.Name) and _t.id in ("_LITERAL_REGEX", "OVERLAP_KEYS"):
                        mirror_names.append("%s:%s" % (fn, _t.id))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr == "regex"):
                    regex_sites.append(f"{fn}:{node.name}")
    return regex_sites, sorted(mirror_names)


def load_specs():
    with open(SPEC_FILE, encoding="utf-8") as f:
        return json.load(f)


def digest_of(table):
    blob = json.dumps({k: v for k, v in sorted(table.items())},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def diff_tables(old, new):
    """返回逐格差异列表（比较器本体，反证组直接调它）。"""
    return sorted((k, old.get(k), new.get(k))
                  for k in set(old) | set(new) if old.get(k) != new.get(k))


def regex_decorators():
    """AST 扫命令模块里的 `@<ns>.regex(...)` 装饰器（不看注释与文档串）。"""
    return scan_command_literals()[0]


def test_A_frozen_table():
    print("【A. 冻结比对：有效指令表逐字不变】")
    now = load_command_table()
    snap = json.load(open(SNAP_FILE, encoding="utf-8"))
    old_table = snap["table"]
    diff = diff_tables(old_table, now)
    check(f"有效表 {len(now)} 条 == 快照 {len(old_table)} 条（键集合一致）",
          set(old_table) == set(now),
          [k for k, _a, _b in diff][:5])
    check("每条正则逐字相等（迁移 = 搬家，不改命令面）", not diff, diff[:3])
    check("sha256 == 快照（%s）" % snap["sha256"][:12],
          digest_of(now) == snap["sha256"], digest_of(now))


def test_B_single_source():
    print("【B. 单源结构：有效表 = 声明表派生；镜像表与字面量装饰器都不存在】")
    now = load_command_table()
    specs = load_specs()
    check("有效表键集 == 声明表键集（不存在第二份来源）",
          set(now) == set(specs),
          sorted(set(now) ^ set(specs))[:5])
    left, mirror = scan_command_literals()
    check("字面量镜像表已退役（无 _LITERAL_REGEX / OVERLAP_KEYS）", not mirror, mirror[:5])
    check("命令层零 @filter.regex 装饰器残留（AST 扫描，跳过注释/文档串）", not left, left[:5])
    # ★ P5F-REPOINT: 独立对侧 = 包内**运行时注册表**（`pkg.command_handlers()` ∪ 平台例外键
    #   `host/adapter_qq.py::PLATFORM_KEYS`：包内有声明、宿主层实现、包内无处理器）。
    #   声明表派生键集与它 1:1 ⇒ 漏登记 / 死声明当场报红（原「表 ↔ @declared 用法」同义）。
    runtime = set(_harness().host.handlers) | set(PLATFORM_KEYS)
    check("有效表键集 == 包内运行时注册表键集（声明 ↔ 注册零漂移）",
          set(now) == runtime, sorted(set(now) ^ runtime)[:5])


def test_C_no_key_lost():
    print("【C. 没有任何 key 在迁移中丢失】")
    now = load_command_table()
    snap = json.load(open(SNAP_FILE, encoding="utf-8"))
    missing = sorted(set(snap["table"]) - set(now))
    check("快照里的 key 全在有效表里", not missing, missing[:5])
    extra = sorted(set(now) - set(snap["table"]))
    check("没有凭空多出来的 key（新增指令须显式更新快照）", not extra, extra[:5])


def test_D_comparator_has_teeth():
    print("【D. 比较器有牙（反证）】")
    snap = json.load(open(SNAP_FILE, encoding="utf-8"))["table"]
    base = dict(snap)
    k0 = sorted(base)[0]

    changed = dict(base); changed[k0] = changed[k0] + "x"
    check("改一格 → 必报红", diff_tables(base, changed) != [])

    dropped = dict(base); dropped.pop(k0)
    check("删一格 → 必报红", diff_tables(base, dropped) != [])

    added = dict(base); added["__ghost__"] = "^x$"
    check("加一格 → 必报红", diff_tables(base, added) != [])

    check("原样 → 报绿（不假阳性）", diff_tables(base, dict(base)) == [])


def main():
    test_A_frozen_table()
    test_B_single_source()
    test_C_no_key_lost()
    test_D_comparator_has_teeth()
    if PASS and not FAIL:
        print(f"\n  单源已达成：{len(load_command_table())} 条指令全部来自包内声明表")
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
