# -*- coding: utf-8 -*-
"""U1-I4 门禁④ 生成器（外围装配）—— 9 段冻结文本 / 双 sha256 / aux 指纹。

口径（照 `design/U1-I4_FROZEN_GATE.md` §1.2 · §2.2 · §2.3）
--------------------------------------------------------
* **冻结侧读 `base/pkg/**`**（= 改动前基线，本工作区 `base/pkg` = L3/L4 落地之后、
  L6 之前），用 `ast` 逐行切片出旧实现文本；切片口径 = `min(装饰器行, def 行)` 起、
  `node.end_lineno` 止、**保留原行尾** ⇒ 与 `inspect.getsource(<活实现>)` 逐字节相等
  （`--emit-frozen` 时对**全部 9 段**当面证明，不只 E 栏）。
* 生成器输出**只写进** `tests/test_u1i4_wiring_outer_frozen.py` 的两行标记之间；
  标记之外的正文（比对逻辑）**一个字节都不碰**。
* 9 段 = 外围 8 文件（`cmds_base_rules` 1 · `instance_cmds` 1 · `shop` 1 · `cmds_world` 1 ·
  `economy_cmds` 2 · `talk_actions` 1 · `item_templates` 1 · `combat_cmds` 1）。
  `item_templates` / `combat_cmds` **只钉不改**（E 栏）。

档位（机械判据，`FROZEN_GATE.md` §1.3）：`丙` ⟺ `async def`；否则 `乙` ⟺ 段内出现 `self.`；
否则 `甲`。本门禁 = **甲 6 / 乙 1 / 丙 2**（与 `FROZEN_GATE.md` §0 一致）。

⚠️ **不跑任何 `git` 命令**（作业书 §5 禁令 1）：base 解析失败即 fail-closed 报 BLOCKED 式错误。

四档命令
--------
    python tests/_u1i4_wiring_outer_gen.py --check        # 只自检（§1.2 三条），不改文件
    python tests/_u1i4_wiring_outer_gen.py --emit-frozen  # 生成 _FROZEN_TEXT + _PIN（红基线档）
    python tests/_u1i4_wiring_outer_gen.py --emit-live    # 实现改完后重生成 _PIN["live"]（落档）
    python tests/_u1i4_wiring_outer_gen.py --emit-aux     # 生成 _PIN["aux"]（存档面指纹 + 丙类 golden）

E/C 分类（§2.3）
----------------
* **E**（预期不变）：本批**不该动**的段 —— `--emit-live` 时断言 `frozen == live`。
  本门禁 3 段：`talk_actions.action_apprentice_check`（**可选线，本批不做**，理由见
  `out/U1-I11_DESIGN.md` §4）· `item_templates.tpl_teleport_portal` · `combat_cmds.roll_wild_encounter`。
* **C**（预期会变）：6 段 —— `cmds_base_rules.wild_trader_here` · `instance_cmds._stage_npcs` ·
  `shop.apprentice_protect_mats` · `cmds_world.quest_view` · `economy_cmds.shop` · `economy_cmds.buy`。

⚠ `--emit-frozen` 只在红基线之前跑一次；`--emit-live` 生成后 `phase` 变 `landed`
（门禁据此启用 C 栏不等式断言）。
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
TEST_FILE = os.path.join(_HERE, "test_u1i4_wiring_outer_frozen.py")

BEGIN = "# >>> _u1i4_outer_gen (auto) >>>"
END = "# <<< _u1i4_outer_gen (auto) <<<"

#: 9 段（文件 · 符号），**顺序即门禁内键序**。本批 = 外围 8 文件。
SEGMENTS = [
    ("content/cmds_base_rules.py", "wild_trader_here"),
    ("content/instance_cmds.py", "_stage_npcs"),
    ("content/shop.py", "apprentice_protect_mats"),
    ("content/cmds_world.py", "quest_view"),
    ("content/economy_cmds.py", "shop"),
    ("content/economy_cmds.py", "buy"),
    ("content/talk_actions.py", "action_apprentice_check"),
    ("content/item_templates.py", "tpl_teleport_portal"),
    ("content/combat_cmds.py", "roll_wild_encounter"),
]

#: E / C 分类（§2.3）。见模块头注。
CLASS = {
    "content/cmds_base_rules.py::wild_trader_here": "C",
    "content/instance_cmds.py::_stage_npcs": "C",
    "content/shop.py::apprentice_protect_mats": "C",
    "content/cmds_world.py::quest_view": "C",
    "content/economy_cmds.py::shop": "C",
    "content/economy_cmds.py::buy": "C",
    "content/talk_actions.py::action_apprentice_check": "E",
    # ↓ 2026-09-18 由 E 改判 C：C 档 15（B-2 第 6 片）把本段的展示句壳迁进文案表（`ItemResult(text=…)`
    #   改 `_T.text/_T.static`）——源码逐字变了，故不再与冻结基线相等（行为不变：输出文本逐字一致，
    #   由经济域/文案表门禁守）。
    "content/item_templates.py::tpl_teleport_portal": "C",
    "content/combat_cmds.py::roll_wild_encounter": "E",
}

#: `design/U1-I4_FROZEN_GATE.md` §1.4 那份 93 段基线里属于本门禁的 **9 条**（全 64 位）。
#: 生成器 `--check` 拿它交叉核对 —— 双向独立来源（设计稿 vs `base/pkg` 切片）必须一致。
_BASELINE_PINS = {
    "content/cmds_base_rules.py::wild_trader_here":
        "cf749f93dba39692b80e519c207e424c855e72a6fd7ac3a4bdbd375d1b293f65",
    "content/instance_cmds.py::_stage_npcs":
        "9fb5d4685298dc82b8c314ade09dda2e3ebc0bd43019f0bc3dde2ff0255451ef",
    "content/shop.py::apprentice_protect_mats":
        "09bedd406ae58502c0d8d10bbfbe9ff54a93ccb9d5356ef5d1b42b54f9703370",
    "content/cmds_world.py::quest_view":
        "bcccf11297a8ae87c51fbb8d14c851c833510ecf30a0888d95a23faf208e1d21",
    "content/economy_cmds.py::shop":
        "c381329ddf1bd4b1865194b0f7a4dd37b8fa7e28db24d407fc96a6a992ba8638",
    "content/economy_cmds.py::buy":
        "76e2b9307e4579d659485c66837430a817b2af8280c2580a4f0a4f3cc6581690",
    "content/talk_actions.py::action_apprentice_check":
        "3079da595d629cb8a83530cbfdaf221a85ee971804ae29895c47577748585edc",
    "content/item_templates.py::tpl_teleport_portal":
        "f833ca2a3eebd4c0fb13e365a049d0b3f484e906bb80f63c4481e15201cc2bd2",
    "content/combat_cmds.py::roll_wild_encounter":
        "2c66022b9137474a748b8bfb1135c88e09e7fa6cbcab9214016e95ae786709a1",
}


# ══════════════════════════════════════════════════════════════ 切片口径（§1.2）
def slice_source(path: str, symbol: str) -> str:
    """从 `path` 里切出 `symbol` 的**整段源码文本**（含装饰器，保留原行尾）。

    支持模块级函数**与类方法**（本门禁有 3 段是类方法：`_stage_npcs` / `shop` / `buy`）。
    与 `inspect.getsource` 逐字节一致（生成时对全部 9 段当面证明）。
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


def tier_of(text: str) -> str:
    """机械档位（§1.3）：`async def` → 丙；含 `self.` → 乙；否则 甲。"""
    if "async def " in text:
        return "丙"
    if "self." in text:
        return "乙"
    return "甲"


# ─────────────────────────────────────────────────── base 解析（四级；找不到 fail-closed）
def _resolve_base_pkg():
    """改动前基线副本 —— ① `GWEN_U1I4_BASE_PKG` → ② `<lane>/base/pkg` → ③ `<pkg>/.u1i4_base/pkg`
    → ④ **git 历史回溯**（最近 20 个改动过被测文件的提交里找「9 段切片 sha256 全等设计 pin」的版本）。

    都失败 ⇒ `(None, "none")`，调用方**必须显式报错**（fail-closed，不静默降级）。
    """
    candidates = []
    env = os.environ.get("GWEN_U1I4_BASE_PKG")
    if env:
        candidates.append(("env", env))
    candidates.append(("lane", os.path.join(LANE_ROOT, "base", "pkg")))
    candidates.append(("repo", os.path.join(PKG_ROOT, ".u1i4_base", "pkg")))
    for tag, path in candidates:
        if os.path.isfile(os.path.join(path, "content", "shop.py")):
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
            tmp = tempfile.mkdtemp(prefix="u1i4o_base_")
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
            "   解析顺序：GWEN_U1I4_BASE_PKG → <lane>/base/pkg → <pkg>/.u1i4_base/pkg → git 历史回溯\n"
            "   启用方式：GWEN_U1I4_BASE_PKG=<含 content/shop.py 的 pkg 目录>")


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
    os.environ.setdefault("GWEN_GAME_DB", os.path.join(lane, "out", "test_u1i4_outer.db"))
    os.environ.setdefault("GWEN_TEST_MODE", "1")
    os.environ.setdefault("PYTHONUTF8", "1")
    shim = os.path.join(_HERE, "shim_astrbot")
    for p in (shim, _HERE, PKG_ROOT,
              os.environ["GWEN_FRAMEWORK_DIR"], os.environ["GWEN_HOST_DIR"]):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    # ★ 走仓库既有测试通道完成宿主绑定（否则 `content.economy_cmds` 等会因取件面缺失拒绝 import）
    import _paths                                                        # noqa: F401
    import _engine_harness                                               # noqa: F401


def _modname_of(relpath: str) -> str:
    return "content." + relpath.split("/", 1)[1][:-3].replace("/", ".")


def live_object(relpath: str, symbol: str):
    """活模块里的对象：模块级函数 → 直取；类方法（`_stage_npcs` / `shop` / `buy`）→ 扫类体。"""
    _boot_work_pkg()
    mod = importlib.import_module(_modname_of(relpath))
    obj = getattr(mod, symbol, None)
    if obj is not None:
        return obj
    for _name, val in list(vars(mod).items()):
        if isinstance(val, type) and symbol in vars(val):
            return vars(val)[symbol]
    return None


def live_pins() -> dict:
    import inspect
    out = {}
    for relpath, symbol in SEGMENTS:
        obj = live_object(relpath, symbol)
        out[key_of(relpath, symbol)] = (
            None if obj is None else sha256_text(inspect.getsource(obj)))
    return out


# ══════════════════════════════════════════════════════════════ 自检（§1.2 三条）
def self_check(*, with_live=True) -> list:
    lines = []
    frozen = frozen_slices()
    if len(frozen) != 9:
        raise SystemExit("自检②失败：切片数 = %d（期望 9）" % len(frozen))
    lines.append("  ① 段数 = %d（期望 9）" % len(frozen))

    for key, text in frozen.items():
        try:
            # 类方法切片带 4 空格缩进 ⇒ 解析前套一个空类壳（**不能 dedent**：`buy` 体内
            # 有一行列 0 的注释，dedent 会因公共前缀为空而失效；注释缩进对 tokenizer 无意义）
            ast.parse(text if not text[:1].isspace() else "class _FrozenNS:\n" + text)
        except SyntaxError as exc:
            raise SystemExit("自检②失败：%s 切片不能 ast.parse：%s" % (key, exc))
        n = text.count("def %s(" % key.split("::")[1])
        if n != 1:
            raise SystemExit("自检③失败：%s 里 `def %s(` 出现 %d 次（期望 1）"
                             % (key, key.split("::")[1], n))
    lines.append("  ② 9 段切片全部 ast.parse 可编译")

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

    # ④ 与设计稿 §1.4 的 93 段基线交叉核对（双向独立来源：设计稿 vs base/pkg 切片）
    if len(_BASELINE_PINS) != 9:
        raise SystemExit("自检④失败：内嵌基线 9 条，实际 %d 条" % len(_BASELINE_PINS))
    mismatch = [k for k, want in _BASELINE_PINS.items()
                if sha256_text(frozen.get(k, "")) != want]
    if mismatch:
        raise SystemExit("自检④失败：与 design/U1-I4_FROZEN_GATE.md §1.4 基线不一致：%s"
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
           "# ⚠ 本块由 `tests/_u1i4_wiring_outer_gen.py` 生成 —— 手工改动 = 门禁失去安全网。",
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
    print("【--emit-frozen】冻结 9 段（base/pkg）+ 红基线 live pin")
    frozen = frozen_slices()
    live = live_pins()
    # ★ 红基线自证：此刻活实现还没改 ⇒ 全 9 段「切片(base) == inspect.getsource(活)」必须逐字节相等
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
    _emit("baseline", live=live)
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        print("  [%s/%s] %-52s frozen=%s live=%s"
              % (CLASS[k], tier_of(frozen[k]), k, sha256_text(frozen[k])[:12], live[k][:12]))
    print("  （红基线自证：9/9 段 切片(base) == inspect.getsource(活实现)）")


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
    print("【--emit-aux】存档面指纹 + 丙类 golden（跑活实现取产物）")
    _boot_work_pkg()
    spec = importlib.util.spec_from_file_location("_u1i4_outer_gate", TEST_FILE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    aux = gate._aux_fingerprints()
    cur = _current_pin()
    phase = cur.get("phase")
    _emit(phase if phase in ("baseline", "landed") else "baseline", aux=aux)
    for k in sorted(aux):
        print("  %-22s %s" % (k, str(aux[k])[:72]))


BASE_PKG, BASE_SOURCE = _resolve_base_pkg()      # ★ 必须在 slice_source / SEGMENTS 之后


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="U1-I4 门禁④ 生成器（外围装配）")
    ap.add_argument("--check", action="store_true", help="只自检（§1.2 三条），不改文件")
    ap.add_argument("--no-live", action="store_true", help="自检跳过「活实现」那一条")
    ap.add_argument("--emit-frozen", action="store_true", help="生成 _FROZEN_TEXT + _PIN（红基线）")
    ap.add_argument("--emit-live", action="store_true", help="重生成 _PIN['live']（落档）")
    ap.add_argument("--emit-aux", action="store_true", help="生成 _PIN['aux']")
    args = ap.parse_args(argv)
    if not (args.check or args.emit_frozen or args.emit_live or args.emit_aux):
        ap.print_help()
        return 2
    print("== U1-I4 门禁④ 生成器（外围装配）==")
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
