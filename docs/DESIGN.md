# DESIGN.md — 航运智能账单助手

> Mode: **Operate**（任务型 SaaS 后台）  
> Skills: impeccable（operate / craft-floor）、design-taste-frontend（app-screens）、landing-page-design（仅借鉴品牌层级，不作落地页）

## 产品身份

- 名称：航运智能账单助手 · Shipping Billing AI
- 场景：航运 / 货代财务 — 单据解析、费用入账、AR/AP、审计
- 签名元素：四态操作芯片（新建 / 更新 / 无需修改 / 待复核）+ 左右账单对比板
- 气质：Premium · Enterprise · Minimal · Structured · Trustworthy

## 色彩（控制数量）

| Token | Hex | 用途 |
|-------|-----|------|
| brand | `#142B49` | 品牌字、侧栏强调、主标题 |
| accent | `#2563EB` | 主按钮、选中、链接 |
| accent-soft | `#EFF4FF` | 轻量选中底 |
| bg | `#F6F8FC` | 页面底 |
| surface | `#FFFFFF` | 卡片 / 面板 |
| ink | `#1F2937` | 主文字 |
| muted | `#64748B` | 次要文字 |
| line | `#E2E8F0` | 分隔 / 边框 |
| success | `#0D9488` | CREATE / 成功 |
| warning | `#D97706` | PENDING / 警告 |
| danger | `#DC2626` | 错误 |
| neutral | `#64748B` | NO_CHANGE |

原则：颜色用在**状态与数据**，不用在装饰性色块。不使用大面积渐变、玻璃拟态。

## 字体

系统中文字体栈（见 `.streamlit/config.toml`）。

| 角色 | 约等于 | 说明 |
|------|--------|------|
| 页面标题 | 22–24px / 600 | 不过大 |
| Section | 16–17px / 600 | |
| 正文 | 14–15px | |
| 辅助 | 12–13px / muted | |
| 指标数字 | tabular-nums | KPI / 金额 |

## 布局

- 内容区舒适留白，避免「空洞大标题 + 控件堆叠」
- 卡片：白底 + 1px `#E2E8F0`，圆角 10–12px，阴影极轻或无
- 间距阶梯：8 / 12 / 16 / 24 / 32
- 侧栏收窄视觉权重，选中态用中性底或文字色，不用大色块

## 组件

- 服务状态卡：配置 ≠ 已验证（文案必须诚实）
- KPI：数字主导，无彩色图标圆
- 操作标签：文字 + 语义色，不只靠颜色
- 空状态：引导去工作台，不填假数据
- 对比面板：左右同结构；变更字段克制高亮

## Anti-patterns（本项目禁止）

- 营销落地页式 Hero / 渐变大字
- KPI 四色图标圆 + 虚假涨跌
- 厚彩色左边框装饰条
- 默认 Streamlit 控件无分区堆叠
- 编造审计步骤或假进度
