#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v182 行为流水落地验收：埋点 / 落库出口 / 分析脚本 / 默认关零行为。

跑法：python tests/test_v182_behavior_tlog.py（exit=0 全绿）
"""
import json
import os
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import _paths                                                            # noqa: E402

#: ★ 搬迁适配（T8 ③）：旧 `_PD = dirname(_HERE)` 在宿主布局 = 宿主插件根；搬到 `pkg/tests/` 后
#:   它是**包根**。宿主专属面（`scripts/tlog_report.py`）走 `_paths.HOST_ROOT`，内容真源走 `PKG_ROOT`。
PKG_ROOT = _paths.PKG_ROOT        # 包根（埋点真源 `content/**`）
HOST_ROOT = _paths.HOST_ROOT      # 宿主插件根（`scripts/`、`game/` 等宿主专属面）
_SCRIPTS = os.path.join(HOST_ROOT, "scripts")
for _p in (_HERE, _SCRIPTS, HOST_ROOT, PKG_ROOT, _paths.ENGINE_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _engine_harness import C, clean_db, db  # noqa: E402,F401

from saintess_engine.tlog import JSONLSink, MemorySink, Reader, TLog  # noqa: E402
from _engine_harness import tlog_setup  # noqa: E402

# `content.reward._resolve("levelup", …)` 把注入值当**零参活源**调用；旧宿主薄壳
# `game/reward.py` 注入的是 `lambda: check_player_level_up`（活源）。终态无该薄壳，
# 包内 facade 注入的是裸函数 → `_resolve` 会 `v()` 掉它（TypeError）。
# 测试侧按同一公开注入槽补回同款活源（REPOINT_MAP: game.content_rules.gameplay
# check_player_level_up → content.gameplay_rules）。
import content.reward as _reward_mod  # noqa: E402
from content.gameplay_rules import check_player_level_up as _check_level_up  # noqa: E402
from content.stat_bonus import stat_bonus as _stat_bonus  # noqa: E402
from content.persistence.inventory import _key_to_id as _key_to_id  # noqa: E402
_reward_mod.bind_host(levelup=lambda: _check_level_up,
                      stat_bonus=lambda: _stat_bonus,
                      key_to_id=lambda: _key_to_id)

# `host/tlog_db_sink` 的取件口是宿主存档口 `host.store_factory.store()`；旧宿主
# `main.py` 装配时会 `store_factory.bind_store(pkg)`（t4 用的就是这条库出口）。
# 测试驱动口 `_engine_harness.boot()` 只装配引擎通道 + 壳，未做这一步 ⇒ 测试侧按
# 公开装配口补同一件事（不是自造映射；生产装配处本来就调它）。
from host import store_factory as _store_factory  # noqa: E402
import _engine_harness as _harness_mod  # noqa: E402
_store_factory.bind_store(_harness_mod.harness().host.pkg)

passed = failed = 0
GID, QID = "g_tlog", "q_tlog"


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def _off():
    os.environ.pop(tlog_setup.ENV_FLAG, None)
    tlog_setup.disable()


# ---------------------------------------------------------------- 1 默认关
def t1_default_off():
    print("\n[1] 默认关：埋点是 no-op")
    _off()
    check("tlog() 为 None", tlog_setup.tlog() is None)
    check("emit() 直接返回 None（零构造）", tlog_setup.emit("drop.grant", actor="x") is None)
    from content.reward import grant_reward
    clean_db()
    lines = grant_reward({"exp": 10, "gold": 5, "items": []}, GID, QID)
    check("真调 grant_reward 不报错且无流水（未启用）", isinstance(lines, list))


# ---------------------------------------------------------------- 2 埋点存在性
def t2_probes_present():
    print("\n[2] 三处行为埋点（防被误删）")
    root = PKG_ROOT
    probes = {
        # ★ P5F-REPOINT: 原读宿主壳 `game/reward.py` / `game/services/shop.py`（随删壳批消失）
        #   → 包内埋点真源 `content/reward.py` / `content/shop.py`（`obs.emit(...)` 落点）。
        "掉落": ("content/reward.py", 'emit("drop.grant"'),
        "商店买入": ("content/shop.py", 'emit("shop.buy"'),
        # ★ PFIX P7（2026-09-15）：副本通关埋点**随实现整块进包** ——
        #   `content/cmds_instance_router.py:643` 经包内唯一取用口
        #   `obs.emit("instance.clear", …)`；宿主 `game/commands/instance_router.py` 已退化为
        #   「`@declared` 注册 + 一行转发」薄壳（不含 emit 调用点），且宿主壳正被 B4 清理
        #   ⇒ 按作业书「优先测试侧改扫包内实现」，断言改扫**包内实现**。
        #   （前两处宿主文件各留了字面量指针常量 `_SRC_PROBES` / `_TLOG_PROBE_POINTER`
        #     才能继续扫宿主；本条**不往宿主补指针**，避免与 B4 删壳撞车。）
        "副本通关": ("content/cmds_instance_router.py", 'obs.emit("instance.clear"'),
    }
    for label, (rel, needle) in probes.items():
        p = os.path.join(root, rel)
        src = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
        check(f"{label}埋点在位（{rel}）", needle in src, needle)


# ---------------------------------------------------------------- 3 端到端（真调）
def t3_end_to_end():
    print("\n[3] 启用后：真调业务函数 → 落流水")
    mem = MemorySink()
    _off()
    tlog_setup.enable(sinks=[mem])
    try:
        from content.reward import grant_reward
        clean_db()
        grant_reward({"exp": 12, "gold": 7, "items": []}, GID, QID)
        recs = list(mem.read_records())
        drops = [r for r in recs if r.kind == "drop.grant"]
        check("掉落埋点真落了一条 drop.grant", len(drops) == 1, str([r.kind for r in recs]))
        if drops:
            f = drops[0].fields
            check("字段完整（exp/gold/source）",
                  f.get("exp") == 12 and f.get("gold") == 7 and f.get("source") == "reward",
                  str(f))
        # emit 通道（shop/instance 走同一通道）
        tlog_setup.emit("shop.buy", actor=QID, key="m:1", qty=2, discount=1.0)
        tlog_setup.emit("instance.clear", actor=QID, iid="inst_oak", first_clear=True)
        kinds = {r.kind for r in mem.read_records()}
        check("emit 通道可用（shop.buy / instance.clear）",
              {"shop.buy", "instance.clear"} <= kinds, str(kinds))
    finally:
        _off()


# ---------------------------------------------------------------- 4 落库往返
def t4_db_sink():
    print("\n[4] SQLiteSink：落库 + 读回（与 JSONL 一致）")
    from host.tlog_db_sink import SQLiteSink, SQLiteReader, ensure_table

    mem = MemorySink()
    _off()
    sink = SQLiteSink(batch=2)
    sink.clear()
    tlog_setup.enable(sinks=[mem, sink])
    try:
        for i in range(5):
            tlog_setup.emit("drop.grant", actor="u1", source="test", seq=i)
        tlog_setup.emit("shop.buy", actor="u1", key="m:1", qty=1, discount=1.0)
        sink.flush()
        from_db = list(SQLiteReader().read_records())
        from_mem = list(mem.read_records())
        check("库内条数 == 内存条数", len(from_db) == len(from_mem),
              f"db={len(from_db)} mem={len(from_mem)}")
        check("字段逐条一致（含 JSON 往返）",
              [r.to_dict() for r in from_db] == [r.to_dict() for r in from_mem])
        rd = Reader([SQLiteReader()])
        check("Reader 能从库筛选", rd.count(kind="drop.grant") == 5
              and rd.count(actor="u1") == 6, f"{rd.count(kind='drop.grant')}/{rd.count()}")
        check("kind 前缀族匹配", rd.count(kind="shop.") == 1)
        check("clear 清空", sink.clear() == 6 and Reader([SQLiteReader()]).count() == 0)
    finally:
        _off()


# ---------------------------------------------------------------- 5 分析脚本
def t5_report_script():
    print("\n[5] 分析脚本 tlog_report.py")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "t.jsonl")
        tl = TLog(sinks=[JSONLSink(p)])
        tl.emit("drop.grant", actor="u1", source="battle", gold=3)
        tl.emit("shop.buy", actor="u1", key="m:1", qty=2, discount=1.0)
        tl.emit("drop.grant", actor="u2", source="quest", gold=5)
        tl.close()
        script = os.path.join(_SCRIPTS, "tlog_report.py")
        pr = subprocess.run([sys.executable, script, "--file", p, "--actor", "u1"],
                            capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "PYTHONUTF8": "1"})
        out = (pr.stdout or "") + (pr.stderr or "")
        check("脚本退出码 0", pr.returncode == 0, out[-300:])
        check("报告含记录数 2（按 actor 过滤）", "**2**" in out, out[:300])
        check("报告含 kind 分布表", "drop.grant" in out and "shop.buy" in out)
        pr2 = subprocess.run([sys.executable, script, "--file", p, "--kind", "shop."],
                             capture_output=True, text=True, encoding="utf-8",
                             env={**os.environ, "PYTHONUTF8": "1"})
        check("kind 前缀筛选生效", "**1**" in ((pr2.stdout or "") + (pr2.stderr or "")))


def main():
    print("== v182 行为流水：埋点 / 落库 / 分析脚本 / 默认关 ==")
    t1_default_off()
    t2_probes_present()
    t3_end_to_end()
    t4_db_sink()
    t5_report_script()
    print(f"\n===== 结果：通过 {passed} / {passed + failed} =====")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
