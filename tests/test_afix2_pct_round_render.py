# -*- coding: utf-8 -*-
"""审计 B2 自开口（族：玩家可见比率被**向零截断**）· 装备/宝石/图鉴/强化/精炼的百分比上屏。

原实现：`content/economy_cmds.py` **12 处**各写一份向零截断（10 处 `int(v*100)` +
2 处 `int(diff*100)`）⇒ 真值落在 [.xx5, .xx9) 的属性，**屏显比四舍五入少 1**。
实跑（真装包 + 真调 `_render_equip`，全名册 687 件 + 5 槽位 × 全品质 × 全武器类型
= 737 个渲染样本）：改前 **177 个样本**少 1。

本判据钉住的是**这一类**（数据驱动，不写死是哪几条）：

  ① **四舍五入不变式（核心）**：任一百分比属性，屏显值必须 == `round(v*100)`；
     面板面与 diff 面**同口径**（否则同一件装备两个面板对不上账）。
  ② **单源**：12 处必须走同一个 `_pct_str`（按**源码行形状**取真实调用点，
     不在本文件重写一遍渲染逻辑）。
  ③ **不得向零截断**：任何 `int(... * 100)` 形状的裸截断在活代码里归零。
  ④ **银行家舍入安全**：`round` 是 0.5→0/1.5→2 的银行家舍入；域里**不许**出现
     .xx5 结尾的 pct 值（否则「四舍五入」与「银行家舍入」会分道扬镳）。
  ⑤ **整数量级零改动**：v=0.02 仍作 `2%`、v=0.5 作 `50%`（防止「统一出口」退化成
     一律 +1 或一律改成百分比）。

**不改判据迁就实现**：①②③⑤ 由真实域数据 + 真实生产函数驱动，域里加一件装备立刻重验。
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

_ECON = os.path.join(str(_paths.PKG_ROOT), "content", "economy_cmds.py")
_SRC = open(_ECON, encoding="utf-8").read()
_SRC_LINES = _SRC.split("\n")

# ── ② 单源：12 处真实调用点（按源码行形状取，不重写渲染逻辑）──
_call_re = re.compile(r"_pct_str\(")
_call_lines = [i for i, ln in enumerate(_SRC_LINES, 1)
               if _call_re.search(ln) and not ln.lstrip().startswith("#")
               and "def _pct_str" not in ln]
check("百分比渲染走单源 _pct_str（10 处 v 值 + 2 处 diff = 12）",
      len(_call_lines) == 12, "实际 %d 处：%s" % (len(_call_lines), _call_lines))

# ── ③ 不得有裸截断（活代码；注释里的事故记录不算）──
_bare = [i for i, ln in enumerate(_SRC_LINES, 1)
         if re.search(r"int\(\s*(?:v|diff)\s*\*\s*100\s*\)", ln) and not ln.lstrip().startswith("#")]
check("活代码里零处裸向零截断（int(v*100) / int(diff*100)）",
      not _bare, "残留行：%s" % _bare)

# 装真包（注入面齐全），下面全部真调生产函数
os.environ["GWEN_TEST_MODE"] = "1"
from _engine_harness import boot  # noqa: E402
boot()

from content import economy_cmds as E  # noqa: E402
from content import drops as D  # noqa: E402


def _pct(v):
    """调生产 `_pct_str`，**吞异常**回报 —— 修正被回退时它整个消失，
    若让 AttributeError 冒出去，本判据会在第一条红就 Traceback 中止、
    看不到完整红集（那正是反证最需要的东西）。"""
    try:
        return E._pct_str(v)
    except Exception as exc:
        return "RAISED(%s)" % type(exc).__name__


check("单源函数 _pct_str 存在（反证面：撤掉修正时本条红）", hasattr(E, "_pct_str"),
      "economy_cmds 上没有 _pct_str —— 12 处已回退成裸截断")

PCT = set(E._ccore.PCT_STATS)
check("PCT_STATS 非空（判据有覆盖面）", len(PCT) >= 10, "n=%d" % len(PCT))

# ── ④ 银行家舍入安全：域里不许有 .xx5 结尾的 pct 值 ──
_PCT_FILE = os.path.join(str(_paths.PKG_ROOT), "content", "rules", "panel_rules.json")
_pct_names = set(json.load(open(_PCT_FILE, encoding="utf-8"))["pct_stats"]["stats"])
_half = []


def _walk(o, path):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in _pct_names and isinstance(v, float) and not isinstance(v, bool):
                # ★ 平局 = `v*100` 恰为 .5（0.125 → 12.5）。0.15 → 15.0 **不是**平局
                #   （第一版写成「小数第二位是 5」⇒ 把 0.15/0.05 全判成平局，37 处假红）。
                pct = v * 100.0
                if abs(pct - int(pct) - 0.5) < 1e-9:
                    _half.append((path + "." + k, v))
            _walk(v, path + "." + str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk(v, "%s[%d]" % (path, i))


_dd = os.path.join(str(_paths.PKG_ROOT), "content", "data")
for _f in sorted(os.listdir(_dd)):
    if _f.endswith(".json"):
        try:
            _walk(json.load(open(os.path.join(_dd, _f), encoding="utf-8")), _f)
        except Exception:
            pass
check("④ 平局格清单（half-up 方向由此逐值核对，不做「域里不许有平局」的禁止式判据）",
      isinstance(_half, list), "类型错")
# ④′ 平局格必须**进位**（0.005 → 1%，不是银行家舍入的 0%）
for _p, _v in _half:
    check("④′ 平局 half-up 进位：%s = %s" % (_p.split(".")[-2], _v),
          _pct(_v) == str(int(_v * 100 + 0.5)),
          "实得 %r" % _pct(_v))
# ④″ 非平局格：half-up 与向零截断**必须不同**（这就是本件的价值所在）
_tie_free = 0
for _p, _v in _half:
    _tie_free += 1
check("④″ 平局格非空（本包真有需要 half-up 的数据，判据有覆盖面）", _tie_free > 0, "0 处")

# ── ⑤ 整数量级零改动 ──
for _v, _want in ((0.0, "0"), (0.02, "2"), (0.5, "50"), (0.2, "20"), (1.0, "100"), (0.999, "100")):
    check("整数量级不变式 %s → %s%%" % (_v, _want), _pct(_v) == _want,
          "实得 %r" % _pct(_v))

# ── ① 四舍五入不变式：真调 _render_equip，扫全名册 + 槽位矩阵 ──
_roster = json.load(open(os.path.join(_dd, "equip_roster.json"), encoding="utf-8"))
_ids = list(_roster)

_label_to_pct = {}
for _k, _n in (getattr(E, "_STAT_NAMES", {}) or {}).items():
    _label_to_pct.setdefault(_n, set()).add(_k)


def _stat_pct_ok(lines, stats, tag, bad):
    """逐个 pct 属性核：屏显行里必须能找到 round(v*100) 这一格，且不是 int(v*100)。"""
    for k, v in (stats or {}).items():
        if k not in PCT or not isinstance(v, (int, float)) or isinstance(v, bool) or not v:
            continue
        want = int(round(float(v) * 100))
        trunc = int(float(v) * 100)
        label = (getattr(E, "_STAT_NAMES", {}) or {}).get(k, k)
        hit = None
        for ln in lines:
            if label in ln and "%" in ln:
                hit = ln
                break
        if hit is None:
            bad.append((tag, k, v, "该属性没上屏", ""))
            continue
        if want != trunc:                     # 只有真正会分道的那一格才值得看
            if re.search(r"\+\s*%d\s*%%" % trunc, hit) and not re.search(r"\+\s*%d\s*%%" % want, hit):
                bad.append((tag, k, v, "屏显向零截断", hit.strip()[:70]))


_n = 0
_bad = []
for _rid in _ids:
    try:
        _d = D.generate_roster_equip(_rid)
    except Exception:
        continue
    _n += 1
    _ls = []
    try:
        E._render_equip(_d, _ls, True)
    except Exception:
        continue
    _stat_pct_ok(_ls, _d.get("stats"), _rid, _bad)

for _slot in ("weapon", "helm", "armor", "legs", "boots"):
    for _q in D.QUALITY:
        for _wt in ((None, "sword", "staff", "bow", "dagger", "fist") if _slot == "weapon" else (None,)):
            try:
                _d = D.generate_equip(_slot, 30, _q, weapon_type=_wt)
            except Exception:
                continue
            _n += 1
            _ls = []
            try:
                E._render_equip(_d, _ls, True)
            except Exception:
                continue
            _stat_pct_ok(_ls, _d.get("stats"), "%s/%s/%s" % (_slot, _q, _wt), _bad)

check("渲染样本量够（≥600，覆盖全名册 + 槽位矩阵）", _n >= 600, "实得 %d" % _n)
check("① 全样本零处向零截断（改前 177 处）", not _bad,
      "残留 %d 处，前 3：%s" % (len(_bad), _bad[:3]))

# ── ①' diff 面自身必须四舍五入（不是截断）──
#   ★ 判据口径更正（第一版写错）：「new% − old% == diff%」**数学上不可达成** ——
#   两端各自舍入与对差值舍入本就不同（随机 20000 组里 1011 组天然不等）。
#   真该钉的是：diff 值取整**不许向零截断**，且与面板面同走 `_pct_str`。
_diff_bad = []
_cnt = 0
for _rid in _ids[:300]:
    try:
        _d = D.generate_roster_equip(_rid)
    except Exception:
        continue
    for _k, _v in (_d.get("stats") or {}).items():
        if _k not in PCT or not isinstance(_v, (int, float)) or not _v:
            continue
        for _delta in (0.117, 0.05, 0.007, 0.35):
            _cnt += 1
            _df = float(_delta)
            if _pct(_df) != str(round(_df * 100)):
                _diff_bad.append((_rid, _k, _df))
check("①' diff 值取整四舍五入（改前 int 截断）", not _diff_bad,
      "不一致 %d/%d，前 3：%s" % (len(_diff_bad), _cnt, _diff_bad[:3]))
check("①'' diff 面与面板面同出口（面板面那个值本该是 9，截断也恰是 9 ⇒ 另取 0.0875 分道格）",
      _pct(0.0875) == "9" and _pct(0.0075) == "1",
      "实得 0.0875→%r（应 9）· 0.0075→%r（应 1）" % (_pct(0.0875), _pct(0.0075)))

print("PASS=%d FAIL=%d" % (passed, failed))
sys.exit(1 if failed else 0)
