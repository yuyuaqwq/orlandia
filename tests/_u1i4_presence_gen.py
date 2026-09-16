# -*- coding: utf-8 -*-
"""U1-I4 门禁② 生成器（在场块）—— 25 段冻结文本 / 双 sha256 / aux 指纹。

口径（照 `design/U1-I4_FROZEN_GATE.md` §1.2 · §2.2 · §2.3）
--------------------------------------------------------
* **冻结侧读 `base/pkg/**`**（= 改动前基线），用 `ast` 逐行切片出旧实现文本；
  切片口径 = `min(装饰器行, def 行)` 起、`node.end_lineno` 止，**保留原行尾** ⇒ 与
  `inspect.getsource(<活实现>)` 逐字节相等（生成器自检 ① 当面证明）。
* 生成器输出**只写进** `tests/test_u1i4_presence_frozen.py` 的两行标记之间；
  标记之外的正文（比对逻辑）**一个字节都不碰**。
* 25 段 = `content/wild.py` 18 段 + `content/persistence/world.py` 7 段（后者**只钉不改**）。

四档命令
--------
    python tests/_u1i4_presence_gen.py --check        # 只自检（§1.2 三条），不改文件
    python tests/_u1i4_presence_gen.py --emit-frozen  # 生成 _FROZEN_TEXT + _PIN（红基线档）
    python tests/_u1i4_presence_gen.py --emit-live    # 实现改完后重生成 _PIN["live"]（落档）
    python tests/_u1i4_presence_gen.py --emit-aux     # 生成 _PIN["aux"]（数据面/存档面指纹）

E/C/A 分类（§2.3）
------------------
* **E**（预期不变）：本批不该动的段 —— 生成 `--emit-live` 时**断言 `frozen == live`**。
* **C**（预期会变）：本批会改的段 —— 断言 `frozen != live`。
* **A**（只钉行为）：`_day_hash`，本批**删除** ⇒ `_PIN["live"]` 写哨兵 `"<deleted>"`，
  并断言活模块里**没有**这个名字；它的行为由 `npc_map_id` / `town_npc_day_sa` /
  `town_npc_visible` / `town_npc_dialogue` 四段的逐格比对间接覆盖。

⚠ `--emit-frozen` 只允许在「红基线」之前跑一次；`--emit-live` 生成后 `phase` 变 `landed`
（门禁据此启用 C 栏不等式断言，见测试文件头注）。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(_HERE)
WORK_ROOT = os.path.dirname(PKG_ROOT)
LANE_ROOT = os.path.dirname(WORK_ROOT)
BASE_PKG = None            # ★ 由文件末尾的 _resolve_base_pkg() 解析（改动前基线副本）
BASE_SOURCE = "unresolved"
TEST_FILE = os.path.join(_HERE, "test_u1i4_presence_frozen.py")

BEGIN = "# >>> _u1i4_gen (auto) >>>"
END = "# <<< _u1i4_gen (auto) <<<"

#: 25 段（文件 · 符号），**顺序即门禁内键序**；每一段是「实现线会改或必须证明没改」的整段文本。
SEGMENTS = [
    ("content/wild.py", "_wild_tables"),
    ("content/wild.py", "_ALL_WILD"),
    ("content/wild.py", "_wild_npc_expire"),
    ("content/wild.py", "_day_hash"),
    ("content/wild.py", "npc_map_id"),
    ("content/wild.py", "_quest_known"),
    ("content/wild.py", "unlock_met"),
    ("content/wild.py", "base_conditions_met"),
    ("content/wild.py", "_get_meta"),
    ("content/wild.py", "_save_meta"),
    ("content/wild.py", "met_wild"),
    ("content/wild.py", "_roll_random"),
    ("content/wild.py", "wild_npc_findable"),
    ("content/wild.py", "roll_wild_encounter"),
    ("content/wild.py", "nearby_hints"),
    ("content/wild.py", "town_npc_day_sa"),
    ("content/wild.py", "town_npc_visible"),
    ("content/wild.py", "town_npc_dialogue"),
    ("content/persistence/world.py", "talk_state_key"),
    ("content/persistence/world.py", "talk_flags_key"),
    ("content/persistence/world.py", "get_talk_state"),
    ("content/persistence/world.py", "set_talk_state"),
    ("content/persistence/world.py", "clear_talk_state"),
    ("content/persistence/world.py", "get_talk_flags"),
    ("content/persistence/world.py", "set_talk_flag"),
]

#: **额外**冻结文本（**不计入 25 段**、不进 `_PIN["frozen"]`/`["live"]`）：网格 D 的旧侧夹具。
#: 它们属门禁③（L5）的独占面，本线**只读不改**；这里冻结只为「三份列表实现 旧 ↔ 新 逐行比」。
EXTRA_SEGMENTS = [
    ("content/world_cmds.py", "_current_npcs"),
    ("content/world_cmds.py", "_present_wild_hints"),
    ("content/world_cmds.py", "_start_talk_list"),
    ("content/world_cmds.py", "_map_blocks"),
    ("content/world_cmds.py", "_hurry_section"),
    ("content/world_cmds.py", "_find_npc_in_map"),
    ("content/world_cmds.py", "_find_wild_npc"),
]

#: E / C / A 分类（§2.3）。`wild_npc_findable` / `nearby_hints` 在 `U1-I4_FROZEN_GATE.md` §2.3
#: 的 C 栏里，但本线**实测未改它们的函数体**（改动全部落在它们调用的 `npc_map_id` /
#: `_roll_random` 上）⇒ 归 E 栏并打印取证，见 `out/U1-I9_DESIGN.md` §口径分歧。
CLASS = {
    "content/wild.py::_wild_tables": "E",
    "content/wild.py::_ALL_WILD": "C",
    "content/wild.py::_wild_npc_expire": "E",
    "content/wild.py::_day_hash": "A",
    "content/wild.py::npc_map_id": "C",
    "content/wild.py::_quest_known": "E",
    "content/wild.py::unlock_met": "E",
    "content/wild.py::base_conditions_met": "E",
    "content/wild.py::_get_meta": "E",
    "content/wild.py::_save_meta": "E",
    "content/wild.py::met_wild": "E",
    "content/wild.py::_roll_random": "C",
    "content/wild.py::wild_npc_findable": "E",
    "content/wild.py::roll_wild_encounter": "C",
    "content/wild.py::nearby_hints": "E",
    "content/wild.py::town_npc_day_sa": "C",
    "content/wild.py::town_npc_visible": "C",
    "content/wild.py::town_npc_dialogue": "C",
    "content/persistence/world.py::talk_state_key": "E",
    "content/persistence/world.py::talk_flags_key": "E",
    "content/persistence/world.py::get_talk_state": "E",
    "content/persistence/world.py::set_talk_state": "E",
    "content/persistence/world.py::clear_talk_state": "E",
    "content/persistence/world.py::get_talk_flags": "E",
    "content/persistence/world.py::set_talk_flag": "E",
}

DELETED_SENTINEL = "<deleted>"

#: `design/U1-I4_FROZEN_GATE.md` §1.4 那份 93 段基线里属于本门禁的 **25 条**（全 64 位）。
#: 生成器 `--check` 拿它交叉核对 —— 双向独立来源（设计稿 vs `base/pkg` 切片）必须一致。
_BASELINE_PINS = {
    "content/wild.py::_wild_tables":
        "4ae971cf8344dde190af12049fb7f97448e137dc0d22c4cbc6a350d10c5c0bdf",
    "content/wild.py::_ALL_WILD":
        "03442ee3068495334a8798871bbeeada58031da678cf377ed417b7343e34b4b4",
    "content/wild.py::_wild_npc_expire":
        "efd30d2bd57d22ae5efdf2b2f6526b654a3d24d527c77883531a6d41ff1cc743",
    "content/wild.py::_day_hash":
        "84c12f1574114da1163ed087cd9c18ce49e522be65ebf1837f2796453c72a677",
    "content/wild.py::npc_map_id":
        "9d7b7ad09dc9ecf52724c6956f15a0a747ce95f8ea19f7bf10ff261b21088e46",
    "content/wild.py::_quest_known":
        "1d3e8096e1d936b870150647284bef7f4153d4316df0cd7a124576d03a803753",
    "content/wild.py::unlock_met":
        "3a53328208e986c5399c2f7742b76f774927175cea1eeac6513479f58546a66a",
    "content/wild.py::base_conditions_met":
        "8850d6cb3ef1c5e6d393e2ec7edf970e1742f7e7fe9f95e4247574966df9e21b",
    "content/wild.py::_get_meta":
        "7db56cdbc3e89f1d63bc877193e9eee6ecbe97bcdd59c7c937abdf264a9119ea",
    "content/wild.py::_save_meta":
        "a7f4aed3a9866f4f6163bfb266b9ba422ee0f608da3d24377a016335158eb244",
    "content/wild.py::met_wild":
        "aecd3b97ab0d7994f2ff5bfa2bd397346f508899211c05d76272757bd823bfd6",
    "content/wild.py::_roll_random":
        "2d83db512dcf449d862287d0bd780fc12c1d8ce0594a65affd44db82069f2868",
    "content/wild.py::wild_npc_findable":
        "cda310ff6969af57e55860f379cac836d6df55f851a8d59fe48f8a635a21657a",
    "content/wild.py::roll_wild_encounter":
        "94ab325957303c857d1ba792346129226865f2f101c942b9b4fee9cd15862285",
    "content/wild.py::nearby_hints":
        "0a00016eeda74c9eff9b829bb94952d1e31446ebbad79dcbf98e4cc8235b5fcd",
    "content/wild.py::town_npc_day_sa":
        "7a9cb42dcbadcc4a420e7349c548705f2c94952bc12d858a4d9960404e7c2300",
    "content/wild.py::town_npc_visible":
        "4ae244fb2f2f688e200b2590c0284f1eaf40f2f42959370e290ad28740c776d1",
    "content/wild.py::town_npc_dialogue":
        "61e86c11ad239e6a14939d9af0034736de1413a489e3eb94c84bacafd55e3fcb",
    "content/persistence/world.py::talk_state_key":
        "508250a32e7b298d42bac9831de793b58e6208f298059fc1671192d478318939",
    "content/persistence/world.py::talk_flags_key":
        "38011e8a01e017e7975a78ba17489f376b9765e44ce5da83efeadf9a1a4efb2c",
    "content/persistence/world.py::get_talk_state":
        "d755d4e2a493d8324bfd1858917220534fc047e56206f1697471132f7f69bc12",
    "content/persistence/world.py::set_talk_state":
        "928ed09992a0ee2db0fdfd1f5765829f662587762a15c5074b5432220ee3361b",
    "content/persistence/world.py::clear_talk_state":
        "7e2f0e651b7a83c6a4934d7ebbe2329c0fac0a403a765d1fc57a13fd1589ceb4",
    "content/persistence/world.py::get_talk_flags":
        "d31abb333a6098dcd337ae8fc04253b15df109e88dca667ef7fa5e36ef065f60",
    "content/persistence/world.py::set_talk_flag":
        "1e4037a9c2136c048e3fca3d51d8d447677572c1608adfb79bca35ff978ace60",
}


# ══════════════════════════════════════════════════════════════ 切片口径（§1.2）
def slice_source(path: str, symbol: str) -> str:
    """从 `path` 里切出 `symbol` 的**整段源码文本**（含装饰器，保留原行尾）。

    与 `inspect.getsource` 逐字节一致（`__check_live_equal` 当面证明）。
    """
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    hits = [n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == symbol]
    if len(hits) != 1:
        raise SystemExit("切不出来：%s 里顶层 `def %s` 有 %d 个（期望 1）"
                         % (path, symbol, len(hits)))
    node = hits[0]
    lo = min([d.lineno for d in node.decorator_list] + [node.lineno])
    return "".join(src.splitlines(True)[lo - 1:node.end_lineno])


def key_of(relpath: str, symbol: str) -> str:
    return "%s::%s" % (relpath, symbol)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ───────────────────────────────────────────────────────── base 解析（四级；找不到 fail-closed）
def _resolve_base_pkg():
    """改动前基线副本 —— ① `GWEN_U1I4_BASE_PKG` → ② `<lane>/base/pkg` → ③ `<pkg>/.u1i4_base/pkg`
    → ④ **git 历史回溯**（最近 20 个改动过被测文件的提交里找「25 段切片 sha256 全等设计 pin」的版本）。
    都失败 ⇒ `(None, "none")`，调用方**必须显式报错**（不许静默降级）。
    """
    candidates = []
    env = os.environ.get("GWEN_U1I4_BASE_PKG")
    if env:
        candidates.append(("env", env))
    candidates.append(("lane", os.path.join(LANE_ROOT, "base", "pkg")))
    candidates.append(("repo", os.path.join(PKG_ROOT, ".u1i4_base", "pkg")))
    for tag, path in candidates:
        if os.path.isfile(os.path.join(path, "content", "wild.py")):
            return path, tag
    try:
        import subprocess
        import tempfile
        gd = os.path.join(PKG_ROOT, ".git")
        if os.path.isdir(gd) or os.path.isfile(gd):
            revs = subprocess.run(["git", "-C", PKG_ROOT, "log", "--format=%H", "-n", "20",
                                   "--", "content/wild.py", "content/persistence/world.py"],
                                  capture_output=True, text=True).stdout.split()
            tmp = tempfile.mkdtemp(prefix="u1i4p_base_")
            for rev in revs:
                ok = True
                for rel in ("content/wild.py", "content/persistence/world.py"):
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
    """候选 base 的 25 段切片是否全等 `_BASELINE_PINS`。"""
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


def frozen_slices() -> dict:
    """25 段冻结文本（读 `base/pkg/**`）+ 7 段额外夹具（网格 D 的旧侧，不计入 25）。"""
    if BASE_PKG is None:
        raise SystemExit(_no_base_msg())
    out = {}
    for relpath, symbol in SEGMENTS:
        out[key_of(relpath, symbol)] = slice_source(os.path.join(BASE_PKG, *relpath.split("/")),
                                                    symbol)
    return out


def _no_base_msg() -> str:
    return ("❌ 找不到改动前基线（base/pkg）—— 生成器**拒绝执行**（fail-closed，不静默降级）。\n"
            "   解析顺序：GWEN_U1I4_BASE_PKG → <lane>/base/pkg → <pkg>/.u1i4_base/pkg → git 历史回溯\n"
            "   启用方式：GWEN_U1I4_BASE_PKG=<含 content/wild.py 的 pkg 目录>  或  在包仓根放 .u1i4_base/pkg/")


def extra_slices() -> dict:
    if BASE_PKG is None:
        raise SystemExit(_no_base_msg())
    out = {}
    for relpath, symbol in EXTRA_SEGMENTS:
        out[key_of(relpath, symbol)] = slice_source(os.path.join(BASE_PKG, *relpath.split("/")),
                                                    symbol)
    return out


# ══════════════════════════════════════════════════════════════ 活侧取件
def _boot_work_pkg():
    """把 `work/pkg`（+ tests + shim + 引擎根 + 宿主壳根）摆进 `sys.path` 并兜底沙箱环境变量。"""
    lane = LANE_ROOT
    os.environ.setdefault("GWEN_FRAMEWORK_DIR", os.path.join(lane, "work", "eng"))
    os.environ.setdefault("GWEN_HOST_DIR", os.path.join(lane, "work", "host"))
    os.environ.setdefault("GWEN_GAME_DB", os.path.join(lane, "out", "test_u1i4_presence.db"))
    os.environ.setdefault("GWEN_TEST_MODE", "1")
    os.environ.setdefault("PYTHONUTF8", "1")
    shim = os.path.join(_HERE, "shim_astrbot")
    for p in (shim, _HERE, PKG_ROOT,
              os.environ["GWEN_FRAMEWORK_DIR"], os.environ["GWEN_HOST_DIR"]):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


def live_object(relpath: str, symbol: str):
    """活模块里的对象；`_day_hash` 这类被删符号 → `None`。"""
    _boot_work_pkg()
    modname = "content." + relpath.split("/", 1)[1][:-3].replace("/", ".")
    mod = importlib.import_module(modname)
    return getattr(mod, symbol, None)


def live_pins() -> dict:
    import inspect
    out = {}
    for relpath, symbol in SEGMENTS:
        obj = live_object(relpath, symbol)
        if obj is None:
            out[key_of(relpath, symbol)] = DELETED_SENTINEL
        else:
            out[key_of(relpath, symbol)] = sha256_text(inspect.getsource(obj))
    return out


# ══════════════════════════════════════════════════════════════ 自检（§1.2 三条）
def self_check(*, with_live=True) -> list:
    """三条自检；返回打印用的行列表。任何一条不过 → 抛 SystemExit。"""
    lines = []
    frozen = frozen_slices()
    if len(frozen) != 25:
        raise SystemExit("自检②失败：切片数 = %d（期望 25）" % len(frozen))
    lines.append("  ① 段数 = %d（期望 25）" % len(frozen))

    for key, text in frozen.items():
        try:
            ast.parse(text)
        except SyntaxError as exc:
            raise SystemExit("自检②失败：%s 切片不能 ast.parse：%s" % (key, exc))
        n = text.count("def %s(" % key.split("::")[1])
        if n != 1:
            raise SystemExit("自检③失败：%s 里 `def %s(` 出现 %d 次（期望 1）"
                             % (key, key.split("::")[1], n))
    lines.append("  ② 25 段切片全部 ast.parse 可编译")

    # ③ 不出现下一段的首行（防切片越界吞掉后面的函数）
    for i, (relpath, symbol) in enumerate(SEGMENTS[:-1]):
        nxt_rel, nxt_sym = SEGMENTS[i + 1]
        if nxt_rel != relpath:
            continue
        text = frozen[key_of(relpath, symbol)]
        marker = "def %s(" % nxt_sym
        if marker in text:
            raise SystemExit("自检③失败：%s 的切片里出现下一段首行 %r" % (
                key_of(relpath, symbol), marker))
    lines.append("  ③ 无切片越界（下一段首行不出现）")

    # ④ 与设计稿 §1.4 的 93 段基线交叉核对（双向独立来源：设计稿 vs base/pkg 切片）
    if len(_BASELINE_PINS) != 25:
        raise SystemExit("自检④失败：内嵌基线 25 条，实际 %d 条" % len(_BASELINE_PINS))
    mismatch = [k for k, want in _BASELINE_PINS.items()
                if sha256_text(frozen.get(k, "")) != want]
    if mismatch:
        raise SystemExit("自检④失败：与 design/U1-I4_FROZEN_GATE.md §1.4 基线不一致：%s"
                         % ", ".join(mismatch))
    lines.append("  ④ 25 条冻结 sha256 == `FROZEN_GATE.md` §1.4 基线（全 64 位）")

    if with_live:
        live = live_pins()
        bad = []
        for key, cls in CLASS.items():
            if cls == "E" and live[key] != sha256_text(frozen[key]):
                bad.append(key)
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
           "# ⚠ 本块由 `tests/_u1i4_presence_gen.py` 生成 —— 手工改动 = 门禁失去安全网。",
           "# 冻结侧读 `base/pkg/**`（改动前基线）；`_PIN[\"live\"]` 由 --emit-live 重生成。",
           "", "_FROZEN_TEXT = {"]
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        out.append("    %r: %r," % (k, frozen[k]))
    out.append("    # ── 额外夹具（不计入 25 段）：网格 D 旧侧（门禁③ 的文件，本线只读不改）──")
    for relpath, symbol in EXTRA_SEGMENTS:
        k = key_of(relpath, symbol)
        out.append("    %r: %r," % (k, extra_slices()[k]))
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
    for label in ("E", "C", "A"):
        keys = [key_of(r, s) for r, s in SEGMENTS if CLASS[key_of(r, s)] == label]
        out.append("        %r: [" % label)
        for k in keys:
            out.append("            %r," % k)
        out.append("        ],")
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
    exec(compile(src[i:j], "<pin>", "exec"), ns)                    # noqa: S102
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
    print("【--emit-frozen】冻结 25 段（base/pkg）+ 红基线 live pin")
    frozen = frozen_slices()
    live = live_pins()
    _emit("baseline", live=live)
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        print("  [%s] %-46s frozen=%s live=%s%s"
              % (CLASS[k], k, sha256_text(frozen[k])[:12], live[k][:12],
                 "  ← 删除哨兵" if live[k] == DELETED_SENTINEL else ""))
    print("  （额外夹具 %d 段：网格 D 旧侧，不进 _PIN）" % len(EXTRA_SEGMENTS))


def _emit_live() -> None:
    print("【--emit-live】重生成 _PIN[\"live\"]（落档）+ E/C/A 断言")
    frozen = frozen_slices()
    live = live_pins()
    bad = []
    report = []
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        cls = CLASS[k]
        f = sha256_text(frozen[k])
        l = live[k]
        changed = (l != f)
        if cls == "E":
            ok = (not changed)
            want = "frozen == live"
        elif cls == "C":
            ok = changed
            want = "frozen != live"
        else:                                                        # A：已删除
            ok = (l == DELETED_SENTINEL)
            want = "live == <deleted>"
        if not ok:
            bad.append("%s（%s：%s；frozen=%s live=%s）" % (k, cls, want, f[:12], str(l)[:12]))
        report.append("  [%s] %-46s %-8s frozen=%s live=%s"
                      % (cls, k, "CHANGED" if changed else "same", f[:12], str(l)[:12]))
    for line in report:
        print(line)
    if bad:
        raise SystemExit("E/C/A 分类断言失败（共 %d 条）：\n    %s" % (len(bad), "\n    ".join(bad)))
    _emit("landed", live=live)
    print("  E/C/A 分类断言全过 → phase=landed")


def _emit_aux() -> None:
    print("【--emit-aux】数据面 / 存档面指纹（跑活实现取产物）")
    _boot_work_pkg()
    spec = importlib.util.spec_from_file_location("_u1i4_presence_gate", TEST_FILE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    aux = gate._aux_fingerprints()
    cur = _current_pin()
    phase = cur.get("phase")
    _emit(phase if phase in ("baseline", "landed") else "baseline", aux=aux)
    for k in sorted(aux):
        print("  %-22s %s" % (k, str(aux[k])[:72]))


BASE_PKG, BASE_SOURCE = _resolve_base_pkg()      # ★ 必须在 slice_source / SEGMENTS / _BASELINE_PINS 之后


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="U1-I4 门禁② 生成器（在场块）")
    ap.add_argument("--check", action="store_true", help="只自检（§1.2 三条），不改文件")
    ap.add_argument("--no-live", action="store_true", help="自检跳过「活实现」那一条")
    ap.add_argument("--emit-frozen", action="store_true", help="生成 _FROZEN_TEXT + _PIN（红基线）")
    ap.add_argument("--emit-live", action="store_true", help="重生成 _PIN['live']（落档）")
    ap.add_argument("--emit-aux", action="store_true", help="生成 _PIN['aux']")
    args = ap.parse_args(argv)
    if not (args.check or args.emit_frozen or args.emit_live or args.emit_aux):
        ap.print_help()
        return 2
    print("== U1-I4 门禁② 生成器 ==")
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
