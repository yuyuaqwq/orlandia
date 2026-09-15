# -*- coding: utf-8 -*-
"""v96 GM 系统验证：停服/开服 + GM 白名单 + 全套 GM 指令

覆盖：
  1. 停服 gate：非 GM 游戏指令被拦、GM(gm_ 测试身份/白名单)放行、日常聊天不拦
  2. gm_停服 / gm_开服 / gm_状态 / gm_广播
  3. gm_查询 / gm_玩家 / gm_发金币 / gm_发物品 / gm_发经验 / gm_设等级
  4. gm_传送 / gm_体力 / gm_改名 / gm_加GM / gm_删GM
  5. 非 GM 使用 GM 指令被拒
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail).encode('utf-8', 'replace').decode('utf-8', 'replace')[:300]}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

# FakeEvent 补 stop_event（gate 测试用）
def _fake_stop(self):
    self._stopped = True
FakeEvent.stop_event = _fake_stop

async def main():
    clean_db()
    m = Main(None)
    # 预置 GM 白名单：鱼鱼 QQ
    db.set_event_state("gm_whitelist", json.dumps(["1454832774"], ensure_ascii=False))

    print("【1. 停服 gate 过滤】")
    from _engine_harness import GameCmdFilter as _GameCmdFilter
    gf = _GameCmdFilter()
    check("『探索』命中游戏指令", gf.filter(FakeEvent("g1", "w1", "探索"), None) is True)
    check("『地图』命中", gf.filter(FakeEvent("g1", "w1", "地图"), None) is True)
    check("『注册 战士 xx』命中", gf.filter(FakeEvent("g1", "w1", "注册 战士 小明 男"), None) is True)
    check("日常聊天不命中", gf.filter(FakeEvent("g1", "w1", "今天天气不错啊"), None) is False)
    check("带At前缀命中", gf.filter(FakeEvent("g1", "w1", "[At:123] 探索"), None) is True)

    print("【2. 停服状态下的 gate 行为】")
    db.set_event_state("server_maintenance", "1")
    db.set_event_state("server_maintenance_msg", "例行维护")

    ev = FakeEvent("g1", "w1", "探索")
    results = await run(m._maint_gate, ev)
    # v134.7：停服非 GM 静默 stop 不产出结果（不再回维护提示）；断言事件被 stop
    check("非 GM 被拦(事件 stop)", getattr(ev, "_stopped", False) is True, str(results))
    check("非 GM 事件被 stop", getattr(ev, "_stopped", False) is True)

    ev = FakeEvent("g1", "gm_playtest", "探索")
    results = await run(m._maint_gate, ev)
    check("gm_playtest 放行(无输出)", len(results) == 0 and not getattr(ev, "_stopped", False), str(results))

    ev = FakeEvent("g1", "gm_alt2", "探索")
    results = await run(m._maint_gate, ev)
    check("gm_alt 测试号放行", len(results) == 0 and not getattr(ev, "_stopped", False), str(results))

    ev = FakeEvent("g1", "1454832774", "探索")
    results = await run(m._maint_gate, ev)
    check("白名单 GM 放行", len(results) == 0 and not getattr(ev, "_stopped", False), str(results))

    ev = FakeEvent("g1", "w1", "今天天气不错")
    results = await run(m._maint_gate, ev)
    # 说明：直接调 handler 会绕过 AstrBot 的 filter 机制；日常聊天不命中
    # _GameCmdFilter 已在【1】验证。此处在停服+非GM下直接调 handler 应被拦(模拟 filter 已过)。
    # v134.7：停服静默 stop 不产出结果 → 断言事件被 stop
    check("日常聊天直接调 handler 也被拦(模拟filter已过)", getattr(ev, "_stopped", False) is True, str(results))

    print("【3. gm_停服 / gm_开服 / gm_状态】")
    out = await cmd(m, "gm_maintenance", "g1", "1454832774", "gm_停服 版本更新")
    check("停服成功", "已停服" in out and db.get_event_state("server_maintenance") == "1", out[:200])
    check("公告已存", db.get_event_state("server_maintenance_msg") == "版本更新")

    out = await cmd(m, "gm_status", "g1", "1454832774", "gm_状态")
    check("状态显示维护中", "维护中" in out and "GM" in out, out[:300])
    check("状态显示鱼鱼", "1454832774" in out, out[:300])

    out = await cmd(m, "gm_open", "g1", "1454832774", "gm_开服")
    check("开服成功", "已开服" in out and db.get_event_state("server_maintenance") is None, out[:200])

    out = await cmd(m, "gm_open", "g1", "1454832774", "gm_开服")
    check("重复开服提示", "运行中" in out, out[:200])

    ev = FakeEvent("g1", "w1", "探索")
    results = await run(m._maint_gate, ev)
    check("开服后非 GM 放行", len(results) == 0 and not getattr(ev, "_stopped", False), str(results))

    print("【4. 玩家查询】")
    await cmd(m, "register", "g1", "w1", "注册 战士 测试员 男")
    db.update_player("g1", "w1", level=5, gold=300, cur_map="ironharbor", cur_subarea="ironharbor_1")
    out = await cmd(m, "gm_query", "g1", "1454832774", "gm_查询 w1")
    check("按 QQ 查详情", "测试员" in out and "Lv.5" in out and "300" in out, out[:300])
    check("位置显示", "铁港城" in out, out[:300])
    out = await cmd(m, "gm_query", "g1", "1454832774", "gm_查询 测试员")
    check("按名字查", "测试员" in out, out[:300])
    out = await cmd(m, "gm_query", "g1", "1454832774", "gm_查询 不存在的名字")
    check("查无此人提示", "没有找到" in out, out[:200])

    out = await cmd(m, "gm_players", "g1", "1454832774", "gm_玩家")
    check("玩家列表", "测试员" in out and "Lv." in out and "金币300" in out, out[:300])
    out = await cmd(m, "gm_players", "g1", "1454832774", "gm_玩家 测试")
    check("列表关键词", "测试员" in out, out[:300])

    print("【5. 玩家操作】")
    out = await cmd(m, "gm_give_gold", "g1", "1454832774", "gm_发金币 w1 500")
    check("发金币", "500" in out and db.get_player("g1", "w1")["gold"] == 800, out[:200])

    out = await cmd(m, "gm_give_item", "g1", "1454832774", "gm_发物品 w1 治疗药水(中) 3")
    check("发物品", "治疗药水(中)" in out, out[:200])
    inv = db.get_inventory("g1", "w1")
    pot = [i for i in inv if "治疗药水(中)" in i["data"]["name"]]
    check("背包 3 瓶", sum(i["count"] for i in pot) == 3, str([(i["data"]["name"], i["count"]) for i in inv]))

    out = await cmd(m, "gm_give_item", "g1", "1454832774", "gm_发物品 w1 不存在的东西 1")
    check("物品不存在提示", "找不到" in out, out[:200])

    out = await cmd(m, "gm_give_exp", "g1", "1454832774", "gm_发经验 w1 100")
    check("发经验", "100" in out and db.get_player("g1", "w1")["exp"] == 100, out[:200])

    out = await cmd(m, "gm_set_level", "g1", "1454832774", "gm_设等级 w1 10")
    p = db.get_player("g1", "w1")
    check("设等级", "Lv.10" in out and p["level"] == 10, out[:200])
    check("血蓝按新等级重算回满", p["hp"] == p["max_hp"] and p["max_hp"] > 100, f"hp={p['hp']}/{p['max_hp']}")
    check("经验清零", p["exp"] == 0, f"exp={p['exp']}")

    out = await cmd(m, "gm_teleport", "g1", "1454832774", "gm_传送 w1 橡木镇")
    check("传送", "橡木镇" in out and db.get_player("g1", "w1")["cur_map"] == "oak_town", out[:200])
    out = await cmd(m, "gm_teleport", "g1", "1454832774", "gm_传送 w1 不存在的图")
    check("地图不存在提示", "找不到地图" in out, out[:200])

    out = await cmd(m, "gm_stamina", "g1", "1454832774", "gm_体力 w1")
    p = db.get_player("g1", "w1")
    check("体力回满", "回满" not in out and p["stamina"] == 100 + p["level"] * 2, f"stamina={p['stamina']}")
    out = await cmd(m, "gm_stamina", "g1", "1454832774", "gm_体力 w1 50")
    check("体力设值", db.get_player("g1", "w1")["stamina"] == 50, f"stamina={db.get_player('g1', 'w1')['stamina']}")

    out = await cmd(m, "gm_rename", "g1", "1454832774", "gm_改名 w1 新名字")
    check("改名", "新名字" in out and db.get_player("g1", "w1")["name"] == "新名字", out[:200])

    print("【6. GM 白名单管理】")
    out = await cmd(m, "gm_add_gm", "g1", "1454832774", "gm_加GM 3588500435")
    wl = json.loads(db.get_event_state("gm_whitelist"))
    check("加 GM", "3588500435" in wl and "已把 QQ 3588500435" in out, out[:200])
    out = await cmd(m, "gm_del_gm", "g1", "1454832774", "gm_删GM 3588500435")
    wl = json.loads(db.get_event_state("gm_whitelist"))
    check("删 GM", "3588500435" not in wl and "移出" in out, out[:200])

    print("【7. 权限与格式校验】")
    out = await cmd(m, "gm_query", "g1", "w1", "gm_查询 测试员")
    check("非 GM 被拒", "仅限管理员" in out, out[:200])
    out = await cmd(m, "gm_give_gold", "g1", "1454832774", "gm_发金币 w1")
    check("缺参数提示", "格式" in out, out[:200])
    out = await cmd(m, "gm_rename", "g1", "1454832774", "gm_改名 不存在的人 新名")
    check("目标不存在提示", "没有找到" in out, out[:200])

    print("【8. 广播(空群不炸)】")
    out = await cmd(m, "gm_broadcast", "g1", "1454832774", "gm_广播 全体注意！")
    check("广播执行不报错", "已广播" in out, out[:200])
    out = await cmd(m, "gm_broadcast", "g1", "1454832774", "gm_广播")
    check("广播缺内容提示", "格式" in out, out[:200])

    print("【9. gm_帮助】")
    out = await cmd(m, "gm_help", "g1", "1454832774", "gm_帮助")
    check("帮助含停服/开服/广播", "gm_停服" in out and "gm_开服" in out and "gm_广播" in out, out[:200])
    check("帮助含全部新指令", all(x in out for x in ["gm_查询", "gm_发金币", "gm_发物品", "gm_发经验",
                                                       "gm_设等级", "gm_传送", "gm_体力", "gm_改名",
                                                       "gm_加GM", "gm_删GM", "gm_玩家", "gm_状态"]), "")

    print(f"\n结果：{passed} 通过 / {failed} 失败")
    return 1 if failed else 0

if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
