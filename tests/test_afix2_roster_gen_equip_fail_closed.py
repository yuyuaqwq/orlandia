# -*- coding: utf-8 -*-
r"""审计 afix2 自查新开口：百科装备「标准装备生成失败」不得静默降级成无属性视图。

原实现（content/economy_cmds.py::_roster_gen_equip）::

    try:
        _rids = ...
        if not _rids:
            return None
        return C.generate_roster_equip(_rids[0])
    except Exception:
        return None

那个 `except Exception: return None` 让**两个语义完全不同的 None 变得不可区分**：

* 形态 B「名册里没这一条」→ None = **正常**（调用点 `if _eq:` 少印几段是对的）
* 形态 A「生成抛错」（装备表坏 / 公式崩 / 宿主导出面缺件）→ None = **静默降级**

两个调用点（`_cmd_encyclopedia` 的装备单查与详情两支）都**只有 `if _eq:`、没有 else** ⇒
形态 A 一命中，**属性 / 词条 / 专属**三段整段消失，玩家看到的是一张
「有名字·有部位·有等级·有品质，但没有一条属性」的装备卡 —— **零报错**，
而装备是真的（名册里躺着 687 条，物品详情也照样印得出属性）。

数据面现状：`EQUIP_ROSTER` 687 条按名反查悬空 **0** ⇒ 今天无玩家可见差异，属**潜伏项**。
留判据是为了「今天潜伏、明天装备表一改就静默」的形状不再发生。

**本判据真调生产函数** `_roster_gen_equip`（不是重写一遍拼装）：只把真源
`content.drops.generate_roster_equip` 换成会抛的替身，其余全走真装配（`_engine_harness.C`）。
"""
import ast
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401  导入即完成 sys.path 装配（引擎根 + extends）
os.environ.setdefault("GWEN_TEST_MODE", "1")

from _engine_harness import C  # noqa: E402  真装配句柄（economy_cmds 里的 `C` 就是它）
import content.drops as D  # noqa: E402  生成的真源模块
import content.catalog_items as ci  # noqa: E402
import content.economy_cmds as EC  # noqa: E402

passed = failed = 0
from _check import bind_check  # noqa: E402  断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")

ER = ci.EQUIP_ROSTER
RID0 = list(ER)[0]
ROW0 = dict(ER[RID0])

_boom = {"n": 0}


def _raise_gen(*_a, **_k):
    _boom["n"] += 1
    raise RuntimeError("SIM 生成失败（模拟装备表坏/公式抛错）")


_orig = D.generate_roster_equip
D.generate_roster_equip = _raise_gen
try:
    # ---------------------------------------------------------------- §1 形态 A：生成抛错 ⇒ 必须抛
    caught = None
    got = "<未赋值：真抛了>"
    try:
        got = EC._roster_gen_equip(ROW0)
    except Exception as _e:  # noqa: BLE001
        caught = _e
    check("§1-1 生成抛错时不得返回 None（须上抛，不得静默变残卡）",
          caught is not None, "returned %r (= 静默降级成无属性视图)" % (got,))
    check("§1-2 抛的是 RuntimeError 且消息点名是哪件装备",
          isinstance(caught, RuntimeError) and ROW0.get("name", "\0") in str(caught),
          "caught=%r" % (caught,))
    check("§1-3 替身真被调到了（不是'异常压根没发生'的假通过）",
          _boom["n"] == 1, "boom called %d times" % _boom["n"])
    check("§1-4 原因用 from _e 保住（__cause__ 有值，不是把原异常吞了重写）",
          getattr(caught, "__cause__", None) is not None
          and "SIM 生成失败" in str(getattr(caught, "__cause__", "")),
          "__cause__=%r" % (getattr(caught, "__cause__", None),))

    # ---------------------------------------------------------------- §2 形态 B：名册没这条 ⇒ 仍返 None
    out_b = EC._roster_gen_equip({"name": "★名册里根本没有这一件★"})
    check("§2-1 名册没这一条仍返回 None（不能一刀切 fail-closed 误伤正常查询）",
          out_b is None, "returned %r" % (out_b,))
    check("§2-2 形态 B 不调生成器（None 的含义仍唯一）",
          _boom["n"] == 1, "boom called %d times" % _boom["n"])
finally:
    D.generate_roster_equip = _orig

# ---------------------------------------------------------------- §3 正常路一字未变
_ok = EC._roster_gen_equip(ROW0)
check("§3-1 正常条目照旧生成出装备 dict", isinstance(_ok, dict) and bool(_ok), "got %r" % (type(_ok).__name__,))
check("§3-2 生成的装备带 stats（百科属性段有内容可印）",
      bool((_ok or {}).get("stats")), "stats=%r" % ((_ok or {}).get("stats"),))

# ---------------------------------------------------------------- §4 防复发：函数体内不许再吞
_src = io.open(EC.__file__, encoding="utf-8").read()
_fn = next(n for n in ast.walk(ast.parse(_src))
           if isinstance(n, ast.FunctionDef) and n.name == "_roster_gen_equip")
_has = next(n for n in ast.walk(_fn) if isinstance(n, ast.ExceptHandler))
_body = _has.body
_ok_shape = (len(_body) == 1 and isinstance(_body[0], ast.Raise))
check("§4-1 except 分支必须只做 raise（不得 return None / pass）",
      _ok_shape, "except body=%r" % ([type(s).__name__ for s in _body],))
# return None 可能嵌在 `if not _rids:` 里 ⇒ 必须 walk，不能只看 _fn.body；
# 也要排除 except 分支内的 return（那是"吞"，§4-1 已单独判）
_in_handler = {id(x) for h in ast.walk(_fn) if isinstance(h, ast.ExceptHandler)
               for x in ast.walk(h)}
_returned = [n for n in ast.walk(_fn) if isinstance(n, ast.Return)
             and id(n) not in _in_handler
             and isinstance(n.value, ast.Constant) and n.value.value is None]
check("§4-2 函数体里只留一处 return None（= 名册没这一条）；多了就是又吞了一个形态",
      len(_returned) == 1, "return None 出现 %d 次" % len(_returned))

print("passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
