#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""门禁：内置守卫拦截句（★ P-11 内容半边）—— 装配 / 回话 / fail-closed 反证 / 逐字冻结。

引擎侧（`saintess_engine/host/runtime.py::Host._guard_text`，P-11 2026-09-27）把**内置守卫**
（`player` / `battle`）拦下时的回话交给内容侧：宿主在 `Host(register_hint=…, battle_hint=…)`
上只传**中性键**（引擎 `host/runtime.py::GUARD_KEYS` 全集：`guard.register_missing` /
`guard.battle_missing`），句子由内容侧经 `config.mount(guard_text_fn=…)` 给
（形状 `fn(key) -> str | None`）——宿主面因此**零游戏词**（宿主自己的零游戏知识门禁
`scripts/check_host_boundary.py` 原先恒红：那两句里的「角色」「战斗」是业务词）。

**内容侧这一半**就是本文件要看的三件事：

  [1] **装了**：装配期 `content/apply.py::install_engine` 把它挂在 `config.mount(...)` 上；
      钩子身份 == 包内 `content/apply.py::guard_text`，形状 `fn(key)`；该函数源码**零中文**
      （句子真源在文案表）；表里两格的键 == 引擎的中性键全集（引擎加键/改名 ⇒ 当场红）。
  [2] **回话**：宿主按 P-11 口径配好（两个参数传**键**、明确「不在战斗中」）⇒ 引擎公开守卫口
      `Host.builtin_guards()` 出的那两句**逐字 = 改前宿主 `main.py` 那两句**（冻在这里当基线）
      **且**逐字 = 文案表槽位渲染（现算，不手写镜像）；键被**原样**问过去；走 `run_guards`
      （引擎真派发那条路）结果一致。另加一条反向：把表里那句临时改掉 ⇒ 回话跟着变
      ⇒ 证明「代码只传槽位、真源在表」。
  [3] **反证有牙（fail-closed 没被放宽）**：临时把钩子撤成 `None` ⇒ 同一处**必抛**
      `EngineNotConfigured`（不静默编一句、**也不回落到键名**）；装回去 ⇒ 逐字回到那两句。
      ★ 这条有牙的前提 = **装配幂等**（`content/apply.py::_MOUNTED`）——否则 `optional_hook`
        的惰性装配器会把钩子又挂回来，反证就成了空转 ⇒ 故先把该前提断言出来。
  [4] **撤改验证**：文案表里把槽位拿掉 ⇒ `guard_text` 当场抛（缺句子时不许把键名当回话交出去）。
  [5] **静态守卫**：那两句整句不许出现在 `content/*.py` 里（文案真源只有文案表）。

跑法：python tests/test_guard_text.py（exit=0 全绿）
"""
import ast
import inspect
import os
import pathlib
import re
import sys
import textwrap

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _paths  # noqa: E402

# 私有库（*.db 已 gitignore；全量跑器会给每文件一份，`setdefault` = 不覆盖它）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_paths.TESTS_DIR, "test_guard_text.db"))

from _check import bind_check                    # noqa: E402
from _engine_harness import boot                  # noqa: E402  （import 即装配：包路径 + 引擎通道）

passed = 0
failed = 0
check = bind_check(globals(), "passed", "failed")

H = boot()                                        # 引擎 Host + 包内声明/处理器/文案表（幂等）

from saintess_engine import config as CFG         # noqa: E402
from saintess_engine.host.env import Env          # noqa: E402
from saintess_engine.host.runtime import GUARD_KEYS   # noqa: E402
from content import apply as A                    # noqa: E402
from content import texts as T                    # noqa: E402

HOOK = "guard_text_fn"
#: ★ 基线（**改前**宿主 `main.py` 那两句，逐字冻结在这里当判据源）——
#:   这两句就是玩家原先会在守卫拦下时看到的话；P-11 之后必须**一字不变**地从包里出来。
FROZEN = {
    GUARD_KEYS[0]: "未找到你的角色档 —— 请先创建角色。",
    GUARD_KEYS[1]: "你现在不在战斗中。",
}
#: 中文字符（「代码里不许写中文」的判据）
CJK = re.compile(r"[\u4e00-\u9fff]")

_env_none = Env(uid="u-p11", group_id="g-p11", player={}, text="测试")
_env_have = Env(uid="u-p11", group_id="g-p11", player={"uid": "u-p11"}, text="测试")
_saved_cfg = (H.host.register_hint, H.host.battle_hint, H.host.battle_check)


def _guard(name, env):
    """走引擎**公开**守卫口（`Host.builtin_guards()`）—— 与 `Host.invoke` 里的派发同一处。"""
    return H.host.builtin_guards()[name](env)


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
print("\n[1] 装了：装配期把 guard_text_fn 挂在 config 上")
hook = CFG._HOOKS.get(HOOK)
check("★ 装配期已挂 `%s`（缺 = 守卫一拦就抛）" % HOOK, hook is not None, repr(hook))
check("★ 挂的就是包内 `content/apply.py::guard_text`（不是引擎/宿主临时拼的）",
      hook is A.guard_text, getattr(hook, "__module__", "?"))
check("可选通道读口（`optional_hook`）读到同一个函数",
      CFG.optional_hook(HOOK) is A.guard_text, repr(CFG.optional_hook(HOOK)))
check("形状 = `fn(key)`（引擎按中性键问；`guard_text` 只收一个形参）",
      list(inspect.signature(A.guard_text).parameters) == ["key"],
      list(inspect.signature(A.guard_text).parameters))
bad_cjk = [s for s in _code_strings_of(A.guard_text) if CJK.search(s)]
check("★ 该函数源码零中文（句子真源在文案表，代码只传槽位）", not bad_cjk, bad_cjk[:3])
check("装配幂等（`install_engine` 只跑一次）—— [3] 那条反证有牙的前提",
      A._MOUNTED is True, repr(getattr(A, "_MOUNTED", None)))
check("★ 文案表里两格都在（键 = 引擎给的中性键）",
      all(T.table().spec(k) is not None for k in GUARD_KEYS),
      [T.table().spec(k) is not None for k in GUARD_KEYS])
check("★ 代码里的字面量键集 == 引擎 `GUARD_KEYS` 全集（引擎加键/改名 ⇒ 这条红）",
      tuple(A.GUARD_TEXT_KEYS) == tuple(GUARD_KEYS), repr(A.GUARD_TEXT_KEYS))
check("★ 键名与引擎 `GUARD_KEYS` 全集逐个对齐（引擎加键/改名 ⇒ 这条红）",
      sorted(T.table().spec(k).key for k in GUARD_KEYS if T.table().spec(k))
      == sorted(GUARD_KEYS), sorted(GUARD_KEYS))


# ══════════════════════════════════════════════════════════════════════════
# [2] 回话（宿主只传键 → 引擎问读口 → 文案表渲染）
# ══════════════════════════════════════════════════════════════════════════
print("\n[2] 回话：宿主传键 ⇒ 引擎问读口 ⇒ 逐字 == 改前那两句")
try:
    H.host.register_hint, H.host.battle_hint = GUARD_KEYS[0], GUARD_KEYS[1]
    H.host.battle_check = lambda uid, gid: False          # 明确「不在战斗中」
    _seen = []
    _real = CFG._HOOKS[HOOK]

    def _spy(key):
        _seen.append(key)
        return _real(key)

    CFG._HOOKS[HOOK] = _spy
    try:
        _reg, _bat = _guard("player", _env_none), _guard("battle", _env_have)
    finally:
        CFG._HOOKS[HOOK] = _real
    check("★ 键被**原样**问过去（宿主给的是键，不是句子）",
          _seen == [GUARD_KEYS[0], GUARD_KEYS[1]], repr(_seen))
    check("★ 无档 ⇒ 拦截句逐字 == 改前宿主那两句（玩家看到的字一个没动）",
          _reg == FROZEN[GUARD_KEYS[0]] and _bat == FROZEN[GUARD_KEYS[1]], "%r / %r" % (_reg, _bat))
    check("★ 逐字 == 文案表槽位现算的渲染（不手写镜像：真源在表里）",
          _reg == T.static(GUARD_KEYS[0]) and _bat == T.static(GUARD_KEYS[1]), "%r / %r" % (_reg, _bat))
    check("有档 ⇒ 不拦（读口只管拦截句，不参与放行判定）", _guard("player", _env_have) is None)
    from saintess_engine.host.env import run_guards
    check("走 `run_guards`（引擎真派发那条路）结果一致",
          run_guards(["player"], _env_none, builtin=H.host.builtin_guards()) == FROZEN[GUARD_KEYS[0]]
          and run_guards(["player"], _env_have, builtin=H.host.builtin_guards()) is None)
    # 反向（注入生效）：改表值 ⇒ 回话跟着变（代码里没有第二份句子）
    spec = T.table().spec(GUARD_KEYS[0])
    saved_value = spec.value
    try:
        spec.value = "【探针替换】没档"
        check("★ 反证（注入生效）：改文案表的值 ⇒ 回话跟着变（句子不是写死在代码里的）",
              _guard("player", _env_none) == "【探针替换】没档", repr(_guard("player", _env_none)))
    finally:
        spec.value = saved_value
    check("还原表值 ⇒ 回话逐字回到真源那句", _guard("player", _env_none) == FROZEN[GUARD_KEYS[0]])
finally:
    H.host.register_hint, H.host.battle_hint, H.host.battle_check = _saved_cfg


# ══════════════════════════════════════════════════════════════════════════
# [3] 反证有牙（撤掉装配 ⇒ fail-closed）
# ══════════════════════════════════════════════════════════════════════════
print("\n[3] 反证有牙：撤掉装配 ⇒ 必抛 EngineNotConfigured（两态验证）")
_saved_hook = CFG._HOOKS.get(HOOK)
try:
    H.host.register_hint, H.host.battle_hint = GUARD_KEYS[0], GUARD_KEYS[1]
    H.host.battle_check = lambda uid, gid: False
    for _nm, _env in (("player", _env_none), ("battle", _env_have)):
        CFG._HOOKS[HOOK] = None
        try:
            _guard(_nm, _env)
            check("★ 撤掉装配（%s）⇒ 必抛 EngineNotConfigured" % _nm, False,
                  "没抛：fail-closed 被放宽了（回落到键名？）")
        except CFG.EngineNotConfigured as exc:
            check("★ 撤掉装配（%s）⇒ 必抛 EngineNotConfigured（点名 `%s`）" % (_nm, HOOK),
                  HOOK in str(exc), str(exc)[:88])
        CFG._HOOKS[HOOK] = _saved_hook
    check("两态：装回去 ⇒ 又逐字回到表里那两句（撤改没留后遗症）",
          _guard("player", _env_none) == FROZEN[GUARD_KEYS[0]]
          and _guard("battle", _env_have) == FROZEN[GUARD_KEYS[1]])
finally:
    CFG._HOOKS[HOOK] = _saved_hook
    H.host.register_hint, H.host.battle_hint, H.host.battle_check = _saved_cfg


# ══════════════════════════════════════════════════════════════════════════
# [4] 撤改验证：真源里缺那句 ⇒ 当场抛（不许把键名当回话交出去）
# ══════════════════════════════════════════════════════════════════════════
print("\n[4] 撤改验证：真源里把那格拿掉 ⇒ `guard_text` 当场抛（两态）")
import json                                                        # noqa: E402
import tempfile                                                    # noqa: E402

_cut = GUARD_KEYS[1]
_tmp = os.path.join(tempfile.mkdtemp(prefix="p11_guard_spec_"), "text_specs.json")
_spec_obj = json.loads(open(T.spec_path(), encoding="utf-8").read())
_spec_obj.pop(_cut, None)                       # 只拿掉守卫那一格（别的照旧）
with open(_tmp, "w", encoding="utf-8", newline="\n") as _f:
    _f.write(json.dumps(_spec_obj, ensure_ascii=False, indent=2) + "\n")
_saved_path = T.SPEC_PATH
_raised = None
try:
    T.SPEC_PATH = _tmp
    T.reload()
    try:
        A.guard_text(_cut)
    except Exception as exc:                    # noqa: BLE001 —— 只要「当场抛」这一件事
        _raised = "%s: %s" % (type(exc).__name__, exc)
finally:
    T.SPEC_PATH = _saved_path
    T.reload()
check("★ 真源里缺那格 ⇒ `guard_text` 当场抛（不把键名当回话交出去）",
      bool(_raised), (_raised or "（没抛）")[:70])
check("两态：还原真源 ⇒ 同一个键照旧取得到句子（撤改没留后遗症）",
      A.guard_text(_cut) == FROZEN[_cut], repr(A.guard_text(_cut)))
check("两态：两个键都还在表里", all(T.table().spec(k) is not None for k in GUARD_KEYS))


# ══════════════════════════════════════════════════════════════════════════
# [5] 静态守卫
# ══════════════════════════════════════════════════════════════════════════
print("\n[5] 静态守卫：两句整句不许出现在 `content/*.py` 里")
_hits = [p.name for p in sorted(pathlib.Path(_paths.PKG_ROOT, "content").glob("*.py"))
         if any(s and s in p.read_text(encoding="utf-8") for s in FROZEN.values())]
check("★ 文案真源只有文案表：整句不许出现在 `content/*.py` 里", not _hits, "%s" % (_hits,))
check("★ 引擎给的两个中性键都是 ASCII（键名不含游戏词）",
      all(k == k.encode("ascii", "ignore").decode() for k in GUARD_KEYS), list(GUARD_KEYS))
print("  · 键 → 槽位：%s" % " · ".join(GUARD_KEYS))
print("  · 逐字：%s / %s" % (FROZEN[GUARD_KEYS[0]], FROZEN[GUARD_KEYS[1]]))


# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 74)
print("结果：通过 %d / %d" % (passed, passed + failed))
print("=" * 74)
sys.exit(1 if failed else 0)
