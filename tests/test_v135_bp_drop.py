# -*- coding: utf-8 -*-
"""v135 图纸掉率提高 + 图纸残页合成验收测试

验收标准（docs/EQUIP_REDESIGN_PLAN_v135.md 六节）：
1. 概率常量：BOSS_BP_DROP_CHANCE=0.10 / CHEST_BP_CHANCE=0.85 / FISH_RARE_CHANCE=0.60
2. Boss 掉落：drops.roll_drop(boss) 基础 10%，幸运 50% 时最高 15%（随机统计 4 万次）
3. 探索宝箱：tpl_open_chest 消费 catalog_core.CHEST_BP_CHANCE（85%；B16 收口后实现与
   常量的**读点**都在包内，宿主聚合层只作取值展示）
4. 垂钓宝物箱：economy 垂钓消费 C.FISH_RARE_CHANCE（60%）
5. 副本首功 + 全员 10%：instance 通关奖励循环消费 catalog_core.INSTANCE_BP_CHANCE（10%），
   已学图纸折算图纸残页、未学整张入包
6. 图纸残页合成：『图纸合成』面板 / 『图纸合成 <装备名>』消耗 10 张残页 → 指定图纸；
   残页不足拦截；未知名拦截

独立运行：python tests/test_v135_bp_drop.py
"""
import os
import sys
import asyncio
import inspect
import re
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import FakeEvent, run, clean_db, make_player  # noqa: F401
from _engine_harness import C, db
from content import drops as DROPS
from content.economy_cmds import EconomyImpl as _EcoImpl  # noqa: E402
from content.instance_cmds import InstanceImpl as _InstImpl  # noqa: E402
from _engine_harness import Main as _CmdHost  # noqa: E402
# B16 收口（2026-09-14）：这两个概率常量的**实现读点**已随代码搬进包内
# （端口 `content/item_templates.py` 读 `catalog_core.CHEST_BP_CHANCE`、
#   `content/instance_cmds.py` 读 `catalog_core.INSTANCE_BP_CHANCE`）。
# 宿主聚合层 `C.<名>` 只是**取值拷贝**（game/content.py 逐名 setdefault），改它不驱动实现
# ⇒ 打桩/源码断言必须指向真正的读点 `content.catalog_core`（否则打桩静默无效 = 假绿）。
from content import catalog_core as _CC  # noqa: E402

PASS = 0
FAIL = 0


def asyncio_run(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@contextmanager
def _patched(mod, attr, value):
    old = getattr(mod, attr)
    setattr(mod, attr, value)
    try:
        yield
    finally:
        setattr(mod, attr, old)


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")


# ============ 1. 概率常量 ============
print("【1. 概率常量（constants.py）】")
check("BOSS_BP_DROP_CHANCE == 0.10", abs(C.BOSS_BP_DROP_CHANCE - 0.10) < 1e-9)
check("CHEST_BP_CHANCE == 0.85", abs(C.CHEST_BP_CHANCE - 0.85) < 1e-9)
check("FISH_RARE_CHANCE == 0.60", abs(C.FISH_RARE_CHANCE - 0.60) < 1e-9)
check("INSTANCE_BP_CHANCE == 0.10", abs(C.INSTANCE_BP_CHANCE - 0.10) < 1e-9)

# ============ 2. Boss 图纸掉落（roll_drop） ============
print("【2. Boss 图纸掉落概率（roll_drop，随机 4 万次）】")
N = 40000
hit0 = sum(1 for _ in range(N) if DROPS.roll_drop(30, "boss", 0.0)[1])
hit50 = sum(1 for _ in range(N) if DROPS.roll_drop(30, "boss", 0.5)[1])
hit100 = sum(1 for _ in range(N) if DROPS.roll_drop(30, "boss", 1.0)[1])  # 幸运上限 50%
r0 = hit0 / N
r50 = hit50 / N
r100 = hit100 / N
print(f"  幸运 0%:  {r0:.3%}（期望 10%）")
print(f"  幸运 50%: {r50:.3%}（期望 15%）")
print(f"  幸运 100%: {r100:.3%}（上限 50% → 15%）")
check("幸运 0% 约 10%（±1.5%）", 0.085 <= r0 <= 0.115)
check("幸运 50% 约 15%（±1.8%）", 0.132 <= r50 <= 0.168)
check("幸运 100% 仍 15%（幸运上限 50%）", 0.132 <= r100 <= 0.168)
bp = DROPS.roll_drop(30, "boss", 1.0)[1]
check("掉落物为图纸物品（type=图纸）", bp is None or (bp.get("type") == "图纸" and bp.get("blueprint_for")))
# 普通怪不掉图纸（v94 铁律）
hit_norm = sum(1 for _ in range(2000) if DROPS.roll_drop(30, "normal", 0.0)[1])
check("普通怪不掉图纸（v94 铁律）", hit_norm == 0)

# ============ 3. 探索宝箱（tpl_open_chest 消费 CHEST_BP_CHANCE） ============
print("【3. 探索宝箱图纸概率（tpl_open_chest 消费 CHEST_BP_CHANCE）】")
from content import item_templates as IT


class _ChestCtx:
    """tpl_open_chest 最小上下文替身（只暴露模板用到的字段）。"""

    def __init__(self, dbm, Cm, gid, qid, lv):
        self.group_id = gid
        self.qq_id = qid
        self.lv = lv
        self._focus = dbm.get_player(gid, qid)
        self._dbm = dbm
        self._Cm = Cm

    def _db(self):
        return self._dbm

    def _C(self):
        return self._Cm

    def item_name(self):
        return "陈旧宝箱"

    def hook(self, name):
        # 真实 ItemContext 在此执行命名钩子（如 remove_item 消耗物品）；测试替身 no-op
        return None

    def plain_result(self, text):
        return text


# 3a. 模板消费 CHEST_BP_CHANCE（源代码引用验证）
tpl_src = inspect.getsource(IT.tpl_open_chest)
check("open_chest 模板消费 CHEST_BP_CHANCE",
      bool(re.search(r"\.CHEST_BP_CHANCE\b", tpl_src)),
      )
# 3b. CHEST_BP_CHANCE=1.0 时开箱必得图纸
clean_db()
make_player("g1", "q1", "宝箱测试", "战士", level=20)
with _patched(_CC, "CHEST_BP_CHANCE", 1.0):
    check("打桩生效（打到实现读点 content.catalog_core 上）", _CC.CHEST_BP_CHANCE == 1.0)
    ctx = _ChestCtx(db, C, "g1", "q1", 20)
    try:
        for _ in IT.tpl_open_chest(ctx):
            pass
    except TypeError:
        pass
    inv = db.get_inventory("g1", "q1")
    check("CHEST_BP_CHANCE=1.0 时开箱必得图纸", any(it["data"].get("type") == "图纸" for it in inv))
# 3c. CHEST_BP_CHANCE=0.0 时开箱不得图纸
with _patched(_CC, "CHEST_BP_CHANCE", 0.0):
    clean_db()
    make_player("g1", "q1", "宝箱测试", "战士", level=20)
    ctx = _ChestCtx(db, C, "g1", "q1", 20)
    try:
        for _ in IT.tpl_open_chest(ctx):
            pass
    except TypeError:
        pass
    inv = db.get_inventory("g1", "q1")
    check("CHEST_BP_CHANCE=0.0 时开箱不得图纸", not any(it["data"].get("type") == "图纸" for it in inv))


class _ChestCtx:
    """tpl_open_chest 最小上下文替身（只暴露模板用到的字段）。"""

    def __init__(self, dbm, Cm, gid, qid, lv):
        self.group_id = gid
        self.qq_id = qid
        self.lv = lv
        self._focus = dbm.get_player(gid, qid)
        self._dbm = dbm
        self._Cm = Cm

    def _db(self):
        return self._dbm

    def _C(self):
        return self._Cm

    def item_name(self):
        return "陈旧宝箱"

    def hook(self, name):
        # 真实 ItemContext 在此执行命名钩子（如 remove_item 消耗物品）；测试替身 no-op
        return None

    def plain_result(self, text):
        return text

# ============ 4. 垂钓惊喜层（v168.2 取代宝物箱 60% 图纸） ============
print("【4. 垂钓惊喜层（v168.2 _fishing_surprise）】")
clean_db()
make_player("g1", "q1", "钓鱼测试", "战士", level=30)
src = inspect.getsource(_EcoImpl)
# ★ 2026-09-13 收口（B9-L1 economy 薄壳 + B10 批）：实现真源已搬到包内
#   `content/economy_cmds.py` 的 `EconomyImpl`；本文件已把 `EconomyCmds` 直接改口为
#   `EconomyImpl`（同一对象）⇒ 源码面就是实现本体，断言与原意不变。
# v168.2 鱼鱼拍板：惊喜不绑定宝箱——每次鱼获按品质判定惊喜（白0/绿2%/蓝5%/紫15%/橙30%），
# 内容池=图纸30/装备25/符文20/宝石15/材料10；彩蛋收藏鱼必橙装。FISH_RARE_CHANCE 常量不再被垂钓消费。
has_surprise_fn = "def _fishing_surprise" in src
has_trigger_map = "_FISHING_SURPRISE_TRIGGER" in src
check("垂钓惊喜层函数 _fishing_surprise 存在", has_surprise_fn)
check("惊喜触发品质表存在", has_trigger_map)
# 内容池边界（累积）：图纸30/装备55/符文75/宝石90/材料100（源码为类属性不带 self. 前缀）
for name, key, val in [("图纸 30%", "_FISHING_SURPRISE_BP", 0.30),
                       ("装备 55%(累)", "_FISHING_SURPRISE_EQ", 0.55),
                       ("符文 75%(累)", "_FISHING_SURPRISE_RUNE", 0.75),
                       ("宝石 90%(累)", "_FISHING_SURPRISE_GEM", 0.90)]:
    check(f"惊喜内容池 {name}", f"{key} = {val}" in src)
check("FISH_RARE_CHANCE 数值仍 0.6（未删常量）", abs(C.FISH_RARE_CHANCE - 0.6) < 1e-9)

# ============ 5. 副本通关全员图纸（INSTANCE_BP_CHANCE） ============
print("【5. 副本通关全员图纸（INSTANCE_BP_CHANCE=10%）】")
clean_db()
insrc = inspect.getsource(_InstImpl)
# ★ 2026-09-14 收口（B11-L1 instance 薄壳）：实现真源已搬到包内 `content/instance_cmds.py` 的
#   `InstanceImpl`；本文件已把 `InstanceCmds` 直接改口为 `InstanceImpl`（同一对象）
#   ⇒ 源码面就是实现本体，断言与原意不变。
check("副本通关循环消费 INSTANCE_BP_CHANCE", bool(re.search(r"\.INSTANCE_BP_CHANCE\b", insrc)))
check("副本已学图纸折算残页逻辑", "图纸残页" in insrc and "learned_blueprints" in insrc)
# 直接断言常量本身。原先用 40000 次抽样间接"测"它 —— 那测的是 Python 随机数分布，
# 不是游戏常量，且是未 seed 的概率性断言（见 FISH_RARE_CHANCE 的直断写法）。
check("INSTANCE_BP_CHANCE = 0.10（直断常量，非抽样）",
      abs(C.INSTANCE_BP_CHANCE - 0.10) < 1e-9)

# ============ 6. 图纸残页合成『图纸合成』 ============
print("【6. 图纸残页合成（bp_craft）】")
clean_db()
eco = _CmdHost(None)
p = make_player("g1", "q1", "合成测试", "战士", level=30)
# 6a. 无残页：面板提示不足
ev = FakeEvent("g1", "q1", "图纸合成")
res = asyncio_run(run(eco.bp_craft, ev))
joined = "\n".join(res)
check("无参面板展示可合成池", "图纸残页合成" in joined and "10" in joined)
check("残页不足提示", "图纸残页不足" in joined or "不足" in joined)
# 6b. 未知名拦截
ev = FakeEvent("g1", "q1", "图纸合成 不存在的装备XYZ")
res = asyncio_run(run(eco.bp_craft, ev))
joined = "\n".join(res)
check("未知名拦截", "没有" in joined and "图纸合成" in joined)
# 6c. 残页不足 + 指定装备
_cand = [(rid, r) for rid, r in C.EQUIP_ROSTER.items()
         if r["source"] in ("图纸", "boss") and rid in C.EQUIP_ROSTER_BY_NAME.get(r["name"], [])]
_cand.sort(key=lambda x: x[1]["lv"])
rid0, r0 = _cand[0]
ev = FakeEvent("g1", "q1", f"图纸合成 {r0['name']}")
res = asyncio_run(run(eco.bp_craft, ev))
joined = "\n".join(res)
check(f"指定装备残页不足拦截（{r0['name']}）", "不足" in joined)
# 6d. 给 10 张残页 → 合成成功
db.add_item("g1", "q1", "mat_tu_zhi_can_ye",
            {"name": "图纸残页", "type": "材料", "stackable": True, "price": 10}, count=10)
ev = FakeEvent("g1", "q1", f"图纸合成 {r0['name']}")
res = asyncio_run(run(eco.bp_craft, ev))
joined = "\n".join(res)
check("10 张残页合成成功", "合成成功" in joined and r0["name"] in joined)
inv = db.get_inventory("g1", "q1")
bp_items = [it for it in inv if it["data"].get("type") == "图纸"]
shards_left = sum(it["count"] for it in inv if it["key"] == "mat_tu_zhi_can_ye")
check("背包出现指定图纸", any(it["data"].get("blueprint_for") == r0["name"] for it in bp_items))
check("残页扣光 10 张", shards_left == 0)
# 6e. 数字选择：『图纸合成 1』 消耗 10 张合成第一件
db.add_item("g1", "q1", "mat_tu_zhi_can_ye",
            {"name": "图纸残页", "type": "材料", "stackable": True, "price": 10}, count=10)
ev = FakeEvent("g1", "q1", "图纸合成 1")
res = asyncio_run(run(eco.bp_craft, ev))
joined = "\n".join(res)
check("数字序号合成成功", "合成成功" in joined and _cand[0][1]["name"] in joined)

# ============ 总结 ============
print()
print(f"✅ PASS: {PASS}  ❌ FAIL: {FAIL}")
if FAIL:
    sys.exit(1)
print("v135 图纸掉率提高 + 图纸残页合成验收全部通过")