# -*- coding: utf-8 -*-
"""全量回归（**包内版**）：逐个直接执行 tests/test_*.py（旧式脚本 + pytest 风格均可独立运行）。

用法（在包仓根跑）：
  python scripts/run_all_tests.py [--file tests/test_xxx.py] [--fail-fast] [--jobs=N] [--serial]
                                  [--skip=test_xxx.py[,test_yyy.py]] [--real-astrbot]

与宿主版语义一致（v117 全量提速：默认并行 + shim astrbot）：
  - 每个测试文件 = 独立子进程 + 独立 GWEN_GAME_DB 私有库（tests/.run_all_workers_<pid>_<ts>/ 下）
  - 每轮跑先 init_db 建一次空白 schema 模板，各文件复制一份 → 表结构齐全且零残留，
    文件间互不污染（conftest 的 setdefault 尊重外层 env）
  - 默认 --jobs 按核数自适应（4~8，实测本机 P/E 核混合架构下 8 路最快）；--serial 恢复旧的纯串行共享库行为
  - --skip= 跳过已知坏测试；--file= 单文件走旧逻辑（共享 test_game_data.db）
  - v117.5：默认注入 tests/shim_astrbot（行为等价的 astrbot 替身）；--real-astrbot 退回真实 astrbot
  - 硬编码共享 test_game_data.db 的文件自动进「串行槽」先跑

包内化的差异（只有「路径装配」这一层）：
  - 包根 = 本文件上两级；测试在 <包根>/tests/
  - 引擎根 = `tests/_paths.py` 发现（`GWEN_FRAMEWORK_DIR` 优先 → 候选 → 缺则**醒目报错**）
  - 宿主壳根 = 引擎根所在部署树根（`host/store_factory.py` 建 worker 模板库用）
  - 子进程解释器 = 本运行器的 `sys.executable`（用哪个 python 跑本器，子进程就用哪个：
    宿主测试要 pypinyin 等依赖 → 请用 AstrBot 的 uv python 启动本器）
  - 跑全量期间不要改动任何源文件（避免中间态误判）
"""
import json
import os
import re
import shutil
import tempfile
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

# P1-1：子进程强制 UTF-8（否则测试打印 ✅/中文在 GBK 控制台崩溃（UnicodeEncodeError）
# → 假红）。先 setdefault 再在 subprocess 环境里也显式传递，双保险。
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
# v110 审计修复：父进程 stdout 同样强制 UTF-8——此前仅子进程侧生效，父进程首个 ✅ 打印
# 在 GBK(CP936) 控制台即 UnicodeEncodeError 崩溃（实测首发必现，吞掉全量结果）
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# P2：单测超时。★ 2026-09-18 修复「并行假红」——阈值必须随**并发度**放宽：
#   实测（24 核机、默认 16 路并发）最慢文件墙钟被 CPU/IO/内存争用放大 1.5–2×：
#     test_texts_table 单跑 164s → 并发 >300s · u1i2 205s → >300s · u1i4 247s → >300s
#   ⇒ 三个门禁恒报 TIMEOUT（单跑全绿），真回归被假红淹掉、还逼人手工单跑复核。
#   现在：基线 × 「每 4 路并发一档」，并设上限（防真 hang 无限拖全量）。
_BASE_TIMEOUT = 300   # 独占单跑基线（秒）
_TIMEOUT_CAP = 900    # 上限（最慢文件 247s 单跑 ×2.5 并发放大 ≈ 620s，留足余量）


def _test_timeout(jobs: int) -> int:
    """单文件超时秒数：基线 × 并发档位（每 4 路一档），不超过上限。"""
    slots = max(1, (int(jobs) + 3) // 4)
    return min(_TIMEOUT_CAP, _BASE_TIMEOUT * slots)


# ★ 2026-09-18：实测耗时记录 + LPT（最长作业优先）调度。
#   动因：总墙钟由**最慢的单文件**决定（一次实测：285 文件共 5994s CPU 时间 / 691s 墙钟，
#   其中 6 个重文件占 43% CPU 时间，最慢 u1i2 605s ⇒ 墙钟下界就等于它）。
#   按枚举顺序启动时重文件可能排在最后 → 尾部空转；按实测耗时降序启动可逼近下界。
#   记录存 TEMP（不入库、不受 tests/ 清理影响；丢了只回退到枚举顺序，无副作用）。
_TIMES_FILE = os.path.join(tempfile.gettempdir(), "gwen_run_all_times.json")
_RUN_SECS = {}


def _load_times() -> dict:
    try:
        with open(_TIMES_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:                                        # noqa: BLE001
        return {}


def _save_times(d: dict) -> None:
    try:
        with open(_TIMES_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, sort_keys=True)
    except Exception:                                        # noqa: BLE001
        pass


PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 包仓根
TESTS_DIR = os.path.join(PKG_ROOT, "tests")
PYTHON = sys.executable
# v117.5：shim astrbot（行为等价替身，省 ~3s/进程 import，详见 tests/shim_astrbot/README.md）。
# 默认注入子进程 PYTHONPATH；--real-astrbot 关闭（对照验证用）。
SHIM_DIR = os.path.join(TESTS_DIR, "shim_astrbot")

# 引擎根 / 宿主壳根：单点发现（`tests/_paths.py`；缺失即醒目报错，不静默跳过）
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)
try:
    import _paths  # noqa: E402
except Exception as _exc:  # noqa: BLE001
    # ★ T8：**不许把「tests 目录没了」表现成普通 traceback / 0 个测试跑绿** ——
    #   包仓 tests 是内容侧真源，目录缺失/被改名/被清空一律醒目报错 + 退非零。
    print("!" * 78, flush=True)
    print("!! 包仓 tests 真源不可用：无法从 %s 导入 `_paths`（路径装配单点）。" % TESTS_DIR,
          flush=True)
    print("!! 目录缺失 / 被改名 / 被清空 —— 拒绝继续（绝不当「0 个测试=全绿」）。", flush=True)
    print("!! 原始异常：%s: %s" % (type(_exc).__name__, _exc), flush=True)
    print("!" * 78, flush=True)
    raise SystemExit(1)
ENGINE_ROOT = _paths.ENGINE_ROOT
HOST_ROOT = _paths.HOST_ROOT

# 串行槽：直接赋值 os.environ["GWEN_GAME_DB"] 指向共享 test_game_data.db 的文件
# （不认外层 env，无法用私有库隔离）→ 必须与并行主体错开，保持旧行为先跑。
# v181 flaky 修复：硬编码自己私有库文件（os.environ[...] = tests/test_xxx_private.db）
# 的文件同样绕过 worker 私有库 env → 归串行槽，避免并行脏残留/文件竞争。
SERIAL_SLOT = {
    "test_v101_28_food_hot.py",
    "test_v1023_life_prof.py",
    # ★ T8：**写包内磁盘真源**的文件必须与「读同一份真源」的文件错开 ——
    #   `test_gm_reload.py` 会改写 `content/rules/effect_rules.json` 再 `finally` 还原
    #   （它就是测「改盘 → 重载」）。并行跑时 `test_export_package_sync.py` 的落盘规范
    #   检查会读到**写了一半**的文件 ⇒ 偶发红
    #   （实测：宿主全量入口 `❌ content/rules/effect_rules.json:['无末尾换行','JSON 坏']`，
    #    单跑 3/3 绿、包仓跑器同池偶发）。
    "test_gm_reload.py",
}

# 退役探针：P2C 族化迁移期 OLD==NEW 差分验证工具。迁移完成（旧 handler 从 HEAD 删除）后
# 差分对象不存在 → 恒 KeyError。semantics 测试（新实现硬断言）已接替持续回归职责。
# 保留名单供历史参考，run_all 不再纳入（文件本身已不在 tests/）。
RETIRED_PROBES = {
    "test_p2cc2_we_family_probe.py",
    "test_p2cc3_we_shield_probe.py",
    "test_p2cc4_extra_dmg_probe.py",
    "test_p2cc5_control_probe.py",
    "test_p2cc6_panel_buff_probe.py",
    "test_p2cc7_marks_probe.py",
    "test_p2cc8_passive_stack_probe.py",
    "test_p2cc9_lifesave_probe.py",
    "test_p2cc10_aux_probe.py",
}

# 探测未来新增的同款硬编码共享库文件（忽略注释行），命中自动进串行槽
_SHARED_DB_RE = re.compile(
    r'os\.environ\[["\']GWEN_GAME_DB["\']\]\s*=\s*[^\n]*test_game_data\.db'
)

# 并行 worker 库的空白 schema 模板初始化（每轮跑只执行一次，init_db 全表 + 老库自愈）。
# 与旧共享库等价：表结构齐全；且每个文件拿到的是零残留新库（项目本就往私有库方向走）。
#   argv[1] = 私有库路径 · argv[2] = 宿主壳根 · argv[3] = 引擎根 · argv[4] = 包根
_TPL_INIT = (
    "import os,sys;"
    "os.environ['GWEN_GAME_DB']=sys.argv[1];"
    "sys.path.insert(0,sys.argv[2]);"
    "sys.path.insert(0,sys.argv[3]);"
    "from host import store_factory as _sf;"
    "from saintess_engine.host import load_package;"
    "_pkg=load_package(sys.argv[4], inject=_sf.inject_handles());"
    "_sf.bind_store(_pkg).init()"
)


def _find_package_dir():
    """包目录：`GWEN_PACKAGE_DIR` 优先；否则 = 包仓根本身（本运行器所在仓）。"""
    env = str(os.environ.get("GWEN_PACKAGE_DIR") or "").strip()
    if env and os.path.isdir(env):
        return env
    if os.path.isfile(os.path.join(PKG_ROOT, "content", "data", "commands.json")):
        return PKG_ROOT
    return None


def _parse_args(argv):
    fail_fast = "--fail-fast" in argv
    serial = "--serial" in argv
    real_astrbot = "--real-astrbot" in argv
    # ★ 2026-09-18 实测：默认并发上限 16 → 8。本机 i7-14650HX = 8 个 P 核 + 8 个 E 核
    #   （24 逻辑核）：16 路时有一半进程落到 E 核（约 P 核六成性能）+ 满载争用，
    #   全量 275s；8 路正好塞满 P 核、不碰 E 核，实测 180~193s（快 30%，连跑两次 285/285）。
    #   需要压满逻辑核时用 `--jobs=16` 覆盖。
    jobs = max(4, min(8, os.cpu_count() or 8))  # 默认按核数自适应（4~8）
    only = None
    skips = []
    for a in argv:
        if a.startswith("--file="):
            only = a.split("=", 1)[1]
        elif a.startswith("--jobs="):
            jobs = int(a.split("=", 1)[1])
        elif a.startswith("--skip="):
            for s in a.split("=", 1)[1].split(","):
                s = s.strip()
                if s:
                    skips.append(s if s.endswith(".py") else s + ".py")
    return fail_fast, serial, real_astrbot, jobs, only, skips


def _collect_files(only, skips):
    """返回 (串行槽文件列表, 并行文件列表)。--file= 模式整体走串行槽（旧行为）。"""
    if only:
        f = only if only.endswith(".py") else only + ".py"
        if not os.path.isabs(f):
            f = os.path.join(TESTS_DIR, os.path.basename(f))
        return [f], []

    def _want(name):
        return name not in skips and name not in RETIRED_PROBES

    serial, parallel = [], []
    for name in sorted(
        f for f in os.listdir(TESTS_DIR)
        if f.startswith("test_") and f.endswith(".py")
    ):
        if not _want(name):
            continue
        if name in SERIAL_SLOT:
            serial.append(os.path.join(TESTS_DIR, name))
            continue
        try:
            with open(os.path.join(TESTS_DIR, name), encoding="utf-8") as fh:
                code_lines = [ln for ln in fh.read().splitlines()
                              if not ln.lstrip().startswith("#")]
                if _SHARED_DB_RE.search("\n".join(code_lines)):
                    serial.append(os.path.join(TESTS_DIR, name))
                    continue
        except OSError:
            pass
        parallel.append(os.path.join(TESTS_DIR, name))
    return serial, parallel


def _run_one(f, env, seed_db=None, timeout=None):
    if seed_db is not None:
        # 给本文件复制一份空白 schema 模板库（复制远快于重新建表 + 重新 import）
        shutil.copy2(seed_db, env["GWEN_GAME_DB"])
    ts = time.time()
    try:
        proc = subprocess.run(
            [PYTHON, f], capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env,
            timeout=timeout if timeout is not None else _BASE_TIMEOUT,
        )
        timed_out, ok = False, proc.returncode == 0
    except subprocess.TimeoutExpired as te:  # P2：超时记录
        proc, timed_out, ok = te, True, False
    dt = time.time() - ts
    _RUN_SECS[os.path.basename(f)] = dt      # ★ LPT 调度用的实测耗时
    return os.path.basename(f), ok, proc, dt, timed_out


def _report(name, ok, proc, dt, timed_out):
    flag = "✅" if ok else ("⏱️" if timed_out else "❌")
    print(f"{flag} {name} ({dt:.1f}s, exit={'TIMEOUT' if timed_out else proc.returncode})", flush=True)
    if not ok:
        if timed_out:
            # ★ 2026-09-18：超时优先怀疑「并发争用」而非真回归 —— 先单跑该文件复核
            #   （若单跑绿 ⇒ 并发假红，别急着改代码）。
            print("   ↳ 疑似并发争用（墙钟被争用放大）：请先 `python tests/%s` 单跑复核" % name,
                  flush=True)
        # P1-2：失败分支同时补打 stdout + stderr 尾（各 30 行），便于定位子进程崩溃/报错
        out_lines = (proc.stdout or "").strip().splitlines() if hasattr(proc, "stdout") else []
        err_lines = (proc.stderr or "").strip().splitlines() if hasattr(proc, "stderr") else []
        for label, lines in (("stdout:", out_lines), ("--- stderr ---", err_lines)):
            tail = lines[-30:] if lines else []
            if tail:
                print(label, flush=True)
                print("\n".join(tail), flush=True)
        print("-" * 60, flush=True)


def _summary(results, t0):
    print("\n" + "=" * 60)
    passed = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]
    print(f"文件: {len(results)} 个，通过 {len(passed)}，失败 {len(failed)}，总耗时 {time.time()-t0:.0f}s")
    if failed:
        print("失败文件:")
        for name, _ in failed:
            print(f"  ❌ {name}")
    return 1 if failed else 0


def _run_framework_tests(base_env):
    """前置：跑引擎框架仓自带测试（S8 拆仓后的双轨，plan §8-R6）。

    引擎已物理分离为独立仓库 —— 它的纯度门禁 / 中性兜底 / 示例冒烟是本包回归的
    **前置依赖**（引擎坏了游戏测试全无意义）。
    返回 True=通过；引擎根不存在（未设 GWEN_FRAMEWORK_DIR 且候选全缺）时 `_paths`
    已经**醒目报错**，这里不会走到。
    """
    runner = os.path.join(ENGINE_ROOT, "tests", "run_all.py")
    if not os.path.exists(runner):
        print("⚠️ 跳过引擎框架仓测试：%s 不存在" % runner, flush=True)
        return True
    print("── 前置：引擎框架仓测试（%s）──" % runner, flush=True)
    try:
        proc = subprocess.run([PYTHON, runner], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=base_env,
                              timeout=_BASE_TIMEOUT)
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
        proc = None
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-12:] if proc else []
    for ln in tail:
        print("   " + ln, flush=True)
    print(f"{'✅' if ok else '❌'} 引擎框架仓测试", flush=True)
    return ok


def main():
    fail_fast, serial_mode, real_astrbot, jobs, only, skips = _parse_args(sys.argv[1:])
    serial_files, parallel_files = _collect_files(only, skips)
    # ★ T8：**不许把「0 个测试」当全绿** —— 包仓 tests 是内容侧真源，目录缺失/被改名/
    #   被 --skip 全跳时，旧行为会打印「文件: 0 个，通过 0，失败 0」并 exit 0（假绿）。
    #   这里改成醒目报错 + 退非零（与宿主跑器同口径）。
    if not only and not serial_files and not parallel_files:
        print("!" * 78, flush=True)
        print("!! 没有枚举到任何测试文件：%s" % TESTS_DIR, flush=True)
        print("!! （目录缺失 / 被改名 / 全被 --skip 跳过）——拒绝当「0 个测试=全绿」。", flush=True)
        print("!! 修法：确认包仓 tests/ 在位且含 test_*.py。", flush=True)
        print("!" * 78, flush=True)
        return 1
    if serial_mode:
        parallel_files, serial_files = [], serial_files + parallel_files
    if skips:
        print(f"跳过 {len(skips)} 个文件: {', '.join(skips)}", flush=True)
    if real_astrbot:
        print("使用真实 astrbot（对照模式，较慢）", flush=True)

    # 按调用唯一：并发跑两份全量回归时，固定名 worker 目录会让两份互相覆盖 worker 库
    worker_dir = os.path.join(
        TESTS_DIR, f".run_all_workers_{os.getpid()}_{int(time.time())}")
    tpl_db = None
    if parallel_files:
        shutil.rmtree(worker_dir, ignore_errors=True)
        os.makedirs(worker_dir, exist_ok=True)
        # 每轮跑只建一次空白 schema 模板（只 import 包 + 建表，~0.3s），
        # 之后每个文件复制一份即可，不重复吃建表开销
        tpl_db = os.path.join(worker_dir, "template.db")
        pkg_dir = _find_package_dir()
        if not pkg_dir:
            print("❌ 找不到包目录（<包根>/content/data/commands.json）"
                  "——worker 模板库无法初始化", flush=True)
            shutil.rmtree(worker_dir, ignore_errors=True)
            return 1
        try:
            subprocess.run(
                [PYTHON, "-B", "-c", _TPL_INIT, tpl_db, HOST_ROOT, ENGINE_ROOT, pkg_dir],
                check=True, timeout=120, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as _e:
            print(f"❌ worker 模板库初始化失败: {_e}", flush=True)
            if isinstance(_e, subprocess.CalledProcessError):
                print("--- 模板初始化 stderr ---\n%s" % (_e.stderr or "")[-2000:], flush=True)
            shutil.rmtree(worker_dir, ignore_errors=True)
            return 1

    results = []
    t0 = time.time()
    # 并行主体按并发档放宽超时；串行槽/引擎前置是独占跑 ⇒ 用基线（更严格）
    par_timeout = _test_timeout(jobs)
    if parallel_files and par_timeout != _BASE_TIMEOUT:
        print(f"单文件超时：串行 {_BASE_TIMEOUT}s ｜ 并行 {par_timeout}s（{jobs} 路并发）",
              flush=True)
    # ★ 2026-09-18：测试库是**一次性的** ⇒ 用 NORMAL 同步模式（WAL 下只在 checkpoint
    #   时 fsync）。实测 6 个重门禁并发：FULL 下磁盘队列 1~9、CPU 只占 19%（全在等 IO），
    #   各文件 29~88s；NORMAL 下各 7~25s。真实运行不设此变量 ⇒ 仍是 FULL（耐久性最高）。
    base_env = {**os.environ, "PYTHONIOENCODING": "utf-8",
                "GWEN_SQLITE_SYNC": os.environ.get("GWEN_SQLITE_SYNC", "NORMAL")}
    if not real_astrbot and os.path.isdir(SHIM_DIR):
        # shim astrbot 注入：放 PYTHONPATH 最前（优先于 site-packages 的真实 astrbot）
        _pp = base_env.get("PYTHONPATH", "")
        base_env["PYTHONPATH"] = SHIM_DIR + (os.pathsep + _pp if _pp else "")

    # 0) 前置：引擎框架仓测试（双轨，plan §8-R6）
    framework_ok = _run_framework_tests(base_env)

    # 1) 串行槽（硬编码共享库的文件，保持旧行为：共享 test_game_data.db）
    for f in serial_files:
        name, ok, proc, dt, timed_out = _run_one(f, base_env, timeout=_BASE_TIMEOUT)
        results.append((name, ok))
        _report(name, ok, proc, dt, timed_out)
        if fail_fast and not ok:
            break

    # 2) 并行主体（每文件独立私有库，互不污染）
    if parallel_files:
        def make_env(i):
            return {**base_env, "GWEN_GAME_DB": os.path.join(worker_dir, f"test_game_data_w{i}.db")}

        jobs = max(1, min(jobs, len(parallel_files)))
        # ★ LPT：最长作业优先启动（无记录的文件按 0 排在后面）
        _t = _load_times()
        if _t:
            parallel_files.sort(key=lambda p: -float(_t.get(os.path.basename(p), 0.0)))
        queue = iter(enumerate(parallel_files))
        executor = ThreadPoolExecutor(max_workers=jobs)
        pending = {}
        fail_seen = False

        def submit_next():
            nonlocal fail_seen
            if fail_fast and fail_seen:
                return False
            try:
                i, f = next(queue)
            except StopIteration:
                return False
            pending[executor.submit(_run_one, f, make_env(i), tpl_db, par_timeout)] = f
            return True

        for _ in range(jobs):
            if not submit_next():
                break
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                f = pending.pop(fut)
                name, ok, proc, dt, timed_out = fut.result()
                results.append((name, ok))
                _report(name, ok, proc, dt, timed_out)
                if not ok:
                    fail_seen = True
                submit_next()
        executor.shutdown(wait=True)

    if _RUN_SECS:
        _merged = {**_load_times(), **_RUN_SECS}
        _save_times(_merged)
        _slow = sorted(_RUN_SECS.items(), key=lambda kv: -kv[1])[:3]
        if _slow:
            print("最慢 3 个：%s（已记入 LPT 耗时表，下次按降序启动）"
                  % " · ".join("%s %.0fs" % kv for kv in _slow), flush=True)
    shutil.rmtree(worker_dir, ignore_errors=True)
    rc = _summary(results, t0)
    if not framework_ok:
        print("❌ 引擎框架仓测试未通过（前置门禁）——游戏侧结果仅供参考")
        return 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
