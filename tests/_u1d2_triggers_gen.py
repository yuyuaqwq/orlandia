# -*- coding: utf-8 -*-
"""U1-D2 门禁③ 生成器（触发器主四件）—— 11 段冻结文本 / 双 sha256 / aux 指纹。

口径（照 `design/U1-D2_FROZEN_GATE.md` §1.2 · §2.2 · §2.3 · §5.3）
-----------------------------------------------------------------
* **冻结侧读 `base/pkg/**`**（= 改动前基线；本工作区 `base/pkg == work/pkg`，开工时冻结），
  用 `ast` 逐行切片出旧实现文本；切片口径 = `min(装饰器行, def 行)` 起、`node.end_lineno` 止、
  **保留原行尾** ⇒ 与 `inspect.getsource(<活实现>)` 逐字节相等
  （`--emit-frozen` 时对**全部 11 段**当面证明，不只 E 栏）。
* 生成器输出**只写进** `tests/test_u1d2_triggers_frozen.py` 的两行标记之间；
  标记之外的正文（比对逻辑）**一个字节都不碰**。
* 11 段 = 4 文件（`equip.py` 4 · `food_proc.py` 4 · `team_procs.py` 1 · `worldboss.py` 2）。
  ★ 2026-09-26（E5-4 收口 2a）：`equip.map_event` 段**退出冻结**（见下方 2a 登记）。

档位（机械判据，`FROZEN_GATE.md` §1.3）：`丙` ⟺ `async def`；否则 `乙` ⟺ 段内出现 `self.`；
否则 `甲`。本门禁 = **甲 11 / 乙 0 / 丙 0**（= `FROZEN_GATE.md` §0 的 12 段去掉 2a 移出的 1 段）。

⚠️ **不跑任何 `git` 写命令**（作业书 §5 禁令 1）：base 解析走 `git log` / `git show`
（只读），解析失败即 fail-closed 报错。

2026-09-26 修复（引擎线台账 §2-1）
----------------------------------
1. **base 判据 = 全基线指纹**：`_BASELINE_PINS`（11 段切片 sha256）**＋**
   `_AUX_BASELINE_PINS`（4 数据表 + 装配契约 + 4 源文件基线 sha256）。
   旧口径只比 12 段切片 ⇒ git 回溯选到 `e4dccb4e`（切片对得上，`content/apply.py`
   是另一版）⇒ aux 生成不出正确值、E 栏自检必红。全指纹口径唯一命中**真正的改动前
   基线** `8f3864f`（2026-09-17）。
2. **base 树整棵落盘**：`BASE_RELS`（4 源文件 + 4 数据表 + `content/apply.py`）
   ⇒ `--emit-aux` 可重新生成（旧 git 兜底只落 4 个源文件，读数据表直接 FileNotFound）。
3. **引擎侧 aux 读活引擎**（`ENG_RELS`）：真仓布局没有「基线引擎副本」，
   门禁 `test_u1d2_triggers_frozen.py::test_aux` 比对的就是**活引擎**
   （`GWEN_FRAMEWORK_DIR`）⇒ 生成器必须从同一个源取。
4. **E 栏登记过的跨线改写**（`LIVE_DIVERGENCE`）：`equip._known_engine_events` 的
   活实现文本比 base 切片只差一条 import 搬迁（`saintess_engine.battle` →
   `ext_combat.battle`，2026-09-23 包栈重构）⇒ 登记成机械改写，自检⑥ 逐字节证明
   「改写(base 切片) == 活实现文本」；**判据只加强**（条数钉 1、old_base 必须等于
   设计稿基线、只能落在 E 栏），任何第三处改动都会被抓住。
5. **活侧兜底环境变量跟真仓布局**：旧 `<lane>/work/{pkg,eng,host}` 随包并入引擎仓
   （`<引擎仓>/games/orlandia`）已不存在 ⇒ 引擎根兜底 = 本包祖父；宿主壳根**不猜**，
   由外层给 `GWEN_HOST_DIR`（与 `_e5_pairs.py` / 宿主跑器同口径；缺失时 `_paths`
   醒目报错，不静默装绿）。

2026-09-26 · E5-4 收口 2a（宣告 `equip.map_event` 段退出冻结）
--------------------------------------------------------
**改写理由**：E5-4 收口第 ② 步 —— `map_event` 旧事件名层要迁进内容侧（展开写进翻译器 /
装配路径），`equip.map_event` 里的**未知名告警**要改挂 `Compiler(on_unknown=…)`（保住
反静默失效）⇒ 该段文本**必然改**；继续按 E 栏冻结（frozen == live）与迁移自相矛盾。
**日期**：2026-09-26。
**旧口径**：12 段全冻结（E 6 / C 6 · 甲 12）；`equip.map_event` / `food_proc._map_event` 属 E 栏。
**新口径**：`equip.map_event` **移出冻结**（`SEGMENTS` / `CLASS` / `_BASELINE_PINS` 三处同删）
⇒ **11 段 · 甲 11 · E 栏 5 / C 栏 6**；它原本承担的语义改由门禁 `[2]` 的**表声明锚定**口径
接住（旧名映射的单一真源 = 数据表声明；活实现展开口逐键 == 声明 · 逐事件双向比对），
判据只加强不削弱。`food_proc._map_event` **继续冻结在 E 栏**：它是纯查表包装（无告警 /
无状态 / 无第二真源），迁移只改它**上游**（`install_food_fx` 的展开循环 = C 栏）⇒
退出冻结的判据是「该段文本会随迁移改动」，不是「属于同一层」。
**若 2b 改成把 food 的展开内联进 `install_food_fx`**（`_map_event` 成死码）：同批把
`food_proc._map_event` 也移出 `SEGMENTS` / `CLASS` / `_BASELINE_PINS`，并在此补一行登记。

2026-09-26 · E5-4 收口 2c（引擎侧 `map_event` 注入面已删）
--------------------------------------------------------
**为何动 aux**：aux 的 `engine:` 两项**读活引擎**（`live_engine_root()`，门禁 `test_aux` 比对的
也是活引擎）—— 2c 删掉 `declarations.py` 的 `map_event` 形参 / 校验 / `_map_event` 槽 /
`_targets()` 后，这两项**必然变**，属设计内合法重采（不是放宽判据）。**其余口径一字不动**：
11 段 / 甲 11 / E 5 / C 6 / base=`git:8f3864f3` / `_BASELINE_PINS` 与 `_AUX_BASELINE_PINS` 全不变。
**重采口令**：`python tests/_u1d2_triggers_gen.py --emit-aux`（引擎侧删面后 aux 不再幂等）。

跑法（真仓布局；`GWEN_HOST_DIR` = 宿主壳根）
------------------------------------------
    set GWEN_FRAMEWORK_DIR=<引擎仓>
    set GWEN_HOST_DIR=<宿主壳根>
    python tests/_u1d2_triggers_gen.py --check

四档命令
--------
    python tests/_u1d2_triggers_gen.py --check        # 只自检（§1.2 三条），不改文件
    python tests/_u1d2_triggers_gen.py --emit-frozen  # 生成 _FROZEN_TEXT + _PIN（红基线档）
    python tests/_u1d2_triggers_gen.py --emit-live    # 实现改完后重生成 _PIN["live"]（落档）
    python tests/_u1d2_triggers_gen.py --emit-aux     # 只重生成 _PIN["aux"]

E/C 分类（§2.3）
----------------
* **E**（预期不变，5 段）：`equip._known_engine_events` · `food_proc._map_event` ·
  `food_proc.food_trigger_decls` · `food_proc.food_period_decl` · `worldboss.wb_gm_dmg_mult`
  （★ 2026-09-26 2a：`equip.map_event` 已移出冻结 ⇒ 本栏 6 → 5）
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
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(_HERE)
WORK_ROOT = os.path.dirname(PKG_ROOT)
LANE_ROOT = os.path.dirname(WORK_ROOT)
BASE_PKG = None            # ★ 由文件末尾的 _resolve_base_pkg() 解析（改动前基线副本）
BASE_SOURCE = "unresolved"
TEST_FILE = os.path.join(_HERE, "test_u1d2_triggers_frozen.py")

BEGIN = "# >>> _u1d2_triggers_gen (auto) >>>"
END = "# <<< _u1d2_triggers_gen (auto) <<<"

#: 11 段（文件 · 符号），**顺序即门禁内键序**。
#: ★ 2026-09-26 2a：`content/mech/equip.py::map_event` 移出（退出冻结，见 2a 登记）。
SEGMENTS = [
    ("content/mech/equip.py", "_known_engine_events"),
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

#: `design/U1-D2_FROZEN_GATE.md` §1.4 那份 74 段基线里属于本门禁的 **11 条**（全 64 位）。
#: ★ 2026-09-26 2a：`equip.map_event` 那条随该段退出冻结一并移出（不再作判据）。
#: 生成器 `--check` 拿它交叉核对 —— 双向独立来源（设计稿 vs `base/pkg` 切片）必须一致。
_BASELINE_PINS = {
    "content/mech/equip.py::_known_engine_events":
        "cd81e2e7c9da6719d0f609a5afb6b5e3025afb90e6296abf96ff837edfbbfbbf",   # 134-140  273 字符
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

#: 基线（改动前）**文件面**指纹 —— 4 张数据表（判据 9：数据面零改动）+ 装配契约
#: （判据 10：六步顺序/保险丝未变）+ 4 个源文件整文件基线。
#: ★ 与切片 pin 一起构成 base 判据（全指纹）；与门禁 `_PIN["aux"]` 的对应项
#:   交叉核对（自检⑤，双向独立来源必须一致）。
_AUX_BASELINE_PINS = {
    "data:content/mech/we_data.py":
        "111ea69b3da481660ebc6ff2807a57935fbf53163ef02baba17f85a55c39d9fe",
    "data:content/data/affixes.json":
        "611a8d578e3b2cb7f9888e9215bc40dbbe92af81de404535a8494acee3710aee",
    "data:content/data/legendary_effects.json":
        "4f5b2cf476b09880e49121acf186a72893164e56c03ea087946ac61bd79dd51a",
    "data:content/data/food_effects.json":
        "4888c26020b5fbb4d5abe2b0b497c6b7ce396d8850cd02f98a9b4353e7b76400",
    "contract:content/apply.py":
        "28f97caa30ab3dcf689e7d91f935a08b3bcce45a56204ddee2d2789473bbd5f4",
    "src_base:content/mech/equip.py":
        "61c2e8e3b453c2f8fa50e3c67986a26ca59f9ecc11f34c79ca4b4e6224cbff18",
    "src_base:content/mech/food_proc.py":
        "caca7c1116448006d298fa5fb94b13e4fd087c01c8b51d276a41c94eae7fe998",
    "src_base:content/mech/team_procs.py":
        "50d3f1e78ba263bb7a873066e4da1f34df4e995c6ee9aa2d7b6f02e61433bca4",
    "src_base:content/mech/worldboss.py":
        "59228a4ee297917cc7c98c1ea39054893ad9035069f4ff673e52fd4e9b11237e",
}

#: E 栏里**基线后登记过的跨线改写**：base 切片 → 活实现文本只允许差这些机械替换。
#: 自检⑥ 逐条证明 `改写(base 切片) == 活实现文本`（**逐字节**），并钉住
#: 「条数恒 1 / old_base == 设计稿基线 / 只能落在 E 栏」—— 判据只加强，不放宽。
LIVE_DIVERGENCE = {
    "content/mech/equip.py::_known_engine_events": {
        "old_base": "cd81e2e7c9da6719d0f609a5afb6b5e3025afb90e6296abf96ff837edfbbfbbf",
        "rewrites": (("from saintess_engine.battle.", "from ext_combat.battle."),),
        "commit": "61a2d93",
        "date": "2026-09-23",
        "why": "包栈重构第 2 批：`battle` 从 `saintess_engine/` 搬进扩展包 `ext_combat/`"
               "（import 面搬迁，行为逐字不变）",
    },
}

#: base 树**必须落盘**的文件（切片源 + aux 的文件面：4 数据表 + 装配契约）
BASE_RELS = tuple(sorted({rel for rel, _sym in SEGMENTS} | {
    "content/mech/we_data.py", "content/data/affixes.json",
    "content/data/legendary_effects.json", "content/data/food_effects.json",
    "content/apply.py",
}))

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
def slice_source_text(src: str, symbol: str, where: str = "<text>") -> str:
    """从源码**文本**里切出 `symbol` 的**整段源码文本**（含装饰器，保留原行尾）。

    与 `inspect.getsource` 逐字节一致（生成时对全部 11 段当面证明）。
    """
    tree = ast.parse(src)
    hits = [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == symbol]
    if len(hits) != 1:
        raise SystemExit("切不出来：%s 里 `def %s` 有 %d 个（期望 1）"
                         % (where, symbol, len(hits)))
    node = hits[0]
    lo = min([d.lineno for d in node.decorator_list] + [node.lineno])
    return "".join(src.splitlines(True)[lo - 1:node.end_lineno])


def slice_source(path: str, symbol: str) -> str:
    """从**文件**里切（= 读文本 + `slice_source_text`）。"""
    with open(path, encoding="utf-8") as fh:
        return slice_source_text(fh.read(), symbol, where=path)


def key_of(relpath: str, symbol: str) -> str:
    return "%s::%s" % (relpath, symbol)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
def _dir_reader(root):
    """目录读口：包内相对路径 → 文件字节。"""
    def read(rel):
        with open(os.path.join(root, *rel.split("/")), "rb") as fh:
            return fh.read()
    return read


def _git_reader(rev):
    """git 读口（**只读**命令 `git show`）：包内相对路径 → 该提交里的文件字节。"""
    def read(rel):
        return subprocess.run(["git", "-C", PKG_ROOT, "show", "%s:%s" % (rev, rel)],
                              capture_output=True).stdout
    return read


def _matches_baseline(read) -> bool:
    """候选 base 的**全基线指纹**是否全中：`_BASELINE_PINS`（11 段切片 sha256）
    **＋** `_AUX_BASELINE_PINS`（9 个基线文件 sha256）。

    ★ 2026-09-26：旧口径只比 12 段切片 ⇒ 命中 `e4dccb4e`（切片对得上，`content/apply.py`
    是另一版）⇒ aux 生成不出正确值、E 栏自检必红。全指纹口径与「改动前基线」一一对应
    （当前唯一命中 `8f3864f`）。
    """
    try:
        cache: dict = {}
        for relpath, symbol in SEGMENTS:
            want = _BASELINE_PINS.get(key_of(relpath, symbol))
            if want is None:
                return False
            if relpath not in cache:
                cache[relpath] = read(relpath).decode("utf-8")
            if sha256_text(slice_source_text(cache[relpath], symbol)) != want:
                return False
        for key, want in _AUX_BASELINE_PINS.items():
            if sha256_bytes(read(key.split(":", 1)[1])) != want:
                return False
        return True
    except Exception:                                            # noqa: BLE001
        return False


def _stage_base_tree(rev: str) -> str:
    """把该提交的 `BASE_RELS` 整棵落到临时目录（只读 `git show`，不碰工作区）。"""
    tmp = tempfile.mkdtemp(prefix="u1d2t_base_")
    root = os.path.join(tmp, "pkg")
    reader = _git_reader(rev)
    for rel in BASE_RELS:
        dst = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(reader(rel))
    return root


def _resolve_base_pkg():
    """改动前基线副本 —— ① `GWEN_U1D2_BASE_PKG` → ② `<lane>/base/pkg` → ③ `<pkg>/.u1d2_base/pkg`
    → ④ **git 历史回溯**（最近 60 个改动过 `BASE_RELS` 的提交里找「全基线指纹」全中的版本；
    命中后把 `BASE_RELS` 整棵落盘 —— 切片与 aux 文件 sha 都要用它）。

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
            if _matches_baseline(_dir_reader(path)):
                return path, tag
            return path, tag + "(baseline-mismatch)"
    try:
        gd = os.path.join(PKG_ROOT, ".git")
        if os.path.isdir(gd) or os.path.isfile(gd):
            revs = subprocess.run(["git", "-C", PKG_ROOT, "log", "--format=%H", "-n", "60",
                                   "--", *BASE_RELS],
                                  capture_output=True, text=True).stdout.split()
            for rev in revs:
                if not _matches_baseline(_git_reader(rev)):
                    continue
                root = _stage_base_tree(rev)
                if _matches_baseline(_dir_reader(root)):          # 落盘后回读复核
                    return root, "git:%s" % rev[:8]
    except Exception as exc:                                     # noqa: BLE001
        print("[gen] ⚠️ git 回溯失败：%r" % (exc,))
    return None, "none"


def _no_base_msg() -> str:
    return ("❌ 找不到改动前基线（base/pkg）—— 生成器**拒绝执行**（fail-closed，不静默降级）。\n"
            "   解析顺序：GWEN_U1D2_BASE_PKG → <lane>/base/pkg → <pkg>/.u1d2_base/pkg → git 历史回溯\n"
            "   判据：**全基线指纹**全中（11 段切片 sha256 ＋ `_AUX_BASELINE_PINS` 9 个文件 sha256）\n"
            "   启用方式：GWEN_U1D2_BASE_PKG=<含 content/mech/worldboss.py 的 pkg 目录>")


def _has_engine(root: str) -> bool:
    """引擎根判据（与 `tests/_paths.py::_has_engine` 同源）。"""
    return os.path.isfile(os.path.join(root, "saintess_engine", "package.py"))


def live_engine_root() -> str:
    """**活引擎**根 —— `GWEN_FRAMEWORK_DIR` 优先 → 本包的祖父（真仓布局）。

    ★ 2026-09-26：aux 的 `engine:` 两项读它（真仓布局没有「基线引擎副本」；
    门禁 `test_aux` 比对的就是活引擎 ⇒ 生成器必须从同一个源取，口径才单一）。
    """
    tried = []
    env = (os.environ.get("GWEN_FRAMEWORK_DIR") or "").strip()
    if env:
        tried.append(("GWEN_FRAMEWORK_DIR=%s" % env, env))
    tried.append(("本包祖父", LANE_ROOT))
    for _label, root in tried:
        if _has_engine(root):
            return root
    raise SystemExit("❌ 找不到活引擎根（aux 的 `engine:` 项读它）：\n    %s"
                     % "\n    ".join("%s -> %s" % (lab, r) for lab, r in tried))


def frozen_slices() -> dict:
    """**base 切片**（改动前基线原文）—— 只用于基线核对（自检④）；
    门禁真正 exec 的「旧实现」文本见 `frozen_texts()`。"""
    if BASE_PKG is None:
        raise SystemExit(_no_base_msg())
    out = {}
    for relpath, symbol in SEGMENTS:
        out[key_of(relpath, symbol)] = slice_source(
            os.path.join(BASE_PKG, *relpath.split("/")), symbol)
    return out


def frozen_texts() -> dict:
    """门禁**真正 exec** 的「旧实现」文本 = base 切片 + 登记过的跨线改写（`LIVE_DIVERGENCE`）。

    ★ 2026-09-26：`equip._known_engine_events` 的活实现文本比 base 切片多一条 import
    搬迁（`saintess_engine.battle` → `ext_combat.battle`）⇒ 直接写 base 切片会让门禁拿
    「搬迁前那份」当旧实现。登记改写把两种 import 面拉到同一可执行面；改写**逐字节**
    可证（自检⑥），登记表外的任何差异都会报红。
    """
    out = frozen_slices()
    for key, div in LIVE_DIVERGENCE.items():
        text = out[key]
        for old, new in div["rewrites"]:
            text = text.replace(old, new)
        out[key] = text
    return out


def aux_pins() -> dict:
    """数据面 / 装配契约 / 源文件基线指纹 —— **读 base**（改动前基线）产出期望值；
    引擎侧两项 —— **读活引擎**（`live_engine_root()`：真仓布局没有基线引擎副本，
    门禁 `test_aux` 比对的就是活引擎）。
    """
    if BASE_PKG is None:
        raise SystemExit(_no_base_msg())
    out = {}
    for rel in DATA_RELS:
        out["data:" + rel] = sha256_file(os.path.join(BASE_PKG, *rel.split("/")))
    for rel in CONTRACT_RELS:
        out["contract:" + rel] = sha256_file(os.path.join(BASE_PKG, *rel.split("/")))
    for rel in SRC_RELS:
        out["src_base:" + rel] = sha256_file(os.path.join(BASE_PKG, *rel.split("/")))
    eng = live_engine_root()
    for rel in ENG_RELS:
        p = os.path.join(eng, *rel.split("/"))
        out["engine:" + rel] = sha256_file(p) if os.path.isfile(p) else "<missing>"
    return out


def _boot_work_pkg():
    """把包根 / tests / shim / 引擎根 / 宿主壳根摆进 `sys.path`，并兜底沙箱环境变量。

    ★ 2026-09-26：旧「工作区布局」（`<lane>/work/{pkg,eng,host}`）随包并入引擎仓
    （`<引擎仓>/games/orlandia`）已不存在 ⇒ 兜底值改真仓布局：
      · 引擎根 = 本包的祖父（判据同 `_paths._has_engine`）
      · 宿主壳根**不猜**：由外层给 `GWEN_HOST_DIR`（与 `_e5_pairs.py` / 宿主跑器同口径），
        缺失时 `_paths` 醒目报错 —— 不静默装绿
      · 私有库落系统临时目录（`<lane>/out` 在真仓布局下不存在）
    """
    if not (os.environ.get("GWEN_FRAMEWORK_DIR") or "").strip() and _has_engine(LANE_ROOT):
        os.environ["GWEN_FRAMEWORK_DIR"] = LANE_ROOT
    db = os.path.join(tempfile.gettempdir(), "gwen_test_u1d2_L6", "test_u1d2_L6.db")
    os.makedirs(os.path.dirname(db), exist_ok=True)
    os.environ.setdefault("GWEN_GAME_DB", db)
    os.environ.setdefault("GWEN_TEST_MODE", "1")
    os.environ.setdefault("PYTHONUTF8", "1")
    shim = os.path.join(_HERE, "shim_astrbot")
    for p in (shim, _HERE, PKG_ROOT,
              os.environ.get("GWEN_FRAMEWORK_DIR") or "",
              os.environ.get("GWEN_HOST_DIR") or ""):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    import _paths                                                        # noqa: F401


def _modname_of(relpath: str) -> str:
    return "content." + relpath.split("/", 1)[1][:-3].replace("/", ".")


def live_object(relpath: str, symbol: str):
    """活模块里的对象（本门禁 11 段全是模块级函数 → 直取）。"""
    _boot_work_pkg()
    mod = importlib.import_module(_modname_of(relpath))
    return getattr(mod, symbol, None)


def _live_text(relpath: str, symbol: str):
    """活实现源码文本（`inspect.getsource`，与门禁取件同一口径）；取不到 → None。"""
    import inspect
    obj = live_object(relpath, symbol)
    return None if obj is None else inspect.getsource(obj)


def live_pins() -> dict:
    out = {}
    for relpath, symbol in SEGMENTS:
        text = _live_text(relpath, symbol)
        out[key_of(relpath, symbol)] = None if text is None else sha256_text(text)
    return out


def self_check(*, with_live=True) -> list:
    """§1.2 四条 + 两条加强：⑤ aux 基线 9 条与门禁文件交叉核对、⑥ 登记跨线改写逐字节可证。

    冻结侧 = `frozen_texts()`（base 切片 + 登记改写）；base 只用于基线核对（④）。
    """
    lines = []
    base = frozen_slices()
    frozen = frozen_texts()
    if len(base) != 11:
        raise SystemExit("自检①失败：切片数 = %d（期望 11）" % len(base))
    lines.append("  ① 段数 = %d（期望 11）" % len(base))

    for key, text in frozen.items():
        try:
            ast.parse(text)
        except SyntaxError as exc:
            raise SystemExit("自检②失败：%s 切片不能 ast.parse：%s" % (key, exc))
        n = text.count("def %s(" % key.split("::")[1])
        if n != 1:
            raise SystemExit("自检②失败：%s 里 `def %s(` 出现 %d 次（期望 1）"
                             % (key, key.split("::")[1], n))
    lines.append("  ② 11 段切片全部 ast.parse 可编译")

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

    if len(_BASELINE_PINS) != 11:
        raise SystemExit("自检④失败：内嵌基线 11 条，实际 %d 条" % len(_BASELINE_PINS))
    mismatch = [k for k, want in _BASELINE_PINS.items()
                if sha256_text(base.get(k, "")) != want]
    if mismatch:
        raise SystemExit("自检④失败：与 design/U1-D2_FROZEN_GATE.md §1.4 基线不一致：%s"
                         % ", ".join(mismatch))
    lines.append("  ④ 11 条冻结 sha256 == `FROZEN_GATE.md` §1.4 基线（全 64 位）")

    if len(_AUX_BASELINE_PINS) != 9:
        raise SystemExit("自检⑤失败：内嵌 aux 基线 9 条，实际 %d 条" % len(_AUX_BASELINE_PINS))
    cur_aux = _current_pin().get("aux") or {}
    amiss = [k for k, want in _AUX_BASELINE_PINS.items() if str(cur_aux.get(k)) != want]
    if amiss:
        raise SystemExit("自检⑤失败：aux 基线 9 条 ≠ 门禁 `_PIN['aux']` 对应项：%s"
                         % ", ".join(amiss))
    lines.append("  ⑤ 9 条 aux 基线（4 数据 + 1 契约 + 4 源文件）== 门禁 `_PIN['aux']`（交叉核对）")

    if with_live:
        live = live_pins()
        div_bad = []
        for key, div in LIVE_DIVERGENCE.items():
            if CLASS.get(key) != "E":
                div_bad.append("%s 不在 E 栏" % key)
            if div.get("old_base") != _BASELINE_PINS.get(key):
                div_bad.append("%s 的 old_base ≠ 设计稿基线" % key)
            text = base[key]
            for old, new in div.get("rewrites", ()):
                text = text.replace(old, new)
            if text != _live_text(*key.split("::")):
                div_bad.append("%s 改写(base 切片) ≠ 活实现文本" % key)
        if len(LIVE_DIVERGENCE) != 1 or div_bad:
            raise SystemExit("自检⑥失败（登记跨线改写恒 1 条、逐字节可证）：%s"
                             % ("; ".join(div_bad) or "条数 ≠ 1"))
        lines.append("  ⑥ 登记过的跨线改写 %d 条：改写(base 切片) == 活实现文本（逐字节）"
                     % len(LIVE_DIVERGENCE))
        bad = [k for k, cls in CLASS.items()
               if cls == "E" and live.get(k) != sha256_text(frozen[k])]
        if bad:
            raise SystemExit("自检①失败：E 栏段「冻结文本（base + 登记改写）≠ inspect.getsource(活实现)」：%s"
                             % ", ".join(bad))
        lines.append("  ① E 栏冻结文本 == inspect.getsource(活实现)（%d 段）"
                     % sum(1 for v in CLASS.values() if v == "E"))
    else:
        lines.append("  ① 跳过（--no-live）")
    return lines


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
    frozen = frozen_texts()
    pin = _current_pin()
    pin["phase"] = phase
    pin["frozen"] = {k: sha256_text(v) for k, v in frozen.items()}
    pin["live"] = live if live is not None else pin["live"]
    if aux is not None:
        pin["aux"] = aux
    _write_region(_render(frozen, pin))


def _emit_frozen() -> None:
    print("【--emit-frozen】冻结 11 段（base/pkg）+ 红基线 live pin + aux 指纹")
    print("  ⚠ 只在红基线之前跑一次（那时 base == work）：本档自证「冻结文本 == 活实现」")
    frozen = frozen_texts()
    live = live_pins()
    bad = []
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        got = _live_text(relpath, symbol)
        if got is None or sha256_text(got) != sha256_text(frozen[k]):
            bad.append(k)
    if bad:
        raise SystemExit("红基线自证失败：冻结文本（base 切片 + 登记改写）≠ inspect.getsource(活实现)：%s"
                         "\n    （本档只在改动前跑；已过红基线请用 --emit-live）"
                         % ", ".join(bad))
    _emit("baseline", live=live, aux=aux_pins())
    for relpath, symbol in SEGMENTS:
        k = key_of(relpath, symbol)
        print("  [%s/%s] %-52s frozen=%s live=%s"
              % (CLASS[k], tier_of(frozen[k]), k, sha256_text(frozen[k])[:12], live[k][:12]))
    print("  （红基线自证：11/11 段 冻结文本 == inspect.getsource(活实现)）")


def _emit_live() -> None:
    print("【--emit-live】重生成 `_PIN[live]`（落档）+ E/C 断言")
    frozen = frozen_texts()
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
        raise SystemExit("E/C 分类断言失败（共 %d 条）：\n    %s"
                         % (len(bad), "\n    ".join(bad)))
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
    print("  live eng = %s" % live_engine_root())
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
