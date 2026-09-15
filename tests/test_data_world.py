# -*- coding: utf-8 -*-
"""data 层 · 世界族：地图 / 连接 / NPC / 传送门 / 垂钓点 / 任务 / 事件

验证 MAP_BY_ID / MAP_CONNECTIONS / NPCS / PORTALS / FISHING_SPOTS 与任务事件池。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ %s" % name)
    else:
        failed += 1
        print("  ❌ %s %s" % (name, detail))


def main():
    print("【data·世界族：地图】")
    check("MAP_BY_ID 72 地图", len(C.MAP_BY_ID) >= 50, str(len(C.MAP_BY_ID)))
    check("MAP_CONNECTIONS 连通", len(C.MAP_CONNECTIONS) >= 50, str(len(C.MAP_CONNECTIONS)))
    if C.MAP_CONNECTIONS:
        mid = next(iter(C.MAP_CONNECTIONS))
        check("地图连接有邻居", isinstance(C.MAP_CONNECTIONS[mid], (list, dict)) and len(C.MAP_CONNECTIONS[mid]) > 0,
              str(C.MAP_CONNECTIONS[mid])[:80])
    check("LEGACY_MAP_ALIAS 兼容别名", len(C.LEGACY_MAP_ALIAS) > 0, str(len(C.LEGACY_MAP_ALIAS)))

    print("【data·世界族：NPC】")
    check("NPCS 33 个", len(C.NPCS) >= 20, str(len(C.NPCS)))
    check("NPC 有名字", all("name" in v for v in C.NPCS.values()), str(list(C.NPCS)[:3]))

    print("【data·世界族：传送门】")
    check("PORTALS 15 个", len(C.PORTALS) >= 10, str(len(C.PORTALS)))

    print("【data·世界族：垂钓点】")
    check("FISHING_SPOTS 6 个", len(C.FISHING_SPOTS) >= 4, str(len(C.FISHING_SPOTS)))
    check("FISH_POOL 非空", hasattr(C, "FISH_POOL") and len(getattr(C, "FISH_POOL", [])) > 0, "FISH_POOL")

    print("【data·世界族：任务/事件】")
    check("MAIN_QUESTS 非空", hasattr(C, "MAIN_QUESTS") and len(getattr(C, "MAIN_QUESTS", [])) > 0, "MAIN_QUESTS")
    check("SIDE_QUESTS 非空", hasattr(C, "SIDE_QUESTS") and len(getattr(C, "SIDE_QUESTS", [])) > 0, "SIDE_QUESTS")
    check("DAILY_QUESTS 非空", hasattr(C, "DAILY_QUESTS") and len(getattr(C, "DAILY_QUESTS", [])) > 0, "DAILY_QUESTS")
    check("EXPLORE_EVENTS 非空", hasattr(C, "EXPLORE_EVENTS") and len(getattr(C, "EXPLORE_EVENTS", [])) > 0, "EXPLORE_EVENTS")

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
