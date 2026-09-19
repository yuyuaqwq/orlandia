# -*- coding: utf-8 -*-
"""v104 R3 M15 垂钓系统第三轮修复回归（tests/test_r3_m15_fishing.py）

覆盖：
  P1-1 星骸遗鳞：采集池移除（垂钓彩蛋独占恢复）+ 历史采集版(type=材料)堆按名兜底可回收 1 金
  P1-2 等待中重复垂钓/采集/挖掘不再白扣 5 体力（M13 同卡共修，复验）
  P2-1 传说档全服广播：鱼王 + 古代鱼骨触发 _broadcast（史诗/普通静默）
  P2-2 夜光鲛消费点：烹饪配方 cook_glow_shark_soup 可制作并消耗 mat_ye_guang_jiao
  P2-3 图鉴收藏永久化：出售收藏鱼后图鉴不回退（钓获成就=永久记录）
  P2-4 鱼饵 24h 过期：挂饵超 24h 不生效并清除；新鲜鱼饵正常生效

⚠️ 隔离说明：不用 conftest 的共享 test_game_data.db——并行 agent 的测试会
clean_db() 清空同库数据（实测注册后被并发清库导致玩家消失），本测试使用
独立库文件 test_game_data_m15_r3.db，避免并行竞态。
"""
import os
import sys
import time
import json
import asyncio
import sqlite3

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # dragonfall/
# 2026-09-13：私有库移进 tests/.private_dbs/（原先直接落在仓根，
# 每次全量回归都在仓根留下 test_game_data_m15_r3.db；见 .gitignore）
TEST_DB = os.path.join(PLUGIN_DIR, "tests", ".private_dbs", "test_game_data_m15_r3.db")
os.makedirs(os.path.dirname(TEST_DB), exist_ok=True)

# 必须在 import 插件前设置（connection.py 模块级读取 DB_PATH）
os.environ["GWEN_GAME_DB"] = TEST_DB
sys.path.insert(0, PLUGIN_DIR)

from _engine_harness import C, db  # noqa: E402
from _engine_harness import Main  # noqa: E402

# v94 体力：测试环境走 register 命令建号后体力拉满（与 conftest 同款）
_orig_register = Main.register
async def _register_with_stamina(self, event):
    gid = event.get_group_id() or "private"
    qid = event.get_sender_id() or "unknown"
    async for r in _orig_register(self, event):
        yield r
    try:
        db.update_player(gid, qid, stamina=999999)
    except Exception:
        pass
Main.register = _register_with_stamina


class FakeEvent:
    def __init__(self, group_id, qq_id, msg=""):
        self._g = group_id
        self._q = qq_id
        self.message_str = msg

    def get_group_id(self):
        return self._g

    def get_sender_id(self):
        return self._q

    def get_message_str(self):
        return self.message_str

    def plain_result(self, text):
        return text

    def stop_event(self):
        pass


async def run(handler, ev):
    gen = handler(ev)
    results = []
    try:
        while True:
            results.append(await gen.__anext__())
    except StopAsyncIteration:
        pass
    return results


def clean_db():
    db.init_db()
    conn = sqlite3.connect(db.db_path())
    try:
        for t in ("players", "player_groups", "inventory", "quests", "battle_state",
                  "achievements", "stats", "feedback", "market", "bestiary",
                  "guilds", "guild_members", "party", "pets", "pet_dex", "reputation",
                  "signin", "fishing", "visited", "world_event", "event_state",
                  "professions", "props_use"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    finally:
        conn.close()


passed = failed = 0
from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

def set_roll_fish(m, fish):
    # 打桩落点 = 包内真源模块 `content.fishing`（`content/facade.py::_NAME_SRC` 直指它）
    import content.fishing as _fm
    m._roll_fish_orig = _fm.roll_fish
    _fm.roll_fish = lambda lv, spot=None, bait=None: fish

def restore_roll_fish(m):
    import content.fishing as _fm
    _fm.roll_fish = m._roll_fish_orig

def set_roll_collect(m, cf):
    import content.fishing as _fm
    m._roll_cf_orig = _fm.roll_collect_fish
    _fm.roll_collect_fish = lambda spot, night=False: cf

def restore_roll_collect(m):
    import content.fishing as _fm
    _fm.roll_collect_fish = m._roll_cf_orig

def fish_dict(name, quality, ftype="鱼", price=12):
    return {"name": name, "quality": quality, "type": ftype, "price": price,
            "spots": None, "weight": 1, "desc": "测试渔获"}

def gold_of(gid, qid):
    return db.get_player(gid, qid)["gold"]

async def main():
    clean_db()
    m = Main(None)
    # w1：主力垂钓+烹饪；w3：采集；w4：挖掘
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    # v130.7 意见#29 重名检查：职业格式（注册 <职业> <名字> <性别>），三玩家须不同名
    await cmd(m, "register", "g1", "w3", "注册 战士 采风 男")
    await cmd(m, "register", "g1", "w4", "注册 战士 铁锤 男")
    db.update_player("g1", "w1", apprentices=["fishing", "cooking"], level=20, gold=5000,
                     cur_map="oak_plain", cur_subarea="oak_plain_3")
    db.activate_prof("g1", "w1", "fishing")
    db.activate_prof("g1", "w1", "cooking")
    db.add_prof_exp("g1", "w1", "fishing", 200)   # Lv.5
    db.add_prof_exp("g1", "w1", "cooking", 500)   # Lv.6（v152 阶段重排：夜光鲛汤需 Lv.6，曲线 need=5lv²+15lv 累计 500）
    db.update_player("g1", "w3", apprentices=["gather"], level=10, gold=5000,
                     cur_map="emerald_forest", cur_subarea="")
    db.activate_prof("g1", "w3", "gather")
    db.add_prof_exp("g1", "w3", "gather", 200)    # Lv.5
    db.update_player("g1", "w4", apprentices=["mining"], level=10, gold=5000,
                     cur_map="hill_mine", cur_subarea="")
    db.activate_prof("g1", "w4", "mining")
    db.add_prof_exp("g1", "w4", "mining", 200)    # Lv.5

    print("【1 P1-1 星骸遗鳞：采集池移除 + 历史采集版可回收】")
    pool = [mid for mid, _w in C.GATHER_MAP_POOLS.get("starlake", [])]
    check("星语湖采集池不再产出 mat_star_remnant", "mat_star_remnant" not in pool, str(pool))
    check("星语湖采集池仍保留其他 4 种采集物", len(pool) == 4, str(pool))
    # 历史采集版（v98.1 时期入包 type 被写死为"材料"）→ 按名兜底仍可 1 金回收
    db.add_item("g1", "w1", "mat_star_remnant",
                {"name": "星骸遗鳞", "type": "材料", "stackable": True, "price": 1})
    db.update_player("g1", "w1", cur_map="dawn_city", cur_subarea="dawn_city_5")
    g0 = gold_of("g1", "w1")
    out = await cmd(m, "sell", "g1", "w1", "出售 星骸遗鳞")
    check("历史采集版星骸遗鳞可出售（旧 bug 0 金卖不掉永久占包）", "你出售了 星骸遗鳞" in out, out[:200])
    check("按 1 金币原价回收（0.8 折 int(0.8)=0 的旧路径不再命中）",
          gold_of("g1", "w1") == g0 + 1, f"{g0} -> {gold_of('g1','w1')}")

    print("【2 P1-2 等待中重复指令不白扣体力（垂钓/采集/挖掘）】")
    # 垂钓：第一次开轮扣 5，等待中重复不扣
    db.update_player("g1", "w1", cur_map="oak_plain", cur_subarea="oak_plain_3")
    m._prof_wait_clear("g1", "w1")
    out1 = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("首次垂钓开启等待轮", "抛出鱼竿" in out1 and "秒后完成" in out1, out1[:200])
    st_after1 = db.get_player("g1", "w1")["stamina"]
    out2 = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("等待中重复垂钓提示剩余秒数", "你还在垂钓呢" in out2, out2[:200])
    check("重复垂钓不扣体力", db.get_player("g1", "w1")["stamina"] == st_after1,
          f"{st_after1} -> {db.get_player('g1','w1')['stamina']}")
    m._prof_wait_clear("g1", "w1")
    # 采集
    out1 = await cmd(m, "gather", "g1", "w3", "采集")
    check("首次采集开启等待轮", "开始采集" in out1, out1[:200])
    st_after1 = db.get_player("g1", "w3")["stamina"]
    out2 = await cmd(m, "gather", "g1", "w3", "采集")
    check("等待中重复采集提示剩余秒数", "你还在采集呢" in out2, out2[:200])
    check("重复采集不扣体力", db.get_player("g1", "w3")["stamina"] == st_after1,
          f"{st_after1} -> {db.get_player('g1','w3')['stamina']}")
    m._prof_wait_clear("g1", "w3")
    # 挖掘
    out1 = await cmd(m, "mining", "g1", "w4", "挖掘")
    check("首次挖掘开启等待轮", "举起镐子" in out1, out1[:200])
    st_after1 = db.get_player("g1", "w4")["stamina"]
    out2 = await cmd(m, "mining", "g1", "w4", "挖掘")
    check("等待中重复挖掘提示剩余秒数", "你还在挖掘呢" in out2, out2[:200])
    check("重复挖掘不扣体力", db.get_player("g1", "w4")["stamina"] == st_after1,
          f"{st_after1} -> {db.get_player('g1','w4')['stamina']}")
    m._prof_wait_clear("g1", "w4")

    print("【3 P2-1 传说档全服广播（鱼王 + 古代鱼骨）】")
    calls = []
    async def fake_broadcast(text, exclude_group=None):
        calls.append(text)
    m._broadcast = fake_broadcast
    db.update_player("g1", "w1", cur_map="oak_plain", cur_subarea="oak_plain_3")
    # 鱼王
    set_roll_fish(m, fish_dict("鱼王·翡翠巨龙", "orange", "鱼王", 500))
    m._settle_fishing("g1", "w1", {"spot": "铁港码头", "spot_map": "harbor_docks"})
    restore_roll_fish(m)
    await asyncio.sleep(0.05)
    check("鱼王触发全服广播", any("鱼王·翡翠巨龙" in t and "玩家" in t for t in calls), str(calls))
    # 古代鱼骨
    calls.clear()
    set_roll_fish(m, fish_dict("古代鱼骨", "orange", "材料", 200))
    m._settle_fishing("g1", "w1", {"spot": "铁港码头", "spot_map": "harbor_docks"})
    restore_roll_fish(m)
    await asyncio.sleep(0.05)
    check("古代鱼骨触发全服广播", any("古代鱼骨" in t for t in calls), str(calls))
    # 普通渔获静默
    calls.clear()
    set_roll_fish(m, fish_dict("银鳞鱼", "white"))
    m._settle_fishing("g1", "w1", {"spot": "橡木溪流", "spot_map": "oak_plain"})
    restore_roll_fish(m)
    await asyncio.sleep(0.05)
    check("普通渔获不广播（史诗静默防刷屏）", not calls, str(calls))

    print("【4 P2-2 夜光鲛消费点（烹饪配方落地）】")
    r = C.COOKING_RECIPES.get("cook_glow_shark_soup")
    check("夜光鲛汤配方存在", bool(r) and r["name"] == "夜光鲛汤", str(r))
    check("配方消费 mat_ye_guang_jiao×2", bool(r) and r["cost"].get("mat_ye_guang_jiao") == 2, str(r))
    check("成品 i_glow_shark_soup 定义存在", "i_glow_shark_soup" in C.ITEMS)
    db.add_item("g1", "w1", "mat_ye_guang_jiao",
                {"name": "夜光鲛", "type": "材料", "stackable": True, "price": 35}, count=2)
    out = await cmd(m, "cooking", "g1", "w1", "烹饪 夜光鲛汤")
    check("烹饪夜光鲛汤成功", "烹饪成功" in out and "夜光鲛汤" in out, out[:300])
    check("夜光鲛材料被消耗（断链修复）", db.count_item("g1", "w1", "mat_ye_guang_jiao") == 0)
    check("成品入包", db.count_item("g1", "w1", "i_glow_shark_soup") >= 1)

    print("【5 P2-3 图鉴收藏永久化（出售后不回退）】")
    # 真实钓获路径解锁月华水母成就（先清背包防干扰）
    for it in db.get_inventory("g1", "w1"):
        if it["key"] == "mat_moon_jelly":
            db.remove_item("g1", "w1", it["key"], it["count"])
    player = db.get_player("g1", "w1")
    set_roll_collect(m, C.FISH_COLLECT[1])  # 月华水母
    set_roll_fish(m, fish_dict("银鳞鱼", "white"))
    out = m._settle_fishing("g1", "w1", {"spot": "橡木溪流", "spot_map": "oak_plain"})
    restore_roll_fish(m)
    restore_roll_collect(m)
    check("钓获月华水母入包", db.count_item("g1", "w1", "mat_moon_jelly") >= 1, out[:300])
    # 出售 → 背包清空
    db.update_player("g1", "w1", cur_map="dawn_city", cur_subarea="dawn_city_5")
    out = await cmd(m, "sell", "g1", "w1", "出售 月华水母")
    check("月华水母出售成功", "你出售了 月华水母" in out, out[:200])
    check("出售后背包已空", db.count_item("g1", "w1", "mat_moon_jelly") == 0)
    out = await cmd(m, "bestiary", "g1", "w1", "图鉴")
    check("出售后图鉴仍显示已收藏（旧 bug 图鉴回退）", "✅ 月华水母" in out, out[:400])

    print("【6 P2-4 鱼饵 24h 过期】")
    db.update_player("g1", "w1", cur_map="oak_plain", cur_subarea="oak_plain_3")
    # 过期鱼饵（挂饵 25h 前）→ 不生效且清除
    db.set_event_state("bait_w1", json.dumps({"kind": "glow", "ts": time.time() - 90000}))
    set_roll_fish(m, fish_dict("银鳞鱼", "white"))
    out = m._settle_fishing("g1", "w1", {"spot": "橡木溪流", "spot_map": "oak_plain"})
    restore_roll_fish(m)
    check("过期鱼饵不生效", "鱼饵【萤光鱼饵】生效了" not in out, out[:300])
    check("过期鱼饵状态被清除", not db.get_event_state("bait_w1"))
    # 新鲜鱼饵 → 正常生效
    db.set_event_state("bait_w1", json.dumps({"kind": "glow", "ts": time.time()}))
    set_roll_fish(m, fish_dict("银鳞鱼", "white"))
    out = m._settle_fishing("g1", "w1", {"spot": "橡木溪流", "spot_map": "oak_plain"})
    restore_roll_fish(m)
    check("新鲜鱼饵正常生效", "鱼饵【萤光鱼饵】生效了" in out, out[:300])
    check("鱼饵一次性消耗", not db.get_event_state("bait_w1"))

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
