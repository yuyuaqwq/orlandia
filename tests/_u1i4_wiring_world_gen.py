# -*- coding: utf-8 -*-
"""U1-I4 门禁③ 生成器（世界侧装配）—— 29 段冻结文本 / 双 sha256 / aux 指纹。

口径（照 `design/U1-I4_FROZEN_GATE.md` §1.2 · §2.2 · §2.3）
--------------------------------------------------------
* **冻结侧读 `base/pkg/**`**（= 改动前基线，取自 L3/L4 落地之后），用 `ast` 逐行切片出旧实现文本；
  切片口径 = `min(装饰器行, def 行)` 起、`node.end_lineno` 止，**保留原行尾** ⇒ 与
  `inspect.getsource(<活实现>)` 逐字节相等（生成器自检①当面证明）。
* 生成器输出**只写进** `tests/test_u1i4_wiring_world_frozen.py` 的两行标记之间；
  标记之外的正文（比对逻辑）**一个字节都不碰**。
* 29 段全在 `content/world_cmds.py`（本线独占文件面）。

四档命令
--------
    python tests/_u1i4_wiring_world_gen.py --check        # 只自检（§1.2 三条），不改文件
    python tests/_u1i4_wiring_world_gen.py --emit-frozen  # 生成 _FROZEN_TEXT + _PIN（红基线档）
    python tests/_u1i4_wiring_world_gen.py --emit-live    # 实现改完后重生成 _PIN["live"]（落档）
    python tests/_u1i4_wiring_world_gen.py --emit-aux     # 生成 _PIN["aux"]（数据面 + 丙类 golden）

E/C 分类（§2.3）
----------------
* **E**（预期不变）：本批不该动的段 —— `--emit-live` 时**断言 `frozen == live`**。
* **C**（预期会变）：本批会改的段 —— 断言 `frozen != live`（**没变说明没真接上**）。

⚠ `--emit-frozen` 只允许在「红基线」之前跑一次；`--emit-aux` 的**丙类 golden 必须在改实现之前**
抓（否则它只是新实现的快照）；`--emit-live` 生成后 `phase` 变 `landed`。
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
TEST_FILE = os.path.join(_HERE, "test_u1i4_wiring_world_frozen.py")

BEGIN = "# >>> _u1i4_gen (auto) >>>"
END = "# <<< _u1i4_gen (auto) <<<"

#: 29 段（文件 · 符号），**顺序即门禁内键序**（照 `FROZEN_GATE.md` §1.4 的 world_cmds 段序）。
SEGMENTS = [
    ("content/world_cmds.py", "_npc_dialogue"),
    ("content/world_cmds.py", "_current_npcs"),
    ("content/world_cmds.py", "_present_wild_hints"),
    ("content/world_cmds.py", "_start_talk_list"),
    ("content/world_cmds.py", "_find_npc_in_map"),
    ("content/world_cmds.py", "_town_npc_absent_hint"),
    ("content/world_cmds.py", "_player_map_name"),
    ("content/world_cmds.py", "_subarea_name"),
    ("content/world_cmds.py", "_find_wild_npc"),
    ("content/world_cmds.py", "_wild_unseen_hint"),
    ("content/world_cmds.py", "_npc_direction_hint"),
    ("content/world_cmds.py", "_wild_cond_label"),
    ("content/world_cmds.py", "_talk_active"),
    ("content/world_cmds.py", "_talk_ctx"),
    ("content/world_cmds.py", "_side_menu_expand"),
    ("content/world_cmds.py", "_render_talk_node"),
    ("content/world_cmds.py", "_apply_talk_action_async"),
    ("content/world_cmds.py", "_apply_talk_action"),
    ("content/world_cmds.py", "talk_choice"),
    ("content/world_cmds.py", "npc_quick_dialog"),
    ("content/world_cmds.py", "find_npc"),
    ("content/world_cmds.py", "move"),
    ("content/world_cmds.py", "time_cmd"),
    ("content/world_cmds.py", "wild_notes"),
    ("content/world_cmds.py", "turn_in"),
    ("content/world_cmds.py", "_grant_wild_unlock_flags"),
    ("content/world_cmds.py", "_teach_by_npc"),
    ("content/world_cmds.py", "_map_blocks"),
    ("content/world_cmds.py", "_hurry_section"),
]

#: E / C 分类（§2.3）。**实测口径**：改完后 `--emit-live` 逐段断言，不等就报错（不静默改分类）。
#:   C = 本线真正接上引擎形状的段；E = 逐字未动（`base == work`，理由写在 `out/LANDING.md`）。
CLASS = {
    # ── E：本批逐字未动（渲染/取值/动作链；无引擎形状可接，见 out/U1-I10_DESIGN.md §不做清单）──
    "content/world_cmds.py::_npc_dialogue": "E",
    # ↓ 2026-09-19 由 E 改判 C：C 档 22c（B-2 第 8 片）把本段的句壳搬进文案表
    #   （`_T.text("npcabsent.*")`），实现不再逐字等于冻结基线（非本线接引擎形状）。
    "content/world_cmds.py::_town_npc_absent_hint": "C",
    "content/world_cmds.py::_player_map_name": "E",
    "content/world_cmds.py::_subarea_name": "E",
    "content/world_cmds.py::_find_wild_npc": "E",
    # ↓ 2026-09-19 由 E 改判 C：C 档 31a（B-2 第 18 片）把本段的句壳搬进文案表
    #   （`_T.text("find.unseen_hint")`），实现不再逐字等于冻结基线（非本线接引擎形状）。
    "content/world_cmds.py::_wild_unseen_hint": "C",
    # ↓ 2026-09-19 由 E 改判 C：C 档 26a（B-2 第 12 片）把本段的句壳搬进文案表
    #   （`_T.static/_T.text("time.*" / "notes.*" / "npcwhere.*" / "wildcond.*" / "time_name.*")），
    #   实现不再逐字等于冻结基线（非本线接引擎形状）。
    "content/world_cmds.py::_npc_direction_hint": "C",
    # ↓ 2026-09-19 由 E 改判 C：C 档 26a（B-2 第 12 片）把本段的句壳搬进文案表
    #   （`_T.static/_T.text("time.*" / "notes.*" / "npcwhere.*" / "wildcond.*" / "time_name.*")），
    #   实现不再逐字等于冻结基线（非本线接引擎形状）。
    "content/world_cmds.py::_wild_cond_label": "C",
    "content/world_cmds.py::_talk_active": "E",
    "content/world_cmds.py::_talk_ctx": "E",
    # ↓ 2026-09-19 由 E 改判 C：C 档 31a（B-2 第 18 片）把本段的句壳搬进文案表
    #   （`_T.text("talk.side_take")`），实现不再逐字等于冻结基线（非本线接引擎形状）。
    "content/world_cmds.py::_side_menu_expand": "C",
    # ↓ 2026-09-19 由 E 改判 C：同上（C 档 22c；`talk.auto_quest_opt` / `talk.end_opt` 入表）。
    "content/world_cmds.py::_render_talk_node": "C",
    "content/world_cmds.py::_apply_talk_action_async": "E",
    "content/world_cmds.py::_apply_talk_action": "E",
    # ↓ 2026-09-18 由 E 改判 C：本次审计修复有意改了这两段的实现（非本线接引擎形状）
    #   · npc_quick_dialog：`talk_choice` 漏传 group_id/qq_id/player ⇒ 生产壳 TypeError、
    #     对话里回复数字整条挂掉（审计 #12）；修后行为=真能答，故与冻结基线不再相等。
    #   · move：`inst_row["state"]["inst_id"]` 与地图 id 直比恒 False（副本内移动兼容分支
    #     实为死代码）；改走 v137 统一口径 `_inst_map_id`。
    "content/world_cmds.py::npc_quick_dialog": "C",
    "content/world_cmds.py::move": "C",
    # ↓ 2026-09-19 由 E 改判 C：C 档 26a（B-2 第 12 片）把本段的句壳搬进文案表
    #   （`_T.static/_T.text("time.*" / "notes.*" / "npcwhere.*" / "wildcond.*" / "time_name.*")），
    #   实现不再逐字等于冻结基线（非本线接引擎形状）。
    "content/world_cmds.py::time_cmd": "C",
    # ↓ 2026-09-19 由 E 改判 C：C 档 26a（B-2 第 12 片）把本段的句壳搬进文案表
    #   （`_T.static/_T.text("time.*" / "notes.*" / "npcwhere.*" / "wildcond.*" / "time_name.*")），
    #   实现不再逐字等于冻结基线（非本线接引擎形状）。
    "content/world_cmds.py::wild_notes": "C",
    # ── C：本线接上引擎形状（Lookup / Presence / minutes_left / Cursor / Dialogue.pick·next_of·is_end）──
    "content/world_cmds.py::_current_npcs": "C",
    "content/world_cmds.py::_present_wild_hints": "C",
    "content/world_cmds.py::_start_talk_list": "C",
    "content/world_cmds.py::_find_npc_in_map": "C",
    "content/world_cmds.py::talk_choice": "C",
    "content/world_cmds.py::find_npc": "C",
    "content/world_cmds.py::turn_in": "C",
    "content/world_cmds.py::_grant_wild_unlock_flags": "C",
    "content/world_cmds.py::_teach_by_npc": "C",
    "content/world_cmds.py::_map_blocks": "C",
    "content/world_cmds.py::_hurry_section": "C",
}

#: `design/U1-I4_FROZEN_GATE.md` §1.4 那份 93 段基线里属于本门禁的 **29 条**（全 64 位）。
#: 生成器 `--check` 拿它交叉核对 —— 双向独立来源（设计稿 vs `base/pkg` 切片）必须一致。
_BASELINE_PINS = {
    "content/world_cmds.py::_npc_dialogue":
        "3b69a0d7c1a114dcc097a38025160792ed5c9a5d3c351a368cf072a91e39ffdc",
    "content/world_cmds.py::_current_npcs":
        "7abc1fe193d17017edf3981096651dd1232c60813e0ea7cdda9ef6eff3c81e6a",
    "content/world_cmds.py::_present_wild_hints":
        "4ffdf11b8f8e88591f0b8b565c3e8524a5c19f147d9a00019594cc5031b3a303",
    "content/world_cmds.py::_start_talk_list":
        "ae896c0baca4ad399de8719be51c08b1a3c70dae63bc300cc073d86726f70082",
    "content/world_cmds.py::_find_npc_in_map":
        "2022fd8f37f85789d196f8794b993f90809db551025cdcfb3b7473138c3c69d3",
    "content/world_cmds.py::_town_npc_absent_hint":
        "4cc4004260498e94271315ee3125b83dbaecee7fb24471997a09ef21a4c4e2aa",
    "content/world_cmds.py::_player_map_name":
        "f716578d359827ea51e1ee9f32cfd6f1ec286e47c530ebf218aea0915544e91e",
    "content/world_cmds.py::_subarea_name":
        "4250943f42e65eee747ecab6aede8dfab04880085198bbcaf9a34d4e4c178a90",
    "content/world_cmds.py::_find_wild_npc":
        "1547f72725e15d2e0d7221ceba33951077de824fc564aaf7393db1ed1041ca7a",
    "content/world_cmds.py::_wild_unseen_hint":
        "229bc0f30467a9a6e131bd42f2ef03f5a398242ecfd8df0fb5306049423af9b3",
    "content/world_cmds.py::_npc_direction_hint":
        "ac72a5c65db6f2b95fafd633d72f247438173174b372af5dd718dc53c7e03b99",
    "content/world_cmds.py::_wild_cond_label":
        "bb68183bc60caec285e16eb6d0a78dcf959b5be3c59c9b72979a68170a969db2",
    "content/world_cmds.py::_talk_active":
        "a58b89826c0a868e6c1336d44ec31e3f64f4a7f63a5b9f3f92e9cabe5233ffd2",
    "content/world_cmds.py::_talk_ctx":
        "830fcdd577ad841c402ab24f81f75a05bce67184808c871fcc4c36cdf898fae9",
    "content/world_cmds.py::_side_menu_expand":
        "315931d7f905d344260257f516e666a18c3290782052ee4949166a1317dba563",
    "content/world_cmds.py::_render_talk_node":
        "1845ed7d74e681366d72742c3bd1f517b799853b627cbf58cd5882eabc1b0d48",
    "content/world_cmds.py::_apply_talk_action_async":
        "5d112ddfde2e89557a474980dfe998af450e49c73fb4d72ef9b65077e258205b",
    "content/world_cmds.py::_apply_talk_action":
        "0e9f55287f28d2e08354d2ab539b0d44fa38e16bac38ed7e6b2a97a06ce576f8",
    "content/world_cmds.py::talk_choice":
        "3dd272614848e5ee448f41df9a0439a2003faf3297f3f1076aefdaa485cec7c6",
    "content/world_cmds.py::npc_quick_dialog":
        "d2cea7fd1041323fe0822fba1b413094dfc49228c0558d03240e8ed7327fe129",
    "content/world_cmds.py::find_npc":
        "afb1319343a37b7e8cb7b364d6aaf05d4771b303fa6c87d3c655e21ed0de3a4c",
    "content/world_cmds.py::move":
        "c5e307ec7b424ccba7487bf7f3191aa672b44374498c06a27216726158b02fd1",
    "content/world_cmds.py::time_cmd":
        "ecd979490d5019b349af04e3f2ac6526423cf7a0d32c35af7c1b6ede50302e39",
    "content/world_cmds.py::wild_notes":
        "99fddc5597f852dee3877e3b2ec9e3d0d0332d5b5c7ada99cf8a682ba87f4dcb",
    "content/world_cmds.py::turn_in":
        "fcae401a25489b2bb19222c949e86a668d3d7068ecc3b35848bfc3cdd9980b3b",
    "content/world_cmds.py::_grant_wild_unlock_flags":
        "6df46a6ece624f86847309f5679539b5e8f7cafa4a8220595d2c7ca78ad8e591",
    "content/world_cmds.py::_teach_by_npc":
        "c1d30c6e42918f3521637ebe51aa1c9cf4109fc4d59d7eebe2e8d8e82ae7bf54",
    "content/world_cmds.py::_map_blocks":
        "3b6e9a5a63a1d03338acbee0e9fcbb72980651615001a4195695d76f6b3c55c5",
    "content/world_cmds.py::_hurry_section":
        "7c29af49565217d3853e7efc9606b3f2155d9569c711cf8eef060e84fcae86fd",
}


# ══════════════════════════════════════════════════════════════ 切片口径（§1.2）
def slice_source(path: str, symbol: str) -> str:
    """从 `path` 里切出 `symbol` 的**整段源码文本**（含装饰器，保留原行尾）。

    与 `inspect.getsource` 逐字节一致（自检①当面证明）。
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
    → ④ **git 历史回溯**（最近 20 个改动过被测文件的提交里找「29 段切片 sha256 全等设计 pin」的版本）。
    都失败 ⇒ `(None, "none")`，调用方**必须显式报错**（不许静默降级）。
    """
    candidates = []
    env = os.environ.get("GWEN_U1I4_BASE_PKG")
    if env:
        candidates.append(("env", env))
    candidates.append(("lane", os.path.join(LANE_ROOT, "base", "pkg")))
    candidates.append(("repo", os.path.join(PKG_ROOT, ".u1i4_base", "pkg")))
    for tag, path in candidates:
        if os.path.isfile(os.path.join(path, "content", "world_cmds.py")):
            return path, tag
    try:
        import subprocess
        import tempfile
        gd = os.path.join(PKG_ROOT, ".git")
        if os.path.isdir(gd) or os.path.isfile(gd):
            revs = subprocess.run(["git", "-C", PKG_ROOT, "log", "--format=%H", "-n", "20",
                                   "--", "content/world_cmds.py"],
                                  capture_output=True, text=True).stdout.split()
            tmp = tempfile.mkdtemp(prefix="u1i4w_base_")
            for rev in revs:
                blob = subprocess.run(["git", "-C", PKG_ROOT, "show",
                                       "%s:content/world_cmds.py" % rev],
                                      capture_output=True).stdout
                if not blob:
                    continue
                dst = os.path.join(tmp, "content", "world_cmds.py")
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as fh:
                    fh.write(blob)
                if _base_matches_pins(tmp):
                    return tmp, "git:%s" % rev[:8]
    except Exception as exc:                                     # noqa: BLE001
        print("[gen] ⚠️ git 回溯失败：%r" % (exc,))
    return None, "none"


def _base_matches_pins(path) -> bool:
    """候选 base 的 29 段切片是否全等 `_BASELINE_PINS`。"""
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
    """29 段冻结文本（读 `base/pkg/**`）。"""
    if BASE_PKG is None:
        raise SystemExit(_no_base_msg())
    return {key_of(r, s): slice_source(os.path.join(BASE_PKG, *r.split("/")), s)
            for r, s in SEGMENTS}


def _no_base_msg() -> str:
    return ("❌ 找不到改动前基线（base/pkg）—— 生成器**拒绝执行**（fail-closed，不静默降级）。\n"
            "   解析顺序：GWEN_U1I4_BASE_PKG → <lane>/base/pkg → <pkg>/.u1i4_base/pkg → git 历史回溯\n"
            "   启用方式：GWEN_U1I4_BASE_PKG=<含 content/world_cmds.py 的 pkg 目录>")


# ══════════════════════════════════════════════════════════════ 活侧取件
def _boot_work_pkg():
    """把 `work/pkg`（+ tests + shim + 引擎根 + 宿主壳根）摆进 `sys.path` 并兜底沙箱环境变量。"""
    lane = LANE_ROOT
    os.environ.setdefault("GWEN_FRAMEWORK_DIR", os.path.join(lane, "work", "eng"))
    os.environ.setdefault("GWEN_HOST_DIR", os.path.join(lane, "work", "host"))
    os.environ.setdefault("GWEN_GAME_DB", os.path.join(lane, "out", "test_u1i4_world.db"))
    os.environ.setdefault("GWEN_TEST_MODE", "1")
    os.environ.setdefault("PYTHONUTF8", "1")
    shim = os.path.join(_HERE, "shim_astrbot")
    for p in (shim, _HERE, PKG_ROOT,
              os.environ["GWEN_FRAMEWORK_DIR"], os.environ["GWEN_HOST_DIR"]):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


def live_object(relpath: str, symbol: str):
    """活模块里的对象（本门禁 29 段全在 `content.world_cmds`）。"""
    _boot_work_pkg()
    modname = "content." + relpath.split("/", 1)[1][:-3].replace("/", ".")
    mod = importlib.import_module(modname)
    return getattr(mod, symbol, None)


def live_pins() -> dict:
    import inspect
    out = {}
    for relpath, symbol in SEGMENTS:
        obj = live_object(relpath, symbol)
        out[key_of(relpath, symbol)] = (
            "<deleted>" if obj is None else sha256_text(inspect.getsource(obj)))
    return out


# ══════════════════════════════════════════════════════════════ 自检（§1.2 三条 + 分级）
def _tier_of(text: str) -> str:
    """机械分级（§1.3）：`丙` ⟺ async def；否则 `乙` ⟺ 段内出现 `self.`；否则 `甲`。"""
    node = ast.parse(text).body[0]
    if isinstance(node, ast.AsyncFunctionDef):
        return "丙"
    return "乙" if "self." in text else "甲"


def self_check(*, with_live=True) -> list:
    """三条自检 + 分级计数；返回打印用的行列表。任何一条不过 → 抛 SystemExit。"""
    lines = []
    frozen = frozen_slices()
    if len(frozen) != 29:
        raise SystemExit("自检②失败：切片数 = %d（期望 29）" % len(frozen))
    lines.append("  ① 段数 = %d（期望 29）" % len(frozen))

    for key, text in frozen.items():
        try:
            ast.parse(text)
        except SyntaxError as exc:
            raise SystemExit("自检②失败：%s 切片不能 ast.parse：%s" % (key, exc))
        n = text.count("def %s(" % key.split("::")[1])
        if n != 1:
            raise SystemExit("自检③失败：%s 里 `def %s(` 出现 %d 次（期望 1）"
                             % (key, key.split("::")[1], n))
    lines.append("  ② 29 段切片全部 ast.parse 可编译")

    for i, (relpath, symbol) in enumerate(SEGMENTS[:-1]):
        nxt_rel, nxt_sym = SEGMENTS[i + 1]
        if nxt_rel != relpath:
            continue
        marker = "def %s(" % nxt_sym
        if marker in frozen[key_of(relpath, symbol)]:
            raise SystemExit("自检③失败：%s 的切片里出现下一段首行 %r"
                             % (key_of(relpath, symbol), marker))
    lines.append("  ③ 无切片越界（下一段首行不出现）")

    if len(_BASELINE_PINS) != 29:
        raise SystemExit("自检④失败：内嵌基线 29 条，实际 %d 条" % len(_BASELINE_PINS))
    mismatch = [k for k, want in _BASELINE_PINS.items()
                if sha256_text(frozen.get(k, "")) != want]
    if mismatch:
        raise SystemExit("自检④失败：与 design/U1-I4_FROZEN_GATE.md §1.4 基线不一致：%s"
                         % ", ".join(mismatch))
    lines.append("  ④ 29 条冻结 sha256 == `FROZEN_GATE.md` §1.4 基线（全 64 位）")

    tiers = {}
    for relpath, symbol in SEGMENTS:
        tiers.setdefault(_tier_of(frozen[key_of(relpath, symbol)]), []).append(symbol)
    if sorted(tiers) != ["丙", "乙", "甲"]:
        raise SystemExit("自检⑤失败：分级不全 %s" % sorted(tiers))
    lines.append("  ⑤ 分级：甲 %d / 乙 %d / 丙 %d（期望 11 / 10 / 8）"
                 % (len(tiers["甲"]), len(tiers["乙"]), len(tiers["丙"])))
    if (len(tiers["甲"]), len(tiers["乙"]), len(tiers["丙"])) != (11, 10, 8):
        raise SystemExit("自检⑤失败：分级计数与 `FROZEN_GATE.md` §1.3 不符")

    if with_live:
        live = live_pins()
        bad = [k for k, cls in CLASS.items()
               if cls == "E" and live[k] != sha256_text(frozen[k])]
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
           "# ⚠ 本块由 `tests/_u1i4_wiring_world_gen.py` 生成 —— 手工改动 = 门禁失去安全网。",
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
        order = sorted(pin[section]) if section == "aux" else \
            [key_of(r, s) for r, s in SEGMENTS if key_of(r, s) in pin[section]]
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
    out.append("    'tier': {")
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        out.append("        %r: %r," % (k, pin["tier"][k]))
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
    pin["tier"] = {key_of(r, s): _tier_of(frozen[key_of(r, s)]) for r, s in SEGMENTS}
    if aux is not None:
        pin["aux"] = aux
    _write_region(_render(frozen, pin))


def _emit_frozen() -> None:
    print("【--emit-frozen】冻结 29 段（base/pkg）+ 红基线 live pin")
    frozen = frozen_slices()
    live = live_pins()
    _emit("baseline", live=live)
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        print("  [%s/%s] %-42s frozen=%s live=%s"
              % (CLASS[k], _tier_of(frozen[k]), k, sha256_text(frozen[k])[:12], live[k][:12]))


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
        ok = (l != f) if cls == "C" else (l == f)
        want = "frozen != live" if cls == "C" else "frozen == live"
        if not ok:
            bad.append("%s（%s：%s；frozen=%s live=%s）" % (k, cls, want, f[:12], l[:12]))
        print("  [%s/%s] %-42s %-8s frozen=%s live=%s"
              % (cls, _tier_of(frozen[k]), k, "CHANGED" if l != f else "same", f[:12], l[:12]))
    if bad:
        raise SystemExit("E/C 分类断言失败（共 %d 条）：\n    %s" % (len(bad), "\n    ".join(bad)))
    _emit("landed", live=live)
    print("  E/C 分类断言全过 → phase=landed")
    print("  提示：甲/乙类逐格比 + 丙类探针由 `test_u1i4_wiring_world_frozen.py` 跑。")


def _emit_aux() -> None:
    print("【--emit-aux】数据面 / 存档面 + 丙类 golden 探针（跑活实现取产物）")
    _boot_work_pkg()
    spec = importlib.util.spec_from_file_location("_u1i4_wiring_gate", TEST_FILE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    aux = gate._aux_fingerprints()
    cur = _current_pin()
    phase = cur.get("phase")
    _emit(phase if phase in ("baseline", "landed") else "baseline", aux=aux)
    for k in sorted(aux):
        print("  %-24s %s" % (k, str(aux[k])[:72]))


BASE_PKG, BASE_SOURCE = _resolve_base_pkg()      # ★ 必须在 slice_source / SEGMENTS / _BASELINE_PINS 之后


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="U1-I4 门禁③ 生成器（世界侧装配）")
    ap.add_argument("--check", action="store_true", help="只自检（§1.2 三条 + 分级），不改文件")
    ap.add_argument("--no-live", action="store_true", help="自检跳过「活实现」那一条")
    ap.add_argument("--emit-frozen", action="store_true", help="生成 _FROZEN_TEXT + _PIN（红基线）")
    ap.add_argument("--emit-live", action="store_true", help="重生成 _PIN['live']（落档）")
    ap.add_argument("--emit-aux", action="store_true", help="生成 _PIN['aux']（数据面 + golden）")
    args = ap.parse_args(argv)
    if not (args.check or args.emit_frozen or args.emit_live or args.emit_aux):
        ap.print_help()
        return 2
    print("== U1-I4 门禁③ 生成器 ==")
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
