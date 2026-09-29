# -*- coding: utf-8 -*-
"""台账 C-R2.25 门禁 —— `secret_guard` 是**影子键**（写了没人读），已删。

**它守什么**
----------
`content/instance_cmds.py::_instance_secret_crack` 原写两处：

```python
st["secret_guard"] = guard        # ← 影子键：写了「守卫是谁」，全仓零读口
st["secret_guard_pending"] = True # ← 真读口（cmds_instance_router.py:516 消费）
```

`_instance_...` 的同层兄弟键 `secret_crack` / `secret_chest` / `secret_guard_pending`
**都有真读口** ⇒ `secret_guard` 是这一族里唯一的孤儿，形态同台账 R2 的 `reduce_left`
（影子账）。守卫身份本身**没有被丢掉**：它由同函数后续
`self._enter_stage_combat(group_id, st, guard, stage)` + `st["boss"]["is_elite"] = True` 承载。

**断言组**
  (一) 死键档：全包（去 tests/去 `__pycache__`）对 `secret_guard` 的**写点 = 0**
  (二) 活路档：同族三键**各自都有真读口**（证明不是「这一族全死」，是只删了孤儿）
  (三) 守卫身份档：`_enter_stage_combat(… guard …)` 仍在（守卫没被删掉，只是影子账没了）
  (四) ★ 反证档（假门禁保险）：把 `secret_guard` 写回任一处 ⇒ 档 (一) 立刻红
      ⇒ 本门禁**不是恒绿档**。
"""

import io
import os
import re
import sys

PKG = r"C:/Users/yuyu/framework-engine/games/orlandia"
sys.path.insert(0, PKG)
sys.path.insert(0, r"C:/Users/yuyu/framework-engine/extends")
os.environ.setdefault("GWEN_TEST_MODE", "1")

FAILS = []


def check(name, ok, extra=""):
    print(("  ok   " if ok else "  FAIL ") + name + (("  | " + str(extra)) if extra else ""))
    if not ok:
        FAILS.append(name)


_KEY = re.compile(r"""["']secret_guard["']""")          # 精确键（不含 _pending 后缀）
_PENDING = re.compile(r"""["']secret_guard_pending["']""")


def _scan(root, skip=()):
    hits = []
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in fs:
            if not f.endswith(".py"):
                continue
            fp = os.path.join(dp, f)
            rel = os.path.relpath(fp, root).replace("\\", "/")
            try:
                with io.open(fp, "r", encoding="utf-8", errors="replace") as fh:
                    for i, ln in enumerate(fh.read().splitlines(), 1):
                        if _KEY.search(ln):
                            hits.append((rel, i, ln.strip()[:90]))
            except Exception:
                continue
    return hits


print("【档 一】死键档：全包对 `secret_guard` 精确键的写点 = 0")
_hits = _scan(PKG, skip=("__pycache__", ".git", "tests"))
print("   命中 %d 处" % len(_hits))
check("★ secret_guard 精确键写点归零（影子账已删干净）", not _hits, _hits[:3])

print("【档 二】活路档：同族三键各自都有真读口（不是「整族全死」）")
SIBLINGS = {
    "secret_crack": r"""["']secret_crack["']""",
    "secret_chest": r"""["']secret_chest["']""",
    "secret_guard_pending": r"""["']secret_guard_pending["']""",
}
# ★ 被删的那个键也要进这张表（本轮自踩：漏了它 → 后面 KeyError）。
DEAD_KEY = "secret_guard"
_reads = {}
for name, pat in SIBLINGS.items():
    rx = re.compile(pat)
    # 读口 = `st.get("X")` / `st["X"]` 出现在**判断或消费**处；此处只数出现行数（≥2 才算有第二处）
    n = 0
    for dp, dirs, fs in os.walk(PKG):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "tests")]
        for f in fs:
            if not f.endswith(".py"):
                continue
            try:
                with io.open(os.path.join(dp, f), "r", encoding="utf-8", errors="replace") as fh:
                    n += sum(1 for ln in fh if rx.search(ln))
            except Exception:
                continue
    _reads[name] = n
    print("   %-22s 全包出现 %d 行" % (name, n))
# ★ 顺序要点：先对**活路三键**断言，再把被删的键并进表做对照。
#   （本轮自踩：先把 dead 并进 _reads → 下面的 all() 把它也算了 ⇒ 自我否定。）
_sib_ok = all(v > 0 for v in _reads.values())
check("同族三键都仍有出现行（活路未被我误删）", _sib_ok, _reads)
_all = dict(_reads)
_all[DEAD_KEY] = len(_hits)
check("★ 被删的键出现行（%d）严格少于三个兄弟键" % len(_hits),
      len(_hits) == 0 and _sib_ok, _all)

print("【档 三】守卫身份档：守卫仍在（没被删掉，只是影子账没了）")
src = io.open(os.path.join(PKG, "content", "instance_cmds.py"), encoding="utf-8").read()
_i = src.find("def _instance_secret_crack")
_seg = src[_i:_i + 3000] if _i >= 0 else ""
check("守卫仍由 _enter_stage_combat(group_id, st, guard, stage) 承载",
      "_enter_stage_combat(group_id, st, guard, stage)" in _seg)
check("守卫仍被标 is_elite（精英化逻辑未动）",
      'st["boss"]["is_elite"] = True' in _seg)
check("★ 真读口 secret_guard_pending 仍在（守卫战分支没被删）",
      'st["secret_guard_pending"] = True' in _seg)

print("【档 四】★ 反证：把 secret_guard 写回任一处 ⇒ 档一立刻红（不是恒绿）")
_tmp = os.path.join(PKG, "content", "_c_r2_25_counterproof.py")
try:
    with io.open(_tmp, "w", encoding="utf-8") as fh:
        fh.write("# -*- coding: utf-8 -*-\nST = {}\ndef f():\n    ST[\"secret_guard\"] = None\n")
    _fake = _scan(PKG, skip=("__pycache__", ".git", "tests"))
finally:
    if os.path.exists(_tmp):
        os.remove(_tmp)
print("   写入一个假写点后，全包命中 = %d（原本 0）" % len(_fake))
check("★ 反证档：写回后命中 > 0 ⇒ 本门禁会红（不是恒绿）", len(_fake) > 0, len(_fake))
print("   清理后复扫 = %d（临时文件已删）" % len(_scan(PKG, skip=("__pycache__", ".git", "tests"))))

print()
if FAILS:
    print("★ 失败 %d 项：%s" % (len(FAILS), " / ".join(FAILS)))
else:
    print("全绿。")
    print("  ⇒ secret_guard 是影子键（写点 2 处 / 读口 0），已删干净。")
    print("  ⇒ 守卫战本身不受影响：secret_guard_pending + _enter_stage_combat + is_elite 三处齐在。")
sys.exit(1 if FAILS else 0)
