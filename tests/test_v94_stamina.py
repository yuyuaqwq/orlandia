# -*- coding: utf-8 -*-
"""v94 体力系统测试：扣减/恢复/拦截/住宿/营地/食物/自然恢复（2026-08-09）

验证：
  1. 新玩家体力 = 100/100+等级×2
  2. 探索/战斗/移动/垂钓/锻造/采集 扣减
  3. 体力不足拦截动作（探索）
  4. 体力不足移动仍允许（防卡死）
  5. 食物恢复体力（黑面包 +20）
  6. 住宿满恢复 + 费用等级挂钩
  7. 营地休息 +50
  8. 自然恢复（5 分钟 +1）
  9. 角色面板显示体力
"""
import sys, os, time, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run, make_player, new_main
from content import wild as W

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

async def cmd(m, name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, name)
    results = await run(handler, ev)
    return results[-1] if results else ""

def stamina(gid, qid):
    return db.get_player(gid, qid).get("stamina", 0)

async def main():
    random.seed(42)  # v117 测试确定性：探索/事件随机分支固定（偶发采集类事件额外扣体力导致假红）
    m = new_main()
    make_player("g1", "q1", level=1)
    # v95.15：固定非雨天，防 emerald_forest 雨天限定的『迷路的骑士』偶遇干扰探索扣体力断言
    W.today_weather = lambda map_id=None: "sunny"
    # 测试档体力 999999 —— 先手动压到正常值验证逻辑
    db.update_player("g1", "q1", stamina=100, stamina_ts=int(time.time()))

    print("【1. 面板显示体力】")
    out = await cmd(m, "profile", "g1", "q1", "角色")
    check("角色面板显示体力", "体力" in out, out[:120])

    print("【2. 探索扣 1】")
    db.update_player("g1", "q1", cur_map="emerald_forest", cur_subarea="")
    out = await cmd(m, "explore", "g1", "q1", "探索")
    st = stamina("g1", "q1")
    check(f"探索后体力 100→{st}（扣1）", st == 99, f"st={st}")
    # v95r38 测试确定性：探索可能遇怪进入战斗（POI/事件未触发时必遇怪），
    # 清掉战斗状态避免后续"跨图移动"被战斗拦截导致随机挂（凌晨跑也必过）
    db.clear_battle("g1", "q1")

    print("【3. 体力 0 拦截探索】")
    db.update_player("g1", "q1", stamina=0, stamina_ts=int(time.time()))
    out = await cmd(m, "explore", "g1", "q1", "探索")
    check("体力 0 拦截探索", "体力不足" in out, out[:80])
    check("拦截后体力不变", stamina("g1", "q1") == 0)

    print("【4. 同图移动免费 + 跨图扣 1 + 体力 0 拦截跨图】")
    db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_1", stamina=10)
    out = await cmd(m, "move", "g1", "q1", "前往 1")
    check(f"同图移动后体力仍 10（免费）", stamina("g1", "q1") == 10, f"st={stamina('g1','q1')}")
    # 跨图：橡木镇 → 橡木平原（相邻地图，需先到镇郊）
    db.update_player("g1", "q1", cur_subarea="oak_town_outskirts", stamina=10)
    out = await cmd(m, "move", "g1", "q1", "前往 橡木平原")
    check(f"跨图移动后体力 10→9", stamina("g1", "q1") == 9, f"st={stamina('g1','q1')} out={out[:60]}")
    # v95r38 测试确定性：跨图移动可能触发撞怪战斗（_travel_ambush），清掉再测体力拦截
    db.clear_battle("g1", "q1")
    db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_outskirts", stamina=0, stamina_ts=int(time.time()))
    out = await cmd(m, "move", "g1", "q1", "前往 橡木平原")
    check("体力 0 拦截跨图移动", "走不动" in out, out[:80])
    check("拦截后体力不变", stamina("g1", "q1") == 0)

    print("【5. 食物恢复体力】")
    db.clear_battle("g1", "q1")  # 跨图移动可能触发野外战斗，先清掉
    db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_1", stamina=10)
    db.add_item("g1", "q1", "i_bread", {"name": "黑面包", "type": "消耗品", "stackable": True, "heal": 0.3, "stamina": 20, "price": 5})
    out = await cmd(m, "use", "g1", "q1", "使用 黑面包")
    check("吃黑面包恢复体力", "体力" in out and "恢复" in out, out[:100])
    check(f"体力 10+20=30", stamina("g1", "q1") == 30, f"st={stamina('g1','q1')}")

    print("【6. 住宿满恢复 + 费用】")
    db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_4", gold=1000, stamina=5)
    out = await cmd(m, "rest", "g1", "q1", "住宿")
    check("住宿恢复体力满", "体力" in out, out[:100])
    check("住宿体力=上限", stamina("g1", "q1") == 100 + 1 * 2, f"st={stamina('g1','q1')}")

    print("【7. 营地休息 +50】")
    db.update_player("g1", "q1", cur_map="rockfall_gorge", cur_subarea="", stamina=10)
    out = await cmd(m, "rest_camp", "g1", "q1", "休息")
    check("营地恢复体力", "体力" in out, out[:100])

    print("【8. 自然恢复（1分钟+1）】")
    db.update_player("g1", "q1", stamina=50, stamina_ts=int(time.time()) - 3600)  # 1小时前
    p = db.get_player("g1", "q1")
    # v166 恢复间隔 300s→60s：1 小时 = 60 点 → 50+60=110 封顶 102
    check("自然恢复 1小时封顶 102（原5分钟档50+12=62 已改）", p["stamina"] == 102, f"st={p['stamina']}")
    db.update_player("g1", "q1", stamina=100, stamina_ts=int(time.time()) - 99999)
    p = db.get_player("g1", "q1")
    check("自然恢复封顶上限", p["stamina"] == 102, f"st={p['stamina']}")

    print("【9. 上限随等级】")
    db.update_player("g1", "q1", level=10, stamina=100, stamina_ts=int(time.time()))
    p = db.get_player("g1", "q1")
    check("Lv.10 上限 120", m._stamina_max(p) == 120)

    print("【10. 战斗每回合扣 1（攻击/技能），防御/逃跑不扣，体力 0 拦截】")
    def _mk_mon(is_boss=False, is_elite=False):
        return {"name": "测试怪", "hp": 999999, "max_hp": 999999, "def": 50, "mdef": 40,
                "spd": 5, "atk": 30, "matk": 30, "crit": 0.0, "dodge": 0.0,
                "is_boss": is_boss, "is_elite": is_elite, "skills": [], "exp": 10, "gold": 10,
                "uid": "e_stam", "level": 5, "lv": 5, "rank": 1, "reach": 1}
    # N5b4-6：普通战斗 state 已 saintess_engine sides-only——命令层（attack/skill/use）恢复
    # 只认 saintess_engine；旧格式（无 sides）按约定清档重开。直接存 saintess_engine to_state。
    def _mk_battle():
        from content import bridge as _BR
        from saintess_engine import Battle as _B2
        pl = db.get_player("g1", "q1")
        _BR.prepare_player_for_battle(pl, {}, db)
        _sides = _BR.build_sides(player=pl, enemies=[_mk_mon()])
        for _a in _sides.get("player", []):
            _a["bonus"] = {"panel": {}, "cap": {}, "cost": {}}
        return _B2("monster", sides=_sides, title_bonus={}).to_state()
    # 攻击扣 1
    db.clear_battle("g1", "q1")
    db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_1", stamina=30, stamina_ts=int(time.time()))
    db.save_battle("g1", "q1", _mk_battle())
    out = await cmd(m, "attack", "g1", "q1", "攻击")
    check(f"攻击后体力 30→29（扣1）", stamina("g1", "q1") == 29, f"st={stamina('g1','q1')} out={out[:60]}")
    # 同场战斗第二击继续扣（每回合都扣）
    out = await cmd(m, "attack", "g1", "q1", "攻击")
    check("第二击再扣 1（29→28）", stamina("g1", "q1") == 28, f"st={stamina('g1','q1')}")
    # 防御不扣
    db.update_player("g1", "q1", stamina=28, stamina_ts=int(time.time()))
    out = await cmd(m, "defend", "g1", "q1", "防御")
    check("防御不扣体力", stamina("g1", "q1") == 28, f"st={stamina('g1','q1')} out={out[:60]}")
    # 技能扣 1（战士基础技能：挥砍，需学习+进技能栏）
    db.update_player("g1", "q1", mp=100, stamina=28, stamina_ts=int(time.time()),
                     learned_skills=["挥砍"])
    db.set_skill_bar("g1", ["挥砍", None, None, None, None, None])
    db.save_battle("g1", "q1", _mk_battle())
    out = await cmd(m, "skill", "g1", "q1", "技能 挥砍")
    check("技能后体力 28→27（扣1）", stamina("g1", "q1") == 27, f"st={stamina('g1','q1')} out={out[:60]}")
    # 体力 0 拦截攻击
    db.clear_battle("g1", "q1")
    db.update_player("g1", "q1", stamina=0, stamina_ts=int(time.time()))
    db.save_battle("g1", "q1", _mk_battle())
    out = await cmd(m, "attack", "g1", "q1", "攻击")
    check("体力 0 拦截攻击", "体力不足" in out and "逃跑" in out, out[:100])
    # 体力 0 时防御/逃跑仍可用（防卡死）
    out = await cmd(m, "flee", "g1", "q1", "逃跑")
    check("体力 0 仍可逃跑", len(out) > 5 and "体力不足" not in out, out[:80])
    db.clear_battle("g1", "q1")

    print(f"\n结果: 通过 {passed}，失败 {failed}")

import asyncio
asyncio.run(main())
if failed:
    raise SystemExit(1)
