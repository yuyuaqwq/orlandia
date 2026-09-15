# -*- coding: utf-8 -*-
"""v130.7 F05 意见#29：注册重名检查 固化测试

覆盖：
  ① 注册『艾琳』成功 → 另一 QQ 注册『艾琳』→ 被拒 + 友好重名提示，且不落库
  ② 不同名注册成功（名字槽正常放行，不误伤）
  ③ 截断逻辑不回归：超长名字（>12 字）仍截断并提示
  ④ 超长名截断后与前人重名 → 仍拒绝（重名检查在截断之后，防顺序回归）

运行：python tests/test_v1307_name_dup.py（exit=0 全绿）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import db, FakeEvent, run, clean_db  # noqa: E402
from _engine_harness import Main  # noqa: E402

passed = failed = 0

G1, G2 = "dup_g1", "dup_g2"
Q_WIN, Q_DUP, Q_OTHER, Q_LONG, Q_DUP12, Q_DUP13, Q_12NAME = (
    "dup_q_win", "dup_q_dup", "dup_q_other", "dup_q_long", "dup_q_a", "dup_q_b", "dup_q_c",
)


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ {name}")
    else:
        failed += 1
        print(f"❌ {name} {detail}")


async def main():
    m = Main(None)
    DUP_TEXT = "这个名字已经有人用啦，换一个吧～"

    # ---- ① 重名拒绝 ----
    clean_db()
    r1 = await run(m.register, FakeEvent(G1, Q_WIN, "注册 艾琳 女"))
    t1 = "".join(str(x) for x in r1)
    check("① 首次注册『艾琳』成功", "欢迎来到奥兰迪亚大陆，艾琳" in t1, t1[:120])
    check("① 首位玩家已落库", db.get_player(G1, Q_WIN) is not None)
    r2 = await run(m.register, FakeEvent(G1, Q_DUP, "注册 艾琳 女"))
    t2 = "".join(str(x) for x in r2)
    check("① 重名被拒+友好提示", "已经有人用啦" in t2 and "换一个吧" in t2, t2[:120])
    check("① 提示即完整文案", t2.strip() == DUP_TEXT, t2[:120])
    check("① 被拒 QQ 未落库", db.get_player(G1, Q_DUP) is None)
    check("① 同群重名仍拒（跨群共用语义）",
          "已经有人用啦" in "".join(str(x) for x in await run(m.register, FakeEvent(G2, Q_OTHER, "注册 艾琳 女"))))
    check("① 原名未被覆盖", db.get_player(G1, Q_WIN)["name"] == "艾琳")

    # ---- ② 不同名注册成功 ----
    r3 = await run(m.register, FakeEvent(G1, Q_OTHER, "注册 露西 女"))
    t3 = "".join(str(x) for x in r3)
    check("② 不同名『露西』注册成功", "欢迎来到奥兰迪亚大陆，露西" in t3, t3[:120])
    check("② 新玩家已落库", db.get_player(G1, Q_OTHER) is not None)

    # ---- ③ 超长名字仍截断（不回归） ----
    long_name = "格温艾琳露西亚梅尔菲丝卡米拉"  # 14 字 → 截断 12 字
    r4 = await run(m.register, FakeEvent(G1, Q_LONG, f"注册 {long_name} 男"))
    t4 = "".join(str(x) for x in r4)
    check("③ 超长名截断提示", f"已截断为『{long_name[:12]}』" in t4, t4[:120])
    check("③ 注册成功", "欢迎来到奥兰迪亚大陆" in t4, t4[:120])
    p4 = db.get_player(G1, Q_LONG)
    check("③ 落库名为截断后 12 字", p4 is not None and p4["name"] == long_name[:12], str(p4))

    # ---- ④ 截断后与前人重名 → 仍拒绝 ----
    n12 = "甲乙丙丁戊己庚辛壬癸子丑"  # 12 字，先占位
    r5 = await run(m.register, FakeEvent(G1, Q_12NAME, f"注册 {n12} 男"))
    check("④ 12 字名注册成功", "欢迎来到奥兰迪亚大陆" in "".join(str(x) for x in r5))
    r6 = await run(m.register, FakeEvent(G1, Q_DUP13, f"注册 {n12}寅 女"))
    t6 = "".join(str(x) for x in r6)
    check("④ 截断后重名仍拒", "已经有人用啦" in t6, t6[:120])
    check("④ 超长重名者未落库", db.get_player(G1, Q_DUP13) is None)

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


import asyncio

asyncio.run(main())