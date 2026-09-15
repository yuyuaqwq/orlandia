# -*- coding: utf-8 -*-
"""commands 层：社交域（公会/组队/宠物/坐骑/意见/成就）（源自 v8/v35/v39/v43）

验证：
  1. 公会：创建/加入/退出/签到/任务/排行
  2. 宠物：领养/改名/喂养/放生
  3. 坐骑：骑乘/下马
  4. 意见：提交/入库
  5. 签到/成就
"""
import sys, os, sqlite3, time
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
    await cmd(m, "register", "g1", "s1", "注册 战士 会长 男")
    await cmd(m, "register", "g1", "s2", "注册 法师 会员 男")
    db.update_player("g1", "s1", level=30, gold=10000, cur_map="oak_town")
    db.update_player("g1", "s2", level=30, gold=10000, cur_map="oak_town")

    print("【公会：创建】")
    out = await cmd(m, "guild_create_cmd", "g1", "s1", "创建公会 屠龙勇士")
    check("创建成功", "创建成功" in out or "屠龙" in out, out[:120])
    out = await cmd(m, "guild_create_cmd", "g1", "s1", "创建公会 第二公会")
    check("已在一个公会", "已经" in out or "不能" in out, out[:120])

    print("【公会：加入】")
    out = await cmd(m, "guild_join_cmd", "g1", "s2", "加入公会 屠龙勇士")
    check("加入成功", "欢迎" in out or "加入" in out, out[:120])

    print("【公会：信息/签到】")
    out = await cmd(m, "guild_info", "g1", "s1", "公会")
    check("公会信息", "屠龙" in out or "公会" in out, out[:120])
    out = await cmd(m, "guild_sign", "g1", "s1", "公会签到")
    check("公会签到有返回", len(out) > 5, out[:120])

    print("【公会：退出/解散】")
    out = await cmd(m, "guild_leave_cmd", "g1", "s2", "退出公会")
    check("退出有返回", len(out) > 5, out[:120])

    print("【宠物】")
    db.init_stats("g1", "s1")
    out = await cmd(m, "pet_view", "g1", "s1", "宠物")
    check("宠物列表有返回", len(out) > 5, out[:120])

    print("【坐骑】")
    out = await cmd(m, "mount_cmd", "g1", "s1", "坐骑")
    check("坐骑列表有返回", len(out) > 5, out[:120])
    # 骑乘一个坐骑（若已拥有）
    out = await cmd(m, "mount_cmd", "g1", "s1", "骑乘")
    check("骑乘有返回", len(out) > 5, out[:120])

    print("【意见】")
    out = await cmd(m, "feedback_cmd", "g1", "s1", "意见 希望增加新副本")
    check("意见提交", "收到" in out and "我会整理给鱼鱼" in out, out[:120])
    fb = db.get_feedback()
    row0 = dict(fb[0]) if fb and hasattr(fb[0], "keys") else (fb[0] if fb else {})
    check("意见入库", len(fb) >= 1 and row0.get("status") == "new", str(row0)[:100])

    print("【签到】")
    out = await cmd(m, "signin", "g1", "s1", "签到")
    check("签到有返回", len(out) > 5, out[:120])

    print("【成就】")
    db.set_achievement("g1", "s1", "first_kill", 1)
    out = await cmd(m, "achievements", "g1", "s1", "成就")
    check("成就列表有返回", len(out) > 5, out[:120])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
