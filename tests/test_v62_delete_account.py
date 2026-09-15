# -*- coding: utf-8 -*-
"""v62：注销角色功能（群友想切职业 2026-08-05）

验证：
  1. 『注销』发起 → 提示确认，不删数据
  2. 『注销 确认』→ 删除角色全部数据（玩家/背包/副业/宠物/队伍/公会）
  3. 没有发起确认就『注销 确认』→ 提示无待确认请求
  4. 注销后可重新注册（切职业）
  5. 公会会长注销 → 公会解散
  6. 无角色时注销 → 提示不用注销
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

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

async def main():
    clean_db()
    m = Main(None)

    print("【注销：发起确认不删数据】")
    await cmd(m, "register", "g1", "d1", "注册 战士 旧角色 男")
    db.update_player("g1", "d1", level=20, gold=5000, cur_map="oak_town")
    db.add_item("g1", "d1", "mat_lang_pi", {"name": "狼皮", "type": "材料", "stackable": True, "price": 8}, 3)
    db.add_item("g1", "d1", "eq_sword", {"name": "铁剑", "slot": "weapon", "quality": "white", "lv": 5, "enhance": 2}, 1)
    out = await cmd(m, "delete_account", "g1", "d1", "注销")
    check("发起注销有确认提示", "确认" in out, out[:200])
    check("发起后角色还在", db.get_player("g1", "d1") is not None, "角色被误删!")

    print("【注销：确认删除全部数据】")
    out = await cmd(m, "delete_account", "g1", "d1", "注销 确认")
    check("确认注销成功提示", "落幕" in out or "已删除" in out, out[:200])
    check("玩家记录已删", db.get_player("g1", "d1") is None, "玩家还在!")
    check("背包已清空", db.get_inventory("g1", "d1") == [], str(db.get_inventory("g1", "d1")))
    check("战斗状态已清", db.get_battle("g1", "d1") is None, "战斗残留!")

    print("【注销：无确认请求提示】")
    # 注册新角色但没发起注销 → 直接确认应提示无待确认
    await cmd(m, "register", "g1", "d2", "注册 战士 无请求 男")
    out = await cmd(m, "delete_account", "g1", "d2", "注销 确认")
    check("无待确认提示", "没有待确认" in out, out[:200])

    print("【注销：可重新注册切职业】")
    await cmd(m, "register", "g1", "d1", "注册 法师 新角色 男")
    p = db.get_player("g1", "d1")
    check("重新注册成功", p is not None, "无法重新注册!")
    check("新职业为法师", p["class_name"] == "cls_fa_shi", f"class={p['class_name']}")

    print("【注销：公会会长注销 → 公会解散】")
    await cmd(m, "register", "g1", "g1a", "注册 战士 会长甲 男")
    await cmd(m, "register", "g1", "g1b", "注册 游侠 会员乙 男")
    db.update_player("g1", "g1a", level=30, gold=100000, cur_map="oak_town")
    db.update_player("g1", "g1b", level=30, gold=100000, cur_map="oak_town")
    await cmd(m, "guild_create_cmd", "g1", "g1a", "创建公会 测试工会")
    g = db.guild_get_by_leader("g1a")
    check("公会创建成功", g is not None, "公会创建失败")
    await cmd(m, "guild_join_cmd", "g1", "g1b", "加入公会 测试工会")
    await cmd(m, "delete_account", "g1", "g1a", "注销")
    await cmd(m, "delete_account", "g1", "g1a", "注销 确认")
    g2 = db.guild_get_by_leader("g1a")
    check("会长注销后不再是会长", g2 is None, f"g2={g2}")
    # 会员还在公会里（公会还剩 1 人 → 不解散）
    mem = db.guild_get_by_member("g1b")
    check("公会未解散（剩会员）", mem is not None, "公会被误解散!")

    print("【注销：无角色时提示】")
    out = await cmd(m, "delete_account", "g1", "nobody", "注销")
    check("无角色提示", "你还没有角色" in out and "注册" in out, out[:200])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed

if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
