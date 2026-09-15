# -*- coding: utf-8 -*-
"""v124 新增任务怪验证：腐牙萨满·嚎骨 / 噬根藤精 / 野猪（S18/S57/S101）

验证项：
1. 三个任务怪挂载到对应子区域槽位（黑森林·腐牙营地 elite / 白鹿之森·月光药园 / 白鹿之森深处）
2. 可通过 ENCY_MAP_MONSTERS / ENCY_MONSTER_MAP / 怪物索引解析到
3. skills 全部存在于 MONSTER_SKILLS；drops 全部可 resolve 到材料 id
4. build_monster 可构建（可遭遇可击杀）；击杀计数逻辑（combat.py 同款）命中三个任务目标
5. 子区域网状连接可达（月光药园 white_deer_forest_7）
6. 黑名单词扫描（灭世/弑神/虚空/血怒/屠戮/金身/不动如山/百裂/气功/金刚/罗汉/内力/内息）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tests/
import conftest  # noqa: E402  设置路径/shim/GWEN_GAME_DB
from conftest import C  # noqa: E402
# ★ P5E-DELETE（2026-09-15，删壳批）：`_INDEXES` 在包侧是**惰性**的（`content/index.py:92-103`；
#   `C._INDEXES` 是同一只 dict，未建时为空）。旧宿主门面是装配期渴求态 ⇒ 本文件过去不需显式建。
#   终态按包侧口径**显式取一次**（`C.resolve` 内部就走 `_indexes()`）。判据与阈值一条未变。
C.resolve("monsters", "野狗")

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


# ---------- 1. 子区域挂载 ----------
print("【1. 子区域槽位挂载】")
bf_sas = {sa["id"]: sa for sa in C.SUBAREAS.get("black_forest", [])}
sa4 = bf_sas.get("black_forest_4")
check("黑森林·腐牙营地(black_forest_4) 存在", sa4 is not None)
elite = sa4.get("elite") if sa4 else None
check("腐牙营地 elite 槽 = 腐牙萨满·嚎骨",
      elite and elite[0] == "m_fu_ya_sa_man_hao_gu" and elite[1] == "腐牙萨满·嚎骨"
      and elite[2] == "elite" and elite[3] == 70,
      str(elite))
check("嚎骨 drops=腐牙血囊", elite and elite[5] == ["腐牙血囊"], str(elite and elite[5]))

wdf_sas = {sa["id"]: sa for sa in C.SUBAREAS.get("white_deer_forest", [])}
sa7 = wdf_sas.get("white_deer_forest_7")
check("白鹿之森·月光药园(white_deer_forest_7) 存在", sa7 is not None and sa7.get("name") == "月光药园")
tg = None
if sa7:
    tg = next((m for m in (sa7.get("monsters") or []) if m[0] == "m_shi_gen_teng_jing"), None)
check("月光药园 monsters 含 噬根藤精 Lv.11",
      tg and tg[1] == "噬根藤精" and tg[2] == "dps" and tg[3] == 11, str(tg))
check("噬根藤精 drops=草药/月光草", tg and tg[5] == ["草药", "月光草"], str(tg and tg[5]))

sa2 = wdf_sas.get("white_deer_forest_2")
boar = None
if sa2:
    boar = next((m for m in (sa2.get("monsters") or []) if m[0] == "m_wild_boar"), None)
check("白鹿之森深处 monsters 含 野猪(复用 m_wild_boar) Lv.5",
      boar and boar[1] == "野猪" and boar[3] == 5, str(boar))
check("野猪 drops=野猪牙+月光棉(v167挂料)", boar and boar[5] == ["野猪牙", "月光棉"], str(boar and boar[5]))

# 04 章怪物表已有（野猪岭）——只挂载未新增重复条目
check("野猪岭 野猪王·裂鬃 仍存在（未重复新增）",
      any(m[1] == "野猪王·裂鬃" for sa in C.SUBAREAS.get("boar_ridge", [])
          for m in (sa.get("monsters") or []) + ([sa["elite"]] if sa.get("elite") else [])),
      "boar_ridge 无野猪王")

# ---------- 2. 百科/索引解析 ----------
print("【2. ENCY_MAP_MONSTERS / ENCY_MONSTER_MAP / 怪物索引】")
bf_entries = [e[0] for e in C.ENCY_MAP_MONSTERS.get("black_forest", [])]
check("黑森林百科含 腐牙萨满·嚎骨(精英)", "腐牙萨满·嚎骨" in bf_entries, str(bf_entries))
check("黑森林百科含 腐牙萨满·嚎骨(精英档)", ("腐牙萨满·嚎骨", 70, "精英") in C.ENCY_MAP_MONSTERS.get("black_forest", []),
      str(C.ENCY_MAP_MONSTERS.get("black_forest", [])))
wdf_entries = [e[0] for e in C.ENCY_MAP_MONSTERS.get("white_deer_forest", [])]
check("白鹿之森百科含 噬根藤精", "噬根藤精" in wdf_entries, str(wdf_entries))
check("白鹿之森百科含 野猪", "野猪" in wdf_entries, str(wdf_entries))
for nm in ("腐牙萨满·嚎骨", "噬根藤精", "野猪"):
    check(f"ENCY_MONSTER_MAP 可查 {nm}", nm in C.ENCY_MONSTER_MAP, str(C.ENCY_MONSTER_MAP.get(nm)))
    check(f"怪物索引 name_to_id 可查 {nm}", nm in C._INDEXES["monsters"]["name_to_id"],
          str(C._INDEXES["monsters"]["name_to_id"].get(nm)))
# 掉落来源反查
check("腐牙血囊 来源含 腐牙萨满·嚎骨",
      any(src[1] == "腐牙萨满·嚎骨" for src in C.ENCY_MATERIAL_SOURCE.get("腐牙血囊", [])),
      str(C.ENCY_MATERIAL_SOURCE.get("腐牙血囊")))

# ---------- 3. skills / drops 校验 ----------
print("【3. skills 存在性 / drops 解析】")
ALL_SKILL_IDS = []
for sa_list in C.SUBAREAS.values():
    for sa in sa_list:
        for m in (sa.get("monsters") or []):
            ALL_SKILL_IDS += m[4]
        for f in ("elite", "boss"):
            if sa.get(f):
                ALL_SKILL_IDS += sa[f][4]
for sk in ("ms_ai_hao", "ms_an_ying_dan", "ms_teng_bian", "ms_gen_xu_chan_rao", "ms_chong_zhuang"):
    check(f"MONSTER_SKILLS 含 {sk}", sk in C.MONSTER_SKILLS)
for drop, expect_id in (("腐牙血囊", "mat_fu_ya_xue_nang"), ("草药", "mat_cao_yao"),
                        ("月光草", "mat_yue_guang_cao"), ("野猪牙", "mat_ye_zhu_ya")):
    rid = C.resolve("materials", drop)
    check(f"掉落 {drop} → {expect_id}", rid == expect_id, rid)

# ---------- 4. build_monster + 击杀计数 ----------
print("【4. build_monster 可构建 + 击杀计数命中（combat.py 同款逻辑）】")
quests = {q["id"]: q for q in C.SIDE_QUESTS}
# 每个任务怪应挂载的精确子区域槽位（map_id, subarea_id, 槽位名, 期望 Lv）
SLOTS = {
    "s18": ("black_forest", "black_forest_4", "elite", 70),
    "s57": ("white_deer_forest", "white_deer_forest_7", "monsters", 11),
    "s101": ("white_deer_forest", "white_deer_forest_2", "monsters", 5),
}
for sid, mob_name, (map_id, sa_id, slot, expect_lv) in (
        ("s18", "腐牙萨满·嚎骨", SLOTS["s18"]),
        ("s57", "噬根藤精", SLOTS["s57"]),
        ("s101", "野猪", SLOTS["s101"])):
    q = quests.get(sid)
    check(f"{sid} 任务注册", q is not None)
    if not q:
        continue
    obj = q.get("objective") or {}
    check(f"{sid} objective.kill={mob_name}", obj.get("kill") == mob_name, str(obj))
    sa = next((s for s in C.SUBAREAS.get(map_id, []) if s["id"] == sa_id), None)
    ent = None
    if sa:
        if slot == "elite":
            ent = sa.get("elite") if sa.get("elite") and sa["elite"][1] == mob_name else None
        else:
            ent = next((m for m in (sa.get("monsters") or []) if m[1] == mob_name), None)
    check(f"{sid} 怪物条目挂载于 {map_id}:{sa_id} {slot} 槽", ent is not None, f"{map_id}:{sa_id} 未找到 {mob_name}")
    if ent:
        monster = C.build_monster(ent, {"id": "x", "name": "测试图", "area": "x"})
        check(f"{sid} build_monster name/lv", monster["name"] == mob_name and monster["lv"] == expect_lv,
              f"{monster['name']} Lv.{monster['lv']}")
        # combat.py 击杀计数：monster['name'] == obj['kill'] or startswith(obj['kill'] + '·')
        hit = monster["name"] == obj.get("kill") or monster["name"].startswith(obj.get("kill", "") + "·")
        check(f"{sid} 击杀计数逻辑命中（可计数）", hit)
        check(f"{sid} skills 非空且均注册", bool(monster["skills"]) and all(s in C.MONSTER_SKILLS for s in monster["skills"]))
        if sid == "s18":
            check("s18 为精英（is_elite）", monster["is_elite"] is True)

# ---------- 5. 子区域连接可达 ----------
print("【5. 月光药园网状连接】")
links = C.subarea_links("white_deer_forest", "white_deer_forest_7")
check("white_deer_forest_7 可到达（连 密林深处）", links == ["white_deer_forest_6"], str(links))
links6 = C.subarea_links("white_deer_forest", "white_deer_forest_6")
check("white_deer_forest_6 连回 月光药园（双向对称）", "white_deer_forest_7" in links6, str(links6))

# ---------- 6. 黑名单词扫描 ----------
print("【6. 黑名单词扫描】")
BLACK = ["灭世", "弑神", "虚空", "血怒", "屠戮", "金身", "不动如山", "百裂", "气功", "金刚", "罗汉", "内力", "内息"]
names = ["腐牙萨满·嚎骨", "噬根藤精", "野猪"]
check("三个怪物名无黑名单词", not any(b in n for n in names for b in BLACK))

print(f"\n结果: {PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)
