# -*- coding: utf-8 -*-
"""包内职业速查命令（`content/cmds_job.py`）—— 『职业』『职业 <名称>』的取参/解析/业务/**渲染**。

终态形状（B18；真源 = `overnight/B18_TERMINAL_SHAPE.md` §1.2）：
* handler 签名 `fn(env) -> list[str]`，**直接返回已渲染行**（本命令全 f-string 字面量 → 随业务进包，
  宿主 `game/commands/job_guide.py` 里已无任何渲染代码，`grep T.text|T.static` → 0）。
* **本命令无守卫**（纯信息查询：注册前可查，与『种族』『图鉴』同款）—— 声明里也不给 guards。
* 取参 `env.arg_text("职业")`（= 旧 `self._strip_cmd(event, "职业").strip()` 同口径）。
* 数据与名称解析 = 包内门面 `content/tables.py`（`JOB_GUIDE` / `job_base_order()` /
  `job_hidden_order()` / `job_hidden_successors()` / `CLASSES` / `resolve("job_guide", …)`）
  —— **包内直连，不经宿主**。

名称解析链（一字未改）：职业 id → 显示名 → 别名（转职分支名 / 兼容名 歌者）→ 模糊子串兜底
（≥2 字双向 contains；多命中给候选列表）。

行为逐字节不变（一览分组 / 详情行序 / 档位路线 / 资源/解锁行 = 改造前逐行）；证据 =
`overnight/W-B18-L6.md` 的 34 场景快照（sha256 改前 = 改后）。
"""
from __future__ import annotations

from . import tables as _TBL
from .commands import register
from . import texts as _T                # ★ C 档 33b（2026-09-19）：文案表读口（本文件首次接入）

JOB_GUIDE = _TBL.JOB_GUIDE                      # 7 条；已含 aliases / extra_resources 注入
BASE_ORDER = _TBL.job_base_order()
HIDDEN_ORDER = _TBL.job_hidden_order()
HIDDEN_SUCCESSORS = _TBL.job_hidden_successors()
CLASSES = _TBL.CLASSES                          # 详情里 `mech`（v130.7 意见#19）读它
# 副资源展示：域里挂在职业条目上（`extra_resources` = [{key,name,max,desc}]）→ 还原成真源的
# 两张查表形状（`EXTRA_RESOURCES` 职业→key 列表 / `EXTRA_RESOURCE_GUIDE` key→元数据），
# 这样下面的渲染代码与文案**一行都不用改**。
EXTRA_RESOURCES = {cid: [r["key"] for r in g["extra_resources"]]
                   for cid, g in JOB_GUIDE.items() if g.get("extra_resources")}
EXTRA_RESOURCE_GUIDE = {r["key"]: r for g in JOB_GUIDE.values()
                        for r in (g.get("extra_resources") or [])}


def resolve_job(raw):
    """职业名 → 职业 id / 多命中 list / None —— 包内**通用解析口**（与真源逐行同义）。"""
    return _TBL.resolve("job_guide", raw)


@register("job_guide", params=("cmd=职业",))
def job_guide(env) -> list:
    """『职业』速查：12 职业一览 + 单职业详情（玩家意见 #1）。"""
    raw = env.arg_text("职业")
    if not raw:
        return _jg_overview().split("\n")
    hit = resolve_job(raw)
    if isinstance(hit, str):
        return _jg_detail(hit).split("\n")
    if isinstance(hit, list):
        # ★ C 档 44：去掉「对已渲染结果再做 .format(raw, names)」的死代码 —— _T.text 已完成渲染，
        #   二次 .format 是空操作；且 raw 来自玩家输入，含 {...} 时二次格式化直接 KeyError 崩命令。
        names = "、".join(f"『职业 {JOB_GUIDE[c]['name']}』" for c in hit)
        return [_T.text("job.multi", raw=raw, names=names)]
    return [_T.text("job.not_found", raw=raw)]


# ---------------- 一览 ----------------

def _jg_overview() -> str:
    lines = [_T.static("job.head"), "━━━━━━━━━━━━"]
    lines.append(_T.static("job.base_head"))
    for cid in BASE_ORDER:
        g = JOB_GUIDE[cid]
        lines.append(f"{g['icon']} {g['name']}：{g['position']}")
    lines.append("")
    lines.append(_T.static("job.hidden_head"))
    for cid in HIDDEN_ORDER:
        g = JOB_GUIDE[cid]
        lines.append(f"{g['icon']} {g['name']}：{g['position']}")
    lines.append("")
    lines.append(_T.static("job.tip"))
    return "\n".join(lines)


# ---------------- 详情 ----------------

def _jg_detail(cid: str) -> str:
    g = JOB_GUIDE[cid]
    kind = "隐藏职业" if g["hidden"] else "基础职业"
    lines = [f"{g['icon']} 【{g['name']}】（{kind}）", "━━━━━━━━━━━━"]
    lines.append(f"📖 {g['desc']}")
    # v130.7 意见#19：核心玩法机制解释（classes.py mech，无该字段的兜底不显示该行）
    _mech = CLASSES.get(cid, {}).get("mech")
    if _mech:
        lines.append(_T.text("job.mech", mech=_mech))
    lines.append(_jg_tier_line(g))
    lines.append(_jg_resource_line(g))
    melee = "近战" if g["reach"] == 1 else "远程"
    role = g["role"] + (" · " + g["rank_label"] if g["rank_label"] else "")
    lines.append(_T.text("job.role", role=role, melee=melee))
    if g["hidden"]:
        lines.append(_jg_unlock_line(g))
    else:
        for s in HIDDEN_SUCCESSORS.get(cid, []):
            sg = JOB_GUIDE[s]
            lines.append(
                _T.text("job.successor", icon=sg['icon'], name=sg['name'],
                    unlock=_jg_unlock_line(sg, short=True)))
    return "\n".join(lines)


def _jg_tier_line(g: dict) -> str:
    """档位路线：T1(Lv.30) 攻线·狂战士 / 守线·盾卫士（基础双线，index0=攻线）"""
    lines = [_T.static("job.tier_head")]
    tlv = g["tier_levels"]
    for t in sorted(g.get("tiers") or {}):
        names = g["tiers"][t]
        lv = tlv.get(int(t), 30)
        if g["hidden"] or len(names) <= 1:
            lines.append(_T.text("job.tier_hidden", t=t, lv=lv, names=' / '.join(names)) if g["hidden"]
                         else _T.text("job.tier_single", t=t, lv=lv, names=' / '.join(names)))
        else:
            atk = names[0] if len(names) > 0 else "?"
            dfn = names[1] if len(names) > 1 else "?"
            lines.append(_T.text("job.tier_base", t=t, lv=lv, atk=atk, dfn=dfn))
    return "\n".join(lines)


def _jg_resource_line(g: dict) -> str:
    """核心资源与机制一句话（JOB_GUIDE resource_desc，源 job_guide CORE_RESOURCE_GUIDE 展示表）+ 转职分支专属资源"""
    lines = [_T.text("job.resource", res_name=g['resource_name'], res_max=g['resource_max'],
                 res_desc=g['resource_desc'])]
    for rk in EXTRA_RESOURCES.get(g["cls_id"], []):
        r = EXTRA_RESOURCE_GUIDE.get(rk)
        if r:
            lines.append(_T.text("job.extra_res", res_name=r.get('name', rk), res_max=r.get('max'),
                             res_desc=r.get('desc')))
    return "\n".join(lines)


def _jg_unlock_line(g: dict, short: bool = False) -> str:
    """隐藏线解锁方式：任务链 + 档位门槛 + 种族血缘限制 + 线索（详情）"""
    tlv = g["tier_levels"]
    tk = g.get("task_name") or "专属试炼"
    if short:
        line = _T.text("job.unlock_short", tk=tk, lv=tlv.get(1, 40))
        if g.get("src_race"):
            line += _T.text("job.race_limit", race=g['race_name'])
        return line
    lines = [_T.text("job.unlock_full", tk=tk, lv1=tlv.get(1, 40), lv1b=tlv.get(1, 40), lv2=tlv.get(2, 60),
                 lv3=tlv.get(3, 90))]
    if g.get("src_race"):
        lines.append(_T.text("job.blood", race=g['race_name']))
    if g.get("src_base"):
        lines.append(_T.text("job.origin", base=JOB_GUIDE[g['src_base']]['name']))
    if g.get("hint"):
        lines.append(g["hint"])
    return "\n".join(lines)
