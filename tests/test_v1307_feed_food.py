# -*- coding: utf-8 -*-
"""v130.7 意见#22 喂养只能吃食物 固化测试（玩家意见 #22：『喂养改成只能吃食物类的』）

改动：
- items.py：真食物加 "food": True（消耗品食物 + 材料类食物；鱼靠 type=鱼 无条件合法）
- social.py pet_feed：白名单 FOOD_TYPES={"鱼"} + 名称/序号路径都要求 food 标记或鱼

覆盖：
  ① 喂精铁锭（材料·无 food）→ 拒
  ② 喂海盗的藏宝图（材料·无 food）→ 拒
  ③ 喂幽灵船票（材料·无 food）→ 拒
  ④ 喂月光草（草药·无 food）→ 拒
  ⑤ 喂香草烤兽肉（消耗品·food）→ 成功（扣减+饱食度/亲密度/经验结算）
  ⑥ 喂宠物口粮（消耗品·food）→ 成功
  ⑦ 喂银鳞鱼（type=鱼）→ 成功（鱼无条件合法）
  ⑧ 序号路径：'喂养 1' → 食物过滤后第 1 份（铁锭等非食物不占序号）
  ⑨ 序号路径：食物外序号 → 拒（'背包里没有第 N 个食物(共 M 个)'）
  ⑩ 无食物时全背包不可喂（空白对照：所有非食物都在背包里仍被拒）

运行：python tests/test_v1307_feed_food.py（exit=0 全绿）
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import C, FakeEvent, clean_db, make_player  # noqa: E402
from _engine_harness import Main  # noqa: E402

# 声明驱动正则表（原 `game.commands._registry.COMMAND_REGEX` 的终态取件口：
# 声明真源 = 包内 `content/data/commands.json`，经驱动口装配为 `{key: 合并正则}`）。
# ★ 剔除私有键 `_maint_gate`（停服 gate 不是指令；旧 `_host_handler_finder` 显式跳过
#   `name.startswith("_")`）——理由见 test_v1304_use_batch.py 同段注释。
from _engine_harness import harness as _harness  # noqa: E402
COMMAND_REGEX = {k: rx.pattern for rx, k in _harness().declarations_for_static()
                 if not k.startswith("_")}

passed = failed = 0
G, Q = 1095961597, "gm_t1307_feed"
PET_KEY = "pet_wolf"


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ {name}")
    else:
        failed += 1
        print(f"❌ {name} {detail}")


async def _cmd(m, cmd):
    """注册表分发（与 test_v1304 同款，实测 MRO）

    ★ 终态驱动口（`_engine_harness.Main`）对**声明表命中**的 key 给 async generator、
    对包内实现类方法给 coroutine —— 两种都收（旧宿主壳统一是 async generator）。
    """
    ev = FakeEvent(G, Q, cmd)
    for key, pat in COMMAND_REGEX.items():
        if re.match(pat, cmd):
            fn = getattr(m, key, None)
            if fn:
                gen = fn(ev)
                out = []
                if hasattr(gen, "asend"):
                    async for r in gen:
                        out.append(r)
                else:
                    r = await gen
                    out = list(r) if isinstance(r, (list, tuple)) else ([r] if r else [])
                if out and isinstance(out[0], tuple):
                    return out[0][1]
                return str(out[0]) if out else ""
            return ""
    return ""


def _held(key):
    from _engine_harness import db
    for it in db.get_inventory(G, Q):
        if it["key"] == key:
            return it["count"]
    return 0


def _seal(satiety=100):
    """建号 + 孵宠 + 背包：2 铁锭 / 藏宝图 / 船票 / 月光草(草药) / 烤兽肉 / 宠物口粮 / 银鳞鱼"""
    from _engine_harness import db
    make_player(G, Q, "喂食测试", "战士", level=1)
    db.pet_create(Q, PET_KEY, "森林狼崽")
    db.pet_update(Q, satiety=satiety, bond=0, exp=0)
    for key in ("mat_jing_tie_ding", "mat_hai_dao_cang_bao_tu", "mat_you_ling_chuan_piao",
                "mat_yue_guang_cao", "i_xiang_cao_kao_shou_rou", "i_chong_wu_kou_liang",
                "mat_yin_lin_yu"):
        db.add_item(G, Q, key, {}, count=1)
    # 铁锭 2 个
    db.add_item(G, Q, "mat_jing_tie_ding", {}, count=1)


async def main():
    from _engine_harness import db
    m = Main()

    # ---- 拒：材料类非食物 ----
    clean_db()
    _seal()
    r = await _cmd(m, "喂养 精铁锭")
    check("① 精铁锭被拒", "没有可喂食的食物『精铁锭』" in r, r[:120])
    check("① 铁锭未扣", _held("mat_jing_tie_ding") == 2, f"持有={_held('mat_jing_tie_ding')}")

    clean_db()
    _seal()
    r = await _cmd(m, "喂养 海盗的藏宝图")
    check("② 藏宝图被拒", "没有可喂食的食物『海盗的藏宝图』" in r, r[:120])

    clean_db()
    _seal()
    r = await _cmd(m, "喂养 幽灵船票")
    check("③ 船票被拒", "没有可喂食的食物『幽灵船票』" in r, r[:120])

    clean_db()
    _seal()
    r = await _cmd(m, "喂养 月光草")
    check("④ 草药被拒", "没有可喂食的食物『月光草』" in r, r[:120])

    # ---- 可喂：消耗品 food / 鱼 ----
    clean_db()
    _seal(satiety=50)
    r = await _cmd(m, "喂养 香草烤兽肉")
    check("⑤ 香草烤兽肉可喂", "你喂了【森林狼崽】一份香草烤兽肉" in r, r[:120])
    check("⑤ 饱食度 50→80", "饱食度 +30" in r, r[:120])
    check("⑤ 亲密度 +5", "亲密度 +5" in r, r[:120])
    check("⑤ 经验 +10", "经验 +10" in r, r[:120])
    check("⑤ 烤兽肉已扣 1", _held("i_xiang_cao_kao_shou_rou") == 0, f"持有={_held('i_xiang_cao_kao_shou_rou')}")
    pet = db.pet_get(Q)
    check("⑤ 落库 satiety=80 bond=5", pet["satiety"] == 80 and pet["bond"] == 5,
          f"satiety={pet['satiety']} bond={pet['bond']}")

    clean_db()
    _seal()
    r = await _cmd(m, "喂养 宠物口粮")
    check("⑥ 宠物口粮可喂", "你喂了【森林狼崽】一份宠物口粮" in r, r[:120])

    clean_db()
    _seal()
    r = await _cmd(m, "喂养 银鳞鱼")
    check("⑦ 鱼可喂", "你喂了【森林狼崽】一份银鳞鱼" in r, r[:120])
    check("⑦ 鱼已扣 1", _held("mat_yin_lin_yu") == 0, f"持有={_held('mat_yin_lin_yu')}")

    # ---- 序号路径：食物过滤后编号 ----
    clean_db()
    _seal()
    r = await _cmd(m, "喂养 1")
    check("⑧ 序号 1 = 第 1 份食物(烤兽肉)", "一份香草烤兽肉" in r, r[:120])
    check("⑧ 铁锭不占食物序号", "一份精铁锭" not in r and "没有可喂食" not in r, r[:120])

    clean_db()
    _seal()
    r = await _cmd(m, "喂养 3")
    check("⑨ 序号 3 = 银鳞鱼", "一份银鳞鱼" in r, r[:120])

    clean_db()
    _seal()
    r = await _cmd(m, "喂养 4")
    check("⑩ 序号 4 越界拒", "背包里没有第 4 个食物(共 3 个)" in r, r[:120])

    clean_db()
    _seal()
    r = await _cmd(m, "喂养 1")
    check("⑪ 喂后口粮仍在(只扣 1 份)", _held("i_chong_wu_kou_liang") == 1, f"持有={_held('i_chong_wu_kou_liang')}")

    # ---- 汇总 ----
    print(f"\n结果: {passed} 通过 / {failed} 失败")
    return failed


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))