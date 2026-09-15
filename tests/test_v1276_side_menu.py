# -*- coding: utf-8 -*-
"""v127.6 支线接取改『多选项自选』：对话 side_menu 动态菜单 + 单条接取 + 预告全量

验证（方案文档 §4）：
  1. 展开数量：玛莎(npc_innkeeper) welcome 含 side_menu 选项时，渲染出 2 个子选项
     （s1 史莱姆果冻 + s111 面包贼蓬尾，按 SIDE_QUESTS 顺序）
  2. 单接：点其中一项 → player side 只有 s1，没有 s111
  3. 隔离：再点 s111 → 两条都在，各自独立；无可接后菜单消失
  4. after：接完 next 指向 side_menu.after（玛莎配 welcome → 返回 welcome 连串接）
  5. 预告全量：对话前引导输出两条『可接取』，不再只 1 条
  6. 单支线 NPC 不破坏：镇长(npc_mayor) 对话树不含 side_menu 键 → 原行为不变（回归）

说明（数据契约）：game/data/dialogues.py 由数据同事另行修改（§2：玛莎『有活儿要交给我吗』
选项 action 换成 side_menu 键，after=welcome）。本测试在运行时对该选项做幂等内存注入，
镜像那份数据契约，避免本文件改动数据文件、并保证与数据合并顺序无关。
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

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


def apply_v1276_data_patch():
    """幂等注入 §2 数据契约：玛莎 welcome 的『有活儿要交给我吗』→ side_menu {after: welcome}。

    数据同事在 game/data/dialogues.py 落地同一内容；此处运行时内存注入保证测试
    与数据合并顺序无关（重复执行结果一致，合并后为无害 no-op）。
    """
    dlg = C.DIALOGUES.get("npc_innkeeper") or {}
    for node in dlg.get("nodes", {}).values():
        for opt in node.get("options", []):
            if opt.get("text") == "📜 有活儿要交给我吗？":
                opt["side_menu"] = {"after": "welcome"}
                opt.pop("action", None)


def opt_no(out, substr):
    """从渲染输出中解析某选项的序号（动态定位，不硬编码序号）。"""
    for line in out.splitlines():
        mm = re.match(r"(\d+)\. (.*)", line)
        if mm and substr in mm.group(2):
            return int(mm.group(1))
    return None


async def main():
    clean_db()
    m = Main(None)
    apply_v1276_data_patch()

    print("【v127.6 side_menu 自选接取：前置】")
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", level=5, gold=1000, cur_map="oak_town", cur_subarea="oak_town_4")

    print("【v127.6 用例1+5：展开数量 / 预告全量】")
    out = await cmd(m, "find_npc", "g1", "w1", "找 玛莎")
    check("1:渲染出 s1 史莱姆果冻 子选项", "📜 接『史莱姆果冻』" in out, out[:300])
    check("1:渲染出 s111 面包贼蓬尾 子选项", "📜 接『面包贼蓬尾』" in out, out[:300])
    check("1:子选项共 2 条", out.count("📜 接『") == 2, out[:300])
    check("1:旧单选项『有活儿要交给我吗』不再出现", "有活儿要交给我吗" not in out, out[:300])
    check("5:预告含 史莱姆果冻 可接取", "📜 支线『史莱姆果冻』可接取" in out, out[:300])
    check("5:预告含 面包贼蓬尾 可接取", "📜 支线『面包贼蓬尾』可接取" in out, out[:300])
    check("5:预告共 2 条（不再 break 只显 1 条）",
          len(re.findall(r"📜 支线『.*?』可接取", out)) == 2, out[:300])

    n1 = opt_no(out, "接『史莱姆果冻』")
    n2 = opt_no(out, "接『面包贼蓬尾』")
    check("前置:解析出两个子选项序号", n1 is not None and n2 is not None, f"n1={n1}, n2={n2}")

    print("【v127.6 用例2+4：单接 s1 / after 返回 welcome】")
    out1 = await cmd(m, "talk_choice", "g1", "w1", str(n1))
    check("1:接取成功提示", "史莱姆果冻" in out1 and "🎯 目标" in out1, out1[:300])
    side1 = db.get_quests("g1", "w1").get("side") or {}
    check("2:单接后 side 只有 s1", set(side1) == {"s1"}, str(side1))
    check("2:未连带接 s111", "s111" not in side1, str(side1))
    check("4:after=welcome 返回欢迎台词", "累了吧？" in out1, out1[:200])
    check("4:会话未结束（连串接），菜单仍在", "0. 结束对话" in out1, out1[:300])
    check("4:未走 __end__ 散场", "那就再会了" not in out1, out1[:200])

    print("【v127.6 用例3：再接 s111 隔离生效】")
    out2 = await cmd(m, "find_npc", "g1", "w1", "找 玛莎")
    n2b = opt_no(out2, "接『面包贼蓬尾』")
    check("3:重入后 s111 项可再选", n2b is not None, out2[:300])
    out2b = await cmd(m, "talk_choice", "g1", "w1", str(n2b))
    check("3:接 s111 成功提示", "面包贼蓬尾" in out2b and "🎯 目标" in out2b, out2b[:300])
    side2 = db.get_quests("g1", "w1").get("side") or {}
    check("3:两条都在,s1 保留", side2.get("s1", {}).get("status") == "active", str(side2))
    check("3:两条都在,s111 独立接取", side2.get("s111", {}).get("status") == "active", str(side2))
    out3 = await cmd(m, "find_npc", "g1", "w1", "找 玛莎")
    check("1:a无任何可接支线→菜单不出现", "📜 接『" not in out3, out3[:300])

    print("【v127.6 用例6：单支线 NPC（镇长）不破坏】")
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
    out_m = await cmd(m, "find_npc", "g1", "w1", "找 镇长")
    check("6:镇长无 side_menu,原选项保留", "有活儿要交给我吗" in out_m, out_m[:300])
    check("6:镇长不被展开（无 📜 接『）", "📜 接『" not in out_m, out_m[:300])
    nm = opt_no(out_m, "有活儿要交给我吗")
    out_m2 = await cmd(m, "talk_choice", "g1", "w1", str(nm)) if nm else ""
    check("6:镇长 side_offer 全接路径仍可用", "迷路的商人" in out_m2, out_m2[:300])
    sideM = db.get_quests("g1", "w1").get("side") or {}
    check("6:镇长 s2 被接取（回归：全接行为不变）",
          sideM.get("s2", {}).get("status") == "active", str(sideM))
    check("6:镇长接取不影响玛莎已接支线",
          "s1" in sideM and "s111" in sideM, str(sideM))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
