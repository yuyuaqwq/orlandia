# -*- coding: utf-8 -*-
"""阶段九.2：成就系统（14 章 97 成就）

验证：
  1. 数据完整性：97 成就 / 6 分类 / 条件字段齐全
  2. check_achievements 触发：注册解锁、战斗胜利解锁（击杀/等级）、副业计数、visited、学习、转职
  3. 奖励发放（经验）
  4. 称号系统：成就称号合并、『称号 装备』、profile 显示
  5. 成就命令：总览/分类
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import FakeEvent, run, clean_db, make_player, TEST_DB, PLUGIN_DIR
from _engine_harness import C, db
from _engine_harness import Main

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}: {detail}")


async def cmd(m, name, gid, qid, msg):
    handler = getattr(m, name)
    ev = FakeEvent(gid, qid, msg)
    return await run(handler, ev)


# ============ 1. 数据完整性 ============
def test_data():
    print("【1. 数据完整性】")
    # v151：成就表 119 条（v140 波2 资源向成就并入后仍 119——v151 未新增成就，隐藏分类 19 条）
    check("119 成就（v151 存量）", len(C.ACHIEVEMENTS) == 119, str(len(C.ACHIEVEMENTS)))
    from collections import Counter
    cats = Counter(a["cat"] for a in C.ACHIEVEMENTS)
    check("分类计数", cats == {"战斗": 23, "成长": 15, "探索": 22, "副业": 29, "社交": 11, "隐藏": 19}, str(dict(cats)))
    ids = [a["id"] for a in C.ACHIEVEMENTS]
    check("id 唯一", len(ids) == len(set(ids)))
    bad = [a["id"] for a in C.ACHIEVEMENTS if not a.get("cond") or not a["cond"].get("type")]
    check("条件齐全", not bad, str(bad[:5]))
    bad_title = [a["id"] for a in C.ACHIEVEMENTS if not a.get("title")]
    check("称号齐全", not bad_title, str(bad_title[:5]))


# ============ 2. 触发解锁 ============
async def test_unlock():
    print("【2. 触发解锁】")
    m = Main(None)
    clean_db()
    # 注册 → 冒险者起步
    await cmd(m, "register", "g1", "q1", "注册 战士 阿铁 男")
    rows = db.get_achievements("g1", "q1")
    unlocked = {r["ach_key"] for r in rows}
    check("注册解锁初出茅庐", "ach_register" in unlocked, str(unlocked))
    # 战斗胜利 → 击杀计数成就
    p = db.get_player("g1", "q1")
    db.bump_stats("g1", "q1", kills=10)
    new = C.check_achievements("g1", "q1", p)
    names = [a["name"] for a in new]
    check("击杀10解锁新手猎人", any("新手猎人" in n for n in names), str(names))
    # 等级 → 等级成就
    db.update_player("g1", "q1", level=10)
    new2 = C.check_achievements("g1", "q1", db.get_player("g1", "q1"))
    names2 = [a["name"] for a in new2]
    check("10级解锁崭露头角", any("崭露头角" in n for n in names2), str(names2))
    # 副业次数 → 垂钓新手
    db.bump_stats("g1", "q1", fish_count=10)
    new3 = C.check_achievements("g1", "q1", db.get_player("g1", "q1"))
    names3 = [a["name"] for a in new3]
    check("垂钓10次解锁", any("垂钓新手" in n for n in names3), str(names3))
    # v101.22 奖励待领取：解锁不再自动发经验，claimed=0；『成就 领取』才发
    await cmd(m, "register", "g1", "q2", "注册 法师 阿水 男")
    db.bump_stats("g1", "q2", kills=1)
    new4 = C.check_achievements("g1", "q2", db.get_player("g1", "q2"))
    p3 = db.get_player("g1", "q2")
    check("首次战斗奖励待领取(不自动发)", any("初试锋芒" in a["name"] for a in new4) and p3["exp"] == 0, f"exp={p3['exp']}")
    ach_row = [r for r in db.get_achievements("g1", "q2") if r["ach_key"] == "ach_first_fight"]
    check("首次战斗成就 claimed=0 待领取", ach_row and ach_row[0]["claimed"] == 0, str(ach_row))
    # 『成就 领取』发放奖励
    r_claim = await cmd(m, "achievements", "g1", "q2", "成就 领取")
    txt_claim = r_claim[-1]
    p4 = db.get_player("g1", "q2")
    check("领取后经验到账", p4["exp"] >= 100, f"exp={p4['exp']}")
    check("领取提示含奖励", "经验 +100" in txt_claim, txt_claim[:80])
    ach_row2 = [r for r in db.get_achievements("g1", "q2") if r["ach_key"] == "ach_first_fight"]
    check("领取后 claimed=1", ach_row2 and ach_row2[0]["claimed"] == 1, str(ach_row2))
    # 重复领取幂等
    r_claim2 = await cmd(m, "achievements", "g1", "q2", "成就 领取")
    check("重复领取提示无奖励", "没有待领取" in r_claim2[-1], r_claim2[-1][:80])
    # 重复检查幂等
    new5 = C.check_achievements("g1", "q2", db.get_player("g1", "q2"))
    check("重复检查不重复解锁", not any(a["name"] == "初试锋芒" for a in new5), str([a["name"] for a in new5]))


# ============ 3. 称号系统 ============
async def test_titles():
    print("【3. 称号系统】")
    m = Main(None)
    clean_db()
    await cmd(m, "register", "g1", "q1", "注册 战士 阿铁 男")
    # 解锁一个成就称号（新手猎人）
    db.bump_stats("g1", "q1", kills=10)
    C.check_achievements("g1", "q1", db.get_player("g1", "q1"))
    r = await cmd(m, "titles", "g1", "q1", "称号")
    txt = r[-1]
    check("称号列表含成就称号", "新手猎人" in txt, txt[:120])
    # 装备称号
    r2 = await cmd(m, "titles", "g1", "q1", "称号 装备 新手猎人")
    txt2 = r2[-1]
    check("装备称号成功", "新手猎人" in txt2, txt2[:80])
    p = db.get_player("g1", "q1")
    check("equipped_title 存库", p.get("equipped_title") == "新手猎人", str(p.get("equipped_title")))
    # profile 显示
    r3 = await cmd(m, "profile", "g1", "q1", "角色")
    txt3 = r3[-1]
    check("profile 显示称号", "[新手猎人]" in txt3, txt3[:80])
    # 卸下
    r4 = await cmd(m, "titles", "g1", "q1", "称号 卸下")
    check("卸下称号", "卸下" in r4[-1])
    # 未获得称号装备拦截
    r5 = await cmd(m, "titles", "g1", "q1", "称号 装备 屠龙者")
    check("未获得拦截", "还没获得" in r5[-1], r5[-1][:80])


# ============ 4. 成就命令 ============
async def test_ach_cmd():
    print("【4. 成就命令】")
    m = Main(None)
    clean_db()
    await cmd(m, "register", "g1", "q1", "注册 战士 阿铁 男")
    r = await cmd(m, "achievements", "g1", "q1", "成就")
    txt = r[-1]
    check("成就总览显示进度", "总进度" in txt and "成就点" in txt, txt[:120])
    check("成就总览含分类", "战斗" in txt and "副业" in txt)
    r2 = await cmd(m, "achievements", "g1", "q1", "成就 战斗")
    txt2 = r2[-1]
    check("分类明细", "成就·战斗" in txt2 and "初试锋芒" in txt2, txt2[:100])
    # 成就点：初出茅庐 1 点
    pts = C.achievement_points("q1")
    check("成就点计算", pts >= 1, str(pts))


async def main():
    test_data()
    await test_unlock()
    await test_titles()
    await test_ach_cmd()
    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
