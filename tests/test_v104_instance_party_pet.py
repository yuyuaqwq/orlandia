# -*- coding: utf-8 -*-
"""v104 修复回归：副本 / 组队 / 宠物（10 项）

覆盖（对应 v104 审计 P1/M04/M05/M17 修复项）：
  1. 退队白拿收益修复：2 人开本→队员退队→队长通关→退队者无金币/经验/材料/首通成就
  2. 退队者不被 Boss 打：战斗中队员退队→Boss 回合只打当前队伍成员
  3. 全灭不误杀退队者：全灭→退队者满血留原地（不受失败回城牵连）
  4. retreated 恢复校验：撤退后队员退队→恢复被拒（按当前队伍重校验人数/等级）
  5. 组队面板：『队伍』→显示成员等级/职业（v104 M04 P2）
  6. 免空格组队：『组队甲』可拉人（正则修复生效）
  7. 超时文案统一：超时阈值 60 秒 + 开本模板无 120 秒/2 分钟残留（v104 批次3）
  8. 副本宠物：v104 M17 P2 设计取舍——副本不携带宠物（饱食度不扣，现状标注）
  9. 宠物饱食度面板：饱食度 0→面板显示减半加成
 10. 宠物蛋定价：make_pet_egg 按品质定价（传说 500 > 白蛋 100）
"""
import sys, os, time, re

# ⚠️ v137 副本彻底重构（副本地图化）：本测试基于旧副本结构（st["boss"]/st["turn"]/分层推进/旧 POI id），
# 已不适用于 v137（副本=多房间地图，怪物在 rooms 池，战斗在 enemies 阵列，推进靠移动）。
# 核心玩法验收由 tests/test_v137_dungeon.py 覆盖。保留本文件供历史参考，跳过执行。
print("⏭️ test_v104_instance_party_pet.py: v137 重构后旧结构测试已跳过（见 test_v137_dungeon.py）")
import sys as _sys
_sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run  # noqa: E402

# v94 体力：副本测试豁免体力扣减，防开本被体力拦截。
def _fake_spend(self, gid, qid, cost, player, action="行动"):
    return True, self._stamina(player)
Main._spend_stamina = _fake_spend

passed = failed = 0
findings = []
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

def finding(name, detail):
    """记录真实发现（不失败，报告用）。"""
    findings.append((name, detail))
    print(f"  ⚠️ 发现: {name} {detail}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def enter_combat(m, gid, qid):
    """副本地图模式『探索』触发第一场战斗（重试防随机无事/陷阱）。"""
    for _ in range(5):
        out = await cmd(m, "explore", gid, qid, "探索")
        if db.get_battle(gid, qid):
            return out
    return out

def reset_battle(m, gid, qid):
    """清战斗状态 + 解锁（测试间隔离）。"""
    try:
        m._unlock_battle(gid, qid)
    except Exception:
        pass
    db.clear_battle(gid, qid)

def heal(gid, qid):
    p = db.get_player(gid, qid)
    if p:
        db.update_player(gid, qid, hp=p.get("max_hp", 9999), mp=p.get("max_mp", 999))

INST = "inst_old_king_tomb"

async def setup(m, with_third=False):
    """注册 3 角色（队长/队员/甲），拉等级，队长备钥匙。"""
    await cmd(m, "register", "g1", "i1", "注册 战士 队长 男")
    await cmd(m, "register", "g1", "i2", "注册 法师 队员 男")
    await cmd(m, "register", "g1", "i3", "注册 游侠 甲 男")
    for q in ("i1", "i2", "i3"):
        db.update_player("g1", q, level=40, gold=10000, cur_map="dawn_city")
        heal("g1", q)
    for _ in range(10):
        db.add_item("g1", "i1", "i_key_old_king", {"name": "王陵钥匙", "type": "钥匙", "stackable": True, "price": 500})

async def open_instance(m, gid="g1", leader="i1"):
    """组队+开本+探索进入第一场战斗。返回战斗 state。"""
    out = await cmd(m, "instance_cmd", gid, leader, f"副本 旧王陵")
    check("开本成功(地图模式)", "副本开启" in out, out[:120])
    await enter_combat(m, gid, leader)
    battle = db.get_battle(gid, leader)
    check("进入战斗", battle is not None and battle["state"].get("boss"), "")
    return battle["state"]

def jump_to_final_boss(st):
    """把战斗状态拨到最后一层 Boss（hp=1 可一击通关）。"""
    inst = C.INSTANCES[INST]
    boss = C.build_monster(inst["boss"], {"id": INST, "name": inst["name"], "area": "instance"})
    boss["hp"] = 1
    boss["atk"] = 5
    boss["matk"] = 5
    st["stage_idx"] = len(st["inst_stages"]) - 1
    st["stage_cleared"] = True
    st["stage_pending"] = []
    st["mode"] = "battle"
    st["boss"] = boss
    st["enemy"] = boss
    st["enemies"] = [dict(boss)]  # v2：敌方阵列（boss/enemy 为兼容键）
    st["alive"] = {str(m): True for m in st["members"]}
    st["turn"] = st["members"].index("i1")
    st["turn_time"] = int(time.time())
    st["acted"] = [False] * len(st["members"])
    return st

async def main():
    clean_db()
    m = Main(None)
    await setup(m)

    # ============ 6. 免空格组队（先做：不占 2 人队名额） ============
    print("【6. 免空格组队】")
    out = await cmd(m, "party", "g1", "i1", "组队甲")
    check("『组队甲』无空格拉人成功", "组队成功" in out or "成为队友" in out, out[:150])
    check("队伍 2 人", len(db.party_members("g1", "i1")) == 2, str(db.party_members("g1", "i1")))
    await cmd(m, "party_leave", "g1", "i3", "退队")

    # ============ 5. 组队面板 ============
    print("【5. 组队面板】")
    await cmd(m, "party", "g1", "i1", "组队 队员")
    out = await cmd(m, "party", "g1", "i1", "队伍")
    check("面板显示等级", "Lv.40" in out, out[:200])
    check("面板显示职业", "战士" in out and "法师" in out, out[:200])
    check("面板标队长", "队长" in out, out[:200])

    # ============ 1. 退队白拿收益修复 ============
    print("【1. 退队白拿收益修复】")
    st = await open_instance(m)
    g2_before = db.get_player("g1", "i2")["gold"]
    e2_before = db.get_player("g1", "i2")["exp"]
    inv2_before = {(it["key"], it.get("count", 1)) for it in (db.get_inventory("g1", "i2") or [])}
    ach2_before = {a.get("ach_key") for a in (db.get_achievements("g1", "i2") or [])}
    out = await cmd(m, "party_leave", "g1", "i2", "退队")
    check("队员退队成功", "退出队伍" in out, out[:120])
    st = jump_to_final_boss(st)
    db.save_battle("g1", "i1", st)
    out = await cmd(m, "attack", "g1", "i1", "攻击")
    check("队长通关", "通关" in out or "击败" in out, out[:300])
    p2 = db.get_player("g1", "i2")
    check("退队者金币不变", p2["gold"] == g2_before, f"{p2['gold']} vs {g2_before}")
    check("退队者经验不变", p2["exp"] == e2_before, f"{p2['exp']} vs {e2_before}")
    inv2_after = {(it["key"], it.get("count", 1)) for it in (db.get_inventory("g1", "i2") or [])}
    check("退队者无材料入包", inv2_after == inv2_before, f"{inv2_before} → {inv2_after}")
    ach2 = {a.get("ach_key") for a in (db.get_achievements("g1", "i2") or [])}
    check("退队者无首通成就", "inst_clear_inst_old_king_tomb" not in ach2 - ach2_before, str(ach2))
    p1 = db.get_player("g1", "i1")
    check("队长正常获得金币", p1["gold"] > 10000, str(p1["gold"]))
    ach1 = {a.get("ach_key") for a in (db.get_achievements("g1", "i1") or [])}
    check("队长获得首通成就(对照)", "inst_clear_inst_old_king_tomb" in ach1, str(ach1))
    out = await cmd(m, "instance_leave", "g1", "i1", "离开副本")
    reset_battle(m, "g1", "i1")

    # ============ 2. 退队者不被 Boss 打 ============
    print("【2. 退队者不被 Boss 打】")
    await cmd(m, "party", "g1", "i1", "组队 队员")
    heal("g1", "i1")
    st = await open_instance(m)
    await cmd(m, "party_leave", "g1", "i2", "退队")
    # Boss 高攻高威胁指向 i2（若 Bug 会打退队者）；两人都预行动 → 行动后触发 Boss 回合
    st["boss"]["hp"] = 50000
    st["boss"]["atk"] = 500
    st["boss"]["matk"] = 500
    st["boss"]["spd"] = 1
    st["threat"] = {"i1": 1, "i2": 999999}
    st["turn"] = st["members"].index("i1")
    st["acted"] = [True] * len(st["members"])
    st["turn_time"] = int(time.time())
    hp_i2_before = st["players"]["i2"]["hp"]
    db.save_battle("g1", "i1", st)
    # v132.1 稳定化：副本入口战斗可能为小怪层（attack 实际打骷髅兵），Boss 回合按 CTB 时序随机，
    # "Boss 必命中当前成员"断言 v131 已知 flake（990→990 / 附近没有敌人）→ 断言收敛为退队者不被打
    out = await cmd(m, "attack", "g1", "i1", "攻击")
    _b = db.get_battle("g1", "i1")
    st2 = _b["state"] if _b else st
    check("退队者血量未被打", st2["players"]["i2"]["hp"] == hp_i2_before,
          f"{st2['players']['i2']['hp']} vs {hp_i2_before}")
    check("退队者存活标记未动", st2["alive"].get("i2", True) is True, str(st2["alive"]))
    reset_battle(m, "g1", "i1")
    heal("g1", "i1")

    # ============ 3. 全灭不误杀退队者 ============
    print("【3. 全灭不误杀退队者】")
    await cmd(m, "party", "g1", "i1", "组队 队员")
    st = await open_instance(m)
    await cmd(m, "party_leave", "g1", "i2", "退队")
    hp_i2_db = db.get_player("g1", "i2")["hp"]
    mp_i2_db = db.get_player("g1", "i2")["mp"]
    map_i2 = db.get_player("g1", "i2")["cur_map"]
    st["alive"] = {"i1": False, "i2": True}  # 队长已死 + 队员退队 → 无行动者
    st["boss"]["hp"] = 50000
    st["turn"] = st["members"].index("i1")
    st["turn_time"] = int(time.time())
    db.save_battle("g1", "i1", st)
    out = await cmd(m, "attack", "g1", "i1", "攻击")
    check("全灭失败结算", "全灭" in out, out[:200])
    p1 = db.get_player("g1", "i1")
    p2 = db.get_player("g1", "i2")
    # O104：失败回城点=副本入口最近城镇（开本前 cur_map=dawn_city → 回 dawn_city）
    check("队长回城 0 血", p1["hp"] == 0 and p1["cur_map"] == "dawn_city", f"hp={p1['hp']} map={p1['cur_map']}")
    check("退队者满血留原地", p2["hp"] == hp_i2_db and p2["cur_map"] == map_i2,
          f"hp {p2['hp']} vs {hp_i2_db}, map {p2['cur_map']} vs {map_i2}")
    check("退队者魔力未动", p2["mp"] == mp_i2_db, f"{p2['mp']} vs {mp_i2_db}")
    check("队长战斗已清", db.get_battle("g1", "i1") is None, "")
    heal("g1", "i1")

    # ============ 4. retreated 恢复校验 ============
    print("【4. retreated 恢复校验】")
    await cmd(m, "party", "g1", "i1", "组队 队员")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    check("开本成功", "副本开启" in out, out[:120])
    out = await cmd(m, "instance_retreat", "g1", "i1", "撤退")
    check("地图模式撤退成功", "进度已保留" in out, out[:150])
    st = db.get_battle("g1", "i1")["state"]
    check("retreated=True", st.get("retreated") is True, str(st.get("retreated")))
    # 队员仍在队 → 恢复成功（按当前队伍重校验，2 人达标）
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    check("全员在队恢复成功", "回到了副本深处" in out, out[:200])
    st = db.get_battle("g1", "i1")["state"]
    check("恢复后 retreated 清除", not st.get("retreated"), str(st.get("retreated")))
    # 再撤退 + 队员退队 → 恢复被拒（1 人 < min_players 2）
    out = await cmd(m, "instance_retreat", "g1", "i1", "撤退")
    check("再次撤退", "进度已保留" in out, out[:150])
    await cmd(m, "party_leave", "g1", "i2", "退队")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    check("退队后恢复被拒", "至少需要" in out or "还差" in out, out[:200])
    st = db.get_battle("g1", "i1")
    check("旧进度仍保留(retreated)", st is not None and st["state"].get("retreated") is True,
          str(st["state"].get("retreated")) if st else "None")
    reset_battle(m, "g1", "i1")

    # ============ 7. 超时文案统一（v104 批次3：120 秒→60 秒） ============
    print("【7. 超时文案统一】")
    from content.instance_cmds import INSTANCE_TIMEOUT
    check("超时阈值=60 秒", INSTANCE_TIMEOUT == 60, str(INSTANCE_TIMEOUT))
    # ★ P5F-REPOINT: 原读宿主壳 `game/commands/instance.py`（随删壳批消失）→ 读**实际含该措辞的
    #   包内模块** `content/misc_cmds.py`（『超时 60 秒自动防御』只此一处；原宿主壳里也没有这句）。
    #   注：本文件自 v137 起 `sys.exit(0)` 早退（旧结构测试已跳过），此处仅为删壳后保持落点。
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content", "misc_cmds.py"),
               encoding="utf-8").read()
    check("开本模板含'超时 60 秒'", "超时 60 秒自动防御" in src, "")
    check("无 120 秒/2 分钟残留", "120 秒" not in src and "2 分钟" not in src, "")
    # 行为探针：地图模式开本（所有当前副本均为地图模式）实际文案是否可见 60 秒
    await cmd(m, "party", "g1", "i1", "组队 队员")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    if "60 秒" not in out:
        finding("地图模式开本文案缺'60 秒'",
                "v104 批次3 只改了战斗模式开本分支（_instance_start 模板），当前全部副本首层有怪→地图模式开本，玩家实际看不到超时提示")
    else:
        check("地图模式开本文案含 60 秒", True, "")
    reset_battle(m, "g1", "i1")

    # ============ 8. 副本宠物（v104 M17 P2：副本不携带宠物） ============
    print("【8. 副本宠物（设计取舍标注）】")
    db.pet_create("i1", "pet_wolf", "小狼")
    db.pet_update("i1", level=10, satiety=100, last_sat_time=int(time.time()))
    await cmd(m, "party", "g1", "i1", "组队 队员")
    st = await open_instance(m)
    st["boss"]["hp"] = 50000
    st["boss"]["atk"] = 5
    st["boss"]["matk"] = 5
    st["turn"] = st["members"].index("i1")
    st["turn_time"] = int(time.time())
    st["acted"] = [False] * len(st["members"])
    db.save_battle("g1", "i1", st)
    out = await cmd(m, "attack", "g1", "i1", "攻击")
    pet = db.pet_get("i1")
    check("副本战斗不扣饱食度", pet["satiety"] == 100, f"satiety={pet['satiety']}")
    st2 = db.get_battle("g1", "i1")["state"]
    check("副本状态无 pet 挂载", "pet" not in st2, str(sorted(st2.keys()))[:120])
    check("副本经验结算不动宠物经验", pet["exp"] == 0, f"exp={pet['exp']}")
    finding("副本宠物未实现挂载（现状）",
            "v104 M17 P2 设计取舍：副本 Battle.from_state 不传 pet——宠物技能/经验加成/饱食度在副本内均不生效；若后续开放需同步怪平衡与结算")
    reset_battle(m, "g1", "i1")

    # ============ 9. 宠物饱食度面板 ============
    print("【9. 宠物饱食度面板】")
    db.pet_update("i1", satiety=0)
    out = await cmd(m, "pet_view", "g1", "i1", "宠物")
    check("面板显示饱食度 0/100", "饱食度：0/100" in out, out[:300])
    check("面板显示加成减半", "加成减半" in out and "+2.5%" in out, out[:300])
    db.pet_update("i1", satiety=100)
    out = await cmd(m, "pet_view", "g1", "i1", "宠物")
    check("满饱食显示全额 +5%", "+5%" in out and "加成减半" not in out, out[:300])

    # ============ 10. 宠物蛋定价 ============
    print("【10. 宠物蛋定价】")
    egg_white = C.make_pet_egg("pet_wolf")
    egg_green = C.make_pet_egg("pet_cat")
    egg_blue = C.make_pet_egg("pet_salamander")
    egg_purple = C.make_pet_egg("pet_drake")
    egg_orange = C.make_pet_egg("pet_griffin")
    check("传说蛋 > 白蛋", egg_orange["price"] > egg_white["price"], f"{egg_orange['price']} vs {egg_white['price']}")
    check("品质分档定价", egg_white["price"] == 100 and egg_green["price"] == 150
          and egg_blue["price"] == 200 and egg_purple["price"] == 300 and egg_orange["price"] == 500,
          f"w{egg_white['price']}/g{egg_green['price']}/b{egg_blue['price']}/p{egg_purple['price']}/o{egg_orange['price']}")
    check("蛋带品质字段", egg_white["quality"] == "white" and egg_orange["quality"] == "orange",
          f"{egg_white['quality']}/{egg_orange['quality']}")

    # ============ 收尾 ============
    print(f"\n结果: {passed} passed, {failed} failed")
    print(f"发现项: {len(findings)}")
    for name, detail in findings:
        print(f"  · {name}: {detail}")
    return failed

if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
