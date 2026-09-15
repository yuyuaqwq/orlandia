# -*- coding: utf-8 -*-
"""v101.23d C 级：对话树『陈旧台词』静态防线（数据交叉校验，零误报）

规则（全部数据驱动，不改引擎）：
  R1 多任务 giver（≥2 主线）且有对话树 → quest_talk 必须有 texts 变体或 text_from
     （防镇长/矮人长老复发：新任务加了但台词还是旧任务）
  R2 text_from 值必须合法（目前支持 story）
  R3 quest_talk 变体 need 里的任务 id 必须存在于 MAIN_QUESTS
  R4 变体 need quest_pending 的任务，其 giver 必须 == 该 NPC（防写错发布者）
"""
import sys, os, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def main():
    # giver → 主线任务列表（含支线 s 系列，只统计主线 q 系列）
    main_by_giver = collections.defaultdict(list)
    for q in C.MAIN_QUESTS:
        main_by_giver[q.get("giver")].append(q)
    all_qids = {q["id"] for q in C.MAIN_QUESTS}

    print("【R1 多任务 giver 的 quest_talk 必须有变体/text_from】")
    for npc_id, qs in sorted(main_by_giver.items()):
        if len(qs) < 2:
            continue
        if npc_id not in C.DIALOGUES:
            continue  # 无对话树 NPC 不受约束（走旧单轮逻辑）
        dlg = C.DIALOGUES[npc_id]
        node = (dlg.get("nodes") or {}).get("quest_talk")
        if not node:
            check(f"{npc_id}({len(qs)}任务) 无 quest_talk 节点", True, "— 无节点则无陈旧风险")
            continue
        has_protect = bool(node.get("texts")) or node.get("text_from") == "story"
        check(f"{npc_id}({len(qs)}任务) quest_talk 有变体或 text_from",
              has_protect, f"→ 只有默认 text，加新任务会念旧台词！")

    print("【R2 text_from 值合法】")
    for npc_id, dlg in C.DIALOGUES.items():
        for nid, node in (dlg.get("nodes") or {}).items():
            tf = node.get("text_from")
            if tf:
                check(f"{npc_id}.{nid} text_from={tf} 合法", tf == "story", f"→ 不支持 {tf}")

    print("【R3/R4 变体 need 任务 id 存在 + giver 匹配】")
    # R4 只对 quest_talk/quest_done_talk 强制 giver 匹配（接取/交付台词必须是自己的任务）；
    # welcome/闲聊节点允许引用任意任务状态（世界传闻类台词，如吟游诗人感知矿洞剧情）
    quest_nodes = ("quest_talk", "quest_done_talk")
    for npc_id, dlg in C.DIALOGUES.items():
        for nid, node in (dlg.get("nodes") or {}).items():
            for i, tv in enumerate(node.get("texts") or []):
                need = tv.get("need") or {}
                for k, v in need.items():
                    if k not in ("quest_pending", "quest_ready", "quest_done", "quest_active"):
                        continue
                    qid = v if isinstance(v, str) else ""
                    if not qid:
                        continue
                    check(f"{npc_id}.{nid}#{i} need {k}={qid} 任务存在",
                          qid in all_qids, f"→ quests.py 无此任务")
                    if nid not in quest_nodes:
                        continue  # 闲聊节点：giver 匹配不强制
                    mq = next((q for q in C.MAIN_QUESTS if q["id"] == qid), None)
                    if mq:
                        check(f"{npc_id}.{nid}#{i} {qid} giver={mq.get('giver')} == {npc_id}",
                              mq.get("giver") == npc_id,
                              f"→ 任务发布者是 {mq.get('giver')}，不该出现在 {npc_id} 的接取/交付台词")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
