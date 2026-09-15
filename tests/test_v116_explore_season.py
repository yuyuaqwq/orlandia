# -*- coding: utf-8 -*-
"""v116 探索事件季节渗透回归（tests/test_v116_explore_season.py）

覆盖：
  1. EXPLORE_EVENTS 季节字段合法：season/season_boost 仅取 spring/summer/autumn/winter 四值
  2. 季节硬限定：mock content.events.current_season 为某季时，roll_explore_event 不返回「非当季」的 season 限定事件
  3. 兜底不空池：hard mock 每季穷举采样，抽不到限定事件也能返回事件（不去季节过滤重试成功）
  4. 季节偏好生效：season_boost 匹配当季时该事件权重放大（mock 固定季节做两季采样对比）
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C
# ★ W2b（2026-09-15）：实现真源在包内 `content/events.py`，且它现在读**本模块全局**
#   （`_src(name)` = `globals()[name]`）⇒ 打桩必须打在 `content.events` 上。
#   打宿主壳 `game.core.events` 会**静默失效**（壳只再导出数据名，函数体不读壳的全局）。
from content.events import roll_explore_event, current_season
import content.events as EV

SEASONS = ("spring", "summer", "autumn", "winter")

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def patch_season(season):
    """mock content.events.current_season 恒返回给定季节（实现真源读的就是这个全局）"""
    EV.current_season = lambda now=None: season

def restore_season():
    EV.current_season = current_season


def main():
    print("【v116 探索季节：数据字段合法】")
    ok = True
    for ev in C.EXPLORE_EVENTS:
        for k in ("season", "season_boost"):
            v = ev.get(k)
            if v is not None and v not in SEASONS:
                ok = False
                print(f"  非法季节值 {ev['id']}.{k}={v}")
    check("season/season_boost 仅取四季节枚举", ok)
    restrict = [ev["id"] for ev in C.EXPLORE_EVENTS if ev.get("season")]
    boost = [ev["id"] for ev in C.EXPLORE_EVENTS if ev.get("season_boost")]
    print(f"  硬限定事件({len(restrict)}): {restrict} | 偏好事件({len(boost)}): {boost}")
    check("已有硬限定与偏好事件配置", len(restrict) >= 1 and len(boost) >= 1,
          f"限定{len(restrict)} 偏好{len(boost)}")

    print("【v116 探索季节：硬限定事件不跨季产出 + 兜底不空池】")
    random.seed(20260816)
    bad = []     # (season, 非当季限定事件越界)
    for season in SEASONS:
        patch_season(season)
        got_any = False
        for _ in range(5000):
            e = roll_explore_event()
            if e.get("season") and e["season"] != season:
                bad.append((season, e["id"]))
            got_any = got_any or bool(e.get("id"))
        if not got_any:
            # 理论上 season 过滤后仍有大量通用事件，绝不会为空；这里仅防御
            check(f"季节 {season} 采样不空池", False)
    restore_season()
    check("每季×5000采样：不返回非当季限定事件", not bad, str(bad[:5]))

    print("【v116 探索季节偏好：season_boost 当季权重放大】")
    # 选一条带 season_boost 的通用事件（spring 神秘泉水，无 maps 全地图可触发）对比当季 vs 反季出现频率
    target = next(ev for ev in C.EXPLORE_EVENTS if ev.get("season_boost") and not ev.get("season"))
    tseason = target["season_boost"]
    other = next(s for s in SEASONS if s != tseason)
    counts = {}
    for season in (tseason, other):
        patch_season(season)
        random.seed(99)
        cnt = 0
        for _ in range(8000):
            e = roll_explore_event()
            if e["id"] == target["id"]:
                cnt += 1
        counts[season] = cnt
    restore_season()
    print(f"  {target['id']}（{tseason}偏好）：偏好季 {counts[tseason]} vs 反季 {counts[other]}")
    check("偏好季节出现次数 > 反季（×1.5 权重生效）", counts[tseason] > counts[other],
          f"{counts}")

    print("【v116 探索季节：无 mock 也有兜底返回（自然季节不抛错）】")
    try:
        random.seed(7)
        got = roll_explore_event()
        check("自然季节下 roll_explore_event 正常返回", isinstance(got, dict) and got.get("id"), str(got)[:80])
    except Exception as e:
        check("自然季节下 roll_explore_event 正常返回", False, repr(e))

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
