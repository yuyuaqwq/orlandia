# -*- coding: utf-8 -*-
"""U1-D2 门禁③ 生成器（触发器主四件）—— 12 段冻结文本 / 双 sha256 / aux 指纹。

口径（照 `design/U1-D2_FROZEN_GATE.md` §1.2 · §2.2 · §2.3 · §5.3）
-----------------------------------------------------------------
* **冻结侧读 `base/pkg/**`**（= 改动前基线；本工作区 `base/pkg == work/pkg`，开工时冻结），
  用 `ast` 逐行切片出旧实现文本；切片口径 = `min(装饰器行, def 行)` 起、`node.end_lineno` 止、
  **保留原行尾** ⇒ 与 `inspect.getsource(<活实现>)` 逐字节相等
  （`--emit-frozen` 时对**全部 12 段**当面证明，不只 E 栏）。
* 生成器输出**只写进** `tests/test_u1d2_triggers_frozen.py` 的两行标记之间；
  标记之外的正文（比对逻辑）**一个字节都不碰**。
* 12 段 = 4 文件（`equip.py` 5 · `food_proc.py` 4 · `team_procs.py` 1 · `worldboss.py` 2）。

档位（机械判据，`FROZEN_GATE.md` §1.3）：`丙` ⟺ `async def`；否则 `乙` ⟺ 段内出现 `self.`；
否则 `甲`。本门禁 = **甲 12 / 乙 0 / 丙 0**（与 `FROZEN_GATE.md` §0 一致）。

⚠️ **不跑任何 `git` 写命令**（作业书 §5 禁令 1）：base 解析失败即 fail-closed 报错。

四档命令
--------
    python tests/_u1d2_triggers_gen.py --check        # 只自检（§1.2 三条），不改文件
    python tests/_u1d2_triggers_gen.py --emit-frozen  # 生成 _FROZEN_TEXT + _PIN（红基线档）
    python tests/_u1d2_triggers_gen.py --emit-live    # 实现改完后重生成 _PIN["live"]（落档）
    python tests/_u1d2_triggers_gen.py --emit-aux     # 只重生成 _PIN["aux"]

E/C 分类（§2.3）
----------------
* **E**（预期不变，6 段）：`equip._known_engine_events` · `equip.map_event` ·
  `food_proc._map_event` · `food_proc.food_trigger_decls` · `food_proc.food_period_decl` ·
  `worldboss.wb_gm_dmg_mult`
* **C**（预期会变，6 段）：`equip.weapon_triggers` · `equip.affix_triggers` ·
  `equip.apply_to_actor` · `food_proc.install_food_fx` · `team_procs._mount` ·
  `worldboss.apply_gm_dmg_mult`

⚠ `--emit-frozen` 只在红基线之前跑一次；`--emit-live` 生成后 `phase` 变 `landed`
（门禁据此启用 C 栏不等式断言）。
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
TEST_FILE = os.path.join(_HERE, "test_u1d2_triggers_frozen.py")

BEGIN = "# >>> _u1d2_triggers_gen (auto) >>>"
END = "# <<< _u1d2_triggers_gen (auto) <<<"

#: 12 段（文件 · 符号），**顺序即门禁内键序**。
SEGMENTS = [
    ("content/mech/equip.py", "_known_engine_events"),
    ("content/mech/equip.py", "map_event"),
    ("content/mech/equip.py", "weapon_triggers"),
    ("content/mech/equip.py", "affix_triggers"),
    ("content/mech/equip.py", "apply_to_actor"),
    ("content/mech/food_proc.py", "_map_event"),
    ("content/mech/food_proc.py", "food_trigger_decls"),
    ("content/mech/food_proc.py", "food_period_decl"),
    ("content/mech/food_proc.py", "install_food_fx"),
    ("content/mech/team_procs.py", "_mount"),
    ("content/mech/worldboss.py", "wb_gm_dmg_mult"),
    ("content/mech/worldboss.py", "apply_gm_dmg_mult"),
]

#: E / C 分类（§2.3）。
CLASS = {
    "content/mech/equip.py::_known_engine_events": "E",
    "content/mech/equip.py::map_event": "E",
    "content/mech/equip.py::weapon_triggers": "C",
    "content/mech/equip.py::affix_triggers": "C",
    "content/mech/equip.py::apply_to_actor": "C",
    "content/mech/food_proc.py::_map_event": "E",
    "content/mech/food_proc.py::food_trigger_decls": "E",
    "content/mech/food_proc.py::food_period_decl": "E",
    "content/mech/food_proc.py::install_food_fx": "C",
    "content/mech/team_procs.py::_mount": "C",
    "content/mech/worldboss.py::wb_gm_dmg_mult": "E",
    "content/mech/worldboss.py::apply_gm_dmg_mult": "C",
}

#: `design/U1-D2_FROZEN_GATE.md` §1.4 那份 74 段基线里属于本门禁的 **12 条**（全 64 位）。
#: 生成器 `--check` 拿它交叉核对 —— 双向独立来源（设计稿 vs `base/pkg` 切片）必须一致。
_BASELINE_PINS = {
    "content/mech/equip.py::_known_engine_events":
        "cd81e2e7c9da6719d0f609a5afb6b5e3025afb90e6296abf96ff837edfbbfbbf",   # 134-140  273 字符
    "content/mech/equip.py::map_event":
        "2bde3f8d58ec59f0075506e4cb387445c10594aaf0ac546e823364ea700bb2c8",   # 144-160  686 字符
    "content/mech/equip.py::weapon_triggers":
        "ff7199dca0852eff5d6a846da8807b8b6724b6b24c95cdb955d1e7e4ba3b6b2b",   # 1423-1437 551 字符
    "content/mech/equip.py::affix_triggers":
        "477930b46af4857910759c2bb0168cf4a0b830083800bc45dc5cf25c8140f2cf",   # 1440-1461 951 字符
    "content/mech/equip.py::apply_to_actor":
        "6d28f9d030d7acd4f0277e11b2e1d466cb6e4d3daa072b1946e15b35cc64d97f",   # 1464-1511 1938 字符
    "content/mech/food_proc.py::_map_event":
        "f4c9be4e258dfc2acd9957c3dafb9a1c27d50229674bc443ffc612bb8f706fa5",   # 84-86    130 字符
    "content/mech/food_proc.py::food_trigger_decls":
        "56e1e0d9f5da1fd66a7bc1bbfadff81e928f85153ac083a5ec95a7db26067a28",   # 98-197   5596 字符
    "content/mech/food_proc.py::food_period_decl":
        "d56fa0cee9d05f18bce4e5bb3effda8deea313777c4ff30dedd2c2ce38e23a2e",   # 208-220  500 字符
    "content/mech/food_proc.py::install_food_fx":
        "1f921216fc6943f0673934d043d2488577afecd84fbea0494c5736ba98ccc0b7",   # 227-262  1628 字符
    "content/mech/team_procs.py::_mount":
        "8e839245bc7f5329cc1aeb6ea58ac4602b07e2eb866b84c370dbe48ef1eee641",   # 140-148  376 字符
    "content/mech/worldboss.py::wb_gm_dmg_mult":
        "f8b2e9c6d2aed67b061c5c38db3fb01ec763e7f9ddf79f02b9e5550b71a5a470",   # 26-42    520 字符
    "content/mech/worldboss.py::apply_gm_dmg_mult":
        "4e196fccd0836f0a30c02dcf01a0be16963ee4c24e508a784a0f2cc7f408e8d1",   # 45-69    801 字符
}

#: 4 张数据表（判据 9：数据面零改动）+ 装配契约（判据 10：六步顺序/保险丝未变）
DATA_RELS = (
    "content/mech/we_data.py",
    "content/data/affixes.json",
    "content/data/legendary_effects.json",
    "content/data/food_effects.json",
)
CONTRACT_RELS = ("content/apply.py",)

#: 引擎侧（本线**引擎零改动**；判据 9/10 的交叉证据）
ENG_RELS = (
    "extends/ext_combat/battle/effect_triggers.py",
    "extends/ext_combat/battle/declarations.py",
)

#: 判据 9 的只读面 = 4 个源文件 + 4 张数据表
SRC_RELS = ("content/mech/equip.py", "content/mech/food_proc.py",
            "content/mech/team_procs.py", "content/mech/worldboss.py")


# ══════════════════════════════════════════════════════════════ 切片口径（§1.2）
def slice_source(path: str, symbol: str) -> str:
    """从 `path` 里切出 `symbol` 的**整段源码文本**（含装饰器，保留原行尾）。

    与 `inspect.getsource` 逐字节一致（生成时对全部 12 段当面证明）。
    """
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


def sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def tier_of(text: str) -> str:
    """机械档位（§1.3）：`async def` → 丙；含 `self.` → 乙；否则 甲。"""
    if "async def " in text:
        return "丙"
    if "self." in text:
        return "乙"
    return "甲"


# ─────────────────────────────────────────────────── base 解析（四级；找不到 fail-closed）
def _resolve_base_pkg():
    """改动前基线副本 —— ① `GWEN_U1D2_BASE_PKG` → ② `<lane>/base/pkg` → ③ `<pkg>/.u1d2_base/pkg`
    → ④ **git 历史回溯**（最近 20 个改动过被测文件的提交里找「12 段切片 sha256 全等设计 pin」的版本）。

    都失败 ⇒ `(None, "none")`，调用方**必须显式报错**（fail-closed，不静默降级）。
    """
    candidates = []
    env = os.environ.get("GWEN_U1D2_BASE_PKG")
    if env:
        candidates.append(("env", env))
    candidates.append(("lane", os.path.join(LANE_ROOT, "base", "pkg")))
    candidates.append(("repo", os.path.join(PKG_ROOT, ".u1d2_base", "pkg")))
    for tag, path in candidates:
        if os.path.isfile(os.path.join(path, "content", "mech", "worldboss.py")):
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
            tmp = tempfile.mkdtemp(prefix="u1d2t_base_")
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
    """候选 base 的 12 段切片是否全等 `_BASELINE_PINS`。"""
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
            "   解析顺序：GWEN_U1D2_BASE_PKG → <lane>/base/pkg → <pkg>/.u1d2_base/pkg → git 历史回溯\n"
            "   启用方式：GWEN_U1D2_BASE_PKG=<含 content/mech/worldboss.py 的 pkg 目录>")


def frozen_slices() -> dict:
    if BASE_PKG is None:
        raise SystemExit(_no_base_msg())
    out = {}
    for relpath, symbol in SEGMENTS:
        out[key_of(relpath, symbol)] = slice_source(
            os.path.join(BASE_PKG, *relpath.split("/")), symbol)
    return out


# ══════════════════════════════════════════════════════════════ aux 指纹
def aux_pins() -> dict:
    """数据面 / 装配契约 / 引擎侧指纹 —— **读 base**（改动前基线）产出期望值。"""
    base_pkg = BASE_PKG
    base_eng = os.path.join(os.path.dirname(base_pkg), "eng") if base_pkg else None
    out = {}
    for rel in DATA_RELS:
        out["data:" + rel] = sha256_file(os.path.join(base_pkg, *rel.split("/")))
    for rel in CONTRACT_RELS:
        out["contract:" + rel] = sha256_file(os.path.join(base_pkg, *rel.split("/")))
    for rel in SRC_RELS:
        out["src_base:" + rel] = sha256_file(os.path.join(base_pkg, *rel.split("/")))
    for rel in ENG_RELS:
        p = os.path.join(base_eng, *rel.split("/"))
        out["engine:" + rel] = sha256_file(p) if os.path.isfile(p) else "<missing>"
    return out


# ══════════════════════════════════════════════════════════════ 活侧取件
def _boot_work_pkg():
    """把 `work/pkg`（+ tests + shim + 引擎根 + 宿主壳根）摆进 `sys.path` 并兜底沙箱环境变量。"""
    lane = LANE_ROOT
    os.environ.setdefault("GWEN_FRAMEWORK_DIR", os.path.join(lane, "work", "eng"))
    os.environ.setdefault("GWEN_HOST_DIR", os.path.join(lane, "work", "host"))
    os.environ.setdefault("GWEN_GAME_DB", os.path.join(lane, "out", "test_u1d2_L6.db"))
    os.environ.setdefault("GWEN_TEST_MODE", "1")
    os.environ.setdefault("PYTHONUTF8", "1")
    shim = os.path.join(_HERE, "shim_astrbot")
    for p in (shim, _HERE, PKG_ROOT,
              os.environ["GWEN_FRAMEWORK_DIR"], os.environ["GWEN_HOST_DIR"]):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    import _paths                                                        # noqa: F401


def _modname_of(relpath: str) -> str:
    return "content." + relpath.split("/", 1)[1][:-3].replace("/", ".")


def live_object(relpath: str, symbol: str):
    """活模块里的对象（本门禁 12 段全是模块级函数 → 直取）。"""
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
    if len(frozen) != 12:
        raise SystemExit("自检①失败：切片数 = %d（期望 12）" % len(frozen))
    lines.append("  ① 段数 = %d（期望 12）" % len(frozen))

    for key, text in frozen.items():
        try:
            ast.parse(text)
        except SyntaxError as exc:
            raise SystemExit("自检②失败：%s 切片不能 ast.parse：%s" % (key, exc))
        n = text.count("def %s(" % key.split("::")[1])
        if n != 1:
            raise SystemExit("自检②失败：%s 里 `def %s(` 出现 %d 次（期望 1）"
                             % (key, key.split("::")[1], n))
    lines.append("  ② 12 段切片全部 ast.parse 可编译")

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

    if len(_BASELINE_PINS) != 12:
        raise SystemExit("自检④失败：内嵌基线 12 条，实际 %d 条" % len(_BASELINE_PINS))
    mismatch = [k for k, want in _BASELINE_PINS.items()
                if sha256_text(frozen.get(k, "")) != want]
    if mismatch:
        raise SystemExit("自检④失败：与 design/U1-D2_FROZEN_GATE.md §1.4 基线不一致：%s"
                         % ", ".join(mismatch))
    lines.append("  ④ 12 条冻结 sha256 == `FROZEN_GATE.md` §1.4 基线（全 64 位）")
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
           "# ⚠ 本块由 `tests/_u1d2_triggers_gen.py` 生成 —— 手工改动 = 门禁失去安全网。",
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
    print("【--emit-frozen】冻结 12 段（base/pkg）+ 红基线 live pin + aux 指纹")
    frozen = frozen_slices()
    live = live_pins()
    import inspect
    bad = []
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        obj = live_object(relpath, symbol)
        got = sha256_text(inspect.getsource(obj))
        if got != sha256_text(frozen[k]):
            bad.append(k)
    if bad:
        raise SystemExit("红基线自证失败：切片(base) ≠ inspect.getsource(活实现)：%s"
                         % ", ".join(bad))
    _emit("baseline", live=live, aux=aux_pins())
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        print("  [%s/%s] %-52s frozen=%s live=%s"
              % (CLASS[k], tier_of(frozen[k]), k, sha256_text(frozen[k])[:12], live[k][:12]))
    print("  （红基线自证：12/12 段 切片(base) == inspect.getsource(活实现)）")


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
        print("  [%s/%s] %-52s %-8s frozen=%s live=%s"
              % (cls, tier_of(frozen[k]), k, "CHANGED" if changed else "same", f[:12], str(l)[:12]))
    if bad:
        raise SystemExit("E/C 分类断言失败（共 %d 条）：\n    %s" % (len(bad), "\n    ".join(bad)))
    _emit("landed", live=live)
    print("  E/C 分类断言全过 → phase=landed")


def _emit_aux() -> None:
    print("【--emit-aux】重生成 _PIN[\"aux\"]（读 base/pkg + base/eng）")
    aux = aux_pins()
    cur = _current_pin()
    phase = cur.get("phase")
    _emit(phase if phase in ("baseline", "landed") else "baseline", aux=aux)
    for k in sorted(aux):
        print("  %-42s %s" % (k, str(aux[k])[:64]))


BASE_PKG, BASE_SOURCE = _resolve_base_pkg()      # ★ 必须在 slice_source / SEGMENTS 之后


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="U1-D2 门禁③ 生成器（触发器主四件）")
    ap.add_argument("--check", action="store_true", help="只自检（§1.2 四条），不改文件")
    ap.add_argument("--no-live", action="store_true", help="自检跳过「活实现」那一条")
    ap.add_argument("--emit-frozen", action="store_true", help="生成 _FROZEN_TEXT + _PIN（红基线）")
    ap.add_argument("--emit-live", action="store_true", help="重生成 _PIN['live']（落档）")
    ap.add_argument("--emit-aux", action="store_true", help="重生成 _PIN['aux']")
    args = ap.parse_args(argv)
    if not (args.check or args.emit_frozen or args.emit_live or args.emit_aux):
        ap.print_help()
        return 2
    print("== U1-D2 门禁③ 生成器（触发器主四件：equip/food_proc/team_procs/worldboss）==")
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
