#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""门禁：`tlogs` 声明表**单源**（P4′-C）—— 真源(包内) ↔ 镜像(宿主) 逐条相等 + 反证。

为什么有这条线
--------------
B14 之后宿主 `game/data/` 只剩三张 JSON 资产，`tlogs.json` 是其中之一。同一份「kind → 字段契约」
在盘上有**两份**、内容却不同：

    宿主 game/data/tlogs.json          2,619 B   ← 运行时 `host/tlog_setup.py:kinds()` 真正读的那份
    包内 content/data/tlogs.json       3,069 B   ← 编辑器（framework 仓）编辑的那份

实测差异只在外层 kind 序（宿主=逻辑序 / 包内=升序）与数组排版（宿主=单行 / 包内=展开），
18 条 kind 的 fields/desc/category **逐条同值** —— 即「已经同值、但没有任何门禁盯着」，
下一次单边编辑就会变成真正的语义漂移（这正是双源隐患的形态）。

单源口径（本门禁所钉）
----------------------
    真源 = 包内 `content/data/tlogs.json`（framework 仓 `games/orlandia`；编辑器编辑的那一份）
    镜像 = 宿主 `game/data/tlogs.json`（**构建期**由真源生成：`scripts/mirror_tlogs.py`）
    运行时读点 = `host/tlog_setup.py:kinds()`（经 `kinds_path()`）—— **只此一处**读盘
    ★ P5F-REPOINT：原读点是待删树 `game/tlog_setup.py`；终态属主 = 宿主层 `host/tlog_setup.py`，
    读的仍是同一份部署期镜像 `game/data/tlogs.json`（保留资产）。

断言
----
  ⓪ 前置：两份都在、都能解析、非空、条数相等（口径完整，否则 ① 会空转假绿）
  ① 逐条相等：kind 集 + 每条 `fields`（**含顺序**）/ `desc` / `category` 全等 → 单边改动报红该 kind
  ② 构建期镜像：两份**LF 归一后逐字节相同**（md5 相同）—— 镜像必须是真源的确定性产物
  ③ 真源落盘规范：UTF-8 无 BOM · `indent=2` 规范形 · 末尾换行 · 外层 kind 键升序（EOL 允许 CRLF：
     宿主仓 `core.autocrlf=true`，checkout 会把 LF 变 CRLF；比对前归一，规范形按 LF 判）
  ④ 运行时单读：宿主层运行时代码里 `tlogs.json` 字面量**只有 `host/tlog_setup.py` 一处**，
     且 `kinds()` 里只有 **1 个 `open(`**（AST 计数）；包内运行时代码**零读盘**（注释不算）
  ⑤ 装载实证（引擎口径）：镜像喂 `saintess_engine.tlog.KindTable` → 18 条 · `validate()` 空
  ⑥ 反证：比较器有牙（内存对拍，不碰盘）—— 改 `fields` / 改 `desc` / 删一条 / 加一条 →
     红 kind 恰好是该条；原样 → 绿

跑法::

    python tests/test_tlogs_single_source.py                 # exit=0 全绿
    python tests/test_tlogs_single_source.py --pkg P --host H # 沙盒副本对拍（反证脚本用）

输出末三行固定为：`红 kind 汇总: [...]` / `== 结果：通过 N / 共 M ==` / `全绿 ✅`
（反证脚本 `overnight/…/tlogs_counterproof.py` 靠 `红 kind 汇总` 这一行判断「只红哪条 kind」）
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import _paths                                                            # noqa: E402

#: 宿主插件根（旧 `PLUGIN_DIR` 语义：宿主镜像 `game/**`、读点 `host/**` 等宿主专属面）。
#: ★ 搬迁适配（T8 ③）：文件现在住在 `pkg/tests/`，`dirname(dirname(__file__))` 已是**包根**，
#:   不再是宿主插件根 —— 旧写法会把真源/镜像都指到 `pkg/framework/...`（不存在）而假红。
PLUGIN_DIR = _paths.HOST_ROOT
#: 包根（内容真源）；旧写法的 `<PLUGIN_DIR>/framework/games/orlandia` 在包仓布局 == 这里。
PKG_ROOT = _paths.PKG_ROOT
ENGINE_ROOT = _paths.ENGINE_ROOT

#: 真源（包内）：相对 `PKG_ROOT`
PKG_REL = os.path.join("content", "data", "tlogs.json")
#: 镜像（宿主）：相对 `PLUGIN_DIR`
HOST_REL = os.path.join("game", "data", "tlogs.json")
# ★ P5F-REPOINT: 「运行时单读点」原先在待删树 `game/tlog_setup.py`；终态属主 = **宿主层**
#   `host/tlog_setup.py::kinds_path()`（同读这一份部署期镜像 `game/data/tlogs.json`）。
#   故运行时代码根 = `host/`（不再扫 `game/`：那里只剩保留资产，没有 .py）。
HOST_RUNTIME_REL = os.path.join("host")                       # 宿主运行时代码根（相对 PLUGIN_DIR）
PKG_RUNTIME_REL = os.path.join("content")                     # 包内运行时代码根（相对 PKG_ROOT）
READ_POINT_REL = os.path.join("host", "tlog_setup.py")
READ_POINT_LITERAL = 'os.path.join(PLUGIN_ROOT, "game", "data", "tlogs.json")'

PASS = 0
FAIL = 0
FAILURES: list = []
RED_MARKERS: set = set()      # 非 kind 的报红标记（<mirror>/<count>/<readpoint>…），进汇总行


def check(name, cond, detail="", red_keys=()):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✅ %s" % name)
    else:
        FAIL += 1
        ks = sorted({str(k) for k in red_keys})
        RED_MARKERS.update(ks)
        FAILURES.append("%s: %s" % (name, detail))
        print("  ❌ %s  红 kind: %s  %s" % (name, ks, detail))


# ============================================================ 读 / 规范化
def norm_eol(raw: bytes) -> bytes:
    """CRLF → LF（比内容不比行尾；宿主仓 autocrlf=true）。"""
    return raw.replace(b"\r\n", b"\n")


def read_raw(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def eol_of(raw: bytes) -> str:
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    if crlf and lf:
        return "mixed(CRLF %d/LF %d)" % (crlf, lf)
    return "CRLF" if crlf else "LF"


def canonical_text(obj: dict) -> str:
    """规范落盘形：外层键升序 + 条目内字段序原样 + indent=2 + 末尾换行（与镜像生成器同款）。"""
    return json.dumps({k: obj[k] for k in sorted(obj)}, ensure_ascii=False, indent=2) + "\n"


def md5(raw: bytes) -> str:
    return hashlib.md5(raw).hexdigest()


# ============================================================ 逐条比较器（反证直接调它）
def entry_diff(src: dict, dst: dict) -> dict:
    """逐条比 `src → dst`；返回 `{kind: 原因}`（空 = 全等）。

    单向只答「src 的每条在 dst 里是否同值」；双向一致 = 两个方向都空。
    比较口径 = 契约口径：`fields`（**含顺序**）/ `desc` / `category`。
    """
    bad: dict = {}
    for kind, spec in (src or {}).items():
        other = (dst or {}).get(kind)
        if other is None:
            bad[str(kind)] = "镜像缺该 kind"
            continue
        if not isinstance(spec, dict) or not isinstance(other, dict):
            bad[str(kind)] = "条目不是 object（%s vs %s）" % (type(spec).__name__, type(other).__name__)
            continue
        for f in ("fields", "desc", "category"):
            a, b = spec.get(f), other.get(f)
            if a != b:
                bad[str(kind)] = "%s 不同（真源 %r / 镜像 %r）" % (f, a, b)
                break
    for kind in (dst or {}):
        if kind not in (src or {}):
            bad[str(kind)] = "镜像多出该 kind"
    return bad


def fmt(bad: dict) -> str:
    return "；".join("%s: %s" % (k, v) for k, v in sorted(bad.items())[:6])


# ============================================================ 读点扫描
def _py_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".pytest_cache")]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def docstring_node_ids(tree) -> set:
    """模块/类/函数体首句的字符串常量（docstring）→ id 集合（这些不算「代码里的字面量」）。"""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                val = body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    ids.add(id(val))
    return ids


def scan_literal(root: str, needle: str = "tlogs.json", base: str = None) -> tuple:
    """扫目录下 `*.py` **代码里**（排除 docstring）含 `needle` 的字符串常量。

    返回 `(code_hits, doc_hits)`：各为 `[(相对路径, 行号, 片段)]`。
    用 AST 而不是 grep —— 注释/docstring 里的提及**不算读点**（否则会冤枉 `game/content.py:5`
    与包内 `tlog_collect.py:26` 这类说明文字）。

    ★ 搬迁适配（T8 ③）：`root` 改为**绝对路径**（宿主侧 = `PLUGIN_DIR/host`，包内 = `PKG_ROOT/content`），
    不再假定「二者都在同一个插件根下」。
    """
    code_hits, doc_hits = [], []
    if not os.path.isdir(root):
        return code_hits, doc_hits
    for path in _py_files(root):
        rel = os.path.relpath(path, base or PLUGIN_DIR).replace("\\", "/")
        try:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
        except (OSError, SyntaxError):
            continue
        docs = docstring_node_ids(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if needle not in node.value:
                continue
            snippet = node.value.strip().replace("\n", " ")[:60]
            (doc_hits if id(node) in docs else code_hits).append((rel, node.lineno, snippet))
    return code_hits, doc_hits


def count_open_calls(path: str, func_name: str) -> int:
    """AST：某函数里 `open(` 调用的个数（数读盘口，不看注释）。"""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return sum(1 for n in ast.walk(node)
                       if isinstance(n, ast.Call) and (
                           (isinstance(n.func, ast.Name) and n.func.id == "open")
                           or (isinstance(n.func, ast.Attribute) and n.func.attr == "open")))
    return -1


# ============================================================ 断言组
def t0_precondition(pkg_raw, host_raw, pkg_obj, host_obj):
    print("【⓪ 前置：两份都在、都能解析（否则 ① 会空转假绿）】")
    check("真源可读且非空（%d B / %d kind）" % (len(pkg_raw), len(pkg_obj)),
          bool(pkg_obj), "真源空表 = 编辑器 0 条且校验全不拦", red_keys=["<pkg>"])
    check("镜像可读且非空（%d B / %d kind）" % (len(host_raw), len(host_obj)),
          bool(host_obj), "镜像空表 = 运行时静默不校验", red_keys=["<host>"])
    check("两份条数相等（%d vs %d）" % (len(pkg_obj), len(host_obj)),
          len(pkg_obj) == len(host_obj), "条数不等先红", red_keys=["<count>"])
    check("真源 kind 集非空且无自相矛盾（fields 是 list）",
          all(isinstance(v, dict) and isinstance(v.get("fields", []), list)
              for v in pkg_obj.values()),
          "有条目的 fields 不是 list —— 契约形状变了", red_keys=["<shape>"])


def t1_entry_equality(pkg_obj, host_obj):
    print("【① 逐条相等：kind 集 + fields(含顺序) + desc + category】")
    bad = entry_diff(pkg_obj, host_obj)
    bad.update({k: v for k, v in entry_diff(host_obj, pkg_obj).items() if k not in bad})
    check("真源 ↔ 镜像逐条相等（%d 条）" % len(pkg_obj), not bad, fmt(bad), red_keys=list(bad))
    only_pkg = sorted(set(pkg_obj) - set(host_obj))
    only_host = sorted(set(host_obj) - set(pkg_obj))
    check("kind 集完全相等（单边：仅真源 %s / 仅镜像 %s）"
          % (only_pkg or "无", only_host or "无"),
          not only_pkg and not only_host, "", red_keys=only_pkg + only_host)


def t2_build_mirror(pkg_raw, host_raw):
    print("【② 构建期镜像：两份 LF 归一后逐字节相同】")
    a, b = norm_eol(pkg_raw), norm_eol(host_raw)
    check("逐字节相同（真源 %s / 镜像 %s）" % (md5(a), md5(b)), a == b,
          "镜像 ≠ 真源 —— 跑 `python scripts/mirror_tlogs.py` 重生成（不许手改镜像）",
          red_keys=["<mirror>"])


def t3_source_format(pkg_raw, host_raw):
    print("【③ 真源落盘规范（EOL 允许 CRLF：autocrlf 产物，比对前归一）】")
    txt = norm_eol(pkg_raw).decode("utf-8-sig")
    probs = []
    if pkg_raw[:3] == b"\xef\xbb\xbf":
        probs.append("BOM")
    if not norm_eol(pkg_raw).endswith(b"\n"):
        probs.append("无末尾换行")
    try:
        obj = json.loads(txt)
        if list(obj) != sorted(obj):
            probs.append("外层 kind 键非升序")
        if canonical_text(obj) != txt:
            probs.append("非 indent=2 规范形")
    except Exception as exc:                                     # noqa: BLE001
        probs.append("JSON 坏：%s" % exc)
    check("真源：无 BOM / 末尾换行 / 外层键升序 / indent=2 规范形", not probs,
          "问题 %s" % (probs,), red_keys=["<format>"])
    print("     · EOL：真源 %s / 镜像 %s（归一后比对，见 ②）" % (eol_of(pkg_raw), eol_of(host_raw)))


def t4_single_read_point():
    print("【④ 运行时单读：宿主层代码只有一处拿 tlogs.json；包内运行时零读点】")
    host_code, host_doc = scan_literal(os.path.join(PLUGIN_DIR, HOST_RUNTIME_REL))
    files = sorted({h[0] for h in host_code})
    check("宿主运行时代码里 `tlogs.json` 字面量只出现在 `host/tlog_setup.py`（实测 %s）" % files,
          files == ["host/tlog_setup.py"],
          "命中 %s" % [(h[0], h[1]) for h in host_code], red_keys=["<readpoint>"])
    check("宿主只有 1 处代码字面量（不双读、不散落读到别处的第二份）",
          len(host_code) == 1, "命中 %d 处：%s" % (len(host_code), [(h[0], h[1]) for h in host_code]),
          red_keys=["<readpoint>"])
    read_point = os.path.join(PLUGIN_DIR, READ_POINT_REL)
    if not os.path.exists(read_point):
        check("读点文件存在（%s）" % READ_POINT_REL, False, read_point, red_keys=["<readpoint>"])
        return
    src = open(read_point, encoding="utf-8").read()
    check("读点路径就是宿主镜像 `game/data/tlogs.json`（%s）" % READ_POINT_LITERAL,
          READ_POINT_LITERAL in src, "读点写法变了 —— 请同步本门禁的口径", red_keys=["<readpoint>"])
    n_open = count_open_calls(read_point, "kinds")
    check("`kinds()` 里只有 1 个 `open(`（一次读盘、无第二条路径）",
          n_open == 1, "实测 %d 个 open(" % n_open, red_keys=["<readpoint>"])

    pkg_code, pkg_doc = scan_literal(os.path.join(PKG_ROOT, PKG_RUNTIME_REL), base=PKG_ROOT)
    check("包内运行时代码无 `tlogs.json` 读点（0 处代码字面量；说明文字不算）",
          not pkg_code, "命中 %s" % [(h[0], h[1], h[2]) for h in pkg_code], red_keys=["<pkgread>"])
    if host_doc:
        print("     · 宿主说明文字提及（非读点）：%s" % [(h[0], h[1]) for h in host_doc])
    if pkg_doc:
        print("     · 包内说明文字提及（非读点）：%s" % [(h[0], h[1]) for h in pkg_doc])


def t5_engine_load(host_path: str, pkg_obj: dict):
    print("【⑤ 装载实证：镜像喂引擎 KindTable（运行时口径）】")
    sys.path.insert(0, ENGINE_ROOT)
    try:
        from saintess_engine.tlog import KindTable  # noqa: E402
    except Exception as exc:                                     # noqa: BLE001
        check("引擎 `saintess_engine.tlog` 可导入", False, str(exc), red_keys=["<engine>"])
        return
    try:
        kt = KindTable(json.loads(open(host_path, encoding="utf-8").read()))
    except Exception as exc:                                     # noqa: BLE001
        check("镜像能装成 KindTable", False, str(exc), red_keys=["<load>"])
        return
    check("镜像装载 = %d 条 kind（真源 %d 条）" % (len(kt), len(pkg_obj)),
          len(kt) == len(pkg_obj) == 18, "条数不符", red_keys=["<load>"])
    check("`validate()` 无问题（引擎口径自检）", kt.validate() == [], str(kt.validate()),
          red_keys=["<validate>"])
    check("抽查字段契约：battle.end ⊇ {result,rounds,p_acts} · battle.start 有 seed",
          set(("result", "rounds", "p_acts")) <= set(kt.fields_of("battle.end"))
          and "seed" in kt.fields_of("battle.start"),
          "字段契约对不上", red_keys=["<fields>"])


def t6_comparator_has_teeth(pkg_obj: dict, host_obj: dict):
    print("【⑥ 反证：比较器有牙（内存对拍，不碰盘）】")
    if not pkg_obj:
        check("有可比样本", False, "真源 0 条，反证无法进行", red_keys=["<empty>"])
        return
    k0 = sorted(pkg_obj)[0]

    changed = json.loads(json.dumps(pkg_obj))
    changed[k0]["fields"] = list(changed[k0].get("fields", [])) + ["__ghost_field__"]
    bad = entry_diff(pkg_obj, changed)
    check("改一条 fields → 必报红，且只红该 kind", bool(bad) and set(bad) == {k0},
          "反例 %s" % bad, red_keys=list(bad))

    changed_desc = json.loads(json.dumps(pkg_obj))
    changed_desc[k0]["desc"] = str(changed_desc[k0].get("desc", "")) + "（改）"
    bad = entry_diff(pkg_obj, changed_desc)
    check("改一条 desc → 必报红，且只红该 kind", bool(bad) and set(bad) == {k0},
          "反例 %s" % bad, red_keys=list(bad))

    dropped = json.loads(json.dumps(pkg_obj))
    dropped.pop(k0)
    bad = entry_diff(pkg_obj, dropped)
    bad.update({k: v for k, v in entry_diff(dropped, pkg_obj).items() if k not in bad})
    check("删一条（镜像少了）→ 必报红该 kind", bool(bad) and set(bad) == {k0},
          "反例 %s" % bad, red_keys=list(bad))

    added = json.loads(json.dumps(pkg_obj))
    added["__ghost_kind__"] = {"fields": [], "desc": "", "category": ""}
    bad = entry_diff(pkg_obj, added)
    bad.update({k: v for k, v in entry_diff(added, pkg_obj).items() if k not in bad})
    check("加一条（镜像多了）→ 必报红该 kind", bool(bad) and set(bad) == {"__ghost_kind__"},
          "反例 %s" % bad, red_keys=list(bad))

    check("原样 → 报绿（不假阳性）",
          entry_diff(pkg_obj, host_obj) == {} and entry_diff(host_obj, pkg_obj) == {})


# ============================================================ 主
def main(argv=None) -> int:
    global PLUGIN_DIR
    ap = argparse.ArgumentParser(description="tlogs 单源门禁（P4′-C）")
    ap.add_argument("--plugin", default=PLUGIN_DIR,
                    help="宿主插件根（读点扫描按它走；默认 = _paths.HOST_ROOT）")
    ap.add_argument("--pkg", default=None, help="真源（包内）；默认 <PKG_ROOT>/%s" % PKG_REL)
    ap.add_argument("--host", default=None, help="镜像（宿主）；默认 <plugin>/%s" % HOST_REL)
    args = ap.parse_args(argv)

    PLUGIN_DIR = os.path.abspath(args.plugin)
    pkg_path = args.pkg or os.path.join(PKG_ROOT, PKG_REL)
    host_path = args.host or os.path.join(PLUGIN_DIR, HOST_REL)

    print("=" * 74)
    print("tlogs 声明表单源门禁（P4′-C）：真源(包内) ↔ 镜像(宿主) 逐条相等 + 反证")
    print("=" * 74)
    print("  真源(包内) = %s" % pkg_path)
    print("  镜像(宿主) = %s" % host_path)
    print("  运行时读点 = %s（只此一处）" % os.path.join(PLUGIN_DIR, READ_POINT_REL))
    print("")

    for label, path in (("真源", pkg_path), ("镜像", host_path)):
        if not os.path.exists(path):
            print("❌ %s不存在：%s" % (label, path))
            print("红 kind 汇总: ['<missing>']")
            print("== 结果：通过 0 / 共 1 ==")
            return 1

    pkg_raw, host_raw = read_raw(pkg_path), read_raw(host_path)
    pkg_obj = json.loads(pkg_raw.decode("utf-8-sig"))
    host_obj = json.loads(host_raw.decode("utf-8-sig"))

    t0_precondition(pkg_raw, host_raw, pkg_obj, host_obj)
    print("")
    t1_entry_equality(pkg_obj, host_obj)
    print("")
    t2_build_mirror(pkg_raw, host_raw)
    print("")
    t3_source_format(pkg_raw, host_raw)
    print("")
    t4_single_read_point()
    print("")
    t5_engine_load(host_path, pkg_obj)
    print("")
    t6_comparator_has_teeth(pkg_obj, host_obj)
    print("")

    red = set(entry_diff(pkg_obj, host_obj)) | set(entry_diff(host_obj, pkg_obj))
    if not pkg_raw or not host_raw:
        red.add("<empty>")
    if norm_eol(pkg_raw) != norm_eol(host_raw):
        red.add("<mirror>")
    red |= RED_MARKERS
    print("红 kind 汇总: %s" % sorted(red))
    print("== 结果：通过 %d / 共 %d ==" % (PASS, PASS + FAIL))
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        return 1
    print("全绿 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
