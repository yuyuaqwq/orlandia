# -*- coding: utf-8 -*-
"""U1-I8（= U1-I4 L3）门禁①·生成器 —— 30 段冻结字面量 + 双 sha256 `_PIN`。

**它做什么**

从 `base/pkg/content/dialogue.py`（10 段）+ `base/pkg/content/dialogue_conds.py`（20 段）
按 `U1-I4_FROZEN_GATE.md` §1.2 的 **ast 行切片**口径逐行切出 30 段旧实现文本，
算 sha256，再把它们**自动写进**门禁文件 `test_u1i4_dialogue_frozen.py` 的
`# >>> GENERATED` / `# <<< GENERATED` 之间（那段里的每个字节都由本脚本产出）。

**为什么冻结侧读 `base/` 而不是 `work/`**

`base/` = 改动前基线副本（本线唯一取旧实现字面量的来源）。冻结的定义就是
「改动前的原文」；读 `work/` 会在实现线改完之后悄悄把冻结侧也换成新实现
（= `x == x` 的假绿）。

**自检（`--check` 与新生成时都会跑；不通过就拒绝产出）**

1. 30 段切片 sha256 **全等** `U1-I4_FROZEN_GATE.md` §1.4 的 `_BASELINE_PINS` 全表
   （逐段交叉核对；`_STORY_PREFIX` 是设计稿 §1.4 表里没列的**第 10 段**，单独登记基线）。
2. **E 栏**「预期逐字节不变」的段：`sha256(base 切片) == sha256(inspect.getsource(work 同名对象))`
   —— 这条不成立就是**切片口径错了**（或实现线越界改了不该改的段），先修口径。
3. 每段 `ast.parse` 可编译（用**真文件名**编译，`type_params` 等语法糖不退化）。
4. 每段文本里 `def <symbol>(` 恰好出现 **1** 次（防切片越界吞掉后面的函数）。
5. 段序与 §1.4 的段落表一致；总段数 == 30。

**跑法**

```
python work/pkg/tests/_u1i4_dialogue_gen.py --check        # 只自检 + 打印，不写任何文件
python work/pkg/tests/_u1i4_dialogue_gen.py --emit-frozen  # 写「30 段冻结字面量 + _PIN」
python work/pkg/tests/_u1i4_dialogue_gen.py --emit-live    # 实现线改完后重生成 _PIN["live"]
python work/pkg/tests/_u1i4_dialogue_gen.py                # = --emit-frozen --emit-live
```

生成器**不 import 被测包**（frozen 侧纯文本）；只有 E 栏自检那一步用
`inspect.getsource`（需要 import `content.dialogue` / `content.dialogue_conds`，
但**只读源码文本、不执行对话判定**）。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import os
import sys

# ───────────────────────────────────────────────────────── 位置
_HERE = os.path.dirname(os.path.abspath(__file__))              # <pkg>/tests
PKG_ROOT = os.path.dirname(_HERE)                               # <pkg>
LANE_ROOT = os.path.dirname(os.path.dirname(PKG_ROOT))          # <lane>（工作区布局；真仓里 = 包根的父父）


def _resolve_base_pkg():
    """改动前基线副本（`base/pkg`）—— **四级解析，找不到就醒目 SKIP**（不许把跳过装成绿）。

    ① `GWEN_U1I4_BASE_PKG` 环境变量（显式指定，最高优先）
    ② 工作区布局 `<lane>/base/pkg`（本线原口径；`<lane>/work/pkg` 是工作副本）
    ③ 仓内可选基线 `<pkg>/.u1i4_base/pkg`（真仓里要重跑 `--emit-*` 时手工放一份）
    ④ **git 历史自动回溯**：在 `<pkg>` 里从最近 20 个改动过 `content/dialogue.py` 的提交里
       找一个「31 段切片 sha256 全等设计 pin」的版本，落到临时目录（真仓常见路径）
    ⇒ 都失败：返回 `(None, "none")`。依赖 base 的检查会**逐条打印 SKIP**，`--emit-*` 直接报错退出。
    """
    candidates = []
    env = os.environ.get("GWEN_U1I4_BASE_PKG")
    if env:
        candidates.append(("env", env))
    candidates.append(("lane", os.path.join(LANE_ROOT, "base", "pkg")))
    candidates.append(("repo", os.path.join(PKG_ROOT, ".u1i4_base", "pkg")))
    for tag, path in candidates:
        if os.path.isfile(os.path.join(path, "content", "dialogue.py")):
            return path, tag
    # ④ git 回溯
    try:
        import subprocess
        import tempfile
        if os.path.isdir(os.path.join(PKG_ROOT, ".git")) or os.path.isfile(os.path.join(PKG_ROOT, ".git")):
            revs = subprocess.run(["git", "-C", PKG_ROOT, "log", "--format=%H", "-n", "20",
                                   "--", "content/dialogue.py", "content/dialogue_conds.py"],
                                  capture_output=True, text=True).stdout.split()
            tmp = tempfile.mkdtemp(prefix="u1i4_base_")
            for rev in revs:
                ok = True
                for rel in ("content/dialogue.py", "content/dialogue_conds.py"):
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
    """该候选 base 的 31 段切片是否全等设计 pin（`_BASELINE_PINS` + `_EXTRA_FROZEN_PIN`）。"""
    try:
        dlg = os.path.join(path, "content", "dialogue.py")
        cnd = os.path.join(path, "content", "dialogue_conds.py")
        for key, fname, symbol, _kind in SEGMENTS:
            want = _EXTRA_FROZEN_PIN if symbol == "_STORY_PREFIX" else _BASELINE_PINS.get(
                "content/%s::%s" % (fname, symbol))
            if want is None:
                return False
            got = hashlib.sha256(slice_source(dlg if fname == "dialogue.py" else cnd, symbol)
                                 .encode("utf-8")).hexdigest()
            if got != want:
                return False
        return True
    except Exception:                                            # noqa: BLE001
        return False


BASE_PKG, BASE_SOURCE = None, "unresolved"   # 真值在 SEGMENTS 定义之后解析（见下）
HAVE_BASE = False                            # （此块只为占位，避免「先用后定义」）
LIVE_DIALOGUE = os.path.join(PKG_ROOT, "content", "dialogue.py")
LIVE_CONDS = os.path.join(PKG_ROOT, "content", "dialogue_conds.py")

GATE_PATH = os.path.join(_HERE, "test_u1i4_dialogue_frozen.py")

BEGIN = "# >>> GENERATED: _FROZEN_DP / _FROZEN_DC / _FROZEN_EXTRA / _PIN  (由 _u1i4_dialogue_gen.py 产出；手改即红)"
END = "# <<< GENERATED"

#: `U1-I4_FROZEN_GATE.md` §1.4 的基线全表（93 段里属于门禁①的 29 段；`_STORY_PREFIX` 另列）。
_BASELINE_PINS = {
    "content/dialogue.py::_read_domain": "4cbe68fb2a39091716a522948ef5a2882d09a9914a83e34e8368a2b9bf6f64eb",
    "content/dialogue.py::_dialogues": "f49aeddf11c5042f4f7cccd45adf87f3a1762f3baa6cd7c9a64c94820a5174bc",
    "content/dialogue.py::_main_quests": "e271d0b6915c300b5fe99314be051dcd4d0f912871fbbce337f604384a4478d5",
    "content/dialogue.py::get_dialogue": "5c5de633222f1b50f74c923aa630c5d3ece74d04ab948afc610f330b293a8b5c",
    "content/dialogue.py::dialogue_node": "082a2ebe53088cd7810a464e064b5171764b726aeafffca9a8be462f6ab748d6",
    "content/dialogue.py::check_need": "0fcbd19aaa3ee2a87edd0fe4a398b6b4926d2a4015e7a454059d2c5bf86eb506",
    "content/dialogue.py::visible_options": "afb3dabf30b508752e5e26b5467321aace9f857064a6879d90f92e18fbbc96e2",
    "content/dialogue.py::_story_to_line": "d9cb0c4b54a3414dcc3372cee0b12478e087d712caeaa434b833edbcd5f04be1",
    "content/dialogue.py::node_text": "ee370b164bbbc0d3a530f96d51c721be080422f872009e3cbed22bd04c84dd8b",
    "content/dialogue.py::is_end": "31c82ce6c5c03536c07c00feee6c21e4056fe38b4fa1bc82e7e13514be5f37b9",
    "content/dialogue_conds.py::_read_domain": "c93e7a0c9878f1166aff13380f6d1fab475a5eecfb44222b7a29d0d813fe5708",
    "content/dialogue_conds.py::_main_quests": "4a0fee274d5da62574840cea84508640dc27831fc3eace55fa0d1a717d3db0c1",
    "content/dialogue_conds.py::register": "bdbc062f40ae9e366d2d0685540d12669167cda57035787f9e26f1c24d914a62",
    "content/dialogue_conds.py::_quest_state": "04766d5f14600c1755037bdbcbeae4430cb0caa2ab210a1b6659b764b57bc160",
    "content/dialogue_conds.py::_c_quest_done": "016c69f887d95a45ccbf27503e72dbfb6d599a9d12bb27ee28923978c8b1de9c",
    "content/dialogue_conds.py::_c_not_quest_done": "168c8c2b7c27e664e716be0192565ec5129f0b1e0d58498c938c63341bc7a39b",
    "content/dialogue_conds.py::_c_quest_active": "34c0959d615af83f3eb2c4ff196d650a13f81cd97dd95946de4e260232e27942",
    "content/dialogue_conds.py::_c_quest_pending": "861a91ac549fa66a38dbb4fd258f74d8783585e1200831f95b9569a105f55b8b",
    "content/dialogue_conds.py::_c_quest_ready": "e36baf63f0afa40f2d3c4d41918d2975bbda435c8f9eaaf9563c3e9e053b8c5e",
    "content/dialogue_conds.py::_c_side_ready": "c5ef258add6730dd0ca55e01035a79e714b28da4f2b9620a612347fba05d3a0b",
    "content/dialogue_conds.py::_c_side_available": "f5dce3bcf9c279a82f454c78d683960c89498db1fd5cfb58ab6abc8ea1991a04",
    "content/dialogue_conds.py::_c_quest_any_active": "4535aa0de397cf73fa129b6ebc00acdc13087644f5b118bf3a34f0faf5bdb304",
    "content/dialogue_conds.py::_c_is_novice": "dc1b97d17fdc59d211c458de70494647185e0669b984c13fcd0974cd04dba08e",
    "content/dialogue_conds.py::_c_not_novice": "ccef729b0ca2ab76be03b4ef545d64688b8c6c7377f9fff78f949f6345de0f7a",
    "content/dialogue_conds.py::_c_class_any": "1def7f38b1f0c0569bde9aec550247e3130a080d2cfe3d693640939503753d24",
    "content/dialogue_conds.py::_c_race_is": "d0319070d89d468f853829ed52ddd596249ae8549be962b7478270ce74f96862",
    "content/dialogue_conds.py::_c_hidden_unlocked": "13ca3f8f7b2e1a362e3726adb12a60068add2c52b7a057a9163c8a0dc4282d20",
    "content/dialogue_conds.py::_c_hidden_current": "1933a5ac5aea4cfddb13df0e859dad542c0fbb3c7c6db68230a318d3f88bf301",
    "content/dialogue_conds.py::_c_not_hidden_current": "72902621dad02007ce166bb6efe75207309f59a90e9a2d62f2cb4a458d6e111e",
    "content/dialogue_conds.py::_c_evolve_ready": "dd58a307f122163846e19c61a22bba22733c13358ee23a37b6c6546137a3c8e2",
}
#: 设计稿 §1.4 表里**没列**的第 10 个 `dialogue.py` 段（段数 10 的差值就是它）
#: = `base/pkg/content/dialogue.py:155` `_STORY_PREFIX = re.compile(r"^[^：:]{1,20}[：:]\s*")`（51 字符）。
_EXTRA_FROZEN_PIN = "913610be2fdf91816ba44679e736fae60b60544f9b49c4ae93d2d4232cba9dd8"

#: 段序（= `U1-I4_FROZEN_GATE.md` §1.4 的行号顺序）与切片列。
#: (`key`, `file`, `symbol`, `kind`)；kind: "def" = 函数/类，含装饰器行；"assign" = 模块级赋值。
SEGMENTS = (
    ("content/dialogue.py::_read_domain", "dialogue.py", "_read_domain", "def"),
    ("content/dialogue.py::_dialogues", "dialogue.py", "_dialogues", "def"),
    ("content/dialogue.py::_main_quests", "dialogue.py", "_main_quests", "def"),
    ("content/dialogue.py::get_dialogue", "dialogue.py", "get_dialogue", "def"),
    ("content/dialogue.py::dialogue_node", "dialogue.py", "dialogue_node", "def"),
    ("content/dialogue.py::check_need", "dialogue.py", "check_need", "def"),
    ("content/dialogue.py::visible_options", "dialogue.py", "visible_options", "def"),
    ("content/dialogue.py::_STORY_PREFIX", "dialogue.py", "_STORY_PREFIX", "assign"),
    ("content/dialogue.py::_story_to_line", "dialogue.py", "_story_to_line", "def"),
    ("content/dialogue.py::node_text", "dialogue.py", "node_text", "def"),
    ("content/dialogue.py::is_end", "dialogue.py", "is_end", "def"),
    ("content/dialogue_conds.py::_read_domain", "dialogue_conds.py", "_read_domain", "def"),
    ("content/dialogue_conds.py::_main_quests", "dialogue_conds.py", "_main_quests", "def"),
    ("content/dialogue_conds.py::register", "dialogue_conds.py", "register", "def"),
    ("content/dialogue_conds.py::_quest_state", "dialogue_conds.py", "_quest_state", "def"),
    ("content/dialogue_conds.py::_c_quest_done", "dialogue_conds.py", "_c_quest_done", "def"),
    ("content/dialogue_conds.py::_c_not_quest_done", "dialogue_conds.py", "_c_not_quest_done", "def"),
    ("content/dialogue_conds.py::_c_quest_active", "dialogue_conds.py", "_c_quest_active", "def"),
    ("content/dialogue_conds.py::_c_quest_pending", "dialogue_conds.py", "_c_quest_pending", "def"),
    ("content/dialogue_conds.py::_c_quest_ready", "dialogue_conds.py", "_c_quest_ready", "def"),
    ("content/dialogue_conds.py::_c_side_ready", "dialogue_conds.py", "_c_side_ready", "def"),
    ("content/dialogue_conds.py::_c_side_available", "dialogue_conds.py", "_c_side_available", "def"),
    ("content/dialogue_conds.py::_c_quest_any_active", "dialogue_conds.py", "_c_quest_any_active", "def"),
    ("content/dialogue_conds.py::_c_is_novice", "dialogue_conds.py", "_c_is_novice", "def"),
    ("content/dialogue_conds.py::_c_not_novice", "dialogue_conds.py", "_c_not_novice", "def"),
    ("content/dialogue_conds.py::_c_class_any", "dialogue_conds.py", "_c_class_any", "def"),
    ("content/dialogue_conds.py::_c_race_is", "dialogue_conds.py", "_c_race_is", "def"),
    ("content/dialogue_conds.py::_c_hidden_unlocked", "dialogue_conds.py", "_c_hidden_unlocked", "def"),
    ("content/dialogue_conds.py::_c_hidden_current", "dialogue_conds.py", "_c_hidden_current", "def"),
    ("content/dialogue_conds.py::_c_not_hidden_current", "dialogue_conds.py", "_c_not_hidden_current", "def"),
    ("content/dialogue_conds.py::_c_evolve_ready", "dialogue_conds.py", "_c_evolve_ready", "def"),
)
#: 降级模式下被跳过的检查（醒目打印用；缺 base 时 ≠ 通过）
SKIPPED = []

#: `dialogue_conds.py` 段的 exec 顺序（段表里它天然有序，此处只做显式声明）。
DC_ORDER = tuple(k for k, f, s, kd in SEGMENTS if f == "dialogue_conds.py")
#: `dialogue.py` 段的 exec 顺序。
DP_ORDER = tuple(k for k, f, s, kd in SEGMENTS if f == "dialogue.py")

#: 生成区里 `_FROZEN_DP` / `_FROZEN_DC` 的键 = 段符号名（去掉 `content/xxx.py::` 前缀）
DP_BARE = tuple(k.split("::", 1)[1] for k in DP_ORDER)
DC_BARE = tuple(k.split("::", 1)[1] for k in DC_ORDER)

#: 活侧「按段取源」的名字（config 块用得到；不写进冻结区）。
DP_FN_ORDER = tuple(n for n in DP_ORDER if n != "_STORY_PREFIX")

#: E 栏（`U1-I4_FROZEN_GATE.md` §2.3）：本批**不该动**的段 → 生成时断言 `frozen == live`。
#: = `dialogue.py` 的 `_read_domain` / `_dialogues` / `_main_quests` / `_story_to_line` / `_STORY_PREFIX`
#:   + `dialogue_conds.py` 全部 20 段。
E_KEYS = frozenset(
    set(k for k, f, s, kd in SEGMENTS
        if k in ("content/dialogue.py::_read_domain", "content/dialogue.py::_dialogues",
                 "content/dialogue.py::_main_quests", "content/dialogue.py::_story_to_line",
                 "content/dialogue.py::_STORY_PREFIX"))
    | set("content/dialogue_conds.py::" + s for s in DC_BARE)
)

#: C 栏：本批**会改**的段（`dialogue.py` 的对外 6 名）→ 生成时断言 `frozen != live`。
C_KEYS = frozenset((
    "content/dialogue.py::get_dialogue",
    "content/dialogue.py::dialogue_node",
    "content/dialogue.py::check_need",
    "content/dialogue.py::visible_options",
    "content/dialogue.py::node_text",
    "content/dialogue.py::is_end",
))

assert len(SEGMENTS) == 31, len(SEGMENTS)                         # 30 段 + `_STORY_PREFIX`（§1.4 表外）
assert len(E_KEYS) == 25, len(E_KEYS)      # 5（dialogue.py）+ 20（dialogue_conds.py）
assert len(C_KEYS) == 6, len(C_KEYS)
assert E_KEYS | C_KEYS == frozenset(k for k, *_ in SEGMENTS)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ───────────────────────────────────────────────────────── 切片（FROZEN_GATE §1.2）
def slice_source(path: str, symbol: str) -> str:
    """按 **ast 行号**切出模块级符号的原文（函数含装饰器行；保留原行尾）。

    口径逐字照 `U1-I4_FROZEN_GATE.md` §1.2；实测与 `inspect.getsource(同名对象)`
    逐字节相等（`--check` 的 E 栏自检就是这条的机器证明）。
    """
    with open(path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src, filename=path)
    node = None
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == symbol:
            node = n
            break
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            tgts = n.targets if isinstance(n, ast.Assign) else [n.target]
            if any(isinstance(t, ast.Name) and t.id == symbol for t in tgts):
                node = n
                break
    if node is None:
        raise KeyError("切片目标不在 %s 顶层：%s" % (path, symbol))
    lines = src.splitlines(True)
    lo = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])
    return "".join(lines[lo - 1:node.end_lineno])


def _slice_all() -> dict:
    out = {}
    for key, fname, symbol, kind in SEGMENTS:
        base_path = BASE_DIALOGUE if fname == "dialogue.py" else BASE_CONDS
        out[key] = slice_source(base_path, symbol)
    return out


# ───────────────────────────────────────────────────────── 活侧（inspect）
def _import_live():
    """import 活实现（只读源码；判定逻辑不执行）。"""
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import _paths  # noqa: F401  ← 包根/引擎根/宿主壳根装配
    from content import dialogue as live_dlg
    from content import dialogue_conds as live_conds
    return live_dlg, live_conds


def _live_sources():
    """30 段的活侧文本（与冻结侧**同一个切片口径**，但取 `work/pkg` 的文件）。"""
    live_dlg, live_conds = _import_live()
    out = {}
    for key, fname, symbol, kind in SEGMENTS:
        live_path = LIVE_DIALOGUE if fname == "dialogue.py" else LIVE_CONDS
        out[key] = slice_source(live_path, symbol)
    out["_LIVE_MODULES"] = (live_dlg, live_conds)
    return out


# ── base 解析（★ 必须在 `slice_source` 定义**之后**：`_base_matches_pins` 要用它做切片比对）──
BASE_PKG, BASE_SOURCE = _resolve_base_pkg()
HAVE_BASE = BASE_PKG is not None
BASE_DIALOGUE = os.path.join(BASE_PKG, "content", "dialogue.py") if HAVE_BASE else ""
BASE_CONDS = os.path.join(BASE_PKG, "content", "dialogue_conds.py") if HAVE_BASE else ""


# ───────────────────────────────────────────────────────── 自检
def self_check(verbose: bool = True) -> list:
    """跑 §1.2 的五条自检；返回违规列表（空 = 全过）。

    ★ 缺 base（`HAVE_BASE=False`）时：依赖 base 切片的检查**逐条记入 `SKIPPED` 并醒目打印**，
    **不算通过**（调用方据 `SKIPPED` 决定口径）。
    """
    bad = []
    if not HAVE_BASE:
        SKIPPED.extend([
            "① 段序 / 段数（需 base 切片）",
            "② 每段可编译 + 不吞下一段（需 base 切片）",
            "③ 冻结切片 sha256 == 设计 pin（需 base 切片）",
            "④ E/C 栏判定（base 切片 vs live）",
        ])
        if verbose:
            for s in SKIPPED:
                print("     ⏭️ SKIP %s" % s)
        return bad
    slices = _slice_all()
    if len(slices) != 31:
        bad.append("切片数 != 31（30 段 + `_STORY_PREFIX`）：%d" % len(slices))

    # ① 段序 / 段数
    if tuple(slices) != tuple(k for k, *_ in SEGMENTS):
        bad.append("段序与段表不一致")

    # ② 每段：可编译 + `def <symbol>(` 恰 1 次 + 不吞下一段
    src_cache = {}
    for key, fname, symbol, kind in SEGMENTS:
        seg = slices[key]
        path = BASE_DIALOGUE if fname == "dialogue.py" else BASE_CONDS
        try:
            compile(seg, path if kind == "def" else "<%s>" % symbol, "exec")
        except SyntaxError as e:
            bad.append("段 %s 编译失败：%s" % (key, e))
        if kind == "def":
            n_def = seg.count("def %s(" % symbol)
            if n_def != 1:
                bad.append("段 %s 里 `def %s(` 出现 %d 次（应恰 1）" % (key, symbol, n_def))
            if not seg.lstrip().startswith(("@", "def ", "async def ")):
                bad.append("段 %s 不是以 def/@decorator 开头" % key)
        if path not in src_cache:
            with open(path, encoding="utf-8") as f:
                src_cache[path] = f.read().splitlines(True)
        lines = src_cache[path]
        # 切片末行之后的那一行不能已经属于本段（防 end_lineno 越界）
        if kind == "def":
            last = seg.splitlines()[-1]
            if last.strip() and not last.startswith((" ", "\t")) and last.strip() not in (
                    "return False", "return True", "pass"):
                # 模块级 def 的末行必然缩进；不缩进 = 可能吞了下一个顶层符号
                bad.append("段 %s 末尾疑似吞掉下一段：%r" % (key, last[:60]))

    # ③ §1.4 基线哈希交叉核对
    pins = dict(_BASELINE_PINS)
    pins["content/dialogue.py::_STORY_PREFIX"] = _EXTRA_FROZEN_PIN
    for key, want in pins.items():
        got = _sha(slices[key])
        if got != want:
            bad.append("冻结哈希与设计稿 §1.4 基线不符：%s 实测 %s / 记录 %s" % (key, got, want))
    for key in slices:
        if key not in pins:
            bad.append("段 %s 没有基线哈希可交叉核对" % key)

    # ④ E 栏自检：frozen == live（**切片口径**的机器证明）
    live = _live_sources()
    live_dlg, live_conds = live.pop("_LIVE_MODULES")
    for key in sorted(E_KEYS):
        got_f = _sha(slices[key])
        got_l = _sha(live[key])
        if got_f != got_l:
            bad.append("E 栏段 %s 冻结 != 活实现（切片口径错 / 实现线越界改了不该改的段）" % key)
    # ⑤ C 栏提示（不判红：红基线阶段 C 栏就是相等的；改完之后才不等）
    changed = [k for k in sorted(C_KEYS) if _sha(slices[k]) != _sha(live[k])]
    if verbose:
        print("[gen] 段数            = %d" % len(slices))
        print("[gen] E 栏（预期不变） = %d 段，全部 frozen == live" % len(E_KEYS))
        print("[gen] C 栏（预期会变） = %d 段，当前 frozen != live 的有 %d 段 %s"
              % (len(C_KEYS), len(changed), sorted(changed)))
        print("[gen] 冻结哈希基线    = %d 段全部命中设计稿 §1.4" % len(pins))
    return bad


# ───────────────────────────────────────────────────────── 生成器文本工具
def _literal(text: str) -> str:
    """把段文本写成 Python 字面量（优先三引号原样；含三引号的行尾统一为 LF）。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    has_d = '"""' in text
    has_s = "'''" in text
    if not has_d:
        return 'r"""%s"""' % text
    if not has_s:
        return "r'''%s'''" % text
    raise ValueError("段文本同时含三单引号与三双引号，需换写法")


def _gen_region(slices: dict, live: dict, aux: dict) -> str:
    """产出 `_FROZEN_*` + `_PIN` 的整段生成文本（BEGIN/END 由调用方加）。"""
    lines = []
    w = lines.append

    def dump(name, order):
        w("%s = {" % name)
        for key in order:
            w("    # %s" % key)
            w("    %s: %s," % ("%r" % key.split("::", 1)[1], _literal(slices[key])))
        w("}")
        w("")

    dump("_FROZEN_DP", DP_ORDER)
    dump("_FROZEN_DC", DC_ORDER)
    w("_FROZEN_EXTRA = {")
    w("    # 设计稿 §1.4 没列的第 10 段（`dialogue.py` 段数 10 = 表里 9 段 + 本段）")
    w("    %r: %s," % ("content/dialogue.py::_STORY_PREFIX",
                       _literal(slices["content/dialogue.py::_STORY_PREFIX"])))
    w("}")
    w("")
    w("#: 冻结侧期望（生成时跑 `sha256(_FROZEN_*)`；跑门禁时逐段重算比对）")
    w("_PIN = {")
    w('    "frozen": {')
    for key, *_ in SEGMENTS:
        w("        %r: %r," % (key, _sha(slices[key])))
    w("    },")
    w('    "live": {')
    for key, *_ in SEGMENTS:
        w("        %r: %r," % (key, _sha(live[key])))
    w("    },")
    w('    "aux": {')
    for k in sorted(aux):
        w("        %r: %r," % (k, aux[k]))
    w('        "gate_self": "PLACEHOLDER",')
    w("    },")
    w("}")
    w("")
    w("#: 本文件（门禁本体）的自哈希 —— 去掉 gate_self 那一行后算；防「安全网自己被动过」")
    w('_GATE_SELF_SHA256 = "PLACEHOLDER"')
    w("")
    w("#: 冻结侧的段落表（段序 = 设计稿 §1.4 的行号序）")
    w("_SEGMENT_KEYS = (")
    for key, *_ in SEGMENTS:
        w("    %r," % key)
    w(")")
    w("_E_KEYS = (")
    for key in sorted(E_KEYS):
        w("    %r," % key)
    w(")")
    w("_C_KEYS = (")
    for key in sorted(C_KEYS):
        w("    %r," % key)
    w(")")
    return "\n".join(lines) + "\n"


def _splice(gate_text: str, region: str) -> str:
    """把 region 放进门禁文件的 BEGIN/END 之间。"""
    if BEGIN not in gate_text or END not in gate_text:
        raise RuntimeError("门禁文件里找不到 GENERATED 区域标记（%s / %s）" % (BEGIN, END))
    head, rest = gate_text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    return head + BEGIN + "\n" + region + END + tail


def _region_text(gate_text: str) -> str:
    head, rest = gate_text.split(BEGIN, 1)
    region, _ = rest.split(END, 1)
    return region


def _gate_self_sha(text: str) -> str:
    """门禁文件自哈希：丢掉 `gate_self` / `_GATE_SELF_SHA256` 两行后算。

    这两行是**自指**的（值等于文件的哈希），必须先排除才能收敛到不动点。
    """
    keep = [ln for ln in text.splitlines(True)
            if '"gate_self"' not in ln and "_GATE_SELF_SHA256" not in ln]
    return _sha("".join(keep))


def _extract_quoted(text: str, needle: str) -> str:
    """从 `text` 里取含 `needle` 的那一行的最后一个引号串（生成/检查都用同一口径）。"""
    for ln in text.splitlines():
        if needle in ln:
            parts = ln.split('"')
            if len(parts) >= 3:
                return parts[-2]
    return ""


# ───────────────────────────────────────────────────────── aux（数据面 / 存档面指纹）
def _aux_pins() -> dict:
    """§3-①②③⑧⑩ 的 aux 指纹（门禁①负责的那几条）。"""
    aux = {}
    # ① 会话键格式
    from content.persistence import world as W
    key = W.talk_state_key("g1", "1001")
    aux["talk_key"] = _sha(key)
    aux["talk_key_plain"] = key
    # ⑧ 数据面：39 棵树逐树规范化指纹
    import json as _json
    from content import dialogue as D
    trees = D._dialogues()
    per = []
    for tid in sorted(trees):
        tree = trees[tid]
        nodes = tree.get("nodes") or {}
        norm = {"start": tree.get("start"), "node_ids": list(nodes)}
        body = {}
        for nid in nodes:
            node = nodes[nid]
            if not isinstance(node, dict):
                body[nid] = {"__nonmapping__": repr(node)}
                continue
            opts = []
            for o in node.get("options") or []:
                opts.append({k: o.get(k) for k in
                             ("text", "next", "need", "action", "fail_next", "side_menu") if k in o}
                            | {"__keys__": list(o)})
            variants = []
            for v in node.get("texts") or []:
                variants.append({"__keys__": list(v), "need": v.get("need"), "text": v.get("text")})
            body[nid] = {"__keys__": list(node), "text": node.get("text"),
                         "text_from": node.get("text_from"), "texts": variants, "options": opts}
        norm["nodes"] = body
        per.append(_sha(_json.dumps(norm, ensure_ascii=False, separators=(",", ":"))))
    aux["trees_fp"] = _sha("|".join(per))
    aux["trees_count"] = str(len(per))
    # ⑩ 主线 (id,giver,story) 指纹
    mains = D._main_quests()
    aux["story_fp"] = _sha("|".join("%s\x1f%s\x1f%s" % (m.get("id"), m.get("giver"), m.get("story"))
                                    for m in mains))
    aux["story_count"] = str(len(mains))
    # ⑩ cond_specs.json 全文
    import hashlib as _h
    spec_path = os.path.join(PKG_ROOT, "content", "data", "cond_specs.json")
    with open(spec_path, "rb") as f:
        aux["cond_specs_fp"] = _h.sha256(f.read()).hexdigest()
    # 数据面计数（防「循环没跑」的假绿，门禁也复算一遍）
    n_nodes = sum(len((t.get("nodes") or {})) for t in trees.values())
    n_opts = sum(len((n.get("options") or [])) for t in trees.values()
                 for n in (t.get("nodes") or {}).values() if isinstance(n, dict))
    aux["trees_n"] = str(len(trees))
    aux["nodes_n"] = str(n_nodes)
    aux["opts_n"] = str(n_opts)
    return aux


# ───────────────────────────────────────────────────────── 入口
def _write_frozen(gate_now: str, region: str) -> tuple:
    """回填门禁自哈希到不动点（自指字段：排除自己那两行后哈希才收敛）。"""
    if '_GATE_SELF_SHA256 = "PLACEHOLDER"' not in region:
        raise RuntimeError("生成区里没有 `_GATE_SELF_SHA256` 占位符")
    spliced = _splice(gate_now, region)
    self_sha = _gate_self_sha(spliced)
    for _ in range(8):
        region2 = region.replace('_GATE_SELF_SHA256 = "PLACEHOLDER"',
                                 '_GATE_SELF_SHA256 = %r' % self_sha)
        region2 = region2.replace('"gate_self": "PLACEHOLDER"', '"gate_self": %r' % self_sha)
        spliced2 = _splice(gate_now, region2)
        got = _gate_self_sha(spliced2)
        if got == self_sha:
            return spliced2, got
        region, self_sha = region2, got
    raise RuntimeError("门禁自哈希回填未收敛")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="U1-I8 门禁①生成器（30 段冻结 + 双 sha256）")
    ap.add_argument("--check", action="store_true", help="只自检 + 打印，不写任何文件")
    ap.add_argument("--emit-frozen", action="store_true", help="写 30 段冻结字面量 + _PIN")
    ap.add_argument("--emit-live", action="store_true", help="重生成 _PIN[\"live\"]")
    ap.add_argument("--require-base", action="store_true",
                    help="缺 base/pkg 时直接退非零（禁止降级模式）")
    args = ap.parse_args(argv)

    print("=" * 74)
    print("U1-I8 门禁①生成器 —— 30 段冻结（base/pkg 切片）→ test_u1i4_dialogue_frozen.py")
    print("=" * 74)
    print("[gen] base 源   = %s%s" % (BASE_PKG if HAVE_BASE else "(未找到)", 
                                      "" if not HAVE_BASE else "  [%s]" % BASE_SOURCE))
    print("[gen] 门禁文件 = %s" % GATE_PATH)
    if not HAVE_BASE:
        print("[gen] ⚠️  降级模式：找不到改动前基线（base/pkg）")
        print("[gen]     解析顺序：GWEN_U1I4_BASE_PKG → < lane >/base/pkg → <pkg>/.u1i4_base/pkg → git 历史回溯")
        print("[gen]     启用完整模式：设 GWEN_U1I4_BASE_PKG=<含 content/dialogue.py 的 pkg 目录>")
    if not HAVE_BASE and (args.emit_frozen or args.emit_live):
        print("[gen] ❌ --emit-* 需要 base/pkg（冻结侧必须逐字节来自改动前实现）—— 拒绝执行（exit 2）")
        return 2

    bad = self_check(verbose=True)
    if bad:
        print("\n[gen] ❌ 自检未过（%d 条）—— 拒绝产出，先修切片口径：" % len(bad))
        for b in bad:
            print("     - %s" % b)
        return 2

    if not HAVE_BASE:
        print("\n[gen] ⏭️  跳过清单（%d 项，缺 base/pkg —— **这些检查没跑，不算通过**）：" % len(SKIPPED))
        for s in SKIPPED:
            print("     - %s" % s)
        print("[gen] ✅ 降级检查全过（仅「设计面」自检；切片/冻结比对未跑）")
        return 2 if args.require_base else 0

    slices = _slice_all()
    live = _live_sources()
    live.pop("_LIVE_MODULES")
    aux = _aux_pins()
    region = _gen_region(slices, live, aux)

    with open(GATE_PATH, encoding="utf-8") as f:
        gate_now = f.read()
    spliced, self_sha = _write_frozen(gate_now, region)

    if args.check:
        # 只读口径：连「按 base 切片重拼后是否与盘上一致」都核，但**不写**。
        if spliced != gate_now:
            print("[gen] ❌ --check：盘上门禁文件与 base 切片重拼结果不一致"
                  "（安全网被动过 / 需重生成）")
            print("[gen]    盘上自哈希 = %s / 重拼自哈希 = %s"
                  % (_extract_quoted(gate_now, "_GATE_SELF_SHA256")[:16], self_sha[:16]))
            return 3
        print("[gen] ✅ --check 全过（未写任何文件；盘上门禁与 base 切片逐字节一致）")
        return 0

    if args.emit_live and not args.emit_frozen:
        print("[gen] --emit-live：frozen 字面量逐字节来自 base（本次写整段，冻结侧零变化）")

    with open(GATE_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(spliced)
    print("[gen] ✅ 已写入 %s" % GATE_PATH)
    print("[gen]    frozen=%d 段 · live=%d 段 · aux=%d 条 · gate_self=%s"
          % (len(slices), len(live), len(aux), self_sha[:16]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
