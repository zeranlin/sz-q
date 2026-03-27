from __future__ import annotations

import json

from .models import CandidateSpan
from .rules import LEGAL_BASIS_POOL, RuleCategory


SYSTEM_PROMPT = """你是政府采购招标文件合规审查专家。

你的任务不是总结文件，而是识别可能存在的合规风险。
你必须严格依据给定候选条款判断，不得编造原文，不得输出没有原文支持的结论。
输出必须是合法 JSON，不要输出 Markdown，不要输出解释性前言。"""


def build_category_prompt(category: RuleCategory, spans: list[CandidateSpan], max_findings: int = 8) -> str:
    span_blocks = []
    for idx, span in enumerate(spans, start=1):
        span_blocks.append(
            {
                "id": idx,
                "line_range": f"第{span.start_line}行-第{span.end_line}行",
                "trigger": span.trigger,
                "text": span.text,
            }
        )

    schema = {
        "findings": [
            {
                "title": "问题标题",
                "risk_level": "高风险/中风险/低风险",
                "review_type": category.review_type,
                "line_refs": ["第X行", "第Y行"],
                "quotes": ["原文摘录1", "原文摘录2"],
                "reason": "风险判断",
                "legal_basis": ["从候选法条池中选择的依据"],
            }
        ]
    }

    return f"""本轮只审查：{category.review_type}

审查目标：{category.description}

请在候选条款中识别真正值得输出的问题。没有风险的问题不要输出。

高风险通常指：
- 明显限制竞争
- 与采购标的不相关却进入评分或资格条件
- 通过证明材料、证书、业绩、检测方式等实质抬高门槛
- 文件存在未定稿、缺失、明显矛盾，足以影响采购公正性

中风险通常指：
- 证明形式偏严
- 分值梯度明显不合理
- 条款表达存在争议空间

低风险仅在确有必要时输出，否则宁可不写。

可选法律依据只能从以下列表中选择：
{json.dumps(LEGAL_BASIS_POOL, ensure_ascii=False, indent=2)}

输出 JSON schema：
{json.dumps(schema, ensure_ascii=False, indent=2)}

最多输出 {max_findings} 条。
如果没有明确风险，输出 {{"findings": []}}。

候选条款：
{json.dumps(span_blocks, ensure_ascii=False, indent=2)}
"""


def build_merge_prompt(findings_json: str) -> str:
    return f"""下面是同一份文件的初步审查结果，请做去重和合并。

要求：
- 合并同一主旨、同一条款、同一审查类型的重复问题
- 不要新增没有原文支撑的新问题
- 保留更完整的 line_refs、quotes、reason 和 legal_basis
- 输出格式仍然是 JSON：{{"findings": [...]}}

待合并结果：
{findings_json}
"""

