# -*- coding: utf-8 -*-
"""v124.2 全量数据自检：SIDE_QUESTS objective/reward 引用可解析（纯数据加载，不建号不落库）

铁律：GWEN_GAME_DB 指向 tests/ 私有临时库（绝对路径），不触碰生产 game_data.db。
覆盖：
  - objective：kill 怪物名在怪物索引；collect/use 物品在 items/materials 可解析；
    explore/map 为合法地图 id；find 型 objective.map（缺省回退任务顶层 map）合法
  - reward：全部 reward_item（含 eq: 前缀/列表/分支选项）可解析；reward_pet/reward_mount 在册
  - v124.2 专项修复锁定：s93 use=月鳞（半片）、s74 凭证 type=任务道具、s80 use=醇香麦酒、
    s77/s115 任务怪挂载、s56/s73 缺口补齐
"""
import os
import sys

os.environ["GWEN_GAME_DB"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "test_v1242_data_integrity.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conftest import C  # noqa: E402
# B16 收口：宿主 game/data 已删 —— 原 _assembly._MONSTER_INDEX 的等价口 = 包内自建索引
from content import index as _IDX  # noqa: E402
_MONSTER_INDEX = _IDX._indexes()["monsters"]["name_to_id"]

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def resolve_item(name):
    """物品名 → items 或 materials 任一表可解析即合法。"""
    iid = C.resolve("items", name)
    if iid in C.ITEMS:
        return True
    mid = C.resolve("materials", name)
    if mid in C.MATERIALS:
        return True
    return False


def resolve_reward_item(ri):
    """单条 reward_item 值可解析（str 或 list）。"""
    items = ri if isinstance(ri, list) else [ri]
    for it in items:
        if not isinstance(it, str):
            return False
        if it.startswith("eq:"):
            if it[3:] not in C.EQUIP_ROSTER_BY_NAME:
                return False
        elif not resolve_item(it):
            return False
    return True


_OBJ_KEYS_OK = {"kill", "collect", "use", "explore", "find", "map",
                "count", "collect_count", "chance", "kill_any"}

print("【全量数据自检】")
sq_list = C.SIDE_QUESTS
ids = [q["id"] for q in sq_list]

# ---- 覆盖范围：s46-s121 + hq 全部存在 ----
miss_ids = [f"s{i}" for i in range(46, 122) if f"s{i}" not in ids]
miss_ids += [h for h in ("hq5_1", "hq5_2", "hq5_3", "hq6_1", "hq6_2", "hq6_3",
                         "hq7_1", "hq7_2", "hq7_3", "hq8_1", "hq8_2", "hq8_3", "hq8_4")
             if h not in ids]
check(f"T1 s46-s121+hq 全部登记（{len(ids)} 条支线）", not miss_ids, f"缺失: {miss_ids}")

# ---- objective 键白名单 ----
bad_keys = []
for sq in sq_list:
    for k in (sq.get("objective") or {}):
        if k not in _OBJ_KEYS_OK:
            bad_keys.append((sq["id"], k))
check("T2 objective 键全部在白名单", not bad_keys, f"{bad_keys}")

# ---- kill 怪物挂载 ----
bad_kill = [(sq["id"], sq["objective"]["kill"]) for sq in sq_list
            if sq.get("objective", {}).get("kill")
            and sq["objective"]["kill"] not in _MONSTER_INDEX]
check("T3 全部 kill 目标在怪物索引", not bad_kill, f"{bad_kill}")

# ---- collect / use 物品可解析 ----
bad_collect = [(sq["id"], sq["objective"]["collect"]) for sq in sq_list
               if sq.get("objective", {}).get("collect")
               and not resolve_item(sq["objective"]["collect"])]
check("T4 全部 collect 目标可解析", not bad_collect, f"{bad_collect}")
bad_use = [(sq["id"], sq["objective"]["use"]) for sq in sq_list
           if sq.get("objective", {}).get("use")
           and not resolve_item(sq["objective"]["use"])]
check("T5 全部 use 目标可解析", not bad_use, f"{bad_use}")

# ---- explore / map 地图合法 ----
bad_explore = [(sq["id"], sq["objective"]["explore"]) for sq in sq_list
               if sq.get("objective", {}).get("explore")
               and sq["objective"]["explore"] not in C.MAP_BY_ID]
check("T6 全部 explore 目标为合法地图", not bad_explore, f"{bad_explore}")
bad_map = []
for sq in sq_list:
    obj = sq.get("objective") or {}
    m = obj.get("map") or sq.get("map")
    if obj.get("find") and m and m not in C.MAP_BY_ID:
        bad_map.append((sq["id"], m))
check("T7 全部 find 型地图合法（objective.map 缺省回退任务顶层 map）", not bad_map, f"{bad_map}")
# use 型带 map 的任务，map 也必须合法（use 地图校验依赖它）
bad_use_map = [(sq["id"], obj.get("map")) for sq in sq_list
               if (obj := sq.get("objective") or {}).get("use") and obj.get("map")
               and obj["map"] not in C.MAP_BY_ID]
check("T8 全部 use 型任务 map 合法", not bad_use_map, f"{bad_use_map}")

# ---- reward_item（含分支选项 / eq: 前缀 / 列表）----
bad_ri = []
for sq in sq_list:
    ri = sq.get("reward_item")
    if ri is not None and not resolve_reward_item(ri):
        bad_ri.append((sq["id"], ri))
    for opt in (sq.get("branch") or {}).get("options") or []:
        oi = opt.get("reward_item")
        if oi is not None and not resolve_reward_item(oi):
            bad_ri.append((sq["id"], "branch:" + str(oi)))
check("T9 全部 reward_item 可解析（含 eq:/列表/分支选项）", not bad_ri, f"{bad_ri}")

# ---- reward_pet / reward_mount ----
pet_keys = [p["key"] for p in C.PET_POOL]
bad_pet = [(sq["id"], sq["reward_pet"]) for sq in sq_list
           if sq.get("reward_pet") and sq["reward_pet"] not in pet_keys]
check("T10 全部 reward_pet 在宠物池", not bad_pet, f"{bad_pet}")
bad_mount = [(sq["id"], sq["reward_mount"]) for sq in sq_list
             if sq.get("reward_mount") and sq["reward_mount"] not in C.MOUNT_BY_KEY]
check("T11 全部 reward_mount 在坐骑池", not bad_mount, f"{bad_mount}")

# ---- v124.2 专项修复锁定 ----
sq93 = next(q for q in sq_list if q["id"] == "s93")
check("T12 s93 objective.use == 『月鳞（半片）』",
      sq93["objective"].get("use") == "月鳞（半片）", f"实际: {sq93['objective'].get('use')!r}")
sq74 = next(q for q in sq_list if q["id"] == "s74")
_voucher = C.ITEMS.get("i_shang_hui_gu_fen_ping_zheng", {})
check("T13 s74 商会股份凭证 type == 任务道具（收藏品改任务道具）",
      _voucher.get("type") == "任务道具", f"实际: {_voucher.get('type')!r}")
sq80 = next(q for q in sq_list if q["id"] == "s80")
check("T14 s80 objective.use == 『醇香麦酒』（消耗品）",
      sq80["objective"].get("use") == "醇香麦酒", f"实际: {sq80['objective'].get('use')!r}")
sq77 = next(q for q in sq_list if q["id"] == "s77")
check("T15 s77 蒙面小贼·米洛 已挂载怪物索引",
      sq77["objective"].get("kill") in _MONSTER_INDEX)
sq115 = next(q for q in sq_list if q["id"] == "s115")
check("T16 s115 精灵兽 已挂载怪物索引",
      sq115["objective"].get("kill") in _MONSTER_INDEX)
sq56 = next(q for q in sq_list if q["id"] == "s56")
check("T17 s56 菜谱拓本 可解析", resolve_item(sq56["objective"].get("use", "")))
sq73 = next(q for q in sq_list if q["id"] == "s73")
check("T18 s73 灰旗会账册 可解析", resolve_item(sq73["objective"].get("collect", "")))
sq18 = next(q for q in sq_list if q["id"] == "s18")
check("T19 s18 腐牙萨满·嚎骨 已挂载怪物索引",
      sq18["objective"].get("kill") in _MONSTER_INDEX)

print(f"\n结果: {PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)
