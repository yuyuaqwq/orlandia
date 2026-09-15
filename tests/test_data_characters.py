# -*- coding: utf-8 -*-
"""data 层 · 角色族：职业 / 技能 / 分支 / 符文 / 称号

验证 CLASSES / PLAYER_SKILLS / BRANCH_SKILLS / RUNES / TITLES 的结构约定。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C
# v181.M-R2c：core_resources.py 退役——资源注册完整性断言改对单源新形态（见 main()）
from content.mech.params import EFFECT_RULES as _ER_RULES  # noqa: E402
# 包内唯一真源（`game/data/` 已删）：`content/data/job_guide.json`
#   · 核心资源引导 = 每职业的 resource_key/resource_name/resource_max/resource_desc
#     （JOB_GUIDE 7 条里 resource_key 非空的 6 条 = 原 CORE_RESOURCE_GUIDE 的 6 职业）
#   · 副资源展示   = 门面 `content.catalog_legacy.EXTRA_RESOURCE_GUIDE`（同文件 extra_resources 折回）
from content.catalog_legacy import EXTRA_RESOURCE_GUIDE as _XRG  # noqa: E402
_CRG = {_c: {"key": _v.get("resource_key"), "name": _v.get("resource_name"),
             "max": _v.get("resource_max"), "desc": _v.get("resource_desc")}
        for _c, _v in C.JOB_GUIDE.items() if _v.get("resource_key")}

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ %s" % name)
    else:
        failed += 1
        print("  ❌ %s %s" % (name, detail))


def main():
    print("【data·角色族：职业】")
    check("CLASSES 6 职业", len(C.CLASSES) >= 6, str(len(C.CLASSES)))
    check("职业含 战士", C.resolve("classes", "战士") in C.CLASSES, str(list(C.CLASSES)[:3]))
    check("职业含 法师", C.resolve("classes", "法师") in C.CLASSES, str(list(C.CLASSES)[:3]))
    cls = C.CLASSES.get(C.resolve("classes", "战士"), {})
    check("职业含基础技能表", isinstance(cls, dict), str(type(cls)))

    print("【data·角色族：技能】")
    # v153 职业重做：新增诗人，PLAYER_SKILLS/BRANCH_SKILLS 各 7 职业
    check("PLAYER_SKILLS 7 职业(7基础)",
          len(C.PLAYER_SKILLS) == 7 and all(c in C.PLAYER_SKILLS for c in
          ("cls_zhan_shi", "cls_fa_shi", "cls_you_xia", "cls_mu_shi", "cls_ci_ke", "cls_wu_seng", "cls_shi_ren")),
          str(len(C.PLAYER_SKILLS)))
    check("每职业有技能表", all(isinstance(v, dict) and len(v) > 0 for v in C.PLAYER_SKILLS.values()),
          str({k: len(v) for k, v in C.PLAYER_SKILLS.items()}))
    check("BRANCH_SKILLS 7 职业(7基础)", len(C.BRANCH_SKILLS) == 7, str(len(C.BRANCH_SKILLS)))
    check("每职业 3 分支（21 章三转体系 30/60/90）", all(len(v.get("branches", {})) == 3 for v in C.BRANCH_SKILLS.values()),
          str({k: len(v.get("branches", {})) for k, v in C.BRANCH_SKILLS.items()}))
    # v181.M-R2c：原 data/core_resources.py 退役（git rm）——『资源注册完整性』闸迁移：
    #   CORE_RESOURCE_GUIDE（6 职业 cid→key/desc）+ EFFECT_RULES（key 均注册 name+cap）
    #   + EXTRA_RESOURCE_GUIDE（歌者副资源 resonance/echo {name,max,desc} 全量；vow 随 v139
    #   未实装退役，设计值留档 docs/REFACTOR_v181_CLASS_MECH_ASSEMBLY.md『v139 形态层设计留档』章）
    check("资源注册完整性：CORE_RESOURCE_GUIDE 6 职业，key 全在 EFFECT_RULES(name+cap)",
          len(_CRG) == 6
          and all(_CRG[c].get("key") in _ER_RULES
                  and _ER_RULES[_CRG[c]["key"]].get("name")
                  and _ER_RULES[_CRG[c]["key"]].get("cap") is not None
                  for c in _CRG),
          str({c: _CRG[c].get("key") for c in _CRG}))
    check("六职业核心资源 key→中文名与 EFFECT_RULES 单源一致（怒气/元素亲和/精力/信仰值/连击点/气）",
          {c: _ER_RULES[_CRG[c]["key"]]["name"] for c in _CRG}
          == {"cls_zhan_shi": "怒气", "cls_fa_shi": "元素亲和", "cls_you_xia": "精力",
              "cls_mu_shi": "信仰值", "cls_ci_ke": "连击点", "cls_wu_seng": "气"},
          str({c: _ER_RULES[_CRG[c]["key"]].get("name") for c in _CRG}))
    check("副资源注册完整性：EXTRA_RESOURCE_GUIDE 仅 共鸣/回声，{name,max,desc} 全量",
          set(_XRG) == {"resonance", "echo"}
          and all(_XRG[k].get("name") and isinstance(_XRG[k].get("max"), int)
                  and _XRG[k].get("desc") for k in _XRG),
          str(_XRG))
    check("副资源展示 desc 逐字（歌者共鸣/回声机制一句话，自旧表逐字迁移）",
          _XRG["resonance"]["desc"].startswith("歌者短周期燃料条")
          and _XRG["echo"]["desc"].startswith("歌者长周期驻留叠层"),
          str({k: (v.get("desc") or "")[:18] for k, v in _XRG.items()}))
    sk = C.resolve("skills", "火球术")
    check("resolve(skills, 火球术) 有值", bool(sk), str(sk))
    if sk:
        check("display(skills, ID)→火球术", C.display("skills", sk) == "火球术", C.display("skills", sk))

    print("【data·角色族：符文】")
    check("RUNES 16 个符文", len(C.RUNES) >= 10, str(len(C.RUNES)))
    check("符文含 残忍", C.resolve("runes", "残忍") in C.RUNES, str(list(C.RUNES)[:5]))
    check("符文值含 effect", all(isinstance(v, dict) and "effect" in v for v in C.RUNES.values()),
          str(list(C.RUNES.values())[0])[:60])

    print("【data·角色族：称号】")
    check("TITLES 非空", hasattr(C, "TITLES") and len(getattr(C, "TITLES", [])) > 0, "TITLES")

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
