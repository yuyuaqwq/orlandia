# -*- coding: utf-8 -*-
"""data 层 · 垂钓族（16 章品质垂钓 v2.0，阶段 9.3）

验证 FISHING_SPOTS / FISH_POOL / FISH_QUALITY_WEIGHTS / roll_fish：
- 档位权重表单调性（白递减、绿/蓝/紫/橙递增）+ 插值
- 钓点 ban_quality 禁出档位（固定 seed 采样）
- 品种 spots 限定水域（固定 seed 采样）
- 品种池完整性（每档兜底品种 + mat_ ID 可 resolve）
- 垂钓产业链配方闭环（炼金鲛人之泪/龙涎药剂、烹饪史莱姆果冻/烤肉串/金鲤盛宴）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C
from content import fishing as F

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
    print("【data·垂钓：钓点表 FISHING_SPOTS】")
    check("11 个钓点", len(C.FISHING_SPOTS) == 11, str(len(C.FISHING_SPOTS)))
    bad_spot = []
    for mid, s in C.FISHING_SPOTS.items():
        if mid not in C.MAP_BY_ID:
            bad_spot.append((mid, "地图不存在"))
        if not s.get("name") or not isinstance(s.get("min_lv"), int):
            bad_spot.append((mid, "结构缺字段"))
        if not isinstance(s.get("ban_quality"), list):
            bad_spot.append((mid, "缺 ban_quality"))
        for bq in s.get("ban_quality", []):
            if bq not in ("white", "green", "blue", "purple", "orange"):
                bad_spot.append((mid, f"非法档位 {bq}"))
    check("钓点 map_id 全在 MAPS + 结构完整", not bad_spot, str(bad_spot[:3]))
    check("铁港码头无禁出（全档位）", C.FISHING_SPOTS["harbor_docks"]["ban_quality"] == [], str(C.FISHING_SPOTS["harbor_docks"]))
    check("橡木溪流禁紫/橙", set(C.FISHING_SPOTS["oak_plain"]["ban_quality"]) == {"purple", "orange"}, str(C.FISHING_SPOTS["oak_plain"]))

    print("【data·垂钓：档位权重表 FISH_QUALITY_WEIGHTS】")
    w = C.FISH_QUALITY_WEIGHTS
    check("表键为 1/3/5/7/9", list(w) == [1, 3, 5, 7, 9], str(list(w)))
    mono_ok = True
    for col in range(5):
        seq = [w[k][col] for k in sorted(w)]
        if col == 0:
            mono_ok = mono_ok and all(seq[i] >= seq[i+1] for i in range(len(seq)-1))
        else:
            mono_ok = mono_ok and all(seq[i] <= seq[i+1] for i in range(len(seq)-1))
    check("白单调递减、绿/蓝/紫/橙单调递增", mono_ok, str(w))
    check("每行权重和≈100", all(abs(sum(row) - 100) < 0.01 for row in w.values()), str({k: sum(v) for k, v in w.items()}))
    check("Lv.9 传说 1.0%", abs(w[9][4] - 1.0) < 1e-9, str(w[9]))
    check("Lv.1 传说 0.05%", abs(w[1][4] - 0.05) < 1e-9, str(w[1]))

    print("【data·垂钓：插值 _quality_weights】")
    w1 = F._quality_weights(1)
    w9 = F._quality_weights(9)
    w2 = F._quality_weights(2)
    w8 = F._quality_weights(8)
    check("Lv.1 返回表值", w1 == w[1], str(w1))
    check("Lv.9 返回表值", w9 == w[9], str(w9))
    check("Lv.2 白介于 Lv.1/3", w[3][0] <= w2[0] <= w[1][0], str(w2))
    check("Lv.8 橙介于 Lv.7/9", w[7][4] <= w8[4] <= w[9][4], str(w8))
    check("Lv.0 钳制到 Lv.1", F._quality_weights(0) == w[1], str(F._quality_weights(0)))
    check("Lv.10 钳制到 Lv.9", F._quality_weights(10) == w[9], str(F._quality_weights(10)))

    print("【data·垂钓：品种池 FISH_POOL】")
    pool = C.FISH_POOL
    check("30 个品种（v126.6 鱼种扩容 +6）", len(pool) == 30, str(len(pool)))
    q_set = set(f["quality"] for f in pool)
    check("品质值全合法", q_set <= {"white", "green", "blue", "purple", "orange"}, str(q_set))
    # 每档至少 1 个全水域兜底（spots is None）；orange 例外：传说只在铁港码头（16 章 2.4 设定）
    for q in ("white", "green", "blue", "purple"):
        fallback = [f for f in pool if f["quality"] == q and not f.get("spots")]
        check(f"{q} 档有全水域兜底品种", len(fallback) >= 1, str([f["name"] for f in fallback]))
    harbor_orange = [f for f in pool if f["quality"] == "orange" and "harbor_docks" in (f.get("spots") or [])]
    check("orange 档在铁港码头有货（传说只在深水）", len(harbor_orange) >= 1, str([f["name"] for f in harbor_orange]))
    # 品种名不重复
    names = [f["name"] for f in pool]
    check("品种名无重复", len(names) == len(set(names)), str([n for n in set(names) if names.count(n) > 1]))
    # 可入包品种（鱼/材料）mat_ ID 可 resolve
    missing = [f["name"] for f in pool if f["type"] in ("鱼", "材料") and not C.resolve("materials", f["name"])]
    check("鱼/材料品种全部可 resolve 到 mat_ ID", not missing, str(missing))
    # 品种 spots 引用合法
    bad_spots = [(f["name"], s) for f in pool if f.get("spots") for s in f["spots"] if s not in C.FISHING_SPOTS]
    check("品种 spots 全部引用合法钓点", not bad_spots, str(bad_spots[:3]))

    print("【data·垂钓：roll_fish 采样（固定 seed 验证 ban/spots）】")
    import random
    random.seed(42)
    ban_bad, spot_bad = [], []
    for mid, s in C.FISHING_SPOTS.items():
        for _ in range(300):
            f = F.roll_fish(9, mid)
            if f["quality"] in s["ban_quality"]:
                ban_bad.append((mid, f["name"], f["quality"]))
            if f.get("spots") and mid not in f["spots"]:
                spot_bad.append((mid, f["name"]))
    check("2000+ 采样无禁出档位品种", not ban_bad, str(ban_bad[:3]))
    check("2000+ 采样无 spots 越界品种", not spot_bad, str(spot_bad[:3]))
    # 传说只在铁港码头
    random.seed(7)
    legend_out = set()
    for mid in C.FISHING_SPOTS:
        for _ in range(400):
            f = F.roll_fish(9, mid)
            if f["quality"] == "orange" and mid != "harbor_docks":
                legend_out.add(mid)
    check("传说档只在铁港码头（非铁港 400 次采样）", not legend_out, str(legend_out))

    print("【data·垂钓：产业链配方闭环（16 章 2.5）】")
    # 炼金：鲛人之泪 / 龙涎药剂
    for rn, mat in (("鲛人之泪", "鲛人泪"), ("龙涎药剂", "龙涎香")):
        rkey = C.resolve("alchemy", rn)
        r = C.ALCHEMY_RECIPES.get(rkey)
        ok = r and C.resolve("materials", mat) in r["cost"] and r["product"]
        pkey = next(iter(r["product"])) if r and r["product"] else None
        ok = ok and pkey in C.ITEMS
        check(f"炼金配方 {rn} 成本/产物闭环", bool(ok), str(r)[:100] if r else "配方不存在")
    # 烹饪：史莱姆果冻 / 烤肉串 / 金鲤盛宴
    for rn, mat in (("史莱姆果冻", "史莱姆黏液"), ("烤肉串(自制)", "兽肉"), ("金鲤盛宴", "金鲤")):
        rkey = C.resolve("cooking", rn)
        r = C.COOKING_RECIPES.get(rkey)
        ok = r and C.resolve("materials", mat) in r["cost"] and r["product"]
        pkey = next(iter(r["product"])) if r and r["product"] else None
        ok = ok and pkey in C.ITEMS
        check(f"烹饪配方 {rn} 成本/产物闭环", bool(ok), str(r)[:100] if r else "配方不存在")
    # 消耗品效果字段
    check("鲛人之泪 effect=buff_matk", C.ITEMS["i_mermaid_tear"].get("effect") == "buff_matk", str(C.ITEMS.get("i_mermaid_tear")))
    check("龙涎药剂 effect=buff_atk_def", C.ITEMS["i_ambergris_draught"].get("effect") == "buff_atk_def", str(C.ITEMS.get("i_ambergris_draught")))

    print("【data·垂钓：渔获材料 quality 字段（16 章 1.1）】")
    for n, q in (("银鳞鱼", "white"), ("金鲤", "green"), ("月光鱼", "blue"), ("鲛人泪", "blue"),
                 ("深海水晶", "purple"), ("龙涎香", "purple"), ("古代鱼骨", "orange")):
        mid = C.resolve("materials", n)
        check(f"{n} quality={q}", bool(mid) and C.MATERIALS[mid].get("quality") == q, f"{mid}: {C.MATERIALS.get(mid)}")

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
