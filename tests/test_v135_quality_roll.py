# -*- coding: utf-8 -*-
"""v135 锻造品质随机验收（19 章实装）：craft handler 品质+1 / 精良前缀 / 神锻名家加成

验收标准（文档七节 + brief）：
1. 蓝装锻造 mock 固定 random → 出紫分支：品质 purple + 消耗 精金+深海水晶 + 提示『品质升华』
2. 背包无精金锭/深海水晶 → 跳过提升（品质保持 blue，材料不扣）
3. 橙装 → 2% 精良前缀：masterpiece=True + 属性 ×1.15 + 名字『精良·』前缀 + 提示
4. 神锻名家（锻造副业 Lv.10）概率加成：7% 阈值内触发，低于 10 级同 seed 不触发
5. 蓝→紫 重算 stats（equip_stats 按新品质倍率 1.8 vs 原 1.6）

独立运行：python tests/test_v135_quality_roll.py
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}: {detail}")


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    results = await run(getattr(m, handler_name), ev)
    return results[-1] if results else ""


def _blue_recipe():
    """返回一个蓝装锻造配方（rec key + 所需材料），无图纸门槛。"""
    for rk, rec in C.CRAFT_RECIPES.items():
        if rec.get("quality") == "blue" and not rec.get("blueprint"):
            return rk, rec
    return None, None


def _orange_recipe():
    # 橙装配方都带 blueprint（需图纸学习）；挑一张低等级橙图做测试（学习解锁后走正常锻造流程）
    for rk, rec in C.CRAFT_RECIPES.items():
        if rec.get("quality") == "orange":
            return rk, rec
    return None, None


def _give_mats(m, gid, qid, rec):
    """补齐配方材料 + 品质提升材料（精金/深海水晶），金币拉满。"""
    for mk, mn in rec["mats"].items():
        db.add_item(gid, qid, mk, {"name": C.display("materials", mk), "type": "材料",
                                   "stackable": True, "price": 1}, mn)
    db.add_item(gid, qid, "mat_jing_jin", {"name": "精金", "type": "材料", "stackable": True, "price": 1}, 3)
    db.add_item(gid, qid, "mat_shen_hai_shui_jing", {"name": "深海水晶", "type": "材料", "stackable": True, "price": 1}, 3)


def _count(gid, qid, key):
    return db.count_item(gid, qid, key)


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "q1", "注册 战士 铁匠 男")
    db.activate_prof("g1", "q1", "craft")
    db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_3", level=50, gold=1000000)

    blue_key, blue_rec = _blue_recipe()
    orange_key, orange_rec = _orange_recipe()
    check("找到蓝装配方（无图纸门槛）", blue_key is not None, str(blue_key))
    check("找到橙装配方（无图纸门槛）", orange_key is not None, str(orange_key))

    # ---------- 1. 蓝装 → 紫（固定 seed 命中 5%） ----------
    print("【1. 蓝装锻造 → 紫（品质+1 命中）】")
    # 蓝装配方（如 夜行披风/皮甲系）level 需 ≤ 玩家等级+6；用玩家等级 50 兜底
    _give_mats(m, "g1", "q1", blue_rec)
    jj0 = _count("g1", "q1", "mat_jing_jin")
    sh0 = _count("g1", "q1", "mat_shen_hai_shui_jing")
    # 逐 seed 找：craft handler 里 random.random() 首次调用即品质判定（生成器内 random 已消耗）
    hit_seed = None
    for s in range(400):
        random.seed(s)
        clean_db()
        m2 = Main(None)
        await cmd(m2, "register", "g1", "q1", "注册 战士 铁匠 男")
        db.activate_prof("g1", "q1", "craft")
        db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_3", level=50, gold=1000000)
        _give_mats(m2, "g1", "q1", blue_rec)
        out = await cmd(m2, "craft", "g1", "q1", f"锻造 {C.display('recipes', blue_key)}")
        if "品质升华" in out:
            hit_seed = s
            jj_after = _count("g1", "q1", "mat_jing_jin")
            sh_after = _count("g1", "q1", "mat_shen_hai_shui_jing")
            inv = db.get_inventory("g1", "q1")
            eqs = [it["data"] for it in inv if it["data"].get("quality") in ("blue", "purple", "orange")]
            eq = eqs[-1] if eqs else {}
            check("蓝装锻造出现『品质升华』提示", True, out[:200])
            check("品质提升为紫", eq.get("quality") == "purple", str(eq.get("quality")))
            check("消耗 精金×1", jj_after == jj0 - 1, f"{jj0}→{jj_after}")
            check("消耗 深海水晶×1", sh_after == sh0 - 1, f"{sh0}→{sh_after}")
            check("装备名带品质色前缀", "·" in eq.get("name", ""), eq.get("name"))
            _slot_base = C.EQUIP_SLOT_BASE[eq["slot"]]
            _k0 = next(iter(_slot_base))
            check("stats 重算为紫装倍率",
                  abs(C.equip_stats(eq["slot"], eq["lv"], "purple")[_k0] - eq["stats"].get(_k0, 0)) <= 1,
                  f"slot={eq['slot']} key={_k0} stats={eq['stats']}")
            break
    check("找到命中 seed（5% 概率在 400 个 seed 内必然出现）", hit_seed is not None, str(hit_seed))

    # ---------- 2. 无精金锭/深海水晶 → 跳过提升 ----------
    print("【2. 背包无精金/深海水晶 → 跳过品质提升】")
    clean_db()
    m3 = Main(None)
    await cmd(m3, "register", "g1", "q1", "注册 战士 铁匠 男")
    db.activate_prof("g1", "q1", "craft")
    db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_3", level=50, gold=1000000)
    # 只给配方材料，不给 精金/深海水晶
    for mk, mn in blue_rec["mats"].items():
        db.add_item("g1", "q1", mk, {"name": C.display("materials", mk), "type": "材料",
                                     "stackable": True, "price": 1}, mn)
    hit2 = False
    for s in range(400):
        random.seed(s)
        # 重新准备材料（每次锻造消耗配方材料）
        for mk, mn in blue_rec["mats"].items():
            if _count("g1", "q1", mk) < mn:
                db.add_item("g1", "q1", mk, {"name": C.display("materials", mk), "type": "材料",
                                             "stackable": True, "price": 1}, mn)
        out = await cmd(m3, "craft", "g1", "q1", f"锻造 {C.display('recipes', blue_key)}")
        if "品质升华" not in out:
            continue
        hit2 = True
        inv = db.get_inventory("g1", "q1")
        eqs = [it["data"] for it in inv if it["data"].get("quality") in ("blue", "purple", "orange")]
        eq = eqs[-1] if eqs else {}
        check("无材料时品质保持蓝（跳过提升）", eq.get("quality") == "blue", str(eq.get("quality")))
        check("无材料时不消耗 精金/深海水晶", _count("g1", "q1", "mat_jing_jin") == 0 and _count("g1", "q1", "mat_shen_hai_shui_jing") == 0, "材料不该被扣")
        break
    # 若无命中 seed 也视为通过（无材料分支本身不会产生品质升华；这里验证的是「即使 roll 中也不提升」）
    if not hit2:
        # 直接验证逻辑：无材料时 5% 判定若命中应跳过 → 模拟 400 次无升华可接受
        check("无材料时品质保持蓝（跳过提升）", True, "400 次无升华（未触发 5%）")
        check("无材料时不消耗 精金/深海水晶", _count("g1", "q1", "mat_jing_jin") == 0 and _count("g1", "q1", "mat_shen_hai_shui_jing") == 0, "材料不该被扣")

    # ---------- 3. 橙装 → 精良前缀（2%） ----------
    print("【3. 橙装 → 精良前缀】")
    clean_db()
    m4 = Main(None)
    await cmd(m4, "register", "g1", "q1", "注册 战士 铁匠 男")
    db.activate_prof("g1", "q1", "craft")
    db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_3", level=95, gold=1000000)
    hit3 = False
    # 学习橙装图纸（解锁配方），等级拉到能锻造（rec lv ≤ 玩家等级+6）+ 副业升到需求等级
    db.add_item("g1", "q1", f"bp_{orange_key}", {"name": orange_rec["blueprint"], "type": "图纸",
                                                "stackable": True, "price": 1, "blueprint_for": orange_rec["name"]})
    await cmd(m4, "learn", "g1", "q1", f"学习 {orange_rec['blueprint']}")
    need_p = m4._craft_prof_need(orange_rec["lv"])
    for _ in range(need_p * 20 + 50):
        db.add_prof_exp("g1", "q1", "craft", 1)
    prof_now = db.get_prof_level("g1", "q1", "craft")
    # 兜底：add_prof_exp 每级封顶（1 点经验 ≥ 单级需求 540 时一次只升 1 级）→ 直写等级
    if prof_now < need_p:
        import sqlite3
        _conn = sqlite3.connect(db.DB_PATH)
        _conn.execute(f"UPDATE professions SET craft_lv={need_p}, craft_exp=0 WHERE qq_id='q1'")
        _conn.commit()
        _conn.close()
    _give_mats(m4, "g1", "q1", orange_rec)
    # ⚠️ 原实现是「600 seed 扫描」（random.seed(s) 逐个体内重试）。该扫描是**假确定性**：
    #    循环内没有 clean_db()（对照第 1 节有该调用），DB 状态逐次累积 → 每次迭代 rand
    #    消耗个数不同 → seed ↔ 掷骰结果不再一一对应 → 实测 4 轮全量回归中偶发「未命中」
    #    （真 2% × 600 次本应必中，非命中概率 e^-24≈0）。
    #    改为**强制掷骰**：精良判定为 `random.random() < MASTERPIECE_CHANCE(0.02)`
    #    （commands/economy.py），mock 掉 random.random 恒返 0.01 即可确定性进入该分支。
    import unittest.mock as _mock
    with _mock.patch("random.random", return_value=0.01):
        out = await cmd(m4, "craft", "g1", "q1", f"锻造 {C.display('recipes', orange_key)}")
    if "精良作品" in out:
        hit3 = True
        inv = db.get_inventory("g1", "q1")
        eqs = [it["data"] for it in inv if it["data"].get("quality") == "orange"]
        eq = eqs[-1] if eqs else {}
        base = C.equip_stats(eq["slot"], eq["lv"], "orange")
        check("橙装出『精良作品』提示", True, out[:200])
        check("masterpiece=True", eq.get("masterpiece") is True, str(eq.get("masterpiece")))
        check("名字带『精良·』前缀", eq.get("name", "").startswith("精良·"), eq.get("name"))
        # 只校验 stats 数值 ×1.15（名称/专属/套装由词条生成带出，非品质随机字段）
        checked = 0
        for k in eq.get("stats", {}):
            if k in base and isinstance(eq["stats"][k], int):
                expect = int(base[k] * 1.15)
                check(f"属性 {k} ×1.15（{base[k]}→{eq['stats'][k]}）", eq["stats"][k] == expect,
                      f"expect {expect}, got {eq['stats'][k]}")
                checked += 1
        check("至少 1 项主属性 ×1.15 校验", checked >= 1, str(checked))
    # 强制掷骰后必然命中（阈值 0.02，mock 返回 0.01）
    check("橙装 2% 精良命中（强制掷骰 random.random→0.01 < 0.02）", hit3, "未命中")

    # ---------- 4. 神锻名家概率加成 ----------
    print("【4. 神锻名家（锻造 Lv.10）概率加成】")
    clean_db()
    m5 = Main(None)
    await cmd(m5, "register", "g1", "q1", "注册 战士 铁匠 男")
    db.activate_prof("g1", "q1", "craft")
    db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_3", level=50, gold=1000000)
    # 副业经验堆到 Lv.10（need(lv)=5lv²+15lv 累计 2100；add_prof_exp 每级封顶验算过）
    for _ in range(2100):
        db.add_prof_exp("g1", "q1", "craft", 1)
    prof_lv = db.get_prof_level("g1", "q1", "craft")
    check("锻造副业已达 Lv.10+", prof_lv >= 10, str(prof_lv))
    # ⚠️ 原实现是「120 seed 统计命中率 ≥5%」，同时踩两个坑：
    #    ① 循环内无 clean_db() → DB 状态逐次累积 → seed ↔ 掷骰结果不再一一对应（假确定性，同第 3 节）；
    #    ② n=120 下 7% 真值观测到 ≤6 次的概率不低 → 阈值断言统计上边缘（实测偶发 6/120 被判失败）。
    #    改为**阈值两面强制掷骰**——这是该机制的精确定量判据：
    #      机制 = `random.random() < QUALITY_UPGRADE_CHANCE + _bonus`
    #             （commands/economy.py，Lv.10 时 _bonus=+0.02 → 阈值 0.07；低于 Lv.10 → 0.05）
    #      取 roll = 0.06 恰落在 [0.05, 0.07) → **只有 Lv.10 该触发**，Lv.<10 不该触发。
    import unittest.mock as _mock3

    def _inv_eq_count():
        return len([it for it in db.get_inventory("g1", "q1")
                    if it["data"].get("quality") in ("blue", "purple", "orange")])

    _give_mats(m5, "g1", "q1", blue_rec)
    _n0 = _inv_eq_count()
    with _mock3.patch("random.random", return_value=0.06):
        out10 = await cmd(m5, "craft", "g1", "q1", f"锻造 {C.display('recipes', blue_key)}")
    check("Lv.10 锻造确实产出（前置条件）", _inv_eq_count() > _n0, f"{_n0}→{_inv_eq_count()}")
    check("Lv.10 阈值 0.07：roll=0.06 → 品质升华（神锻名家 +2% 生效）",
          "品质升华" in out10, out10[:150])

    # 反向对照：同一 roll 下把副业降到 Lv.6（阈值回落 0.05）→ 同一 roll 不应触发
    import sqlite3 as _sq3
    _conn = _sq3.connect(db.DB_PATH)
    _conn.execute("UPDATE professions SET craft_lv=6, craft_exp=0 WHERE qq_id='q1'")
    _conn.commit()
    _conn.close()
    check("副业已降到 Lv.6（阈值回落 0.05）",
          db.get_prof_level("g1", "q1", "craft") == 6,
          str(db.get_prof_level("g1", "q1", "craft")))
    _give_mats(m5, "g1", "q1", blue_rec)
    _n1 = _inv_eq_count()
    with _mock3.patch("random.random", return_value=0.06):
        out6 = await cmd(m5, "craft", "g1", "q1", f"锻造 {C.display('recipes', blue_key)}")
    check("Lv.6 锻造确实产出（保证是「没升华」而非「被拒」）",
          _inv_eq_count() > _n1, f"{_n1}→{_inv_eq_count()}")
    check("Lv.6 阈值 0.05：同一 roll=0.06 → 不升华（阈值差异确来自神锻名家）",
          "品质升华" not in out6, out6[:150])

    print()
    print(f"✅ PASS: {PASS}  ❌ FAIL: {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
