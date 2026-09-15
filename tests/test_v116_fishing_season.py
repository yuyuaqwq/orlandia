# -*- coding: utf-8 -*-
"""v116 垂钓季节限定改进回归（tests/test_v116_fishing_season.py）

覆盖：
  1. FISH_POOL 季节字段合法：season/season_boost 仅取 spring/summer/autumn/winter 四值
  2. roll_fish 季节硬限定：mock current_season 为某季时，钓点不会产出「非当季」的 season 限定鱼
  3. 兜底不钓空：hard mock 每季穷举钓点采样，抽不到限定鱼也能返回（并守禁出/水域规则）
  4. 季节偏好权重生效：season_boost 匹配当季时该鱼权重放大（mock 固定季节做两季采样对比）
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C
from content.fishing import roll_fish, current_season
import content.fishing as F

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
    """mock core.fishing.current_season 恒返回给定季节"""
    F.current_season = lambda now=None: season

def restore_season():
    F.current_season = current_season


def main():
    print("【v116 季节限定：数据字段合法】")
    ok = True
    for f in C.FISH_POOL:
        for k in ("season", "season_boost"):
            v = f.get(k)
            if v is not None and v not in SEASONS:
                ok = False
                print(f"  非法季节值 {f['name']}.{k}={v}")
    check("season/season_boost 仅取四季节枚举", ok)
    restrict = [f["name"] for f in C.FISH_POOL if f.get("season")]
    boost = [f["name"] for f in C.FISH_POOL if f.get("season_boost")]
    print(f"  硬限定鱼({len(restrict)}): {restrict} | 偏好鱼({len(boost)}): {boost}")
    check("已有硬限定鱼与偏好鱼配置", len(restrict) >= 1 and len(boost) >= 1,
          f"限定{len(restrict)} 偏好{len(boost)}")

    print("【v116 季节限定：硬限定鱼不跨季产出 + 兜底不钓空】")
    random.seed(20260816)
    bad = []       # (season, spot, 非当季限定鱼越界)
    banned = []    # 禁出档位越界
    spot_bad = []  # spots 水域越界
    for season in SEASONS:
        patch_season(season)
        for mid, s in C.FISHING_SPOTS.items():
            for _ in range(300):
                f = roll_fish(9, mid)
                if f.get("season") and f["season"] != season:
                    bad.append((season, mid, f["name"]))
                if f["quality"] in s["ban_quality"]:
                    banned.append((season, mid, f["name"], f["quality"]))
                if f.get("spots") and mid not in f["spots"]:
                    spot_bad.append((season, mid, f["name"]))
    restore_season()
    check("每季×11钓点×300采样：不产出非当季限定鱼", not bad, str(bad[:5]))
    check("每季采样遵循禁出档位（无越界）", not banned, str(banned[:3]))
    check("每季采样遵循种水域（无越界）", not spot_bad, str(spot_bad[:3]))

    print("【v116 季节偏好：season_boost 当季权重放大】")
    # 选一条带 season_boost 的鱼（月光鱼=autumn）在指定钓点对比当季 vs 反季出现频率
    target = next(f for f in C.FISH_POOL if f.get("season_boost"))
    tloc = "oak_plain"  # 全水域鱼任意钓点可测；若为限定水域则换相应钓点
    if target.get("spots"):
        tloc = target["spots"][0]
    tseason = target["season_boost"]
    other = next(s for s in SEASONS if s != tseason)
    counts = {}
    for season in (tseason, other):
        patch_season(season)
        random.seed(99)
        cnt = 0
        for _ in range(8000):
            f = roll_fish(9, tloc)
            if f["name"] == target["name"]:
                cnt += 1
        counts[season] = cnt
    restore_season()
    print(f"  {target['name']}（{target['season_boost']}偏好，钓点{tloc}）：偏好季 {counts[tseason]} vs 反季 {counts[other]}")
    check("偏好季节出现次数 > 反季（×1.5 权重生效）", counts[tseason] > counts[other],
          f"{counts}")

    print("【v116 季节限定：无 mock 也有兜底返回（自然季节不抛错）】")
    try:
        random.seed(7)
        got = roll_fish(9, "harbor_docks")
        check("自然季节下 roll_fish 正常返回", isinstance(got, dict) and got.get("name"), str(got)[:80])
    except Exception as e:
        check("自然季节下 roll_fish 正常返回", False, repr(e))

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
