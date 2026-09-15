# -*- coding: utf-8 -*-
"""v95r75 #380：道具使用修复回归测试
1. 同名材料/消耗品『麦酒』——『使用』必须命中消耗品版（材料版劫持静默失效 bug）
2. 副本战斗内材料类道具被 battle_ok 拦截（不再"假装使用"误导玩家）
3. 副本层肃清后(boss=None)使用道具走战斗外路径（不再白扣道具）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, Main, FakeEvent, run, clean_db

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

def inv(gid, qid):
    return db.get_inventory(gid, qid)

async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", cur_map="oak_plain", level=5, gold=999999)
    p0 = db.get_player("g1", "w1")
    db.update_player("g1", "w1", hp=p0["max_hp"], mp=p0["max_mp"])
    ok = fail = 0
    def check(name, cond, detail=""):
        nonlocal ok, fail
        if cond: ok += 1; print(f"  ✅ {name}")
        else: fail += 1; print(f"  ❌ {name} {detail}")

    # ---- 1. 同名材料/消耗品：『使用 麦酒』必须命中消耗品版 ----
    p = db.get_player("g1", "w1")
    db.update_player("g1", "w1", hp=int(p["max_hp"] * 0.5))
    db.add_item("g1", "w1", "mat_mai_jiu",
                {"name": "麦酒", "type": "材料", "stackable": True, "price": 15})
    db.add_item("g1", "w1", "i_ale",
                {"name": "麦酒", "type": "消耗品", "stackable": True,
                 "heal": 0.15, "mana": 0.15, "price": 10, "effect": None, "stamina": 15})
    p = db.get_player("g1", "w1")
    hp0 = p["hp"]
    out = await cmd(m, "use", "g1", "w1", "使用 麦酒")
    p = db.get_player("g1", "w1")
    check("麦酒回血(命中消耗品版)", p["hp"] > hp0, f"hp={p['hp']} vs {hp0} out={out[:100]}")
    keys = [it["key"] for it in inv("g1", "w1")]
    check("消耗品版麦酒已扣", "i_ale" not in keys, str(keys))
    check("材料版麦酒保留", "mat_mai_jiu" in keys, str(keys))

    # ---- 2. 副本战斗内材料类道具被 battle_ok 拦截 ----
    mon = {"name": "测试Boss", "hp": 99999, "max_hp": 99999, "def": 50, "mdef": 40,
           "spd": 5, "atk": 30, "matk": 30, "crit": 0.0, "dodge": 0.0,
           "is_boss": True, "is_elite": False, "skills": [], "exp": 10, "gold": 10}
    db.save_battle("g1", "w1", {"type": "instance", "round": 0, "boss": mon,
                                "members": ["w1"], "alive": {"w1": True},
                                "players": {"w1": {}}, "p_buffs": {}, "e_buffs": {},
                                "p_defending": {}, "mech_stacks": {}, "contribution": {}})
    db.add_item("g1", "w1", "mat2",
                {"name": "测试材料", "type": "材料", "stackable": True, "price": 5})
    out = await cmd(m, "use", "g1", "w1", "使用 测试材料")
    check("副本战斗内材料被拦截", "战斗中只能使用" in out, out[:120])
    keys = [it["key"] for it in inv("g1", "w1")]
    check("拦截不扣材料", "mat2" in keys, str(keys))

    # ---- 3. 副本层肃清后(boss=None)道具正常使用不白扣 ----
    db.save_battle("g1", "w1", {"type": "instance", "round": 0, "boss": None,
                                "members": ["w1"], "alive": {"w1": True},
                                "players": {"w1": {}}, "p_buffs": {}, "e_buffs": {},
                                "p_defending": {}, "mech_stacks": {}, "contribution": {}})
    p = db.get_player("g1", "w1")
    db.update_player("g1", "w1", hp=int(p["max_hp"] * 0.5))
    db.add_item("g1", "w1", "pot3",
                {"name": "治疗药水(中)", "type": "消耗品",
                 "stackable": True, "heal": 0.4, "price": 30})
    p = db.get_player("g1", "w1")
    hp0 = p["hp"]
    out = await cmd(m, "use", "g1", "w1", "使用 治疗药水(中)")
    p = db.get_player("g1", "w1")
    check("层肃清后道具回血", p["hp"] > hp0, f"hp={p['hp']} vs {hp0} out={out[:100]}")
    check("层肃清后道具已扣",
          not any(it["key"] == "pot3" for it in inv("g1", "w1")), "")
    check("层肃清后有恢复播报", "恢复" in out, out[:120])

    print(f"\n结果: {ok} 通过, {fail} 失败")
    return fail == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
