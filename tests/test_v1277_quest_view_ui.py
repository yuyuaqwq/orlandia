# -*- coding: utf-8 -*-
"""v127.7 冒险日志面板 UI 回归：任务名拆行 + 翻页上一页 + 每日"没领"引导

验证：
  1. 支线排版：任务名单独一行（名字+状态），描述缩进下一行
     （此前名字/状态/描述挤一行，长描述刷屏）
  2. 支线翻页：多支线第 1 页有『下一页』，末页有『上一页』，总页数提示
  3. 每日未领取 → 引导『每日』领取，不再误报"今日任务已完成"（v127.7 修复）
  4. 每日领取后 → 任务名拆行、进度显示
  5. 每日做完但不满上限 → 显示已完成 N 个 + 还能再接（不再笼统"已完成"）
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
    results = await run(getattr(m, handler_name), ev)
    return results[-1] if results else ""

async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", level=10, gold=1000, cur_map="oak_town", cur_subarea="oak_town_2")

    print("【1. 每日未领取 → 引导领取（v127.7 bug 修复）】")
    out = await cmd(m, "quest_view", "g1", "w1", "任务")
    check("没领每日不显示'已完成'", "今日任务已完成" not in out, out[:300])
    check("没领每日提示『每日』领取", "『每日』" in out and "领取" in out, out[:300])

    print("【2. 每日领取后 → 任务名拆行 + 进度】")
    await cmd(m, "daily", "g1", "w1", "每日")
    out = await cmd(m, "quest_view", "g1", "w1", "任务")
    seg = out[out.find("【每日】"):][:400] if "【每日】" in out else out
    check("每日任务名单独一行", "『" in seg and "\n    " in seg, seg[:200])
    check("每日进度显示( /need)", "/" in seg and ")" in seg, seg[:200])

    print("【3. 多支线拆行排版】")
    quests = db.get_quests("g1", "w1")
    side = quests.get("side") or {}
    for s in ["s1", "s2", "s3", "s4", "s5", "s6"]:
        side[s] = {"status": "active", "progress": {}}
    quests["side"] = side
    db.save_quests("g1", "w1", quests)
    out = await cmd(m, "quest_view", "g1", "w1", "任务")
    i1, i2 = out.find("【支线】"), out.find("【每日】")
    if i2 == -1:
        i2 = len(out)
    seg = out[i1:i2]
    check("支线任务名单独一行(名字行后不跟desc)", "『史莱姆果冻』[⏳]" in seg, seg[:300])
    check("支线描述缩进下一行", "   收集 5 份史莱姆黏液，给玛莎做果冻" in seg, seg[:300])
    check("支线收集进度独立行", "   收集：史莱姆黏液 0/5" in seg, seg[:300])
    check("分页提示出现(共 2 页)", "共 2 页" in seg, seg[:300])
    check("第1页有『任务 2』下一页", "『任务 2』下一页" in seg, seg[:300])

    print("【4. 翻页到末页 → 上一页提示】")
    out2 = await cmd(m, "quest_view", "g1", "w1", "任务 2")
    i1b, i2b = out2.find("【支线】"), out2.find("【每日】")
    if i2b == -1:
        i2b = len(out2)
    seg2 = out2[i1b:i2b]
    check("末页序号从 6 续号", " 6. 『" in seg2, seg2[:200])
    check("末页有『任务 1』上一页", "『任务 1』上一页" in seg2, seg2[:200])
    check("末页不再显示下一页", "『任务 3』下一页" not in seg2, seg2[:200])

    print("【5. 每日做完一部分(不满上限) → 仍有引导】")
    q2 = db.get_quests("g1", "w1")
    d = q2.get("daily") or {}
    for k in [k for k in d if k not in ("_date", "_completed", "_repeat")]:
        d.pop(k, None)
    d["_completed"] = 3  # 做完了 3 个(实际只领了2个,模拟已完成部分)
    q2["daily"] = d
    db.save_quests("g1", "w1", q2)
    out = await cmd(m, "quest_view", "g1", "w1", "任务")
    seg3 = out[out.find("【每日】"):][:200] if "【每日】" in out else out
    # v127.7: active 清空但 _completed 未满 → 提示还能再接(此前歪打误撞显示"已完成,明天再来")
    check("有完成记录未满上限提示还能再接", "还能再接" in seg3 or "已完成 3" in seg3, seg3[:200])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
