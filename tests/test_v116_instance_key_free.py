# -*- coding: utf-8 -*-
"""v116 副本已通关免钥匙 (game/commands/instance.py)

验证：
  1. 首通前无钥匙 → 被封印之门拦截（需要『军旗碎片』）
  2. 首通前有钥匙 → 开本成功，钥匙被消耗，且输出不含"免钥匙入场"
  3. 已通关（inst_clear_* 成就）→ 无钥匙也开本成功，输出提示"已通关副本，免钥匙入场"
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

# 副本测试不测体力系统，直接豁免体力扣减，防开本被体力拦截
def _fake_spend(self, gid, qid, cost, player, action="行动"):
    return True, self._stamina(player)
Main._spend_stamina = _fake_spend

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
    await cmd(m, "register", "g1", "i1", "注册 战士 队长 男")
    db.update_player("g1", "i1", level=20, gold=10000, cur_map="dawn_city", hp=500)

    print("【v116：首通前无钥匙拦截】")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 鹿角要塞")
    check("无钥匙被封印拦截", "军旗碎片" in out and "封印" in out, out[:200])
    battle = db.get_battle("g1", "i1")
    check("拦截后未开本", battle is None, "")

    print("【v116：首通前有钥匙 → 消耗且无免钥匙提示】")
    db.add_item("g1", "i1", "mat_jun_qi_sui_pian", {"name": "军旗碎片", "type": "材料", "stackable": True, "price": 100})
    # F2 入口设施化：鹿角要塞入口 = hill_mine/hill_mine_3，开本前站到入口
    db.update_player("g1", "i1", cur_map="hill_mine", cur_subarea="hill_mine_3")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 鹿角要塞")
    check("有钥匙开本成功", "副本开启" in out, out[:200])
    check("首通前无免钥匙提示", "免钥匙" not in out, out[:200])
    inv = db.get_inventory("g1", "i1")
    keys = [i for i in inv if "军旗" in (i.get("data") or {}).get("name", "")]
    check("钥匙已消耗", len(keys) == 0, str([(i.get("data") or {}).get("name") for i in inv])[:200])
    for q in ("i1",):
        m._unlock_battle("g1", q)
        db.clear_battle("g1", q)

    print("【v116：已通关免钥匙入场】")
    # 直接落首通成就模拟历史通关（真实路径：_instance_victory 结算 → db.set_achievement）
    db.set_achievement("g1", "i1", "inst_clear_inst_deer_fort", 1)
    # F2：已通关豁免位置校验，但仍在入口更稳（已在入口）
    db.update_player("g1", "i1", cur_map="hill_mine", cur_subarea="hill_mine_3")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 鹿角要塞")
    check("已通关无钥匙开本成功", "副本开启" in out, out[:200])
    check("已通关免钥匙入场提示", "已通关副本，免钥匙入场" in out, out[:200])
    battle = db.get_battle("g1", "i1")
    check("已通关开本正常", battle is not None, "")
    for q in ("i1",):
        m._unlock_battle("g1", q)
        db.clear_battle("g1", q)

    print(f"\n结果: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
