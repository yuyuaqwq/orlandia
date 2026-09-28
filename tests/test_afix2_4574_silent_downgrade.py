# -*- coding: utf-8 -*-
"""L4578 #3/#5 门禁：冒险手册两处**内层** `except Exception: pass` 把读失败
降级成假数据（足迹首访日期 / 收藏大类）。

缺陷形状（两处同族，与本文件同仓 #1「足迹 0/0」已按同一口径修掉的那处一致）：

    try:  ...  except Exception:  pass          ← 内层：错误被**降级**
    try:  ...  except Exception as e: <可见文案>  ← 外层：真兜底，给玩家报错

两处语义相反。内层把错误吃掉 ⇒ 外层永远走不到 ⇒ 玩家读到一份「看着正常、
实则少一整个维度」的卡片/图鉴，零报错。已修：两处内层兜底删掉，由外层接管。

判据只**注入失败**并断言「外层真兜底接管」；正常路径逐字同基线（证明只改失败那一路）。
真调生产读口（`Main._footprint_view` / `Main._possessed_view`），不重写被测逻辑。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main  # noqa: E402
from _check import bind_check  # noqa: E402  断言助手单源：tests/_check.py
from content import texts as _TX  # noqa: E402

passed = failed = 0
check = bind_check(globals(), "passed", "failed")

clean_db()
db.init_db()
m = Main()
gid, qid = "g1", "afix2_4574"


def _boom(msg):
    def _f(*a, **k):
        raise RuntimeError(msg)
    return _f


def _one_visited():
    """造一条到访行，返回 (map_id, subarea_id)。"""
    for x in C.MAPS:
        if x.get("type") in ("副本", "隐藏区域"):
            continue
        sas = (C.SUBAREAS or {}).get(x["id"]) or []
        if sas:
            db.add_visited_subarea(gid, qid, x["id"], sas[0]["id"])
            return x["id"], sas[0]["id"]
    raise AssertionError("域里没有可用的城镇/野外子区域，探针前提不成立")


# ---------------------------------------------------------------- 正常基线
_one_visited()
base_fp = m._footprint_view(gid, qid)
check("基线：足迹卡片带首访日期 (MM-DD)", "(" in base_fp and "-" in base_fp, repr(base_fp[:200]))
base_iv = m._possessed_view(gid, qid, "")
check("基线：收藏页含「装备」大类（三段循环都跑到）", "装备" in base_iv, repr(base_iv[:200]))

# ---------------------------------------------------------------- ③ 首访日期读失败
_o = db.get_visited_subareas_rows
db.get_visited_subareas_rows = _boom("模拟首访日期读失败")
try:
    out = m._footprint_view(gid, qid)
finally:
    db.get_visited_subareas_rows = _o
check("③ rows 读失败 → 报错可见（不再静默退成「无日期」形态）",
      out != base_fp and "加载失败" in out, repr(out[:200]))

# ---------------------------------------------------------------- ⑤ 末段（装备）读失败
# ★ 只让**带 slot 的装备**抛错：旧实现下材料/物品两段已攒进 cat_items、末段被
#   except 吞掉 ⇒ 玩家拿到「半个图鉴」。若让第一段就失败，cat_items 为空、旧实现
#   也会走 item_empty ⇒ 测不出这个洞。
_oc = m._item_cat


def _boom_on_equip(v):
    if isinstance(v, dict) and v.get("slot"):
        raise RuntimeError("模拟装备分类读失败")
    return _oc(v)


m._item_cat = _boom_on_equip
try:
    out2 = m._possessed_view(gid, qid, "")
finally:
    m._item_cat = _oc
check("⑤ 末段（装备）读失败 → 报错可见（不再是半个图鉴）",
      bool(out2) and "加载失败" in out2, repr(out2[:200]))

# ---------------------------------------------------------------- 反证：正常路一字未改
check("正常路径 · 足迹 与基线逐字相同（只改失败那一路）",
      m._footprint_view(gid, qid) == base_fp, repr(m._footprint_view(gid, qid)[:200]))
check("正常路径 · 收藏 与基线逐字相同", m._possessed_view(gid, qid, "") == base_iv)
check("外层两条兜底文案仍登记在文案表里（没被删掉换绿）",
      bool(_TX.static("footprint.fail")) and bool(_TX.static("adv.item_fail")),
      repr(_TX.static("footprint.fail")))

# ---------------------------------------------------------------- ⑦ 彩蛋鱼成就读失败
# ★ 代价形态与 #3/#5 不同：这里被降级掉的是**永久收藏记录**。鱼卖掉后背包里没有了，
#   只靠 collect_fish 成就记着；成就读失败 ⇒ 玩家永久解锁的那条退回「❌ ??? 没收集过」，
#   计数 1/3 → 0/3。派发层 `command/router.py:147` 有真兜底（记日志 + 给通用句），
#   所以这里 fail-closed 是把错误**升级到玩家看得见**，不是让命令崩掉。
_fish0 = [a for a in C.ACHIEVEMENTS
          if (a.get("cond") or {}).get("type") == "collect_fish"]
check("前提：域里有 collect_fish 成就（探针前提成立）", bool(_fish0), str(len(_fish0)))

if _fish0:
    db.set_achievement(gid, qid, _fish0[0]["id"], 1, 1)     # 已解锁、背包里没有
    base_fish = m._collect_fish_bestiary(gid, qid)
    check("基线：彩蛋鱼卡片认这条永久解锁记录（1/3 而非 0/3）",
          "1/3" in base_fish, repr(base_fish[:160]))

    _oa = db.get_achievements
    db.get_achievements = _boom("模拟成就读失败")
    try:
        raised, outf = None, ""
        try:
            outf = m._collect_fish_bestiary(gid, qid)
        except Exception as exc:                            # noqa: BLE001
            raised = exc
    finally:
        db.get_achievements = _oa
    check("⑦ 成就读失败 → 不再谎报「没收集过」（上抛给派发层真兜底）",
          raised is not None, "没抛，却返回了 %r" % (outf[:160],))
    check("⑦ 正常路径 · 彩蛋鱼 与基线逐字相同（只改失败那一路）",
          m._collect_fish_bestiary(gid, qid) == base_fish)


print("\n== %d 通过 / %d 失败 ==" % (passed, failed))
sys.exit(1 if failed else 0)
