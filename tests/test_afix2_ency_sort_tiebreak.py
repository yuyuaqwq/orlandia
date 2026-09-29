# -*- coding: utf-8 -*-
"""审计 B2 自开口（族：并列值后截断的排序 ——「取前 N」由插入序决定）。

真开口（两处，同仓同一渲染面「百科 总览/材料」，同一种机制）：
  · economy_cmds.py 装备总览 `_pool[0]`：(slot,quality) 内取最高 lv 的一件代表
      —— 3 组并列（helm/orange lv=98 共 3 件、legs/purple lv=90、necklace/orange lv=95）
  · economy_cmds.py 材料百科 `_rep[:3]`：每类取价格最高的 3 件作代表
      —— 6 个分类的第 3/4 名价格并列（兽材 p=395 有 4 件、精华 355 有 7 件、收藏 300 有 3 件…）
两处注释都自称「稳定 / 不随插入序漂移」，实跑反插入序**6/6 全变**：
  兽材 原序「磐涡龟甲、云殿铠甲、古龙鳞」→ 反序「磐涡龟甲、雷鸟羽、深渊犬牙」。

修法 = 并列时加次级键（name），非并列格**逐字不变**。
本判据钉住「并列格稳定 + 非并列格不变 + 覆盖面自检（域里真有并列格）」。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401

from _check import bind_check  # noqa: E402

passed = failed = 0
check = bind_check(globals(), "passed", "failed")

sys.path.insert(0, str(_paths.PKG_ROOT))
from content import catalog_items as _cit  # noqa: E402

_SRC = os.path.join(str(_paths.PKG_ROOT), "content", "economy_cmds.py")
_lines = open(_SRC, encoding="utf-8").read().split("\n")

# ---------------------------------------------------------- 1 材料百科 [:3]
_by_type = {}
for _k, _m in _cit.MATERIALS.items():
    _by_type.setdefault(_m.get("type") or "?", []).append(_m.get("name", _k))


def _rep(names):
    """生产口径：价格降序，name 作次级键，截前 3"""
    return sorted(names, key=lambda n: (-int(_cit.MATERIALS_BY_NAME[n].get("price", 0)), n))[:3]


def _rep_naive(names):
    """★ 反证用：修法**之前**的形状（没有次级键）"""
    return sorted(names, key=lambda n: -int(_cit.MATERIALS_BY_NAME[n].get("price", 0)))[:3]


_tie_cats = []
for _t, _names in _by_type.items():
    if len(_names) <= 3:
        continue
    _p = sorted(_names, key=lambda n: -int(_cit.MATERIALS_BY_NAME[n].get("price", 0)))
    if int(_cit.MATERIALS_BY_NAME[_p[2]].get("price", 0)) == int(_cit.MATERIALS_BY_NAME[_p[3]].get("price", 0)):
        _tie_cats.append(_t)

check("覆盖面自检：材料域里真有「截断点并列」的分类（否则判据恒绿=假门禁）",
      len(_tie_cats) >= 1,
      "材料域 %d 条 / %d 个分类里找不到第 3、4 名同价的分类 —— "
      "要么数据变了（要重钉），要么本判据挑错了集合" % (len(_cit.MATERIALS), len(_by_type)))

_drifting = [t for t in _tie_cats
             if _rep(list(_by_type[t])) != _rep(list(reversed(_by_type[t])))]
check("材料百科并列分类：反插入序后代表 3 个**不变**（%d 个并列分类全覆盖）" % len(_tie_cats),
      not _drifting,
      "这些分类的「代表性 3 个」仍随插入序漂移：%s" % _drifting)

_naive_drift = [t for t in _tie_cats
                if _rep_naive(list(_by_type[t])) != _rep_naive(list(reversed(_by_type[t])))]
check("★ 证明原写法真的会漂（反证：没有次级键时必须变）",
      len(_naive_drift) == len(_tie_cats),
      "没有次级键的旧形状在 %d/%d 个并列分类上竟然不变 —— 判据证明力不足"
      % (len(_naive_drift), len(_tie_cats)))

_all_stable = all(_rep(list(v)) == _rep(list(reversed(v))) for v in _by_type.values())
check("材料百科**全部分类**（不止并列那些）反插入序后一律不变", _all_stable,
      "有分类在非并列情形下也漂了 —— 次级键写错了方向或类型")

# ---------------------------------------------------------- 2 装备总览 [0]
_g = {}
for _r in _cit.EQUIP_ROSTER.values():
    _g.setdefault((_r.get("slot"), _r.get("quality")), []).append(_r)

_tie_groups = []
for (_slot, _q), _items in _g.items():
    if not _slot or not _q or not _items:
        continue
    _mx = max(int(_r.get("lv", 0) or 0) for _r in _items)
    if sum(1 for _r in _items if int(_r.get("lv", 0) or 0) == _mx) > 1:
        _tie_groups.append((_slot, _q, _items))

check("覆盖面自检：装备名册里真有「最高 lv 并列」的 (slot,quality) 组",
      len(_tie_groups) >= 1,
      "EQUIP_ROSTER %d 件里找不到并列组 —— 数据变了要重钉判据" % len(_cit.EQUIP_ROSTER))


def _top(items):
    """生产口径：lv 降序、name 次级键，取第一件"""
    return sorted(items, key=lambda r: (-int(r.get("lv", 0) or 0), str(r.get("name", ""))))[0]


def _top_naive(items):
    return sorted(items, key=lambda r: -r.get("lv", 0))[0]


_drift_e = [(s, q) for (s, q, it) in _tie_groups
            if _top(list(it)) != _top(list(reversed(it)))]
check("装备总览并列组：反插入序后「代表一件」不变（%d 组全覆盖）" % len(_tie_groups),
      not _drift_e,
      "这些组的代表件仍随插入序漂移：%s" % _drift_e)

_nd = [(s, q) for (s, q, it) in _tie_groups
       if _top_naive(list(it)) != _top_naive(list(reversed(it)))]
check("★ 证明原写法真的会漂（反证：装备面没有次级键时必须变）",
      len(_nd) == len(_tie_groups),
      "旧形状在 %d/%d 组上竟然不变 —— 判据证明力不足" % (len(_nd), len(_tie_groups)))

# ------------------------------------------------- 3 源码形状（钉住单源键）
_mat_site = [i for i, l in enumerate(_lines, 1) if "_rep = sorted(_names" in l]
check("材料百科那一行带 name 次级键",
      bool(_mat_site) and "key=lambda n: (-int(" in _lines[_mat_site[0] - 1]
      and _lines[_mat_site[0] - 1].rstrip().endswith(", n))[:3]"),
      "economy_cmds.py 上材料百科的排序键 %r —— 次级键不在（改法被回退？）"
      % ([_lines[i - 1].strip()[:120] for i in _mat_site[:1]],))

_eq_site = [i for i, l in enumerate(_lines, 1) if "_pool = sorted((r for r in _items" in l]
check("装备总览那一行带 name 次级键", bool(_eq_site),
      "economy_cmds.py 上找不到装备总览的 _pool 排序")
if _eq_site:
    _ctx = "\n".join(_lines[_eq_site[0] - 1:_eq_site[0] + 1])
    check("装备总览次级键是 name（不是别的键）", 'str(r.get("name", ""))' in _ctx,
          "装备总览次级键形状变了：%r" % _ctx[:120])

# ------------------------------- 3b 真调生产排序行（判据不许自备副本）
#  ★ 前 4 条数据断言用的是本文件里的 _rep/_top —— 它们证明「加次级键后稳定」，
#    但**证明不了生产那一行真的加了**（反证时 4 条仍绿）。这一条从**源码里抠出
#    生产排序的 key 函数并真调一次**，让数据断言与源码绑在一起。
import ast as _ast  # noqa: E402


def _prod_key(line_no):
    """取生产那一行的 key= 表达式，**编译成真函数**（自己写小解释器会漏闭包捕获）"""
    # 括号配平取完整语句（生产那行可能跨两行）
    _buf, _bal = "", 0
    for _i in range(line_no - 1, len(_lines)):
        _buf += _lines[_i] + " "
        _bal += _lines[_i].count("(") - _lines[_i].count(")")
        if _bal == 0 and "(" in _buf:
            break
    _stmt = _ast.parse(_buf.strip()).body[0]
    _seg = _stmt.value if isinstance(_stmt, _ast.Assign) else _stmt
    while isinstance(_seg, _ast.Subscript):      # `sorted(...)[0:3]` / `sorted(...)[0]`
        _seg = _seg.value
    for _k in _seg.keywords:
        if _k.arg == "key":
            _mod = _ast.Expression(body=_k.value)
            _ast.fix_missing_locations(_mod)
            return eval(compile(_mod, "<prod-key>", "eval"),
                        {"_cit": _cit, "str": str, "int": int, "float": float})
    return None


_mat_key = _prod_key(_mat_site[0]) if _mat_site else None
_eq_key = _prod_key(_eq_site[0]) if _eq_site else None
if _mat_key is not None:
    _bad = []
    for _t in _by_type:
        _a = sorted(_by_type[_t], key=_mat_key)[:3]
        _b = sorted(list(reversed(_by_type[_t])), key=_mat_key)[:3]
        if _a != _b:
            _bad.append(_t)
    check("★ 真调生产排序键（从源码抠出来跑）：材料百科全分类反插入序后不变",
          not _bad, "生产那一行的 key 实跑仍漂：%s" % _bad)
if _eq_key is not None:
    _bade = [(s_, q_) for (s_, q_, it) in _tie_groups
             if sorted(it, key=_eq_key)[0] != sorted(list(reversed(it)), key=_eq_key)[0]]
    check("★ 真调生产排序键（从源码抠出来跑）：装备总览并列组反插入序后不变",
          not _bade, "生产那一行的 key 实跑仍漂：%s" % _bade)

# ------------------------------------------------------------ 4 报告
print("并列分类 %d：%s" % (len(_tie_cats), _tie_cats))
print("并列装备组 %d：%s" % (len(_tie_groups), [(s, q) for s, q, _ in _tie_groups]))
print("check: %d pass, %d fail" % (passed, failed))
sys.exit(1 if failed else 0)
