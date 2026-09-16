#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""门禁：命令注册优先级（priority）声明**双向一致**（B18-L12，P5 前置）。

背景（为什么有这条线）
----------------------
终态口径：**路由与声明的真源在包**（引擎按包内 `content/data/commands.json` 的正则/元数据
路由；见 `saintess_engine/host/package.py::command_declarations()`）。注册优先级
（`priority`）此前**只硬编码在宿主装饰器**里：

    game/commands/world.py    @declared("npc_quick_dialog",   priority=100)
    game/commands/base.py     @declared("_maint_gate",        priority=100)
                              @filter.custom_filter(_GameCmdFilter, priority=100)
    game/commands/economy.py  @declared("item_view_mode_cmd", priority=50)
    game/commands/social.py   @declared("stall_deprecated",   priority=5)

    ★ P5F-REPOINT：宿主壳随删壳批消失 ⇒ 上表已成历史；终态的「装饰器面」= 包内
    `content/*.py` 残留的 `@declared(..., priority=N)` 替身（实测 1 处：`economy_cmds.py`），
    其余 3 条的值只存在于包内声明表（引擎 `CommandSpec.priority` 是唯一读点）。

本线只做「**声明显式化**」：把装饰器里的既有值搬进两份声明表（值一个不改）。
引擎路由按 priority 排序见 `saintess_engine/command/registry.py::_ranked()`。

断言（三条硬要求 + 两条加固）
----------------------------
  ① 宿主声明面（终态 = 包内 `content/*.py`）每个 `@declared(key, priority=N)` /
     `@filter.custom_filter(_, priority=N)` → 包内 `commands.json[key].priority == N`
  ② 包内每条含 `priority` 的 key → **运行时注册表**（引擎 `CommandSpec.priority`）同值
     （**不允许单边存在**：注册表有而表里没有、或表里有而注册表读不到，都算红）
  ③ 两份声明表（**部署期镜像** `game/data/command_specs.json` / 包内 `content/data/commands.json`）
     的 `priority` 字段**逐条相等**（键集与值都相等）
  ④ （加固）包内 `content/*.py` 里残留的 `@declared(..., priority=N)` 替身也必须与包内表同值
     —— 防「搬进来的第三份拷贝」静默漂移
  ⑤ （加固）比较器有牙：内存里改一格 / 删一格 / 加一格 → 必报红；原样 → 报绿
  ⑥ （加固）包内那份仍满足落盘规范：UTF-8 无 BOM · LF · `indent=2` · 末尾换行 · 外层键升序

跑法：`python tests/test_command_priority_sync.py`（exit=0 全绿）
输出末三行固定为：`红 key 汇总: [...]` / `== 结果：通过 N / 共 M ==` / `全绿 ✅`
（反证脚本靠 `红 key 汇总` 这一行判断「只红哪条 key」）
"""
from __future__ import annotations

import ast
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import _paths                                                            # noqa: E402

# ★ 搬迁适配（T8 ③）：旧 `PLUGIN_DIR = dirname(dirname(__file__))` 在宿主布局 = 宿主插件根；
#   文件搬到 `pkg/tests/` 后那是**包根**。宿主专属的部署期镜像走 `_paths.HOST_ROOT`，
#   内容真源走 `_paths.PKG_ROOT`（旧写法的 `<PLUGIN_DIR>/framework/games/orlandia`）。
PLUGIN_DIR = _paths.HOST_ROOT
PKG_ROOT = _paths.PKG_ROOT

# ★ P5F-REPOINT: 原宿主壳那两处（`game/data/command_specs.json` 声明表 + `game/commands/` 的
#   `@declared(..., priority=N)` 装饰器，随删壳批消失）→ 包内真源
#   `content/data/commands.json`（声明表）+ `content/*.py`（priority 替身装饰器）。
PKG_SPEC = os.path.join(PKG_ROOT, "content", "data", "commands.json")
PKG_CONTENT_DIR = os.path.join(PKG_ROOT, "content")
#: 部署期镜像（**保留资产**，不随删壳批消失）= `game/data/command_specs.json`。
#   ★ P5F-REPOINT: ③ 段「两份声明表逐条相等」的**独立对侧**仍是这份镜像（不是包内那份自己）——
#   保留比较对象，判据不削弱；镜像 ↔ 真源漂移当场报红。
MIRROR_SPEC = os.path.join(PLUGIN_DIR, "game", "data", "command_specs.json")

PASS = 0
FAIL = 0
FAILURES: list = []


def check(name, cond, detail="", red_keys=()):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✅ %s" % name)
    else:
        FAIL += 1
        ks = sorted({str(k) for k in red_keys})
        FAILURES.append("%s: %s" % (name, detail))
        print("  ❌ %s  红 key: %s  %s" % (name, ks, detail))


# ============================================================ 读
def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def table_priorities(table) -> dict:
    """声明表 → `{key: priority}`（只取确实写了 priority 的条目）。"""
    out = {}
    for key, entry in (table or {}).items():
        if isinstance(entry, dict) and "priority" in entry:
            out[str(key)] = entry["priority"]
    return out


# ============================================================ AST 扫装饰器
def _kwarg(node, name):
    for kw in node.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def _func_name(func) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return "<expr>"


def scan_priority_sites(cmd_dir: str) -> list:
    """扫一个命令目录：返回 `[(file, lineno, key|None, 装饰器名, priority)]`。

    只认两种**注册**写法（与宿主 `_declared.declared()` / 平台 `filter.custom_filter` 对应）：
      * `@declared("<key>", priority=N)`              → key 取第一个字符串实参
      * `@filter.custom_filter(<任意>, priority=N)`   → key 取被装饰函数名
    其余带 `priority=` 的装饰器 → key=None（由调用方决定是否报红：扫描口径必须完整）。
    纯 static AST：不 import、不执行任何命令代码。
    """
    sites = []
    for fn in sorted(os.listdir(cmd_dir)):
        if not fn.endswith(".py"):
            continue
        with open(os.path.join(cmd_dir, fn), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                prio = _kwarg(dec, "priority")
                if prio is None:
                    continue
                key = None
                dname = _func_name(dec.func)
                if dname == "declared" and dec.args and isinstance(dec.args[0], ast.Constant) \
                        and isinstance(dec.args[0].value, str):
                    key = dec.args[0].value
                elif dname == "custom_filter":
                    key = node.name
                sites.append((fn, dec.lineno, key, dname, prio))
    return sites


def priorities_of(sites, *, label="") -> dict:
    """`[(file, lineno, key, dname, prio)]` → `{key: priority}`；同 key 多值 → 抛。"""
    raw: dict = {}
    for fn, ln, key, _dname, prio in sites:
        if key is None:
            continue
        raw.setdefault(key, {})["%s:%d" % (fn, ln)] = prio
    out = {}
    for key, at in raw.items():
        vals = set(at.values())
        if len(vals) != 1:
            raise ValueError("%skey %r 的 priority 自相矛盾：%s" % (label, key, at))
        out[key] = vals.pop()
    return out


# ============================================================ 比较器（反证直接调它）
def diff_one_way(src: dict, dst: dict) -> list:
    """`src` 每条 priority 都必须在 `dst` 里且相等 → 反例 `[(key, 应有, 实有)]`。

    单向只答「src → dst」；双向一致 = 两个方向都空（这样「单边存在」两个方向各抓一次）。
    """
    return sorted((k, v, dst.get(k)) for k, v in src.items() if dst.get(k) != v)


def fmt(bad) -> str:
    return ", ".join("%s(应有 %s / 实有 %s)" % t for t in bad[:6])


# ============================================================ 断言组
def t0_precondition():
    print("【0. 前置：扫描口径完整（否则 ①② 会空转）】")
    sites = scan_priority_sites(PKG_CONTENT_DIR)
    unknown = sorted({(fn, ln, dname) for fn, ln, key, dname, _p in sites if key is None})
    check("宿主声明面（终态 = 包内 `content/*.py`）里能扫到 priority 注册装饰器（非空）",
          bool(sites), "扫到 0 处 —— 扫描口径失配，①② 会假绿", red_keys=["<scan>"])
    check("带 priority 的装饰器只有 `declared` / `custom_filter` 两种（无未识别写法）",
          not unknown, "未识别：%s（请扩展本门禁的扫描口径）" % (unknown or ""),
          red_keys=[d for _f, _l, d in unknown] or ["<scan>"])
    return sites


def t1_host_to_pkg(deco: dict, pkg: dict):
    print("【① 宿主声明面的装饰器替身 → 包内声明表】")
    bad = diff_one_way(deco, pkg)
    check("每条 `@declared/…priority=N` 都能在包内 commands.json 里找到同值 priority",
          not bad, fmt(bad), red_keys=[k for k, _a, _b in bad])


def runtime_priorities() -> dict:
    """引擎注册表里**实际生效**的 `{key: priority}`（只取声明表显式写了 priority 的 key）。

    ★ P5F-REPOINT: 原「宿主装饰器 priority」这一侧的终态对侧 = 包内声明经引擎
    `CommandRegistry` 装载后的 `CommandSpec.priority`（替身装饰器 + 声明表 + 引擎读值三段合一）。
    """
    from _engine_harness import harness
    decls = harness().host.pkg.command_declarations() or {}
    reg = harness().host.commands
    out = {}
    for key, raw in decls.items():
        spec = reg.get(key)
        if isinstance(raw, dict) and "priority" in raw and spec is not None:
            out[str(key)] = spec.priority
    return out


def t2_pkg_to_host(pkg: dict, runtime: dict):
    print("【② 包内声明表 → 运行时注册表（不允许单边存在）】")
    bad = diff_one_way(pkg, runtime)
    check("包内每条含 priority 的 key 都被运行时注册表以同值装载（无单边声明）",
          not bad, fmt(bad), red_keys=[k for k, _a, _b in bad])
    only_runtime = sorted(set(runtime) - set(pkg))
    check("运行时注册表的 priority 键都在包内表里（单边：仅注册表 %s）" % (only_runtime or "无"),
          not only_runtime, "", red_keys=only_runtime)


def t3_tables_agree(host: dict, pkg: dict, host_tbl: dict, pkg_tbl: dict):
    print("【③ 两份声明表 priority 逐条相等（部署期镜像 ↔ 包内真源）】")
    bad = diff_one_way(host, pkg) + diff_one_way(pkg, host)
    check("部署期镜像 command_specs.json 与包内 commands.json 的 priority 值逐条相等",
          not bad, fmt(bad), red_keys=[k for k, _a, _b in bad])
    check("两份表的 priority 键集相等（%d vs %d）" % (len(host), len(pkg)),
          set(host) == set(pkg), "差集：%s" % sorted(set(host) ^ set(pkg)),
          red_keys=sorted(set(host) ^ set(pkg)))
    check("两份表其它字段也仍然一致（196 条逐条 JSON 相等，防顺手改别的）",
          host_tbl == pkg_tbl,
          "条目差异：%s" % sorted(k for k in set(host_tbl) | set(pkg_tbl)
                                  if host_tbl.get(k) != pkg_tbl.get(k))[:6],
          red_keys=sorted(k for k in set(host_tbl) | set(pkg_tbl)
                          if host_tbl.get(k) != pkg_tbl.get(k)))


def t4_pkg_content_stub(pkg: dict):
    print("【④ 包内 content/*.py 的 priority 替身也必须同值（防第三份拷贝漂移）】")
    sites = scan_priority_sites(PKG_CONTENT_DIR)
    stub = priorities_of(sites, label="包内 content：")
    bad = diff_one_way(stub, pkg)
    check("包内 content/*.py 里残留的 `@declared(..., priority=N)` 与包内表同值",
          not bad, fmt(bad), red_keys=[k for k, _a, _b in bad])
    miss = sorted(set(stub) - set(pkg))
    check("包内 content/*.py 的 priority 装饰器 key 都在包内表里（不存在的 key：%s）"
          % (miss or "无"), not miss, "", red_keys=miss)


def t5_comparator_has_teeth(pkg: dict):
    print("【⑤ 反证：比较器有牙（内存对拍，不碰盘）】")
    base = dict(pkg)
    if not base:
        check("有可比样本（包内至少 1 条 priority）", False, "包内 0 条 priority，反证无法进行",
              red_keys=["<empty>"])
        return
    k0 = sorted(base)[0]

    changed = dict(base)
    changed[k0] = base[k0] + 1
    bad = diff_one_way(base, changed) + diff_one_way(changed, base)
    check("改一格 → 必报红，且只报该 key", bool(bad) and {k for k, _a, _b in bad} == {k0},
          "反例 %s" % (bad,), red_keys=[k for k, _a, _b in bad])

    dropped = dict(base)
    dropped.pop(k0)
    # 「表少了」要由**反方向**抓：另一侧仍有该 key 而这一侧没有 → 必须有反例
    bad = diff_one_way(base, dropped) + diff_one_way(dropped, base)
    check("删一格（表少了）→ 必报红", bool(bad) and {k for k, _a, _b in bad} == {k0},
          "反例 %s" % (bad,), red_keys=[k for k, _a, _b in bad])

    added = dict(base)
    added["__ghost_cmd__"] = 7
    bad = diff_one_way(added, base)
    check("加一格（表多了）→ 必报红", bool(bad) and {k for k, _a, _b in bad} == {"__ghost_cmd__"},
          "反例 %s" % (bad,), red_keys=[k for k, _a, _b in bad])

    check("原样 → 报绿（不假阳性）", diff_one_way(base, dict(base)) == [])


def t6_pkg_on_disk_format():
    print("【⑥ 包内那份仍满足落盘规范】")
    raw = open(PKG_SPEC, "rb").read()
    probs = []
    if raw[:3] == b"\xef\xbb\xbf":
        probs.append("BOM")
    if b"\r\n" in raw:
        probs.append("CRLF")
    if not raw.endswith(b"\n"):
        probs.append("无末尾换行")
    txt = raw.decode("utf-8-sig")
    obj = json.loads(txt)
    if list(obj) != sorted(obj):
        probs.append("外层键非升序")
    if json.dumps(obj, ensure_ascii=False, indent=2) + "\n" != txt:
        probs.append("非 indent=2 规范形")
    check("包内 commands.json：UTF-8 无 BOM / LF / indent=2 / 末尾换行 / 外层键升序",
          not probs, "问题 %s" % (probs,), red_keys=["<format>"])


# ============================================================ 主
def main():
    print("=" * 74)
    print("命令注册优先级（priority）声明双向一致性门禁（B18-L12）")
    print("=" * 74)
    print("  宿主声明表(部署期镜像) = %s" % MIRROR_SPEC)
    print("  包内声明表 = %s" % PKG_SPEC)
    print("  宿主声明面(终态=包内 content) = %s/*.py" % PKG_CONTENT_DIR)
    print("")

    host_tbl = load_json(MIRROR_SPEC) if os.path.exists(MIRROR_SPEC) else {}
    pkg_tbl = load_json(PKG_SPEC)
    host = table_priorities(host_tbl)
    pkg = table_priorities(pkg_tbl)

    sites = t0_precondition()
    deco = priorities_of(sites, label="宿主：")
    runtime = runtime_priorities()
    print("  实测：装饰器替身 %s ｜ 部署期镜像 %s ｜ 包内表 %s ｜ 运行时 %s"
          % (deco, host, pkg, runtime))
    print("")
    t1_host_to_pkg(deco, pkg)
    print("")
    t2_pkg_to_host(pkg, runtime)
    print("")
    t3_tables_agree(host, pkg, host_tbl, pkg_tbl)
    print("")
    t4_pkg_content_stub(pkg)
    print("")
    t5_comparator_has_teeth(pkg)
    print("")
    t6_pkg_on_disk_format()
    print("")

    # 红 key 汇总（反证脚本靠这一行判断「只红哪条 key」）
    red = set()
    red.update(k for k, _a, _b in diff_one_way(deco, pkg))
    red.update(k for k, _a, _b in diff_one_way(pkg, runtime))
    red.update(k for k, _a, _b in diff_one_way(host, pkg))
    red.update(k for k, _a, _b in diff_one_way(pkg, host))
    print("红 key 汇总: %s" % sorted(red))
    print("== 结果：通过 %d / 共 %d ==" % (PASS, PASS + FAIL))
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        return 1
    print("全绿 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
