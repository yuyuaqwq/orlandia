# -*- coding: utf-8 -*-
"""commands 层：9.3 品质垂钓（16 章）

验证：
  1. 地图显示垂钓点 + 特色描述
  2. 垂钓入口：无水域提示 / 高级水域等级拦截
  3. _settle_fishing 品质化：mat_ ID 入包（非 fish_ 中文动态 key）+ quality 字段
  4. 品质经验（蓝 2 点 / 紫 3 点 / 橙 5 点）
  5. 品质标记文案（✦蓝·月光鱼；白档无 ✦）
  6. 鱼王 / 宝物 / 垃圾 分支保留
"""
import sys, os, sqlite3, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run
# ★ P5E-DELETE（2026-09-15，删壳批）：猴补落点改到**包内真源模块**。
#   删壳前 `C` = 宿主聚合壳 `game.content`（普通模块对象，可写）；终态 `C` =
#   `content.facade._Aggregate`（`__slots__` 惰性句柄，**不可写**）⇒ `C.roll_fish = …` 报
#   `AttributeError: '_Aggregate' object has no attribute 'roll_fish'`。
#   口径 = 项目既有「补名会移动打桩落点 ⇒ 就地改真源那一只对象」（R5/`test_v1264` 同款）：
#   `C.roll_fish` 的 `_NAME_SRC` 真源 = `content.fishing`，包内消费方
#   （`content/profession.py::_PkgFace._MAP["roll_fish"]` → `content.fishing`）按名取它
#   ⇒ 桩打在真源模块上，取件时机与可见性逐字不变。判据一条未变。
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


def prof_exp(gid, qid):
    conn = sqlite3.connect(db.DB_PATH)
    try:
        row = conn.execute(
            "SELECT fishing_exp FROM professions WHERE qq_id=?", (qid,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def set_roll_fish(m, fish):
    """monkeypatch C.roll_fish 返回固定渔获（垂钓结算品质化单测）"""
    m.roll_fish_orig = _FISH.roll_fish
    _FISH.roll_fish = lambda lv, spot=None, bait=None: fish


def restore_roll_fish(m):
    _FISH.roll_fish = m.roll_fish_orig


def fish_dict(name, quality, ftype="鱼", price=12):
    return {"name": name, "quality": quality, "type": ftype, "price": price,
            "spots": None, "weight": 1, "desc": "测试渔获"}


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 精灵 男")
    # 激活垂钓 + 练到 Lv.5（蓝档 10%）
    await cmd(m, "fishing", "g1", "w1", "垂钓")
    db.add_prof_exp("g1", "w1", "fishing", 200)
    db.update_player("g1", "w1", level=20, gold=5000, cur_map="oak_plain", cur_subarea="oak_plain_3")  # v87.17 垂钓点=溪边草地

    print("【9.3 垂钓点显示】")
    out = await cmd(m, "map_view", "g1", "w1", "地图")
    check("橡木平原显示垂钓点·橡木溪流", "垂钓点·橡木溪流" in out, out[:300])
    check("钓点特色描述显示", "新手区，白绿为主" in out, out[:300])

    print("【9.3 垂钓入口】")
    db.update_player("g1", "w1", cur_map="dawn_city")
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("无水域提示", "这里没有水域" in out, out[:200])
    # 低级玩家（Lv.1）去高级水域 → 拦截
    await cmd(m, "register", "g1", "w2", "注册 法师 新手 男")
    await cmd(m, "fishing", "g1", "w2", "垂钓")
    db.update_player("g1", "w2", cur_map="harbor_docks", cur_subarea="harbor_docks_1")  # v87.17 垂钓点=码头栈桥
    db.update_player("g1", "w2", apprentices=["fishing"])  # v95.22 拜师模拟
    m._prof_wait_clear("g1", "w2")
    out = await cmd(m, "fishing", "g1", "w2", "垂钓")
    check("高级水域等级不足拦截（Lv.1→铁港 Lv.3）", "高级水域" in out, out[:200])
    # 铁港 min_lv 3，当前 Lv.5 → 放行（等待开始）
    db.update_player("g1", "w1", cur_map="harbor_docks", cur_subarea="harbor_docks_1")
    m._prof_wait_clear("g1", "w1")
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("铁港 Lv.5 放行开始垂钓", "抛出鱼竿" in out, out[:200])
    m._prof_wait_clear("g1", "w1")

    print("【9.3 结算·蓝·稀有】")
    exp0 = prof_exp("g1", "w1")
    set_roll_fish(m, fish_dict("月光鱼", "blue", "鱼", 55))
    out = m._settle_fishing("g1", "w1", {"spot": "铁港码头", "spot_map": "harbor_docks"})
    restore_roll_fish(m)
    check("品质标记 ✦稀有·月光鱼", "✦稀有·月光鱼" in out, out[:300])
    check("蓝档出货文案光晕", "奇异的光晕" in out, out[:300])
    conn = sqlite3.connect(db.DB_PATH)
    try:
        row = conn.execute("SELECT item_data FROM inventory WHERE qq_id='w1' AND item_key='mat_yue_guang_yu'").fetchone()
    finally:
        conn.close()
    check("月光鱼以 mat_ ID 入包", row is not None, "背包查 mat_yue_guang_yu")
    # v126.3 瘦身后存储不再含类属性——品质走配置水合（FISH_POOL quality=blue），改查水合结果
    d = {}
    for it in db.get_inventory("g1", "w1"):
        if it["key"] == "mat_yue_guang_yu":
            d = it["data"]
            break
    check("入包带 quality=blue", d.get("quality") == "blue", str(d))
    check("蓝档经验 +2", prof_exp("g1", "w1") == exp0 + 2, f"{prof_exp('g1','w1')} vs {exp0}+2")

    print("【9.3 结算·紫·史诗】")
    exp0 = prof_exp("g1", "w1")
    set_roll_fish(m, fish_dict("深海水晶", "purple", "材料", 80))
    out = m._settle_fishing("g1", "w1", {"spot": "铁港码头", "spot_map": "harbor_docks"})
    restore_roll_fish(m)
    check("品质标记 ✦史诗·深海水晶", "✦史诗·深海水晶" in out, out[:300])
    check("紫档出货文案绷紧", "鱼线猛地绷紧" in out, out[:300])
    check("紫档经验 +3", prof_exp("g1", "w1") == exp0 + 3, f"{prof_exp('g1','w1')} vs {exp0}+3")

    print("【9.3 结算·橙·传说（古代鱼骨）】")
    exp0 = prof_exp("g1", "w1")
    set_roll_fish(m, fish_dict("古代鱼骨", "orange", "材料", 200))
    out = m._settle_fishing("g1", "w1", {"spot": "铁港码头", "spot_map": "harbor_docks"})
    restore_roll_fish(m)
    check("品质标记 ✦传说·古代鱼骨", "✦传说·古代鱼骨" in out, out[:300])
    check("橙档出货文案金光", "一道金光破水而出" in out, out[:300])
    check("橙档经验 +5", prof_exp("g1", "w1") == exp0 + 5, f"{prof_exp('g1','w1')} vs {exp0}+5")
    conn = sqlite3.connect(db.DB_PATH)
    try:
        row = conn.execute("SELECT item_data FROM inventory WHERE qq_id='w1' AND item_key='mat_gu_dai_yu_gu'").fetchone()
    finally:
        conn.close()
    check("古代鱼骨以 mat_ ID 入包", row is not None, "背包查 mat_gu_dai_yu_gu")

    print("【9.3 结算·白·普通（无 ✦）】")
    exp0 = prof_exp("g1", "w1")
    set_roll_fish(m, fish_dict("银鳞鱼", "white", "鱼", 12))
    out = m._settle_fishing("g1", "w1", {"spot": "铁港码头", "spot_map": "harbor_docks"})
    restore_roll_fish(m)
    check("白档无品质前缀", "【银鳞鱼】" in out and "✦" not in out.split("银鳞鱼")[0][-10:], out[:300])
    check("白档经验 +1", prof_exp("g1", "w1") == exp0 + 1, f"{prof_exp('g1','w1')} vs {exp0}+1")

    print("【9.3 结算·鱼王 / 宝物 / 垃圾 分支保留】")
    gold0 = db.get_player("g1", "w1")["gold"]
    set_roll_fish(m, fish_dict("鱼王·翡翠巨龙", "orange", "鱼王", 500))
    out = m._settle_fishing("g1", "w1", {"spot": "铁港码头", "spot_map": "harbor_docks"})
    restore_roll_fish(m)
    check("鱼王分支（天啊+赏金）", "鱼王出水" in out and "赏金" in out, out[:300])
    check("鱼王加金币", db.get_player("g1", "w1")["gold"] > gold0, str(db.get_player("g1", "w1")["gold"]))
    set_roll_fish(m, fish_dict("陈旧的宝箱", "purple", "宝物", 0))
    out = m._settle_fishing("g1", "w1", {"spot": "铁港码头", "spot_map": "harbor_docks"})
    restore_roll_fish(m)
    check("宝物分支（打开一看）", "打开一看" in out, out[:300])
    set_roll_fish(m, fish_dict("水草", "white", "垃圾", 1))
    out = m._settle_fishing("g1", "w1", {"spot": "铁港码头", "spot_map": "harbor_docks"})
    restore_roll_fish(m)
    check("垃圾分支（唉）", "运气不太好" in out, out[:300])

    print("【9.3 旧动态 key 清理】")
    conn = sqlite3.connect(db.DB_PATH)
    try:
        old_keys = conn.execute("SELECT item_key FROM inventory WHERE item_key LIKE 'fish_%'").fetchall()
    finally:
        conn.close()
    check("背包无 fish_ 动态中文 key", not old_keys, str(old_keys[:3]))

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
