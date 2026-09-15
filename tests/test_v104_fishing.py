# -*- coding: utf-8 -*-
"""v104 M15 垂钓修复回归（tests/test_v104_fishing.py）

覆盖 8 项 v104 垂钓修复：
  1. 血饵生效：core/fishing.py roll_fish 稀有鱼种阈值（≤15）——固定 seed 采样
     带血饵 vs 不带，稀有鱼种（夜光鲛）概率显著提升；结算链路一次性消耗并提示
  2. 收藏鱼回收：彩蛋收藏鱼『出售』按 1 金币回收（0.8 折 int(1*0.8)=0 卖不掉的旧 bug）
  3. 每日垂钓任务漏计修复：鱼王/宝物/垃圾 分支也推进每日副业任务（连钓 5 次垃圾→进度 5）
  4. 鱼饵配方存在：炼金 萤光鱼饵 + 烹饪 面团鱼饵/血饵，材料可备齐、制作成功
  5. 夜光鲛有产出源：FISH_POOL 含 夜光鲛（限迷雾沼泽），MATERIALS 有 mat_ye_guang_jiao
  6. 垂钓图鉴：图鉴命令展示彩蛋收藏鱼进度（已收藏 X/3 + 累计钓获计数）
  7. 钓点子区域：11 个钓点全部带 subarea 且均存在于对应地图子区域；行为拦截/放行
  8. 渔获价格一致：FISH_POOL 与 MATERIALS 全量交叉价格一致（鲛人泪/深海水晶/龙涎香等）
"""
import sys, os, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run
# ★ P5E-DELETE（2026-09-15，删壳批）：猴补落点改到**包内真源模块**。
#   删壳前 `C` = 宿主聚合壳 `game.content`（普通模块对象，可写）；终态 `C` =
#   `content.facade._Aggregate`（`__slots__` 惰性句柄，**不可写**）⇒ `C.roll_fish = …` /
#   `C.roll_collect_fish = …` 报 `AttributeError: '_Aggregate' object has no attribute …`。
#   口径 = 项目既有「补名会移动打桩落点 ⇒ 就地改真源那一只对象」（R5/`test_v1264` 同款）：
#   两个名的 `_NAME_SRC` 真源都是 `content.fishing`，包内消费方
#   （`content/profession.py::_PkgFace._MAP`）也按名取它 ⇒ 桩打在真源模块上，
#   取件时机与可见性逐字不变。判据一条未变。
from content import fishing as _FISH  # noqa: E402

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""


def set_roll_fish(m, fish):
    """monkeypatch content.fishing.roll_fish（包内真源；`C.roll_fish` 的落点）返回固定渔获"""
    m._roll_fish_orig = _FISH.roll_fish
    _FISH.roll_fish = lambda lv, spot=None, bait=None: fish

def restore_roll_fish(m):
    _FISH.roll_fish = m._roll_fish_orig

def set_roll_collect(m, cf):
    """monkeypatch content.fishing.roll_collect_fish（包内真源）返回固定彩蛋收藏鱼（None=不触发）"""
    m._roll_cf_orig = _FISH.roll_collect_fish
    _FISH.roll_collect_fish = lambda spot, night=False: cf

def restore_roll_collect(m):
    _FISH.roll_collect_fish = m._roll_cf_orig

def fish_dict(name, quality, ftype="鱼", price=12):
    return {"name": name, "quality": quality, "type": ftype, "price": price,
            "spots": None, "weight": 1, "desc": "测试渔获"}

def gold_of(gid, qid):
    return db.get_player(gid, qid)["gold"]

def daily_state(m, gid, qid):
    return m._daily_prof_state(gid, qid)  # (tkey, name, need, gold, cnt, claimed)


async def main():
    clean_db()
    m = Main(None)
    # w1：主力垂钓（fishing + cooking 双副业）；w2：炼金
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    await cmd(m, "register", "g1", "w2", "注册 法师 新手 男")
    db.update_player("g1", "w1", apprentices=["fishing", "cooking"], level=20, gold=5000,
                     cur_map="oak_plain", cur_subarea="oak_plain_3")
    db.activate_prof("g1", "w1", "fishing")
    db.activate_prof("g1", "w1", "cooking")
    db.add_prof_exp("g1", "w1", "fishing", 200)   # Lv.5
    db.add_prof_exp("g1", "w1", "cooking", 200)   # Lv.5
    db.update_player("g1", "w2", apprentices=["alchemy"], level=10, gold=5000,
                     cur_map="oak_plain", cur_subarea="oak_plain_3")
    db.activate_prof("g1", "w2", "alchemy")
    db.add_prof_exp("g1", "w2", "alchemy", 200)   # Lv.5 ≥ 3

    print("【1 血饵生效（roll_fish 稀有鱼种阈值）】")
    def sample(spot, bait, n=4000, lv=9):
        random.seed(20260813)
        cnt = {}
        for _ in range(n):
            f = _FISH.roll_fish(lv, spot, bait)
            cnt[f["name"]] = cnt.get(f["name"], 0) + 1
        return cnt
    base = sample("misty_swamp", None)
    blood = sample("misty_swamp", "blood")
    b0 = base.get("夜光鲛", 0)
    b1 = blood.get("夜光鲛", 0)
    print(f"  迷雾沼泽 Lv.9 ×4000 采样：无血饵 夜光鲛 {b0}（{b0/40:.2f}%）| 血饵 {b1}（{b1/40:.2f}%）| 提升 {b1/max(1,b0):.2f}×")
    check("无血饵基线能出夜光鲛（产出源）", b0 > 0, f"{b0}")
    check("血饵稀有鱼种概率显著提升(>1.5×)", b1 > b0 * 1.5, f"{b1} vs {b0}*1.5={b0*1.5:.0f}")
    # 结算链路：血饵一次性消耗 + 提示
    db.set_event_state(f"bait_w1", json.dumps({"kind": "blood"}, ensure_ascii=False))
    set_roll_fish(m, fish_dict("银鳞鱼", "white"))
    out = m._settle_fishing("g1", "w1", {"spot": "橡木溪流", "spot_map": "oak_plain"})
    restore_roll_fish(m)
    check("结算提示血饵生效", "鱼饵【血饵】生效了" in out, out[:200])
    check("血饵结算后一次性清除", not db.get_event_state(f"bait_w1"))

    print("【2 收藏鱼回收（1 金币，非 0.8 折=0）】")
    db.update_player("g1", "w1", cur_map="oak_plain", cur_subarea="oak_plain_3")
    set_roll_collect(m, C.FISH_COLLECT[0])  # 虹彩龙鲤
    set_roll_fish(m, fish_dict("银鳞鱼", "white"))
    out = m._settle_fishing("g1", "w1", {"spot": "橡木溪流", "spot_map": "oak_plain"})
    restore_roll_fish(m)
    restore_roll_collect(m)
    check("钓获彩蛋收藏鱼入包", db.count_item("g1", "w1", "mat_rainbow_kite") >= 1, out[:300])
    check("入包提示回收仅 1 金币", "回收仅 1 金币" in out, out[:300])
    # 出售需在商店子区域（材料对应店铺规则，_pawn_rate 先于 _sell_one）
    db.update_player("g1", "w1", cur_map="dawn_city", cur_subarea="dawn_city_5")  # 晨曦药剂坊
    g0 = gold_of("g1", "w1")
    out = await cmd(m, "sell", "g1", "w1", "出售 虹彩龙鲤")
    check("出售成功提示", "你出售了 虹彩龙鲤" in out, out[:200])
    check("按 1 金币回收（旧 bug 为 0 金卖不掉）", gold_of("g1", "w1") == g0 + 1,
          f"{g0} -> {gold_of('g1','w1')}")
    check("收藏鱼已从背包移除", db.count_item("g1", "w1", "mat_rainbow_kite") == 0)

    print("【3 每日垂钓任务漏计修复（鱼王/宝物/垃圾分支推进）】")
    # v105R3 M13 P2-1：key 已去 group_id，测试同步新签名
    key = m._daily_prof_key("w1")
    # 3a. 连钓 5 次垃圾 → 进度 5 + 领奖
    db.set_event_state(key, "fishing|垂钓|5|50|0|0")
    g0 = gold_of("g1", "w1")
    set_roll_fish(m, fish_dict("水草", "white", "垃圾", 1))
    last = ""
    for i in range(5):
        last = m._settle_fishing("g1", "w1", {"spot": "橡木溪流", "spot_map": "oak_plain"})
    restore_roll_fish(m)
    tkey, name, need, rgold, cnt, claimed = daily_state(m, "g1", "w1")
    check("垃圾×5 → 每日任务进度 5 并完成", cnt == 5 and claimed, f"{tkey} {cnt}/{need} claimed={claimed}")
    check("任务完成发放奖励 50 金币", gold_of("g1", "w1") == g0 + 50, f"{g0} -> {gold_of('g1','w1')}")
    check("结算文案含任务完成提示", "今日副业任务完成" in last, last[:200])
    # 3b. 鱼王分支推进
    db.set_event_state(key, "fishing|垂钓|5|50|0|0")
    set_roll_fish(m, fish_dict("鱼王·翡翠巨龙", "orange", "鱼王", 500))
    m._settle_fishing("g1", "w1", {"spot": "铁港码头", "spot_map": "harbor_docks"})
    restore_roll_fish(m)
    tkey, name, need, rgold, cnt, claimed = daily_state(m, "g1", "w1")
    check("鱼王分支推进每日任务（原漏计）", cnt == 1, f"{cnt}")
    # 3c. 宝物分支推进
    db.set_event_state(key, "fishing|垂钓|5|50|0|0")
    set_roll_fish(m, fish_dict("陈旧的宝箱", "purple", "宝物", 0))
    m._settle_fishing("g1", "w1", {"spot": "铁港码头", "spot_map": "harbor_docks"})
    restore_roll_fish(m)
    tkey, name, need, rgold, cnt, claimed = daily_state(m, "g1", "w1")
    check("宝物分支推进每日任务（原漏计）", cnt == 1, f"{cnt}")

    print("【4 鱼饵配方（炼金/烹饪 3 条）】")
    r_glow = C.ALCHEMY_RECIPES.get("al_ying_guang_yu_er")
    r_dough = C.COOKING_RECIPES.get("cook_dough_bait")
    r_blood = C.COOKING_RECIPES.get("cook_blood_bait")
    check("萤光鱼饵配方存在", bool(r_glow) and r_glow["name"] == "萤光鱼饵", str(r_glow))
    check("面团鱼饵配方存在", bool(r_dough) and r_dough["name"] == "面团鱼饵", str(r_dough))
    check("血饵配方存在", bool(r_blood) and r_blood["name"] == "血饵", str(r_blood))
    # 材料备齐 → 炼金合成 萤光鱼饵
    for k, cnt in (r_glow or {}).get("cost", {}).items():
        db.add_item("g1", "w2", k, {"name": C.display("materials", k), "type": "材料",
                                    "stackable": True, "price": C.MATERIALS[k]["price"]}, count=cnt)
    out = await cmd(m, "alchemy_craft", "g1", "w2", "合成 萤光鱼饵")
    check("炼金合成萤光鱼饵成功", "炼金成功" in out and "萤光鱼饵" in out, out[:300])
    check("萤光饵入包", db.count_item("g1", "w2", "it_glow_bait") >= 1)
    check("材料已扣除（月光草/空瓶）",
          db.count_item("g1", "w2", "mat_yue_guang_cao") == 0 and db.count_item("g1", "w2", "mat_kong_ping") == 0)
    # 烹饪 面团鱼饵 + 血饵
    for k, cnt in (r_dough or {}).get("cost", {}).items():
        db.add_item("g1", "w1", k, {"name": C.display("materials", k), "type": "材料",
                                    "stackable": True, "price": C.MATERIALS[k]["price"]}, count=cnt)
    for k, cnt in (r_blood or {}).get("cost", {}).items():
        db.add_item("g1", "w1", k, {"name": C.display("materials", k), "type": "材料",
                                    "stackable": True, "price": C.MATERIALS[k]["price"]}, count=cnt)
    out = await cmd(m, "cooking", "g1", "w1", "烹饪 面团鱼饵")
    check("烹饪面团鱼饵成功", "烹饪成功" in out and "面团鱼饵" in out, out[:300])
    out = await cmd(m, "cooking", "g1", "w1", "烹饪 血饵")
    check("烹饪血饵成功", "烹饪成功" in out and "血饵" in out, out[:300])
    check("面团饵入包", db.count_item("g1", "w1", "it_dough_bait") >= 1)
    check("血饵入包", db.count_item("g1", "w1", "it_blood_bait") >= 1)
    check("烹饪材料已扣除（面粉/兽血）",
          db.count_item("g1", "w1", "mat_mian_fen") == 0 and db.count_item("g1", "w1", "mat_shou_xue") == 0)

    print("【5 夜光鲛产出源】")
    yj = [f for f in C.FISH_POOL if f["name"] == "夜光鲛"]
    check("FISH_POOL 含夜光鲛", len(yj) == 1, str(yj))
    check("夜光鲛限定迷雾沼泽钓点", bool(yj) and "misty_swamp" in yj[0]["spots"], str(yj))
    mm = C.MATERIALS.get("mat_ye_guang_jiao")
    check("MATERIALS 定义 mat_ye_guang_jiao", bool(mm) and mm["name"] == "夜光鲛", str(mm))
    check("夜光鲛价格一致(35)", bool(yj) and bool(mm) and yj[0]["price"] == mm["price"] == 35,
          f"{yj[0]['price']} vs {mm and mm['price']}")
    check("迷雾沼泽可实际钓出夜光鲛", b0 > 0, f"采样 {b0} 条")

    print("【6 垂钓图鉴（收藏鱼计数展示出口）】")
    # catch_collect 统计已由第 2 节真实钓获路径（_collect_bonus_line）累计 1 次
    db.add_item("g1", "w1", "mat_moon_jelly", {"name": "月华水母", "type": "收藏",
                                               "stackable": True, "price": 1})
    out = await cmd(m, "bestiary", "g1", "w1", "图鉴")
    check("图鉴展示彩蛋收藏鱼区块", "彩蛋收藏鱼" in out, out[:400])
    check("图鉴展示已收藏鱼名", "月华水母" in out, out[:400])
    # v104 R3 M15 P2-3：收藏状态永久化——第 2 节钓获的虹彩龙鲤已解锁隐藏成就（出售后仍在），
    # 加上背包里的月华水母 = 2/3（旧语义按背包判定只算 1/3，出售后图鉴会回退）
    check("图鉴展示已收藏进度 2/3", "已收藏 2/3" in out, out[:400])
    check("图鉴展示累计钓获计数", "累计钓获 1 次" in out, out[:400])
    st = db.get_stats("g1", "w1") or {}
    check("catch_collect 统计落库", int(st.get("catch_collect", 0) or 0) == 1, str(st))

    print("【7 钓点子区域绑定】")
    spots = C.FISHING_SPOTS
    check("11 个钓点全部带 subarea 字段", len(spots) == 11 and all(
        isinstance(s, dict) and s.get("subarea") for s in spots.values()))
    bad = []
    for mid, sp in spots.items():
        sas = [sa.get("id") for sa in (C.MAP_BY_ID.get(mid, {}).get("subareas") or [])]
        if sp.get("subarea") not in sas:
            bad.append((mid, sp.get("subarea"), sas))
    check("钓点 subarea 均存在于对应地图子区域", not bad, str(bad[:3]))
    # 行为验证：不在钓点子区域 → 无钓位拦截；正确子区域放行
    db.update_player("g1", "w1", cur_map="oak_plain", cur_subarea="oak_plain_1")  # 错误子区域
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("错误子区域拦截（无钓位提示）", "没有好钓位" in out, out[:200])
    db.update_player("g1", "w1", cur_subarea="oak_plain_3")  # 溪边草地=正确钓点子区域
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("正确子区域放行垂钓", "抛出鱼竿" in out, out[:200])
    m._prof_wait_clear("g1", "w1")

    print("【8 渔获价格一致（FISH_POOL ↔ MATERIALS）】")
    for fname in ["鲛人泪", "深海水晶", "龙涎香"]:
        fp = next((f for f in C.FISH_POOL if f["name"] == fname), None)
        mp = C.MATERIALS_BY_NAME.get(fname)
        check(f"{fname} 价格一致", bool(fp) and bool(mp) and fp["price"] == mp["price"],
              f"FISH_POOL {fp and fp['price']} vs MATERIALS {mp and mp['price']}")
    mismatch = [(f["name"], f["price"], C.MATERIALS_BY_NAME[f["name"]]["price"])
                for f in C.FISH_POOL
                if f["name"] in C.MATERIALS_BY_NAME and f["price"] != C.MATERIALS_BY_NAME[f["name"]]["price"]]
    check("FISH_POOL↔MATERIALS 全量交叉价格一致", not mismatch, str(mismatch[:5]))

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
