# -*- coding: utf-8 -*-
"""schema 层回归：schema 合法性 + 校验器正反例 + 现网违规基线（锁死数字）。

直接运行：
    python tests/test_schema_validate.py      # 全绿 exit 0；失败 exit 1
也可被 pytest 收集（函数名 test_*）。

锁定基线（2026-09-11，见 docs/DATA_SCHEMA_AUDIT.md）：
    现网违规 = 5   （skills 3 / items 2 / 其余 0）
    现网提醒 = 19
若这里是红的：要么数据被改了（真违规），要么 battle_rules.py 被并行重构改了 →
先看 docs/DATA_SCHEMA_AUDIT.md §4 与 schema/README.md『维护规则』再决定改数据还是改 schema。
"""
import importlib.util
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402

# 包仓布局：本文件在 `pkg/tests/`，`dirname(dirname(__file__))` 是**包根**（不是插件根）。
PLUGIN_DIR = _paths.HOST_ROOT      # 宿主插件根（旧语义；`schema/` 在宿主侧）
PKG_ROOT = _paths.PKG_ROOT         # 包根（内容真源）
SCHEMA_DIR = os.path.join(PLUGIN_DIR, "schema")
PYTHON = sys.executable

# 现网基线（数字来源：docs/DATA_SCHEMA_AUDIT.md，python schema/validate.py）
# 2026-09-11：首轮审计发现的 5 条违规**已全部修复**（3 skills accuracy/crit 类型 + 2 items
# 图纸缺 roster_id）→ 现网违规基线 = 0；下方 test_former_violations_are_fixed 作回归守卫。
BASELINE_ERRORS = {"skills": 0, "monsters": 0, "affixes": 0,
                   "items": 0, "effect_rules": 0, "passive_proc": 0}
BASELINE_ERRORS_TOTAL = 0
BASELINE_WARNINGS_TOTAL = 19

SCHEMA_FILES = ("skill.schema.json", "monster.schema.json", "affix.schema.json",
                "item.schema.json", "effect_rules.schema.json", "passive_proc.schema.json")


def _load_validator():
    if PLUGIN_DIR not in sys.path:
        sys.path.insert(0, PLUGIN_DIR)
    spec = importlib.util.spec_from_file_location("df_schema_validate",
                                                 os.path.join(SCHEMA_DIR, "validate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


V = _load_validator()


# ------------------------------------------------------------------ 1. schema 文件
def test_schema_files_parse_and_are_draft_2020_12():
    for name in SCHEMA_FILES:
        path = os.path.join(SCHEMA_DIR, name)
        assert os.path.isfile(path), f"缺少 schema 文件 {name}"
        doc = json.loads(open(path, "r", encoding="utf-8").read())
        assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema", name
        assert "$defs" in doc and doc["$defs"], f"{name} 没有 $defs"
        prim = doc.get("x-primary")
        assert prim in doc["$defs"], f"{name} 的 x-primary={prim!r} 不在 $defs 中"
        assert doc["$defs"][prim].get("type") in ("object", "array"), f"{name} 主 schema 无 type"


def test_every_schema_declares_examples_or_is_documented():
    """README 里必须覆盖全部 schema 文件名（防止加了 schema 忘了写文档）。"""
    readme = open(os.path.join(SCHEMA_DIR, "README.md"), "r", encoding="utf-8").read()
    for name in SCHEMA_FILES:
        assert name in readme, f"schema/README.md 未提及 {name}"


def test_primary_defs_have_examples_and_examples_are_valid():
    """每个主 schema（+ 关键整表 schema）必须配 examples，且 examples 自己必须过 schema。"""
    required = {
        "skill.schema.json": ["skill"],
        "monster.schema.json": ["monster_skill", "monster_template", "hidden_monster",
                                "elite_equip_drop"],
        "affix.schema.json": ["affix", "affix_pool_by_quality", "affix_kind"],
        "item.schema.json": ["item"],
        "effect_rules.schema.json": ["effect_rule", "effect_actions", "mech_cash"],
        "passive_proc.schema.json": ["passive_proc"],
    }
    checked = 0
    for fname, defs in required.items():
        doc = V.load_schema(fname)
        for d in defs:
            assert doc["$defs"][d].get("examples"), f"{fname}:$defs/{d} 缺 examples"
            for ex in doc["$defs"][d]["examples"]:
                checked += 1
                errs = V.validate_instance(ex, doc, d)
                assert not errs, f"{fname}:$defs/{d} 的 example 自身不合法: {errs}"
    assert checked >= 15, f"examples 太少（{checked}）"


# --------------------------------------------------------- 2. 校验器正反例（坏数据）
def _errs(instance, schema_name, def_name):
    doc = V.load_schema(schema_name)
    return V.validate_instance(instance, doc, def_name)


def test_bad_skill_reports_required_and_enum():
    e = _errs({}, "skill.schema.json", "skill")
    assert len(e) >= 4, f"空技能应报 4 个必填缺失，实际 {e}"
    e = _errs({"name": "x", "kind": "不存在的类型", "lv": 1, "desc": "d"},
              "skill.schema.json", "skill")
    assert any(p.endswith("$.kind") for p, _m in e), f"非法 kind 未被拦: {e}"


def test_bad_skill_wrong_types():
    e = _errs({"name": "x", "kind": "物理", "lv": "三", "desc": "d"},
              "skill.schema.json", "skill")
    assert any("lv" in p for p, _m in e), f"lv 类型错误未被拦: {e}"
    e = _errs({"name": "x", "kind": "物理", "lv": 1, "desc": "d",
               "accuracy": "true"}, "skill.schema.json", "skill")
    assert e, "字符串 'true' 冒充 bool 应被判违规（正是现网 skills 的 3 条违规模式）"


def test_good_skill_passes():
    ok = {"name": "挥砍", "kind": "物理", "lv": 1, "mp": 6, "power": 0.82,
          "cast": 0.45, "desc": "长剑划出利落的弧光", "exprs": ["atk*1.0"]}
    assert _errs(ok, "skill.schema.json", "skill") == []


def test_bad_monster_template_shape_and_role():
    assert _errs(["m", "名", "tank", 1, []], "monster.schema.json", "monster_template"), \
        "5 元组应被拦（必须 6 元）"
    e = _errs(["m", "名", "空想职", 1, [], []], "monster.schema.json", "monster_template")
    assert e, "非法 role 应被拦"
    assert _errs(["m", "名", "tank", 0, [], []], "monster.schema.json", "monster_template"), \
        "lv=0 应被拦"
    assert _errs(["m", "名", "tank", 1, ["ms_不存在"], []],
                 "monster.schema.json", "monster_template") == [], "schema 层不管跨表引用"
    assert _errs(["m", "名", "tank", 1, [], []], "monster.schema.json", "monster_template") == []


def test_bad_affix_missing_trigger_and_empty_effect():
    e = _errs({"name": "x", "kind": "attack", "effect": {}, "desc": "d"},
              "affix.schema.json", "affix")
    assert any("trigger" in m for _p, m in e), f"缺 trigger 未被拦: {e}"
    e = _errs({"name": "x", "kind": "attack", "trigger": "on_hit", "effect": {}, "desc": "d"},
              "affix.schema.json", "affix")
    assert e, "空 effect 应被拦（minProperties）"


def test_bad_item_price_and_roster_id():
    e = _errs({"name": "x", "price": -1, "desc": "d"}, "item.schema.json", "item")
    assert e, "负 price 应被拦"
    e = _errs({"name": "x", "price": 1, "desc": "d", "roster_id": "not_eq_1"},
              "item.schema.json", "item")
    assert e, "roster_id 不合 eq_* 形态应被拦"
    assert _errs({"name": "x", "price": 1, "desc": "d"}, "item.schema.json", "item") == []


def test_bad_effect_rule_cap_and_passive_proc_shape():
    assert _errs({"cap": 0}, "effect_rules.schema.json", "effect_rule"), "cap=0 应被拦"
    assert _errs({}, "effect_rules.schema.json", "effect_rule"), "空规则应被拦（minProperties）"
    assert _errs({"cap": 5, "stat_scale": {"atk": 0.04}}, "effect_rules.schema.json",
                 "effect_rule") == []
    # passive_proc：既无 event/action 又无 domain
    assert _errs({"foo": 1}, "passive_proc.schema.json", "passive_proc"), \
        "无 event/action 也无 domain 应被拦（anyOf）"
    assert _errs({"event": "不存在的事件", "action": "passive_dmg_mult"},
                 "passive_proc.schema.json", "passive_proc"), "非法 event 应被拦"
    assert _errs({"event": "dmg_calc", "action": "passive_dmg_mult", "judge": {"kind": "mech"}},
                 "passive_proc.schema.json", "passive_proc") == []
    assert _errs({"domain": "cap", "cap_key": "poison"}, "passive_proc.schema.json",
                 "passive_proc") == []


# ------------------------------------------------------ 3. 两个校验引擎判定一致
def test_minimal_engine_agrees_with_jsonschema():
    if not V.HAS_JSONSCHEMA:
        return  # 只有内建引擎，无需对照
    js = V.validate_all()
    saved = V.HAS_JSONSCHEMA
    try:
        V.HAS_JSONSCHEMA = False
        mn = V.validate_all()
    finally:
        V.HAS_JSONSCHEMA = saved
    assert js["totals"]["errors"] == mn["totals"]["errors"], \
        f"两条引擎违规数不一致 jsonschema={js['totals']} minimal={mn['totals']}"
    for d in js["domains"]:
        assert len(js["domains"][d]["errors"]) == len(mn["domains"][d]["errors"]), d


# ------------------------------------------------------------ 4. 现网违规基线
def test_live_data_violations_match_baseline():
    res = V.validate_all()
    detail = {d: len(i["errors"]) for d, i in res["domains"].items()}
    assert detail == BASELINE_ERRORS, (
        f"现网违规基线漂移: 期望 {BASELINE_ERRORS} 实际 {detail}\n"
        "→ 见 docs/DATA_SCHEMA_AUDIT.md §3/§5；确认是数据 bug 还是 schema 该放宽")
    assert res["totals"]["errors"] == BASELINE_ERRORS_TOTAL, res["totals"]
    assert res["totals"]["warnings"] == BASELINE_WARNINGS_TOTAL, \
        f"提醒数漂移: {res['totals']}（警告不拦门禁，但报告要同步）"
    assert res["exit_code"] == 0, "现网零违规 → 门禁 exit 0"
    assert res["ok"] is True


def test_former_violations_are_fixed():
    """2026-09-11 首轮审计的 5 条违规已修复 → 作回归守卫（不得复发）。"""
    res = V.validate_all()
    sk = {(e["entry"], e["field"]) for e in res["domains"]["skills"]["errors"]}
    assert ("BRANCH_SKILLS/cls_fa_shi/奥术学者/奥术飞弹", "$.accuracy") not in sk
    it = {e["entry"] for e in res["domains"]["items"]["errors"]}
    assert "ITEMS/mat_tu_zhi_ye_xing_pi_feng" not in it
    assert "ITEMS/mat_chuan_shuo_tu_zhi_rong_lu_zhi_xin" not in it
    assert res["domains"]["skills"]["errors"] == []
    assert res["domains"]["items"]["errors"] == []


# -------------------------------------------------------------------- 5. CLI 门禁
def test_cli_exit_codes_and_json():
    r = subprocess.run([PYTHON, os.path.join("schema", "validate.py")],
                       cwd=PLUGIN_DIR, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"现网零违规，CLI 应 exit 0；实际 {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "结论:" in r.stdout

    r = subprocess.run([PYTHON, os.path.join("schema", "validate.py"), "--json"],
                       cwd=PLUGIN_DIR, capture_output=True, text=True, encoding="utf-8")
    data = json.loads(r.stdout)
    assert data["totals"]["errors"] == BASELINE_ERRORS_TOTAL
    assert data["engine"] in ("jsonschema", "minimal")

    r = subprocess.run([PYTHON, os.path.join("schema", "validate.py"), "--domain", "items"],
                       cwd=PLUGIN_DIR, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0
    assert "违规明细 [items]" not in r.stdout, r.stdout
    assert "违规明细 [skills]" not in r.stdout, "--domain 只应验一个域"


def test_domain_filter_isolates_errors():
    res = V.validate_all(domain="items")
    assert list(res["domains"]) == ["items"]
    assert len(res["domains"]["items"]["errors"]) == BASELINE_ERRORS["items"] == 0
    res = V.validate_all(domain="monsters")
    assert res["domains"]["monsters"]["errors"] == []
    assert res["exit_code"] == 0, "单域 monsters 全绿 → exit 0"


# ---------------------------------------------------------------------- 手动跑
def _run_all():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    fails = []
    for n, f in fns:
        try:
            f()
            print(f"✅ {n}")
        except AssertionError as exc:
            fails.append((n, exc))
            print(f"❌ {n}: {exc}")
        except Exception as exc:  # noqa: BLE001
            fails.append((n, exc))
            print(f"💥 {n}: {type(exc).__name__}: {exc}")
    print()
    print(f"schema 校验测试: {len(fns) - len(fails)}/{len(fns)} 通过")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(_run_all())
