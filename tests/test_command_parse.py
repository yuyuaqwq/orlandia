# -*- coding: utf-8 -*-
"""命令解析域：正则互斥 / 免空格 / 序号 / 分页 / 命令矩阵（源自 test_regex/test_nospace/test_move_num/v81/v84/v86/v87/v91）

验证：
  1. 命令矩阵互斥性：任意两个 handler 不得同时命中不同命令（防双触发）
  2. 免空格触发：『背包材料』『宠物改名小黑』『公会签到5』等
  3. 序号分流：『物品详情1』只走物品详情，『背包2』只走背包
  4. 翻页：『列表2』等
  5. 移动序号：『移动 2』按邻居列表
"""
import sys, os, re, glob
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


# ---------- 命令正则扫描：走共享 helper（tests/_cmd_registry.py，**唯一实现**）----------
# 2026-09-12 v185 指令表迁移（路线图 #9）：本文件原先自带一份「只认 @filter.regex 字面量」的
# 扫描实现 → 一批指令迁到声明表（@declared）后，它们**整体掉出正则池**，用例当场变红
# （实测：『宠物改名小黑』/『公会签到5』/『公会任务』3 例命中 []）。改为走 helper：
# 两种装饰器写法（@filter.regex 字面量 / @declared 声明）都认，扫描实现只此一处。
from _cmd_registry import pattern_map as _pattern_map  # noqa: E402

handlers = [(pat, name) for name, pat in _pattern_map().items() if name != "_maint_gate"]
# `_maint_gate`（base.py:179 停服全局 gate）模式无 $ 锚定、设计上匹配所有消息，不参与指令互斥
# （同 test_v87_command_matrix.py 的剔除口径）。
comps = [re.compile(p) for p, _ in handlers]
CMD_PREFIX = r"^(?:\[At:[^\]]+\]\s*)?"


def body(pat):
    p = pat
    if p.startswith("^"):
        p = p[1:]
    if p.startswith("(?:\\[At:\\d+\\]\\s*)?"):
        p = p[len("(?:\\[At:\\d+\\]\\s*)?"):]
    elif p.startswith(r"(?:\[At:[^\]]+\]\s*)?"):
        p = p[len(r"(?:\[At:[^\]]+\]\s*)?"):]
    return p


def tokens(pat):
    b = body(pat)
    out = []
    head = re.match(r"[\u4e00-\u9fff]+|[A-Za-z]{3,}", b)
    if head:
        out.append(head.group(0))
    for m in re.finditer(r"\(\?:([^()]*)\)", b):
        for part in m.group(1).split("|"):
            part = part.strip()
            # 过滤正则语法噪声（\s* 空匹配、.* 通配、[\s\S]* 换行通配、纯符号）
            if not part or part in (r"\s*", r"\s+", r".*", r".+", r"$", r"[\s\S]*", r"\S*"):
                continue
            if re.fullmatch(r"[\s.*+?$^|()\\\[\]]+", part):
                continue
            # v105 M23：通用正则片段（\s*.*、\s*.+ 等纯元字符组合，如 guild_info/inventory
            # 共享的尾部通配）——不含任何字面命令词、命中一切文本，不参与互斥判定
            # （否则同一通用片段必然被多个 handler 共享而误报冲突）
            _lit = re.sub(r"\\[\s\S]", "", part)  # 剥掉 \s \d 等转义序列
            _lit = re.sub(r"[\s.*+?$^|()\[\]]", "", _lit)
            if not _lit:
                continue
            if len(part) >= 2:
                out.append(part)
    return out


async def main():
    print("【命令矩阵：互斥性】")    # 提取所有命令词
    all_tokens = {}
    for pat, name in handlers:
        for t in tokens(pat):
            all_tokens.setdefault(t, set()).add(name)
    # 检查：同一命令词命中多个 handler 且不是同一 handler 的别名
    conflicts = []
    for t, names in all_tokens.items():
        if len(names) > 1:
            conflicts.append((t, sorted(names)))
    check("命令词无跨 handler 冲突", not conflicts, str(conflicts[:5]))

    print("【命令矩阵：历史 bug 回归】")
    # 物品详情1 只走物品详情（不抢背包）
    cases = [
        ("物品详情1", "item_detail"),
        ("技能详情1", "skill_detail"),
        ("背包2", "inventory"),
        ("宠物改名小黑", "pet_rename"),
        ("公会签到5", "guild_sign"),
        ("公会任务", "guild_task"),
        ("技能学习怒吼", "skill_learn"),
        ("背包材料", "inventory"),      # v42：无空格筛选走 inventory（内部解析类型）
        ("背包 材料", "inventory"),
        ("背包筛选 材料", "bag_filter"),  # 独立筛选指令（v83.1 只留『背包筛选』，删『筛选』别名）
        ("背包", "inventory"),
    ]
    for text, expect in cases:
        hit = []
        for (pat, name), c in zip(handlers, comps):
            if c.search(text):
                hit.append(name)
        check(f"『{text}』→ {expect}（命中 {hit}）", expect in hit and len(hit) == 1, str(hit))

    print("【命令矩阵：随机 fuzz】")
    random.seed(42)
    fuzz_hits = 0
    for i in range(200):
        # 随机中文命令词组合
        w = random.choice(["背包", "技能", "物品", "锻造", "公会", "攻击", "探索", "前往", "宠物", "属性", "任务", "地图", "垂钓"])
        n = random.choice(["", "1", "2", "材料", "详情", "学习", "升级", " 2", "5"])
        text = w + n
        hit = [name for (_, name), c in zip(handlers, comps) if c.search(text)]
        if len(hit) > 1:
            fuzz_hits += 1
    check("200 次 fuzz 无双触发", fuzz_hits == 0, f"{fuzz_hits} 次多命中")

    print("【免空格：移动序号】")
    # 移动 2：从 oak_town 的邻居（橡木平原, ...）取第 2 个
    from conftest import db as _db, Main as _Main
    _db.init_db()
    clean_db()  # v110.5 X3：建号前清库，防其他测试/重复运行的玩家残留影响移动判定
    m = _Main(None)
    ev = FakeEvent("g1", "m1", "注册 战士 移动者 男")
    await run(m.register, ev)
    _db.update_player("g1", "m1", cur_map="oak_town")
    ev = FakeEvent("g1", "m1", "前往 2")
    results = await run(m.move, ev)
    out = results[-1] if results else ""
    check("移动序号有返回", len(out) > 5, out[:100])

    print("【分页：列表序号】")
    # 背包翻页（无物品时提示空）
    out = ""
    results = await run(m.inventory, FakeEvent("g1", "m1", "背包 2"))
    out = results[-1] if results else ""
    check("背包翻页有返回", len(out) > 3, out[:100])

    print("【正则：At 前缀】")
    hit = [name for (_, name), c in zip(handlers, comps) if c.search("[At:123] 背包")]
    check("At+背包 → inventory", "inventory" in hit, str(hit))

    print("【攻击目标解析 B7：@昵称 / 名字(QQ)】")
    from conftest import db as _db2, Main as _Main2
    _db2.init_db()
    clean_db()
    m2 = _Main2(None)
    ev = FakeEvent("g2", "p1", "注册 战士 阿呆 男")
    await run(m2.register, ev)
    # 纯 @昵称：前导 @ 剥掉后按名字查（B7 修复前无法命中）
    r = m2._parse_target_qq("@阿呆")
    check("@昵称 命中玩家", r is not None and r[0] == "p1", str(r))
    # 纯名字
    r = m2._parse_target_qq("阿呆")
    check("纯名字 命中玩家", r is not None and r[0] == "p1", str(r))
    # @名字(QQ)
    r = m2._parse_target_qq("@阿呆(8888)")
    check("@名字(QQ) 命中", r is not None and r[0] == "8888", str(r))
    # 名字(QQ)（无 @）
    r = m2._parse_target_qq("阿呆(8888)")
    check("名字(QQ) 命中", r is not None and r[0] == "8888", str(r))
    # 未知名字 → None（不误报）
    check("未知名字 → None", m2._parse_target_qq("@不存在") is None, str(m2._parse_target_qq("@不存在")))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio, random
    sys.exit(0 if asyncio.run(main()) else 1)
