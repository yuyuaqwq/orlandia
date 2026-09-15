# -*- coding: utf-8 -*-
"""v130.7 意见#19 固化测试（test_v1307_job_mech.py）：职业详情『🎯 核心玩法』机制解释行

落地玩家意见 #19（回滚为 new）「出一点职业特殊机制解释」：
  - classes.py 每职业新增 mech 字段（1-2 句核心玩法/核心循环，数据驱动）
  - job_guide.py 详情展示『🎯 核心玩法：{mech}』（desc 后、档位路线前；无 mech 字段兜底不显示）

覆盖：
  ① 『职业 拳师』详情含『🎯 核心玩法』且非空
  ② 12 职业循环断言（classes.py 数据）：mech 字段非空、长度合规、详情均显示且含 mech 原文
  ③ 基础六/隐藏六全量覆盖（BASE_ORDER/HIDDEN_ORDER 各 6 均含 mech）
  ④ 无 mech 字段兜底：不崩、不显示『🎯 核心玩法』行

运行：python tests/test_v1307_job_mech.py（exit=0 全绿）
设计：纯数据 + 纯信息指令，不依赖玩家存档（库走 _engine_harness 机制，不设残留环境变量）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import C, run, FakeEvent, clean_db  # noqa: E402
from content.tables import JOB_GUIDE  # noqa: E402
# B16 收口：宿主 game/data 已删 —— 真源 = 包内 content/tables.py 的同义函数口（逐值等：7 / 0）
from content.tables import job_base_order as _job_base_order, job_hidden_order as _job_hidden_order  # noqa: E402
BASE_ORDER, HIDDEN_ORDER = _job_base_order(), _job_hidden_order()
from _engine_harness import Main as JobGuideCmds  # noqa: E402  （原 game.commands.job_guide 壳 → 驱动口）
# ★ B18-L6（2026-09-14）：『职业』详情渲染随命令整块进包（`content/cmds_job.py`），
#   宿主 `game/commands/job_guide.py` 只剩 `@declared` + 一行转发 ⇒ [④] 的「无 mech 兜底」
#   打桩点与直调口**跟着实现搬家**（`CLASSES` 与 `_jg_detail` 现在都在包内模块上）。
import content.cmds_job as _jg_mod  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")
    return cond


async def job_cmd(msg, jc):
    """直跑 『职业』handler，返回拼接文本"""
    msgs = await run(jc.job_guide, FakeEvent("g1", "u1", msg))
    return "".join(str(x) for x in msgs)


async def main():
    clean_db()  # 建独立测试库（handler 不读档，仅保环境干净）
    jc = JobGuideCmds(None)
    ok = True

    # ===== ① 『职业 拳师』详情含『🎯 核心玩法』且非空 =====
    print("【① 拳师详情】")
    d = await job_cmd("职业 拳师", jc)
    mech_q = C.CLASSES["cls_wu_seng"].get("mech", "")
    ok &= check("『职业 拳师』详情含『🎯 核心玩法』", "🎯 核心玩法" in d, d[:120])
    ok &= check("『职业 拳师』mech 非空且展示原文", bool(mech_q.strip()) and mech_q in d,
                f"mech={mech_q!r}")

    # ===== ② 12 职业循环断言（classes.py 数据） =====
    print("【② 12 职业循环】")
    for cid, g in JOB_GUIDE.items():
        cls = C.CLASSES[cid]
        mech = cls.get("mech")
        ok &= check(f"[{cid}] classes.py mech 字段存在且非空",
                    bool(mech and mech.strip()), repr(mech))
        ok &= check(f"[{cid}] mech 长度合规(<=40 字)", bool(mech) and len(mech) <= 40,
                    f"len={len(mech) if mech else 0}")
        d = await job_cmd(f"职业 {g['name']}", jc)
        ok &= check(f"『职业 {g['name']}』详情含『🎯 核心玩法』", "🎯 核心玩法" in d, d[:120])
        if mech:
            ok &= check(f"『职业 {g['name']}』详情含 mech 原文", mech in d)
        if g["hidden"]:
            ok &= check(f"『职业 {g['name']}』隐藏线详情仍完整", "解锁" in d)

    # ===== ③ 基础六/隐藏六全量覆盖 =====
    print("【③ 分组覆盖】")
    ok &= check("基础六职业全部含 mech",
                all(bool(C.CLASSES[cid].get("mech")) for cid in BASE_ORDER),
                [cid for cid in BASE_ORDER if not C.CLASSES[cid].get("mech")])
    ok &= check("隐藏六职业全部含 mech",
                all(bool(C.CLASSES[cid].get("mech")) for cid in HIDDEN_ORDER),
                [cid for cid in HIDDEN_ORDER if not C.CLASSES[cid].get("mech")])

    # ===== ④ 无 mech 字段兜底：不崩、不显示该行 =====
    print("【④ 无 mech 兜底】")
    _orig_classes = _jg_mod.CLASSES
    try:
        _jg_mod.CLASSES = dict(_orig_classes, cls_wu_seng={})  # 模拟无 mech 字段
        d = _jg_mod._jg_detail("cls_wu_seng")                   # ★ B18-L6：渲染在包内
        ok &= check("无 mech 字段详情不崩", isinstance(d, str) and bool(d), d[:80])
        ok &= check("无 mech 字段不显示『核心玩法』行", "核心玩法" not in d)
        ok &= check("无 mech 字段其余字段仍在", "核心资源" in d and "档位路线" in d)
    finally:
        _jg_mod.CLASSES = _orig_classes

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()) or (1 if failed else 0))