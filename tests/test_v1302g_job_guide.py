# -*- coding: utf-8 -*-
"""v130.2g 新功能固化测试（test_v1302g_job_guide.py）：『职业』/『职业 <名称>』指令

落地玩家意见 #1（zerc）「增加查看职业信息的功能」。覆盖：
 ① 数据一致性：job_guide 表与 classes.py 全字段交叉核对 + 资源展示字段与单源新形态核对
   （v181.M-R2c：原 core_resources.py 退役——resource_key/desc = CORE_RESOURCE_GUIDE、
   resource_name/max = EFFECT_RULES 派生；desc 逐字一致、基础档位门槛与
   EVOLVE_LEVELS 同源、攻/守双线分支展示）
 ② 『职业』一览：6 基础职业全名出现 + 分组标题
 ③ 『职业 <名称>』详情：6 职业名逐一可解析（resolve_job + 指令直跑），
    详情含核心机制字段（资源名 + 上限 + 机制 desc）
 ④ 别名解析：歌者/牧师攻线歌者 → 牧师（详情含 歌者/吟游诗人）；职业 id 直查
 ⑤ 未知职业友好提示（未找到 + 『职业』看列表指引）；模糊多命中提示
 ⑥ 注册一致性：_registry 静态表含 job_guide，正则命中 无参/带参/At 前缀
 ⑦ v151 隐藏职业删除：JOB_GUIDE 仅 6 基础职业，隐藏职业 id 全部不可解析

运行：python tests/test_v1302g_job_guide.py（exit=0 全绿）
设计：纯数据 + 纯信息指令，不依赖玩家存档；独立私有临时库（绝不触碰生产库）。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 独立私有临时库（与 conftest 默认隔离，防残留影响）
_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_v1302g_job_guide.db")
os.environ["GWEN_GAME_DB"] = _DB

from _engine_harness import C, run, FakeEvent, clean_db  # noqa: E402

from content.tables import (  # noqa: E402
    JOB_GUIDE, JOB_ALIAS as JOB_ALIASES, resolve_job,
)
# B16 收口：宿主 game/data 已删 —— 真源 = 包内门面（catalog_legacy 同义表口 / tables 同义函数口）
from content.catalog_legacy import (  # noqa: E402
    BASE_ORDER, EXTRA_RESOURCES, EXTRA_RESOURCE_GUIDE,
)
from content.tables import (  # noqa: E402
    JOB_GUIDE as _JOB_GUIDE, job_base_order as _job_base_order,
    job_hidden_order as _job_hidden_order, job_hidden_successors as _job_hidden_successors,
)
HIDDEN_ORDER = _job_hidden_order()          # 原表名的同义口（逐值等：0 条）
HIDDEN_SUCCESSORS = _job_hidden_successors()  # 同上（空表）
# CORE_RESOURCE_GUIDE：原字面表 {cid: {key, desc}} → 包内 job_guide 域派生，按 BASE_ORDER 保键序
CORE_RESOURCE_GUIDE = {c: {"key": _JOB_GUIDE[c]["resource_key"], "desc": _JOB_GUIDE[c]["resource_desc"]}
                       for c in _job_base_order() if _JOB_GUIDE[c].get("resource_key")}
from content.mech.params import EFFECT_RULES  # noqa: E402
from _engine_harness import Main as JobGuideCmds  # noqa: E402  （原 game.commands.job_guide 壳 → 驱动口）
from _engine_harness import harness as _harness  # noqa: E402
COMMAND_REGEX = {k: rx.pattern for rx, k in _harness().declarations_for_static()
                 if not k.startswith("_")}   # 私有 gate 非指令（旧 `_registry` 同口径）

passed = failed = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")


async def job_cmd(msg, jc):
    """直跑 『职业』handler，返回拼接文本"""
    msgs = await run(jc.job_guide, FakeEvent("g1", "u1", msg))
    return "".join(str(x) for x in msgs)


async def main():
    clean_db()  # 建独立测试库（handler 不读档，仅保环境干净）
    jc = JobGuideCmds(None)
    ok = True

    # ===== ① 数据一致性（classes.py + 单源新形态：CORE_RESOURCE_GUIDE / EFFECT_RULES） =====
    print("【① 数据一致性】")
    ok &= check("7 职业全量（基础七；v151 隐藏六已删除）",
                len(JOB_GUIDE) == 7 and len(BASE_ORDER) == 7 and len(HIDDEN_ORDER) == 0,
                f"实际 {len(JOB_GUIDE)}/{len(BASE_ORDER)}/{len(HIDDEN_ORDER)}")
    for cid, g in JOB_GUIDE.items():
        cls = C.CLASSES[cid]
        cfg = CORE_RESOURCE_GUIDE.get(cid)
        ok &= check(f"[{cid}] name 与 classes.py 一致", g["name"] == cls.get("name"), g["name"])
        ok &= check(f"[{cid}] desc 与 classes.py 逐字一致", g["desc"] == cls.get("desc"))
        ok &= check(f"[{cid}] position 为 desc 子串", g["position"] in g["desc"])
        # v181.M-R2c：展示字段新源 = CORE_RESOURCE_GUIDE(key/desc) + EFFECT_RULES(name/cap 派生)，
        # desc 逐字一致性继续强断言（原 core_resources.py 表已退役）
        if cfg:
            _er = EFFECT_RULES.get(cfg["key"], {})
            ok &= check(f"[{cid}] resource_key 与 CORE_RESOURCE_GUIDE.key 一致",
                        g["resource_key"] == cfg["key"], g["resource_key"])
            ok &= check(f"[{cid}] resource_name 与 EFFECT_RULES.name 派生一致",
                        g["resource_name"] == _er.get("name", ""), g["resource_name"])
            ok &= check(f"[{cid}] resource_max 与 EFFECT_RULES.cap 派生一致",
                        g["resource_max"] == int(_er.get("cap", 0) or 0), str(g["resource_max"]))
            ok &= check(f"[{cid}] resource_desc 与 CORE_RESOURCE_GUIDE.desc 逐字一致",
                        g["resource_desc"] == cfg.get("desc", ""), (g["resource_desc"] or "")[:40])
        else:
            ok &= check(f"[{cid}] 无核心资源注册（诗人）resource_* 字段全空",
                        g["resource_key"] == "" and g["resource_name"] == ""
                        and g["resource_max"] == 0 and g["resource_desc"] == "",
                        f"{g['resource_key']!r}/{g['resource_name']!r}/{g['resource_max']}")
        ok &= check(f"[{cid}] 基础档位门槛与 EVOLVE_LEVELS 同源",
                    g["tier_levels"] == C.EVOLVE_LEVELS, str(g["tier_levels"]))
        ok &= check(f"[{cid}] 攻/守双线（T1 两个分支）",
                    len(g.get("tiers", {}).get(1, [])) == 2, str(g.get("tiers", {}).get(1)))

    # ★ 冻结闸（不削弱）：原两表（`core_resources.py` 的 CRG ↔ `job_guide.py` 的 resource_*）已并成
    #   包内**一源** ⇒ 上面两条「一致」检查在新形状下退化为同源自比；改由**冻结期望值**钉住单源取值。
    #   冻结值经 `git show 90fc06b^:game/data/job_guide.py` 的 CORE_RESOURCE_GUIDE 逐值对拍
    #   （6 职业 key/desc 全等，sha256 见 overnight/migL1_crg_proof.py）：任一 key / 中文名 / desc 漂移即红。
    import hashlib as _hl
    _crg_payload = "\n".join("%s|%s|%s" % (c, CORE_RESOURCE_GUIDE[c]["key"], CORE_RESOURCE_GUIDE[c]["desc"])
                             for c in BASE_ORDER if c in CORE_RESOURCE_GUIDE)
    ok &= check("核心资源冻结：key 集 == 删表前 CRG 的 6 键",
                {c: CORE_RESOURCE_GUIDE[c]["key"] for c in CORE_RESOURCE_GUIDE}
                == {"cls_zhan_shi": "rage", "cls_fa_shi": "element", "cls_you_xia": "energy",
                    "cls_mu_shi": "faith", "cls_ci_ke": "cp", "cls_wu_seng": "chi"}
                and len(CORE_RESOURCE_GUIDE) == 6,
                str({c: CORE_RESOURCE_GUIDE[c]["key"] for c in CORE_RESOURCE_GUIDE}))
    ok &= check("核心资源中文名冻结（EFFECT_RULES 跨源派生 → 怒气/元素亲和/精力/信仰值/连击点/气）",
                {c: EFFECT_RULES[CORE_RESOURCE_GUIDE[c]["key"]]["name"] for c in CORE_RESOURCE_GUIDE}
                == {"cls_zhan_shi": "怒气", "cls_fa_shi": "元素亲和", "cls_you_xia": "精力",
                    "cls_mu_shi": "信仰值", "cls_ci_ke": "连击点", "cls_wu_seng": "气"},
                str({c: EFFECT_RULES[CORE_RESOURCE_GUIDE[c]["key"]]["name"] for c in CORE_RESOURCE_GUIDE}))
    ok &= check("核心资源 desc 冻结（sha256 == 删表前原值 f0fbdb24…）",
                _hl.sha256(_crg_payload.encode("utf-8")).hexdigest()
                == "f0fbdb248994f3afa27489b3a31984495d5f5ffd80fb3605b2c2bcbb549d1db6",
                _hl.sha256(_crg_payload.encode("utf-8")).hexdigest())

    # 副资源展示闸：EXTRA_RESOURCES 引用的每个副资源 key 在 EXTRA_RESOURCE_GUIDE 全量 {name,max,desc}
    ok &= check("EXTRA_RESOURCES 副资源 key 全在 EXTRA_RESOURCE_GUIDE 注册",
                all(rk in EXTRA_RESOURCE_GUIDE
                    for rks in EXTRA_RESOURCES.values() for rk in rks),
                str(EXTRA_RESOURCE_GUIDE.keys()))

    # ===== ② 『职业』一览 =====
    print("【② 『职业』一览】")
    txt = await job_cmd("职业", jc)
    ok &= check("一览含 6 基础职业全名", all(g["name"] in txt for g in JOB_GUIDE.values()))
    ok &= check("一览分组标题（基础六职业）", "基础六职业" in txt)
    ok &= check("一览带使用指引", "『职业 <名称>』" in txt or "看详情" in txt)

    # ===== ③ 单职业详情：6 职业名逐一解析 + 核心机制字段 =====
    print("【③ 单职业详情】")
    for cid, g in JOB_GUIDE.items():
        ok &= check(f"resolve_job('{g['name']}') → {cid}", resolve_job(g["name"]) == cid)
        d = await job_cmd(f"职业 {g['name']}", jc)
        ok &= check(f"『职业 {g['name']}』详情可出", g["name"] in d and "核心资源" in d)
        ok &= check(f"『职业 {g['name']}』含资源机制字段",
                    g["resource_name"] in d and str(g["resource_max"]) in d and g["resource_desc"] in d)
        ok &= check(f"『职业 {g['name']}』含档位路线", "档位路线" in d)

    # ===== ④ 别名解析 =====
    print("【④ 别名解析】")
    ok &= check("别名 歌者 → 牧师", resolve_job("歌者") == "cls_mu_shi")
    d = await job_cmd("职业 牧师攻线歌者", jc)
    ok &= check("『职业 牧师攻线歌者』→ 牧师详情（攻线·歌者）",
                "牧师" in d and "歌者" in d and "神谕者" in d, d[:120])
    ok &= check("显示名 id 直查", resolve_job("cls_zhan_shi") == "cls_zhan_shi")
    # v153：诗人独立为第 7 职业 → 吟游诗人 解析到 cls_shi_ren
    ok &= check("吟游诗人 → 诗人（v153 独立职业）", resolve_job("吟游诗人") == "cls_shi_ren")
    ok &= check("诗人转职名别名（咏叹者 → 诗人）", resolve_job("咏叹者") == "cls_shi_ren")
    ok &= check("分支名别名（影舞者 → 刺客）", resolve_job("影舞者") == "cls_ci_ke")
    # 牧师攻线·歌者双资源（共鸣+回声）在详情中展示
    d = await job_cmd("职业 牧师", jc)
    ok &= check("牧师详情含歌者双资源（共鸣+回声）", "共鸣" in d and "回声" in d)

    # ===== ⑤ 未知/模糊 =====
    print("【⑤ 未知/模糊】")
    d = await job_cmd("职业 龙傲天", jc)
    ok &= check("未知职业友好提示", "未找到" in d and "『职业』" in d, d[:80])
    d = await job_cmd("职业 行者", jc)
    ok &= check("模糊多命中→候选提示", "匹配到多个职业" in d, d[:80])

    # ===== ⑥ 注册一致性 =====
    print("【⑥ 注册一致性】")
    pat = COMMAND_REGEX.get("job_guide")
    ok &= check("_registry 静态表含 job_guide", pat is not None)
    if pat:
        rx = re.compile(pat)
        ok &= check("『职业』命中", bool(rx.match("职业")))
        ok &= check("『职业 战士』命中", bool(rx.match("职业 战士")))
        ok &= check("『[At:1] 职业 战士』命中", bool(rx.match("[At:1] 职业 战士")))
        ok &= check("『职业重置』不命中（与转职重置无冲突）", not rx.match("职业重置"))
        # 正则与命令层装饰器同源（防矩阵测试漂移）：2026-09-12 v185 指令表迁移后，
        # 命令层不再写正则字面量 → 断言「handler 从声明表取正则」+「声明值 == 静态表值」
        import json as _json
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # ★ P5F-REPOINT: 原读宿主壳 `game/commands/job_guide.py` 的 `@declared("job_guide")`
        #   （随删壳批消失）→ 包内登记面 `content/cmds_job.py` 的 `@register("job_guide", …)`。
        src = open(os.path.join(_root, "content", "cmds_job.py"),
                   encoding="utf-8").read()
        ok &= check("登记面走声明表（@register 取 job_guide）", '@register("job_guide"' in src)
        # ★ P5F-REPOINT: 原读宿主 `game/data/command_specs.json`（保留下来的**部署期镜像**）
        #   → 包内**声明真源** `content/data/commands.json`（单源：静态表与声明表同源同值）。
        _specs = _json.load(open(os.path.join(_root, "content",
                                              "data", "commands.json"),
                                 encoding="utf-8"))
        ok &= check("声明表该 key 的正则 == 静态表值",
                    _specs.get("job_guide", {}).get("patterns") == [pat],
                    _specs.get("job_guide", {}).get("patterns"))

    # ===== ⑦ v151 隐藏职业删除 =====
    print("【⑦ v151 隐藏职业删除】")
    ok &= check("隐藏六职业 id 均不可解析",
                all(resolve_job(hid) is None
                    for hid in ("cls_dragon_oath", "cls_chronomancer", "cls_wild_hunter",
                                "cls_hymn", "cls_shadow_blade", "cls_wu_sheng")))
    ok &= check("隐藏线旧别名（武僧/龙血）已清除",
                resolve_job("武僧") is None and resolve_job("龙血") is None)

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()) or (1 if failed else 0))
