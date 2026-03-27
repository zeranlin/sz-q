from __future__ import annotations

from .models import Finding


FURNITURE_TITLE_MAP: dict[str, tuple[str, ...]] = {
    "评分项与采购标的不相关": (
        "生产设备评分",
        "设备数量",
        "体系认证",
        "星级",
        "高级管理师",
        "软件著作权",
        "与采购标的不相关",
    ),
    "证书认证设置过多或过细": (
        "认证证书",
        "认证范围",
        "iso",
        "greenguard",
        "五星级",
        "中国环境标志",
        "绿色产品认证",
        "环保卫士认证",
        "产品安全认证",
    ),
    "检测报告要求前置且证明材料过严": (
        "检测报告",
        "cma",
        "cnas",
        "委托单位",
        "原件备查",
        "查询截图",
        "认e云",
        "本单位关于",
    ),
    "样品评分主观且量化不足": (
        "样品",
        "演示",
        "美观",
        "精美",
        "质感",
        "优评分标准",
        "良评分标准",
        "中评分标准",
        "差评分标准",
    ),
    "业绩要求及证明材料设置偏严": (
        "同类业绩",
        "中标通知书",
        "验收报告",
        "发票",
        "合同关键页",
        "完工项目",
    ),
    "技术参数存在倾向性或排他性": (
        "同一品牌",
        "进口品牌",
        "优质品牌",
        "保税库",
        "唯一授权",
        "只接受直接授权",
    ),
    "招标文件存在未定稿或模板残留问题": (
        "示例",
        "20xx",
        "xx月xx日",
        "x分",
        "扣？分",
        "***设备",
    ),
}


def normalize_furniture_title(title: str, finding: Finding) -> str:
    source = " ".join(
        [
            title or "",
            finding.review_type or "",
            " ".join(finding.quotes),
            finding.reason or "",
        ]
    ).lower()

    for normalized, keywords in FURNITURE_TITLE_MAP.items():
        if any(keyword in source for keyword in keywords):
            return normalized
    return title


def normalize_findings(findings: list[Finding], profile: str) -> list[Finding]:
    if profile != "furniture":
        return findings
    normalized: list[Finding] = []
    for finding in findings:
        normalized.append(
            Finding(
                title=normalize_furniture_title(finding.title, finding),
                risk_level=finding.risk_level,
                review_type=finding.review_type,
                line_refs=finding.line_refs,
                quotes=finding.quotes,
                reason=finding.reason,
                legal_basis=finding.legal_basis,
                source_category=finding.source_category,
            )
        )
    return normalized
