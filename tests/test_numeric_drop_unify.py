# -*- coding: utf-8 -*-
"""test_numeric_drop_unify —— 掉落系统统一门禁（v174）

防退化断言：
  1. DROP_POOLS 全量 0 断链 / 0 空池（audit_all）
  2. 四策略 roll 冒烟（weighted/fish/table/fixed 各抽得出）
  3. 采集/挖掘/垂钓/副本Boss 消费数据源一致性（老数据↔新池集合相等）
  4. expand_pool 权重展开等价旧逻辑

运行：python tests/test_numeric_drop_unify.py（exit=0 全绿；由 run_numeric_tests.py 自动纳入门禁）
"""
import os
import sys
import random

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_DIR = os.path.dirname(_SCRIPT_DIR)
for _p in (_PLUGIN_DIR,):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_PLUGIN_DIR, "test_game_data.db"))

# flaky 修复（2026-09-11）：本文件用全局 random 做概率型抽样（暗格 2000 次档位分布、
# 各池 roll 冒烟）。未固定种子时 run 之间结果不保证一致；门禁只应因**真实退化**变红。
# 固定种子 = 确定性基线（沿用 test_v135_quality_roll / test_battle_n9_equip 的既有做法）。
random.seed(20260911)

from _engine_harness import C  # noqa: E402
from _engine_harness import db as _db  # noqa: E402
from content.catalog_rules import DROP_POOLS  # noqa: E402  W10：包内单源（game/data 删表后同一份）
from content.loot import (  # noqa: E402  REPOINT_MAP: game.drop_engine → content.loot
    roll, expand_pool, audit_all, _SimpleCtx, _resolve_item_ref,
)
_db.init_db()   # 本文件用真库（`content.wild_king._roll_chest_rewards` 读 players）

passed, failed = 0, 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")


def main():
    print("【drop_unify：全量审计 0 断链】")
    rep = audit_all()
    issues = rep["issues"]
    check("DROP_POOLS 审计 0 问题", len(issues) == 0, f"发现 {len(issues)}: {issues[:3]}")
    check("池数 ≥ 500", rep["pool_count"] >= 500, f"实际 {rep['pool_count']}")
    check("条目数 ≥ 1300", rep["entry_count"] >= 1300, f"实际 {rep['entry_count']}")

    print("【drop_unify：四策略 roll 冒烟】")
    # weighted
    r = roll("gather:oak_plain", _SimpleCtx(map_id="oak_plain", player_level=5))
    check("weighted 采集出材料", len(r) >= 1 and r[0]["type"] == "item", f"{r}")
    # fish
    r = roll("fish:oak_plain", _SimpleCtx(map_id="oak_plain", prof_lv=3))
    check("fish 垂钓出鱼", len(r) >= 1 and r[0]["type"] == "fish", f"{r}")
    # table
    r = roll("chest:low", _SimpleCtx(player_level=20))
    check("table 宝箱出金", any(x["type"] == "gold" for x in r), f"{r}")
    # fixed
    r = roll("elite:狼王·灰影", _SimpleCtx(player_level=14))
    check("fixed 精英专属出装", any(x["type"] == "equip" for x in r), f"{r}")

    print("【drop_unify：数据源一致性（老数据 ↔ 新池）】")
    # 采集
    for mapid in ("oak_plain", "white_deer_forest", "hill_mine", "dragon_ridge"):
        old = {m for m, _w in C.GATHER_MAP_POOLS.get(mapid, []) for _ in range(_w)}
        new = set(expand_pool(f"gather:{mapid}"))
        check(f"gather:{mapid} 集合一致", old == new, f"old{len(old)} new{len(new)}")
    # 挖掘深池
    for mapid in ("hill_mine", "dragon_ridge"):
        old = {m for m, _w in C.MINING_DEEP_POOLS.get(mapid, []) for _ in range(_w)}
        new = set(expand_pool(f"mine:{mapid}"))
        check(f"mine:{mapid} 集合一致", old == new, f"old{len(old)} new{len(new)}")
    # 副本Boss 池主题装备
    for iid in ("inst_goblin_camp", "inst_sea_cave", "inst_sea_god_temple", "inst_frost_throne"):
        old_pool = set((C.INSTANCE_BOSS_EQUIP_DROP.get(iid) or {}).get("pool") or [])
        sub_key = f"inst_pool:{iid}"
        new_pool = set()
        if sub_key in DROP_POOLS:
            new_pool = {e["item"].replace("equip:", "") for e in DROP_POOLS[sub_key]["entries"]}
        check(f"boss:{iid} 主题池一致", old_pool == new_pool, f"old{len(old_pool)} new{len(new_pool)}")

    print("【drop_unify：expand_pool 权重展开】")
    # 展开数 = 权重和
    for mapid in ("oak_plain", "emerald_forest"):
        old_w = sum(w for _m, w in C.GATHER_MAP_POOLS.get(mapid, []))
        new_n = len(expand_pool(f"gather:{mapid}"))
        check(f"gather:{mapid} 权重展开数一致", old_w == new_n, f"old{old_w} new{new_n}")

    print("【drop_unify：引用解析】")
    r = _resolve_item_ref("equip:eq_hui_ying_lang_ya_ren", _SimpleCtx(player_level=14))
    check("equip: 引用解析成名册装", r and r["type"] == "equip", f"{r}")
    r = _resolve_item_ref("gold:10:50", _SimpleCtx())
    check("gold: 区间解析", r and r["type"] == "gold" and 10 <= r["count"] <= 50, f"{r}")

    print("【drop_unify：精英专属接线（ELITE_EQUIP_DROP 全接线）】")
    # 每个 ELITE_EQUIP_DROP 登记的精英 → elite: 池存在（数据同步）
    from _engine_harness import C as _C  # noqa: E402
    ELITE_EQUIP_DROP = _C.ELITE_EQUIP_DROP
    for name, rid in list(ELITE_EQUIP_DROP.items())[:5]:
        check(f"elite:{name} 池存在且引用正确", f"elite:{name}" in DROP_POOLS, f"{rid}")
    # 登记数 = elite: 池数（全 18 接线）
    elite_pool_n = len([k for k in DROP_POOLS if k.startswith("elite:")])
    check("ELITE_EQUIP_DROP 全登记到 elite: 池", len(ELITE_EQUIP_DROP) == elite_pool_n,
          f"登记{len(ELITE_EQUIP_DROP)} 池{elite_pool_n}")
    # 每个登记的 rid 可生成（名册有效）
    all_gen = all(C.EQUIP_ROSTER.get(rid) for rid in ELITE_EQUIP_DROP.values())
    check("专属装备全部名册有效", all_gen)
    # 掉率常量已导出
    check("ELITE_EQ_DROP_CHANCE 已导出", hasattr(C, "ELITE_EQ_DROP_CHANCE") and C.ELITE_EQ_DROP_CHANCE > 0)

    print("【drop_unify：副本搜刮（战利品堆/暗格宝箱）】")
    # 22 副本都应有 loot_pile / secret_chest 池
    from _engine_harness import C as _C  # noqa: E402
    INSTANCES = _C.INSTANCES
    inst_ids = [iid for iid in INSTANCES if INSTANCES[iid].get("stages")]
    loot_ok = all(f"loot_pile:{iid}" in DROP_POOLS for iid in inst_ids)
    chest_ok = all(f"secret_chest:{iid}" in DROP_POOLS for iid in inst_ids)
    check(f"全部副本有 loot_pile 池 ({len(inst_ids)}个)", loot_ok)
    check(f"全部副本有 secret_chest 池 ({len(inst_ids)}个)", chest_ok)
    # 战利品堆必出金币（gold_base 折算）
    r = roll("loot_pile:inst_goblin_camp", _SimpleCtx(inst_id="inst_goblin_camp", monster_lv=20,
                                                      player_level=20, gold_base=220))
    check("战利品堆必出金币(220×30%=66)", any(x["type"] == "gold" and x["count"] == 66 for x in r), f"{r}")
    # 暗格宝箱 5 档互斥分布（2000 次每档都出现且无 2 档同时出）
    from collections import Counter
    dc = Counter()
    double = 0
    for _ in range(2000):
        res = roll("secret_chest:inst_goblin_camp",
                   _SimpleCtx(inst_id="inst_goblin_camp", monster_lv=20, player_level=20))
        if len(res) > 1:
            double += 1
        for x in res:
            t = x.get("type")
            if t == "petegg": dc["蛋"] += 1
            elif t == "equip": dc["装备"] += 1
            elif t == "rune": dc["符文"] += 1
            elif x.get("item_id") == "mat_tu_zhi_can_ye": dc["图纸残页"] += 1
            elif t == "item": dc["材料"] += 1
    check("暗格互斥无双出", double == 0, f"双出{double}")
    total_rolls = sum(dc.values())
    check("暗格5档覆盖且≈2000", total_rolls >= 1800 and len(dc) >= 4, f"{dict(dc)} total{total_rolls}")

    print("【drop_unify：野王宝箱 collect 死数据修复】")
    # chest:low 池含 collect 子池（铁牌徽章），且消费端 _roll_chest_rewards 走引擎后能发 collect
    import content.wild_king as _WK  # noqa: E402
    WILD_KING_CHEST_TIERS = C.WILD_KING_CHEST_TIERS
    king = {"lv": 20, "chest_tier": "low", "drops": ["兽肉"]}
    lines, _bc = _WK._roll_chest_rewards("gr", "wr", king, WILD_KING_CHEST_TIERS["low"], is_loot=False)
    check("公共箱发 collect(铁牌徽章)", any("徽章" in l for l in lines), str(lines))
    # 战利箱必出图纸
    lines2, _bc2 = _WK._roll_chest_rewards("gr", "wr", king, WILD_KING_CHEST_TIERS["low"], is_loot=True)
    check("战利箱必出图纸", any("图纸" in l or "残页" in l for l in lines2), str(lines2))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
