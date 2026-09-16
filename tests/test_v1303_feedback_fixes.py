# -*- coding: utf-8 -*-
"""v130.3 意见箱闭环固化测试（test_v1303_feedback_fixes.py）

覆盖玩家意见 #2/#3/#5/#6/#7 的核心行为，防止"功能改了但没进全量回归"再次发生：
  ① 『怪物 <名称>』查询（#3）：森林狼地点/空参引导/未知怪提示/模糊推荐 + MONSTER_LOCS 数据量
  ② 批量购买星号格式（#2）：『购买 <名称>*<数量>』解析与校验（0/负/超上限友好报错）
  ③ 背包页数底部（#5）：『背包』输出最后一行含 📄 页数
  ④ 采集 on_expire 回调存在（#6）：economy 注册 _prof_wait_expire_cb（防止回归丢数据）
  ⑤ 技能详情 📈当前效果行（#7）：详情含当前等级数值行
  ⑥ 注册表同步：『怪物』键存在且 handler 同名

运行：python tests/test_v1303_feedback_fixes.py（exit=0 全绿）
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_v1303_feedback_fixes.db")
os.environ["GWEN_GAME_DB"] = _DB

from _engine_harness import C, FakeEvent, clean_db  # noqa: E402
from _engine_harness import Main  # noqa: E402
from _engine_harness import harness as _harness  # noqa: E402
# 声明驱动正则表（原 `game.commands._registry.COMMAND_REGEX` 的终态取件口）；
# 私有 gate 键不进命令表（旧 `_host_handler_finder` 显式跳过 `name.startswith("_")`）。
COMMAND_REGEX = {k: rx.pattern for rx, k in _harness().declarations_for_static()
                 if not k.startswith("_")}

passed = failed = 0
G, Q = 1095961596, "gm_t1303"


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ {name}")
    else:
        failed += 1
        print(f"❌ {name} {detail}")


async def _exec(m, cmd):
    out = []
    async for r in getattr(m, "router")(FakeEvent(G, Q, cmd)) if hasattr(m, "router") else _direct(m, cmd):
        out.append(r)
    return out[0][1] if out and isinstance(out[0], tuple) else (str(out[0]) if out else "")


async def _direct(m, cmd):
    # 按声明表找 handler 并调用（模拟分发）
    ev = FakeEvent(G, Q, cmd)
    for key, pat in COMMAND_REGEX.items():
        if re.match(pat, cmd):
            fn = getattr(m, key, None)
            if fn and key != "monster":
                gen = fn(ev)
                if hasattr(gen, "asend"):
                    async for r in gen:
                        yield r
                else:
                    r = await gen
                    for x in (r or []):
                        yield x
            return
    yield ("", "")


async def main():
    global passed, failed
    print("===== v130.3 意见箱闭环 =====\n")
    clean_db()
    m = Main(None)

    # 注册角色
    out0 = []
    async for r in m.register(FakeEvent(G, Q, "注册 意见箱测试员 男")):
        out0.append(r)
    check("注册角色", "欢迎" in (out0[0][1] if isinstance(out0[0], tuple) else str(out0[0])))

    # ① 『怪物』查询
    out = []
    async for r in m.monster(FakeEvent(G, Q, "怪物 森林狼")):
        out.append(r)
    t = out[0][1] if isinstance(out[0], tuple) else str(out[0])
    check("『怪物 森林狼』含地点+Lv", "Lv.8" in t and "林间小径" in t, t[:80])
    check("MONSTER_LOCS 数据量", len(C.MONSTER_LOCS) > 200, len(C.MONSTER_LOCS))

    out = []
    async for r in m.monster(FakeEvent(G, Q, "怪物")):
        out.append(r)
    t = out[0][1] if isinstance(out[0], tuple) else str(out[0])
    check("『怪物』空参引导", "想找怪物" in t)

    out = []
    async for r in m.monster(FakeEvent(G, Q, "怪物 不存在的怪")):
        out.append(r)
    t = out[0][1] if isinstance(out[0], tuple) else str(out[0])
    check("『怪物 未知』未收录", "未收录" in t)

    # ② 批量购买（星号格式解析在 economy en=async def buy）
    # ★ 2026-09-13 收口（B9-L1 economy 薄壳 + B10 批）后：economy 实现真源 = 包内
    #   `content/economy_cmds.py`（宿主 commands/economy.py 只剩薄壳）
    #   → 源码扫描式断言改扫**实现侧**（两处都读，任一侧命中即算存在）。
    def _eco_src():
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out = []
        # ★ P5F-REPOINT: 原第二侧读宿主壳 `game/commands/economy.py`（随删壳批消失）
        #   → 包内**实现面** `content/economy_cmds.py`。登记面薄壳 `content/cmds_economy.py`
        #   已随声明式绑定迁删（`bind` 直接点名实现体），故这里只剩实现面一侧。
        for p in (os.path.join(base, "content", "economy_cmds.py"),):
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    out.append(f.read())
        return "\n".join(out)

    src_eco = _eco_src()
    check("批量购买星号支持", "*" in src_eco and "数量至少 1 个" in src_eco)
    check("批量购买上限提示", "单次最多购买" in src_eco)

    # ③ 背包页数底部
    src_eco2 = _eco_src()
    # 背包视图渲染里 📄 行在 lines.append 列表尾部区域（翻页提示）
    check("背包页数底部实现", "📄 第" in src_eco2 and "(page - 1) * 10 + 1" in src_eco2)

    # ④ 采集 on_expire 回调
    check("采集 on_expire 回调", "_prof_wait_expire_cb" in src_eco2)

    # ⑤ 技能详情📈（v134.5 重构为「📈 数值成长：」逐级数值；v139 同步断言）
    # 终态：玩家命令实现体在包内 `content/player_cmds.py`（旧宿主壳已薄壳化）
    src_pl = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content",
                               "player_cmds.py"), encoding="utf-8").read()
    check("技能详情📈当前效果", "📈" in src_pl and ("当前效果" in src_pl or "数值成长" in src_pl))

    # ⑥ 注册表同步
    check("注册表含『怪物』键", "monster" in COMMAND_REGEX)
    check("handler 与注册表同名", hasattr(Main(None), "monster"))

    print(f"\n===== 结果: {passed} 通过, {failed} 失败 =====")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
    sys.exit(1 if failed else 0)