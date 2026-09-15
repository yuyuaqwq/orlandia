#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v185 门禁「有牙」实测 —— `tests/test_v185_instance_admission.py` 的伴随自检。

**为什么要有这个文件**：冻结比对门禁最危险的失败态不是"红"，是**假绿** —— 矩阵里某条
断言写宽了（或压根没覆盖到某个维度），改坏代码它照样全绿，那这道门禁就只是装饰。
本文件用**猴补破坏法**把这一点证伪：故意破坏 7 种东西，断言门禁**真的变红**。

破坏清单（全部在内存里做，跑完还原，**不碰仓库源文件**）：

| # | 破坏 | 期望谁变红 |
|---|---|---|
| 1 | 措辞漂移（`text_leader_only` 改一句） | `t1` 开本矩阵 |
| 2 | 措辞漂移（`stamina_short_msg` 改一句） | `t2` 措辞链 |
| 3 | 副作用时机回退（`consume` 塞回 `check`＝旧的链中段白扣） | `t6` D1 白扣反证 |
| 4 | 链顺序改了（成员关整段挪到最后） | `t1` 顺序刻度 |
| 5 | 删掉一关（`not_full`） | `t4` 加入链矩阵 |
| 6 | 偷改**旧源码片段**（改冻结文本） | `t0` 片段 sha 自检 |
| 7 | 只偷改**冻结函数体**（片段不动） | `t0` 冻结体 sha 自检 |

跑法：python tests/test_v185_gate_teeth.py（exit=0 = 7 项破坏全部被门禁抓到）
"""
import importlib.util
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _engine_harness import C  # noqa: E402,F401  （先 import _engine_harness：装配引擎通道 + sys.path）
from content.flow import instance_gate  # noqa: E402

GATE = os.path.join(_HERE, "test_v185_instance_admission.py")
TMP = os.path.join(_HERE, "_tmp_v185_teeth_probe.py")

passed = failed = skipped = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def _load(name):
    """按文件路径加载门禁模块（不执行它的 main）——每个破坏案例一份独立模块，互不串味。"""
    spec = importlib.util.spec_from_file_location(name, GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _red(mod, fn_name):
    """跑门禁里的某节，返回 (新增红, 新增绿)。抛错也算红（崩了同样是"门禁有反应"）。

    ★ P5D-REPOINT：宿主壳随 game/** 退役后，包内链不再自带「每次链入口把宿主模块的
    文案函数回挂包内全局」那一步 ⇒ 本文件的猴补（`instance_gate.text_leader_only = …`）
    对包内链会静默失效（有牙测试会**假绿**）。故在调用门禁某节前显式触发门禁模块自己的
    `_bind_text_funcs()`（逐字等价宿主壳同名机制），让猴补照旧打在包内真读点上。
    """
    f0, p0 = mod.failed, mod.passed
    _bind = getattr(mod, "_bind_text_funcs", None)
    if _bind is not None:
        _bind()
    try:
        getattr(mod, fn_name)()
    except Exception as e:
        print(f"    （{fn_name} 抛错：{type(e).__name__}: {e}）")
        return (1, mod.passed - p0)
    return (mod.failed - f0, mod.passed - p0)


def main():
    global skipped
    print("== v185 门禁有牙实测（猴补破坏 → 断言变红；不写仓库源文件） ==")
    if not os.path.exists(GATE):
        print(f"  ⏭️ 没有 {os.path.basename(GATE)}，本伴随自检跳过（exit=0）")
        skipped += 1
        return 0
    G = instance_gate

    g0 = _load("v185_probe_warmup")
    need = [n for n in ("t0_freeze_self_check", "t1_open_matrix", "t2_open_text_verbatim",
                        "t4_join_matrix", "t6_d1_white_deduct") if not hasattr(g0, n)]
    check(f"门禁模块可加载且五节齐备（{'/'.join(need) if need else 't0/t1/t2/t4/t6'}）",
          not need, f"缺 {need}")

    # ── 1. 措辞漂移：队长关 ──
    m = _load("v185_probe_1")
    orig = G.text_leader_only
    try:
        G.text_leader_only = lambda *a, **k: "只有队长才能开启副本！（措辞被偷改）"
        f, p = _red(m, "t1_open_matrix")
    finally:
        G.text_leader_only = orig
    check(f"破坏①措辞漂移（队长关）→ t1 变红（红 {f} / 绿 {p}）", f >= 1, f"红 {f}")

    # ── 2. 措辞漂移：体力不足 ──
    m = _load("v185_probe_2")
    orig = G.stamina_short_msg
    try:
        G.stamina_short_msg = lambda cost, cur, action="行动": f"体力不足（被偷改）{cost}/{cur}"
        f, p = _red(m, "t2_open_text_verbatim")
    finally:
        G.stamina_short_msg = orig
    check(f"破坏②措辞漂移（体力不足）→ t2 变红（红 {f} / 绿 {p}）", f >= 1, f"红 {f}")

    # ── 3. 副作用时机回退：通过即立刻扣（等价旧的链中段白扣） ──
    m = _load("v185_probe_3")
    orig = G.open_admission

    def _eager(ctx):
        adm = orig(ctx)
        rules = []
        for r in adm.rules:
            if r.consume is not None:
                def _mk(rr):
                    def _check(c):
                        out = rr.check(c) if rr.check else None
                        if out is None or out is True:
                            rr.consume(c)
                        return out
                    return G.Rule(rr.name, check=_check, reason=rr.reason)
                rules.append(_mk(r))
            else:
                rules.append(r)
        return G.Admission(rules, name=adm.name, mode=adm.mode, reason=adm.reason)

    try:
        G.open_admission = _eager
        f, p = _red(m, "t6_d1_white_deduct")
    finally:
        G.open_admission = orig
    check(f"破坏③副作用时机回退（白扣复现）→ t6 变红（红 {f} / 绿 {p}）", f >= 1, f"红 {f}")

    # ── 4. 链顺序改了：成员关整段挪到最后 ──
    m = _load("v185_probe_4")
    orig = G.open_admission

    def _reorder(ctx):
        adm = orig(ctx)
        rs = sorted(adm.rules, key=lambda r: 1 if r.name.startswith("member:") else 0)
        return G.Admission(rs, name=adm.name, mode=adm.mode, reason=adm.reason)

    try:
        G.open_admission = _reorder
        f, p = _red(m, "t1_open_matrix")
    finally:
        G.open_admission = orig
    check(f"破坏④链顺序被改（成员关挪后）→ t1 变红（红 {f} / 绿 {p}）", f >= 1, f"红 {f}")

    # ── 5. 删掉一关：满员 ──
    m = _load("v185_probe_5")
    orig = G.join_admission

    def _drop_full(ctx):
        adm = orig(ctx)
        return G.Admission([r for r in adm.rules if r.name != "not_full"],
                           name=adm.name, mode=adm.mode, reason=adm.reason)

    try:
        G.join_admission = _drop_full
        f, p = _red(m, "t4_join_matrix")
    finally:
        G.join_admission = orig
    check(f"破坏⑤删掉一关（满员）→ t4 变红（红 {f} / 绿 {p}）", f >= 1, f"红 {f}")

    # ── 6/7. 偷改冻结体（改的是**临时副本**，不动仓库里的门禁文件） ──
    with io.open(GATE, encoding="utf-8") as fh:
        body_src = fh.read()

    def _tampered_run(tag, new_src):
        with io.open(TMP, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_src)
        try:
            spec = importlib.util.spec_from_file_location(tag, TMP)
            tm = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tm)
            return _red(tm, "t0_freeze_self_check")
        finally:
            if os.path.exists(TMP):
                os.remove(TMP)

    frag_marker = '"队友还没有角色！无法开本～"'
    check("门禁文件里找到片段冻结标记（6/7 两项破坏的前提）", frag_marker in body_src)
    if frag_marker in body_src:
        f, p = _tampered_run("v185_probe_6",
                             body_src.replace(frag_marker, '"队友还没有角色！无法开本（偷改）～"', 1))
        check(f"破坏⑥偷改旧源码片段 → t0 变红（红 {f} / 绿 {p}）", f >= 1, f"红 {f}")
    def_marker = "def _old_resume_decision(inst, ok_members, sim):\n"
    check("门禁文件里找到冻结函数 def 行（7 的前提）", def_marker in body_src)
    if def_marker in body_src:
        f, p = _tampered_run(
            "v185_probe_7",
            body_src.replace(def_marker, def_marker + "    # 偷改（只动函数体，不动旧源码片段）\n", 1))
        check(f"破坏⑦只偷改冻结函数体 → t0 变红（红 {f} / 绿 {p}）", f >= 1, f"红 {f}")

    # ── 收尾：所有猴补已还原 → 门禁本体必须仍然全绿（防猴补泄漏） ──
    m = _load("v185_probe_final")
    f, p = _red(m, "t0_freeze_self_check")
    f2, p2 = _red(m, "t1_open_matrix")
    check(f"收尾：还原后门禁本体仍全绿（t0 红 {f} / t1 红 {f2}，绿 {p + p2}）",
          f == 0 and f2 == 0, f"t0 红 {f} / t1 红 {f2}")

    print(f"\n===== 结果：{passed} 通过 / {failed} 失败（闸门有牙 = 7 项破坏全部被抓到）=====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
