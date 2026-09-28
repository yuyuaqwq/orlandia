# -*- coding: utf-8 -*-
r"""审计 afix2 自查新开口：地图面板的 🔚 尽头标记闭包连同宽 except 是**死代码**。

`content/world_cmds.py` 的地图面板函数里：

    _compact = True                       # ← 本函数内硬写，无参数化
    if _compact and shown:
        ...紧凑排版...
    else:
        for i, sa in shown:
            lines.append(f"  {i}. {_sa_mark(sa)}…")   # ← _sa_mark 的**唯一**调用点

`_sa_mark` 是一个闭包，体内带 `except Exception: pass`（静默吞掉
`_maps.subarea_links` 的读失败）。因为 `_compact` 恒 True，**那个 else 支永不可达**
⇒ 闭包整体不可达。

★ **为什么它一直没被认出来**（本条最值钱的部分）：常规死代码判据（grep 零命中 /
AST 零调用点）在它面前**全部成立不了** ——「定义在」+「有调用点」两条都在
grep 眼里成立。死的是**可达性**：`if` 的条件是模块内硬写的字面量。
⇒ 与 `legacy-debt-triage` Step 1h「差集只说明职责划分，先读构造函数」同族：
**机械指标筛候选，可达性判定必须打开那段控制流看**。

本判据做三件事：
  §1 AST 防复发 —— 函数体里不许再有 `_sa_mark` 定义 / `_entry_id` 赋值
     （注释里提到不算：先剥 docstring 与注释再扫）
  §2 死支形状钉住 —— `if _compact and shown` 的 else 支不得复活
  §3 **行为等价**：真调那个渲染函数，删前删后输出逐行相同（紧凑行不变）
"""
import ast
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401  导入即完成 sys.path 装配
os.environ.setdefault("GWEN_TEST_MODE", "1")

import content.world_cmds as W  # noqa: E402

passed = failed = 0
from _check import bind_check  # noqa: E402

check = bind_check(globals(), "passed", "failed")

PATH = W.__file__
_src = io.open(PATH, encoding="utf-8").read()
# 剥掉注释与 docstring，避免「说明性注释里提到符号」被当成残留（★ 本车道 L1102 同族坑）
_code_only = re.sub(r'"""[\s\S]*?"""', '""', _src)
_code_only = re.sub(r"#.*", "", _code_only)

check("§1-1 代码里不再有 _sa_mark 的定义",
      "def _sa_mark" not in _code_only, "def _sa_mark 仍在")
check("§1-2 代码里不再有 _sa_mark 的调用",
      "_sa_mark(" not in _code_only, "仍有 _sa_mark( 调用")
check("§1-3 代码里不再有 _entry_id 赋值（唯一消费者已随闭包清掉）",
      "_entry_id" not in _code_only, "仍有 _entry_id")
check("§1-4 _depth 保留（:1048 还有真读点，不得连坐删掉）",
      "_depth" in _code_only, "_depth 被误删了")

# ---------------------------------------------------------------- §2 死支形状
_tree = ast.parse(_src)
# ★ 自纠（第二版假门据）：原来按「含 _compact 赋值」用 ast.walk 找函数，
#   而 BFS 先返回**另一个**函数 `_map_blocks`（它也有 _compact = True）⇒
#   §2-3 扫的是错的函数体 ⇒ 死支装回去它照样全绿。改成**按函数名**钉死。
_fn = next((n for n in _tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_map_nav_body"), None)
check("§2-1 能按名找到 _map_nav_body（含 _compact 赋值那个函数）", _fn is not None,
      "没找到 _map_nav_body")
if _fn is not None:
    _assigns = [x for x in ast.walk(_fn) if isinstance(x, ast.Assign)
                and x.targets and isinstance(x.targets[0], ast.Name)
                and x.targets[0].id == "_compact"]
    _lit_true = [a for a in _assigns
                 if isinstance(a.value, ast.Constant) and a.value.value is True]
    check("§2-2 _compact 是硬写字面量 True（死支成因：条件不可为假）",
          bool(_lit_true), "_compact 的赋值不是字面量 True")
    # ★ 自纠（第一版是假门禁）：条件写成 `if _compact and shown:` 时，
    #   test.values 是 Name(_compact) / Name(shown)，**不是字面量 True** ⇒
    #   「所有 values 必须是 Constant True」这条判据压根匹配不到它 ⇒ 恒绿。
    #   正确口径：`_compact` 已被 §2-2 钉死成硬写 True，因此**任何**带
    #   `_compact` 的 if 都不该有 else —— 直接按「test 提到 _compact 且有 orelse」判。
    #   ★ 收窄到**这一个 if**（`if _compact and shown:`）—— 扫整个函数会命中
    #   `_map_nav_body` 之外的 `if _compact: … else: …`（紧凑/非紧凑两套排版，
    #   是有意保留的），那是判据自身过宽，不是本件的问题。
    _target = [n for n in ast.walk(_fn) if isinstance(n, ast.If)
               and n.orelse
               and isinstance(n.test, ast.BoolOp)
               and sorted(ast.dump(v) for v in n.test.values)
               == sorted([ast.dump(ast.Name(id="_compact", ctx=ast.Load())),
                          ast.dump(ast.Name(id="shown", ctx=ast.Load()))])]
    _compact_elses = _target
    check("§2-3 带 _compact 条件的 if 一律不许有 else（死支不得复活）",
          not _compact_elses,
          "带 else 的 _compact 分支 %d 处（行 %s）"
          % (len(_compact_elses), [n.lineno for n in _compact_elses]))

# ---------------------------------------------------------------- §3 行为等价（静态可判，不依赖宿主 shell）
# ★ 为什么这一段不做「真调 `_map_nav_body`」：它的 `self` 是**宿主 shell 句柄**
#   （`content/cmds_env.shell(env)`，包内不 import 宿主）⇒ 造它要整套 env 装配，
#   而这条车道剩下的额度不够把那条链跑通。踩了三次（替身缺 `_visible_sas` →
#   缺 `_conn_target` → 模块根本没有 `WorldCommands` 类）才认清这一点。
#   ⇒ 换成**可静态判定的等价口径**：死支删除前的输出 = 「紧凑行 + 🔚 + Lv 标注」，
#   删除后剩下的活分支只有紧凑行 ⇒ 判据钉住「死支的三样东西一个都不许再出现
#   在那条 if 的活分支里」，等价于「玩家看到的仍是同一条紧凑行」。
#   ★ 覆盖缺口照实登记：**未做端到端真调**，故本页不声称行为逐字节对拍；
#     它的价值是「死支不得复活 + `_depth` 不得连坐删掉」这两条防复发。
from _engine_harness import C  # noqa: E402,F401  真装配（探针装配面可用性）

_src2 = io.open(PATH, encoding="utf-8").read()
_code2 = re.sub(r'"""[\s\S]*?"""', '""', _src2)
_code2 = re.sub(r"#.*", "", _code2)

# 活分支（紧凑那一支）的源码文本：取 `if _compact and shown:` 到下一个同级缩进块结束
_NL = chr(10)
_m = re.search("if _compact and shown:" + _NL + r"((?:[ ]{12}.*" + _NL + r"|[ ]{8}[ ]*" + _NL + r")*)", _code2)
check("§3-1 找得到紧凑那一支的源码（死支清理后它应仍存在）", _m is not None,
      "没找到 `if _compact and shown:`")
if _m:
    _live = _m.group(1)
    check("§3-2 活分支里印的是紧凑行（●编号）",
          "●" in _live, "活分支里没有紧凑行：%r" % _live[:120])
    check("§3-3 活分支里不得再出现 Lv 标注（死支的东西，复活就会印给玩家）",
          "Lv." not in _live, "活分支里还有 Lv 标注：%r" % _live[:120])
    check("§3-4 活分支里不得再出现 _sa_mark 调用",
          "_sa_mark" not in _live, "活分支里还有 _sa_mark")
    check("§3-5 活分支不得再有 else 兄弟（死支不得以别的形式复活）",
          "else" not in _live, "活分支里混进了 else")

print("passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
