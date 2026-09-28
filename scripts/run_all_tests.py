# -*- coding: utf-8 -*-
"""全量回归（**包仓入口**）—— 薄壳：转调宿主跑器（跑器真源唯一 = 宿主仓那份）。

口径（T8 终态 + P0-6 收口 2026-09-19）
------------------------------------
内容侧测试真源 = 本仓 `tests/`（编辑器里的 `framework/games/<pkg>/tests` 是它经 `sync.sh`
部署出来的那一份）。**跑器**只留一份：宿主仓 `scripts/run_all_tests.py` —— 它同时认
「宿主自留件 + 包仓那份 tests」，且支持 `--pkg-only`（只跑后者）。

本文件不再持有第二份实现（旧版 445 行分叉里的 `_parse_args` / `_run_one` / `submit_next` /
`RETIRED_PROBES` / `_TPL_INIT` / 模板库初始化段与宿主版逐字重复）。薄壳只做三件事：
  ① 路径装配 —— 复用 `tests/_paths.py`（包内唯一发现点；缺引擎/宿主即醒目报错）
  ② 交包根   —— `GWEN_PACKAGE_DIR` + `--pkg-root=<本仓根>`
  ③ 转调     —— argv 原样透传，退出码即跑器退出码

为什么必须带 `--pkg-root=`：宿主跑器默认枚举**部署面** `framework/games/*/tests`；在包仓入口
要跑的必须是**本仓 `tests/`**（工作树可能领先/落后于部署副本），所以把本仓根显式交过去。
连带：worker 空白 schema 模板库也按本仓包目录建（`_pick_package_dir` 直接命中）。

用法（在包仓根跑，参数与宿主跑器**完全一致**）：
  python scripts/run_all_tests.py [--file=<名|路径>] [--fail-fast] [--jobs=N] [--serial]
                                  [--skip=test_xxx.py[,test_yyy.py]] [--real-astrbot]

注意：
  - 需要引擎 + 宿主壳在位（`tests/_paths.py` 的硬 requirement）；缺则醒目报错，
    绝不静默跳过、绝不当「0 个测试=全绿」。
  - 必须用带 pypinyin 的 python 启动（AstrBot 的 uv python 或同依赖的 python）。
"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
TESTS_DIR = os.path.join(PKG_ROOT, "tests")


def _die(lines):
    print("!" * 78, flush=True)
    for ln in lines:
        print(ln, flush=True)
    print("!" * 78, flush=True)
    raise SystemExit(1)


# ---- ① 路径装配：复用 `tests/_paths.py`（包内唯一发现点）----
sys.path.insert(0, TESTS_DIR)
try:
    import _paths  # noqa: E402
except Exception as _exc:  # noqa: BLE001
    _die(["!! 包仓 tests 真源不可用：无法从 %s 导入 `_paths`（路径装配单点）。" % TESTS_DIR,
          "!! 目录缺失 / 被改名 / 被清空 / 引擎或宿主壳不在位 —— 拒绝继续"
          "（绝不当「0 个测试=全绿」）。",
          "!! 原始异常：%s: %s" % (type(_exc).__name__, _exc)])

HOST_ROOT = _paths.HOST_ROOT
RUNNER = os.path.join(HOST_ROOT, "scripts", "run_all_tests.py")
if not os.path.isfile(RUNNER):
    _die(["!! 找不到宿主跑器（T8 终态：跑器真源唯一 = 宿主仓那份）：%s" % RUNNER,
          "!! 宿主壳根 = %s（由 `tests/_paths.py` 发现）" % HOST_ROOT,
          "!! 修法：确认宿主仓在位（可用 `GWEN_HOST_DIR` 显式指定），"
          "或 `bash sync.sh` 重同步部署树。"])

# 宿主跑器必须**已经**带 `--pkg-only` / `--pkg-root=`（P0-6 之后的那一版）：否则它会照旧
# 枚举「宿主自留件 + 包仓那份」⇒ 本入口的语义（只跑本仓这份）会**静默**变成两侧全跑。
# 判据 = 源码里两个开关名都在（把版本耦合显式化，不靠「未知参数被忽略」兜底）。
with io.open(RUNNER, encoding="utf-8", errors="replace") as _fh:
    _runner_src = _fh.read()
_missing = [o for o in ("--pkg-only", "--pkg-root=") if o not in _runner_src]
if _missing:
    _die(["!! 宿主跑器版本过旧（缺 %s）：%s" % (" / ".join(_missing), RUNNER),
          "!! 部署树未同步到 P0-6（跑器单源化）之后的引擎提交 —— 拒绝继续，"
          "以免静默按旧语义（两侧全跑）执行。",
          "!! 修法：`cd <宿主仓>/framework && git fetch origin main && git checkout <新 sha> && "
          "git submodule update --init games/orlandia`。"])

# ---- ② 交包根 ----
# ★ 引擎面一致性取证与**归因提示**（2026-09-28 实测 · 同一件事第三次撞，台账 §3.5）
#   包内测试吃哪份引擎由 `tests/_paths.py::find_engine_root()` 决定，`GWEN_FRAMEWORK_DIR`
#   **优先**。但真正被调用的是**宿主跑器**，它在自己那份
#   `base_env["GWEN_FRAMEWORK_DIR"] = <plugin>/framework`（部署面检出）上**强制覆盖** ——
#   与它自己文档第 40 行写的「环境变量 `GWEN_FRAMEWORK_DIR` 覆盖」**矛盾**。
#   ⇒ 在工作树上跑全量时，包测实际吃的是**部署面那份旧引擎**：本树 `Slots.load` 有
#     `strict=`（存仓/取仓的 fail-closed 形状），部署面 `78da079` 没有 ⇒
#     `home_storage_deposit_atomic` 抛 `TypeError: Slots.load() got an unexpected
#     keyword argument 'strict'`，**5 支测试假红**（逐支单跑全绿）—— 长得极像真回归。
#   ★ 本入口**不修**那个覆盖（跑器在宿主仓，不在本车道文件面），也**不因此中止**：
#     中止 = 门禁彻底不可用 = 判据被削弱。所以只做两件**不削弱**的事：
#     ① 开跑前把「本次红集可能是环境红」这条证据（两棵树的路径 + HEAD）打在最前面；
#     ② 有红时在末尾**再打一遍**并附「逐支单跑复核」配方 ⇒ 归因不再靠人记得台账。
GU_DECLARED = (os.environ.get("GWEN_FRAMEWORK_DIR") or "").strip()
GU_INJECTED = os.path.join(os.path.dirname(os.path.dirname(RUNNER)), "framework")
GU_MISMATCH = bool(
    GU_DECLARED
    and os.path.normcase(os.path.abspath(GU_DECLARED))
    != os.path.normcase(os.path.abspath(GU_INJECTED))
)


def _gu_banner(where):
    """引擎面不一致的取证横幅（开着这一态才打印；两棵树各给 HEAD）。"""
    if not GU_MISMATCH:
        return
    import subprocess as _sp

    def _head(root):
        try:
            return _sp.run(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True,
                           errors="replace").stdout.strip() or "?"
        except Exception:  # noqa: BLE001 —— 取证失败不许影响主流程
            return "?"

    print("!" * 78, flush=True)
    print("!! ★ 引擎面不一致（台账 §3.5 · 已第三次撞）—— **本次若有红，先按环境红归因**：",
          flush=True)
    print("!!   导出的引擎根   = %s  @ %s" % (GU_DECLARED, _head(GU_DECLARED)), flush=True)
    print("!!   实际被注入的   = %s  @ %s" % (GU_INJECTED, _head(GU_INJECTED)),
          flush=True)
    print("!!   机制：宿主跑器 `base_env['GWEN_FRAMEWORK_DIR']` **强制覆盖**了导出值",
          flush=True)
    print("!!         （与它自己文档第 40 行「环境变量覆盖」矛盾）⇒ 包测 import 的是部署面引擎。",
          flush=True)
    print("!!   症状：引擎侧新形状缺失 ⇒ 几支测试假红，而**逐支单跑全绿**。", flush=True)
    if where == "before":
        print("!!   复核配方：把下面几支**逐支单跑**（同环境、单进程）⇒ 全绿即坐实环境红：",
              flush=True)
    print("!" * 78, flush=True)


_gu_banner("before")

os.environ["GWEN_PACKAGE_DIR"] = PKG_ROOT
cmd = [sys.executable, RUNNER, "--pkg-only", "--pkg-root=" + PKG_ROOT] + sys.argv[1:]

# ---- ③ 转调（同机同解释器；stdio 继承，输出逐行直通）----
_rc = subprocess.call(cmd)
if _rc != 0 and GU_MISMATCH:
    # ★ 有红且引擎面不一致 ⇒ 把归因**再钉一次**在末尾（人只会看最后一段输出）
    print("!" * 78, flush=True)
    print("!! ↑ 上面这份红集**可能有环境红**（引擎面不一致，见开头横幅）。", flush=True)
    print("!! 归因判据：把红的那几支**逐支单跑**（逐文件独立进程）：", flush=True)
    print("!!   unset SAINTESS_EXTENDS  GWEN_FRAMEWORK_DIR=<工作树>  GWEN_HOST_DIR=<宿主>", flush=True)
    print("!!   <python> tests/<红的那支>.py    —— 全绿 ⇒ 环境红，**不是回归**。", flush=True)
    print("!! 真回归的判据：单跑**仍然红**（真回归在单跑与全量里指向同一处）。", flush=True)
    print("!! 根治（两条都不是本入口能替你做的）：① 同步部署面 `git -C <plugin>/framework", flush=True)
    print("!!   fetch origin main && git -C <plugin>/framework checkout <引擎 sha>`（引擎须已 push）；", flush=True)
    print("!!   ② 跑器侧改成尊重 `GWEN_FRAMEWORK_DIR`（一行归属改动，需宿主仓立项）。", flush=True)
    print("!" * 78, flush=True)
sys.exit(_rc)
