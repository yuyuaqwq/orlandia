# -*- coding: utf-8 -*-
"""v130.7 批量喂养固化测试（玩家意见 #21：『喂养 <名>*<数量>』/『喂养 <名> <数量>』）

覆盖：
  ① 『喂养 <名>*<数量>』星号格式批量（扣减 + 饱食度累计 + 汇总行）
  ② 『喂养 <名> <数量>』空格格式批量
  ③ 数量超过持有 → 显式报错『最多喂养 X 个！』且不扣物
  ④ 数量 0/负 → 显式报错『数量至少 1 个！』
  ⑤ 数量格式错（*abc）→ 提示格式（对齐 v130.4『使用』批量）
  ⑥ 饱食度满自动停：喂到 100 停，汇总『已喂食 X/Y 份（饱食度已满）』，超上限不扣物
  ⑦ 单份喂养不回归：原文案、无汇总行、亲密度/经验照常；子串/序号匹配不回归

运行：python tests/test_v1307_feed_batch.py（exit=0 全绿）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conftest import db, FakeEvent, Main, clean_db, make_player, run  # noqa: E402

passed = failed = 0
G, Q = 1095961596, "gm_t1307"
FOOD = "银鳞鱼"  # type 鱼（意见#22 白名单内）


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ {name}")
    else:
        failed += 1
        print(f"❌ {name} {detail}")


async def _cmd(m, msg):
    ev = FakeEvent(G, Q, msg)
    results = await run(m.pet_feed, ev)
    return results[-1] if results else ""


def _seal(satiety=10, count=5):
    """落库玩家 + 宠物（指定饱食度）+ 银鳞鱼×count。"""
    make_player(G, Q, "批量喂食测试", "战士", level=3)
    db.pet_create(Q, "pet_cat", "阿黄")
    db.pet_update(Q, satiety=satiety)
    db.add_item(G, Q, "m_fish", {"name": FOOD, "type": "鱼", "stackable": True, "price": 10}, count=count)


def _held():
    for it in db.get_inventory(G, Q):
        if it["data"]["name"] == FOOD:
            return it["count"]
    return 0


async def main():
    m = Main()

    # ---- ① 星号格式批量 *3：饱食度 10 → 100（3 份 +90 封顶），亲密度 0→15 ----
    clean_db()
    _seal(satiety=10, count=5)
    r = await _cmd(m, f"喂养 {FOOD}*3")
    check("① 星号批量汇总", "你喂了" in r and "已喂食 3/3 份" in r, r[:160])
    check("① 扣减 3 条", _held() == 2, f"持有={_held()}")
    p = db.pet_get(Q)
    check("① 饱食度 10→100", p["satiety"] == 100, f"satiety={p['satiety']}")
    check("① 亲密度 +15", p["bond"] == 15, f"bond={p['bond']}")

    # ---- ② 空格格式批量 2 个 ----
    clean_db()
    _seal(satiety=10, count=5)
    r = await _cmd(m, f"喂养 {FOOD} 2")
    check("② 空格格式汇总", "已喂食 2/2 份" in r, r[:160])
    check("② 扣减 2 条", _held() == 3, f"持有={_held()}")
    p = db.pet_get(Q)
    check("② 饱食度 10→70", p["satiety"] == 70, f"satiety={p['satiety']}")

    # ---- ③ 超持有显式报错不扣物 ----
    clean_db()
    _seal(satiety=10, count=2)
    r = await _cmd(m, f"喂养 {FOOD}*99")
    check("③ 超持有报错", "最多喂养 2 个" in r, r[:160])
    check("③ 不扣减", _held() == 2, f"持有={_held()}")

    # ---- ④ 0/负数量报错 ----
    clean_db()
    _seal(satiety=10, count=5)
    r = await _cmd(m, f"喂养 {FOOD}*0")
    check("④ 数量 0 报错", "数量至少 1 个" in r, r[:160])
    r = await _cmd(m, f"喂养 {FOOD} -1")
    check("④ 数量负报错", "数量至少 1 个" in r, r[:160])
    check("④ 不扣减", _held() == 5, f"持有={_held()}")

    # ---- ⑤ 格式错 ----
    clean_db()
    _seal(satiety=10, count=5)
    r = await _cmd(m, f"喂养 {FOOD}*abc")
    check("⑤ 格式错报错", "数量格式不对" in r, r[:160])

    # ---- ⑥ 饱食度满自动停 ----
    # 70 → 第 1 份到 100，剩 2 份不扣
    clean_db()
    _seal(satiety=70, count=5)
    r = await _cmd(m, f"喂养 {FOOD}*3")
    check("⑥ 满自动停汇总", "已喂食 1/3 份" in r and "饱食度已满" in r, r[:160])
    check("⑥ 只扣 1 条", _held() == 4, f"持有={_held()}")
    # 起始已满 → 1 份都不喂、不扣
    clean_db()
    _seal(satiety=100, count=3)
    r = await _cmd(m, f"喂养 {FOOD}*3")
    check("⑥ 起始满 0 份", "已喂食 0/3 份" in r and "饱食度已满" in r, r[:160])
    check("⑥ 起始满不扣", _held() == 3, f"持有={_held()}")

    # ---- ⑦ 单份喂养不回归 ----
    clean_db()
    _seal(satiety=10, count=5)
    r = await _cmd(m, f"喂养 {FOOD}")
    check("⑦ 单份原文案", "你喂了【阿黄】一份" in r and "饱食度 +30" in r, r[:160])
    check("⑦ 单份无汇总行", "已喂食" not in r, r[:160])
    check("⑦ 单份扣 1 条", _held() == 4, f"持有={_held()}")
    p = db.pet_get(Q)
    check("⑦ 单份饱食度 40", p["satiety"] == 40, f"satiety={p['satiety']}")
    # 子串/序号匹配不回归（意见#21 名字匹配诉求）
    r = await _cmd(m, "喂养 1")
    check("⑦ 序号喂养", "一份银鳞鱼" in r, r[:160])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


os_asy = __import__("asyncio")
os_asy.run(main())