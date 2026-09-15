# -*- coding: utf-8 -*-
"""v97.2 采集地图绑定测试：全野外地图专属池 + 回退逻辑修复。

覆盖：
1. 68 张野外地图全部配置专属采集池
2. 池内材料 id 全部存在于 MATERIALS（无幽灵引用）
3. 各地图采集结果只出本地材料（不串池）
4. 稀有材料低权重存在（如深渊祭坛的灰烬之核、星辉台的星尘沙漏）
5. 回退逻辑：副本/隐藏区域按地图等级映射价格区间（Lv94 能采到 500+ 材料）
6. 采集结算流程正常入包
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, make_player, Main

from _engine_harness import Main as EconomyCmds  # 原 game.commands.economy.EconomyCmds 壳 → 包内实现驱动口

# `content.profession` 的 `bind_host(expand_pool=…)` 槽（旧宿主薄壳
# `game/services/profession.py` 注入；终态无该薄壳）。REPOINT_MAP: game.drop_engine → content.loot。
from content.loot import expand_pool as _expand_pool
from content import profession as _profession_mod
_profession_mod.bind_host(expand_pool=_expand_pool)

FAILS = []

def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        FAILS.append(name)
        print(f"  ✗ {name} {detail}")

def main():
    e = EconomyCmds(None)
    # v98.1 数据下沉：采集池移到数据层（game/data/gather_pools.py）
    pools = C.GATHER_MAP_POOLS

    print("== 1. 全野外地图配池 ==")
    wild = [m["id"] for m in C.MAPS if m["type"] == "野外"]
    missing = [m for m in wild if m not in pools]
    check(f"68 张野外地图全部配池 (实际 {len(wild)})", len(missing) == 0, f"缺: {missing}")
    extra = [m for m in pools if m not in wild]
    check("池子不包含非野外地图", not extra, f"多余: {extra}")

    print("\n== 2. 池内材料 id 全部有效 ==")
    bad = []
    for mid, pool in pools.items():
        for mat_id, w in pool:
            if mat_id not in C.MATERIALS:
                bad.append((mid, mat_id))
            if not isinstance(w, int) or w <= 0:
                bad.append((mid, f"权重非法 {w}"))
    check(f"无幽灵材料引用 (共 {sum(len(p) for p in pools.values())} 条)", not bad, f"坏: {bad}")

    print("\n== 3. 各地图采集只出本地材料 ==")
    random.seed(7)
    leak = []
    for mid, pool in pools.items():
        local_ids = {m for m, _w in pool}
        # 条件池（GATHER_COND_POOLS，如 night 限定）也是本地材料，并入判定
        cond_pool = C.GATHER_COND_POOLS.get(mid, [])
        local_ids |= {m for m, *_ in cond_pool}
        for _ in range(30):
            mats = e._gather_roll(50, 6, mid)
            for m in mats:
                if m not in local_ids:
                    leak.append((mid, m))
                    break
    check("30 次采样无串池", not leak, f"串池: {leak[:5]}")

    print("\n== 4. 稀有材料低权重存在 ==")
    rare_checks = [
        ("abyss_altar", "mat_hui_jin_zhi_he", "灰烬之核 1200"),
        ("starlight_terrace", "mat_star_hourglass", "星尘沙漏 800"),
        ("dragon_roost", "mat_long_xue_cao", "龙血草 400"),
        ("storm_plateau", "mat_lei_he", "雷核 280"),
    ]
    for mid, mat_id, desc in rare_checks:
        pool = dict((m, w) for m, w in pools[mid])
        check(f"{mid} 含 {desc}", mat_id in pool, f"池: {pool}")

    print("\n== 5. 回退逻辑（副本/隐藏区域按地图等级）==")
    random.seed(11)
    # 低等级副本不应出 500+ 材料
    low = e._gather_roll(15, 1, "goblin_camp")
    check("Lv15 副本不采 500+ 材料", all(C.MATERIALS[m]["price"] < 500 for m in low))
    # 高等级副本能采 500+ 材料（原逻辑 Lv50+ 永远采不到）
    hi_ok = False
    for _ in range(200):
        mats = e._gather_roll(94, 1, "cloud_sanctum")
        if any(C.MATERIALS[m]["price"] >= 500 for m in mats):
            hi_ok = True
            break
    check("Lv94 副本能采到 500+ 材料（修复原上限问题）", hi_ok)
    # 未知地图兜底不崩
    try:
        r = e._gather_roll(1, 1, "no_such_map")
        check("未知地图兜底不崩", isinstance(r, list) and len(r) >= 1, f"got {r}")
    except Exception as ex:
        check("未知地图兜底不崩", False, str(ex))

    print("\n== 6. 采集结算流程 ==")
    import asyncio

    async def _settle_case():
        clean_db()
        m = Main(None)
        make_player("g1", "q1", level=5)
        qq, grp = "q1", "g1"
        db.update_player(grp, qq, cur_map="starlake")

        # 直接调结算（模拟等待完成）
        st = {"finish": 0, "type": "gather"}
        text = m._settle_gather(grp, qq, st)
        check("采集结算返回文案", text and "采集完成" in text, text or "")
        bag = db.get_inventory(grp, qq)
        lake_mats = {mat for mat, _w in pools["starlake"]}
        names = set()
        for item in bag:
            # v126.4 审计 P2-1：get_inventory 返回 {key,data,count} 包装，顶层无 type；
            # 且 v126.3 后 data.type 是配置真实值（兽材/矿石等），须用 MATERIAL_KIND_TYPES 归并
            if item.get("data", {}).get("type") in C.MATERIAL_KIND_TYPES:
                names.add(item["data"].get("name", ""))
        lake_names = {C.MATERIALS[x]["name"] for x in lake_mats}
        check("入包材料全部来自星语湖池", names <= lake_names, f"包内: {names}")

    asyncio.run(_settle_case())

    print(f"\n结果: {'全部通过' if not FAILS else f'{len(FAILS)} 项失败: {FAILS}'}")
    return 0 if not FAILS else 1

if __name__ == "__main__":
    sys.exit(main())
