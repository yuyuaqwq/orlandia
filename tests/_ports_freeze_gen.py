# -*- coding: utf-8 -*-
"""参数表**冻结基线**生成器（`test_package_mech_ports.py` 的伴随脚本）。

背景（B16 收口，2026-09-14）
---------------------------
宿主数据层 `game/data/*.py`（87 文件 / 74.7k 行）已物理删除，参数表的唯一真源 = 包内
`<framework>/games/orlandia/content/mech/*.py`。门禁原来那句「端口源码 == 宿主真源源码逐值」
失去参照物 ⇒ 换成**冻结基线**（键数 + canonical sha256 + 锚点），改值必须显式重跑本脚本。

用法
----
    python tests/_ports_freeze_gen.py            # 只报告当前值与基线是否一致（只读，exit 1=漂移）
    python tests/_ports_freeze_gen.py --write    # 把当前实测值写回 SKILL 里的 FROZEN_TABLE/FROZEN_SKILLKIND

注意：只改**有意**变化的表；写回前先看清 diff（本脚本会打印每张表的旧/新 sha 与键数）。
"""
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "test_package_mech_ports.py")


def _load_gate():
    spec = importlib.util.spec_from_file_location("_ports_gate_gen", GATE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_ports_gate_gen"] = mod
    spec.loader.exec_module(mod)
    return mod


def _measure(M):
    """实测：{表名: {n, sha, anchors}} + SkillKind 成员（同一套 canonical 实现 = 门禁里的那份）。"""
    out = {}
    for name, _src, _sline, prel, var in M.TABLES:
        p = os.path.join(M.PKG_ROOT, prel.replace("/", os.sep))
        if not os.path.isfile(p):
            out[name] = {"err": "端口文件缺失 %s" % p}
            continue
        view = M.ModView(p)
        v = M._resolve(view, view.value(var))
        if v == "«missing»":
            out[name] = {"err": "端口里取不到 %s" % var}
            continue
        anchors = []

        def _leaves(_v, _path=()):
            if isinstance(_v, dict):
                for _k, _x in _v.items():
                    yield from _leaves(_x, _path + (repr(_k),))
            elif isinstance(_v, (list, tuple)):
                for _i, _x in enumerate(_v):
                    yield from _leaves(_x, _path + (str(_i),))
            elif isinstance(_v, (set, frozenset)):
                return
            else:
                if not (isinstance(_v, str) and _v.startswith(M.EXPR)):
                    yield _path, _v

        for _p_, _val in _leaves(v):
            anchors.append([list(_p_), repr(_val)])
            if len(anchors) == 3:
                break
        out[name] = {"n": len(v) if isinstance(v, (dict, list, tuple, set, frozenset)) else 1,
                     "sha": M._canon_sha(v), "anchors": anchors}
    enc = M.ModView(os.path.join(M.PKG_ROOT, M.SKILL_KIND_REL.replace("/", os.sep)))
    out["§SkillKind"] = {"members": enc.enum_members("SkillKind")}
    return out


def _render(cur):
    lines = ["FROZEN_TABLE = {"]
    for name, v in cur.items():
        if name.startswith("§"):
            continue
        if "err" in v:
            lines.append('    # %s: 跳过（%s）' % (name, v["err"]))
            continue
        lines.append('    "%s": {' % name)
        lines.append('        "n": %d,' % v["n"])
        lines.append('        "sha": "%s",' % v["sha"])
        if v["anchors"]:
            lines.append('        "anchors": [')
            for path, val in v["anchors"]:
                lines.append('            (%s, %s),' % (repr(tuple(path)), val))
            lines.append('        ],')
        else:
            lines.append('        "anchors": [],')
        lines.append('    },')
    lines.append("}")
    lines.append("")
    lines.append("FROZEN_SKILLKIND = {")
    for k in sorted(cur["§SkillKind"]["members"]):
        lines.append('    "%s": %s,' % (k, repr(cur["§SkillKind"]["members"][k])))
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    write = "--write" in sys.argv[1:]
    M = _load_gate()
    cur = _measure(M)
    drift = []
    for name in [t[0] for t in M.TABLES]:
        v = cur.get(name) or {}
        old = M.FROZEN_TABLE.get(name)
        if "err" in v:
            print("❌ %-30s %s" % (name, v["err"]))
            drift.append(name)
            continue
        if old is None:
            print("❌ %-30s 基线里没有这张表" % name)
            drift.append(name)
            continue
        same = (v["n"] == old["n"] and v["sha"] == old["sha"]
                and [tuple(a[0]) for a in v["anchors"]] == [tuple(a[0]) for a in old["anchors"]])
        print("%s %-30s n=%-5d sha=%s… %s" % ("✅" if same else "❌", name, v["n"], v["sha"][:12],
                                              "" if same else "（基线 n=%d sha=%s…）"
                                              % (old["n"], old["sha"][:12])))
        if not same:
            drift.append(name)
    sk = cur["§SkillKind"]["members"]
    sk_same = sk == dict(M.FROZEN_SKILLKIND)
    print("%s §SkillKind 成员 %d 个" % ("✅" if sk_same else "❌", len(sk)))
    if not sk_same:
        drift.append("§SkillKind")
    if write:
        txt = open(GATE, encoding="utf-8").read()
        new = _render(cur)
        out = re.sub(r"FROZEN_TABLE = \{.*?\nFROZEN_SKILLKIND = \{.*?\n\}",
                     new.rstrip("\n"), txt, count=1, flags=re.S)
        if out == txt:
            print("⚠️ 未替换（正则没命中 FROZEN_TABLE/FROZEN_SKILLKIND 区块）")
            return 1
        with open(GATE, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        print("✍️ 已写回基线：%s" % GATE)
        return 0
    print("== 漂移 %d 处（加 --write 写回）" % len(drift))
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
