from __future__ import annotations

from .models import Finding


def render_markdown(findings: list[Finding]) -> str:
    lines: list[str] = ["# 审查结果", "", "**问题明细**", ""]
    for idx, finding in enumerate(findings, start=1):
        lines.append(f"**{idx}. {finding.title}**")
        lines.append(f"问题定性：**{finding.risk_level}**")
        lines.append("")
        lines.append(f"审查类型：{finding.review_type}")
        lines.append(f"原文位置：{'；'.join(finding.line_refs)}")
        lines.append("原文摘录：")
        for quote in finding.quotes:
            lines.append(f'- “{quote}”')
        lines.append("")
        lines.append("风险判断：")
        lines.append(finding.reason)
        lines.append("")
        lines.append("法律/政策依据：")
        for basis in finding.legal_basis:
            lines.append(f"- {basis}")
        lines.append("")

    if not findings:
        lines.extend(
            [
                "**1. 未发现明确高风险条款**",
                "问题定性：**低风险**",
                "",
                "审查类型：初步审查",
                "原文位置：无",
                "原文摘录：",
                "- “未命中明确高风险规则，建议人工抽查评分项、技术参数、样品和业绩条款。”",
                "",
                "风险判断：",
                "自动审查未发现明确高风险条款，但这不等于完全无风险，仍建议人工复核。",
                "",
                "法律/政策依据：",
                "- 《政府采购需求管理办法》（财库〔2021〕22号）",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"

