# -*- coding: utf-8 -*-
"""v130.5 技能列表随机提示固化测试（意见 #8 落地）

覆盖：
  ① 技能列表底部不再有固定长引导（旧：『技能学习 <名称>』消耗技能点学会；…指定目标）
  ② 底部改为 TIPS.skill 随机池条目（带 emoji，单行）
  ③ _tip 前缀逻辑：中文开头条目带 💡，emoji 开头条目不带（防双 emoji 冗余）
  ④ 翻页引导『技能列表 N』仍在

运行：python tests/test_v1305_skill_tip.py（exit=0 全绿）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_v1305_skill_tip.db")
os.environ["GWEN_GAME_DB"] = _DB

from _engine_harness import C, clean_db, make_player  # noqa: E402
from _engine_harness import Main  # noqa: E402

passed = failed = 0
G, Q = 1095961596, "gm_t1305"


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ {name}")
    else:
        failed += 1
        print(f"❌ {name} {detail}")


def main():
    clean_db()
    make_player(G, Q, "提示测试", "牧师", level=15)
    m = Main()
    p = m._player(G, Q)
    out = m._skill_list_page(p, 1)
    lines = out.splitlines()

    # ① 长引导已移除
    old = "『技能学习 <名称>』消耗技能点学会"
    check("① 固定长引导已移除", not any(old in ln for ln in lines),
          [ln for ln in lines if "技能学习" in ln][:2])

    # ② 底部为 TIPS.skill 随机池条目
    pool = C.TIPS["skill"]
    tail = lines[-1]
    check("② 底部是 skill 池随机条目", tail in pool or tail in [f"💡 {t}" for t in pool],
          f"tail={tail!r}")

    # ②b 随机提示 ≤20 字（不含 emoji 粗略按 2 计）——池内全部短提示
    too_long = [t for t in pool if len(t) > 22]
    check("②b 池条目全部 ≤22 字符", not too_long, too_long)

    # ③ _tip 前缀逻辑
    for _ in range(30):
        t = m._tip("skill")
        check("③ emoji 开头不带 💡 前缀", not t.startswith("💡"), t)
    for _ in range(30):
        t = m._tip("bag")
        check("③ 中文开头带 💡 前缀", t.startswith("💡"), t)

    # ④ 翻页引导仍在
    check("④ 翻页引导保留", any("看下一页" in ln for ln in lines), lines[-3:])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


main()