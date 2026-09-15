# -*- coding: utf-8 -*-
"""v47 测试重构：commands 层（QQ 交互薄层冒烟）

验证重构后的命令装配（Main Mixin）与核心流程：
  1. 注册 → 角色 → 地图 → 探索 → 攻击 全链路
  2. 背包 / 锻造 / 商店 基础命令
  3. 帮助指令含 6 大 Mixin 的命令
  4. 快捷指令静态表回退（test_v14 核心场景）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import FakeEvent, run, clean_db, Main, db

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
    """执行命令并返回最后一条回复文本"""
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""


async def main():
    m = Main(None)
    clean_db()
    print("【commands 层：注册→角色→探索→攻击 全链路】")
    out = await cmd(m, "register", "g1", "q1", "注册 战士 格温 男")
    check("注册成功", "注册成功" in out or "战士" in out, out[:80])
    out = await cmd(m, "profile", "g1", "q1", "角色")
    check("角色显示", "格温" in out and "战士" in out, out[:80])
    out = await cmd(m, "map_view", "g1", "q1", "地图")
    check("地图显示", "橡木" in out or "地图" in out, out[:80])
    out = await cmd(m, "explore", "g1", "q1", "探索")
    check("探索有返回", len(out) > 10, out[:80])
    out = await cmd(m, "attack", "g1", "q1", "攻击")
    check("攻击有返回", len(out) > 10, out[:80])

    print("【commands 层：背包/锻造/商店】")
    out = await cmd(m, "inventory", "g1", "q1", "背包")
    check("背包显示", "背包" in out or "空" in out or "狼皮" in out, out[:80])
    out = await cmd(m, "craft", "g1", "q1", "锻造")
    check("锻造显示", "铁匠" in out or "锻造" in out or "配方" in out, out[:80])
    out = await cmd(m, "shop", "g1", "q1", "商店")
    check("商店显示", "商店" in out or "购买" in out, out[:80])
    # v87.17 设施子区域绑定：广场没商店被拦，到商店子区域才能打开
    # v92 #28 铁匠铺改造：oak_town_3=老铁铁匠铺 → 卖武器+锻造材料（铁矿石），不再卖治疗药水
    db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_3")
    out = await cmd(m, "shop", "g1", "q1", "商店")
    check("商店子区域可打开", "商店" in out and "铁矿石" in out, out[:120])

    print("【commands 层：帮助含各 Mixin】")
    out = await cmd(m, "help_cmd", "g1", "q1", "帮助")
    # v114.6 帮助主面板只排系统标题，不展开详细指令
    for section in ("角色系统", "冒险系统", "战斗系统", "技能系统", "副业系统",
                    "物品系统", "社交系统", "世界系统"):
        check(f"帮助含『{section}』", section in out, out[:200])

    print("【commands 层：快捷指令静态表回退】")
    # 绑定后数字触发
    out = await cmd(m, "shortcut", "g1", "q1", "快捷绑定 1 探索")
    check("快捷绑定成功", "绑定成功" in out, out[:80])
    out = await cmd(m, "shortcut_trigger", "g1", "q1", "1")
    check("发1=探索（静态回退）", "❌" not in out and len(out) > 10, out[:100])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
