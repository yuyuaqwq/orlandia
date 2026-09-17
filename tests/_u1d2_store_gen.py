# -*- coding: utf-8 -*-
"""U1-D2 门禁② 生成器（存档块 L5）—— 23 段冻结文本 / 双 sha256 / aux 指纹。

口径（照 `design/U1-D2_FROZEN_GATE.md` §1.2 · §2.2 · §2.3 与 `U1-D2_BATCHES.md` §5）
----------------------------------------------------------------------------------
* **冻结侧读 `base/pkg/**`**（= 改动前基线；本工作区 `base/pkg == work/pkg`，开工时冻结），
  用 `ast` 逐行切片出旧实现文本；切片口径 = `min(装饰器行, def 行)` 起、
  `node.end_lineno` 止、**保留原行尾** ⇒ 与 `inspect.getsource(<活实现>)` 逐字节相等
  （`--emit-frozen` 时对**全部 23 段**当面证明，不只 E 栏）。
* 生成器输出**只写进** `tests/test_u1d2_store_frozen.py` 的两行标记之间；
  标记之外的正文（比对逻辑）**一个字节都不碰**。
* 23 段 = `battle_state.py`(6) + `stats.py`(5) + `props_use.py`(3) + `worlds.py`(9)。

档位（机械判据，`FROZEN_GATE.md` §1.3）：`丙` ⟺ `async def`；否则 `乙` ⟺ 段内出现 `self.`；
否则 `甲`。本门禁 = **甲 23 / 乙 0 / 丙 0**（与 `FROZEN_GATE.md` §0 一致）。

⚠️ base 解析四级（`U1-D2_BATCHES.md` §5 步骤 1）照 `_u1i4_wiring_outer_gen.py:147-212` 复制骨架：
`GWEN_U1D2_BASE_PKG` → `<lane>/base/pkg` → `<pkg>/.u1d2_base/pkg` → git 历史回溯；全失败
⇒ **fail-closed 拒绝执行**（不静默降级）。`work/pkg` 无 `.git`，故 git 档在本工作区不会跑。

四档命令
--------
    python tests/_u1d2_store_gen.py --check        # 只自检，不改文件
    python tests/_u1d2_store_gen.py --emit-frozen  # 生成 _FROZEN_TEXT + _PIN（红基线）
    python tests/_u1d2_store_gen.py --emit-live    # 实现改完后重生成 _PIN["live"]（落档）
    python tests/_u1d2_store_gen.py --emit-aux     # 生成 _PIN["aux"]（存档面指纹）

E/C 分类（`FROZEN_GATE.md` §2.3）
--------------------------------
* **E**（预期不变）6 段：`_monster_display_name` · `get_instance_world` · `create_instance_world` ·
  `destroy_instance_world` · `update_instance_world` · `resolve_map_for`。
  `--emit-live` 断言 `frozen == live`（变了就是范围蔓延）。
* **C**（预期会变）17 段：其余 16 段 + 两份 `_json_ready`（**本批删除** ⇒ `live == "<deleted>"`）。
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
TEST_FILE = os.path.join(_HERE, "test_u1d2_store_frozen.py")

BEGIN = "# >>> _u1d2_store_gen (auto) >>>"
END = "# <<< _u1d2_store_gen (auto) <<<"

DELETED_SENTINEL = "<deleted>"

#: 23 段（文件 · 符号），**顺序即门禁内键序**（照 `FROZEN_GATE.md` §1.4）。
SEGMENTS = [
    ("content/persistence/battle_state.py", "_json_ready"),
    ("content/persistence/battle_state.py", "_monster_display_name"),
    ("content/persistence/battle_state.py", "save_battle"),
    ("content/persistence/battle_state.py", "get_battle"),
    ("content/persistence/battle_state.py", "get_battle_raw"),
    ("content/persistence/battle_state.py", "clear_battle"),
    ("content/persistence/stats.py", "init_stats"),
    ("content/persistence/stats.py", "bump_stats"),
    ("content/persistence/stats.py", "get_stats"),
    ("content/persistence/stats.py", "set_achievement"),
    ("content/persistence/stats.py", "get_achievements"),
    ("content/persistence/props_use.py", "get_props_use"),
    ("content/persistence/props_use.py", "mark_props_use"),
    ("content/persistence/props_use.py", "props_use_claim_atomic"),
    ("content/worlds.py", "get_instance_world"),
    ("content/worlds.py", "_restore_from_db"),
    ("content/worlds.py", "create_instance_world"),
    ("content/worlds.py", "destroy_instance_world"),
    ("content/worlds.py", "_json_ready"),
    ("content/worlds.py", "_persist"),
    ("content/worlds.py", "update_instance_world"),
    ("content/worlds.py", "cleanup_stale_instances"),
    ("content/worlds.py", "resolve_map_for"),
]

#: E / C 分类（§2.3）。见模块头注。
CLASS = {
    "content/persistence/battle_state.py::_json_ready": "C",
    "content/persistence/battle_state.py::_monster_display_name": "E",
    "content/persistence/battle_state.py::save_battle": "C",
    "content/persistence/battle_state.py::get_battle": "C",
    "content/persistence/battle_state.py::get_battle_raw": "C",
    "content/persistence/battle_state.py::clear_battle": "C",
    "content/persistence/stats.py::init_stats": "C",
    "content/persistence/stats.py::bump_stats": "C",
    "content/persistence/stats.py::get_stats": "C",
    "content/persistence/stats.py::set_achievement": "C",
    "content/persistence/stats.py::get_achievements": "C",
    "content/persistence/props_use.py::get_props_use": "C",
    "content/persistence/props_use.py::mark_props_use": "C",
    "content/persistence/props_use.py::props_use_claim_atomic": "C",
    "content/worlds.py::get_instance_world": "E",
    "content/worlds.py::_restore_from_db": "C",
    "content/worlds.py::create_instance_world": "E",
    "content/worlds.py::destroy_instance_world": "E",
    "content/worlds.py::_json_ready": "C",
    "content/worlds.py::_persist": "C",
    "content/worlds.py::update_instance_world": "E",
    "content/worlds.py::cleanup_stale_instances": "C",
    "content/worlds.py::resolve_map_for": "E",
}

#: `design/U1-D2_FROZEN_GATE.md` §1.4 那份 74 段基线里属于本门禁的 **23 条**（全 64 位）。
#: 生成器 `--check` 拿它交叉核对 —— 双向独立来源（设计稿 vs `base/pkg` 切片）必须一致。
_BASELINE_PINS = {
    # ── battle_state.py（6）──
    "content/persistence/battle_state.py::_json_ready":
        "31a957bcb740bb09128fd572c33250f4db96254e46664d233f5821f929c47635",
    "content/persistence/battle_state.py::_monster_display_name":
        "6dba7c5d03011e63b858b278069cd48d05b9de282819bbc5d7ae2119be7ebe58",
    "content/persistence/battle_state.py::save_battle":
        "c8c94d2ffb5f7301c00f79d21bcbea17fc2f62a86dd8ecd5098fc25e4f5a6321",
    "content/persistence/battle_state.py::get_battle":
        "f52c1f4e30a472f0788a2c88b1c9232f8a25c2f61cdefe594baf04a0a59075ea",
    "content/persistence/battle_state.py::get_battle_raw":
        "84e583dc300f423b7f01fd39b8019e8ac416acb4b11a4f9bb01b7422e5106507",
    "content/persistence/battle_state.py::clear_battle":
        "3fdf1ec108796178ff8638b0e42464e58e870c92ec8becb96005217ef1e35d36",
    # ── stats.py（5）──
    "content/persistence/stats.py::init_stats":
        "b07d28ba220580b604c6d0ddf85433e1dec319b2e2cebd7cefd374ec47e4097a",
    "content/persistence/stats.py::bump_stats":
        "d754b42ddf3f3bcaeb4a7b8e46e3f994cd6c7c3304252725bcc6b5d1943e68da",
    "content/persistence/stats.py::get_stats":
        "6ac5a074b670aac29414079351aa39efba13f5c2c34b245389b4a106d57d71b2",
    "content/persistence/stats.py::set_achievement":
        "cef8f7e2d063c8974153faf2caf49adc39ab45cd39228cf0c66ca268ee0ca305",
    "content/persistence/stats.py::get_achievements":
        "164a4d3d634e7665292c6d3abc8d125250f6a34be861e5cfe1b10dde819df37e",
    # ── props_use.py（3）──
    "content/persistence/props_use.py::get_props_use":
        "0b4f8d26e417d7183d61bc9eeca43935efb1feb354a1307ff1cb82979769d094",
    "content/persistence/props_use.py::mark_props_use":
        "8e22a4396794d4bd31175aa3ccccef7e951c5dde74ba0d013bd54db804c37b96",
    "content/persistence/props_use.py::props_use_claim_atomic":
        "f11659f1b54848c26bdcb5c3bc903f41c3eea6348695989e3b88124d80900291",
    # ── worlds.py（9）──
    "content/worlds.py::get_instance_world":
        "abfa3639859424ba87149776254ba7c6a24de34292aedd38c326c559bf0ec2cb",
    "content/worlds.py::_restore_from_db":
        "15e1133494870aa0d7e9bad89afd3090f1d0434116690e8012378aa343ed2cdc",
    "content/worlds.py::create_instance_world":
        "1085ebc18004e207fc9f9114bea6b1c82b67e08a23409d57b7c2084d7600195f",
    "content/worlds.py::destroy_instance_world":
        "b44b3d4db6cdde2427dd462b115d8fd7e64e0a2aa97353ee18d96633f84d133b",
    "content/worlds.py::_json_ready":
        "99b170e37596ba818cc21ef15a73759b5a1d803a6ac97c0a27182c2d77352fa7",
    "content/worlds.py::_persist":
        "f1b7da8e56bf5831b682f907a4126412bccdc33eeea6f8958d58b31c5623130c",
    "content/worlds.py::update_instance_world":
        "586e5b8580ea887a910e7c0a1be3448d0b07402b078cb9931cf2b809ec528cb4",
    "content/worlds.py::cleanup_stale_instances":
        "3f35723fbf693f4de9e52c6912f1876d8638b2ec3bf65192ed7211c74f0aba7f",
    "content/worlds.py::resolve_map_for":
        "ce72a0fa44a6f19877aedf95bee5131e8b66988571c7c5c9bb65ea0dea7dcad9",
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
    """改动前基线副本 —— ① `GWEN_U1D2_BASE_PKG` → ② `<lane>/base/pkg` → ③ `<pkg>/.u1d2_base/pkg`
    → ④ **git 历史回溯**（最近 20 个改动过被测文件的提交里找「23 段切片 sha256 全等设计 pin」的版本）。

    都失败 ⇒ `(None, "none")`，调用方**必须显式报错**（fail-closed，不静默降级）。
    """
    candidates = []
    env = os.environ.get("GWEN_U1D2_BASE_PKG")
    if env:
        candidates.append(("env", env))
    candidates.append(("lane", os.path.join(LANE_ROOT, "base", "pkg")))
    candidates.append(("repo", os.path.join(PKG_ROOT, ".u1d2_base", "pkg")))
    for tag, path in candidates:
        if os.path.isfile(os.path.join(path, "content", "persistence", "battle_state.py")):
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
            tmp = tempfile.mkdtemp(prefix="u1d2s_base_")
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
    """候选 base 的 23 段切片是否全等 `_BASELINE_PINS`。"""
    try:
        for relpath, symbol in SEGMENTS:
            want = _BASELINE_PINS.get(key_of(relpath, symbol))
            if want is None:
                return False
            got = sha256_text(slice_source(
                os.path.join(path, *relpath.split("/")), symbol))
            if got != want:
                return False
        return True
    except Exception:                                            # noqa: BLE001
        return False


def _no_base_msg() -> str:
    return ("❌ 找不到改动前基线（base/pkg）—— 生成器**拒绝执行**（fail-closed，不静默降级）。\n"
            "   解析顺序：GWEN_U1D2_BASE_PKG → <lane>/base/pkg → <pkg>/.u1d2_base/pkg → git 历史回溯\n"
            "   启用方式：GWEN_U1D2_BASE_PKG=<含 content/persistence/battle_state.py 的 pkg 目录>")


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
    os.environ.setdefault("GWEN_GAME_DB", os.path.join(lane, "out", "test_u1d2_L5.db"))
    os.environ.setdefault("GWEN_TEST_MODE", "1")
    os.environ.setdefault("PYTHONUTF8", "1")
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
    """活模块里的对象；被删符号（两份 `_json_ready`）→ `None`。"""
    _boot_work_pkg()
    mod = importlib.import_module(_modname_of(relpath))
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


# ══════════════════════════════════════════════════════════════ 自检
def self_check(*, with_live=True) -> list:
    lines = []
    frozen = frozen_slices()
    if len(frozen) != 23:
        raise SystemExit("自检②失败：切片数 = %d（期望 23）" % len(frozen))
    lines.append("  ① 段数 = %d（期望 23）" % len(frozen))

    for key, text in frozen.items():
        try:
            ast.parse(text)
        except SyntaxError as exc:
            raise SystemExit("自检②失败：%s 切片不能 ast.parse：%s" % (key, exc))
        n = text.count("def %s(" % key.split("::")[1])
        if n != 1:
            raise SystemExit("自检③失败：%s 里 `def %s(` 出现 %d 次（期望 1）"
                             % (key, key.split("::")[1], n))
    lines.append("  ② 23 段切片全部 ast.parse 可编译")

    # ③ 不出现下一段的首行（防切片越界吞掉后面的函数；只对同文件相邻段生效）
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

    # ④ 与设计稿 §1.4 的 74 段基线交叉核对（双向独立来源：设计稿 vs base/pkg 切片）
    if len(_BASELINE_PINS) != 23:
        raise SystemExit("自检④失败：内嵌基线 23 条，实际 %d 条" % len(_BASELINE_PINS))
    mismatch = [k for k, want in _BASELINE_PINS.items()
                if sha256_text(frozen.get(k, "")) != want]
    if mismatch:
        raise SystemExit("自检④失败：与 design/U1-D2_FROZEN_GATE.md §1.4 基线不一致：%s"
                         % ", ".join(mismatch))
    lines.append("  ④ 23 条冻结 sha256 == `FROZEN_GATE.md` §1.4 基线（全 64 位）")
    lines.append("  ⑤ 档位（机械判据）：甲 %d / 乙 %d / 丙 %d"
                 % (sum(1 for v in frozen.values() if tier_of(v) == "甲"),
                    sum(1 for v in frozen.values() if tier_of(v) == "乙"),
                    sum(1 for v in frozen.values() if tier_of(v) == "丙")))
    tiers = {tier_of(v) for v in frozen.values()}
    if tiers != {"甲"}:
        raise SystemExit("自检⑤失败：档位不是 甲 23 / 乙 0 / 丙 0：%s" % sorted(tiers))

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
           "# ⚠ 本块由 `tests/_u1d2_store_gen.py` 生成 —— 手工改动 = 门禁失去安全网。",
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
    print("【--emit-frozen】冻结 23 段（base/pkg）+ 红基线 live pin")
    frozen = frozen_slices()
    live = live_pins()
    # ★ 红基线自证：此刻活实现还没改 ⇒ 全 23 段「切片(base) == inspect.getsource(活)」必须逐字节相等
    import inspect
    bad = []
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        obj = live_object(relpath, symbol)
        if obj is None:
            bad.append(k + "（活实现缺失）")
            continue
        got = sha256_text(inspect.getsource(obj))
        if got != sha256_text(frozen[k]):
            bad.append(k)
    if bad:
        raise SystemExit("红基线自证失败：切片(base) ≠ inspect.getsource(活实现)：%s"
                         % ", ".join(bad))
    _emit("baseline", live=live)
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        print("  [%s/%s] %-58s frozen=%s live=%s"
              % (CLASS[k], tier_of(frozen[k]), k,
                 sha256_text(frozen[k])[:12], live[k][:12]))
    print("  （红基线自证：23/23 段 切片(base) == inspect.getsource(活实现)）")


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
        if cls == "E":
            ok, want = (l == f), "frozen == live"
        else:
            ok, want = (l != f), "frozen != live"
        if not ok:
            bad.append("%s（%s：%s；frozen=%s live=%s）" % (k, cls, want, f[:12], str(l)[:12]))
        print("  [%s/%s] %-58s %-8s frozen=%s live=%s"
              % (cls, tier_of(frozen[k]), k,
                 "CHANGED" if l != f else "same", f[:12], str(l)[:12]))
    if bad:
        raise SystemExit("E/C 分类断言失败（共 %d 条）：\n    %s" % (len(bad), "\n    ".join(bad)))
    _emit("landed", live=live)
    print("  E/C 分类断言全过 → phase=landed")


def _emit_aux() -> None:
    print("【--emit-aux】存档面指纹（跑活实现取产物）")
    _boot_work_pkg()
    spec = importlib.util.spec_from_file_location("_u1d2_store_gate", TEST_FILE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    aux = gate._aux_fingerprints()
    cur = _current_pin()
    phase = cur.get("phase")
    _emit(phase if phase in ("baseline", "landed") else "baseline", aux=aux)
    for k in sorted(aux):
        print("  %-26s %s" % (k, str(aux[k])[:72]))


BASE_PKG, BASE_SOURCE = _resolve_base_pkg()      # ★ 必须在 slice_source / SEGMENTS 之后


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="U1-D2 门禁② 生成器（存档块 L5）")
    ap.add_argument("--check", action="store_true", help="只自检，不改文件")
    ap.add_argument("--no-live", action="store_true", help="自检跳过「活实现」那一条")
    ap.add_argument("--emit-frozen", action="store_true", help="生成 _FROZEN_TEXT + _PIN（红基线）")
    ap.add_argument("--emit-live", action="store_true", help="重生成 _PIN['live']（落档）")
    ap.add_argument("--emit-aux", action="store_true", help="生成 _PIN['aux']")
    args = ap.parse_args(argv)
    if not (args.check or args.emit_frozen or args.emit_live or args.emit_aux):
        ap.print_help()
        return 2
    print("== U1-D2 门禁② 生成器（存档块 L5）==")
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
