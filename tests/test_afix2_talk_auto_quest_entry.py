# -*- coding: utf-8 -*-
r"""审计 afix2 自查新开口：NPC 对话树「自动补任务入口」fail-closed 判据。

原实现（content/world_cmds.py:3220-3228）::

    try:
        npc_id = ctx.get("npc_id") or ""
        _auto_opt = {...}
        _expanded = self._side_menu_expand(ctx.get("_gid") or "", ctx.get("_qid") or "", npc_id, _auto_opt)
        if _expanded:
            opts = list(opts) + _expanded
    except Exception:
        pass

`pass` 盖住的是「自动补任务入口」。读支线清单一抛 ⇒ 整个补入口步骤被跳过 ⇒
**玩家在对话菜单里看不到「有委托可接」那个按钮**，NPC 名下的支线静默不可见：
回话照常渲染、只少一条选项、**零报错**。

**为什么这条按钮不能静默丢**：它是 v173.3 鱼鱼拍板加的**新手可发现性**功能
（docstring 原话「新手不再"找不到任务"」）。静默吞异常 = 把这个功能悄悄关掉，
而玩家与维护者都看不到任何线索。

**本判据真调生产函数** `content.world_cmds._render_talk_node`（不是重写一遍拼装）——
替身只做两件事：① 提供 `visible_options` / `node_text` ② 让
`_side_menu_expand` 按开关抛或返回固定子选项。§1 的两臂数字即原 bug 现场。
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401  导入即完成 sys.path 装配（引擎根 + extends）

import content.world_cmds as W  # noqa: E402

passed = failed = 0
from _check import bind_check  # noqa: E402  断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "content", "world_cmds.py")

NPC = {"icon": "X", "name": "测试NPC", "title": "村民"}
NODE = {"id": "n1"}
CTX = {"npc_id": "n1", "_gid": "g1", "_qid": "q1"}
DLG = {"start": "n1"}
BASE_OPTS = [{"text": "随便聊聊", "next": "__end__"}]
SUB_OPTS = [{"text": "【支线】测试委托", "next": "__end__",
             "action": {"side_take_one": "sq1"}}]


class _Self(object):
    def __init__(self, boom):
        self.boom = boom
        self.calls = 0

    def _side_menu_expand(self, gid, qq, npc_id, opt):
        self.calls += 1
        if self.boom:
            raise RuntimeError("存档行读不到")
        return [dict(x) for x in SUB_OPTS]

    def _tip(self, _k):
        return ""


class _Dlg(object):
    @staticmethod
    def visible_options(_dlg, _node, _ctx):
        return [dict(x) for x in BASE_OPTS]

    @staticmethod
    def node_text(_node, _ctx):
        return "……"


def _render(boom):
    """真调生产函数 _render_talk_node，返回玩家实际看到的那几行选项。"""
    self_ = _Self(boom)
    old = W._dlg
    W._dlg = _Dlg
    try:
        lines = W._render_talk_node(self_, dict(NPC), dict(DLG), dict(NODE), dict(CTX))
    finally:
        W._dlg = old
    return lines, self_


def _opts_of(lines):
    """玩家看到的**编号选项**行（剥掉序号）。

    ★ 要点：结尾的「结束对话」也是编号行（`talk.end_opt`），不是选项。
      第一版把它也收进来，于是 §1/§3 三条判据全红——**是我的取件正则不对**，
      不是被测代码变了。判据必须按「玩家的选项」取，不按「所有编号行」取。
    """
    out = []
    for l in lines:
        m = re.match(r"^\s*(\d+)\.\s*(.*)$", l)
        if m and m.group(2).strip() and m.group(2).strip() != "结束对话":
            out.append(m.group(2).strip())
    return out


def _code_lines():
    """生产源码的**代码**行（整行注释与行尾注释剔除，原文另存）。

    ★ 必须剔：修正自带一段说明性注释，里面逐字引用了 `except Exception: pass`
    —— 不剔就会「按文本定位撞上我自己写的解释」（L1102 同族）。
    """
    raw = io.open(SRC, encoding="utf-8").read().splitlines()
    code = []
    for l in raw:
        s = l.strip()
        if s.startswith("#"):
            code.append("")
            continue
        body, in_s, in_d, i = "", False, False, 0
        while i < len(l):
            ch = l[i]
            if ch == "\\" and in_s:
                body += l[i:i + 2]
                i += 2
                continue
            if ch == "'" and not in_d:
                in_s = not in_s
            elif ch == '"' and not in_s:
                in_d = not in_d
            elif ch == "#" and not in_s and not in_d:
                break
            body += ch
            i += 1
        code.append(body)
    return raw, code


def main():
    global passed, failed

    # ---- §1 端到端：读失败时支线入口整条消失（原 bug 现场）----
    lines_ok, self_ok = _render(False)
    check("§1 读成功 ⇒ 支线入口出现", _opts_of(lines_ok)[-1].endswith("测试委托"),
          repr(_opts_of(lines_ok)))

    boom_err = None
    try:
        lines_bad, self_bad = _render(True)
    except RuntimeError as exc:
        boom_err, self_bad = exc, None
    # 修后：抛（fail-closed）⇒ 不得静默返回一份「少一条选项」的菜单
    check("§1 读失败 ⇒ 上抛（不得静默少一条选项）", boom_err is not None,
          "返回了 %r" % (boom_err and boom_err or _opts_of(lines_bad)))
    check("§1 上抛的原因被保住（__cause__/消息可读）",
          boom_err is not None and "存档行读不到" in str(boom_err),
          str(boom_err))

    # ---- §2 结构：那段不再有 except…pass 吞 ----
    raw, code = _code_lines()
    idx = [i for i, l in enumerate(code) if "_auto_opt = " in l]
    check("§2 定位到自动补入口那段", len(idx) == 1, repr(idx))
    at = idx[0]
    seg = code[at:at + 12]
    swallowed = []
    for i in range(len(seg) - 1):
        if seg[i].strip().startswith("except") and seg[i].rstrip().endswith(":"):
            nxt = seg[i + 1].strip()
            if nxt == "pass" or nxt in ("return None", "return {}", "return []"):
                swallowed.append((at + i, seg[i].strip(), nxt))
    check("§2 自动补入口那段不再有 except…pass", not swallowed, repr(swallowed))

    # ---- §3 正常路逐字不变：有支线 / 无支线 / 已有任务类选项 三臂 ----
    lines_none, _ = _render(False)
    check("§3 正常路仍渲染原有选项 + 补入口", len(_opts_of(lines_none)) == 2,
          repr(_opts_of(lines_none)))

    class _SelfNoQuest(_Self):
        def _side_menu_expand(self, gid, qq, npc_id, opt):
            self.calls += 1
            return []          # NPC 名下没有可接支线 = 正常情况

    old = W._dlg
    W._dlg = _Dlg
    try:
        s2 = _SelfNoQuest(False)
        lines_nq = W._render_talk_node(s2, dict(NPC), dict(DLG), dict(NODE), dict(CTX))
    finally:
        W._dlg = old
    check("§3 NPC 无可接支线 ⇒ 只印原有选项（不过度补）",
          _opts_of(lines_nq) == ["随便聊聊"], repr(_opts_of(lines_nq)))

    class _DlgHasQuest(_Dlg):
        @staticmethod
        def visible_options(_dlg, _node, _ctx):
            return [{"text": "接主线", "next": "__end__", "action": {"quest_take": "mq1"}}]

    old = W._dlg
    W._dlg = _DlgHasQuest
    try:
        s3 = _Self(False)
        lines_hq = W._render_talk_node(s3, dict(NPC), dict(DLG), dict(NODE), dict(CTX))
    finally:
        W._dlg = old
    check("§3 节点已有任务类选项 ⇒ 不再补（闸门原语义）",
          _opts_of(lines_hq) == ["接主线"] and s3.calls == 0,
          "opts=%r calls=%d" % (_opts_of(lines_hq), s3.calls))

    print("passed=%d failed=%d" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
