# -*- coding: utf-8 -*-
"""台账 C-R2.8 门禁 —— `apply._read_json`（全包共享读口）必须 fail-closed（不许静默空表）。

**它守什么**
----------
`content/apply.py::_read_json` 是**全包共享读口**（改前 6 个直接调用方：
`apply` 自身 ×2 / `affix` ×2 / `item_templates` ×1 / `mech/equip` ×2 惰性）。
它原先是 `except Exception: return default` —— 缺文件与坏 JSON 都把表清零而**零报错**
（黑盒实测：两种失败都得到 `{}`）⇒ 下游症状：

| 表 | 条数 | 清零后的症状 |
|---|---|---|
| `classes.json` | 8 | `basic_skill_of()` 恒 `None` -> 引擎回落 `basic_fallback`（物理 `atk*1.0`）；法师/牧师全 int、atk=0 ⇒ **普攻 0 伤害** |
| `monsters.json` | 330 `ms_*` | `monster_skill(key)` 恒 `None` -> 引擎回落默认技能 |
| `affixes.json` | 76 | 词缀池整类消失（装备数值权威失据） |
| `legendary_effects.json` | 93 | 传说专属效果整类消失 |
| `tips.json` | 58 | 提示语整类消失 |

症状与内容改动**无法区分**、也无法从报错栈定位到读文件那一步 ⇒ 收成 fail-closed，
口径照抄本包**已有**的三处先例：`content/catalog_space.py::_read` ·
`content/config.py::_read_table` · `content/_domainio.py:read_data_json_strict`。

**★ 与另两处的区别（为什么它们不在本门禁里）** ——
`content/dialogue.py` / `content/dialogue_conds.py` 的 `_read_domain` 是**同形**问题
（吞掉读失败 ⇒ 39 棵对话树 / 70 条主线任务静默清零），但它们被
`tests/test_u1i4_dialogue_frozen.py` 的 **E 栏冻结基准**钉住（`_E_KEYS` 含这两段、
frozen/live 双 sha256 都 pin 死）⇒ 改它们必须先重采冻结基准，属另一件，已在台账登记。

**断言组**
  (一)   正常态：五张表真读到**非空且等于真源条数** + 真实消费者面（防「永远抛」式假修）
  (二)(三)(四) 缺文件 / 坏 JSON / 空表 `{}` / 非 dict -> RuntimeError 点名**表名 + 路径**
  (五)   有牙反证：猴补 `json.load` 抛异常时必须抛（静默返回 `{}` = 门禁没牙）
  (六)   只读：源文件 sha256 前后一致
  (七)   `default` 实参与惰性 `try/except` 兜底都已删（留默认参数 = 兜底的影子还在）
  (八)   **6 个调用方零残留**带 `default` 实参（第一版就死在这条：漏改调用方 => TypeError）

**跑法**（自跑风格，不依赖 pytest）
```
export GWEN_FRAMEWORK_DIR=<引擎> GWEN_HOST_DIR=<宿主壳> GWEN_TEST_MODE=1 PYTHONUTF8=1
python tests/test_cr2_8_readfail.py
```
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import io
import os
import shutil
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)                      # tests/_paths.py 装配 sys.path
sys.path.insert(0, PKG_ROOT)

import _paths  # noqa: E402  路径装配（唯一发现点，找不到引擎会醒目报错）

_HERE = os.path.join(PKG_ROOT, "content")
_FAILS = []
_N = [0]


def check(ok, label, detail=""):
    _N[0] += 1
    if ok:
        print("  [OK] %s" % label)
    else:
        _FAILS.append(label + (" | " + detail if detail else ""))
        print("  [XX] %s%s" % (label, (" | " + detail) if detail else ""))


def sha(path):
    with io.open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


SRC_FILES = [
    os.path.join(_HERE, "apply.py"),
    os.path.join(_HERE, "affix.py"),
    os.path.join(_HERE, "item_templates.py"),
    os.path.join(_HERE, os.path.join("mech", "equip.py")),
]


# 五张表：文件名 -> 真源条数
TABLES = [
    ("classes.json", 8),
    ("monsters.json", 330),
    ("affixes.json", 76),
    ("legendary_effects.json", 93),
    ("tips.json", 58),
]

_BAD = [("missing", "缺文件"), ("broken", "坏JSON"), ("empty", "空表{}"), ("nondict", "非dict")]


def _stage(tmp, name, mode):
    d = os.path.join(tmp, "data")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    if os.path.exists(p):
        os.remove(p)
    if mode == "good":
        shutil.copy(os.path.join(_HERE, "data", name), p)
    elif mode == "broken":
        io.open(p, "w", encoding="utf-8").write("{ BROKEN JSON ")
    elif mode == "empty":
        io.open(p, "w", encoding="utf-8").write("{}")
    elif mode == "nondict":
        io.open(p, "w", encoding="utf-8").write("[1, 2, 3]")
    return d


def _call(fn, *a):
    try:
        return fn(*a)
    except Exception as ex:                                # noqa: BLE001
        return ("RAISE", type(ex).__name__, str(ex))


def _brief(r):
    if isinstance(r, (dict, list)):
        return "%s(%d)" % (type(r).__name__, len(r))
    return repr(r)[:60]


def apply_case(tmp, mode, name):
    import content.apply as A
    saved = A._DATA_DIR
    try:
        A._DATA_DIR = _stage(tmp, name, mode)
        return _call(A._read_json, name)
    finally:
        A._DATA_DIR = saved


# ============================================================
# (一) 正常态：真源上真跑，非空且等于真源条数 + 真实消费者面
# ============================================================

def group1_normal():
    print("(一) 正常态（假修防线：读口必须还能真读到东西）")
    import content.affix as AF
    import content.apply as A
    import content.item_templates as IT
    import content.mech.equip as EQ

    want = dict(TABLES)
    for mod, attr, label in [
        (A, "_CLASSES", "apply._CLASSES"),
        (A, "_MONSTERS", "apply._MONSTERS"),
        (AF, "AFFIXES", "affix.AFFIXES"),
        (AF, "LEGENDARY_EFFECTS", "affix.LEGENDARY_EFFECTS"),
        (IT, "TIPS", "item_templates.TIPS"),
    ]:
        v = getattr(mod, attr)
        n = want["classes.json"] if attr == "_CLASSES" else (
            want["monsters.json"] if attr == "_MONSTERS" else (
                want["affixes.json"] if attr == "AFFIXES" else (
                    want["legendary_effects.json"] if attr == "LEGENDARY_EFFECTS" else want["tips.json"])))
        check(isinstance(v, dict) and len(v) == n,
              "(一) %s = %d 条" % (label, n), _brief(v))
    check(len(EQ._affix_data()) == 76, "(一) equip._affix_data() = 76 条", _brief(EQ._affix_data()))
    check(len(EQ._legendary_data()) == 93, "(一) equip._legendary_data() = 93 条", _brief(EQ._legendary_data()))

    # 真实消费者面（表清零 ⇒ 这两条塌）
    bs = A.basic_skill_of("法师")
    check(isinstance(bs, dict) and bool(bs), "(一) basic_skill_of(法师) 拿到普攻配置", _brief(bs))
    check(A.monster_skill("ms_ai_hao") is not None, "(一) monster_skill(ms_ai_hao) 非 None")


# ============================================================
# (二)(三)(四) 失败态：四种坏态 -> RuntimeError 点名表名与路径
# ============================================================

def group2_4_failures():
    tmp = tempfile.mkdtemp(prefix="cr2_8_")
    try:
        for name, _n in TABLES:
            for mode, desc in _BAD:
                r = apply_case(tmp, mode, name)
                want = "(二)(三)(四) %s | %s -> RuntimeError 点名表名+路径" % (name, desc)
                if isinstance(r, tuple) and r[0] == "RAISE" and r[1] == "RuntimeError":
                    msg = r[2]
                    check(name in msg and name in msg and "域文件" in msg, want, "msg=%r" % msg[:110])
                else:
                    check(False, want, "实际返回 %s（不抛 = 没 fail-closed）" % _brief(r))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================
# (五) 有牙反证：猴补 json.load 抛异常时必须抛（只猴补内存，不改源文件）
# ============================================================

def group5_counterproof():
    print("(五) 有牙反证（猴补 json.load 抛异常）")
    import content.apply as A

    class _J(object):
        @staticmethod
        def load(*a, **k):
            raise ValueError("cr2_8 猴补：读文件时炸")

    saved = A.json
    try:
        A.json = _J
        r = _call(A._read_json, "classes.json")
        if isinstance(r, tuple) and r[0] == "RAISE":
            check(r[1] == "RuntimeError" and "猴补" in r[2],
                  "(五) 猴补后抛 RuntimeError 且带底层原因（不吞栈）",
                  "%s: %s" % (r[1], r[2][:90]))
        else:
            check(False, "(五) 猴补后必须抛", "静默返回 %s = 门禁没牙" % _brief(r))
    finally:
        A.json = saved


# ============================================================
# (七) `default` 实参与惰性 try/except 兜底都已删
# ============================================================

def group7_no_fallback_left():
    print("(七) default 实参与惰性 try/except 兜底都已删")
    import content.apply as A
    params = list(inspect.signature(A._read_json).parameters)
    check("default" not in params, "(七) _read_json 签名无 default (%s)" % (params,))

    # equip 两处惰性读不得再有 except -> {} 兜底
    p = os.path.join(_HERE, "mech", "equip.py")
    with io.open(p, "r", encoding="utf-8") as f:
        src = f.read()
    check("except Exception:\n            _AFFIX_TABLE = {}" not in src,
          "(七)b equip._affix_data 无 except->{} 兜底")
    check("except Exception:\n            _LEGENDARY_TABLE = {}" not in src,
          "(七)c equip._legendary_data 无 except->{} 兜底")


# ============================================================
# (八) 6 个调用方零残留带 default 实参
#     ★ 第一版就死在这条：只改本体、没改调用方 ⇒ TypeError（包全量在 item_templates 报红）
# ============================================================

def group8_no_stale_callers():
    print("(八) 调用方零残留 default 实参（AST 级，不靠正则）")
    import ast as _ast
    bad = []
    for path in SRC_FILES:
        with io.open(path, "r", encoding="utf-8") as f:
            tree = _ast.parse(f.read(), filename=path)
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, _ast.Attribute) else (fn.id if isinstance(fn, _ast.Name) else None)
            if name != "_read_json":
                continue
            # 本门禁管的是 `apply._read_json` 这一族：名字带 .json 扩展名的调用
            if len(node.args) >= 2:
                bad.append("%s:%d  _read_json(%d 个位置实参)" % (
                    os.path.relpath(path, PKG_ROOT), node.lineno, len(node.args)))
            if node.keywords:
                bad.append("%s:%d  _read_json 带关键字实参" % (
                    os.path.relpath(path, PKG_ROOT), node.lineno))
    check(not bad, "(八) 4 个源文件里 _read_json 调用全部单实参", "; ".join(bad))


def main():
    print("=" * 74)
    print("台账 C-R2.8 · apply._read_json fail-closed 门禁")
    try:
        print("  引擎根：%s" % _paths.find_engine_root())
    except Exception as ex:                                # noqa: BLE001
        print("  引擎发现失败：%s" % ex)
    print("=" * 74)
    before = dict((p, sha(p)) for p in SRC_FILES)
    try:
        group1_normal()
        print("")
        group2_4_failures()
        print("")
        group5_counterproof()
        print("")
        group7_no_fallback_left()
        print("")
        group8_no_stale_callers()
    finally:
        after = dict((p, sha(p)) for p in SRC_FILES)
    print("")
    changed = [os.path.relpath(p, PKG_ROOT) for p in SRC_FILES if before[p] != after[p]]
    check(not changed, "(六) 只读：%d 个源文件 sha256 前后一致" % len(SRC_FILES), "变了：%s" % changed)
    print("=" * 74)
    print("断言 %d 条 · 通过 %d · 失败 %d" % (_N[0], _N[0] - len(_FAILS), len(_FAILS)))
    for f in _FAILS:
        print("  [XX] %s" % f)
    print("=" * 74)
    return 1 if _FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
