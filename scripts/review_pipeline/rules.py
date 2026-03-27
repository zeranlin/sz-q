from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


LEGAL_BASIS_POOL = [
    "《中华人民共和国政府采购法》",
    "《中华人民共和国政府采购法实施条例》第二十条",
    "《政府采购货物和服务招标投标管理办法》（财政部令第87号）第五十五条",
    "《政府采购需求管理办法》（财库〔2021〕22号）",
    "《深圳经济特区政府采购条例》",
    "《深圳经济特区政府采购条例实施细则》",
]


@dataclass(frozen=True)
class RuleCategory:
    key: str
    review_type: str
    description: str
    patterns: tuple[str, ...]


RULE_CATEGORIES: list[RuleCategory] = [
    RuleCategory(
        key="relevance",
        review_type="评分因素关联性审查",
        description="识别与采购标的不直接相关的评分内容，如设备、利润、与履约无直接关系的资质能力。",
        patterns=(
            r"生产设备",
            r"设备.*得\d+分",
            r"利润率|净利润率|财务报告",
            r"软件企业认定|ITSS|履约能力达标",
            r"体系认证|售后服务认证|五星级",
            r"软件著作权",
            r"高级管理师|项目经理证书|网络工程师|调音员",
        ),
    ),
    RuleCategory(
        key="qualification",
        review_type="资格条件合理性审查",
        description="识别资格条件或商务条件设置过高、本地化或特定组织结构要求。",
        patterns=(
            r"只接受直接授权|不接受逐级授权",
            r"本地|驻场|仓库|保税库",
            r"同一品牌",
            r"唯一授权|原厂授权",
            r"分公司",
        ),
    ),
    RuleCategory(
        key="performance",
        review_type="业绩设置合理性审查",
        description="识别业绩数量过高、证明材料过严、限定业绩范围过窄等问题。",
        patterns=(
            r"同类业绩",
            r"中标通知书",
            r"验收报告",
            r"发票",
            r"合同关键页",
            r"提供\d+个.*得满分",
        ),
    ),
    RuleCategory(
        key="certification",
        review_type="证书认证设置合理性审查",
        description="识别过多证书、认证范围过细、以证代评等问题。",
        patterns=(
            r"认证证书",
            r"ISO\d+",
            r"CQC|GREENGUARD",
            r"中国环境标志",
            r"绿色产品认证",
            r"产品安全认证",
            r"认证范围",
        ),
    ),
    RuleCategory(
        key="testing",
        review_type="检测报告与证明材料审查",
        description="识别大量检测报告、双资质、固定时间区间、限定委托单位等要求。",
        patterns=(
            r"检测报告",
            r"CMA|CNAS",
            r"原件备查",
            r"委托单位",
            r"查询截图|认e云|全国认证认可",
            r"本单位关于",
            r"检测报告须包含本项参数的全部内容",
        ),
    ),
    RuleCategory(
        key="sample",
        review_type="样品/演示/讲解审查",
        description="识别样品、演示、主观评分、现场程序负担等问题。",
        patterns=(
            r"样品",
            r"演示|讲解",
            r"优评分标准|良评分标准|中评分标准|差评分标准",
            r"美观|精美|质感|工艺",
            r"不提供样品不得分",
            r"签到",
        ),
    ),
    RuleCategory(
        key="technical_bias",
        review_type="技术参数倾向性审查",
        description="识别品牌、进口、排他性技术参数和绑定要求。",
        patterns=(
            r"进口品牌|优质品牌",
            r"接受进口|拒绝进口",
            r"同一品牌",
            r"指定|唯一",
            r"保税库",
        ),
    ),
    RuleCategory(
        key="template",
        review_type="文件完整性与模板残留审查",
        description="识别示例未删、占位符未替换、规则缺失和表述矛盾。",
        patterns=(
            r"示例",
            r"20XX|XX月XX日",
            r"x分|扣x分",
            r"扣？分",
            r"\*\*\*设备",
            r"可选",
        ),
    ),
]


FURNITURE_RULE_ENHANCEMENTS: dict[str, tuple[str, ...]] = {
    "relevance": (
        r"最基础生产设备|主要生产设备|具备以下生产设备",
        r"设备实物照片|设备购买合同|租赁设备",
        r"社会责任管理体系|企业标准化管理体系|创新评价体系",
        r"家具定制服务认证|家具防火阻燃质量等级认证",
        r"售后服务高级管理师",
    ),
    "qualification": (
        r"同一品牌",
        r"只接受直接授权",
        r"不接受逐级授权",
        r"境内.*保税库",
        r"零配件.*保税库",
    ),
    "performance": (
        r"办公家具类同类业绩|实验台类业绩|学生宿舍家具",
        r"项目发票|不少于30%的项目发票",
        r"完工项目",
    ),
    "certification": (
        r"中国环保产品认证|环保卫士认证",
        r"售后服务认证证书",
        r"五星级",
        r"GREENGUARD|人类工效学产品认证",
        r"低VOCS家具产品认证|产品健康认证证书|家具耐久性质量认证证书",
    ),
    "testing": (
        r"检测报告委托单位须为投标人",
        r"本单位关于《",
        r"检测报告须包含本项参数的全部内容",
        r"全国认证认可信息公共服务平台",
        r"认e云",
        r"固定时间.*检测报告|202[0-9]年.*检测报告",
    ),
    "sample": (
        r"样品材质|制作工艺|合理精美|美观度|质感",
        r"优评分标准|良评分标准|中评分标准|差评分标准",
        r"不提供样品不得分|样品不全.*不得分",
        r"现场演示人员|样品递交签到",
    ),
    "technical_bias": (
        r"优质进口品牌胶粘剂|优质品牌阻尼铰链",
        r"公寓组合床与宿舍椅要求为同一品牌",
        r"优质进口品牌",
    ),
    "template": (
        r"扣？分",
        r"\*\*\*设备",
        r"20XX",
        r"示例",
    ),
}


PROFILE_PROMPT_HINTS: dict[str, dict[str, tuple[str, ...]]] = {
    "furniture": {
        "relevance": (
            "重点警惕把生产设备、体系认证、星级服务认证、软件著作权等作为评分项。",
            "家具项目通常更应关注成品质量、环保性能、交付安装和售后响应，而不是企业证书储备。",
        ),
        "performance": (
            "重点警惕要求提供中标通知书、合同、验收报告、发票同时齐备的高证明门槛。",
        ),
        "certification": (
            "重点识别家具类项目中大量 ISO、环保、绿色、五星级、工效学、创新类证书叠加评分。",
        ),
        "testing": (
            "重点识别原材料和成品检测报告前置化、要求同时具备 CMA 和 CNAS、限定委托单位为投标人、限定固定时间区间。",
        ),
        "sample": (
            "重点识别样品以美观、精美、质感、优良中差等主观词评分，或要求不提供样品不得分。",
        ),
        "technical_bias": (
            "重点识别进口品牌、同一品牌绑定、原材料品牌偏好等倾向性表述。",
        ),
        "template": (
            "重点识别家具模板中残留的示例、xx、20XX、扣？分、***设备等未定稿痕迹。",
        ),
    }
}


def _merge_patterns(base: Iterable[str], extra: Iterable[str]) -> tuple[str, ...]:
    merged: list[str] = []
    for value in list(base) + list(extra):
        if value not in merged:
            merged.append(value)
    return tuple(merged)


def get_rule_categories(profile: str = "generic") -> list[RuleCategory]:
    if profile != "furniture":
        return RULE_CATEGORIES

    enhanced: list[RuleCategory] = []
    for category in RULE_CATEGORIES:
        extra = FURNITURE_RULE_ENHANCEMENTS.get(category.key, ())
        enhanced.append(
            RuleCategory(
                key=category.key,
                review_type=category.review_type,
                description=category.description,
                patterns=_merge_patterns(category.patterns, extra),
            )
        )
    return enhanced


def get_profile_prompt_hints(profile: str, category_key: str) -> tuple[str, ...]:
    return PROFILE_PROMPT_HINTS.get(profile, {}).get(category_key, ())


def compile_rules(profile: str = "generic") -> list[tuple[RuleCategory, re.Pattern[str]]]:
    compiled: list[tuple[RuleCategory, re.Pattern[str]]] = []
    for category in get_rule_categories(profile):
        for pattern in category.patterns:
            compiled.append((category, re.compile(pattern)))
    return compiled
