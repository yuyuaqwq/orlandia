#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""门禁：路由未命中回话（★ P-54 内容半边）—— 装配 / 回话 / fail-closed 反证。

引擎侧（`saintess_engine/host/runtime.py::Host._miss_reply`，P-54 2026-09-26）把
「玩家敲了一个没命中任何包内声明的词」的回话改成**必需注入**：`_optional_hook(
"route_miss_text_fn")` 为 None ⇒ 抛 `EngineNotConfigured`（引擎零玩家文案、也不提宿主
命令名 —— 改前那句里带着 `<prefix>help`）。**内容侧这一半**就是本文件要看的三件事：

  [1] **装了**：装配期 `content/apply.py::install_engine` 把它挂在 `config.mount(...)` 上；
      钩子身份 == 包内 `content/apply.py::route_miss_text`，形状 `fn(text, prefix)`；
      该函数源码**零中文**（只传槽位，句子真源在文案表）。
  [2] **回话**：真跑一次「故意不命中」的输入（走引擎 `Host.route`，不是直调内部函数）：
      回话非空、逐字等于文案表 `route.miss` 的渲染、带上玩家原词、点名的指令名
      **是本包真有的指令名**（判据 = 声明表里**可见**声明的 `usage` 首词；不用
      `declared_hit()` 单条兜 —— 它容忍「帮助」带尾巴，会把不存在的名字放过），且一个
      `/`、一个拉丁字母都不许有（杜绝 `/help` 这类宿主命令名漏给玩家）。
      另加一条反向：把表里那句话临时改掉 ⇒ 回话跟着变 ⇒ 证明「代码只传槽位、真源在表」。
  [3] **反证有牙（fail-closed 没被放宽）**：临时把钩子撤成 `None` ⇒ 同一个输入**必抛**
      `EngineNotConfigured`（不静默编一句、也不退回旧句）；装回去 ⇒ 逐字回到表里那句。
      ★ 这条有牙的前提 = **装配幂等**（`content/apply.py::_MOUNTED`）——否则 `optional_hook`
        的惰性装配器会把钩子又挂回来，反证就成了空转 ⇒ 故先把该前提断言出来。

跑法：python tests/test_route_miss_text.py（exit=0 全绿）
"""
import ast
import inspect
import os
import re
import sys
import textwrap

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _paths  # noqa: E402

# 私有库（*.db 已 gitignore；全量跑器会给每文件一份，`setdefault` = 不覆盖它）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_paths.TESTS_DIR, "test_route_miss_text.db"))

from _check import bind_check                    # noqa: E402
from _engine_harness import boot                  # noqa: E402  （import 即装配：包路径 + 引擎通道）

passed = 0
failed = 0
check = bind_check(globals(), "passed", "failed")

H = boot()                                        # 引擎 Host + 包内声明/处理器/文案表（幂等）

from saintess_engine import config as CFG         # noqa: E402
from content import apply as A                    # noqa: E402
from content import texts as T                    # noqa: E402

HOOK = "route_miss_text_fn"
MISS_KEY = "route.miss"
#: 故意不命中的输入（每条先断言「确实没命中」——否则这条就退化成「命中测试」，不再有牙）
MISS_WORDS = ["歪比巴卜", "离奇之词", "咕噜咕噜噜"]
#: 中文字符（「代码里不许写中文」的判据）
CJK = re.compile(r"[\u4e00-\u9fff]")

WORD = MISS_WORDS[0]


def _miss(word):
    """走引擎公开路由口（未命中 → `_miss_reply` → 内容侧钩子）。"""
    return H.host.route({"uid": "u-probe", "group_id": "g-probe", "text": word}, {}, word)


def _code_strings_of(fn):
    """函数里除 docstring 之外的字符串字面量（docstring 是写给开发者的，不算玩家文案）。"""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    fdef = tree.body[0]
    doc = ast.get_docstring(fdef, clean=False)
    out = []
    for node in ast.walk(fdef):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if doc is not None and node.value == doc:
                continue
            out.append(node.value)
    return out


# ══════════════════════════════════════════════════════════════════════════
# [1] 装了（装配期挂 hook）
# ══════════════════════════════════════════════════════════════════════════
print("\n[1] 装了：装配期把 route_miss_text_fn 挂在 config 上")
hook = CFG._HOOKS.get(HOOK)
check("★ 装配期已挂 `%s`（缺 = 玩家敲没命中的词时一句回话都拿不到）" % HOOK,
      hook is not None, repr(hook))
check("★ 挂的就是包内 `content/apply.py::route_miss_text`（不是引擎/宿主临时拼的）",
      hook is A.route_miss_text, getattr(hook, "__module__", "?"))
check("可选通道读口（`optional_hook`）读到同一个函数",
      CFG.optional_hook(HOOK) is A.route_miss_text, repr(CFG.optional_hook(HOOK)))
params = list(inspect.signature(A.route_miss_text).parameters)
check("形状 = `fn(text, prefix)`（引擎口径；`prefix` 收下但不用）",
      params[:2] == ["text", "prefix"], params)
bad_cjk = [s for s in _code_strings_of(A.route_miss_text) if CJK.search(s)]
check("★ 该函数源码零中文（句子真源在文案表，代码只传槽位）", not bad_cjk, bad_cjk[:3])
check("文案表里有 `%s`（钩子指向的那条）" % MISS_KEY,
      T.table().spec(MISS_KEY) is not None, repr(T.table().spec(MISS_KEY)))


# ══════════════════════════════════════════════════════════════════════════
# [2] 回话（真跑未命中）
# ══════════════════════════════════════════════════════════════════════════
print("\n[2] 回话：故意不命中的输入 → 非空 + 指向本包真有的声明")
for w in MISS_WORDS:
    check("前提：%r 确实没命中任何**可见**包内声明" % w,
          H.host.declared_hit(w) is None, repr(H.host.declared_hit(w)))
    check("前提：%r 不以宿主前缀 %r 开头（不走宿主命令通道）" % (w, H.host.prefix),
          not w.startswith(H.host.prefix))

want = T.text(MISS_KEY, word=WORD)
got = _miss(WORD)
check("★ 未命中 ⇒ 有回话（非空、每段非空）",
      bool(got) and all(str(x).strip() for x in got), repr(got))
check("★ 回话逐字 = 文案表 `%s` 的渲染" % MISS_KEY, got == [want],
      "got=%r want=%r" % (got, want))
line = got[0] if got else ""
check("★ 回话带上玩家原词（槽位真的传进去了）", WORD in line, line)
check("★ 回话零宿主命令痕迹（无 `/`、无拉丁字母 —— 杜绝 `/help` 那类名字）",
      "/" not in line and not re.search(r"[A-Za-z]", line), line)
names = re.findall(r"『([^』]+)』", line)
check("★ 回话给了「下一步」：点了至少一个指令名", bool(names), line)
# 「本包真有的指令名」的判据 = 声明表（`content/data/commands.json` → 引擎注册表）里
# **可见**声明的 `usage` 首词（玩家敲的那个词）。★ 不能用 `declared_hit()` 单条兜：
# 它的正则允许「帮助」后跟尾巴（实测 `declared_hit("帮助我")` → `help_cmd`），
# 那样「点了个不存在的名字」照样过 —— 本门禁会被这条假绿放过去。
declared_words = set()
for _s in H.host.commands.visible():
    _u = (getattr(_s, "usage", "") or "").strip()
    if _u:
        declared_words.add(_u.split()[0])
check("前提：本包可见声明的「指令名」集合非空（判据源不是空表）",
      len(declared_words) > 0, len(declared_words))
for nm in names:
    check("★ 点名的『%s』是本包真有的指令名（声明表 `usage` 首词）" % nm,
          nm in declared_words,
          "『%s』不在 %d 个可见声明的指令名里" % (nm, len(declared_words)))
    check("★ 点名的『%s』引擎真能路由到（declared_hit 非空）" % nm,
          H.host.declared_hit(nm) is not None, repr(H.host.declared_hit(nm)))

# 反向（注入生效）：改表值 ⇒ 回话跟着变（代码里没有第二份句子）
probe_value = "【探针替换】没接住「{word}」"
spec = T.table().spec(MISS_KEY)
saved_value = spec.value
try:
    spec.value = probe_value
    check("★ 反证（注入生效）：改文案表的值 ⇒ 回话跟着变（句子不是写死在代码里的）",
          _miss(WORD) == ["【探针替换】没接住「%s」" % WORD], repr(_miss(WORD)))
finally:
    spec.value = saved_value
check("还原表值 ⇒ 回话逐字回到真源那句", _miss(WORD) == [want], repr(_miss(WORD)))


# ══════════════════════════════════════════════════════════════════════════
# [3] 反证有牙（撤掉装配 ⇒ fail-closed）
# ══════════════════════════════════════════════════════════════════════════
print("\n[3] 反证有牙：撤掉装配 ⇒ 必抛 EngineNotConfigured（两态验证）")
check("前提：装配幂等（`install_engine` 只跑一次）—— 否则惰性装配器会把钩子又挂回来，"
      "下面这条反证就成空转",
      A._MOUNTED is True, repr(getattr(A, "_MOUNTED", None)))
saved_hook = CFG._HOOKS.get(HOOK)
try:
    CFG._HOOKS[HOOK] = None
    try:
        _miss(WORD)
        check("★ 撤掉装配 ⇒ 必抛 EngineNotConfigured", False,
              "没抛：fail-closed 被放宽了（引擎又自己编兜底？）")
    except CFG.EngineNotConfigured as exc:
        check("★ 撤掉装配 ⇒ 必抛 EngineNotConfigured（且点名 `%s`）" % HOOK,
              HOOK in str(exc), str(exc)[:100])
finally:
    CFG._HOOKS[HOOK] = saved_hook
check("两态：装回去 ⇒ 又逐字回到表里那句（撤改没留后遗症）",
      _miss(WORD) == [want], repr(_miss(WORD)))


# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 74)
print("结果：通过 %d / %d" % (passed, passed + failed))
print("=" * 74)
sys.exit(1 if failed else 0)
