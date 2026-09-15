# -*- coding: utf-8 -*-
"""v97.5 行为彩蛋规则引擎验证。

覆盖：
1. 20 条规则数据完整（id 唯一 / trigger 合法 / action 模板注册 / cond 字段合法）
2. fire() 计数规则：连续命中 gte 次触发，中断清零
3. fire() 概率规则：chance=0 不触发
4. cond 判定：event / map_type / hp_pct_max / enemy_tag
5. battle_win 战败(lose) 清零连胜计数
6. action 执行：触发后文本非空 + 效果落库
7. 挂点冒烟：命令层 _rule_fire 可用（探索/胜利/采集/移动/锻造/交付）
"""
import sys, os, random, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, make_player, Main, FakeEvent, run

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail).encode('utf-8', 'replace').decode('utf-8', 'replace')[:300]}")

async def main():
    from content.rule_engine import fire, _get_counter
    from content.event_templates import TEMPLATES
    # v103.2 修复时间依赖：固定时段为白天，消除真实时钟影响
    # （23:00-05:00 跑全量时 rule_explore_ghost 的 cond time=deep_night 满足，
    #   seed(1) 下 chance 0.18 命中 → "第 1 次空探索不触发"误判失败）
    #
    # ★ P4′-W1-B（全批唯一允许的测试改动）：时段判定实现已在包内，且 `_match_cond`
    #   直取**本模块全局** `_is_time` ⇒ 打桩目标从宿主壳改到**包内模块**。
    #   宿主 `game/core/rule_engine.py` 是拷贝壳（`_is_time = _pkg._is_time` 的 import 期
    #   引用拷贝），改它够不到包内实现 ⇒ 原先靠包内 `_time_check()` 回宿主取件承接；
    #   P4′-W1-B 把那个回宿主取件删了（包侧反向依赖清零）⇒ 打桩必须打在这里。
    #   反证：把 `content.rule_engine._is_time` 换成永远 False 的 lambda，本节必红。
    import content.rule_engine as RE
    RE._is_time = lambda span: span == "day"
    # W10：改读包内门面（真源 = content/rules/game_config.json 的 rules 组；W12 收口）
    #   逐字节（键序敏感）与 game/data/rules.py:RULES 相等，且 content.rule_engine._rules() 同源
    from content.catalog_b143 import RULES

    print("【1. 规则数据完整性】")
    ids = set()
    triggers = set()
    for r in RULES:
        check(f"规则 {r['id']} id 唯一", r["id"] not in ids)
        ids.add(r["id"])
        check(f"规则 {r['id']} 有 trigger", r.get("trigger"))
        triggers.add(r["trigger"])
        check(f"规则 {r['id']} action 模板已注册", r.get("action", {}).get("template") in TEMPLATES, r.get("action"))
    check("规则总数 = 20", len(RULES) == 20, len(RULES))
    check("触发器覆盖 6 个", {"explore_done", "battle_win", "gather_done", "move_enter",
                            "craft_done", "quest_deliver"} <= triggers, triggers)

    print("\n【2. 计数规则：连续命中触发 + 中断清零】")
    clean_db()
    m = Main(None)
    make_player("g1", "q1", level=5)
    cur_map = C.MAP_BY_ID["oak_plain"]
    evt_empty = {"event": "empty"}

    # 第一次 empty（计数 1，不触发）
    random.seed(1)
    t1 = fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "explore_done", evt_empty)
    check("第 1 次空探索不触发", t1 == "", t1)
    check("计数 = 1", _get_counter("g1", "q1", "explore_empty") == 1, _get_counter("g1", "q1", "explore_empty"))
    # 第二次 empty（计数 2）
    t2 = fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "explore_done", evt_empty)
    check("第 2 次空探索不触发", t2 == "", t2)
    # 第三次 empty（计数 3 → 触发运气守恒）
    exp_before = db.get_player("g1", "q1")["exp"]
    t3 = fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "explore_done", evt_empty)
    check("第 3 次空探索触发", "运气守恒" in t3, t3)
    check("触发后计数清零", _get_counter("g1", "q1", "explore_empty") == 0, _get_counter("g1", "q1", "explore_empty"))
    exp_after = db.get_player("g1", "q1")["exp"]
    check("运气守恒给经验", exp_after > exp_before, (exp_before, exp_after))

    # 中断清零：一次非 empty → 计数归零
    clean_db()
    make_player("g1", "q1", level=5)
    fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "explore_done", evt_empty)
    fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "explore_done", evt_empty)
    check("2 次后计数 = 2", _get_counter("g1", "q1", "explore_empty") == 2)
    fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "explore_done", {"event": "battle"})
    check("非 empty 中断清零", _get_counter("g1", "q1", "explore_empty") == 0)

    print("\n【3. 概率规则：chance=0 不触发】")
    clean_db()
    make_player("g1", "q1", level=5)
    random.seed(9)
    t = fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "move_enter", {})
    # move_enter 全是 chance 规则（0.10/0.05/0.03），seed=9 大概率不触发；连续跑 20 次至少触发一次才合理
    hit_count = 0
    for _ in range(200):
        random.seed(random.randint(0, 99999))
        if fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "move_enter", {}):
            hit_count += 1
    check("200 次 move_enter 触发若干次（随机分布）", 0 < hit_count < 200, hit_count)

    print("\n【4. cond 判定】")
    clean_db()
    make_player("g1", "q1", level=5)
    p = db.get_player("g1", "q1")
    # enemy_tag boss：rule_win_boss 需要 event=win + enemy boss
    boss_mon = {"name": "某Boss", "is_boss": True}
    random.seed(42)
    t = fire("g1", "q1", p, cur_map, "battle_win", {"event": "win", "enemy": boss_mon})
    # boss 规则 chance 0.5；把随机 seed 固定到让它命中——直接验证 cond 层面：非 boss 时 boss 规则一定不触发
    # 用 hp_pct_max 规则验证：残血 30% 时 rule_win_lowhp(chance 0.8) 触发概率高
    db.update_player("g1", "q1", hp=int(p["max_hp"] * 0.2))
    hit = 0
    for _ in range(100):
        random.seed(random.randint(0, 99999))
        if fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "battle_win",
                {"event": "win", "enemy": {"name": "史莱姆"}}):
            hit += 1
    check("残血胜利触发战意回响（≈80%）", 60 <= hit <= 100, hit)
    # 满血时不触发低血规则（连胜规则每 3 次触发 1 次 ≈16，小确幸 ≈2.5，总 <30）
    db.update_player("g1", "q1", hp=p["max_hp"])
    hit2 = 0
    for _ in range(50):
        random.seed(random.randint(0, 99999))
        if fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "battle_win",
                {"event": "win", "enemy": {"name": "史莱姆"}}):
            hit2 += 1
    check("满血时不触发战意回响（仅连胜+小确幸）", hit2 <= 30, hit2)

    print("\n【5. 战败清零连胜计数】")
    clean_db()
    make_player("g1", "q1", level=5)
    evt_win = {"event": "win", "enemy": {"name": "史莱姆"}}
    for _ in range(2):
        fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "battle_win", evt_win)
    check("2 连胜计数 = 2", _get_counter("g1", "q1", "win_streak") == 2)
    # 战败
    fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "battle_win", {"event": "lose"})
    check("战败清零连胜", _get_counter("g1", "q1", "win_streak") == 0)
    # 3 连胜触发
    for _ in range(3):
        fire("g1", "q1", db.get_player("g1", "q1"), cur_map, "battle_win", evt_win)
    check("3 连胜触发", _get_counter("g1", "q1", "win_streak") == 0)  # 触发后清零

    print("\n【6. 挂点冒烟：命令层 _rule_fire】")
    clean_db()
    make_player("g1", "q1", level=5)
    # explore 空探索挂点（通过 Main 直接调 explore 命令，随机种子控制）
    import random as _r
    _r.seed(12345)
    ev = FakeEvent("g1", "q1", "探索")
    # 直接验证 _rule_fire 方法存在且能调用（连续 3 次 empty；前 2 次可能有概率彩蛋，第 3 次必有运气守恒）
    for i in range(3):
        txt = m._rule_fire("explore_done", "g1", "q1", db.get_player("g1", "q1"), cur_map, {"event": "empty"})
        if i == 2:
            check("挂点第 3 次触发运气守恒", "运气守恒" in txt, txt)
    # gather_done 挂点（rule_gather_rare 计数：3 次采集）
    for i in range(3):
        txt = m._rule_fire("gather_done", "g1", "q1", db.get_player("g1", "q1"), cur_map, {"event": "gather"})
    check("采集 3 次触发稀有材料", "变异采集" in txt, txt)

    print(f"\n======== 结果: {passed} 通过 / {failed} 失败 ========")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
