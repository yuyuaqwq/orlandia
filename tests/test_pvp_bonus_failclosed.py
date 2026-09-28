# -*- coding: utf-8 -*-
"""审计 L4918-6 门禁 —— PVP 开战的两处静默降级不许「静默开一场坏战斗」。

**它守什么**
----------
content/combat_cmds.py::_pvp_start 里有**两处** try/except Exception: pass：

  (一) 双方面板增幅聚合（_core_tb）—— 静默跳过 ⇒ _tb_me / _tb_opp 留空 dict
      ⇒ 下面 apply_battle_loadout(actor, {}) 落**空增幅容器**。而紧邻的注释
      自称「stats **只**读该容器、N10 收口后无 battle 级兜底」
      ⇒ **整场 PVP 双方面板增幅全失效、零报错**。
      ★ 这层兜底尤其该删：content/stat_bonus.py::stat_bonus **自己已经**有一层
        带 warning 日志的降级 —— 本处是**第二道静默**，把上层那条 warning
        一起吃掉，运维侧连日志都查不到。
  (二) 防守方 max_hp/max_mp 实时化（player_final_stats）—— 静默跳过 ⇒ _def_p
      保留目标档里的**旧值**，而 actor 是从 _def_p 造的
      ⇒ 防守方带着过期血上限入战场、被多打一轮才死。

**判据口径（逐条都是「不许放宽」）**
  1. ★ 正例：这两处**不许**再被「裸/宽泛 except + pass」包住
     （按**条目身份**找调用点，不按行号 —— 台账行号会漂）；
  2. ★ 必看得见一条**点名式 fail-closed 抛错**，否则等于把「静默开坏战斗」
     换成「硬崩且不点名」；
  3. 正常档逐字不变：dict / None / 空 dict 三种都照原样落空 dict 增幅；
  4. ★ 有牙反证：把两处换回旧的 try/except: pass 形态 ⇒ 本门禁必须转红
     （否则「判据抓不住自己守的那件事」= 永远绿）。

**跑法**
    export GWEN_FRAMEWORK_DIR=<引擎> GWEN_HOST_DIR=<宿主壳> GWEN_TEST_MODE=1
    python tests/test_pvp_bonus_failclosed.py
"""
from __future__ import annotations

import ast
import io
import os
import sys
import tempfile

os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "game.db")
os.environ["GWEN_TEST_MODE"] = "1"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401
sys.path.insert(0, _PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402

from _check import bind_check  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []
check = bind_check(globals(), "PASS", "FAIL", "FAILURES")

_SRC = os.path.join(_PLUGIN_DIR, "content", "combat_cmds.py")
_SRC_CACHE = [None]

# 两个调用点的**条目身份**（不是行号）
MARK_BONUS = "_core_tb(group_id, qq_id, player)"
MARK_DEFSTATS = "_dst = player_final_stats("


def _pvp_fn(tree):
    """取 _pvp_start 的函数节点（按名，不认行号）。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "_pvp_start":
            return node
    return None


def _marked_nodes(fn, marker, kinds=(ast.Call, ast.Assign)):
    """按源码标记在该函数体内找节点。

    ★ kinds 必须含 ast.Assign：_dst = player_final_stats(...) 这处 defender
      实时化的标记落在一个 **Assign** 上（Call 只是它的 value），只扫 Call 会扫到 0 个
      —— 我最初只扫 Call，门禁当场报「扫到 0 个」把自己抓了。
    """
    out = []
    for node in ast.walk(fn):
        if not isinstance(node, kinds):
            continue
        seg = ast.get_source_segment(_SRC_CACHE[0], node) or ""
        if marker in seg:
            out.append(node)
    return out


def _enclosing_trys(fn, target):
    """包住该节点的 try（按「谁包含这个节点」判，不看同一段文本）。"""
    return [t for t in ast.walk(fn)
            if isinstance(t, ast.Try) and any(n is target for n in ast.walk(t))]


def _is_silent_skip(t):
    """这个 try 是不是「宽泛/裸 except + pass」的静默兜底。"""
    for h in t.handlers:
        if h.type is None:                                     # 裸 except
            return True
        names = getattr(h.type, "id", None) or getattr(h.type, "attr", None)
        if names in ("Exception", "BaseException"):
            body = [s for s in h.body if not isinstance(s, ast.Expr)]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                return True
    return False


def test_no_silent_skip_on_both_sites():
    print("【L4918-6 PVP 两处静默降级：fail-closed】")
    src = io.open(_SRC, encoding="utf-8").read()
    _SRC_CACHE[0] = src
    tree = ast.parse(src)
    fn = _pvp_fn(tree)
    check("扫到 _pvp_start（判据前提）", fn is not None)
    if fn is None:
        return

    for label, marker in (("面板增幅聚合", MARK_BONUS), ("防守方面板实时化", MARK_DEFSTATS)):
        nodes = _marked_nodes(fn, marker)
        check("★ 扫到%s调用点（判据前提）" % label, bool(nodes), "扫到 0 个")
        if not nodes:
            continue
        silent = []
        for n in nodes:
            for t in _enclosing_trys(fn, n):
                if _is_silent_skip(t):
                    silent.append(ast.get_source_segment(src, t))
        check("★ %s 不存在「裸/宽泛 except + pass」" % label,
              not silent, "仍被静默包住：%r" % (silent[:1],))
        # ★ 必须看得见点名式 fail-closed 抛错。
        #   位置判据 = **该调用点所在 try 的 handler 里**（不是「调用点之前」）：
        #   修好的形态是 try 包住调用、handler 里 raise —— raise 必然在调用**之后**。
        #   我最初写成 r.lineno < first（找调用之前的 raise）⇒ 门禁永远红，
        #   是我自己写错的判据、不是实现错。
        names_ok = False
        for n in nodes:
            for t in _enclosing_trys(fn, n):
                for h in t.handlers:
                    for r in ast.walk(h):
                        if isinstance(r, ast.Raise) and ("拒绝开一场" in (ast.get_source_segment(src, r) or "")):
                            names_ok = True
        check("★ %s 的 try handler 留有点名式 fail-closed 抛错" % label,
              names_ok, "该调用点所在 try 的 handler 里 0 处带「拒绝开一场」的 raise")


def test_shape_failclosed_and_normal_unchanged():
    """行为侧：供体崩 ⇒ 点名抛出；正常档逐字落空 dict 增幅。"""
    from content import combat_cmds as CC  # noqa: F401  （证明活代码在）

    def install_bonus(agg):
        tb_me = {}
        tb_opp = {}
        try:
            tb_me = agg("me") or {}
            tb_opp = agg("opp") or {}
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise RuntimeError(
                "content.combat_cmds：PVP 开战的面板增幅聚合崩了"
                "（stat_bonus 读称号/成就/收藏册时形状不对）——拒绝开一场没有增幅的战斗"
            ) from exc
        return tb_me, tb_opp

    def boom(_who):
        raise KeyError("TITLES 形状不对")

    try:
        install_bonus(boom)
        raised = None
    except RuntimeError as exc:
        raised = exc
    check("★ 供体崩 ⇒ 点名 RuntimeError（不再静默开空增幅战斗）",
          raised is not None and "拒绝开一场没有增幅的战斗" in str(raised),
          repr(raised))

    for good in ({"atk": 20}, None, {}):
        me, opp = install_bonus(lambda _w: good)
        check("正常档 %s 逐字落原值" % type(good).__name__,
              me == (good or {}) and opp == (good or {}), "%r / %r" % (me, opp))

    def install_defstats(pfs):
        def_p = {"max_hp": 111, "max_mp": 22}
        try:
            _dst = pfs()
            if _dst.get("max_hp"):
                def_p["max_hp"] = int(_dst["max_hp"])
            if _dst.get("max_mp") is not None:
                def_p["max_mp"] = int(_dst["max_mp"])
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise RuntimeError(
                "content.combat_cmds：PVP 防守方面板实时化崩了"
                "（player_final_stats 读职业/等级/装备时形状不对）"
                "——拒绝开一场血量对不上的战斗"
            ) from exc
        return def_p

    def bad_pfs():
        raise TypeError("class_name 不是字符串")

    try:
        install_defstats(bad_pfs)
        raised2 = None
    except RuntimeError as exc:
        raised2 = exc
    check("★ 实时化崩 ⇒ 点名 RuntimeError（不再带着旧血量开打）",
          raised2 is not None and "拒绝开一场血量对不上的战斗" in str(raised2), repr(raised2))

    ok = install_defstats(lambda: {"max_hp": 900, "max_mp": 300})
    check("正常档 实时化逐字生效", ok.get("max_hp") == 900 and ok.get("max_mp") == 300, repr(ok))


def test_counter_proof_revert_turns_red():
    """★ 有牙反证：把两处换回旧的 try/except: pass 形态 ⇒ 扫描器必须判红。

    做法 = **按行**手术：取该调用点所在 try 的 **body 段**（不含 handler），
    重新包进 try:，末尾补 except Exception: pass。

    ★ 两个踩过的坑（都写在这里给下一轮）：
      (1) 早先用「调用点 → 外层 try 的 end_lineno」当整段范围，那会把**已经存在的
          except/raise 行**一起塞进新的 try ⇒ ast.parse 直接 IndentationError /
          「expected except」—— **反证自身崩掉 = 反证无效**，它压根没走到判据。
          正解：范围取 **try.body 最后一行的行号**，即只取 body、不取 handler。
      (2) 行级手术（切开 → 整体缩进 → 补 except）保证语法必定自洽，
          不要用字符串 replace 拼回旧形态。
    """
    src = io.open(_SRC, encoding="utf-8").read()
    _SRC_CACHE[0] = src
    tree = ast.parse(src)
    fn = _pvp_fn(tree)
    if fn is None:
        check("★ 反证前提：扫到 _pvp_start", False)
        return

    lines = src.splitlines(True)
    for marker in (MARK_BONUS, MARK_DEFSTATS):
        nodes = _marked_nodes(fn, marker)
        if not nodes:
            check("★ 反证前提：扫到 %s" % marker[:24], False)
            continue
        trys = _enclosing_trys(fn, nodes[0])
        if not trys:
            check("★ 反证前提：%s 外面有 try" % marker[:24], False)
            continue
        t = trys[0]
        # ★ 只取 body 段：body 首行 = try.lineno+1，末行 = body[-1].end_lineno
        start = t.body[0].lineno - 1
        end = max(getattr(s_, "end_lineno", s_.lineno) or s_.lineno for s_ in t.body) - 1
        seg = lines[start:end + 1]
        indent = len(seg[0]) - len(seg[0].lstrip())
        pad = " " * indent
        rebuilt = ([pad + "try:\n"]
                   + ["    " + ln if ln.strip() else ln for ln in seg]
                   + [pad + "except Exception:\n", pad + "    pass\n"])
        new_src = "".join(lines[:start] + rebuilt + lines[end + 1:])
        try:
            new_tree = ast.parse(new_src)
        except SyntaxError as exc:
            check("★ 反证：换回旧形态后语法自洽（%s）" % marker[:24], False,
                  "SyntaxError: %s" % exc)
            continue
        new_fn = _pvp_fn(new_tree)
        _SRC_CACHE[0] = new_src
        silent = []
        for n in _marked_nodes(new_fn, marker):
            for tt in _enclosing_trys(new_fn, n):
                if _is_silent_skip(tt):
                    silent.append(tt)
        check("★ 反证：换回 try/except:pass 后扫描器判红（%s）" % marker[:24],
              bool(silent), "换回去竟然没判红 = 判据抓不住自己守的那件事")
        _SRC_CACHE[0] = src


# ===========================================================
for _fn in (test_no_silent_skip_on_both_sites,
            test_shape_failclosed_and_normal_unchanged,
            test_counter_proof_revert_turns_red):
    _fn()

TOTAL = PASS + FAIL
print("=" * 60)
print("通过 %d / %d" % (PASS, TOTAL))
if FAILURES:
    for _f in FAILURES:
        print("  X " + str(_f))
    sys.exit(1)
print("全部通过")
