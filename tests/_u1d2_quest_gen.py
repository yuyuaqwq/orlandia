# -*- coding: utf-8 -*-
"""U1-D2 门禁① 生成器（任务块）—— 28 段冻结文本 / 双 sha256 / aux 指纹。

口径（照 `design/U1-D2_FROZEN_GATE.md` §1.2 · §2.2 · §2.3 与作业书 §2 步骤 1）
--------------------------------------------------------------------------------
* **冻结侧读 `<lane>/base/pkg/**`**（本工作区 `base/` 取自 L1 落地之后、L4 动手之前；
  `work/pkg == base/pkg` 开工时成立）。用 `ast` 逐行切片出旧实现文本；
  切片口径 = `min(装饰器行, def 行)` 起、`node.end_lineno` 止，**保留原行尾**
  ⇒ 与 `inspect.getsource(<活实现>)` 逐字节相等（`--emit-frozen` 时对**全部 28 段**
  当面证明，不只 E 栏）。
* 生成器输出**只写进** `tests/test_u1d2_quest_frozen.py` 的两行标记之间；
  标记之外的正文（比对逻辑）**一个字节都不碰**。
* 28 段 = `quests_flow.py`(17) + `profession_quests.py`(5) + `world_cmds.py`(3) +
  `cmds_world.py`(3)；档位（机械判据 `§1.3`）实测 **甲 28 / 乙 0 / 丙 0**。

base 解析四级（照 `_u1i4_wiring_outer_gen.py:147-212` 的现成骨架，找不到 **fail-closed**）
--------------------------------------------------------------------------------
    ① 环境变量 `GWEN_U1D2_BASE_PKG`
    ② `<lane>/base/pkg`
    ③ `<pkg>/.u1d2_base/pkg`
    ④ `git` 历史回溯（只读；不可用就走前三级）

⚠️ `design/U1-D2_FROZEN_GATE.md` §1.4 的 28 条基线是**设计期快照**：实测 27/28 逐字相等，
   `content/cmds_world.py::quest_view` 因 U1-I4 的 L6 在本设计之后落地而不同
   （`base/pkg` 是 L1 之后、L4 之前的状态 ⇒ 以本工作区 `base/pkg` 切片为准）。
   交叉核对只打印 SAME/DIFF，不据此改冻结侧。

四档命令
--------
    python tests/_u1d2_quest_gen.py --check        # 只自检，不改文件
    python tests/_u1d2_quest_gen.py --emit-frozen  # 生成 _FROZEN_TEXT + _PIN（红基线档）
    python tests/_u1d2_quest_gen.py --emit-live    # 实现改完后重生成 _PIN["live"]（落档）
    python tests/_u1d2_quest_gen.py --emit-aux     # 生成 _PIN["aux"]（**必须在改实现之前**）

E/C 分类（§2.3）
----------------
* **E**（预期不变）：本批不该动的段 —— `--emit-live` 时**断言 `frozen == live`**。
* **C**（预期会变）：本批会改的段 —— 断言 `frozen != live`（**没变说明没真接上**）。
  与设计 §2.3 的两处**实测出入**（见 `out/LANDING.md` §「E/C 口径出入」）：
  `world_cmds.py::_take_main_quest` / `cmds_world.py::_svc` / `cmds_world.py::_kill_prog_count`
  是**行为保持的薄壳/取值段**（本批零改动）⇒ 归 E；设计把它们记在 C 栏。
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
TEST_FILE = os.path.join(_HERE, "test_u1d2_quest_frozen.py")

BEGIN = "# >>> _u1d2_quest_gen (auto) >>>"
END = "# <<< _u1d2_quest_gen (auto) <<<"

#: 28 段（文件 · 符号），**顺序即门禁内键序**（照 `FROZEN_GATE.md` §1.4 的段序）。
SEGMENTS = [
    ("content/quests_flow.py", "obj_text"),
    ("content/quests_flow.py", "sq_unlocked"),
    ("content/quests_flow.py", "sq_stats_met"),
    ("content/quests_flow.py", "available_quest_list"),
    ("content/quests_flow.py", "update_explore_quests"),
    ("content/quests_flow.py", "take_main_quest"),
    ("content/quests_flow.py", "quest_reputation"),
    ("content/quests_flow.py", "deliver_hint"),
    ("content/quests_flow.py", "side_available_list"),
    ("content/quests_flow.py", "offer_side_quest"),
    ("content/quests_flow.py", "offer_side_quests"),
    ("content/quests_flow.py", "grant_quest_rewards"),
    ("content/quests_flow.py", "complete_side_quest"),
    ("content/quests_flow.py", "talk_quest_progress"),
    ("content/quests_flow.py", "update_use_quests"),
    ("content/quests_flow.py", "branch_wait_sid"),
    ("content/quests_flow.py", "quest_kill_progress"),
    ("content/profession_quests.py", "daily_need"),
    ("content/profession_quests.py", "settle_daily_quest"),
    ("content/profession_quests.py", "bump_daily_progress"),
    ("content/profession_quests.py", "daily_pool"),
    ("content/profession_quests.py", "draw_daily"),
    ("content/world_cmds.py", "_obj_text"),
    ("content/world_cmds.py", "_obj_text_lines"),
    ("content/world_cmds.py", "_take_main_quest"),
    ("content/cmds_world.py", "_svc"),
    ("content/cmds_world.py", "_kill_prog_count"),
    ("content/cmds_world.py", "quest_view"),
]

#: E / C 分类（§2.3）。**实测口径**：改完后 `--emit-live` 逐段断言，不等就报错
#: （不静默改分类；出入写进 `out/LANDING.md`）。
CLASS = {
    # ── C：本批真接上引擎形状（quest 账本 / 目标注册表 / lines 骨架）──
    "content/quests_flow.py::obj_text": "C",
    "content/quests_flow.py::sq_unlocked": "C",
    "content/quests_flow.py::available_quest_list": "C",
    "content/quests_flow.py::update_explore_quests": "C",
    "content/quests_flow.py::take_main_quest": "C",
    "content/quests_flow.py::side_available_list": "C",
    "content/quests_flow.py::offer_side_quest": "C",
    "content/quests_flow.py::offer_side_quests": "C",
    "content/quests_flow.py::complete_side_quest": "C",
    "content/quests_flow.py::talk_quest_progress": "C",
    "content/quests_flow.py::update_use_quests": "C",
    "content/quests_flow.py::quest_kill_progress": "C",
    "content/profession_quests.py::daily_need": "C",
    "content/profession_quests.py::bump_daily_progress": "C",
    "content/profession_quests.py::draw_daily": "C",
    "content/world_cmds.py::_obj_text": "C",
    "content/world_cmds.py::_obj_text_lines": "C",
    "content/cmds_world.py::quest_view": "C",
    # ── E：本批逐字未动（取值/奖励/门槛/薄壳；无引擎形状可接）──
    "content/quests_flow.py::sq_stats_met": "E",
    # ★ C 档 29a（B-2 第 16 片）：两段源码因「文案入表」改动（行为逐字不变：
    #   只把字面量换成 `_T.text/_T.static` 调用）⇒ E → C（实测口径）。
    "content/quests_flow.py::quest_reputation": "C",
    "content/quests_flow.py::deliver_hint": "E",
    "content/quests_flow.py::grant_quest_rewards": "C",
    "content/quests_flow.py::branch_wait_sid": "E",
    # ★ C 档（2026-09-26 N10 收口 3）：本段源码因「`_title_bonus` → `_panel_bonus` 全局改名」
    #   改动（**行为逐字不变**：只换玩家 dict 的键名，值 = 同一份 stat_bonus 聚合结果；
    #   13 064 格冻结网格实测无不一致）⇒ E → C（实测口径，与上面 29a 同法）。
    "content/profession_quests.py::settle_daily_quest": "C",
    "content/profession_quests.py::daily_pool": "E",
    "content/world_cmds.py::_take_main_quest": "E",
    "content/cmds_world.py::_svc": "E",
    "content/cmds_world.py::_kill_prog_count": "E",
}

#: `design/U1-D2_FROZEN_GATE.md` §1.4 那份 28 段基线里属于本门禁的 28 条（全 64 位）。
#: 生成器 `--check` 拿它交叉核对（**软核对**：`quest_view` 实测不同，理由见模块头注）。
_BASELINE_PINS = {
    "content/quests_flow.py::obj_text":
        "76056be4a678d4e19318695f373fb6c33ca0258453efda84980688613a468b8f",
    "content/quests_flow.py::sq_unlocked":
        "05962447d140bd93dd329c1dd1d375d7006db64d301edfa3bbe1c974354c6a93",
    "content/quests_flow.py::sq_stats_met":
        "a3123a3bfcfc390bf3e87afe8942fea7476ff14b45d9270cae36c80ac4b740a6",
    "content/quests_flow.py::available_quest_list":
        "b1d4e08ed6a16f424b86d73936480ae4cfec83b139e8cb31050c41ebfd10e1f7",
    "content/quests_flow.py::update_explore_quests":
        "706f2b893e2fb170cac94f619a2396280d34e946c5f8e9fc864f2c2142ee9fd0",
    "content/quests_flow.py::take_main_quest":
        "84d7001b07232abb7f6d6cdc3d65895c82826c8381a657e7fb2223109c560f66",
    "content/quests_flow.py::quest_reputation":
        "5a5f851ed84a9165cfd55495dc3268ebbe59da9b756fbd1eeed781f49d566eec",
    "content/quests_flow.py::deliver_hint":
        "f075d5a2d35f430cdf6774df4f936732252c63d5e4d0a6bdf03bd045d01a4d8f",
    "content/quests_flow.py::side_available_list":
        "be41cf9c7c9f8f5e831a4b123f036c967b408b668c433acbc8079e037ffd16be",
    "content/quests_flow.py::offer_side_quest":
        "bcc6f23d8817fa33d152f33088f915f44e201a8a45aee5c1ccdde7669759d453",
    "content/quests_flow.py::offer_side_quests":
        "203fb0f187274f8ef89e2067c4114eb4057d935b3ca1326ae0c151da099a36e1",
    "content/quests_flow.py::grant_quest_rewards":
        "2643c85478a15244a2c50c9d26c8a4ea74679632080c93056d91182c5eb8f8f4",
    "content/quests_flow.py::complete_side_quest":
        "14ca1cb0f9fd031340472ee0c0c476a194fd952734f2b1b260b45ef52efc4006",
    "content/quests_flow.py::talk_quest_progress":
        "9bd1304069f51121bd3fd35298f4e538aac559a8fb2cf2abaffc69b812e3406c",
    "content/quests_flow.py::update_use_quests":
        "52c1cdd4456c354babcf9c12b7de5071559681217edb7dac229a02dbbb43e38b",
    "content/quests_flow.py::branch_wait_sid":
        "4436a53533504b4be1d11d3dea8434c774039a48ffcec52c4991a3fcee47b680",
    "content/quests_flow.py::quest_kill_progress":
        "7e02e92cd335e79af35f625d8ea2e4820a9e1993bedd35180055ac694ed7b897",
    "content/profession_quests.py::daily_need":
        "ec38afa1f7c242a6f303bac8b5e1de94bea363c1f17cc8a63922e05bc7a7b48e",
    "content/profession_quests.py::settle_daily_quest":
        "c1e2cf3ddffb394bbbd905f6e41e440233907daa38a8fd6e024a9259aaf9da2f",
    "content/profession_quests.py::bump_daily_progress":
        "df50f27b5236e4ee52689a7644c64f2ced85ad072153776c1518c3133d48e66e",
    "content/profession_quests.py::daily_pool":
        "75d20348e9403773e5ba464e88aa86dad6de5cefc71611a822672a9c5cf17533",
    "content/profession_quests.py::draw_daily":
        "9b4bde65ea3cdc184e1649b4d1f8871908fe9daa7345bf37583edc020e1488d0",
    "content/world_cmds.py::_obj_text":
        "713000406a20fe7ed72eac8b3a97d283bb91730d0cf382250e18dc0b50b4ab5a",
    "content/world_cmds.py::_obj_text_lines":
        "91b9e23b8186631d1fb7e5284cebe66cab9a5dbdd4ba9ef6bc7578a69d08dd05",
    "content/world_cmds.py::_take_main_quest":
        "0b3f8c8dc0ec564e2dff5a77e27ee826cf2788e9e1df2bcefc899c583026556a",
    "content/cmds_world.py::_svc":
        "84f063ece8743a96b4c98ba39aaaa4c293799b285d01b16c5472ecd5ffeba3b9",
    "content/cmds_world.py::_kill_prog_count":
        "a0446090c33bb1e071c4892236a2938a0d7ca84e5d0987185de00a7b3575f495",
    # ⚠ 设计期快照；U1-I4 L6 之后实测 = a7a9e96ec5c3…（见模块头注）
    "content/cmds_world.py::quest_view":
        "bcccf11297a8ae87c51fbb8d14c851c833510ecf30a0888d95a23faf208e1d21",
}


# ══════════════════════════════════════════════════════════════ 切片口径（§1.2）
def slice_source(path: str, symbol: str) -> str:
    """从 `path` 里切出 `symbol` 的**整段源码文本**（含装饰器，保留原行尾）。

    与 `inspect.getsource` 逐字节一致（生成时对全部 28 段当面证明）。
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


# ─────────────────────────────────────────────── base 解析（四级；找不到 fail-closed）
def _resolve_base_pkg():
    """改动前基线副本 —— ① `GWEN_U1D2_BASE_PKG` → ② `<lane>/base/pkg`
    → ③ `<pkg>/.u1d2_base/pkg` → ④ `git` 历史回溯（只读）。

    都失败 ⇒ `(None, "none")`，调用方**必须显式报错**（fail-closed，不静默降级）。
    """
    candidates = []
    env = os.environ.get("GWEN_U1D2_BASE_PKG")
    if env:
        candidates.append(("env", env))
    candidates.append(("lane", os.path.join(LANE_ROOT, "base", "pkg")))
    candidates.append(("repo", os.path.join(PKG_ROOT, ".u1d2_base", "pkg")))
    for tag, path in candidates:
        if os.path.isfile(os.path.join(path, "content", "quests_flow.py")):
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
            for rev in revs:
                tmp = tempfile.mkdtemp(prefix="u1d2_base_")
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
    """候选 base 的 28 段切片是否与设计 §1.4 基线**基本一致**（允许 1 处已知出入）。"""
    try:
        same = 0
        for relpath, symbol in SEGMENTS:
            want = _BASELINE_PINS.get(key_of(relpath, symbol))
            if want is None:
                return False
            got = sha256_text(slice_source(os.path.join(path, *relpath.split("/")), symbol))
            if got == want:
                same += 1
        return same >= 27
    except Exception:                                            # noqa: BLE001
        return False


def _no_base_msg() -> str:
    return ("❌ 找不到改动前基线（base/pkg）—— 生成器**拒绝执行**（fail-closed，不静默降级）。\n"
            "   解析顺序：GWEN_U1D2_BASE_PKG → <lane>/base/pkg → <pkg>/.u1d2_base/pkg → git 历史回溯\n"
            "   启用方式：GWEN_U1D2_BASE_PKG=<含 content/quests_flow.py 的 pkg 目录>")


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
    os.environ.setdefault("GWEN_GAME_DB", os.path.join(lane, "out", "test_u1d2_L4.db"))
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
    """活模块里的对象：28 段全是模块级函数 → 直取。"""
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


# ══════════════════════════════════════════════════════════════ 自检（§1.2）
def self_check(*, with_live=True) -> list:
    lines = []
    frozen = frozen_slices()
    if len(frozen) != 28:
        raise SystemExit("自检①失败：切片数 = %d（期望 28）" % len(frozen))
    lines.append("  ① 段数 = %d（期望 28）" % len(frozen))

    for key, text in frozen.items():
        try:
            ast.parse(text)
        except SyntaxError as exc:
            raise SystemExit("自检②失败：%s 切片不能 ast.parse：%s" % (key, exc))
        n = text.count("def %s(" % key.split("::")[1])
        if n != 1:
            raise SystemExit("自检②失败：%s 里 `def %s(` 出现 %d 次（期望 1）"
                             % (key, key.split("::")[1], n))
    lines.append("  ② 28 段切片全部 ast.parse 可编译")

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

    # ④ 与设计稿 §1.4 基线交叉核对（软核对：打印 SAME/DIFF，允许 quest_view 一处已知出入）
    if len(_BASELINE_PINS) != 28:
        raise SystemExit("自检④失败：内嵌基线 28 条，实际 %d 条" % len(_BASELINE_PINS))
    diff = [k for k, want in _BASELINE_PINS.items()
            if sha256_text(frozen.get(k, "")) != want]
    lines.append("  ④ 与 `FROZEN_GATE.md` §1.4 基线一致：%d/28（DIFF：%s）"
                 % (28 - len(diff), ", ".join(diff) or "无"))
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
           "# ⚠ 本块由 `tests/_u1d2_quest_gen.py` 生成 —— 手工改动 = 门禁失去安全网。",
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
    print("【--emit-frozen】冻结 28 段（base/pkg）+ 红基线 live pin")
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
    _emit("baseline", live=live)
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        print("  [%s/%s] %-52s frozen=%s live=%s"
              % (CLASS[k], tier_of(frozen[k]), k, sha256_text(frozen[k])[:12], live[k][:12]))
    print("  （红基线自证：28/28 段 切片(base) == inspect.getsource(活实现)）")


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
    print("【--emit-aux】存档面指纹 + 只读零改动指纹（跑活实现取产物）")
    _boot_work_pkg()
    spec = importlib.util.spec_from_file_location("_u1d2_quest_gate", TEST_FILE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    aux = gate._aux_fingerprints()
    cur = _current_pin()
    phase = cur.get("phase")
    _emit(phase if phase in ("baseline", "landed") else "baseline", aux=aux)
    for k in sorted(aux):
        print("  %-24s %s" % (k, str(aux[k])[:72]))


BASE_PKG, BASE_SOURCE = _resolve_base_pkg()      # ★ 必须在 slice_source / SEGMENTS 之后


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="U1-D2 门禁① 生成器（任务块）")
    ap.add_argument("--check", action="store_true", help="只自检，不改文件")
    ap.add_argument("--no-live", action="store_true", help="自检跳过「活实现」那一条")
    ap.add_argument("--emit-frozen", action="store_true", help="生成 _FROZEN_TEXT + _PIN（红基线）")
    ap.add_argument("--emit-live", action="store_true", help="重生成 _PIN['live']（落档）")
    ap.add_argument("--emit-aux", action="store_true", help="生成 _PIN['aux']")
    args = ap.parse_args(argv)
    if not (args.check or args.emit_frozen or args.emit_live or args.emit_aux):
        ap.print_help()
        return 2
    print("== U1-D2 门禁① 生成器（任务块）==")
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
