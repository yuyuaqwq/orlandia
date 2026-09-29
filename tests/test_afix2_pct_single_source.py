# -*- coding: utf-8 -*-
"""审计 B2 自开口（族：玩家可见比率被向零截断）的**包级单源**那一半。

上一轮（test_afix2_pct_round_render.py / 8b2d6cb）只在 content/economy_cmds.py
**一个文件内**收口：12 处裸 int(v*100) 改成文件私有出口 _pct_str。
但同一类上屏在**另一个命令模块**里仍各写一份裸截断 —— content/world_cmds.py 7 处
（房屋恢复 / 房屋回购 / 传送折扣 / 野外遭遇概率 / 转职成长加成）
=> 同一渲染口径散在两个模块，而两个模块都已经在用 catalog_core（它持有 PCT_STATS）。

本判据钉住的是这一类（数据驱动，不写死是哪几条）：

  1. 包级单源：pct_str 住在 catalog_core，两个命令模块都走它；
     economy_cmds._pct_str 只允许是薄转发（名字/签名保留 => 不破坏已有调用点）。
  2. 真实数据上的 half-up 不变式（核心）：扫全部内容域的比率字段，
     任一 v 必须渲染成 round_half_up(v*100)；数据里真有需要进位的格子（覆盖面自检）。
  3. 活代码零裸截断：两个命令模块里 int(... * 100) 形状必须归零。
  4. 端到端：真调生产渲染口，玩家看到的那一行必须含 half-up 后的值。
  5. 整数量级零改动：0.02->2% / 0.5->50% / 1.0->100%（防统一出口退化成一律 +1）。

不改判据迁就实现：1/2/3/5 由真实域数据 + 真实生产函数驱动，域里加一件东西立刻重验。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401  导入即完成 sys.path 装配

from _check import bind_check  # noqa: E402  断言助手单源

passed = failed = 0
check = bind_check(globals(), "passed", "failed")

_CT = os.path.join(str(_paths.PKG_ROOT), "content", "catalog_core.py")
_ECON = os.path.join(str(_paths.PKG_ROOT), "content", "economy_cmds.py")
_WORLD = os.path.join(str(_paths.PKG_ROOT), "content", "world_cmds.py")
_ct_src = open(_CT, encoding="utf-8").read()
_econ_lines = open(_ECON, encoding="utf-8").read().split("\n")
_world_lines = open(_WORLD, encoding="utf-8").read().split("\n")

# ---- 1. 包级单源 ----
check("1 单源 pct_str 住在 catalog_core", "def pct_str(v)" in _ct_src,
      "catalog_core 上没有 pct_str —— 包级出口缺失")
check("1 单源在 __all__ 里（对外可寻址）", '"pct_str"' in _ct_src,
      "pct_str 未登记进 __all__")
_fwd = [i for i, ln in enumerate(_econ_lines, 1) if "return _ccore.pct_str(v)" in ln]
check("1 economy_cmds._pct_str 已是薄转发（签名/名字保留）", len(_fwd) == 1,
      "找到 %d 处转发：%s" % (len(_fwd), _fwd))
check("1 world_cmds 走 catalog_core.pct_str（零处本地复制）",
      not re.search(r"^\s*def\s+pct_str\s*\(", "\n".join(_world_lines), re.M),
      "world_cmds 自己又定义了一份 pct_str => 出现第二份实现")

os.environ["GWEN_TEST_MODE"] = "1"
from _engine_harness import boot  # noqa: E402
boot()

from content import catalog_core as C  # noqa: E402
from content import economy_cmds as E  # noqa: E402
from content import world_cmds as W  # noqa: E402


def _pct(v):
    """调生产单源，吞异常回报 —— 修正被回退时整个函数会消失，
    让 AttributeError 冒出去会让判据在第一条红就 Traceback 中止、看不到完整红集。"""
    try:
        return C.pct_str(v)
    except Exception as exc:
        return "RAISED(%s)" % type(exc).__name__


check("1 单源函数可调（反证面：撤掉修正时本条红）", hasattr(C, "pct_str"),
      "catalog_core 上没有 pct_str")
check("1 economy_cmds._pct_str 仍可调（既有调用点不许断）", hasattr(E, "_pct_str"),
      "economy_cmds._pct_str 消失 => 12 处调用点会 AttributeError")

# ---- 3. 活代码零裸截断（注释里的事故记录不算）----
_bare = []
for _tag, _lines in (("economy_cmds", _econ_lines), ("world_cmds", _world_lines)):
    for i, ln in enumerate(_lines, 1):
        if ln.lstrip().startswith("#"):
            continue
        if re.search(r"int\([^()]*\*\s*100\s*\)", ln):
            _bare.append("%s:%d %s" % (_tag, i, ln.strip()[:70]))
check("3 两个命令模块里零处裸向零截断 int(...*100)", not _bare, "残留：%s" % _bare[:5])

# ---- 2. 真实数据上的 half-up 不变式 ----
_DD = os.path.join(str(_paths.PKG_ROOT), "content", "data")
_RULES = os.path.join(str(_paths.PKG_ROOT), "content", "rules")


def _half_up(v):
    from decimal import Decimal, ROUND_HALF_UP
    return int(Decimal(str(float(v) * 100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _walk(o, path, out, keys):
    if isinstance(o, dict):
        for k, v in o.items():
            if (k in keys and isinstance(v, (int, float)) and not isinstance(v, bool)):
                out.append((path + "." + str(k), v))
            _walk(v, path + "." + str(k), out, keys)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk(v, "%s[%d]" % (path, i), out, keys)


_PCT_NAMES = {"hot", "hot_mana", "heal", "mana", "chance", "rate", "mult",
              "discount", "pct", "pct_boss", "dot_pct", "per_pct", "dmg_pct_per"}
_ppr = os.path.join(_RULES, "panel_rules.json")
if os.path.isfile(_ppr):
    try:
        _d = json.load(open(_ppr, encoding="utf-8"))
        for _k, _v in _d.items():
            if isinstance(_v, dict) and isinstance(_v.get("stats"), list):
                _PCT_NAMES |= set(_v["stats"])
    except Exception:
        pass

_rows = []
for _root in (_DD, _RULES):
    if not os.path.isdir(_root):
        continue
    for _f in sorted(os.listdir(_root)):
        if not _f.endswith(".json"):
            continue
        try:
            _d = json.load(open(os.path.join(_root, _f), encoding="utf-8"))
        except Exception:
            continue
        _walk(_d, _f, _rows, _PCT_NAMES)
_ratios = [(p, v) for p, v in _rows if 0 < v < 1]
check("2 扫描到真比率格子（判据有覆盖面）", len(_ratios) >= 20, "n=%d" % len(_ratios))

_bad = [(p, v, _pct(v), _half_up(v)) for p, v in _ratios if _pct(v) != str(_half_up(v))]
check("2 全部 %d 个真比率格 half-up 渲染正确" % len(_ratios), not _bad,
      "错 %d 处，前 5：%s" % (len(_bad), _bad[:5]))

# 覆盖面自检：数据里真存在需要进位的格子（否则本判据恒绿 = 假门禁）
_need = [(p, v) for p, v in _ratios if _pct(v) != str(int(float(v) * 100))]
check("2b 数据里真有需要 half-up 进位的格子（本判据不是恒绿）", len(_need) >= 1,
      "0 处 —— 改前改后同值，本判据证明力为 0；实得 %s" % (_need[:3],))
for _p, _v in _need[:8]:
    check("2c 进位格 %s=%s 渲染成 %d%%（改前是 %d%%）" % (_p.split(".")[0], _v, _half_up(_v), int(_v * 100)),
          _pct(_v) == str(_half_up(_v)), "实得 %r" % _pct(_v))

# ---- 5. 整数量级零改动 ----
for _v, _want in ((0.0, "0"), (0.02, "2"), (0.1, "10"), (0.5, "50"), (0.2, "20"), (1.0, "100")):
    check("5 整数量级不变式 %s -> %s%%" % (_v, _want), _pct(_v) == _want, "实得 %r" % _pct(_v))

# ---- 4. 端到端：真调生产渲染口 ----
# 4a 宝石阶位（economy_cmds 的 GEM_TIERS 面）—— 改前 1/2 两阶都印「×1%」
try:
    _gem = E._b143.GEM_TIERS
    _rows_g = []
    for _t in sorted(_gem):
        _m = _gem[_t].get("mult", 0)
        if _m:
            _rows_g.append((_t, _m, _pct(_m)))
    # ★ 判读口径（本轮自纠）：不能用「有阶位屏显同值」作为判据。
    #   宝石阶位每级相差 0.5%（0.01/0.015/0.02/…）⇒ 整数百分比上屏本就会把邻级压成同一个数
    #   （正确口径下 2%/3% 仍会碰上）。那是**数据本身**的问题（阶距小于一个百分点），
    #   不是舍入方向的错。真正的不变式 = **每个阶位的屏显值必须是它自己 mult 的
    #   half-up**（见 4b）。
    check("4a 宝石阶位数量非空（判据有覆盖面）", len(_rows_g) >= 10, "n=%d" % len(_rows_g))
    for _t, _m, _s in _rows_g:
        check("4b 宝石第 %s 阶 mult=%s 渲染 %s%%（真值 %d%%）" % (_t, _m, _s, _half_up(_m)),
              _s == str(_half_up(_m)), "实得 %r" % _s)
except Exception as _exc:
    check("4a 宝石阶位端到端可跑", False, "抛错 %s: %s" % (type(_exc).__name__, _exc))

# 4c 转职成长加成（world_cmds 的 _do_evolve_via_npc 那一格 · TIER_GROWTH[1]=1.15）
try:
    _tg = W.TIER_GROWTH
    _bad_t = []
    for _k, _v in sorted(_tg.items()):
        _delta = float(_v) - 1.0
        _got = _pct(_delta)
        if _got != str(_half_up(_delta)):
            _bad_t.append((_k, _v, _got, _half_up(_delta)))
    check("4c 转职成长加成全部 half-up（改前 TIER_GROWTH[1] 印 14%，真值 15%）",
          not _bad_t, "错：%s" % _bad_t)
    _t1 = float(_tg.get(1, 1.0)) - 1.0
    check("4d TIER_GROWTH[1]=1.15 渲染成 15%（改前 14%，float 误差 14.9999…）",
          _pct(_t1) == "15", "实得 %r" % _pct(_t1))
except Exception as _exc:
    check("4c 转职成长加成端到端可跑", False, "抛错 %s: %s" % (type(_exc).__name__, _exc))

# 4e 坐骑传送折扣（world_cmds portal 面 · MOUNT_POOL 的 discount）
try:
    _pool = W._cat_life.MOUNT_POOL
    _bad_d = [(m.get("key", m), m.get("discount"), _pct(m.get("discount", 0)))
              for m in _pool
              if isinstance(m, dict) and m.get("discount")
              and _pct(m["discount"]) != str(_half_up(m["discount"]))]
    check("4e 坐骑传送折扣全部 half-up", not _bad_d, "错：%s" % _bad_d)
except Exception as _exc:
    check("4e 坐骑折扣端到端可跑", False, "抛错 %s: %s" % (type(_exc).__name__, _exc))

# 4f 房屋恢复 / 回购（world_cmds house 面）
try:
    _hl = W._cat_life.HOUSE_LEVELS
    _bad_h = [(k, v.get("heal_pct"), _pct(v.get("heal_pct")))
              for k, v in _hl.items()
              if isinstance(v, dict) and isinstance(v.get("heal_pct"), (int, float))
              and _pct(v["heal_pct"]) != str(_half_up(v["heal_pct"]))]
    check("4f 房屋恢复率全部 half-up", not _bad_h, "错：%s" % _bad_h)
    _ref = W._cat_life.HOUSE_REFUND
    _bad_r = [(k, v, _pct(v)) for k, v in _ref.items()
              if isinstance(v, (int, float)) and _pct(v) != str(_half_up(v))]
    check("4g 房屋回购率全部 half-up", not _bad_r, "错：%s" % _bad_r)
except Exception as _exc:
    check("4f 房屋面端到端可跑", False, "抛错 %s: %s" % (type(_exc).__name__, _exc))

print("PASS=%d FAIL=%d" % (passed, failed))
sys.exit(1 if failed else 0)
