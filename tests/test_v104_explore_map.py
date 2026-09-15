# -*- coding: utf-8 -*-
"""v104 探索/事件/地图模块 10 项修复回归（批次2/批次3，M22/M23/M24/M06）。

覆盖：
1. 孤儿 prop 修复：oak_town_street / oak_town_outskirts / silver_brook_outskirts /
   maple_village_fields 的『交互』正常（无 KeyError，stall/well/washing_line/haystack 已定义）
2. 壁炉满血不吞次数：满血交互旅店壁炉 → 只出氛围文案，不 mark_props_use（M23）
3. POI 键覆盖修复：7 个重点子区域（oak_plain_3 等）功能 POI + 风景 POI 共存（M22/M24）
4. 城镇探索冷却：连续城镇探索 → 第二次被 60s 冷却拦截（M23）
5. 世界 Boss 掉落：世界 Boss 结算 → 出物品（非仅金币经验）（M06 P2-3）
6. 7 城镇旅店：月冠王庭/无名港/风翼城/铁砧要塞/龙脊山口/珍珠城/灰烬营地 各有 1 子区域可住宿（M22）
7. deep_tunnel 商店：中央大厅(deep_tunnel_2) 有 shop funcs + 配货（M22）
8. HIDDEN_MAP_UNLOCK 无死条目：所有目标地图在 MAPS（M22 P2）
9. 回城卷轴落广场：使用回城卷轴 → 落最近城镇 subareas[0]（M22 P2）
10. 战败回就近城镇：战败 → 回当前图就近城镇非橡木镇 + 落中心广场（M22 P3）
"""
import sys, os, time, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, make_player, Main, FakeEvent, run
from content.pois import (subarea_props as _subarea_props,  # REPOINT_MAP: game.core.* → content.pois
                        subarea_pois as _subarea_pois, prop_entry as _prop_entry)

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail).encode('utf-8', 'replace').decode('utf-8', 'replace')[:300]}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

def set_pos(m, gid, qid, map_id, sa_id):
    db.update_player(gid, qid, cur_map=map_id, cur_subarea=sa_id)

async def main():
    from content.combat_cmds import WORLD_BOSS_DROPS

    print("【1. 孤儿 prop 修复：4 个子区域交互正常】")
    clean_db()
    m = Main(None)
    make_player("g1", "q1", level=10)
    ORPHAN_AREAS = [
        ("oak_town", "oak_town_street", ["布棚摊", "水井", "晾衣绳"]),
        ("oak_town", "oak_town_outskirts", ["干草堆"]),
        ("silver_brook", "silver_brook_outskirts", ["干草堆"]),
        ("maple_village", "maple_village_fields", ["干草堆"]),
    ]
    for map_id, sa_id, expect_names in ORPHAN_AREAS:
        # 数据级：挂载条目全部能解析到 PROPS（无孤儿）
        ents = _subarea_props(map_id, sa_id)
        missing = [e for e in ents if _prop_entry(e)[0] not in C.PROPS]
        check(f"{map_id}:{sa_id} 无孤儿 prop", not missing, missing)
        # 命令级：无参列表 + 首个序号交互不崩
        set_pos(m, "g1", "q1", map_id, sa_id)
        out1 = await cmd(m, "interact_prop", "g1", "q1", "交互")
        check(f"{map_id}:{sa_id} 『交互』列表正常", not out1.startswith("这里没什么"), out1[:80])
        out2 = await cmd(m, "interact_prop", "g1", "q1", "交互 1")
        check(f"{map_id}:{sa_id} 『交互 1』不崩", len(out2) > 0 and "Traceback" not in out2, out2[:80])
        # 4 个孤儿 prop 本体已定义
    for pid in ["stall", "well", "washing_line", "haystack"]:
        check(f"孤儿 prop [{pid}] 已定义", pid in C.PROPS, pid)

    print("\n【2. 壁炉满血不吞次数】")
    clean_db()
    m = Main(None)
    make_player("g1", "q1", level=10)
    set_pos(m, "g1", "q1", "oak_town", "oak_town_4")  # 橡木镇旅店
    use_key = "oak_town:oak_town_4:fireplace"
    out = await cmd(m, "interact_prop", "g1", "q1", "交互 旅店壁炉")
    used = db.get_props_use("q1")
    check("满血交互→氛围文案(不恢复)", "暖意融融" in out, out[:120])
    check("满血交互→不 mark_props_use", use_key not in used, used)
    # 扣血后交互 → 正常恢复 + 记录
    p = db.get_player("g1", "q1")
    db.update_player("g1", "q1", hp=int(p["max_hp"] * 0.5))
    p = db.get_player("g1", "q1")
    hp0 = p["hp"]
    out = await cmd(m, "interact_prop", "g1", "q1", "交互 旅店壁炉")
    p = db.get_player("g1", "q1")
    used = db.get_props_use("q1")
    check("伤血交互→回血", p["hp"] > hp0, (hp0, p["hp"]))
    check("伤血交互→记录每日次数", use_key in used, used)
    # 当日再交互 → 每日限额
    out = await cmd(m, "interact_prop", "g1", "q1", "交互 旅店壁炉")
    check("当日第二次交互→每日限额文案", "今天已经在这里翻找过" in out, out[:120])

    print("\n【3. POI 键覆盖修复：功能 POI + 风景 POI 共存】")
    SCENIC = {"scenic_view", "ancient_tree_sight", "star_gazing"}
    FUNC = {"campfire", "shrine", "herb_patch", "loot_pile", "rune_stone", "fishing_spot", "note"}
    POI_KEYS = [
        "oak_plain:oak_plain_3", "emerald_forest:emerald_forest_3",
        "starlake:starlake_3", "frost_field:frost_field_3",
        "cinder_mountain:cinder_mountain_3", "dragon_ridge:dragon_ridge_3",
        "coral_reef:coral_reef_3",
    ]
    for key in POI_KEYS:
        ids = _subarea_pois(*key.split(":"))
        ok = (len(ids) >= 2
              and any(i in FUNC for i in ids)
              and any(i in SCENIC for i in ids)
              and all(i in C.POIS for i in ids))
        check(f"{key} 功能+风景共存", ok, ids)
    # v115 后块覆盖丢失：oak_plain_3 需保留 campfire（与基础块并集）
    ids = _subarea_pois("oak_plain", "oak_plain_3")
    check("oak_plain_3 保留 campfire", "campfire" in ids, ids)
    # 全局：所有 SUBAREA_POIS 挂载无死键
    dead = [k for k, ids in C.SUBAREA_POIS.items()
            for i in ids if i not in C.POIS]
    check("全部 SUBAREA_POIS 挂载可解析", not dead, dead[:10])
    # q9：SUBAREA_POIS 无重复 key（基础块 + v115 块须并集合并，重复 key 会被后者覆盖而静默丢 POI）。
    # 运行期 dict 键天然唯一，故用"受影响子区域并集保序断言"守护：基础块 POI 一个都不能丢。
    # 【基础块条目在前，v115 追加的新条目在后，去重保序】
    NEW_POI = {"merchant_camp", "ancient_altar", "bird_nest", "ice_sculpture",
               "dragon_bone", "shipwreck", "traveler_grave"}  # v115 新增 POI 前缀尾段
    BASE_MERGE = {
        "oak_plain_2": ["herb_patch", "campfire", "merchant_camp"],
        "gold_plain_3": ["star_gazing", "merchant_camp"],
        "gold_plain_2": ["campfire", "herb_patch", "ancient_altar"],
        "deep_lake_2": ["fishing_spot", "shrine", "ancient_altar"],
        "silverwood_2": ["fishing_spot", "loot_pile", "bird_nest"],
        "starlake_2": ["fishing_spot", "shrine", "bird_nest"],
        "emerald_forest_2": ["herb_patch", "campfire", "bird_nest"],
        "frost_field_1": ["campfire", "shrine", "ice_sculpture"],
        "frost_field_2": ["campfire", "shrine", "ice_sculpture"],
        "permafrost_field_2": ["campfire", "shrine", "ice_sculpture"],
        "dragon_ridge_1": ["campfire", "dragon_bone"],
        "bone_wild_2": ["campfire", "loot_pile", "dragon_bone"],
        "coral_reef_1": ["fishing_spot", "loot_pile", "shipwreck"],
        "storm_sea_2": ["scenic_view", "campfire", "shipwreck"],
        "misty_swamp_1": ["herb_patch", "loot_pile", "campfire", "traveler_grave"],
        "molten_abyss_1": ["loot_pile", "campfire", "traveler_grave"],
    }
    sa_by_tail = {k.rsplit(":", 1)[1]: k for k in C.SUBAREA_POIS}
    lost = []
    for tail, expect in BASE_MERGE.items():
        got = C.SUBAREA_POIS.get(sa_by_tail.get(tail), [])
        base_part = [b for b in expect if b not in NEW_POI]
        if not set(base_part) <= set(got):
            lost.append((tail, got))
    check("SUBAREA_POIS 并集合并：基础块 POI 无丢失(q9)", not lost, lost[:10])

    print("\n【4. 城镇探索冷却】")
    clean_db()
    m = Main(None)
    make_player("g1", "q1", level=10)
    set_pos(m, "g1", "q1", "oak_town", "oak_town_1")
    random.seed(1)
    out1 = await cmd(m, "explore", "g1", "q1", "探索")
    check("城镇首次探索正常", len(out1) > 0 and "过一会儿再来" not in out1, out1[:80])
    out2 = await cmd(m, "explore", "g1", "q1", "探索")
    check("连续探索→60s 冷却拦截", "过一会儿再来" in out2, out2[:120])
    cd = db.get_event_state("town_explore_cd_q1")  # v105 M23 P2-1：冷却 key 全局化（只含 qq_id，防跨群绕过）
    check("冷却 key 已写入 event_state", bool(cd), cd)

    print("\n【5. 世界 Boss 掉落：结算出物品】")
    clean_db()
    m = Main(None)
    # 5a. 掉落池数据完整性：Boss 名都在 WORLD_BOSS_POOL，物品全部可发放
    pool_names = {b["name"] for b in C.WORLD_BOSS_POOL}
    bad_pool = [k for k in WORLD_BOSS_DROPS if k not in pool_names]
    check("掉落池 Boss 名全部存在", not bad_pool, bad_pool)
    bad_item = []
    for boss, items in WORLD_BOSS_DROPS.items():
        for it in items:
            if it.startswith("mount_"):
                try:
                    C.make_mount_rein(it)
                except Exception as e:
                    bad_item.append((boss, it, repr(e)))
            elif it not in C.MATERIALS:
                bad_item.append((boss, it, "非材料"))
    check("掉落池物品全部可发放", not bad_item, bad_item[:5])
    # 5b. 单发验证：材料直入包
    r = m._grant_worldboss_drop("g1", "q1", "mat_zhan_hun_zhi_chen")
    check("掉落材料入包", db.count_item("g1", "q1", "mat_zhan_hun_zhi_chen") == 1, r)
    # 5c. 单发验证：缰绳生成道具
    r = m._grant_worldboss_drop("g1", "q1", "mount_steed")
    check("掉落缰绳入包", db.count_item("g1", "q1", "mountrein_mount_steed") == 1, r)
    # 5d. 完整结算模拟：世界事件 Boss hp=1 → 讨伐 → 攻击 → 击杀结算
    clean_db()
    m = Main(None)
    make_player("g1", "q1", level=20, name="测试")
    boss = dict(next(b for b in C.WORLD_BOSS_POOL if b["name"] == "巨史莱姆王·咕噜咕噜"))
    boss["hp"] = 1  # 一击击杀
    boss["max_hp"] = 80000
    if not boss.get("skills"):
        cand = [s for s, si in C.MONSTER_SKILLS.items() if si.get("kind") in ("物理", "魔法")]
        boss["skills"] = random.sample(cand, min(2, len(cand)))
    db.save_world_event("boss", int(time.time()) + 3600, {"boss": boss})
    set_pos(m, "g1", "q1", boss["map"], (C.MAP_BY_ID[boss["map"]]["subareas"] or [{}])[0].get("id", ""))
    p0 = db.get_player("g1", "q1")
    gold0, exp0 = p0["gold"], p0["exp"]
    out = await cmd(m, "hunt_boss", "g1", "q1", "讨伐")
    check("讨伐开战", "讨伐开始" in out, out[:100])
    # v154 读条命中制：攻击只排读条——命中结算在 _hostile_phase 推进时；Boss 一击残血后
    # 需下一次行动命令才会触发击杀判定。连续攻击直至击杀（上限 5 次防死循环）。
    out_lines = []
    for _i in range(5):
        out2 = await cmd(m, "attack", "g1", "q1", "攻击")
        out_lines.append(out2)
        if db.get_world_event() is None:
            break
    out = out + "\n" + "\n".join(out_lines)
    p = db.get_player("g1", "q1")
    n_mat = db.count_item("g1", "q1", "mat_zhan_hun_zhi_chen")
    n_mount = db.count_item("g1", "q1", "mountrein_mount_steed")
    check("世界Boss击杀结算出物品", n_mat + n_mount >= 1, (n_mat, n_mount))
    check("结算文案含掉落标记", "🎁" in out, out[-200:])
    check("结算金币/经验入账", p["gold"] > gold0 and p["exp"] > exp0, (gold0, p["gold"], exp0, p["exp"]))
    check("世界事件已清除", db.get_world_event() is None)

    print("\n【6. 7 城镇旅店】")
    for town in ["moon_court", "nameless_harbor", "wind_city", "anvil_fort",
                 "dragon_pass", "pearl_city", "ember_camp"]:
        sas = C.MAP_BY_ID.get(town, {}).get("subareas") or []
        inn = [s["id"] for s in sas if "heal" in (s.get("funcs") or []) and s.get("healer")]
        check(f"{town} 有 1 子区域可住宿(旅店)", len(inn) >= 1, sas and [s["id"] for s in sas])

    print("\n【7. deep_tunnel 商店】")
    dt = [s for s in C.MAP_BY_ID["deep_tunnel"]["subareas"] if s["id"] == "deep_tunnel_2"]
    check("deep_tunnel_2 存在", len(dt) == 1, dt)
    if dt:
        d2 = dt[0]
        check("中央大厅 funcs 含 shop", "shop" in (d2.get("funcs") or []), d2.get("funcs"))
        check("中央大厅 shop=True", d2.get("shop") is True, d2.get("shop"))
    from content.catalog_life import SHOP_SUBAREA_ITEMS, SHOP_WEAPONS
    stock = SHOP_SUBAREA_ITEMS.get("deep_tunnel_2") or []
    check("中央大厅有配货", len(stock) >= 1, stock)
    bad = [i for i in stock if i not in C.ITEMS]
    check("配货物品全部可解析", not bad, bad)
    check("deep_tunnel 武器配货存在", "deep_tunnel" in SHOP_WEAPONS, list(SHOP_WEAPONS)[:5])

    print("\n【8. HIDDEN_MAP_UNLOCK 无死条目】")
    dead_hidden = [k for k in C.HIDDEN_MAP_UNLOCK if k not in C.MAP_BY_ID]
    check("所有隐藏图目标在 MAPS", not dead_hidden, (dead_hidden, list(C.HIDDEN_MAP_UNLOCK)))

    print("\n【9. 回城卷轴落广场】")
    clean_db()
    m = Main(None)
    make_player("g1", "q1", level=70)
    set_pos(m, "g1", "q1", "cinder_mountain", "cinder_mountain_3")
    db.add_item("g1", "q1", "i_scroll_escape",
                {"name": "回城卷轴", "type": "消耗品", "stackable": True,
                 "effect": "return_vila", "price": 500})
    out = await cmd(m, "use", "g1", "q1", "使用 回城卷轴")
    p = db.get_player("g1", "q1")
    town = C.MAP_BY_ID.get(p["cur_map"], {})
    check("回城卷轴→最近城镇(非橡木镇)", p["cur_map"] != "oak_town" and town.get("type") == C.MAP_TYPE_TOWN,
          (p["cur_map"], out[:80]))
    first_sa = (town.get("subareas") or [{}])[0]
    check("落点=城镇 subareas[0](广场)", p["cur_subarea"] == first_sa.get("id"), (p["cur_subarea"], first_sa.get("id")))
    check("回城卷轴已消耗", db.count_item("g1", "q1", "i_scroll_escape") == 0)
    check("文案含城镇名", town.get("name", "") in out, out[:100])

    print("\n【10. 战败回就近城镇】")
    clean_db()
    m = Main(None)
    make_player("g1", "q1", level=70)
    # 10a. 就近城镇 BFS：Lv.60+ 场景不再送回橡木镇
    for wild_map, expect_not in [("cinder_mountain", "oak_town"), ("dragon_ridge", "oak_town"),
                                 ("storm_sea", "oak_town"), ("molten_abyss", "oak_town")]:
        t = m._nearest_town(wild_map)
        town = C.MAP_BY_ID.get(t, {})
        check(f"{wild_map}→就近城镇({t})非橡木镇且是城镇",
              t != expect_not and town.get("type") == C.MAP_TYPE_TOWN, (t, town.get("name")))
    # 10b. 战败全流程：落最近城镇中心广场 + 满血 + 扣 10% 金币
    set_pos(m, "g1", "q1", "cinder_mountain", "cinder_mountain_3")
    p = db.get_player("g1", "q1")
    db.update_player("g1", "q1", hp=10, gold=1000)
    p = db.get_player("g1", "q1")
    ev = FakeEvent("g1", "q1", "攻击")
    results = []
    for r in m._handle_defeat(ev, "g1", "q1", p, {"name": "烬山魔物", "lv": 70}, "你被击败了"):
        results.append(r)
    out = "\n".join(results)
    p = db.get_player("g1", "q1")
    town = C.MAP_BY_ID.get(p["cur_map"], {})
    first_sa = (town.get("subareas") or [{}])[0]
    check("战败→回就近城镇(非橡木镇)", p["cur_map"] != "oak_town" and town.get("type") == C.MAP_TYPE_TOWN,
          (p["cur_map"], town.get("name")))
    check("战败→落中心广场 subareas[0]", p["cur_subarea"] == first_sa.get("id"),
          (p["cur_subarea"], first_sa.get("id")))
    check("战败→满血复活", p["hp"] == p["max_hp"], (p["hp"], p["max_hp"]))
    check("战败→扣 10% 金币", p["gold"] == 900, p["gold"])
    check("战败文案含落点广场名", first_sa.get("name", "") in out, out[:120])

    print(f"\n======== 结果: {passed} 通过 / {failed} 失败 ========")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
