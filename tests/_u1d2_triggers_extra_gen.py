# -*- coding: utf-8 -*-
"""U1-D2 门禁④ 生成器（触发器追加四件）—— 9 段冻结文本 / 双 sha256 / aux 指纹。

口径（照 `design/U1-D2_FROZEN_GATE.md` §1.2 · §2.2 · §2.3 与作业书 §2）
--------------------------------------------------------------------
* **冻结侧读 `base/pkg/**`**（= 改动前基线副本；本工作区 `base/pkg == work/pkg`（源文件口径）），
  用 `ast` 逐行切片出旧实现文本；切片口径 = `min(装饰器行, def 行)` 起、`node.end_lineno` 止、
  **保留原行尾** ⇒ 与 `inspect.getsource(<活实现>)` 逐字节相等（`--emit-frozen` 时对**全部 9 段**
  当面证明，不只 E 栏）。
* 生成器输出**只写进** `tests/test_u1d2_triggers_extra_frozen.py` 的两行标记之间；
  标记之外的正文（比对逻辑）**一个字节都不碰**。
* 9 段 = `bar_procs`(1) · `cond_procs`(1) · `element_procs`(1) · `class_mech`(6)。

档位（机械判据，`FROZEN_GATE.md` §1.3）：`丙` ⟺ `async def`；否则 `乙` ⟺ 段内出现 `self.`；
否则 `甲`。本门禁 = **甲 9 / 乙 0 / 丙 0**（与 `FROZEN_GATE.md` §0 一致）。

E/C 分类（`FROZEN_GATE.md` §2.3）
--------------------------------
* **C**（预期会变）：**全 9 段**。本线把 9 段里的「手写判重 + 手写追加」换成 `_DECL.mount(...)`，
  段文本必然变 → `frozen != live`。
  ⚠ 与设计稿 `FROZEN_GATE.md` §2.3 E 栏（把 `class_mech` 6 段列为「不该动」）**冲突**：
  §1.4 明说这 6 段「**包含挂载点**」，而作业书 §2 要求改这些挂载点 ⇒ 文本必变；
  本生成器按「9 段全 C」落地，冲突与证据写进 `out/LANDING.md`「没验证什么 / 分歧」一节。
* **E**：无（0 段）。

四档命令
--------
    python tests/_u1d2_triggers_extra_gen.py --check        # 只自检，不改文件
    python tests/_u1d2_triggers_extra_gen.py --emit-frozen  # 生成 _FROZEN_TEXT + _PIN（红基线档）
    python tests/_u1d2_triggers_extra_gen.py --emit-live    # 实现改完后重生成 _PIN["live"]
    python tests/_u1d2_triggers_extra_gen.py --emit-aux     # 生成 _PIN["aux"]（改动前抓一次）
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(_HERE)
WORK_ROOT = os.path.dirname(PKG_ROOT)
LANE_ROOT = os.path.dirname(WORK_ROOT)
BASE_PKG = None            # ★ 由文件末尾的 _resolve_base_pkg() 解析（改动前基线副本）
BASE_SOURCE = "unresolved"
TEST_FILE = os.path.join(_HERE, "test_u1d2_triggers_extra_frozen.py")

BEGIN = "# >>> _u1d2_triggers_extra_gen (auto) >>>"
END = "# <<< _u1d2_triggers_extra_gen (auto) <<<"

#: 9 段（文件 · 符号），**顺序即门禁内键序**（照 `FROZEN_GATE.md` §1.4 门禁④ 的列出序）。
SEGMENTS = [
    ("content/mech/bar_procs.py", "apply_bar_procs"),
    ("content/mech/cond_procs.py", "apply_cond_procs"),
    ("content/mech/element_procs.py", "apply_element_procs"),
    ("content/mech/class_mech.py", "_melody_ensure_tick"),
    ("content/mech/class_mech.py", "class_stance_guard_enter"),
    ("content/mech/class_mech.py", "class_guard_stance_enter"),
    ("content/mech/class_mech.py", "apply_class_channels"),
    ("content/mech/class_mech.py", "apply_class_passives"),
    ("content/mech/class_mech.py", "apply_class_mech"),
]

#: E / C 分类（见模块头注）。本线 9 段全 C。
CLASS = {key: "C" for key in ("%s::%s" % (r, s) for r, s in SEGMENTS)}

#: `design/U1-D2_FROZEN_GATE.md` §1.4 那份 74 段基线里属于本门禁的 **9 条**（全 64 位）。
#: 生成器 `--check` 拿它交叉核对 —— 双向独立来源（设计稿 vs `base/pkg` 切片）必须一致。
_BASELINE_PINS = {
    "content/mech/bar_procs.py::apply_bar_procs":
        "3e1a13799f18a4f7d93ee52aaac8e2fffb2993fbe1fc273f1e79827e26782f30",
    "content/mech/cond_procs.py::apply_cond_procs":
        "341faa80d822131320bf81d6d8a840839b6c488f192221e2402759089f99f1dc",
    "content/mech/element_procs.py::apply_element_procs":
        "801a0fa4f61b1392157ed3e66284e020901e65fb390f49b85e27cf28508c87e7",
    "content/mech/class_mech.py::_melody_ensure_tick":
        "cfe5068bd72fcfa520cb1425a1e8aa2164f9acddf0f8d531dfd9c7dec72c224b",
    "content/mech/class_mech.py::class_stance_guard_enter":
        "e9f80aa38ef2261ac6d3c96dc000be53ff2755d2c6fc96f02092db53e5a8d2de",
    "content/mech/class_mech.py::class_guard_stance_enter":
        "8eea84e72f6f9b0598bdd64b4ced8fba77fae24e99d0faf3ed2615ffb53f130f",
    "content/mech/class_mech.py::apply_class_channels":
        "5eacb60626f7ea6c609352f8ce1a2f087708baca35fe69e43479d4dcf9e5edf1",
    "content/mech/class_mech.py::apply_class_passives":
        "5471cced46ea0e3984bf69b81938d0eee412b04f13168952f7c379b2434782ea",
    "content/mech/class_mech.py::apply_class_mech":
        "d127924ba577d96d587565bd74532ac5399efb4873e4c95f2196bc208e1bc235",
}


# ══════════════════════════════════════════════════════════════ 切片口径（§1.2）
def slice_source(path: str, symbol: str) -> str:
    """从 `path` 里切出 `symbol` 的**整段源码文本**（含装饰器，保留原行尾）。"""
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    hits = [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == symbol]
    if len(hits) != 1:
        raise SystemExit("切不出来：%s 里 `def %s` 有 %d 个（期望 1）"
                         % (path, symbol, len(hits)))
    node = hits[0]
    lo = min([d.lineno for d in node.decorator_list] + [node.lineno])
    return "".join(src.splitlines(True)[lo - 1:node.end_lineno])


def key_of(relpath: str, symbol: str) -> str:
    return "%s::%s" % (relpath, symbol)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tier_of(text: str) -> str:
    """机械档位（§1.3）：`async def` → 丙；含 `self.` → 乙；否则 甲。"""
    if "async def " in text:
        return "丙"
    if "self." in text:
        return "乙"
    return "甲"


# ─────────────────────────────────────────────── base 解析（四级；找不到 fail-closed）
def _resolve_base_pkg():
    """改动前基线副本 —— ① `GWEN_U1D2_L7_BASE_PKG` → ② `<lane>/base/pkg` →
    ③ `<pkg>/.u1d2_l7_base/pkg` → ④ **git 历史回溯**（只读 `git log/show`；无 `.git` 即跳过）。

    都失败 ⇒ `(None, "none")`，调用方**必须显式报错**（fail-closed，不静默降级）。
    """
    candidates = []
    env = os.environ.get("GWEN_U1D2_L7_BASE_PKG")
    if env:
        candidates.append(("env", env))
    candidates.append(("lane", os.path.join(LANE_ROOT, "base", "pkg")))
    candidates.append(("repo", os.path.join(PKG_ROOT, ".u1d2_l7_base", "pkg")))
    for tag, path in candidates:
        if os.path.isfile(os.path.join(path, "content", "mech", "bar_procs.py")):
            if _base_matches_pins(path):
                return path, tag
            return path, tag + "(pin-mismatch)"
    try:
        import subprocess
        import tempfile
        gd = os.path.join(PKG_ROOT, ".git")
        if os.path.isdir(gd) or os.path.isfile(gd):
            probe_files = sorted({rel for rel, _sym in SEGMENTS})
            revs = subprocess.run(["git", "-C", PKG_ROOT, "log", "--format=%H", "-n", "20",
                                   "--", *probe_files],
                                  capture_output=True, text=True).stdout.split()
            tmp = tempfile.mkdtemp(prefix="u1d2l7_base_")
            for rev in revs:
                ok = True
                for rel in probe_files:
                    blob = subprocess.run(["git", "-C", PKG_ROOT, "show", "%s:%s" % (rev, rel)],
                                          capture_output=True).stdout
                    if not blob:
                        ok = False
                        break
                    dst = os.path.join(tmp, rel.replace("/", os.sep))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(dst, "wb") as fh:
                        fh.write(blob)
                if ok and _base_matches_pins(tmp):
                    return tmp, "git:%s" % rev[:8]
    except Exception as exc:                                     # noqa: BLE001
        print("[gen] ⚠️ git 回溯失败：%r" % (exc,))
    return None, "none"


def _base_matches_pins(path) -> bool:
    """候选 base 的 9 段切片是否全等 `_BASELINE_PINS`。"""
    try:
        for relpath, symbol in SEGMENTS:
            want = _BASELINE_PINS.get(key_of(relpath, symbol))
            if want is None:
                return False
            got = sha256_text(slice_source(os.path.join(path, *relpath.split("/")), symbol))
            if got != want:
                return False
        return True
    except Exception:                                            # noqa: BLE001
        return False


def _no_base_msg() -> str:
    return ("❌ 找不到改动前基线（base/pkg）—— 生成器**拒绝执行**（fail-closed，不静默降级）。\n"
            "   解析顺序：GWEN_U1D2_L7_BASE_PKG → <lane>/base/pkg → <pkg>/.u1d2_l7_base/pkg → git 历史回溯\n"
            "   启用方式：GWEN_U1D2_L7_BASE_PKG=<含 content/mech/bar_procs.py 的 pkg 目录>")


def frozen_slices() -> dict:
    if BASE_PKG is None:
        raise SystemExit(_no_base_msg())
    out = {}
    for relpath, symbol in SEGMENTS:
        out[key_of(relpath, symbol)] = slice_source(
            os.path.join(BASE_PKG, *relpath.split("/")), symbol)
    return out


# ══════════════════════════════════════════════════════════════ 活侧取件
def _boot_work_pkg():
    """把 `work/pkg`（+ tests + shim + 引擎根 + 宿主壳根）摆进 `sys.path` 并兜底沙箱环境变量。"""
    lane = LANE_ROOT
    os.environ.setdefault("GWEN_FRAMEWORK_DIR", os.path.join(lane, "work", "eng"))
    os.environ.setdefault("GWEN_HOST_DIR", os.path.join(lane, "work", "host"))
    os.environ.setdefault("GWEN_GAME_DB", os.path.join(lane, "out", "test_u1d2_L7.db"))
    os.environ.setdefault("GWEN_TEST_MODE", "1")
    shim = os.path.join(_HERE, "shim_astrbot")
    for p in (shim, _HERE, PKG_ROOT,
              os.environ["GWEN_FRAMEWORK_DIR"], os.environ["GWEN_HOST_DIR"]):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    import _paths                                                        # noqa: F401
    import _engine_harness                                               # noqa: F401


def _modname_of(relpath: str) -> str:
    return "content." + relpath.split("/", 1)[1][:-3].replace("/", ".")


def live_object(relpath: str, symbol: str):
    """活模块里的对象（本门禁 9 段全是模块级函数）。"""
    _boot_work_pkg()
    mod = importlib.import_module(_modname_of(relpath))
    return getattr(mod, symbol, None)


def live_pins() -> dict:
    import inspect
    out = {}
    for relpath, symbol in SEGMENTS:
        obj = live_object(relpath, symbol)
        out[key_of(relpath, symbol)] = (
            None if obj is None else sha256_text(inspect.getsource(obj)))
    return out


# ══════════════════════════════════════════════════════════════ 自检（§1.2 四条）
def self_check(*, with_live=True) -> list:
    lines = []
    frozen = frozen_slices()
    if len(frozen) != 9:
        raise SystemExit("自检①失败：切片数 = %d（期望 9）" % len(frozen))
    lines.append("  ① 段数 = %d（期望 9）" % len(frozen))

    for key, text in frozen.items():
        try:
            ast.parse(text if not text[:1].isspace() else "class _FrozenNS:\n" + text)
        except SyntaxError as exc:
            raise SystemExit("自检②失败：%s 切片不能 ast.parse：%s" % (key, exc))
        n = text.count("def %s(" % key.split("::")[1])
        if n != 1:
            raise SystemExit("自检③失败：%s 里 `def %s(` 出现 %d 次（期望 1）"
                             % (key, key.split("::")[1], n))
    lines.append("  ② 9 段切片全部 ast.parse 可编译")

    for i, (relpath, symbol) in enumerate(SEGMENTS[:-1]):
        nxt_rel, nxt_sym = SEGMENTS[i + 1]
        if nxt_rel != relpath:
            continue
        text = frozen[key_of(relpath, symbol)]
        marker = "def %s(" % nxt_sym
        if marker in text:
            raise SystemExit("自检③失败：%s 的切片里出现下一段首行 %r"
                             % (key_of(relpath, symbol), marker))
    lines.append("  ③ 无切片越界（下一段首行不出现）")

    if len(_BASELINE_PINS) != 9:
        raise SystemExit("自检④失败：内嵌基线 9 条，实际 %d 条" % len(_BASELINE_PINS))
    mismatch = [k for k, want in _BASELINE_PINS.items()
                if sha256_text(frozen.get(k, "")) != want]
    if mismatch:
        raise SystemExit("自检④失败：与 design/U1-D2_FROZEN_GATE.md §1.4 基线不一致：%s"
                         % ", ".join(mismatch))
    lines.append("  ④ 9 条冻结 sha256 == `FROZEN_GATE.md` §1.4 基线（全 64 位）")
    lines.append("  ⑤ 档位（机械判据）：甲 %d / 乙 %d / 丙 %d"
                 % (sum(1 for v in frozen.values() if tier_of(v) == "甲"),
                    sum(1 for v in frozen.values() if tier_of(v) == "乙"),
                    sum(1 for v in frozen.values() if tier_of(v) == "丙")))

    if with_live:
        live = live_pins()
        bad = [k for k, cls in CLASS.items()
               if cls == "E" and live.get(k) != sha256_text(frozen[k])]
        if bad:
            raise SystemExit("自检①失败：E 栏段「切片(base) ≠ inspect.getsource(活实现)」：%s"
                             % ", ".join(bad))
        lines.append("  ① E 栏切片(base) == inspect.getsource(活实现)（%d 段）"
                     % sum(1 for v in CLASS.values() if v == "E"))
    else:
        lines.append("  ① 跳过（--no-live）")
    return lines


# ══════════════════════════════════════════════════════════════ 写盘（标记区）
def _render(frozen: dict, pin: dict) -> str:
    out = [BEGIN, "",
           "# ⚠ 本块由 `tests/_u1d2_triggers_extra_gen.py` 生成 —— 手工改动 = 门禁失去安全网。",
           "# 冻结侧读 `base/pkg/**`（改动前基线）；`_PIN[\"live\"]` 由 --emit-live 重生成。",
           "", "_FROZEN_TEXT = {"]
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        out.append("    %r: %r," % (k, frozen[k]))
    out.append("}")
    out.append("")
    out.append("_PIN = {")
    out.append("    %r: %r," % ("phase", pin["phase"]))
    for section in ("frozen", "live", "aux"):
        out.append("    %r: {" % section)
        if section == "aux":
            order = sorted(pin[section])
        else:
            order = [key_of(r, s) for r, s in SEGMENTS if key_of(r, s) in pin[section]]
        for k in order:
            out.append("        %r: %r," % (k, pin[section][k]))
        out.append("    },")
    out.append("    'segments': {")
    for label in ("E", "C"):
        keys = [key_of(r, s) for r, s in SEGMENTS if CLASS[key_of(r, s)] == label]
        out.append("        %r: [" % label)
        for k in keys:
            out.append("            %r," % k)
        out.append("        ],")
    out.append("    },")
    out.append("    'tier': {")
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        out.append("        %r: %r," % (k, tier_of(frozen[k])))
    out.append("    },")
    out.append("}")
    out.append(END)
    return "\n".join(out)


def _read_test_file() -> str:
    with open(TEST_FILE, encoding="utf-8") as fh:
        return fh.read()


def _write_region(text: str) -> None:
    src = _read_test_file()
    i = src.index(BEGIN)
    j = src.index(END) + len(END)
    with open(TEST_FILE, "w", encoding="utf-8", newline="") as fh:
        fh.write(src[:i] + text + src[j:])
    print("  → 已写入 %s 标记区" % os.path.basename(TEST_FILE))


def _current_pin() -> dict:
    src = _read_test_file()
    i = src.index(BEGIN)
    j = src.index(END) + len(END)
    ns = {}
    exec(compile(src[i:j], "<pin>", "exec"), ns)                 # noqa: S102
    return ns["_PIN"]


def _emit(phase: str, *, aux=None, live=None) -> None:
    frozen = frozen_slices()
    pin = _current_pin()
    pin["phase"] = phase
    pin["frozen"] = {k: sha256_text(v) for k, v in frozen.items()}
    pin["live"] = live if live is not None else pin["live"]
    if aux is not None:
        pin["aux"] = aux
    _write_region(_render(frozen, pin))


def _emit_frozen() -> None:
    print("【--emit-frozen】冻结 9 段（base/pkg）+ 红基线 live pin + aux（改动前抓一次）")
    import inspect
    frozen = frozen_slices()
    live = live_pins()
    bad = []
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        got = sha256_text(inspect.getsource(live_object(relpath, symbol)))
        if got != sha256_text(frozen[k]):
            bad.append(k)
    if bad:
        raise SystemExit("红基线自证失败：切片(base) ≠ inspect.getsource(活实现)：%s"
                         % ", ".join(bad))
    # aux（改动前）：39 个动作体哈希 —— §3-⑭
    _boot_work_pkg()
    spec = importlib.util.spec_from_file_location("_u1d2_l7_gate", TEST_FILE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    aux = gate._aux_fingerprints()
    _emit("baseline", live=live, aux=aux)
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        print("  [%s/%s] %-56s frozen=%s live=%s"
              % (CLASS[k], tier_of(frozen[k]), k, sha256_text(frozen[k])[:12], live[k][:12]))
    print("  （红基线自证：9/9 段 切片(base) == inspect.getsource(活实现)）")
    print("  （aux：%d 条，class_mech 动作体 39 个 + 2 条汇总）" % len(aux))


def _emit_live() -> None:
    print("【--emit-live】重生成 _PIN[\"live\"]（落档）+ E/C 断言")
    frozen = frozen_slices()
    live = live_pins()
    bad = []
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        cls = CLASS[k]
        f = sha256_text(frozen[k])
        l = live[k]
        changed = (l != f)
        if cls == "E":
            ok, want = (not changed), "frozen == live"
        else:
            ok, want = changed, "frozen != live"
        if not ok:
            bad.append("%s（%s：%s；frozen=%s live=%s）" % (k, cls, want, f[:12], str(l)[:12]))
        print("  [%s/%s] %-56s %-8s frozen=%s live=%s"
              % (cls, tier_of(frozen[k]), k, "CHANGED" if changed else "same", f[:12], str(l)[:12]))
    if bad:
        raise SystemExit("E/C 分类断言失败（共 %d 条）：\n    %s" % (len(bad), "\n    ".join(bad)))
    _emit("landed", live=live)
    print("  E/C 分类断言全过 → phase=landed")


def _emit_aux() -> None:
    print("【--emit-aux】class_mech 动作体指纹（跑活实现取件）")
    _boot_work_pkg()
    spec = importlib.util.spec_from_file_location("_u1d2_l7_gate", TEST_FILE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    aux = gate._aux_fingerprints()
    cur = _current_pin()
    phase = cur.get("phase")
    _emit(phase if phase in ("baseline", "landed") else "baseline", aux=aux)
    for k in sorted(aux):
        if not k.startswith("class_mech_action::"):
            print("  %-28s %s" % (k, str(aux[k])[:72]))


BASE_PKG, BASE_SOURCE = _resolve_base_pkg()      # ★ 必须在 slice_source / SEGMENTS 之后


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="U1-D2 门禁④ 生成器（触发器追加四件）")
    ap.add_argument("--check", action="store_true", help="只自检（§1.2 四条），不改文件")
    ap.add_argument("--no-live", action="store_true", help="自检跳过「活实现」那一条")
    ap.add_argument("--emit-frozen", action="store_true", help="生成 _FROZEN_TEXT + _PIN（红基线）")
    ap.add_argument("--emit-live", action="store_true", help="重生成 _PIN['live']（落档）")
    ap.add_argument("--emit-aux", action="store_true", help="生成 _PIN['aux']")
    args = ap.parse_args(argv)
    if not (args.check or args.emit_frozen or args.emit_live or args.emit_aux):
        ap.print_help()
        return 2
    print("== U1-D2 门禁④ 生成器（触发器追加四件）==")
    print("  base/pkg = %s  [%s]" % (BASE_PKG if BASE_PKG else "(未找到)", BASE_SOURCE))
    print("  work/pkg = %s" % PKG_ROOT)
    if BASE_PKG is None:
        print(_no_base_msg())
        return 2
    if args.check:
        for line in self_check(with_live=not args.no_live):
            print(line)
        print("自检：通过")
    if args.emit_frozen:
        _emit_frozen()
    if args.emit_live:
        _emit_live()
    if args.emit_aux:
        _emit_aux()
    print("生成器：完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
