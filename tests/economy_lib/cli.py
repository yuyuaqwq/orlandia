# -*- coding: utf-8 -*-
"""economy_lib.cli —— 经济模型命令行入口
用法（cd 插件目录）:
  python scripts/economy_lib/cli.py scan          # 全阶段经济扫描 + 健康检查
  python scripts/economy_lib/cli.py prof          # 副业(炼金/烹饪)成本-价值扫描
  python scripts/economy_lib/cli.py drop [lv]     # 指定等级掉落仿真（默认全阶段）
  python scripts/economy_lib/cli.py json          # 输出全量 JSON
"""
import sys
import json
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from economy_lib import (  # noqa: E402
    economy_scan, check_health, profession_scan, drop_count_sim, shop_scan,
    heal_alignment_scan,
    md_table, to_json, health_text,
)


def cmd_scan():
    scan = economy_scan()
    rows = scan["stages"]
    print("== 经济模型全阶段扫描 ==")
    headers = ["stage", "lv", "per_kill_gold", "drop_value", "income_10_kills",
               "blue_price", "blue_kills", "enhance9_blue_ratio",
               "craft_cost", "craft_cost_ratio", "drop_avg_count", "drop_max_count"]
    print(md_table(headers, rows))
    print("\n== 健康检查 ==")
    issues = [(r, check_health(r)) for r in rows]
    for r, iss in issues:
        tag = "🔴" if iss else "✅"
        print(f"{tag} {r['stage']} (Lv{r['lv']})" + ("" if not iss else " | " + "; ".join(iss)))


def cmd_prof():
    prof = profession_scan()
    for sect, label in (("alchemy", "炼金"), ("cooking", "烹饪")):
        p = prof[sect]
        print(f"\n== {label}（共 {p['total']} 配方）==")
        print(f"亏本(成本>产品价90%): {len(p['broken'])}")
        for b in p["broken"][:15]:
            print(f"  {b['name']}(min_lv{b['min_lv']}): 成本{b['cost']} 产品价{b['prod']} {b['ratio']:.0%}")
        print(f"暴利(成本<产品价20%): {len(p['overpriced'])}")
        for o in p["overpriced"][:8]:
            print(f"  {o['name']}(min_lv{o['min_lv']}): 成本{o['cost']} 产品价{o['prod']} {o['ratio']:.0%}")


def cmd_drop(lv_arg=None):
    lvs = [int(x) for x in lv_arg.split(",")] if lv_arg else [10, 24, 45, 60, 80, 95]
    print("== 掉落数量仿真（单只普通怪单种材料）==")
    print("Lv | avg_count | max_count | 撞cap(>10) | 样例")
    for lv in lvs:
        d = drop_count_sim(lv, "dps")
        samples = "; ".join(f"{s[3]}级{s[4]}→{s[1]}({s[2]}元)x{s[0]}" for s in d["samples"][:2])
        print(f"{lv} | {d['avg_count']} | {d['max_count']} | {d.get('over_cap', 0)} | {samples}")


def cmd_json():
    out = {
        "economy": economy_scan(),
        "professions": profession_scan(),
        "shop": shop_scan(),
    }
    print(to_json(out))


def cmd_heal():
    """回复道具对齐扫描（食物 vs 药水性价比）。"""
    r = heal_alignment_scan()
    print(f"== 回复道具对齐（食物 {r['health']['food_count']} / 药水 {r['health']['potion_count']}）==")
    if not r["issues"]:
        print("✅ 全部对齐（无食物回复碾压药水）")
    for x in sorted(r["issues"], key=lambda x: x["price"]):
        print(f"  ⚠️ {x['name']} p={x['price']} heal={x['heal']*100:.0f}% hot累计={x['hot_sum']*100:.0f}% 体力={x['stamina']} | {x['issue']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if cmd == "scan":
        cmd_scan()
    elif cmd == "prof":
        cmd_prof()
    elif cmd == "drop":
        cmd_drop(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "shop":
        scan = shop_scan()
        print(f"== 商店价格分阶段扫描（{scan['total']} 条配货）==")
        for x in scan["anchor_issues"]:
            print(f"  ⚠️ [{x['verdict']}] {x['name']} @ {x['sa']} Lv{x['town_lv']} p={x['price']} kills={x['kills']} band={x['band']}")
        print(f"锚点问题 {len(scan['anchor_issues'])}（须 0）/ 便利品 warning {len(scan['stage_issues'])}")
    elif cmd == "heal":
        cmd_heal()
    elif cmd == "json":
        cmd_json()
    else:
        print(__doc__)
