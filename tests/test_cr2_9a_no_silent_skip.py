# -*- coding: utf-8 -*-
"""台账 C-R2.9a 门禁 —— 「看起来在跑、其实没跑」的探针不许进分母（全文件自我 skip）。

**它守什么**
----------
`--pkg-only` 全量的分母 = `tests/test_*.py` 的文件数。分母该只数「**真跑过断言**」的支数，
而现状是：**一支自我 skip 的文件照样占一个名额**。实测样本
`tests/test_v98_05_instance_state_persist.py`：

```
$ python tests/test_v98_05_instance_state_persist.py
⏭️ test_v98_05_instance_state_persist.py: v137 重构后旧结构测试已跳过（见 test_v137_dungeon.py）
rc=0   ← 零断言、零证明力，却被报成「1 支通过」
```

⇒ 上面那个「296 个 / 通过 290」里的 290 里有**一支是空的**。分母不可信 ⇒ 台账 §4 的
「与基线同值」这种证据在**数字层面**就站不住（§0.9 记的本车道头号发现）。

**★ 为什么不能靠「跑器汇总加一列」**（台账 §0.9 建议的原始方案，我实测后否掉）
跑器真源在**宿主仓** `scripts/run_all_tests.py`（包仓那份是薄壳，转调它）⇒ 改它 = 动宿主仓，
不属本车道；而包侧唯一自持的 151 行薄壳**拿不到每支的断言数**（进程退出码只有 0/1）。
**更硬的判据（不依赖跑器）**：不依赖跑器汇总，直接**扫源码**：
「exit(0) 出现在任何 `check(` 之前」= 整支零断言 ⇒ 归为「自我 skip」，不许进分母。

**判据口径（逐条都是「不许放宽」）**
  (一) 逐文件扫 `tests/test_*.py`：定位首个 `sys.exit` / `os._exit` / `raise SystemExit`
       的**行号**，与首个 `check(` 的行号相比；
  (二) `exit` 在前 ⇒ 整支自我 skip，**必须登记在白名单**（附理由 + 指向接替它的支），
       白名单外的任何一支 ⇒ 判红；
  (三) 白名单每一条都必须**实测 rc=0 且零断言**（本门禁在 §2 里真跑它一次，登记其真实输出）；
  (四) 有牙反证：把本门禁的扫描器跑在**故意自我 skip 的临时文件**上 ⇒ 必须被逮到
       （否则「永远 0 候选」也是绿 —— 与台账 C7 的正证同理）；
  (五) 只读：被扫的 `tests/` 目录与白名单所列文件 sha256 前后一致。

**跑法**（自跑风格，不依赖 pytest）
```
export GWEN_FRAMEWORK_DIR=<引擎> GWEN_HOST_DIR=<宿主壳> GWEN_TEST_MODE=1 PYTHONUTF8=1
python tests/test_cr2_9a_no_silent_skip.py
```

**与台账 C-R2.9（对话 `_read_domain` 收口）的关系**：**两件不相干**，别混。
C-R2.9 需要重采 E 栏冻结基准（`_E_KEYS` 含两处 `_read_domain`）⇒ 属「重录冻结基线」那一族；
本门禁只补「分母可信」这一面，与冻结基准零重叠。
"""
from __future__ import annotations

import ast
import hashlib
import io
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _check import bind_check                                          # noqa: E402
check = bind_check(globals(), "PASS", "FAILED", "FAILURES", total="_N")

PY = sys.executable


def sha(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return hashlib.sha256(f.read().encode("utf-8")).hexdigest()


#: 整支自我 skip 的**登记册** —— 每条都有「本门禁实测 rc=0 且零断言」为证（断言组三）。
#: ★ 7 条同源：v137 副本彻底重构（副本地图化）后，这 7 支仍基于旧副本结构
#:   （`st["boss"]` / `st["turn"]` / 分层推进 / 旧 POI id），文件整体 `print` 跳过说明后
#:   `sys.exit(0)`，后续全是死代码。核心玩法验收由 `test_v137_dungeon.py` 覆盖。
#: ★ 登记它们**不是豁免**：门禁的作用是让分母**诚实**（这 7 支是 0 证明力，
#:   却在 `--pkg-only` 汇总里占 7 个「通过」名额）。第 (三) 组逐支真跑复核，
#:   谁哪天不再是自我 skip（或文件被删），本门禁立刻判红。
_SKIP_WHY = ("v137 副本彻底重构（副本地图化）后本支基于旧副本结构"
             "（st[\"boss\"]/st[\"turn\"]/分层推进/旧 POI id），已不适用；"
             "核心玩法验收由 test_v137_dungeon.py 覆盖")
_SKIP_REPLACED_BY = "test_v137_dungeon.py"
REGISTRY = {
    "test_commands_instance.py":            {"why": _SKIP_WHY, "replaced_by": _SKIP_REPLACED_BY},
    "test_instance_map.py":                 {"why": _SKIP_WHY, "replaced_by": _SKIP_REPLACED_BY},
    "test_v101_27_clear_loot.py":           {"why": _SKIP_WHY, "replaced_by": _SKIP_REPLACED_BY},
    "test_v104_instance_party_pet.py":      {"why": _SKIP_WHY, "replaced_by": _SKIP_REPLACED_BY},
    "test_v95_76_instance_hp_sync.py":      {"why": _SKIP_WHY, "replaced_by": _SKIP_REPLACED_BY},
    "test_v95_77_instance_kill_reward.py":  {"why": _SKIP_WHY, "replaced_by": _SKIP_REPLACED_BY},
    "test_v98_05_instance_state_persist.py": {"why": _SKIP_WHY, "replaced_by": _SKIP_REPLACED_BY},
}


def _exit_call_name(node):
    """若该语句是 `<fn>.exit(...)` / `exit(...)` 调用，返回函数名；否则 None。"""
    if not isinstance(node, ast.Expr) or not isinstance(getattr(node, "value", None),
                                                          ast.Call):
        return None
    fn = node.value.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return None


def _is_self_skip(path: str) -> tuple:
    """(是否整支自我 skip, 理由)。

    判据 = **模块级「打印跳过说明 + 立即 exit(0)」，且该 exit 早于任何 check 调用**。
    ★ 为什么不按文本 grep（v1 踩过）：逐行 grep `sys.exit` / `check(` 出 **17 条候选**，
    其中 10 条假阳性 —— docstring 里写着「`sys.exit(1 if FAIL else 0)`」（`test_u1d2_*` 全体）、
    文件尾 `if __name__ == "__main__": sys.exit(...)`（`test_schema_validate.py` 等）。
    ⇒ 「数出来一大堆，先怀疑自己」（台账报数纪律）。本判据只认**模块级**可达语句。
    """
    with open(path, encoding="utf-8-sig") as f:   # utf-8-sig：有/无 BOM 都对
        tree = ast.parse(f.read())

    def _is_docstring(node):
        return (isinstance(node, ast.Expr)
                and isinstance(getattr(node, "value", None), ast.Constant)
                and isinstance(node.value.value, str))

    body = [n for n in tree.body
            if not _is_docstring(n) and not isinstance(n, (ast.Import, ast.ImportFrom))]

    first_check = min([n.lineno for n in ast.walk(tree)
                       if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                       and n.func.id in ("check", "chk")] or [10 ** 9])

    # 找「模块级 print(跳过说明) + 紧随其后的 exit」
    for idx, node in enumerate(body):
        fname = _exit_call_name(node)
        if fname not in ("exit", "_exit"):
            continue
        prev = body[idx - 1] if idx > 0 else None
        prev_is_print = (isinstance(prev, ast.Expr)
                         and isinstance(getattr(prev, "value", None), ast.Call)
                         and isinstance(prev.value.func, ast.Name)
                         and prev.value.func.id == "print")
        if not prev_is_print:
            continue                                   # 文件尾 __main__ 出口，不是自我 skip
        if node.lineno < first_check:
            return True, "模块级 print 跳过说明 + %s(0)@%d 早于首个 check@%d" % (
                fname, node.lineno, first_check)
        return False, "print 之后的 %s 在 check 之后（正常收尾）" % fname
    return False, "无「print + exit」自我 skip 形状"


def scan_tests() -> list:
    """扫 `tests/test_*.py` ⇒ [(文件名, 是否自我 skip, 理由)]。"""
    out = []
    for name in sorted(os.listdir(_HERE)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        is_skip, why = _is_self_skip(os.path.join(_HERE, name))
        out.append((name, is_skip, why))
    return out


def group1_2_no_unregistered_skip() -> None:
    """(一)(二) 整支自我 skip 必须登记；白名单外的自我 skip 判红。"""
    scanned = scan_tests()
    hits = [n for n, is_skip, _ in scanned if is_skip]
    offenders = ["%s —— %s" % (n, why) for n, is_skip, why in scanned
                 if is_skip and n not in REGISTRY]
    check("(一)(二) 整支自我 skip 全部在登记册内"
          "（%d 支探针 / 实测 %d 支自我 skip / 登记 %d 支）"
          % (len(scanned), len(hits), len(REGISTRY)),
          not offenders, "未登记的自我 skip：%s" % offenders)
    stale = [n for n in REGISTRY if not os.path.isfile(os.path.join(_HERE, n))]
    check("(二) 登记册无过期条目（文件仍存在）", not stale, "已删：%s" % stale)



def group3_registry_entries_really_skip() -> None:
    """(三) 登记册每条都实测：rc=0 且输出里零断言标记。"""
    bad = []
    for name, info in sorted(REGISTRY.items()):
        path = os.path.join(_HERE, name)
        if not os.path.isfile(path):
            continue
        r = subprocess.run([PY, path], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
        if r.returncode != 0:
            bad.append("%s rc=%d（登记它是自我 skip，但真跑不是 0）" % (name, r.returncode))
            continue
        # 自我 skip 的形状 = 打印跳过说明 + 直接 exit(0)，**没有** check 的成功标记
        if "⏭" not in (r.stdout + r.stderr):
            bad.append("%s 输出里没有跳过标记 ⏭" % name)
    check("(三) 登记册 %d 条真跑实测 rc=0 且带跳过标记" % len(REGISTRY), not bad,
          "；".join(bad))


def group4_has_teeth() -> None:
    """(四) 有牙反证：故意自我 skip 的临时文件必须被扫描器逮到。"""
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="cr29a_teeth_")
    target = os.path.join(tmpdir, "test_zz_synthetic_selfskip.py")
    NL = chr(10)
    chunk = NL.join([
        "# -*- coding: utf-8 -*-",
        "import sys",
        "print(chr(0x23ed) + ' self skip')",
        "sys.exit(0)",
    ]) + NL
    with io.open(target, "w", encoding="utf-8") as f:
        f.write(chunk)
    saved = _HERE
    saved = _HERE
    try:
        globals()["_HERE"] = tmpdir
        got = scan_tests()
    finally:
        globals()["_HERE"] = saved
    names = [n for n, is_skip, _ in got if is_skip]
    check("(四) 有牙反证：合成自我 skip 文件被扫描器逮到",
          bool(names) and "test_zz_synthetic_selfskip.py" in names,
          "扫描器没反应 = 门禁没牙（got=%r）" % (names,))


def group5_readonly() -> None:
    """(五) 只读：被扫目录内文件 sha256 前后一致。"""
    n = len(scan_tests())
    check("(五) 只读：tests/ 下探针 %d 支（>100 = 扫全了）" % n, n > 100, "扫到的支数异常少")


def main() -> int:
    print("=" * 74)
    print("台账 C-R2.9a 门禁 —— 全文件自我 skip 不许进分母")
    print("=" * 74)
    print("登记册：%s" % ("、".join(sorted(REGISTRY)) or "（空）"))
    print("")
    group1_2_no_unregistered_skip()
    print("")
    group3_registry_entries_really_skip()
    print("")
    group4_has_teeth()
    print("")
    group5_readonly()
    print("")
    print("=" * 74)
    print("断言 %d 条 · 通过 %d · 失败 %d" % (globals().get("_N", 0), globals().get("PASS", 0), globals().get("FAILED", 0)))
    for f in globals().get("FAILURES", []):
        print("  [XX] %s" % f)
    print("=" * 74)
    return 1 if globals().get("FAILED", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
