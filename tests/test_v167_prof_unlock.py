# -*- coding: utf-8 -*-
"""commands 层：v67 副业体系（v167 解除数量上限修订）

验证：
  1. 副业面板：不显示分母，只报当前已激活条数
  2. 未激活副业做动作自动激活（连续激活 3+ 条不拦截 = 无数量上限）
  3. 遗忘副业：等级清零 + 学徒资格清空（保持原功能），文案不再提"腾位/占位"
  4. 拜师门槛保留：未拜师的副业动作仍被拦截并引导找导师
  5. 强化/附魔同为副业：拜师后可激活，未拜师动作被拦（引导拜师）
  6. 老玩家兼容：已有等级未激活 → 自动激活
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

passed = failed = 0
from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed", limit=300)


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""


def reset_profs(gid, qid):
    for k in ("gather", "mining", "fishing", "alchemy", "craft", "cooking", "enhance", "enchant"):
        db.forget_prof(gid, qid, k)


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", level=20, gold=5000, cur_map="oak_plain")

    print("【v167 副业面板：无分母，当前条数口径】")
    out = await cmd(m, "profession_view", "g1", "w1", "副业")
    check("面板标题不显示 /2 分母", "【副业面板】" in out and "/2" not in out
          and "当前已激活 0 条" in out, out[:120])
    check("未激活提示仍在", "还没有解锁任何副业" in out, out[:200])

    print("【v167 解除数量上限：连续激活 3+ 条不拦截】")
    # 拜师模拟：学徒资格 = 动作门槛；已拜师的副业做动作应自动激活
    db.update_player("g1", "w1", apprentices=["gather", "mining", "fishing", "alchemy"])
    db.update_player("g1", "w1", cur_map="oak_plain", cur_subarea="oak_plain_3")
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("第 1 条(垂钓)自动激活", "选择了「垂钓」" in out and "当前已激活 1 条" in out, out[:200])
    m._prof_wait_clear("g1", "w1")
    db.update_player("g1", "w1", cur_map="rockfall_gorge", cur_subarea="rockfall_gorge_1")  # v173 矿点门槛=挖1，Lv1 新号可挖
    out = await cmd(m, "mining", "g1", "w1", "挖掘")
    check("第 2 条(挖掘)自动激活", "选择了「挖掘」" in out and "当前已激活 2 条" in out, out[:200])
    m._prof_wait_clear("g1", "w1")
    db.update_player("g1", "w1", cur_map="oak_plain", cur_subarea="oak_plain_3")
    out = await cmd(m, "gather", "g1", "w1", "采集")
    check("第 3 条(采集)照常激活", "选择了「采集」" in out and "当前已激活 3 条" in out, out[:200])
    m._prof_wait_clear("g1", "w1")
    db.update_player("g1", "w1", cur_map="oak_plain")
    out = await cmd(m, "alchemy", "g1", "w1", "炼金")
    check("第 4 条(炼金)自动激活", "副业位已满" not in out and "炼金" in out, out[:200])
    check("激活数 > 2（无上限实锤）", len(db.get_activated_profs("g1", "w1")) > 2,
          str(db.get_activated_profs("g1", "w1")))

    print("【v167 遗忘副业：保留功能，中性文案】")
    out = await cmd(m, "prof_forget", "g1", "w1", "遗忘副业 挖掘")
    check("遗忘成功", "遗忘了「挖掘」" in out and "原 Lv." in out, out[:200])
    check("遗忘文案无 腾位/占位/分母", "副业位" not in out and "/4" not in out and "腾" not in out, out[:200])
    check("挖掘等级清零", db.get_prof_level("g1", "w1", "mining") == 1,
          str(db.get_prof_level("g1", "w1", "mining")))
    p = db.get_player("g1", "w1")
    check("挖掘学徒资格同步清", "mining" not in (p.get("apprentices") or []), str(p.get("apprentices")))
    out = await cmd(m, "prof_forget", "g1", "w1", "遗忘副业 不存在")
    check("不存在副业提示", "没有" in out, out[:120])

    print("【v167 拜师门槛保留（require_apprentice）】")
    # 铸造未拜师 → 动作拦截引导拜师（不再有"遗忘副业"腾位引导）
    reset_profs("g1", "w1")
    db.update_player("g1", "w1", apprentices=["craft"])
    db.update_player("g1", "w1", gold=5000, cur_map="oak_town", cur_subarea="oak_town_2")
    out = await cmd(m, "fishing", "g1", "w1", "垂钓")
    check("未拜师垂钓被拦引导拜师", "还没解锁" in out and "拜师" in out, out[:200])
    out = await cmd(m, "craft", "g1", "w1", "锻造 铁剑")
    check("已拜师锻造可激活", "选择了「锻造」" in out or "锻造" in out, out[:200])

    print("【v167 强化/附魔同步放开（同为副业）】")
    reset_profs("g1", "w1")
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_3", apprentices=["enhance", "enchant"])
    db.add_item("g1", "w1", "eq_t_w1_剑", {"name": "铁剑", "type": "武器", "slot": "weapon",
                                           "quality": "white", "lv": 3, "atk": 12, "stackable": False}, 1)
    db.set_event_state(f"prof_daily_w1_{time.strftime('%Y-%m-%d')}", "enhance|强化装备|1|50|1|1")
    out = await cmd(m, "enhance", "g1", "w1", "强化 铁剑")
    check("已拜师强化可直接激活", "选择了「强化」" in out or "强化成功" in out
          or "强化失败" in out or "需要强化" in out, out[:200])
    out = await cmd(m, "profession_view", "g1", "w1", "副业")
    check("强化已激活进面板", "强化" in out, out[:200])
    # 附魔：无参给格式（说明没被副业位拦）
    out = await cmd(m, "enchant", "g1", "w1", "附魔")
    check("无参附魔给格式（不被数量拦）", "格式" in out or "哪件装备" in out, out[:200])

    print("【v167 文案残留扫描】")
    import re as _re
    srcs = []
    # ★ P5F-REPOINT: 原扫宿主壳三棵树（`game/commands` · `game/store` · `game/data`，随删壳批消失）
    #   → 扫包内真源树 `content`（命令/存档/数据表都在这一棵里）。
    for _dir in ("content",):
        for _root, _dirs, _files in os.walk(_dir):
            for _f in _files:
                if _f.endswith(".py"):
                    srcs.append(os.path.join(_root, _f))
    bad = []
    for _fp in srcs:
        _txt = open(_fp, encoding="utf-8").read()
        if "MAX_ACTIVE_PROFS" in _txt:
            for _ln in _txt.splitlines():
                if "/MAX_ACTIVE_PROFS" in _ln or "MAX_ACTIVE_PROFS)" in _ln:
                    bad.append(f"{_fp}:{_ln.strip()}")
    check("无 MAX_ACTIVE_PROFS 参与文案残留", not bad, str(bad))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
