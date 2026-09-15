# -*- coding: utf-8 -*-
"""v126.4 个体属性（tags）详情显示（tests/test_v1264_item_tag_display.py）

数据驱动注册表 ITEM_TAG_DISPLAY：『物品详情』对有 tags 的堆叠个体物（垂钓渔获）
逐条渲染个体属性（鱼 → 每条重量/体长）。覆盖：
  1. 鱼详情逐条显示重量/体长（handler 全链路）
  2. 通配 * 兜底：未注册 type 的 tag 物品也显示
  3. max_lines 截断 + 省略行（31 条 → 30 行 + 「还有 1 条」）
  4. tag 字段缺失 → 单条跳过不炸（其它条正常）
  5. 无 tags 物品详情不受影响（不出现「个体：」区）
  6. 出售截断 tags 后详情同步（count>=len(tags) 不变量）
  7. 多行模板（line 列表）渲染机制
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run
from content.economy_cmds import _render_item_tags

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


def fish_key(name):
    return C.resolve("materials", name)


def add_fish(gid, qid, name, size, weight, n=1):
    """入包 n 条个体鱼（等价垂钓 add_item(tag=...)）"""
    key = fish_key(name)
    for _ in range(n):
        db.add_item(gid, qid, key,
                    {"name": name, "type": "鱼", "stackable": True,
                     "price": 6, "quality": "white"},
                    tag={"size": size, "weight": weight})
    return key


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    await cmd(m, "register", "g1", "w2", "注册 法师 新手 女")

    print("【1 鱼详情逐条显示重量/体长（handler 全链路）】")
    add_fish("g1", "w1", "银鳞鱼", 35.2, 1.2)
    add_fish("g1", "w1", "银鳞鱼", 28.0, 0.8)
    add_fish("g1", "w1", "银鳞鱼", 41.5, 1.9)
    out = await cmd(m, "item_detail", "g1", "w1", "物品详情 银鳞鱼")
    check("详情含『个体：』区", "个体：" in out, out)
    check("逐条显示第 1 条 35.2cm/1.2kg", "35.2cm / 1.2kg" in out, out)
    check("逐条显示第 2 条 28.0cm/0.8kg", "28.0cm / 0.8kg" in out, out)
    check("逐条显示第 3 条 41.5cm/1.9kg", "41.5cm / 1.9kg" in out, out)
    check("鱼行带 🐟 图标（type=鱼 显式配置）", "🐟 35.2cm" in out, out)
    # 三条鱼不触发省略行
    check("3 条不显示省略行", "还有" not in out, out)
    # 序号查看也走同一渲染
    out2 = await cmd(m, "item_detail", "g1", "w1", "物品详情 1")
    check("序号查看也显示个体区", "个体：" in out2, out2)

    print("【2 通配 * 兜底：未注册 type 也显示】")
    # 构造 type='奇物'（不在 ITEM_TAG_DISPLAY 且不在材料归并）→ 走 '*' 模板
    lines = []
    _render_item_tags({"name": "神秘水晶", "type": "奇物",
                        "tags": [{"size": 12.3, "weight": 0.5}]}, lines)
    joined = "\n".join(lines)
    check("* 通配显示个体行", "个体：" in joined and "12.3cm / 0.5kg" in joined, joined)
    check("* 通配行有 `  · ` 前缀", "  · 12.3cm / 0.5kg" in joined, joined)

    print("【3 max_lines 截断 + 省略行】")
    add_fish("g1", "w1", "金鲤", 50.0, 2.2, n=31)   # 30 上限 + 1
    out3 = await cmd(m, "item_detail", "g1", "w1", "物品详情 金鲤")
    cnt = out3.count("cm / ")
    check("只显示上限 30 行", cnt == 30, f"实际 {cnt} 行:\n{out3}")
    check("超出显示省略行『还有 1 条』", "……还有 1 条" in out3, out3)

    print("【4 tag 字段缺失 → 单条跳过不炸】")
    lines4 = []
    _render_item_tags({"name": "残缺鱼", "type": "鱼",
                        "tags": [{"size": 10.0, "weight": 0.4},
                                 {"size": 11.0},            # 缺 weight
                                 {"size": 12.0, "weight": 0.6}]}, lines4)
    j4 = "\n".join(lines4)
    check("缺字段条被跳过，其余正常", "10.0cm / 0.4kg" in j4 and "12.0cm / 0.6kg" in j4, j4)
    check("缺字段条不产生空行", "11.0cm" not in j4, j4)

    print("【5 无 tags 物品详情不受影响】")
    db.add_item("g1", "w1", fish_key("海藻"),
                {"name": "海藻", "type": "材料", "stackable": True,
                 "price": 15, "quality": "green"})
    out5 = await cmd(m, "item_detail", "g1", "w1", "物品详情 海藻")
    check("普通材料详情无『个体：』", "个体：" not in out5, out5)
    check("普通材料详情正常显示", "海藻" in out5, out5)

    print("【6 出售截断 tags 后详情同步】")
    # w2 备 4 条银鳞鱼 → 卖 3 条 → 详情只剩 1 条
    add_fish("g1", "w2", "银鳞鱼", 20.0, 0.5, n=4)
    key = fish_key("银鳞鱼")
    db.sell_item_atomic("g1", "w2", key, 3, 18)
    out6 = await cmd(m, "item_detail", "g1", "w2", "物品详情 银鳞鱼")
    cnt6 = out6.count("cm / ")
    check("卖掉 3 条后详情只剩 1 条个体", cnt6 == 1, f"实际 {cnt6} 条:\n{out6}")

    print("【7 多行模板（line 列表）机制】")
    # 临时配置验证渲染机制支持 list line（数据表注释说明的扩展形态）。
    # ★ R5 打桩落点：`ITEM_TAG_DISPLAY` 已进 `content/facade.py::_NAME_SRC`（权威真源 =
    #   `content.catalog_legacy`），`C.ITEM_TAG_DISPLAY` 不再经聚合面 `_namespace()` 取件。
    #   落点选**真源那一只 dict 就地改**（不是重绑名字）：`_namespace()["ITEM_TAG_DISPLAY"]`
    #   与宿主 `game.content`（`from content.catalog_legacy import *` 拿的同一只对象，实测
    #   `is` 判定为 True）都跟着变 ⇒ 消费方无论经哪条路取件，判据都成立。
    import content.catalog_legacy as _cl
    _tbl = _cl.ITEM_TAG_DISPLAY
    _had = "奇物" in _tbl
    _saved = _tbl.get("奇物")
    _tbl["奇物"] = {"line": ["✨ 秘宝 {size:.1f}cm", "  来历：{origin}"],
                    "max_lines": 5}
    try:
        lines7 = []
        _render_item_tags({"name": "神秘水晶", "type": "奇物",
                            "tags": [{"size": 5.0, "origin": "深海"}]}, lines7)
        j7 = "\n".join(lines7)
        check("一条 tag 渲染多行", "秘宝 5.0cm" in j7 and "来历：深海" in j7, j7)
    finally:
        if _had:
            _tbl["奇物"] = _saved
        else:
            _tbl.pop("奇物", None)

    print(f"\n结果：{passed} 通过 / {failed} 失败")
    if failed:
        sys.exit(1)

if __name__ == "__main__":
    asyncio = __import__("asyncio")
    asyncio.run(main())