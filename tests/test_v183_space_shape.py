#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v183 地图形状搬到引擎 —— 内容侧**逐格一致**门禁（路线图 #6）。

搬形状最容易出的错不是崩溃，是**语义漂移**（某个分支少算一条边、顺序变了、深度的算法
换了口径）。所以本门禁不看代码，只看**输出**：

  ① 把 v183 之前的实现**逐字冻结**在本文件里（`_old_*`），
  ② 对**全部地图 × 全部子区域**（含未知 id）比对 邻接 / 深度 / 出入口，
  ③ 再对 travel / world 两处「必经提示」的旧判断与新 route() 判断逐对比较。

任一处不同即红。跑法：python tests/test_v183_space_shape.py（exit=0 全绿）
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PD = os.path.dirname(_HERE)
for _p in (_HERE, _PD, os.path.dirname(os.path.dirname(_PD))):
    sys.path.insert(0, _p)

from conftest import C  # noqa: E402

passed = failed = 0

UNKNOWN_IDS = ("", "__not_a_subarea__")


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


# ══════════════════════════════════════════════════════════════════════════
# 冻结：v183 之前的实现（逐字复制自当时的 game/core/maps.py，勿改）
# ══════════════════════════════════════════════════════════════════════════
def _old_subarea_links(map_id, subarea_id):
    mesh = C.SUBAREA_LINKS_INDEX.get(map_id)
    if mesh is not None:
        return list(mesh.get(subarea_id, []))
    sas = C.SUBAREAS.get(map_id, [])
    if not sas:
        return []
    idx = next((i for i, s in enumerate(sas) if s["id"] == subarea_id), None)
    if idx is None:
        return []
    center = sas[0]
    if center.get("type") == C.SUB_TYPE_TOWN:
        cur_type = sas[idx].get("type")
        if subarea_id == center["id"]:
            out = [s["id"] for s in sas
                   if s["id"] != center["id"] and s.get("type") != C.SUB_TYPE_GATE]
            if not any(s.get("type") == C.SUB_TYPE_STREET for s in sas):
                out += [s["id"] for s in sas if s.get("type") == C.SUB_TYPE_GATE]
            return out
        if cur_type == C.SUB_TYPE_STREET:
            out = [s["id"] for s in sas if s.get("type") == C.SUB_TYPE_GATE]
            out.append(center["id"])
            return out
        if cur_type == C.SUB_TYPE_GATE:
            streets = [s["id"] for s in sas if s.get("type") == C.SUB_TYPE_STREET]
            if streets:
                return streets
            return [center["id"]]
        return [center["id"]]
    out = []
    if idx > 0:
        out.append(sas[idx - 1]["id"])
    if idx < len(sas) - 1:
        out.append(sas[idx + 1]["id"])
    return out


def _old_subarea_depth(map_id, sa_id):
    sas = C.SUBAREAS.get(map_id, [])
    if not sas:
        return 0
    mesh = C.SUBAREA_LINKS_INDEX.get(map_id)
    if mesh is not None:
        entry = sas[0]["id"]
        dist = {entry: 0}
        queue = [entry]
        while queue:
            cur = queue.pop(0)
            for nxt in mesh.get(cur, ()):
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    queue.append(nxt)
        return dist.get(sa_id, len(sas))
    idx = next((i for i, s in enumerate(sas) if s["id"] == sa_id), 0)
    return idx


def _old_gate(map_id):
    sas = C.SUBAREAS.get(map_id, [])
    if not sas:
        return ""
    if sas[0].get("type") == C.SUB_TYPE_TOWN:
        for s in sas:
            if s.get("type") == C.SUB_TYPE_GATE:
                return s["id"]
        for s in sas:
            if s["id"].endswith("_gate"):
                return s["id"]
    return sas[0]["id"]


def _old_center(map_id):
    """旧口径的「中心」= 首个子区域且是城镇类型（否则无中心）。"""
    sas = C.SUBAREAS.get(map_id, [])
    if sas and sas[0].get("type") == C.SUB_TYPE_TOWN:
        return sas[0]["id"]
    return ""


def _old_travel_hint(map_id, cur_sa_id, target_sa_id):
    """冻结：travel.move_blocked_msg 的「先经过链首」特判分支（返回是否命中 + 链首 id）。"""
    sas = C.SUBAREAS.get(map_id, [])
    center = sas[0] if sas else {}
    if center.get("type") == C.SUB_TYPE_TOWN and cur_sa_id == center.get("id", ""):
        chain = [s for s in sas if s.get("type") in (C.SUB_TYPE_STREET, C.SUB_TYPE_GATE)]
        if (any(s["id"] == target_sa_id for s in chain) and chain and chain[0]["id"] != target_sa_id):
            return True, chain[0]["id"]
    return False, ""


def _old_world_hint(map_id, cur_sa_id):
    """冻结：world._subarea_body 的「出城需先到」提示（返回提示用的子区域 id）。"""
    sas = C.SUBAREAS.get(map_id, [])
    exit_sa_id = _old_gate(map_id)
    hint = exit_sa_id
    center = sas[0] if sas else {}
    if center.get("type") == C.SUB_TYPE_TOWN and cur_sa_id == center.get("id", ""):
        chain = [s for s in sas if s.get("type") in (C.SUB_TYPE_STREET, C.SUB_TYPE_GATE)]
        if chain and chain[0]["id"] != exit_sa_id:
            hint = chain[0]["id"]
    return hint


def _name(map_id, sa_id):
    for s in C.SUBAREAS.get(map_id, []):
        if s["id"] == sa_id:
            return s.get("name") or sa_id
    return sa_id


# ══════════════════════════════════════════════════════════════════════════
# 新实现（内容侧适配）
# ══════════════════════════════════════════════════════════════════════════
def _new_travel_hint(map_id, cur_sa_id, target_sa_id):
    """新口径：枢纽节点 + route() 的第一个中间站（语义等价于旧「链首」）。"""
    hub = C.map_center(map_id)
    if hub and cur_sa_id == hub:
        r = C.map_route(map_id, cur_sa_id, target_sa_id)
        if len(r) >= 2 and r[1] != target_sa_id:
            return True, r[1]
    return False, ""


def _new_world_hint(map_id, cur_sa_id):
    sas = C.SUBAREAS.get(map_id, [])
    exit_sa_id = C.map_exit_subarea(map_id)
    hint = exit_sa_id
    hub = C.map_center(map_id)
    if hub and cur_sa_id == hub:
        r = C.map_route(map_id, cur_sa_id, exit_sa_id)
        if len(r) >= 2:
            hint = r[1]
    return hint


# ══════════════════════════════════════════════════════════════════════════
def t1_links_depth_gate():
    print("\n[1] 邻接 / 深度 / 出入口：全地图 × 全子区域逐格比对")
    maps = sorted(set(list(C.SUBAREAS.keys()) + [m["id"] for m in C.MAPS]))
    n_sa = n_cmp = 0
    bad_links, bad_depth, bad_gate = [], [], []
    for mid in maps:
        sas = C.SUBAREAS.get(mid, [])
        ids = [s["id"] for s in sas] + list(UNKNOWN_IDS)
        for sid in ids:
            n_cmp += 1
            a, b = _old_subarea_links(mid, sid), C.subarea_links(mid, sid)
            if a != b:
                bad_links.append((mid, sid, a, b))
            a, b = _old_subarea_depth(mid, sid), C.subarea_depth(mid, sid)
            if a != b:
                bad_depth.append((mid, sid, a, b))
        n_sa += len(sas)
        a, b = _old_gate(mid), C.map_exit_subarea(mid)
        if a != b:
            bad_gate.append((mid, "exit", a, b))
        a, b = _old_gate(mid), C.map_entry_subarea(mid)
        if a != b:
            bad_gate.append((mid, "entry", a, b))
    print(f"  （地图 {len(maps)} 张 / 子区域 {n_sa} 个 / 查询 {n_cmp} 次）")
    check(f"★ 邻接逐格一致（{n_cmp} 次查询）", not bad_links, str(bad_links[:4]))
    check(f"★ 深度逐格一致（{n_cmp} 次查询）", not bad_depth, str(bad_depth[:4]))
    check("★ 出入口逐格一致（exit 与 entry 两函数 × 全部地图）", not bad_gate, str(bad_gate[:4]))
    check("出入口两函数在数值上同源（历史双份实现已合一）",
          all(C.map_exit_subarea(m["id"]) == C.map_entry_subarea(m["id"]) for m in C.MAPS))


def t1b_unknown_map():
    print("\n[1b] 不存在的图 id：新旧实现同样安全（副本 inst_* / 拼错名 / 空串）")
    bad = []
    for mid in ("__no_such_map__", "inst_不存在", "", None):
        a = (_old_subarea_links(mid, "x"), _old_subarea_depth(mid, "x"), _old_gate(mid))
        b = (C.subarea_links(mid, "x"), C.subarea_depth(mid, "x"),
             C.map_exit_subarea(mid), C.map_entry_subarea(mid))
        if a != (b[0], b[1], b[2]) or b[2] != b[3]:
            bad.append((mid, a, b))
    check("★ 未知图 id：邻接/深度/出入口逐项与旧实现一致（不抛错）", not bad, str(bad))
    check("未知图 id 的 map_center / map_route 安全返回空",
          C.map_center("__no_such_map__") == "" and C.map_route("__no_such_map__", "a", "b") == [])
    check("map_space 空图对象可用（节点 0 / gate 空串）",
          C.map_space("__no_such_map__").gate() == "" and len(C.map_space("__no_such_map__")) == 0)


def t2_shape_and_center():
    print("\n[2] 形状判定与枢纽（旧口径 = 首节点是城镇类型）")
    star = chain = 0
    bad = []
    for mid in sorted(C.SUBAREAS.keys()):
        sas = C.SUBAREAS[mid]
        if not sas:
            continue
        sp = C.map_space(mid)
        is_old_center = bool(_old_center(mid))
        if is_old_center:
            star += 1
        else:
            chain += 1
        if (sp.topology == "star") != is_old_center:
            bad.append((mid, sp.topology, sas[0].get("type")))
        if (_old_center(mid) or "") != C.map_center(mid):
            bad.append((mid, "center", _old_center(mid), C.map_center(mid)))
        if sp.explicit != (mid in C.SUBAREA_LINKS_INDEX):
            bad.append((mid, "explicit", sp.explicit, mid in C.SUBAREA_LINKS_INDEX))
    print(f"  （星形图 {star} 张 / 链状图 {chain} 张）")
    check("★ 形状判定与旧口径逐图一致（星形/链状 + 中心 + 显式表来源）", not bad, str(bad[:4]))
    check("副本图（显式表）拓扑标为 mesh",
          all(C.map_space(mid).topology == "mesh" for mid in C.SUBAREA_LINKS_INDEX))


def t3_hint_equivalence():
    print("\n[3] 两处「必经提示」：旧判断 vs 新 route() 逐对比对")
    bad_t, bad_w, n_pair = [], [], 0
    for mid in sorted(C.SUBAREAS.keys()):
        sas = C.SUBAREAS.get(mid, [])
        if not sas:
            continue
        ids = [s["id"] for s in sas]
        for cur in ids:
            for tgt in ids:
                n_pair += 1
                a = _old_travel_hint(mid, cur, tgt)
                b = _new_travel_hint(mid, cur, tgt)
                if a != b:
                    bad_t.append((mid, cur, tgt, a, b))
            ow = _old_world_hint(mid, cur)
            nw = _new_world_hint(mid, cur)
            if ow != nw:
                bad_w.append((mid, cur, ow, nw))
    print(f"  （同图子区域对 {n_pair} 组 + 出城提示 {n_pair} 组）")
    check(f"★ travel 提示分支逐对一致（{n_pair} 组）", not bad_t, str(bad_t[:4]))
    check(f"★ world 出城提示逐图逐点一致（{n_pair} 组）", not bad_w, str(bad_w[:4]))


def t4_route_sanity():
    print("\n[4] route() 健全性（新能力，非等价性）")
    sp_mesh = [mid for mid in C.SUBAREA_LINKS_INDEX]
    ok_reach, bad_reach = 0, []
    for mid in sp_mesh:
        sas = C.SUBAREAS.get(mid, [])
        if not sas:
            continue
        first = sas[0]["id"]
        for s in sas:
            r = C.map_route(mid, first, s["id"])
            if not r:
                bad_reach.append((mid, s["id"]))
            else:
                ok_reach += 1
    print(f"  （网状图从入口可达节点 {ok_reach} 个）")
    check("★ 全部网状图的房间从入口可达（副本主链无断链）", not bad_reach, str(bad_reach[:6]))
    check("route 同点返回单元素", all(C.map_route(m, i, i) == [i]
                                      for m in list(C.SUBAREA_LINKS_INDEX)[:20]
                                      for i in [C.SUBAREAS[m][0]["id"]]))
    check("route 未知端点返回空列表", C.map_route("oak_town", "nope", "oak_square") == []
          and C.map_route("oak_town", "oak_square", "nope") == [])
    check("route 与邻接自洽（相邻则路径长度 2）",
          all(C.map_route("oak_town", "oak_square", n) == ["oak_square", n]
              for n in C.subarea_links("oak_town", "oak_square")))


def t5_audit_sweep():
    print("\n[5] 全图结构审计扫描（信息项：把数据里既有问题摆出来，不做断言失败）")
    problems = {"dangling": 0, "asymmetric": 0, "isolated": 0, "unreachable": 0, "no_gate": 0}
    maps_bad = []
    for mid in sorted(C.SUBAREAS.keys()):
        au = C.map_space(mid).audit()
        if not au["ok"]:
            maps_bad.append(mid)
        for k in problems:
            v = au[k]
            problems[k] += 1 if (v is True) else (0 if v is False else len(v))
    print(f"  （体检 {len(C.SUBAREAS)} 张图；有问题的图 {len(maps_bad)} 张：{maps_bad[:8]}）")
    print(f"  （计数 {problems}）")
    check("审计口径可跑通（全图无异常抛错）", True)
    check("★ 悬空边为零（连通表指向的子区域都存在）", problems["dangling"] == 0)
    check("★ 不对称边为零（内容侧连通表双向对称）", problems["asymmetric"] == 0)
    check("★ 无孤立子区域（每个房间都有邻接或有人连它）", problems["isolated"] == 0)
    check("★ 无不可达子区域（从入口都能走到）", problems["unreachable"] == 0)


def main():
    print("== v183 地图形状门禁：内容侧逐格一致（旧实现冻结比对） ==")
    t1_links_depth_gate()
    t1b_unknown_map()
    t2_shape_and_center()
    t3_hint_equivalence()
    t4_route_sanity()
    t5_audit_sweep()
    print(f"\n===== 结果：通过 {passed} / {passed + failed} =====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
