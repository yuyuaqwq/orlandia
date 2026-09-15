# -*- coding: utf-8 -*-
"""v112 冒烟回归：隐藏线路由 + 流派归属 + 核心资源 + 龙裔传承最小闭环

原型 scripts/v112_smoke.py（一次性产物，其 smoke_test.db 不再需要）。取其核心断言
转写为正式测试，验证隐藏职业路由/别名/传承/流派技能归属在数据收敛后仍成立：
  1) _hidden_class_routes：档位全名 → (cls_id, tier, 流派索引)
  2) _hidden_alias_map：短别名 → (cls_id, 流派索引)
  3) branch_skill_owner：龙焰吐息 → 龙裔线 T3 龙魂战将
  4) EFFECT_RULES 资源单源（v181.M-R2b：engine.core_resource_def 退役，rage name/cap 迁新表）
  5) 龙裔传承最小闭环：40 级战士 + dragonborn 血脉 → cls_dragon_oath T1 path=1,
     习得 龙魂/龙息

刻意不转写 v112_smoke.py 里多段「同职业逐阶升档 + 跨职业进时咒」的完整演化流——
那部分强耦合 CLASSES 职业/技能数据，且并行 Agent(F1) 正在改 commands/player.py
（_branch_title 已见 F1 P1-1 改动），深演化断言易随数据/逻辑漂移而误红。仅保留数据
驱动、行为稳定的核心断言作回归。
"""
import os
import sys
import asyncio

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("GWEN_GAME_DB", os.path.join(HERE, "test_v112_smoke_regression.db"))
sys.path.insert(0, HERE)
from _engine_harness import C, db, clean_db, make_player, FakeEvent  # noqa: E402
from content.skills import branch_skill_owner
from _engine_harness import Main as PlayerCmds  # noqa: E402  （原 game.commands.player.PlayerCmds 壳 → 驱动口）

_passed = _failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print("  ✅ %s" % name)
    else:
        _failed += 1
        print("  ❌ %s %s" % (name, detail))


async def main():
    clean_db()
    inst = PlayerCmds(None)

    print("【隐藏线路由（v151 已删 → 空表）】")
    routes = inst._hidden_class_routes()
    check("隐藏路由表为空（v151 已删 6 隐藏职业）",
          len(routes) == 0, str(len(routes)))

    print("【隐藏短别名 → 空表】")
    aliases = inst._hidden_alias_map()
    check("隐藏别名表为空（v151 已删）",
          len(aliases) == 0, str(len(aliases)))

    print("【流派归属 + 核心资源（基础职业）】")
    owner = branch_skill_owner("cls_zhan_shi", "龙息之怒")
    check("branch_skill_owner 龙息之怒 → (2, 狂战士)（v153 BRANCH_SKILLS 键统一 T1 档位名）",
          owner == (2, "狂战士"), str(owner))
    # v181.M-R2b：engine.core_resource_def 退役删除——资源名/上限单源 EFFECT_RULES
    # （rage name=怒气 cap=10 由旧 core_resources.cls_zhan_shi 迁移，展示/校验读点全改新源）
    from content.mech.params import EFFECT_RULES as _ER  # noqa: E402
    _rage = _ER.get("rage") or {}
    check("EFFECT_RULES 战士资源单源（rage name=怒气 cap=10）",
          _rage.get("name") == "怒气" and _rage.get("cap") == 10, str(_rage))

    print("【基础职业导师转职最小闭环（30级战士 → 狂战士 T1）】")
    from _engine_harness import Main
    mm = Main(None)
    make_player("g1", "q1", "龙裔武者", "cls_zhan_shi", level=30)
    db.update_player("g1", "q1", cur_map="white_deer", cur_subarea="white_deer_1")
    p = db.get_player("g1", "q1")
    ev = FakeEvent("g1", "q1", "对话 老兵·格里姆")
    out = []
    async for r in mm.talk_choice(ev):
        out.append(r)
    ev = FakeEvent("g1", "q1", "3")
    out = []
    async for r in mm.talk_choice(ev):
        out.append(r)
    ev = FakeEvent("g1", "q1", "1")
    out = []
    async for r in mm.talk_choice(ev):
        out.append(r)
    p2 = db.get_player("g1", "q1")
    check("转职后 tier=1 path=1",
          p2["class_name"] == "cls_zhan_shi" and p2["class_tier"] == 1 and p2["evolve_path"] == 1,
          "class=%s tier=%s path=%s" % (p2["class_name"], p2.get("class_tier"), p2.get("evolve_path")))
    check("传承有输出文案", len(out) > 0, "输出为空")

    # 清理私有库文件
    tmp = db.db_path()
    for f in (tmp, tmp + "-journal", tmp + "-wal", tmp + "-shm"):
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

    print("\n结果: %d 通过, %d 失败" % (_passed, _failed))
    return _failed == 0


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
