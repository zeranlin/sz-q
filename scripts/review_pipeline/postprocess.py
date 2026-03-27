from __future__ import annotations

from collections import defaultdict

from .models import Finding


RISK_ORDER = {"高风险": 0, "中风险": 1, "低风险": 2}


def calibrate_risk_level(finding: Finding, profile: str) -> str:
    if profile != "furniture":
        return finding.risk_level

    if finding.risk_level != "高风险":
        return finding.risk_level

    title = finding.title
    source = " ".join([title, finding.review_type, finding.reason, " ".join(finding.quotes)]).lower()

    medium_titles = {
        "业绩要求及证明材料设置偏严",
        "样品评分主观且量化不足",
        "证书认证设置过多或过细",
    }
    high_titles = {
        "评分项与采购标的不相关",
        "检测报告要求前置且证明材料过严",
        "技术参数存在倾向性或排他性",
        "招标文件存在未定稿或模板残留问题",
    }

    if title in high_titles:
        return "高风险"

    if title in medium_titles:
        return "中风险"

    if any(keyword in source for keyword in ("示例", "20xx", "扣？分", "***设备", "同一品牌", "唯一授权")):
        return "高风险"

    if any(keyword in source for keyword in ("发票", "验收报告", "美观", "精美", "质感", "认证证书", "五星级")):
        return "中风险"

    return finding.risk_level


def calibrate_findings(findings: list[Finding], profile: str) -> list[Finding]:
    calibrated: list[Finding] = []
    for finding in findings:
        calibrated.append(
            Finding(
                title=finding.title,
                risk_level=calibrate_risk_level(finding, profile),
                review_type=finding.review_type,
                line_refs=finding.line_refs,
                quotes=finding.quotes,
                reason=finding.reason,
                legal_basis=finding.legal_basis,
                source_category=finding.source_category,
            )
        )
    return calibrated


def _best_risk(group: list[Finding]) -> str:
    return sorted((item.risk_level for item in group), key=lambda value: RISK_ORDER.get(value, 9))[0]


def aggregate_furniture_findings(findings: list[Finding], max_items: int = 6) -> list[Finding]:
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.title].append(finding)

    merged: list[Finding] = []
    for title, group in grouped.items():
        base = group[0]
        all_lines = sorted({line for item in group for line in item.line_refs})
        all_quotes: list[str] = []
        for item in group:
            for quote in item.quotes:
                if quote and quote not in all_quotes:
                    all_quotes.append(quote)
        all_basis: list[str] = []
        for item in group:
            for basis in item.legal_basis:
                if basis and basis not in all_basis:
                    all_basis.append(basis)
        reasons = [item.reason for item in group if item.reason]
        merged.append(
            Finding(
                title=title,
                risk_level=_best_risk(group),
                review_type=base.review_type,
                line_refs=all_lines,
                quotes=all_quotes[:4],
                reason=max(reasons, key=len) if reasons else "",
                legal_basis=all_basis[:4],
                source_category=base.source_category,
            )
        )

    merged.sort(key=lambda item: (RISK_ORDER.get(item.risk_level, 9), len(item.line_refs) * -1, item.title))
    if len(merged) <= max_items:
        return merged

    primary = merged[: max_items - 1]
    tail = merged[max_items - 1 :]
    if not tail:
        return primary

    combined_lines = sorted({line for item in tail for line in item.line_refs})
    combined_quotes: list[str] = []
    for item in tail:
        for quote in item.quotes:
            if quote and quote not in combined_quotes:
                combined_quotes.append(quote)
    combined_basis: list[str] = []
    for item in tail:
        for basis in item.legal_basis:
            if basis and basis not in combined_basis:
                combined_basis.append(basis)

    summary_reason = "其余条款主要集中在证明材料要求偏严、样品与证书评分叠加、分值设置不够均衡等方面，建议在正式发标前合并清理并统一调整。"
    primary.append(
        Finding(
            title="其他条款存在证明材料偏严或评分设置不优问题",
            risk_level=_best_risk(tail),
            review_type="综合性审查",
            line_refs=combined_lines,
            quotes=combined_quotes[:4],
            reason=summary_reason,
            legal_basis=combined_basis[:4],
            source_category="postprocess",
        )
    )
    primary.sort(key=lambda item: (RISK_ORDER.get(item.risk_level, 9), item.title))
    return primary


def postprocess_findings(findings: list[Finding], profile: str) -> list[Finding]:
    calibrated = calibrate_findings(findings, profile)
    if profile == "furniture":
        return aggregate_furniture_findings(calibrated, max_items=6)
    return calibrated
