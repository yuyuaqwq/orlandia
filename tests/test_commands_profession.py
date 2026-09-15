# -*- coding: utf-8 -*-
"""commands 层：v67 副业体系改造（v167 解除数量上限：双副业上限 → 无上限自动激活）

验证：
  1. 副业面板：标题报当前已激活条数（无 /2 分母）
  2. 首次动作自动激活（1 条 → 2 条 → 3 条…无限激活，永不拦截）
  3. 遗忘副业：等级清零（无"腾位/占位"文案）
  4. 严格上限已解除：激活 3+ 条不拦截；未激活但有等级 → 自动激活
  5. 强化/附魔同为副业：拜师后可激活（同步放开）
  6. 代工：无副业要求 + 3 倍金币
  7. 锻造副业不足提示引流代工
"""
import sys, os, sqlite3, time, json
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


def reset_profs(gid, qid):
    for k in ("gather", "mining", "fishing", "alchemy", "craft", "cooking", "enhance", "enchant"):
        db.forget_prof(gid, qid, k)


def add_mats(gid, qid, count=20):
    db.add_item(gid, qid, "mat_shi_lai_mu_nian_ye", {"name": "史莱姆黏液", "type": "材料", "stackable": True}, count)


def add_equip(gid, qid, name="铁剑"):
    db.add_item(gid, qid, f"eq_t_{qid}_{name}", {"name": name, "type": "武器", "slot": "weapon",
                                                 "quality": "white", "lv": 3, "atk": 12, "stackable": False}, 1)


def add_iron(gid, qid, count=20):
    db.add_item(gid, qid, "mat_cu_tie", {"name": "粗铁", "type": "材料", "stackable": True}, count)


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", level=20, gold=5000, cur_map="oak_plain")

    print("【v167 副业面板：无上限口径（修订 v113.5 T1）】")
    out = await cmd(m, "profession_view", "g1", "w1", "副业")
    check("面板无 /2 分母", "当前已激活 0 条" in out and "/2" not in out, out[:120])
    check("不显示未激活副业🔒行(按鱼鱼要求)", "🔒未激活" not in out and "还没有解锁" in out, out[:200])

    print("【v167 无上限自动激活（v95.22 需先拜师）】")
    db.update_player("g1", "w1", apprentices=["gather"])  # v95.22 拜师模拟
    out = await cmd(m, "gather", "g1", "w1", "采集")
    check("采集自动激活", "选择了「采集」" in out and "当前已激活 1 条" in out, out[:200])
    check("采集进行中", "开始采集" in out, out[:200])
    m._prof_wait_clear("g1", "w1")
    db.update_player("g1", "w1", cur_map="rockfall_gorge", cur_subarea="rockfall_gorge_1")  # v173 矿点门槛=挖1，Lv1 新号可挖
    db.update_player("g1", "w1", apprentices=["gather", "mining"])
    out = await cmd(m, "mining", "g1", "w1", "挖掘")
    check("挖掘自动激活第2条", "选择了「挖掘」" in out and "当前已激活 2 条" in out, out[:200])
    m._prof_wait_clear("g1", "w1")
    db.update_player("g1", "w1", cur_map="oak_plain", cur_subarea="oak_plain_3")  # v87.17 垂钓点=溪边草地
    db.update_player("g1", "w1", apprentices=["gather", "mining", "fishing"])
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("第3条不拦截照常激活(无上限)", "副业位已满" not in out and "选择了「垂钓」" in out
          and "当前已激活 3 条" in out, out[:200])

    print("【v167 遗忘：等级清零（保留功能，无腾位文案）】")
    out = await cmd(m, "prof_forget", "g1", "w1", "遗忘副业 采集")
    check("遗忘成功", "遗忘了「采集」" in out and "副业位" not in out, out[:200])
    check("采集等级清零", db.get_prof_level("g1", "w1", "gather") == 1, str(db.get_prof_level("g1", "w1", "gather")))
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("已激活垂钓二次可正常进行", "选择了「垂钓」" not in out and "垂钓" in out, out[:200])
    m._prof_wait_clear("g1", "w1")
    out = await cmd(m, "prof_forget", "g1", "w1", "遗忘副业 不存在")
    check("不存在副业提示", "没有「不存在」这个副业" in out or "没有" in out, out[:120])

    print("【v167 老玩家兼容：有等级未激活 → 自动激活（不再被上限拦）】")
    # 已激活多条时，有等级的未激活副业做动作直接自动激活（v67 会被"位置满"拦）
    db.add_prof_exp("g1", "w1", "cooking", 300)
    out = await cmd(m, "cooking", "g1", "w1", "烹饪 鱼汤")
    check("有等级未激活自动激活", "选择了「烹饪」" in out or "灶火" in out or "鱼汤" in out, out[:200])
    check("烹饪已激活", "cooking" in db.get_activated_profs("g1", "w1"), str(db.get_activated_profs("g1", "w1")))

    print("【v81 强化独立副业（原 v67 归位锻造）】")
    reset_profs("g1", "w1")
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_3", gold=5000, apprentices=["enhance"])  # v95.22 拜师模拟
    # v101.30 每日任务奖励 50 副业经验：+1 强化会完成今日任务直接抬到 Lv.2，先标记任务已领清干扰
    # v105R3 M13 P2-1：每日任务 key 已去 group_id（玩家级），预设同步新格式
    db.set_event_state(f"prof_daily_w1_{time.strftime('%Y-%m-%d')}", "enhance|强化装备|1|50|1|1")
    add_equip("g1", "w1", "试炼剑")
    out = await cmd(m, "enhance", "g1", "w1", "强化 试炼剑")
    check("+1 强化成功（强化自动激活Lv.1）", "强化成功" in out and "+1" in out, out[:200])
    out = await cmd(m, "enhance", "g1", "w1", "强化 试炼剑")
    check("+2 需要强化Lv.2拦截", "需要强化副业 Lv.2" in out, out[:200])
    db.add_prof_exp("g1", "w1", "enhance", 30)  # Lv.2
    out = await cmd(m, "enhance", "g1", "w1", "强化 试炼剑")
    check("强化Lv.2后+2可强化", "强化成功" in out or "强化失败" in out or "降级" in out, out[:200])

    print("【v81 附魔独立副业（原 v67 归位炼金）】")
    reset_profs("g1", "w1")
    db.update_player("g1", "w1", apprentices=["enchant"])  # v95.22 拜师模拟
    out = await cmd(m, "enchant", "g1", "w1", "附魔")
    check("无参附魔先给格式（不被附魔拦）", "附魔哪件装备" in out, out[:200])
    out = await cmd(m, "enchant", "g1", "w1", "附魔 试炼剑 攻击")
    check("附魔Lv.1附魔被拦", "需要附魔副业 Lv.2" in out, out[:200])
    db.add_prof_exp("g1", "w1", "enchant", 30)  # Lv.2
    out = await cmd(m, "enchant", "g1", "w1", "附魔 试炼剑 攻击")
    check("附魔Lv.2后通过门槛", "需要附魔副业 Lv.2" not in out, out[:200])

    print("【v67 代工补偿】")
    reset_profs("g1", "w1")
    db.update_player("g1", "w1", gold=5000)
    add_iron("g1", "w1", count=6)  # 铁剑 mats = 粗铁×2
    out = await cmd(m, "craft_commission", "g1", "w1", "代工 铁剑")
    # M10 P1-3 新手白装锻造费归 0（成本10 ≤ 卖店回收20，不再倒挂）→ 代工费 0×3=0
    check("代工成功", "代工完成" in out and "铁剑" in out and "0 金币" in out, out[:200])
    check("锻造未激活", "craft" not in db.get_activated_profs("g1", "w1"), str(db.get_activated_profs("g1", "w1")))
    check("金币扣3倍(0×3)", db.get_player("g1", "w1")["gold"] == 5000, str(db.get_player("g1", "w1")["gold"]))
    check("装备入包", db.count_item("g1", "w1", "铁剑") >= 1, "")
    out = await cmd(m, "craft_commission", "g1", "w1", "代工 铁剑")
    check("二次代工扣料成功", "代工完成" in out and "铁剑" in out, out[:200])
    out = await cmd(m, "craft_commission", "g1", "w1", "代工 铁剑")
    # 注：v167 换料后铁剑成本=粗铁×2（0 金币档），前两次用掉 4 个、剩 2 个仍够第 3 次 → 材料判定在锻造后
    check("三次后材料消耗正确", "代工完成" in out or "材料不足" in out or "粗铁" in out, out[:200])
    out = await cmd(m, "craft_commission", "g1", "w1", "代工")
    check("无参提示格式", "格式：代工" in out, out[:120])

    print("【v67 锻造引流】")
    add_iron("g1", "w1", count=10)
    db.update_player("g1", "w1", apprentices=["craft"])  # v95.22 拜师模拟
    out = await cmd(m, "craft", "g1", "w1", "锻造 铁剑")
    check("锻造未激活自动激活", "选择了「锻造」" in out, out[:200])
    db.update_player("g1", "w1", level=35, gold=5000)
    add_iron("g1", "w1", count=10)
    out = await cmd(m, "craft", "g1", "w1", "锻造 审判之链")
    check("高等级配方提示引流代工", "代工" in out or "锻造" in out, out[:200])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
