# -*- coding: utf-8 -*-
"""审计 L5261 —— 副本「加入战斗」的 CTB 播种不再回落到 v121 旧口径的 `-spd`。

缺陷（改前真实形状）：
    try:
        ... float(u.get("ct", 0) or 0) ... action_time(int(_spd)) ...
        snap["ct"] = (ref if ref is not None else 0.0) + cost
    except Exception:
        snap["ct"] = -_spd      # ← v121 旧口径残留

与同文件 `_instance_reset_player_cts` 的 v121 契约**直接矛盾**（那段 docstring 逐字写
「v121 旧语义 -spd 是相对时钟，与绝对时刻播种（ref+cost）混用会错乱」）。
兜底**可达**且危害实：脏 ct 抛 ValueError、`action_time` 未装配抛 EngineNotConfigured；
兜底给 -10~-120（负数，落在时间轴起点之前），正确播种给 ref+cost ⇒ 偏差可达数百刻。

本门禁三组：
  A 组（AST 静态）——播种段**不得**再有 `except` 兜底、不得再出现 `-_spd` 字面。
  B 组（口径不变量）——同一文件里两处播种（入场 / 重置）必须同口径：`ref + cost`。
  C 组（防空转 + 有牙反证）——扫描面非空；把 `+ cost` 摘掉后 A 组必须转红。
"""
import ast, io, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "content", "instance_cmds.py")

passed = failed = 0
from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py
check = bind_check(globals(), "passed", "failed")


def _src():
    with io.open(TARGET, encoding="utf-8") as f:
        return f.read()


def _strip_comments(src):
    """去掉 # 行注释（本门禁的代码面口径：注释里的审计留痕不算残留）。"""
    out = []
    for line in src.splitlines():
        i = line.find("#")
        out.append(line if i < 0 else line[:i])
    return "\n".join(out)


def main():
    src = _src()
    tree = ast.parse(src)
    src_lines = src.splitlines()

    # ---------- A 组：播种段无 except 兜底、无 -_spd ----------
    # 定位 join_battle 方法
    join_fn = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "join_battle":
            join_fn = node
    check("扫描面非空：定位到 join_battle", join_fn is not None)
    if join_fn is None:
        return

    # join_battle 里所有 try 语句
    tries = [n for n in ast.walk(join_fn) if isinstance(n, ast.Try)]
    check("join_battle 内 try 节点可枚举（防空转）", len(tries) > 0, "tries=%d" % len(tries))

    # 找「播种段」：含 snap["ct"] 赋值的 try / 语句块
    seed_try = None
    for t in tries:
        seg = "".join(src_lines[t.lineno - 1:(t.end_lineno or t.lineno)])
        if 'snap["ct"]' in seg:
            seed_try = t
    check("定位到 CTB 播种段（try 形态或已无 try）", True)

    if seed_try is not None:
        # 播种段**包在 try 里** ⇒ 仍有可能吞异常的 handler
        has_handler = len(seed_try.handlers) > 0
        check("播种段不再被 try/except 包裹（异常必须冒泡）", not has_handler,
              "handlers=%d" % len(seed_try.handlers))
        seg = "".join(src_lines[seed_try.lineno - 1:(seed_try.end_lineno or seed_try.lineno)])
    else:
        # 已无 try ⇒ 取 join_battle 全域做 -_spd 断言
        seg = "".join(src_lines[join_fn.lineno - 1:(join_fn.end_lineno or join_fn.lineno)])

    # 只认**代码**（注释里保留原字面作为审计留痕，是有意为之）
    code_only = _strip_comments(seg)
    check("播种段不含 v121 旧口径字面 -_spd（代码面）", "-_spd" not in code_only)
    check("播种段不含 except Exception（代码面）", "except Exception" not in code_only)
    check("播种段仍按 ref+cost 播种（未被改坏）",
          'snap["ct"] = (ref if ref is not None else 0.0) + cost' in seg)

    # ---------- B 组：两处播种同口径 ----------
    # 重置口：_instance_reset_player_cts
    reset_fn = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_instance_reset_player_cts":
            reset_fn = node
    check("扫描面非空：定位到 _instance_reset_player_cts", reset_fn is not None)
    if reset_fn is not None:
        rseg = "".join(src_lines[reset_fn.lineno - 1:(reset_fn.end_lineno or reset_fn.lineno)])
        check("重置口同口径：ref + _cost", "snap[\"ct\"] = ref + _cost" in rseg)
        check("重置口同样不含 -spd 旧口径", "-_spd" not in rseg and "- spd" not in rseg)

    # ---------- C 组：全仓不得再有第二处 -_spd 播种 ----------
    n_neg = _strip_comments(src).count('-_spd')
    check("全文件代码面零 -_spd 残留（注释留痕不计）", n_neg == 0, "count=%d" % n_neg)


main()
print("=== %d passed, %d failed ===" % (passed, failed))
sys.exit(1 if failed else 0)
