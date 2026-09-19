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
os.environ["GWEN_PACKAGE_DIR"] = PKG_ROOT
cmd = [sys.executable, RUNNER, "--pkg-only", "--pkg-root=" + PKG_ROOT] + sys.argv[1:]

# ---- ③ 转调（同机同解释器；stdio 继承，输出逐行直通）----
sys.exit(subprocess.call(cmd))
