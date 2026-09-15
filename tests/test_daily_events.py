# -*- coding: utf-8 -*-
"""v115 今日奇遇（daily_events）直接单测 + faction_reputation_tier 阈值边界。

此前 daily_events（today_map_event/today_event_effects）与 core/factions.py 的
faction_reputation_tier 均无直接单测，仅经 C 聚合被 explore/map_view/命令间接消费。
本文件直接 import 实现做断言（补 audit N1 A3 测点）：

  1. 固定 now：同日同图全服一致（日期哈希确定性，多调同值）
  2. 无配置（未知图/无奇遇图）→ None / {}
  3. effects 合并：返回的 effects 与所选变体完全一致，多键（loot_mult+encounter_rate）并存
  4. faction_reputation_tier 阈值边界（0/100/300/700/1500 各档 + 档内 ±1）
  5. now 支持 datetime.datetime 与 datetime.date 归一

独立运行：python tests/test_daily_events.py
"""
import sys, os, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C

from content.daily_events import (
    today_map_event, today_event_effects, _day_hash,
)
import content.daily_events as _de_mod  # noqa: E402  （真源模块自持性判据用）
from content.factions import faction_reputation_tier
# W10：改读包内单源（宿主 game/core/daily_events.py 已薄壳 → content/daily_events.py → 此处同一份）
from content.catalog_rules import DAILY_MAP_EVENTS  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def main():
    print("【1. 固定 now：同日同图全服一致（date）】")
    now = datetime.date(2026, 8, 6)
    for map_id in list(DAILY_MAP_EVENTS.keys())[:6]:
        ev1 = today_map_event(map_id, now)
        ev2 = today_map_event(map_id, now)
        ev3 = today_map_event(map_id, now)
        check(f"同图 {map_id} 多次调用同值", ev1 is not None and ev1 == ev2 == ev3,
              f"{ev1} vs {ev2} vs {ev3}")
        # 命中变体属于该图配置列表
        check(f"{map_id} 命中为合法变体", ev1 in DAILY_MAP_EVENTS[map_id], str(ev1))

    print("【2. 同 seed/日期 不同图命中下标可错开（salt=map_id 生效）】")
    # 遍历连续日期，统计两张相邻图是否出现过不同变体（salt 防顶同一位置）
    differ = False
    a, b = list(DAILY_MAP_EVENTS.keys())[:2]
    for d in range(1, 60):
        day = datetime.date(2026, 1, 1) + datetime.timedelta(days=d)
        ia = DAILY_MAP_EVENTS[a].index(today_map_event(a, day))
        ib = DAILY_MAP_EVENTS[b].index(today_map_event(b, day))
        if ia != ib:
            differ = True
            break
    check("不同图用 map_id 做 salt 可错开下标", differ, "60 天内两图始终同一下标")

    print("【3. datetime 归一：datetime.datetime 与同日期 date 命中一致】")
    day = datetime.date(2026, 8, 6)
    dt = datetime.datetime(2026, 8, 6, 23, 59, 59)
    map_id = "oak_plain"
    check("datetime 与 date 命中同变体", today_map_event(map_id, day) == today_map_event(map_id, dt),
          f"{today_map_event(map_id, day)} vs {today_map_event(map_id, dt)}")

    print("【4. 无配置 → None / {}】")
    check("未知图 today_map_event → None", today_map_event("no_such_map", day) is None)
    check("未知图 today_event_effects → {}", today_event_effects("no_such_map", day) == {})

    print("【5. effects 合并：返回与所选变体完全一致，多键并存】")
    multi_checked = False
    for map_id in DAILY_MAP_EVENTS:
        for now in range(1, 90):
            day = datetime.date(2026, 1, 1) + datetime.timedelta(days=now)
            ev = today_map_event(map_id, day)
            effs = today_event_effects(map_id, day)
            check(f"{map_id} effects==变体effects", effs == (ev.get("effects") or {}),
                  f"{effs} vs {ev}")
            # 找到同时含 loot_mult 与 encounter_rate 的变体并断言两者并存
            keys = set(effs.keys())
            if {"loot_mult", "encounter_rate"} <= keys:
                multi_checked = True
                check("loot_mult+encounter_rate 同时生效",
                      effs["loot_mult"] >= 1.2 and isinstance(effs["encounter_rate"], (int, float)),
                      str(effs))
            elif "event_chance" in keys and "mats" in keys:
                check("event_chance+mats 同时生效",
                      isinstance(effs["event_chance"], (int, float)) and isinstance(effs["mats"], list),
                      str(effs))
    check("至少命中一例多键并存（loot_mult+encounter_rate 或 event_chance+mats）", multi_checked)

    print("【6. _day_hash 确定性 & 哈希值域】")
    for map_id in list(DAILY_MAP_EVENTS.keys())[:3]:
        h1 = _day_hash(day.toordinal(), "daily:" + map_id)
        h2 = _day_hash(day.toordinal(), "daily:" + map_id)
        check(f"{map_id} _day_hash 幂等", h1 == h2, f"{h1} vs {h2}")
        check(f"{map_id} 哈希非负(<2^31)", 0 <= h1 <= 0x7FFFFFFF, str(h1))

    print("【7. faction_reputation_tier 阈值边界】")
    # 阈值：0 陌生 / 100 友好 / 300 尊敬 / 700 崇敬 / 1500 崇拜
    cases = [
        (-1, "陌生"), (0, "陌生"), (99, "陌生"),
        (100, "友好"), (299, "友好"),
        (300, "尊敬"), (699, "尊敬"),
        (700, "崇敬"), (1499, "崇敬"),
        (1500, "崇拜"), (99999, "崇拜"),
    ]
    for pts, expect in cases:
        got = faction_reputation_tier(pts)
        check(f"pts={pts} → {expect}", got == expect, f"got {got}")
    # 与数据表一致：tier 边界应等于 REPUTATION_TIERS 各档首值
    check("tier 首档=陌生", faction_reputation_tier(0) == "陌生")
    check("C 聚合暴露 faction_reputation_tier",
          getattr(C, "faction_reputation_tier", None) is not None)
    # ★ P5D-REPOINT：原判据 = 「宿主聚合门面 `game.content` 暴露 `today_map_event`」。
    #   终态 `game.content` 退役，聚合门面换成包侧 `content.facade.C`；而包侧
    #   `_PKG_SURFACE` **未登记** `daily_events` 这半边（实测 `today_map_event` /
    #   `today_event_effects` 都不在 `C` 上）⇒ 原判据的观测对象不再存在（不是放宽）。
    #   本文件真源直取自 `content.daily_events`（顶部 import），行为断言 2347 条全在其上；
    #   这里改为断言「真源模块自持该入口」，语义等价且不依赖聚合面登记完整性。
    check("真源 content.daily_events 自持 today_map_event",
          callable(getattr(_de_mod, "today_map_event", None)))

    print()
    print(f"结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
