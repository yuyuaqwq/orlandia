# -*- coding: utf-8 -*-
"""v130.7 意见#24 列表→序号快捷查看引导固化测试。

覆盖：
  ① TIPS.bag / TIPS.skill 池新增『物品详情/技能详情 <序号>』引导条目
     （≤20字、无重复，与 test_v127_tips 同规则）
  ② 『背包』面板底部随机提示可命中新条目
     （mock random.choice 确定性强制 + 统计 120 次真实随机）
  ③ 『技能列表』面板底部随机提示同理

运行：python tests/test_v1307_list_seq_tip.py（exit=0 全绿）
"""
import os
import re
import sys
import random
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import C, FakeEvent, run, clean_db, make_player  # noqa: E402
from _engine_harness import Main  # noqa: E402
from _engine_harness import db  # noqa: E402

TIP_BAG = "💡 发送『物品详情 <序号>』查看详情"
TIP_SKILL = "🔍 发送『技能详情 <序号>』查看详情"
G, Q = 1095961597, "gm_t1307_seq"

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ {name}")
    else:
        failed += 1
        print(f"❌ {name} {detail}")


# base._tip 的 emoji 前缀规则：条目以 emoji 开头时原样返回，否则补 '💡 ' 前缀
_EMOJI_RE = re.compile(r"^[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


def _tip_forms(pool):
    """池条目的实际渲染形态集合（与 CommandBase._tip 行为一致）。"""
    return {t if _EMOJI_RE.match(t) else "💡 " + t for t in pool}


def _force_choice(needle, orig):
    """mock random.choice：目标池命中新条目时强制返回，其余走原逻辑。"""
    def _c(pool):
        if isinstance(pool, list) and needle and needle in pool:
            return needle
        return orig(pool)
    return _c


async def _bag_panel(m):
    r = await run(m.inventory, FakeEvent(G, Q, "背包"))
    return r[0]


async def _skill_panel(m):
    r = await run(m.skill, FakeEvent(G, Q, "技能 列表"))
    return r[0]


async def main():
    # ---- ① 结构：新条目存在 + ≤20 字 + 无重复（test_v127_tips 同规则）----
    bag_pool, skill_pool = C.TIPS["bag"], C.TIPS["skill"]
    check("① bag 池含新引导条目", TIP_BAG in _tip_forms(bag_pool))
    check("① skill 池含新引导条目", TIP_SKILL in _tip_forms(skill_pool))
    check("① bag 新条目≤20字", len(TIP_BAG) <= 20, f"len={len(TIP_BAG)}")
    check("① skill 新条目≤20字", len(TIP_SKILL) <= 20, f"len={len(TIP_SKILL)}")
    for name, pool in (("bag", bag_pool), ("skill", skill_pool)):
        check(f"① {name} 池无重复", len(set(pool)) == len(pool),
              f"dup={[x for x in set(pool) if pool.count(x) > 1]}")
        over = [t for t in pool if len(t) > 20]
        check(f"① {name} 池每条≤20字", not over, f"过界={over}")

    m = Main()
    clean_db()
    make_player(G, Q, "列表测试", "战士", level=3)
    db.add_item(G, Q, "test_pot", {"name": "测试药水", "type": "药剂", "heal": 20}, count=3)
    db.add_item(G, Q, "test_mat", {"name": "测试矿石", "type": "材料"}, count=5)

    # ---- ② 背包：mock random.choice 确定性命中新条目 ----
    _orig = random.choice
    try:
        random.choice = _force_choice(TIP_BAG.replace("💡 ", "", 1), _orig)
        panel = await _bag_panel(m)
    finally:
        random.choice = _orig
    check("② 背包面板底部命中新引导(强制)", TIP_BAG in panel, panel[-80:])
    check("② 背包仍渲染列表序号", all(f"{i}. " in panel for i in (1, 2)), panel[:200])

    # ---- ② 背包：统计 120 次真实随机 ----
    forms = _tip_forms(bag_pool)
    seen = []
    for _ in range(120):
        seen.append((await _bag_panel(m)).splitlines()[-1])
    bad = [s for s in set(seen) if s not in forms]
    check("② 背包120次底部提示均来自bag池", not bad, f"异常行={bad}")
    check("② 背包120次命中新条目(出现%d次)" % seen.count(TIP_BAG), TIP_BAG in seen)

    # ---- ③ 技能列表：mock random.choice 确定性命中新条目 ----
    try:
        random.choice = _force_choice(TIP_SKILL, _orig)
        panel = await _skill_panel(m)
    finally:
        random.choice = _orig
    check("③ 技能列表底部命中新引导(强制)", TIP_SKILL in panel, panel[-80:])
    check("③ 技能列表渲染序号行", re.search(r"^\d+\..+\[", panel, re.M) is not None, panel[:120])

    # ---- ③ 技能列表：统计 120 次真实随机 ----
    forms = _tip_forms(skill_pool)
    seen = []
    for _ in range(120):
        seen.append((await _skill_panel(m)).splitlines()[-1])
    bad = [s for s in set(seen) if s not in forms]
    check("③ 技能列表120次底部提示均来自skill池", not bad, f"异常行={bad}")
    check("③ 技能列表120次命中新条目(出现%d次)" % seen.count(TIP_SKILL), TIP_SKILL in seen)

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


asyncio.run(main())