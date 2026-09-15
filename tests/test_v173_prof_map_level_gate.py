# -*- coding: utf-8 -*-
"""v173 副业地图分阶段门禁：采集/挖掘按副业等级分档（每 10 级图 ≈ 1 级副业）。

规则（鱼鱼 2026-09 拍板）：
- 采集：图等级 → 需采集副业 Lv = 1 + (图lv-1)//10；副业 Lv 不足 → 拦
- 挖掘：矿点图配置 min_lv（同规则）；副业 Lv 不足 → 拦
- 副业有每日任务（50 exp/天）加速，不会卡死

覆盖：
1. 低采集等级(Lv1)在 Lv50 星语湖『采集』被拦（需采 Lv.6）
2. 低采集等级(Lv1)在新手图 oak_plain(Lv1) 采集放行
3. 采集等级足够后在高级图放行（Lv50 星语湖 Lv6）
4. 低挖掘等级在冰牙谷(Lv63，需挖 Lv7)『挖掘』被拦
5. 挖掘等级足够后在冰牙谷放行
6. 城镇采集仍保持原拦截（不回归）
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, make_player, Main, run

FAILS = []

def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        FAILS.append(name)
        print(f"  ✗ {name} {detail}")

async def cmd(m, handler_name, gid, qid, msg):
    from conftest import FakeEvent
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

def set_prof(gid, qid, key, lv):
    while db.get_prof_level(gid, qid, key) < lv:
        db.add_prof_exp(gid, qid, key, 100)

async def main():
    clean_db()
    m = Main(None)
    # --- 1. 低采集(Lv1) 在 Lv50 星语湖采集被拦（需采 Lv.6）---
    make_player("g1", "low", name="低采集", cls="战士", level=50)
    db.update_player("g1", "low", cur_map="starlake", cur_subarea="starlake_1",
                     apprentices=["gather", "mining"])
    set_prof("g1", "low", "gather", 1)
    out = await cmd(m, "gather", "g1", "low", "采集")
    check("采集Lv1在Lv50星语湖被拦", "需采集 Lv.5" in out, out[:200])

    # --- 2. 低采集(Lv1) 在新手图 oak_plain(Lv1) 放行 ---
    db.update_player("g1", "low", cur_map="oak_plain", cur_subarea="oak_plain_1")
    out = await cmd(m, "gather", "g1", "low", "采集")
    check("采集Lv1在新手图放行", "秒后完成" in out or "还在采集" in out, out[:200])
    m._prof_wait_clear("g1", "low")

    # --- 3. 采集等级够后在星语湖放行（升到 Lv.6）---
    set_prof("g1", "low", "gather", 6)
    db.update_player("g1", "low", cur_map="starlake", cur_subarea="starlake_1")
    out = await cmd(m, "gather", "g1", "low", "采集")
    check("采集Lv6在Lv50星语湖放行", "秒后完成" in out or "还在采集" in out, out[:200])
    m._prof_wait_clear("g1", "low")

    # --- 4. 低挖掘在冰牙谷(Lv63, 需挖7)被拦 ---
    make_player("g1", "miner", name="低挖掘", cls="战士", level=63)
    db.update_player("g1", "miner", cur_map="frost_fang", cur_subarea="frost_fang_1",
                     apprentices=["gather", "mining"])
    set_prof("g1", "miner", "mining", 1)
    out = await cmd(m, "mining", "g1", "miner", "挖掘")
    check("挖掘Lv1在冰牙谷(需挖7)被拦", "需要挖掘 Lv.7" in out, out[:200])

    # --- 5. 挖掘等级够后在冰牙谷放行 ---
    set_prof("g1", "miner", "mining", 7)
    out = await cmd(m, "mining", "g1", "miner", "挖掘")
    check("挖掘Lv7在冰牙谷放行", "矿脉" in out and "凿向" in out, out[:200])
    m._prof_wait_clear("g1", "miner")

    # --- 6. 城镇采集仍被原拦截（不回归）---
    make_player("g1", "town", name="城镇", cls="战士", level=5)
    db.update_player("g1", "town", cur_map="oak_town", cur_subarea="oak_town_1",
                     apprentices=["gather"])
    set_prof("g1", "town", "gather", 1)
    out = await cmd(m, "gather", "g1", "town", "采集")
    check("城镇采集仍被拦", "城镇里没有可采集" in out, out[:200])

    print(f"\n结果: {'全部通过' if not FAILS else f'{len(FAILS)} 项失败: {FAILS}'}")
    return 0 if not FAILS else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
