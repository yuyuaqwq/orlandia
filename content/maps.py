# -*- coding: utf-8 -*-
"""包内空间域（`content/maps.py`）—— 游戏仓 `game/core/maps.py`（229 行）**逐字端口**。

B13-L7（2026-09-14）。宿主 `game/core/maps.py` 已改成薄壳（本模块再导出 + 一行委托）。

搬的边界（**只改「宿主取件」两类**，正文逐字不动）
--------------------------------------------------
| 真源取件 | 包内替身 | 依据 |
|---|---|---|
| `SUBAREAS[map_id]` / `SUBAREA_LINKS_INDEX[map_id]`（形状读） | 包内 `maps` 域（`content/data/maps.json`：`nodes/roles/topology/links`） | 逐项对拍 121 图 **0 差异**（见下「等价证据」） |
| `SUBAREAS[map_id]`（`hidden`/`reveal` 读） | 包内 `subareas` 域（`content/data/subareas.json`，键 = 子区域 id） | 628 条**逐字段**与宿主装配后 `SUBAREAS` 相同、逐图列表序相同（对拍 0 差异） |
| `from .. import db`（`db.xxx`） | 模块级 `db`（`bind_host` 注入 / `sys.modules` 兜底） | 存储层留宿主（平台适配） |
| `MAPS` / `SUBAREAS`（两个装配钩子的**输入**） | 包内 `worlds` / `subareas` + 序真源 `exploration.order`（`content/catalog_space.py`） | 逐条对拍 0 差异（见下「等价证据」） |
| `ENCY_*` / `MONSTER_LOCS`（两个装配钩子的**产出**） | **`content/catalog_space.py`**（本模块 B15-W9 那份副本已删，审计 #26） | 见下「派生表落点」 |

派生表落点（审计 #26 收口，2026-09-19）
--------------------------------------------------
`ENCY_MAP_MONSTERS` / `ENCY_MONSTER_MAP` / `ENCY_MATERIAL_SOURCE` / `MONSTER_LOCS` 4 张装配期
派生表的**唯一真源 = `content/catalog_space.py`**：那里的 `build_ency()` / `build_monster_locs()`
在模块 import 期各跑一次（口径 = 该文件头「装配时机」：3 张 `ENCY_*` 用并入后 628 条，
`MONSTER_LOCS` 用并入前基础 430 条）。

本模块 B15-W9 曾把 4 张表的落点搬进来（`build_*` + 4 只模块级 dict + `_mirror_to_host` 兼容镜像）。
宿主 `game/data` 删除后，宿主壳 `game/core/maps.py` 的调用点一并消失 ⇒ 那条构建链**无人调用、
无人读取**：全仓 grep 的读点全在 `content/catalog_space.py`，且门面聚合序里 `content.catalog_space`
排在 `content.maps` 之前 ⇒ `C.ENCY_*` / `C.MONSTER_LOCS` 只会命中 catalog_space。
即：本模块那 4 张表成了第二份死副本，本次按「单源」删净（审计 #26）。
跨源对拍 0 差异的证据仍在：`overnight/_w9_dump_tables.py` / `_w9_cmp_tables.py`。
"""
from __future__ import annotations

import os

from saintess_engine.records import apply_replacements, placeholder, register_view, set_from_domains, update_in_place

_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>

# 读表口 = 引擎 records 形状：**域元数据唯一源** = 包内 `editor/domains.json`
# （S2 ②：只声明「我要哪些域」，落点由声明的 `kind` 派生；缺项/缺文件即报错，不静默空表）
_R = set_from_domains(_PKG_ROOT, ("maps", "subareas"))


# maps 域（图内形状）：{map_id: {name, roles, nodes:[{id,name,role}], topology, links?}}
_MAPS = placeholder("_MAPS")
_SUBS = placeholder("_SUBS")
_DOM_ROLES = placeholder("_DOM_ROLES")

from saintess_engine.wire import Wire
_WIRE = Wire()


def bind_host(**objs):
    """宿主替身注入（幂等）——键 = 模块名（`db`；`data` 镜像口随宿主 `game/data` 删除已撤）。"""
    _WIRE.bind(**objs)


from ._pkgref import DB as db            # B1：包内存储层（引擎 wire 形状的惰性句柄）


# ============================================================
# 包内域读口（maps / subareas 域）—— 宿主 `SUBAREAS` / `SUBAREA_LINKS_INDEX` 的等价物
# ============================================================
def _map_entry(map_id: str) -> dict:
    """该图的形状条目（未知图 → 空 dict，与宿主 `SUBAREAS.get(map_id) or []` 同义）。"""
    ent = _MAPS.get(map_id)
    return ent if isinstance(ent, dict) else {}


def _role_by_type(ent: dict) -> dict:
    """子区域 type（域 `nodes[].role` 原样）→ 引擎角色名（= 宿主 `_ROLE_BY_TYPE` 的**逆映射**，
    取值来自域 `roles`，不新增第二处定义）。"""
    return {v: k for k, v in ((ent.get("roles") or _DOM_ROLES) or {}).items()}


def _sa_rows(map_id: str) -> list:
    """该图子区域行（**声明序** = `maps.nodes` 序；行 = `subareas` 域原样）。
    与宿主 `SUBAREAS.get(map_id, [])` 逐字段等价（实测 628 条 0 差异）。"""
    return [row for row in (_SUBS.get(n.get("id")) for n in (_map_entry(map_id).get("nodes") or []))
            if isinstance(row, dict)]


def _subarea_links_index(map_id: str):
    """该图的显式网状连通表（无显式定义 → None，与宿主 `SUBAREA_LINKS_INDEX.get` 同义）。"""
    return _map_entry(map_id).get("links")


# ---- v183 引擎形状适配：本游戏的「角色映射」----------------------------------
# 引擎只认角色名（hub/through/exit），**取值**由内容侧给 —— 这三条映射就是全部内容。
_ROLES = {"hub": "hub", "through": "through", "exit": "exit"}


def map_space(map_id: str):
    """本图的引擎 `Space`（节点 = 子区域，角色 = type 映射；显式连通表优先）。

    不缓存：`SUBAREAS` 运行期可被副本克隆增补（缓存会读到半成品）；构造很便宜
    （每图 ≤ 十余节点），移动路径上的调用量级可接受。
    """
    from saintess_engine.space import MESH, Space
    ent = _map_entry(map_id)
    role_of_type = _role_by_type(ent)
    nodes = [{"id": n["id"], "name": n.get("name"), "role": role_of_type.get(n.get("role"))}
             for n in (ent.get("nodes") or [])]
    mesh = _subarea_links_index(map_id)
    # 旧数据兜底（v87 时期的老图）：城里没有「城镇出口」类型节点时，出入口退回
    # id 以 `_gate` 结尾者。属**内容策略**（引擎不认识 id 命名习惯），故在适配层算好传进去。
    gate_override = None
    if (nodes and nodes[0]["role"] == _ROLES["hub"]
            and not any(n["role"] == _ROLES["exit"] for n in nodes)):
        gate_override = next((n["id"] for n in nodes if str(n["id"]).endswith("_gate")), None)
    if mesh is not None:
        return Space(nodes=nodes, topology=MESH, roles=_ROLES, links=mesh,
                     label_key="name", gate=gate_override)
    topo = "star" if (nodes and nodes[0]["role"] == _ROLES["hub"]) else "chain"
    return Space(nodes=nodes, topology=topo, roles=_ROLES, label_key="name", gate=gate_override)


def map_center(map_id: str) -> str:
    """枢纽节点 id（星形图的中心）；链状/网状图无枢纽 → ""。"""
    sp = map_space(map_id)
    return sp.root if sp.role_of(sp.root) == _ROLES["hub"] else ""


def map_route(map_id: str, src: str, dst: str) -> list:
    """同图必经路径（**含两端**）；同点 → 单元素；任一端未知或不可达 → []。

    用途：把「不能直达，需要先经过 X、Y」这类提示从手算改成问引擎
    （v183 之前该判断在 travel / world 各抄了一份星形链首逻辑）。
    """
    return map_space(map_id).route(src, dst)


def subarea_links(map_id: str, subarea_id: str) -> list:
    """同图内可直达的子区域 id 列表（v183：派生搬进引擎 `saintess_engine.space`）。

    显式网状连通表（`maps` 域的 `links`）优先；否则按拓扑派生：**城镇星形
    （枢纽 ↔ 场所、通道 ↔ 出口，含无通道时枢纽直连出口的防断链分支）/ 野外线性**。
    结果**包含隐藏房间，不过滤** —— 隐藏房间的可见性由命令层过滤（历史契约不变）。

    注（v141 审计）：副本大陆克隆的 subareas 无命令层消费本函数 —— 保留待动态化；
    命令层副本移动走 SUBAREA_LINKS_INDEX（instance.py _subarea_arrive 直读数据表）。
    """
    return map_space(map_id).links(subarea_id)


def map_exit_subarea(map_id: str) -> str:
    """离开该图必须所在的子区域（v183：= 引擎 `Space.gate()`）。

    城镇：城镇出口子区域；非城镇：首个子区域（入口）。
    ★ 与 `map_entry_subarea` **同义** —— v183 之前这两份实现逐字重复，现已合一
    （两者都问引擎同一个 gate，名字保留只为调用方零改动）。
    """
    return map_space(map_id).gate()


def map_entry_subarea(map_id: str) -> str:
    """跨图进入该图的落点子区域（v183：= 引擎 `Space.gate()`，与 map_exit_subarea 同义）。

    城镇：出口子区域（从野外进城先到镇郊，再经东大街进广场）；非城镇：首个子区域。
    注：注册/传送/回家等「城内直达」场景用 subareas[0]（广场），不走城门。
    """
    return map_space(map_id).gate()


# ---- v115 网状子区域核心 ----

def _explore_count(group_id: str, qq_id: str, map_id: str) -> int:
    """当前探索计数：event_state key = reveal_{map_id}_{qq_id}。"""
    raw = db.get_event_state("reveal_{}_{}".format(map_id, qq_id))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def subarea_depth(map_id: str, sa_id: str) -> int:
    """从该图首个子区域（入口）算的深度（v183：口径由引擎定）。

    - 显式连通表 → 从入口 BFS（网状图没有天然顺序）
    - 否则 → 声明序（子区域列表位置：链状/星形图里顺序本身就是作者给的由近及远）
    """
    return map_space(map_id).depth(sa_id)


def is_hidden_room(map_id: str, sa_id: str) -> bool:
    """查 subareas 域中该子区域条目的 hidden 字段（默认 False）。"""
    for s in _sa_rows(map_id):
        if s.get("id") == sa_id:
            return bool(s.get("hidden"))
    return False


def reveal_met(cond, group_id: str, qq_id: str, map_id: str) -> bool:
    """reveal 条件是否满足。cond 形如：
    - "explore:N"：event_state key=reveal_{map}_{qq} 的探索次数 ≥ N
    - "item:道具名"：db.count_item > 0
    无 cond / 未知格式化 → True（开放）。"""
    if not cond:
        return True
    if cond.startswith("explore:"):
        try:
            need = int(cond.split(":", 1)[1])
        except (TypeError, ValueError):
            return False
        return _explore_count(group_id, qq_id, map_id) >= need
    if cond.startswith("item:"):
        item = cond.split(":", 1)[1]
        return db.count_item(group_id, qq_id, item) > 0
    return True


def reveal_progress(group_id: str, qq_id: str, map_id: str):
    """返回 (cur, need)——当前探索计数 与 本图需探索次数的最大值。
    本图无 explore: 型 reveal 房间 → 返回 (0, 0)。"""
    needs = []
    for s in _sa_rows(map_id):
        cond = s.get("reveal")
        if cond and cond.startswith("explore:"):
            try:
                needs.append(int(cond.split(":", 1)[1]))
            except (TypeError, ValueError):
                pass
    if not needs:
        return (0, 0)
    return _explore_count(group_id, qq_id, map_id), max(needs)


def bump_explore_count(group_id: str, qq_id: str, map_id: str):
    """探索计数 +1（G agent 会在每次野外探索时调用）。
    event_state key = reveal_{map_id}_{qq_id}。"""
    key = "reveal_{}_{}".format(map_id, qq_id)
    db.set_event_state(key, _explore_count(group_id, qq_id, map_id) + 1)


__all__ = [
    "map_space", "map_center", "map_route",
    "subarea_links", "map_exit_subarea", "map_entry_subarea", "subarea_depth",
    "is_hidden_room", "reveal_met", "reveal_progress", "bump_explore_count",
    "bind_host",
]


def _rebuild_view() -> list:
    """重读本模块声明的域 → 重建模块级派生状态；返回非容器替换序列（见文件头 ★ 视图）。

    容器（dict / list / set）就地更新（身份不变、内容已新）；非容器（tuple / frozenset /
    数字 / 字符串）本模块换引用，并把 `(旧对象, 新对象)` 序列交引擎做别名回填。
    import 期（见文件尾）与每次重载走**同一条路径**：本函数是唯一构建处。
    """
    global _MAPS, _SUBS, _DOM_ROLES

    # 旧对象：容器要就地更新、非容器要交代给引擎（全部先抓一遍，再重建）
    old = {
        '_MAPS': None, '_SUBS': None, '_DOM_ROLES': None,
    }
    for _n in list(old):
        old[_n] = globals()[_n]

    _MAPS = _R.maps.all()
    # subareas 域（房间内容）：{subarea_id: 源行原样 + 注入 map}
    _SUBS = _R.subareas.all()

    # `roles` 兜底（域里每张图都带 `roles`，实测 121/121 同值 —— 取第一个非空的当兜底，防单图缺键）
    _DOM_ROLES = next((e.get("roles") for e in _MAPS.values() if e.get("roles")), {})

    # ============================================================
    # 宿主替身口（`db` / `data`）—— 正文 `db.xxx(...)` 一行未改
    # ============================================================

    # 收敛：容器就地更新（身份不变）；非容器交引擎按身份回填
    out = []
    for name in old:
        before, new = old[name], globals()[name]
        if before is new:
            continue
        if isinstance(new, (dict, list, set)):
            if _same_container(before, new):
                update_in_place(before, new)   # 就地更新：消费方手头引用身份不变
                globals()[name] = before
            continue                           # 首次构建：全局已是新对象
        out.append((before, new))
    return out


from ._domainio import same_container as _same_container   # P0-4d 单源（纯函数小工具）


register_view(_rebuild_view, order=120)
apply_replacements(_rebuild_view(), __package__)
