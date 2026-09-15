# -*- coding: utf-8 -*-
"""门禁：指令**声明驱动**接入（游戏侧，2026-09-11）。

背景：命令正则原先有两处来源（各文件 `@filter.regex(<字面量>)` + 手工维护的
`_registry.COMMAND_REGEX` 镜像表），靠「表与装饰器 1:1」测试盯着。本批把一部分指令
迁到**声明表**（`game/data/command_specs.json`），让声明成为唯一真源。

本门禁锁住迁移后的不变量：
  1. **单源**：有效表键集 == 声明表键集（字面量镜像表 `_LITERAL_REGEX` / `OVERLAP_KEYS`
     已随 2026-09-12 路线图 #9 迁移收尾退役）
  2. **派生保真**：声明 → 有效表 的正则与声明值一致；`@declared` 注册的正则 == 有效表该 key
  3. **两处 combine 同语义**：`_registry._combine_patterns` ≡ 框架 `combine_patterns`
     （本表为可独立加载而有意复制了 5 行逻辑 —— 用断言锁死，防两边漂移）
  4. **漂移自检双向干净**：声明表 ↔ 代码里 `@declared` 的实际使用
     （有声明没用 = 死声明；用了没声明 = 漏登记）
  5. **编辑器可编辑**：声明表能被框架 schema 校验通过（用编辑器真能改）
  6. **帮助/目录可用**：`catalog()` 按分类返回可见声明（声明里的 desc/category/order 有消费者）

跑法：python tests/test_v181_command_declaration.py（exit=0 全绿）
"""
import ast
import json
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_cmd_decl.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine.command import combine_patterns   # noqa: E402

# ★ P5F-REPOINT: 原宿主壳 `game/commands` + `game/data/command_specs.json`（随删壳批消失）
#   → 包内真源 `content` + `content/data/commands.json`。
CMD_DIR = os.path.join(PLUGIN_DIR, "content")
SPEC_FILE = os.path.join(CMD_DIR, "data", "commands.json")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cmd_registry import declared_usage as _pkg_declared_usage  # noqa: E402

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


def _combine_local(patterns):
    """逐字复制退役的宿主 `_registry._combine_patterns`（那 5 行）—— 与框架对拍用。"""
    pats = [p for p in (patterns or ()) if p]
    if not pats:
        return ""
    if len(pats) == 1:
        return pats[0]
    return "|".join("(?:%s)" % p for p in pats)


def load_command_table():
    """包内声明表 → 有效表 `{key: 合并正则}`（终态等价物 = 原 `_registry.COMMAND_REGEX`）。

    ★ P5F-REPOINT: 原 `importlib` 直载宿主 `game/commands/_registry.py`（随删壳批消失）
    → 就地按同一口径从包内声明表派生；「两处 combine 同语义」由 2/3 段继续锁死。
    """
    with open(SPEC_FILE, encoding="utf-8") as f:
        specs = json.load(f)
    out = {}
    for k, v in (specs or {}).items():
        pats = v.get("patterns", v.get("pattern")) if isinstance(v, dict) else v
        if isinstance(pats, str):
            pats = [pats]
        c = _combine_local(pats or [])
        if c:
            out[str(k)] = c
    return out


def _mirror_table_names():
    """AST 扫包内命令层：模块级 `_LITERAL_REGEX` / `OVERLAP_KEYS` 赋值（手工镜像表残留）。"""
    names = []
    for fn in sorted(os.listdir(CMD_DIR)):
        if not fn.endswith(".py") or fn.startswith("__"):
            continue
        with open(os.path.join(CMD_DIR, fn), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for _t in node.targets:
                    if isinstance(_t, ast.Name) and _t.id in ("_LITERAL_REGEX", "OVERLAP_KEYS"):
                        names.append("%s:%s" % (fn, _t.id))
    return sorted(names)


_PKG_SPEC = os.path.join(
    PLUGIN_DIR, "content", "data", "commands.json")


def _pkg_registry():
    """包内真源声明表构建的框架注册表（旧宿主 `_declared.registry()` 的终态等价物）。"""
    from saintess_engine.command import CommandRegistry
    with open(_PKG_SPEC, encoding="utf-8") as f:
        data = json.load(f)
    return CommandRegistry.from_data(data, name="orlandia.commands")


def _pkg_catalog():
    """`{分类: [声明, ...]}`（仅 visible，按 order）——旧 `_declared.catalog()` 的终态等价物。"""
    reg = _pkg_registry()
    out = {}
    for spec in reg.visible():
        out.setdefault(spec.category or "其他", []).append(spec)
    return out


def scan_declared_usages():
    """`{处理器名: 声明key}` —— 终态等价于原「AST 扫宿主 `@declared("key")`」。

    ★ P5F-REPOINT: 宿主壳用 `@declared("<key>")`（随删壳批消失）；包内登记面是
    `content/commands.py::COMMANDS`（`@register("<key>")` **+ 循环/别名登记**两种写法都有，
    AST 扫不全）⇒ 统一走 `tests/_cmd_registry.py::declared_usage()`（读包内运行时注册表，
    并把 `register_() → "register"` 这种历史异名映射保留）。
    """
    return _pkg_declared_usage()


# ============================================================

def test_1_single_source():
    print("【1. 单源：有效表完全由声明表派生】")
    table = load_command_table()
    with open(SPEC_FILE, encoding="utf-8") as f:
        specs = json.load(f)
    check("声明表非空（本批已迁入至少 7 条）", len(specs) >= 7, len(specs))
    check("有效表键集 == 声明表键集（不存在第二份来源）",
          set(table) == set(specs),
          sorted(set(table) ^ set(specs))[:5])
    check("字面量镜像表已退役（无 _LITERAL_REGEX / OVERLAP_KEYS）",
          not _mirror_table_names(), _mirror_table_names())


def test_2_derivation_faithful():
    print("【2. 派生保真：声明 → 有效表 → 运行时注册】")
    table = load_command_table()
    with open(SPEC_FILE, encoding="utf-8") as f:
        specs = json.load(f)
    bad = []
    for k, v in specs.items():
        want = combine_patterns(v.get("patterns") or [])
        if table.get(k) != want:
            bad.append((k, table.get(k), want))
    check(f"有效表 {len(specs)} 条声明与声明值逐字一致", not bad, bad[:2])

    # ★ 终态：运行时注册用的正则 = 从**包内真源**直接构建的框架注册表逐 key 合并串
    #   （旧宿主 `_declared.registry()` 已删；引擎 `CommandRegistry.from_data` 是同一实现）。
    D = _pkg_registry()
    bad2 = [(k, D.get(k).combined(), table.get(k))
            for k in specs if D.get(k).combined() != table.get(k)]
    check("运行时注册用的正则 == 有效表该 key", not bad2, bad2[:2])
    check("声明表通过 CommandRegistry.validate（无空正则/非法正则/共用正则）",
          _pkg_registry().validate() == [], _pkg_registry().validate())


def test_3_combine_semantics():
    print("【3. 两处 combine 同语义（测试侧就地复制的那 5 行逻辑 → 断言锁死）】")
    cases = [([], ""), (["^a$"], "^a$"), (["^a$", "^b$"], "(?:^a$)|(?:^b$)"),
             (["^a$", "", "^b$"], "(?:^a$)|(?:^b$)"), (["x"], "x")]
    bad = [(c, _combine_local(c), combine_patterns(c))
           for c, _w in cases if _combine_local(c) != combine_patterns(c)]
    check("本地 _combine_local ≡ 框架 combine_patterns（5 例）", not bad, bad)
    check("空输入两边都给空串",
          _combine_local([]) == "" and combine_patterns([]) == "")


def test_4_drift_both_ways():
    print("【4. 漂移自检双向干净：声明表 ↔ 包内运行时登记实际使用】")
    D = _pkg_registry()
    used = scan_declared_usages()
    check("扫到包内登记使用点（非空即证明迁移真的接上了）", len(used) > 0, len(used))
    check("处理器名与声明的 key 一致（唯一历史异名 register_ → register）",
          all(method == key for method, key in used.items() if method != "register_"),
          {m: k for m, k in used.items() if m != k and m != "register_"})
    au = D.audit_handlers(list(used.values()))
    check("无「用了没声明」（missing_spec 为空）", au["missing_spec"] == [], au)
    check("无「声明了没用」（missing_handler 为空）", au["missing_handler"] == [], au)
    check("audit 总体 ok", au["ok"] is True, au)
    _cat = _pkg_catalog()
    check("catalog 按分类给可见声明（desc/category/order 有消费者）",
          bool(_cat) and all(
              [s.key for s in v] == sorted([s.key for s in v], key=lambda k: D.get(k).order)
              for v in _cat.values()),
          {k: [s.key for s in v] for k, v in _cat.items()})


def test_5_editor_editable():
    print("【5. 编辑器可编辑：声明表过框架 schema 校验】")
    try:
        sys.path.insert(0, os.path.join(_paths.ENGINE_ROOT, "editor"))
        import editor.packages as PK
        import editor.validate as V
    except Exception as e:                                   # noqa: BLE001
        check("编辑器模块可导入（框架 submodule 已在位）", False, repr(e))
        return
    with open(SPEC_FILE, encoding="utf-8") as f:
        specs = json.load(f)
    bad = []
    for k, v in specs.items():
        errs = V.validate_entry("commands", v)
        if errs:
            bad.append((k, errs))
    check(f"声明表 {len(specs)} 条全部通过 `commands` schema", not bad, bad[:2])
    check("域 `commands` 已注册（编辑器 tab 可见）", "commands" in PK.DOMAINS, list(PK.DOMAINS))
    check("域 schema 文件存在", os.path.exists(
        os.path.join(_paths.ENGINE_ROOT, "schemas",
                     PK.DOMAINS["commands"]["schema"])))


def main():
    test_1_single_source()
    test_2_derivation_faithful()
    test_3_combine_semantics()
    test_4_drift_both_ways()
    test_5_editor_editable()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
