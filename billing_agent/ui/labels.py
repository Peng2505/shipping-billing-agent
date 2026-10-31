"""Centralized Simplified Chinese UI copy for Streamlit.

Display-only translations. Backend enums / delivery JSON stay English.
"""

from __future__ import annotations

# --- Brand ---
APP_NAME = "航运智能账单助手"
APP_TAGLINE = "Shipping Billing AI"
APP_EN = "Shipping Billing AI"
PAGE_TITLE_BROWSER = "航运智能账单助手 · Shipping Billing AI"

# --- Navigation ---
NAV_DASHBOARD = "工作台"
NAV_DOCUMENTS = "文档解析"
NAV_BILLS = "账单核对"
NAV_AUDIT = "处理记录与审计"
NAV_JSON = "结果导出"

# --- Operation / posting (UI only) ---
OPERATION_LABELS = {
    "CREATE": "新建账单",
    "UPDATE": "更新账单",
    "NO_CHANGE": "无需修改",
    "PENDING_REVIEW": "待人工复核",
    "ALL": "全部",
}

POSTING_LABELS = {
    "AR": "应收账款（AR）",
    "AP": "应付账款（AP）",
    "null": "未判定",
    "ALL": "全部",
}

ORIGIN_LABELS = {
    "all": "全部",
    "native": "原始结构",
    "text_layer": "PDF 文本层",
    "ocr_api": "OCR 识别",
}

STAGE_LABELS = {
    "init": "初始化",
    "load_bills": "加载已有账单",
    "parse": "文档解析",
    "ocr": "OCR",
    "extract": "字段提取",
    "decide": "账单决策",
    "json": "生成 JSON",
}

STATUS_LABELS = {
    "ok": "完成",
    "failed": "失败",
    "running": "进行中",
    "skipped": "未执行",
    "blocked": "已阻塞",
    "empty": "无结果",
}


def operation_label(value: str | None) -> str:
    if value is None:
        return "—"
    return OPERATION_LABELS.get(value, value)


def posting_label(value: str | None) -> str:
    if value is None:
        return POSTING_LABELS["null"]
    return POSTING_LABELS.get(value, value)


def origin_label(value: str | None) -> str:
    if value is None:
        return "—"
    return ORIGIN_LABELS.get(value, value)


def stage_label(value: str | None) -> str:
    if not value:
        return "—"
    return STAGE_LABELS.get(value, value)


def status_label(value: str | None) -> str:
    if not value:
        return "—"
    return STATUS_LABELS.get(value, value)


# --- Demo ---
DEMO_BADGE = "演示模式"
DEMO_HINT_SHORT = (
    "当前已有账单带合成标记；处理链路仍为真实执行。"
)
DEMO_HINT_UPLOADED = "已有账单来自上传的合成样例 JSON（非默认模拟账本）；处理链路仍为真实执行。"
DEMO_HINT_DEFAULT = "已有账单来自系统默认模拟账本；处理链路仍为真实执行。"
DEMO_SIDEBAR = "演示模式 · 合成样例账本"
DEMO_SIDEBAR_UPLOADED = "演示模式 · 已上传样例账本"
DEMO_SIDEBAR_DEFAULT = "演示模式 · 默认模拟账本"

# --- Service status ---
SVC_LLM = "大模型"
SVC_OSS = "对象存储"
SVC_STORAGE = "文件外发"
SVC_OCR = "OCR 网关"
STATUS_CONFIGURED = "已配置"
STATUS_VERIFIED = "已验证"
STATUS_NOT_CONFIGURED = "未配置"
STATUS_CONNECT_FAILED = "连接失败"
STATUS_UNAVAILABLE = "暂不可用"
STATUS_ENDPOINT_ONLY = "已配置"

# --- Shared empty / errors ---
EMPTY_RUN_FIRST = "请先在工作台上传文件并开始处理。"
EMPTY_NO_DATA = "暂无数据"
EMPTY_NO_FILTER = "当前筛选条件下没有记录。"
ERR_PIPELINE = "处理出错"
ERR_MISSING_FILES = "请至少上传一个待处理文档。"
WARN_LLM_BLOCKED_TITLE = "大模型未配置"
WARN_LLM_BLOCKED = "请在 .env 中设置 LLM_API_KEY 与 LLM_MODEL。解析可继续，字段提取将阻塞。"
WARN_OSS_BLOCKED_TITLE = "文件外发未配置"
WARN_OSS_BLOCKED = (
    "当前未配置 FileUrlProvider（local_tunnel / R2 Worker / OSS）。"
    "勾选 OCR 授权前请先按 README 启动 LocalTunnel 或配置其他 Provider。"
)

# --- Dashboard ---
DASH_TITLE = "工作台"
DASH_CAPTION = "上传单据、设置记账主体并处理账单。"
DASH_SECTION_UPLOAD = "上传"
DASH_SECTION_CONFIG = "配置"
DASH_SECTION_INPUTS = "输入"
DASH_SECTION_SERVICES = "服务"
DASH_SECTION_RESULTS = "结果"
DASH_METRIC_CHARGES = "费用"
DASH_METRIC_AMOUNT = "金额合计"
DASH_EMPTY_SUMMARY_TITLE = "尚无结果"
DASH_EMPTY_SUMMARY = "上传单据并开始处理后，将在此显示处理摘要。"
DASH_UPLOAD_DOCS = "待处理文档"
DASH_UPLOAD_DOCS_HELP = "EML / PDF / PNG / JPG / TIFF / XLSX / XLS / DOCX / DOC / JSON"
DASH_UPLOAD_BILLS = "已有账单 JSON（可选）"
DASH_ENTITY = "记账主体"
DASH_ENTITY_HELP = "用于判定 AR / AP。"
DASH_SYNTH = "使用模拟已有账单"
DASH_SYNTH_HELP = "勾选后加载系统自带的示例已有账单，便于演示匹配与更新；关闭则可上传真实已有账单 JSON。"
DASH_OCR = "授权临时外发并调用 OCR"
DASH_OCR_HELP = (
    "勾选后，系统会把文件临时传到外网，供 OCR 服务读取。"
    "不勾选时，PDF 仍可按文本层解析，不会调用 OCR。"
)
DASH_OCR_ON_TITLE = "已授权 OCR"
DASH_OCR_ON = "本轮文件将经当前 Provider 临时外发。"
DASH_START = "开始处理"
DASH_CLEAR = "清空结果"
DASH_STATUS = "处理日志"
DASH_RUNNING = "正在处理…"
DASH_LAST_RUN = "最近一次处理"
DASH_IDLE_TITLE = "待处理"
DASH_IDLE = "上传文件后点击「开始处理」。"
DASH_ELAPSED = "耗时 {ms} ms"
DASH_SUMMARY = "处理摘要"
DASH_METRIC_FILES = "文件"
DASH_METRIC_DECISIONS = "决策"
DASH_WARNINGS = "提醒"
DASH_ERRORS = "错误"
DASH_OCR_SKIP_TITLE = "本次未执行 OCR"
DASH_OCR_SKIP = "PDF 文本层可用时将按其解析；需要 OCR 时请勾选授权。"
DASH_OCR_FAIL_TITLE = "OCR 未成功"
DASH_OCR_FAIL = "部分文件 OCR 失败。若展示文本层，不会标为 OCR 成功。"
DASH_BILLS_JSON_ERR = "已有账单 JSON 无效"
DASH_SOURCE_TEXT = "识别方式：PDF 文本层"
DASH_SOURCE_OCR = "识别方式：OCR"
DASH_SOURCE_MIXED = "识别方式：混合"

# --- Document centre ---
DOC_TITLE = "文档解析"
DOC_CAPTION = "原文、字段与费用证据。"
DOC_SELECT = "选择文档"
DOC_TYPE = "类型"
DOC_STATUS = "状态"
DOC_BLOCKS = "内容块"
DOC_ATTACHMENTS = "附件"
DOC_EMAIL = "邮件头"
DOC_OCR = "OCR"
DOC_OCR_STATUS = "OCR 状态"
DOC_OCR_ERR = "OCR 错误"
DOC_ORIGIN_HINT = "OCR 块 {ocr} · 文本层块 {text}"
DOC_OCR_RAW = "OCR 原始 JSON"
DOC_TREE = "文件结构"
DOC_BLOCKS_SECTION = "内容块"
DOC_ORIGIN_FILTER = "来源"
DOC_EXTRACT = "提取字段"
DOC_EXTRACT_FAIL = "提取失败"
DOC_EXTRACT_MISSING = "无提取结果"
DOC_EXTRACT_MISSING_BODY = "该文档尚无完成提取。"
DOC_EXTRACT_META = "{model} · {strategy} · {ms} ms · 工具 {tools}"
DOC_COL_FIELD = "字段"
DOC_COL_VALUE = "值"
DOC_COL_EVIDENCE = "依据"
DOC_CHARGES_KEPT = "费用明细"
DOC_COL_RAW = "原始费用名"
DOC_COL_NATURE = "性质"
DOC_COL_AMOUNT = "金额"
DOC_COL_CURRENCY = "币种"
DOC_COL_SOURCE = "来源"
DOC_EXCLUDED = "已排除"
DOC_ISSUES = "证据问题"
DOC_TREE_LINE = "{pad}- `{name}` · {dtype} · {status}"

# --- Bill review ---
BILL_TITLE = "账单核对"
BILL_CAPTION = "费用、操作类型与差异。"
BILL_FILTER_OP = "操作"
BILL_FILTER_POST = "收付"
BILL_COL_OP = "操作"
BILL_COL_CHARGE = "费用名称"
BILL_COL_AMOUNT = "金额"
BILL_COL_CURRENCY = "币种"
BILL_COL_POST = "收付"
BILL_COL_MATCH = "匹配"
BILL_COL_MATCH_STATUS = "匹配状态"
BILL_COL_BILL_ID = "账单编号"
BILL_COL_REF = "单据号"
BILL_DETAIL = "明细"
BILL_MATCH = "匹配过程"
BILL_NO_MATCH = "无匹配账单。"
BILL_ARAP = "收付判断"
BILL_POSTING = "入账类型"
BILL_COMPARE = "账单对比"
BILL_MATCHED = "已匹配账单"
BILL_INCOMING = "已有账单"
BILL_NO_EXISTING = "未找到已有账单"
BILL_PROPOSED = "拟写入"
BILL_CHANGES = "字段变更"
BILL_COL_OLD = "原值"
BILL_COL_NEW = "新值"
BILL_CHANGED = "已变更"
BILL_NO_CHANGES = "无字段变更。"
BILL_VALIDATION = "校验"
BILL_AUDIT = "决策依据"
BILL_REVIEW_NOTE = "复核备注（仅会话）"
BILL_REVIEW_PLACEHOLDER = "备注"
BILL_EMPTY_DECISIONS_TITLE = "暂无决策"
BILL_EMPTY_DECISIONS = "未产生账单决策。"
BILL_HINTS_SUMMARY = "{n} 项编号格式提醒"
BILL_WARN_SUMMARY = "{n} 项业务警告"
BILL_ERR_SUMMARY = "{n} 项阻断错误"

# --- Audit ---
AUDIT_TITLE = "处理记录与审计"
AUDIT_CAPTION = "处理摘要、阶段与依据。"
AUDIT_TIMELINE = "阶段时间线"
AUDIT_COL_AT = "时间"
AUDIT_COL_STAGE = "阶段"
AUDIT_COL_STATUS = "状态"
AUDIT_COL_FILE = "文件"
AUDIT_COL_DETAIL = "说明"
AUDIT_NO_STAGES = "尚无阶段事件。"
AUDIT_SVC = "服务配置"
AUDIT_DOC = "文档"
AUDIT_TOOLS = "工具调用"
AUDIT_NORM = "费用标准化"
AUDIT_COL_RAW = "原始名称"
AUDIT_COL_STD = "标准名称"
AUDIT_COL_ALIAS = "别名"
AUDIT_MATCH_STEPS = "匹配"
AUDIT_POSTING = "收付"
AUDIT_VALIDATION = "校验"
AUDIT_REASONS = "依据"
AUDIT_NONE = "（无）"
AUDIT_NO_VALIDATION = "无校验问题。"
AUDIT_FINGERPRINT = "指纹"
AUDIT_WARNINGS = "提醒"
AUDIT_ERRORS = "错误"
AUDIT_EXTRACT = "提取"
AUDIT_REVIEW_REASON = "复核原因"
AUDIT_SUMMARY = "本轮摘要"
AUDIT_TECH = "技术细节"

# --- JSON ---
JSON_TITLE = "结果导出"
JSON_CAPTION = "交付 JSON（字段名与枚举保持英文）。"
JSON_EMPTY_TITLE = "暂无 JSON"
JSON_EMPTY = "尚未生成交付 JSON。"
JSON_VALID_TITLE = "结构校验"
JSON_VALID = "Schema 通过 · {n} 条"
JSON_INVALID_TITLE = "结构校验失败"
JSON_INVALID = "Schema 未通过"
JSON_PREVIEW = "完整 JSON"
JSON_DL_RESULT = "下载 result.json"
JSON_DL_REPORT = "下载处理报告"
JSON_REPORT = "处理报告"
JSON_SCHEMA_NOTE = "结构校验通过只表示 JSON 形状合法，不代表无业务风险。"
JSON_BIZ_SUMMARY = "业务摘要"
JSON_RECORD = "当前记录"

# --- Sidebar ---
SIDEBAR_FLOW = "解析 → 提取 → 决策 → 导出"
SIDEBAR_DECISIONS = "决策"
SIDEBAR_SESSION = "本会话"
SIDEBAR_NO_RESULT = "尚未处理。"
SIDEBAR_ERRORS = "错误"

_MESSAGE_MAP = (
    (
        "OCR upload disabled for this run (enable_ocr_upload=False). "
        "PDF text_layer may still be used and is labelled text_layer, not OCR. "
        "Authorize OCR on the Dashboard only after data-use approval.",
        "本次未授权调用 OCR；已使用 PDF 文本层解析。",
    ),
    (
        "OCR upload disabled for this run (enable_ocr_upload=False). "
        "PDF text_layer may still be used and is labelled text_layer, not OCR. "
        "Set the Dashboard checkbox or AUTHORIZE_OCR_UPLOAD=1 only after data-use approval.",
        "本次未授权调用 OCR；已使用 PDF 文本层解析。",
    ),
    (
        "OCR upload was not authorized for this run; OCR was not called. "
        "PDF text_layer (if any) may still be used.",
        "本次未授权调用 OCR，未发起识别；如有 PDF 文本层仍可解析。",
    ),
    ("Existing bills JSON invalid:", "已有账单 JSON 无效："),
    ("No input files provided", "未提供待处理文件"),
    ("LLM not configured (set LLM_API_KEY and LLM_MODEL)", "大模型未配置"),
    ("Extraction skipped", "已跳过字段提取"),
    ("OCR result unavailable; only the PDF text layer (origin=text_layer) is present.",
     "OCR 不可用；当前仅有 PDF 文本层。"),
    ("No text layer and no OCR result: document content is unavailable.",
     "无文本层且无 OCR 结果。"),
    ("No file URL provider configured", "未配置文件外发服务"),
    ("OCR was not called.", "未调用 OCR。"),
)


def localize_message(text: str | None) -> str:
    """Display Chinese for operators; strip internal status codes from prose."""
    if not text:
        return ""
    out = text
    for en, zh in _MESSAGE_MAP:
        if en in out:
            out = out.replace(en, zh)
    # Phrase-level first
    out = out.replace("OCR FAILED", "OCR 失败")
    out = out.replace("OCR BLOCKED", "OCR 未配置")
    out = out.replace("OCR SKIPPED", "OCR 未执行")
    out = out.replace("OCR SUCCESS", "OCR 成功")
    out = out.replace("PDF text_layer available", "已使用 PDF 文本层")
    out = out.replace("text_layer", "文本层")
    out = out.replace("not OCR", "非 OCR 结果")
    # Raw codes → Chinese (codes remain in technical JSON/logs)
    out = out.replace("[OCR_NOT_AUTHORIZED]", "")
    out = out.replace("OCR_NOT_AUTHORIZED", "未授权")
    out = out.replace("[STORAGE_NOT_CONFIGURED]", "")
    out = out.replace("STORAGE_NOT_CONFIGURED", "文件外发未配置")
    out = out.replace("[NOT_CONFIGURED]", "")
    out = out.replace("NOT_CONFIGURED", "未配置")
    out = out.replace("[NOT_APPLICABLE]", "")
    out = out.replace("NOT_APPLICABLE", "不适用")
    out = out.replace("enable_ocr_upload=False", "未勾选 OCR 授权")
    out = out.replace("enable_ocr_upload=false", "未勾选 OCR 授权")
    out = out.replace(" blocks)", " 块)")
    out = out.replace(" blocks", " 块")
    # Tidy leftover punctuation after code stripping
    while "  " in out:
        out = out.replace("  ", " ")
    out = out.replace("：;", "：").replace(";;", ";").replace(" : ", "：").strip(" ;")
    return out
