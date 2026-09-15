# -*- coding: utf-8 -*-
"""commands 层：组队副本（v49）

验证：
  1. 副本列表 / 未组队开本拦截 / 非队长开本拦截
  2. 队长开本：状态结构、Boss 血量倍率、队员自动参战
  3. 轮流回合：未轮到的人不能行动
  4. 超时自动防御（惰性检测：改 turn_time 模拟超时）
  5. 通关结算：奖励/材料/图纸/首通成就/战斗清除
  6. 全灭失败：回城 HP 0、战斗清除
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

# ⚠️ v137 副本彻底重构（副本地图化）：本测试基于旧副本结构（st["boss"]/st["turn"]/分层推进），
# 已不适用于 v137（副本=多房间地图，怪物在 rooms 池，战斗在 enemies 阵列，推进靠移动）。
# 核心玩法验收由 tests/test_v137_dungeon.py 覆盖。保留本文件供历史参考，跳过执行。
print("⏭️ test_commands_instance: v137 重构后旧结构测试已跳过（见 test_v137_dungeon.py）")
sys.exit(0)

# v94 体力：本文件用 register 命令建号（不走 make_player 的 999999），
# 副本测试不测体力系统，直接豁免体力扣减，防开本被体力拦截。
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


async def enter_combat(m, gid, qid):
    """v87.2 副本地图化：开本后为地图模式（无直接战斗），『探索』触发第一场战斗。

    副本探索可能随机触发陷阱/无事（不进入战斗），重试最多 5 次直到真正开战，
    消除全量回归下的偶发失败。
    """
    for _ in range(5):
        out = await cmd(m, "explore", gid, qid, "探索")
        if db.get_battle(gid, qid):
            return out
    return out


def _next_player_key(st):
    """v121 CTB：下一行动者 = 存活玩家中 ct 最小者（与 instance._instance_next_actor 同口径）。

    旧固定轮次断言（turn==1/2/0）在 CTB 下失效——速度快的玩家行动后可能连动
    （ct 仍最小），下一行动者完全由 ct 决定。用此辅助验证 CTB 核心语义。"""
    cts = {str(m): float(st["players"][str(m)].get("ct", 0) or 0)
           for m in st["members"]
           if st.get("alive", {}).get(str(m), True)}
    return min(cts, key=cts.get) if cts else None


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "i1", "注册 战士 队长 男")
    await cmd(m, "register", "g1", "i2", "注册 法师 队员 男")
    db.update_player("g1", "i1", level=40, gold=10000, cur_map="dawn_city")
    db.update_player("g1", "i2", level=40, gold=10000, cur_map="dawn_city")
    # v121 CTB：注册角色当前 hp 是 1 级初始值（150/90），level 提升不回满血；
    # CTB 下敌方按 ct 连动，残血前排会在首回合暴毙 → 首通成就（alive 条件）丢失、
    # 后续开本被"生命值为 0"拦截。补满血专注测副本流程（旧固定轮次下怪每回合
    # 只动一次碰巧撑住，CTB 如实呈现连动）。
    for _m in ("i1", "i2"):
        _p = db.get_player("g1", _m)
        db.update_player("g1", _m, hp=_p["max_hp"], max_hp=_p["max_hp"], mp=_p["max_mp"], max_mp=_p["max_mp"])
    # v86.3 入场钥匙：旧王陵用例多，队长备 10 把王陵钥匙（每个用例开本消耗 1 把）
    for _ in range(10):
        db.add_item("g1", "i1", "i_key_old_king", {"name": "王陵钥匙", "type": "钥匙", "stackable": True, "price": 500})

    print("【副本：列表】")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本")
    check("显示副本列表", "旧王陵" in out, out[:200])

    print("【副本：未组队开本】")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    check("提示先组队", "组队" in out, out[:120])

    print("【副本：组队后开本】")
    await cmd(m, "party", "g1", "i1", "组队 队员")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    check("开本成功", "副本开启" in out, out[:200])
    check("地图模式展示", "营地" in out or "第 1 层" in out or "探索" in out, out[:200])
    battle = db.get_battle("g1", "i1")
    check("状态存队长名下", battle and battle["state"]["type"] == "instance")
    st = battle["state"]
    check("成员 2 人", len(st["members"]) == 2, str(st["members"]))
    # v57：行动序按速度降序（快者 index 0）
    spd0 = st["players"][st["members"][0]].get("spd", 0)
    spd1 = st["players"][st["members"][1]].get("spd", 0)
    check("行动序按速度排序", spd0 >= spd1, f"{st['members']} spd={spd0},{spd1}")
    # v87.2 副本地图化：开本为地图模式（boss 未进入战斗）
    check("地图模式 mode=map", st.get("mode") == "map", f"mode={st.get('mode')}")
    check("地图模式 boss=None", st.get("boss") is None, f"boss={st.get('boss')}")
    check("层内有待清怪物", len(st.get("stage_pending", [])) >= 2, str(st.get("stage_pending")))
    # 『探索』触发第一场战斗
    out = await enter_combat(m, "g1", "i1")
    st = db.get_battle("g1", "i1")["state"]
    boss = st["boss"]
    # v86.2 分层：旧王陵第 1 层是骷髅兵（非 Boss）
    check("第 1 层小怪登场", boss["name"] in ("骷髅兵", "僵尸"), f"enemy={boss['name']}")
    check("小怪非首领", boss.get("is_boss") is not True, f"is_boss={boss.get('is_boss')}")
    check("分层状态", st.get("stage_idx") == 0 and st.get("inst_stages"), str(st.get("stage_idx")))
    check("战斗模式 mode=battle", st.get("mode") == "battle", f"mode={st.get('mode')}")

    print("【副本：轮流回合】")
    # v121 CTB：先调低首怪攻击——骷髅兵默认 atk 在 CTB 连动（8 动上限）下
    # 伤害波动/暴击可秒杀满血前排（990 血临界），干扰轮转测试（偶发首通成就丢失）
    st["boss"]["atk"] = 5
    st["boss"]["matk"] = 5
    for _eu in (st.get("enemies") or []):
        _eu["atk"] = 5
        _eu["matk"] = 5
    db.save_battle("g1", "i1", st)
    first_m = st["members"][0]
    second_m = st["members"][1]
    out = await cmd(m, "attack", "g1", second_m, "攻击")
    check("非当前行动者被拦", "等待" in out or "回合" in out, out[:120])
    out = await cmd(m, "attack", "g1", first_m, "攻击")
    check("当前行动者有返回", "骷髅兵" in out or "轮到" in out or "僵尸" in out, out[:200])
    st2 = db.get_battle("g1", "i1")["state"]
    # v121 CTB：下一行动者 = 存活玩家中 ct 最小者（快者可能连动，非固定顺序 +1）
    check("轮到下一位(ct 判定)", str(st2["members"][st2["turn"]]) == _next_player_key(st2),
          f"turn={st2['turn']}")

    print("【副本：超时自动防御】")
    st3 = db.get_battle("g1", "i1")["state"]
    # v57：Boss 速度可能触发多动秒人，调低攻击专注测轮转逻辑
    # v121 CTB：敌方阵列单位是实际结算对象（st["boss"] 为 JSON 往返后的兼容副本，
    # 改它不生效）——阵列 atk 不调低时 CTB 连动（8 动上限）会秒杀满血前排，必须一并调低
    st3["boss"]["atk"] = 5
    st3["boss"]["matk"] = 5
    for _eu in (st3.get("enemies") or []):
        _eu["atk"] = 5
        _eu["matk"] = 5
    st3["turn"] = 0  # 把回合拨回首位
    st3["turn_time"] = int(time.time()) - 200  # 模拟首位超时 200s
    # v130.10 绝对时刻 CTB：行动次序由 ct 判定（st["turn"] 仅展示，拨号不再生效）——
    # 此刻最小 ct 行动者恰为请求者（队员），旧『turn 拨回首位』不再触发超时路径。
    # 把队长 ct 拨到全场最小并保持超时 200s，使队员的攻击触发『队长自动防御 → 轮到队员』。
    for key in st3["players"]:
        st3["players"][key]["ct"] = -50.0 if key == st3["members"][0] else 0.0
    for _eu in (st3.get("enemies") or []):
        _eu["ct"] = 0.0
    db.save_battle("g1", "i1", st3)
    out = await cmd(m, "attack", "g1", second_m, "攻击")
    check("超时自动防御并行动", "自动" in out, out[:200])

    print("【副本：分层推进通关】")
    st4 = db.get_battle("g1", "i1")["state"]
    # 第 1 层：清掉当前小怪（骷髅兵）→ 自动切僵尸 → 再清 → 待深入
    st4["boss"]["hp"] = 1
    st4["turn_time"] = int(time.time())
    st4["boss"]["atk"] = 5
    st4["boss"]["matk"] = 5
    db.save_battle("g1", "i1", st4)
    cur = st4["members"][st4["turn"]]
    out = await cmd(m, "attack", "g1", cur, "攻击")
    check("清完首怪切下一只", "又一只怪物" in out or "骷髅兵" in out or "僵尸" in out, out[:200])
    # 继续清僵尸 → 第 1 层完成
    for _ in range(6):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt4 = battle["state"]
        stt4["boss"]["hp"] = 1
        stt4["boss"]["atk"] = 5
        stt4["boss"]["matk"] = 5
        for _eu in (stt4.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt4["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt4)
        cur = stt4["members"][stt4["turn"]]
        out = await cmd(m, "attack", "g1", cur, "攻击")
        if "肃清" in out or "深入" in out:
            check("第 1 层肃清提示深入", "深入" in out, out[:200])
            break
    # 『深入』→ 第 2 层（幽灵 + 幽灵骑士精英）
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    check("深入第 2 层", "第 2 层" in out or "幽灵" in out, out[:200])
    # v87.2 地图模式：探索触发第 2 层战斗
    await enter_combat(m, "g1", "i1")
    # 清第 2 层
    for _ in range(8):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt4 = battle["state"]
        stt4["boss"]["hp"] = 1
        stt4["boss"]["atk"] = 5
        stt4["boss"]["matk"] = 5
        for _eu in (stt4.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt4["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt4)
        cur = stt4["members"][stt4["turn"]]
        out = await cmd(m, "attack", "g1", cur, "攻击")
        if "肃清" in out or "深入" in out:
            break
    # 『深入』→ 第 3 层 Boss（古王·奥德里克）
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    check("深入第 3 层 Boss", "古王·奥德里克" in out, out[:200])
    # v87.2 地图化：Boss 房探索触发 Boss 战
    await enter_combat(m, "g1", "i1")
    # Boss 血量缩放验证（2 人队：inst.hp_mult + 0.65×(2-min)）——v131 动态公式（area=instance 豁免野外分档）
    _inst = C.INSTANCES["inst_old_king_tomb"]
    base = C.build_monster(_inst["boss"], {"id": "x", "name": "x", "area": "instance"})["max_hp"]
    expect = int(base * (_inst["hp_mult"] + 0.65 * (2 - _inst.get("min_players", 1))))
    stboss = db.get_battle("g1", "i1")["state"]
    check("Boss 血量 2.5 倍", abs(stboss["boss"]["max_hp"] - expect) <= 1, f"{stboss['boss']['max_hp']} vs {expect}")
    # 击杀 Boss → 通关
    # v121 CTB：Boss 速度碾压时连动多次，召唤爪牙（新召唤满血）挡前排会挡住玩家
    # 一击——改为循环攻击，每轮把全阵列（含新召唤爪牙）hp 压 1，直到真正通关
    for _ in range(6):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stboss = battle["state"]
        stboss["boss"]["hp"] = 1
        stboss["boss"]["atk"] = 5
        stboss["boss"]["matk"] = 5
        for _eu in (stboss.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stboss["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stboss)
        cur = stboss["members"][stboss["turn"]]
        out = await cmd(m, "attack", "g1", cur, "攻击")
        if "通关" in out or "击败" in out:
            break
    check("通关结算", "通关" in out or "击败" in out, out[:300])
    check("金币奖励", "+200" in out or "金币" in out, out[:300])
    check("材料奖励", "古王剑" in out, out[:300])
    battle = db.get_battle("g1", "i1")
    # v101.27 #390：通关后不再立即清战斗——保留状态供停留搜刮（cleared=True），『离开副本』才清
    check("通关后停留搜刮", battle is not None and battle["state"].get("cleared"), str(battle)[:200])
    out = await cmd(m, "instance_leave", "g1", "i1", "离开副本")
    check("离开副本传出", "离开" in out, out[:150])
    battle = db.get_battle("g1", "i1")
    check("战斗已清除", battle is None, "")
    achs = db.get_achievements("g1", "i1") or []
    found = any(a.get("ach_key") == "inst_clear_inst_old_king_tomb" and a.get("progress", 0) >= 1 for a in achs)
    check("首通成就", found, str(achs)[:200])

    print("【副本：3 人队】")
    await cmd(m, "register", "g1", "i3", "注册 游侠 第三人 男")
    db.update_player("g1", "i3", level=40, gold=10000, cur_map="dawn_city")
    out = await cmd(m, "party", "g1", "i1", "组队 第三人")
    check("队长拉第三人", "加入" in out and "3" in out, out[:150])
    members3 = db.party_members("g1", "i1")
    check("队伍 3 人", len(members3) == 3, str(members3))
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    check("3 人开本成功", "副本开启" in out, out[:150])
    st6 = db.get_battle("g1", "i1")["state"]
    check("3 人状态成员", len(st6["members"]) == 3, str(st6["members"]))
    # v87.2 副本地图化：探索触发战斗
    await enter_combat(m, "g1", "i1")
    st6 = db.get_battle("g1", "i1")["state"]
    boss6 = st6["boss"]
    # v86.2 分层：3 人开本第 1 层也是小怪（骷髅兵）
    check("3 人第 1 层小怪", boss6["name"] in ("骷髅兵", "僵尸"), f"enemy={boss6['name']}")
    # 调低攻击，专注测轮转逻辑（避免随机秒杀脆皮导致 turn 跳变）
    st6["boss"]["atk"] = 5
    st6["boss"]["matk"] = 5
    db.save_battle("g1", "i1", st6)
    # v57：行动序按速度排序（快者 index 0）。i1/i2/i3 中速度最高者先动
    # v121 CTB：行动序由 ct 判定（快者可连动），每次用当前 turn 的行动者攻击，
    # 行动后验证下一行动者 = 存活玩家中 ct 最小者
    for _ in range(4):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt = battle["state"]
        cur = stt["members"][stt["turn"]]
        out = await cmd(m, "attack", "g1", cur, "攻击")
        stn = db.get_battle("g1", "i1")["state"]
        if stn.get("over"):
            break
        check("轮流 ct 判定", str(stn["members"][stn["turn"]]) == _next_player_key(stn),
              f"turn={stn['turn']}")
    # 清理 3 人测试战斗，避免影响后续用例
    for q in ("i1", "i2", "i3"):
        m._unlock_battle("g1", q)
        db.clear_battle("g1", q)

    print("【副本：团队技能广播（v50）】")
    # 三人队：战士(队长) 牧师 拳师，30 级学会团队技能
    # 上一用例残留队伍 → 先全员退队
    await cmd(m, "party_leave", "g1", "i1", "退队")
    await cmd(m, "party_leave", "g1", "i2", "退队")
    await cmd(m, "party_leave", "g1", "i3", "退队")
    db.update_player("g1", "i1", level=40, gold=10000, cur_map="dawn_city", hp=990, mp=990)
    db.update_player("g1", "i2", level=40, gold=10000, cur_map="dawn_city", hp=990, mp=990)
    db.update_player("g1", "i3", level=40, gold=10000, cur_map="dawn_city", hp=990, mp=990)
    # 注入学会的团队技能（learned_skills 存中文名，update_player 内部转 ID 存档）
    db.update_player("g1", "i1", learned_skills=["战吼", "铁壁"], skill_points=50)
    db.update_player("g1", "i2", learned_skills=["元素流转", "奥术强化"], skill_points=50)
    # v52 Build：技能必须装进技能栏才能战斗施放
    db.set_skill_bar("i1", ["战吼", "铁壁", None, None, None, None])
    db.set_skill_bar("i2", ["元素流转", "奥术强化", None, None, None, None])
    out = await cmd(m, "party", "g1", "i1", "组队 队员")
    check("队伍已建", "组队成功" in out, out[:100])
    out = await cmd(m, "party", "g1", "i1", "组队 第三人")
    check("第三人入队", "加入了你的队伍" in out, out[:100])
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    check("团队技能本开本", "副本开启" in out, out[:120])
    # v87.2 副本地图化：探索触发战斗
    await enter_combat(m, "g1", "i1")
    stt = db.get_battle("g1", "i1")["state"]
    # 全员低血量，便于验证团队治疗
    for key in stt["players"]:
        stt["players"][key]["hp"] = 50
        stt["players"][key]["max_hp"] = 500
    stt["boss"]["atk"] = 1
    stt["boss"]["matk"] = 1
    # v121 CTB：行动者由 ct 判定（手动拨 turn 无效）——把施放者 i1 的 ct 设为全场最小
    for key in stt["players"]:
        stt["players"][key]["ct"] = -100.0 if key == "i1" else 0.0
    for _eu in (stt.get("enemies") or []):
        _eu["ct"] = 0.0
    stt["turn_time"] = int(time.time())
    db.save_battle("g1", "i1", stt)
    # 队长（战士）施放团队增益【战吼】(atk_all → 全队 atk_up)
    out = await cmd(m, "skill", "g1", "i1", "技能 战吼")
    stt2 = db.get_battle("g1", "i1")["state"]
    check("战吼广播全队 buff", all(stt2["p_buffs"].get(k, {}).get("atk_up", 0) > 0 for k in stt2["players"]),
          str(stt2["p_buffs"]))
    # 法师（队员2）施放团队增益【元素流转】(matk_all → 全队 matk_up)
    for key in stt2["players"]:
        stt2["players"][key]["ct"] = -100.0 if key == "i2" else 0.0
    for _eu in (stt2.get("enemies") or []):
        _eu["ct"] = 0.0
    stt2["turn_time"] = int(time.time())
    db.save_battle("g1", "i1", stt2)
    out = await cmd(m, "skill", "g1", "i2", "技能 元素流转")
    stt3 = db.get_battle("g1", "i1")["state"]
    check("元素流转广播全队", all(stt3["p_buffs"].get(k, {}).get("matk_up_strong", 0) > 0 or stt3["p_buffs"].get(k, {}).get("matk_up", 0) > 0 for k in stt3["players"]),
          str({k: stt3["p_buffs"].get(k, {}) for k in stt3["players"]}))
    # 清理
    for q in ("i1", "i2", "i3"):
        m._unlock_battle("g1", q)
        db.clear_battle("g1", q)

    print("【副本：全灭失败】")
    await cmd(m, "party", "g1", "i1", "组队 队员")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    check("再次开本", "副本开启" in out, out[:120])
    # v87.2 副本地图化：探索触发战斗
    await enter_combat(m, "g1", "i1")
    st5 = db.get_battle("g1", "i1")["state"]
    for key in st5["players"]:
        st5["players"][key]["hp"] = 1
        # v121 CTB + 站位：Boss reach=1 只打前排，后排玩家打不到会导致僵持（不全灭）。
        # 全员压到前排 + Boss reach=3，保证秒杀可达
        st5["players"][key]["rank"] = 1
    st5["boss"]["atk"] = 99999   # Boss 秒杀，保证每轮杀一人
    st5["boss"]["matk"] = 99999
    for _eu in (st5.get("enemies") or []):  # v2：阵列单位才是结算对象（兼容键为副本）
        _eu["atk"] = 99999
        _eu["matk"] = 99999
        _eu["reach"] = 3
        # v121 CTB：骷髅兵 spd 低会被玩家连动压制 15 轮不动（僵持）——拉满速度先手秒杀
        _eu["spd"] = 999
        _eu["ct"] = -999
    st5["turn_time"] = int(time.time())
    db.save_battle("g1", "i1", st5)
    # 轮流攻击直到战斗结束（Boss 一轮杀一人，3 人队最多 3 轮全灭）
    last = ""
    for _ in range(15):
        battle = db.get_battle("g1", "i1")
        if battle is None:
            break
        st = battle["state"]
        # 找到当前行动者（跳过已阵亡者）
        idx = st["turn"]
        for _j in range(len(st["members"])):
            if st["alive"].get(str(st["members"][idx]), True):
                break
            idx = (idx + 1) % len(st["members"])
        cur = st["members"][idx]
        last = await cmd(m, "attack", "g1", cur, "攻击")
    battle = db.get_battle("g1", "i1")
    check("失败后战斗清除", battle is None, last[:200])
    check("失败提示", "失败" in last or "全灭" in last, last[:200])
    p1 = db.get_player("g1", "i1")
    check("队长 HP 0 回城", p1["hp"] == 0, f"hp={p1['hp']}")

    print("【副本：人数配置（v53）】")
    # 清理全灭残留队伍
    await cmd(m, "party_leave", "g1", "i1", "退队")
    await cmd(m, "party_leave", "g1", "i2", "退队")
    await cmd(m, "party_leave", "g1", "i3", "退队")
    db.update_player("g1", "i1", level=70, gold=10000, cur_map="dawn_city", hp=500)
    # 列表显示人数要求
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本")
    check("列表显示单人标记", "单人" in out, out[:300])
    check("列表显示 2-3 人", "2-3人" in out, out[:300])
    check("列表显示 4 人", "4人" in out, out[:300])
    # 单人副本：无需组队直接开本
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 哥布林营地")
    check("单人副本免组队开本", "副本开启" in out, out[:200])
    battle = db.get_battle("g1", "i1")
    stg = battle["state"]
    check("单人副本成员 1 人", len(stg["members"]) == 1, str(stg["members"]))
    # v87.2 副本地图化：探索触发战斗
    await enter_combat(m, "g1", "i1")
    stg = db.get_battle("g1", "i1")["state"]
    # v86.2 分层：第 1 层是哥布林守卫（非 Boss）
    check("单人第 1 层小怪", stg["boss"]["name"] in ("哥布林守卫", "哥布林萨满"), f"enemy={stg['boss']['name']}")
    check("单人无队伍构成警告", "没有坦克" not in out, out[:200])
    # 打到第 3 层验证 Boss 血量缩放（单人 min_players=1 → 1.6 倍）
    for _ in range(20):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt = battle["state"]
        stt["boss"]["hp"] = 1
        stt["boss"]["atk"] = 5
        stt["boss"]["matk"] = 5
        for _eu in (stt.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt)
        out = await cmd(m, "attack", "g1", "i1", "攻击")
        if "深入" in out or "通关" in out:
            break
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    # v87.2 地图模式：探索触发第 2 层战斗
    await enter_combat(m, "g1", "i1")
    for _ in range(20):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt = battle["state"]
        stt["boss"]["hp"] = 1
        stt["boss"]["atk"] = 5
        stt["boss"]["matk"] = 5
        for _eu in (stt.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt)
        out = await cmd(m, "attack", "g1", "i1", "攻击")
        if "深入" in out or "通关" in out:
            break
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    # v87.2 地图化：Boss 房探索触发 Boss 战
    await enter_combat(m, "g1", "i1")
    stg3 = db.get_battle("g1", "i1")["state"]
    check("单人第 3 层 Boss", "哥布林酋长" in stg3["boss"]["name"], f"enemy={stg3['boss']['name']}")
    _inst = C.INSTANCES["inst_goblin_camp"]
    base_g = C.build_monster(_inst["boss"], {"id": "x", "name": "x", "area": "instance"})["max_hp"]
    expect_g = int(base_g * (_inst["hp_mult"] + 0.65 * (1 - _inst.get("min_players", 1))))  # 单人
    check("单人 Boss 血量 = 1.6 倍", abs(stg3["boss"]["max_hp"] - expect_g) <= 1, f"{stg3['boss']['max_hp']} vs {expect_g}")
    # 单人副本直接通关（v2：Boss rank2 + 2 爪牙 rank1——先清爪牙，Boss 前移后才可及，需多次攻击）
    for _ in range(12):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stg3 = battle["state"]
        stg3["boss"]["hp"] = 1
        stg3["boss"]["atk"] = 5
        stg3["boss"]["matk"] = 5
        for _eu in (stg3.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stg3["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stg3)
        out = await cmd(m, "attack", "g1", "i1", "攻击")
        if "通关" in out or "击败" in out:
            break
    check("单人副本通关", "通关" in out or "击败" in out, out[:300])
    check("单人掉落咕噜皇冠材料", "咕噜皇冠" in out, out[:300])
    # v101.27 #390：通关后停留搜刮状态保留，主动『离开副本』清战斗
    out = await cmd(m, "instance_leave", "g1", "i1", "离开副本")
    check("单人离开副本", "离开" in out, out[:150])
    battle = db.get_battle("g1", "i1")
    check("单人副本战斗清除", battle is None, "")
    # 4 人副本：3 人队伍被拦截
    await cmd(m, "register", "g1", "i4", "注册 牧师 第四人 男")
    # 全队提到 70 级（深海龙宫 Lv.70+）+ 恢复满血（v101.27 #393：0 血进本被拦截）
    for q in ("i1", "i2", "i3", "i4"):
        p = db.get_player("g1", q)
        db.update_player("g1", q, level=70, gold=10000, cur_map="dawn_city",
                         hp=p.get("max_hp", 100) if p else 100)
    await cmd(m, "party", "g1", "i1", "组队 队员")
    await cmd(m, "party", "g1", "i1", "组队 第三人")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 深海龙宫")
    check("4 人副本 3 人拦截", "至少需要 4 人" in out, out[:200])
    # 拉第四人 → 4 人队伍开本成功
    out = await cmd(m, "party", "g1", "i1", "组队 第四人")
    check("队长拉第四人", "加入了你的队伍" in out and "4" in out, out[:200])
    members4 = db.party_members("g1", "i1")
    check("队伍 4 人", len(members4) == 4, str(members4))
    # v86.3 入场钥匙：深海龙宫需要龙宫珠（v110 审计：key_item 回退材料名，材料即钥匙）
    db.add_item("g1", "i1", "mat_long_gong_zhu", {"name": "龙宫珠", "type": "材料", "stackable": True, "price": 300})
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 深海龙宫")
    check("4 人副本开本成功", "副本开启" in out, out[:200])
    stm = db.get_battle("g1", "i1")["state"]
    check("4 人副本成员 4 人", len(stm["members"]) == 4, str(stm["members"]))
    # v87.2 副本地图化：探索触发战斗
    await enter_combat(m, "g1", "i1")
    stm = db.get_battle("g1", "i1")["state"]
    # v86.2 分层：第 1 层小怪，推进到 Boss 层验证血量缩放
    check("4 人第 1 层小怪", stm["boss"].get("is_boss") is not True, f"enemy={stm['boss']['name']}")
    for _ in range(25):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt = battle["state"]
        stt["boss"]["hp"] = 1
        stt["boss"]["atk"] = 5
        stt["boss"]["matk"] = 5
        for _eu in (stt.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt)
        curm = stt["members"][stt["turn"]]
        out = await cmd(m, "attack", "g1", curm, "攻击")
        if "深入" in out or "通关" in out:
            break
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    # v87.2 地图模式：探索触发第 2 层战斗
    await enter_combat(m, "g1", "i1")
    for _ in range(25):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt = battle["state"]
        stt["boss"]["hp"] = 1
        stt["boss"]["atk"] = 5
        stt["boss"]["matk"] = 5
        for _eu in (stt.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt)
        curm = stt["members"][stt["turn"]]
        out = await cmd(m, "attack", "g1", curm, "攻击")
        if "深入" in out or "通关" in out:
            break
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    # v87.2 地图化：Boss 房探索触发 Boss 战
    await enter_combat(m, "g1", "i1")
    stm3 = db.get_battle("g1", "i1")["state"]
    _inst = C.INSTANCES["inst_deep_dragon_palace"]
    base_m = C.build_monster(_inst["boss"], {"id": "x", "name": "x", "area": "instance"})["max_hp"]
    expect_m = int(base_m * (_inst["hp_mult"] + 0.65 * (4 - _inst.get("min_players", 1))))  # 4 人
    check("4 人 Boss 血量 = 2.7 倍", abs(stm3["boss"]["max_hp"] - expect_m) <= 1, f"{stm3['boss']['max_hp']} vs {expect_m}")
    # 清理深海龙宫战斗（否则 instance_cmd 直接显示状态，走不到人数校验）
    for q in ("i1", "i2", "i3", "i4"):
        m._unlock_battle("g1", q)
        db.clear_battle("g1", q)
    # 2 人副本超限提示（队伍 4 人打旧王陵）
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    check("旧王陵 4 人超限", "最多 3 人" in out, out[:200])
    for q in ("i1", "i2", "i3", "i4"):
        m._unlock_battle("g1", q)
        db.clear_battle("g1", q)

    print("【副本：入场钥匙（v86.3）】")
    # 单人副本鹿角要塞需要军旗碎片（v110 审计：key_item 回退材料名，材料即钥匙）
    await cmd(m, "party_leave", "g1", "i1", "退队")
    db.update_player("g1", "i1", level=20, gold=10000, cur_map="dawn_city", hp=500)
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 鹿角要塞")
    check("无钥匙被拦截", "军旗碎片" in out and "封印" in out, out[:200])
    battle = db.get_battle("g1", "i1")
    check("拦截后未开本", battle is None, "")
    # 给钥匙（材料）→ 开本成功 → 钥匙消耗
    db.add_item("g1", "i1", "mat_jun_qi_sui_pian", {"name": "军旗碎片", "type": "材料", "stackable": True, "price": 100})
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 鹿角要塞")
    check("有钥匙开本成功", "副本开启" in out, out[:200])
    inv = db.get_inventory("g1", "i1")
    keys = [i for i in inv if "军旗" in (i.get("data") or {}).get("name", "")]
    check("钥匙已消耗", len(keys) == 0, str([(i.get("data") or {}).get("name") for i in inv])[:200])
    # v87.2 副本地图化：探索触发战斗
    await enter_combat(m, "g1", "i1")
    stk = db.get_battle("g1", "i1")["state"]
    stk["boss"]["hp"] = 1
    stk["boss"]["atk"] = 5
    stk["boss"]["matk"] = 5
    for _eu in (stk.get("enemies") or []):  # v2：兼容键同步到阵列单位
        _eu["hp"] = 1
        _eu["atk"] = 5
        _eu["matk"] = 5
    stk["turn_time"] = int(time.time())
    db.save_battle("g1", "i1", stk)
    for _ in range(10):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt = battle["state"]
        stt["boss"]["hp"] = 1
        stt["boss"]["atk"] = 5
        stt["boss"]["matk"] = 5
        for _eu in (stt.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt)
        cur = stt["members"][stt["turn"]]
        out = await cmd(m, "attack", "g1", cur, "攻击")
        if "深入" in out or "通关" in out:
            break
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    # v87.2 地图模式：探索触发第 2 层战斗
    await enter_combat(m, "g1", "i1")
    for _ in range(10):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt = battle["state"]
        stt["boss"]["hp"] = 1
        stt["boss"]["atk"] = 5
        stt["boss"]["matk"] = 5
        for _eu in (stt.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt)
        cur = stt["members"][stt["turn"]]
        out = await cmd(m, "attack", "g1", cur, "攻击")
        if "深入" in out or "通关" in out:
            break
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    # v87.2 地图化：Boss 房探索触发 Boss 战
    await enter_combat(m, "g1", "i1")
    # v121 CTB：Boss 狂暴后连动+召唤挡刀会挡住一击——循环攻击（每轮全阵列 hp 压 1）直到通关
    for _ in range(6):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stk3 = battle["state"]
        stk3["boss"]["hp"] = 1
        stk3["boss"]["atk"] = 5
        stk3["boss"]["matk"] = 5
        for _eu in (stk3.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stk3["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stk3)
        cur = stk3["members"][stk3["turn"]]
        out = await cmd(m, "attack", "g1", cur, "攻击")
        if "通关" in out or "击败" in out:
            break
    check("首通完成", "通关" in out or "击败" in out, out[:300])
    # v101.27 #390：通关后停留状态保留，先『离开副本』再验证免钥匙开本
    out = await cmd(m, "instance_leave", "g1", "i1", "离开副本")
    check("鹿角离开副本", "离开" in out, out[:150])
    # 首通后再开本 → 免钥匙直接进
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 鹿角要塞")
    check("首通后免钥匙开本", "副本开启" in out, out[:200])
    for q in ("i1",):
        m._unlock_battle("g1", q)
        db.clear_battle("g1", q)

    print(f"\n结果: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
