# WorkBuddy OSS 最终产品架构与长期规划

版本：v4.0 Active Master Plan
日期：2026-06-01
定位：WorkBuddy OSS 当前唯一总准线。新窗口、新 Agent、后续交接都应先读本文档，再读 `docs/` 记忆库。

---

## 0. 最终结论

本项目最终建议采用：

- 仓库名：`WorkBuddy OSS`
- 产品名：`WorkBuddy OSS`
- 一句话定位：面向中国团队的开源 IM Agent 工作流中台，把飞书、企业微信、钉钉、聊天记录和业务消息转化为可跟踪、可审批、可复盘的业务流程。

核心判断：

1. 不做另一个 Dify、Coze、RAGFlow，也不做通用 Agent 搭建平台。
2. 不做纯聊天机器人，而是做“IM 消息到业务对象”的自动化中台。
3. 国内 IM Agent 网关是底座，业务对象层是核心，场景 Agent 是开源模板。
4. 第一批核心场景包括：客服工单知识 Agent、私域社群运营 Agent、销售线索跟进 Agent、招聘与入职 Agent。
5. 企业级可用的关键不是“AI 自动回复”，而是“AI 生成草稿、人类确认执行、系统完整留痕”。

当前执行结论：

1. 不要急着开源发布，先把本地和私有化产品做完整。
2. 飞书是真实优先环境，不再只是未来阶段；可以真实收消息、真实验收。
3. 对外发送必须经过审批、发送预览、安全提示和审计留痕。
4. 企业微信是第二优先级；当前可 mock，但配置入口、适配器结构和数据模型必须朝真实接入推进。
5. 钉钉排在企微之后，不能打断飞书和企微主线。
6. 所有密钥、模型配置、渠道配置必须能从前端配置中心输入，不能要求用户手写代码文件。
7. 所有产品显示、记录、验收说明默认使用北京时间 `Asia/Shanghai`。
8. 当前开发节奏按“大版本主线 + 小版本补丁池”推进，不再每次做零散小补丁。
9. 当前大版本是 `v1.1.x 私有运行安全与验收`；本地代码缺口已经归零，已进入本地正式收口和维护稳定性扫尾。
10. 本文档是顶层目标；当前运行状态和补丁池以 `docs/KNOWN_ISSUES.md` 和 `docs/ROADMAP.md` 为准。

最终产品形态：

```text
国内 IM Agent 网关
  ↓
统一消息模型
  ↓
Agent Router
  ↓
业务对象中台
  ├── 工单 Ticket
  ├── 任务 Task
  ├── 线索 Lead
  ├── 候选人 Candidate
  ├── 知识 Knowledge
  └── 报告 Report
  ↓
人工审批与审计
  ↓
业务场景 Agent 模板
```

---

## 0A. 新窗口 / 新 Agent 必读交接

如果重新开一个窗口，或换一个 Agent 继续开发，必须按下面顺序理解项目：

1. 先读 `/path/to/workbuddy-oss/MASTER_PLAN_FINAL.md`。
2. 再读 `/path/to/workbuddy-oss/README.md`。
3. 再读 `/path/to/workbuddy-oss/docs/ROADMAP.md`。
4. 再读 `/path/to/workbuddy-oss/docs/KNOWN_ISSUES.md`。
5. 再读 `/path/to/workbuddy-oss/docs/ROADMAP.md`。

当前项目状态：

- 当前本地版本：`v1.1.11`
- 当前大版本：`v1.1.x 私有运行安全与验收`
- 最新本地提交以 `git log --oneline -5` 为准。
- 本地 `main` 与远端 `origin/main` 需要保持同步；用户已确认后续每次更新都要本地 commit 并 push 到 GitHub。
- 当前 API：`http://127.0.0.1:8000`
- 当前 Web：`http://127.0.0.1:5173`
- 飞书 worker 不要擅自启动，避免误碰真实接收环境；需要真实验收时用 `npm run dev:feishu-stream`。

当前未跟踪项不要误删：

- `docs/assets/workbuddy_v0.12.0_demo.mp4`
- `generated_documents/`
- `scripts/`

每次继续开发时的固定要求：

- 先确认当前大版本，不要随意跳版本。
- 除非阻塞验收，否则小问题写入 `docs/ROADMAP.md`。
- 每个版本结束必须说明：本版做了什么、什么是新增、什么是优化、什么是修复、最终结果是什么、用户如何人工验收、下个版本规划是什么。
- 涉及代码改动后必须按需要运行：
  - `npm run build:web`
  - `.venv/bin/python -m compileall apps/api`
  - 必要时 `npm run check:feishu-stream`
- 必要时重启 API/Web/worker。
- 每个版本结束要本地 git commit。
- 每个版本结束要 push 到 GitHub `origin/main`，除非用户当次明确要求不要 push。

---

## 1. 项目边界

### 1.1 不是什么

本项目不做以下事情：

| 不做 | 原因 |
|---|---|
| 不做 Dify / Coze 竞品 | 通用 AI 应用搭建平台已经很拥挤 |
| 不做单纯聊天机器人 | 聊天回复价值有限，难形成企业业务闭环 |
| 不做完整 CRM / ATS / SCRM | 重型业务系统开发成本高，且商业产品成熟 |
| 不做模型平台 | 模型调用只做兼容层，不做训练、推理、模型托管 |
| 不做大而全 OA | 项目重点是 IM 消息驱动的业务工作流 |

### 1.2 是什么

本项目要做的是：

| 是什么 | 说明 |
|---|---|
| 国内 IM Agent 网关 | 统一接入飞书、企业微信、钉钉、Webhook、CSV 聊天记录 |
| 消息结构化中间层 | 把非结构化聊天消息变成标准 MessageEvent |
| 业务对象生成器 | 从消息中生成工单、线索、任务、候选人、知识条目 |
| 人机协同工作台 | AI 生成建议，人类审批后执行，对外输出有留痕 |
| 场景 Agent 模板库 | 提供客服、社群、销售、招聘等可直接复用的业务 Agent |
| 开源插件生态 | 允许社区贡献新的 IM 适配器、新 Agent、新工具 |

### 1.3 为什么这个方向成立

中国企业大量真实工作流发生在 IM 里：

- 客服在企业微信里处理客户问题。
- 运营在微信群、企微群、飞书群里维护用户。
- 销售在私聊和群聊中推进线索。
- HR 在飞书、钉钉里安排候选人、面试、入职。
- 管理者依赖群消息、日报和人工同步了解进度。

这些工作流的共同问题不是“有没有 AI 聊天能力”，而是：

- 消息很多，但没有结构化。
- 重要事项靠人记，容易漏。
- AI 能回答，但不能变成任务、工单、线索、报告。
- 人工接管、审批、审计没有闭环。
- 管理者看不到过程数据，也无法复盘。
- 开源项目大多停留在模型、RAG、Bot 接入层，缺少业务闭环层。

所以本项目的真正机会是：

> 做一个面向中国团队 IM 场景的开源业务 Agent 中台，把聊天消息变成可执行、可追踪、可复盘的业务流程。

---

## 2. 市场缺口分析

### 2.1 已经拥挤的区域

| 类型 | 代表产品 / 项目 | 拥挤原因 |
|---|---|---|
| 通用 Agent 平台 | Dify、Coze、LangGraph、Flowise | 产品成熟，生态丰富，新项目难差异化 |
| RAG 知识库 | RAGFlow、MaxKB、FastGPT | 已有多个成熟开源项目 |
| 多平台聊天机器人 | AstrBot、LangBot、OpenClaw | 偏消息接入和聊天能力，业务层不足 |
| 传统工单系统 | Frappe Helpdesk、Zammad | 工单流程成熟，但 AI 和 IM 原生不足 |
| 商业 SCRM | 微伴助手、尘锋、销售易等 | 商业能力强，但闭源、重、价格高 |
| 商业招聘系统 | Moka、北森、飞书招聘等 | 完整 ATS 成熟，但开源轻量 AI 助手少 |

### 2.2 真正值得切入的缺口

| 缺口 | 现状 | 本项目机会 |
|---|---|---|
| 国内 IM 统一接入 + 业务模板层 | 多数项目有 Bot 能力，但缺业务对象层 | 做统一 MessageEvent + Agent Router + Action |
| AI 草稿到人工审批闭环 | 很多工具直接回答，缺少审批和留痕 | 默认对外消息进入审批队列 |
| IM 消息转工单 / 线索 / 任务 | 业务信息散落在群聊和私聊 | 建立统一 Business Object 模型 |
| 私域社群智能运营开源方案 | 商业产品较多，开源轻量方案不足 | 从 CSV 群聊导入开始，逐步接企微 |
| 销售跟进轻量 AI 助手 | CRM 太重，销售不爱填 | 从聊天记录自动提取线索和下一步 |
| 招聘与入职 AI 流程助手 | ATS 重，创业团队用不起或用不动 | 做简历/JD/面试/入职的轻量闭环 |
| 可私有化部署的国内模型方案 | 企业担心数据外泄 | 支持 DeepSeek、Qwen、Moonshot、Ollama |

注意：文档和宣传中不要使用“完全空白”“没有任何项目”这类绝对表述。更稳妥的表达是：

> 缺少成熟的、国内 IM 原生的、可私有化部署的开源业务闭环方案。

---

## 3. 总体产品架构

### 3.1 总架构图

```text
┌─────────────────────────────────────────────────────────┐
│                    接入层 IM Gateway                     │
│  CSV 导入 │ 飞书 Bot │ 企业微信 │ 钉钉 │ 通用 Webhook │ API │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│                    消息标准化层                           │
│  签名验证 │ 去重幂等 │ 用户映射 │ 会话映射 │ MessageEvent │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│                    消息与事件存储                         │
│  messages │ conversations │ users │ raw_payloads │ imports │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│                    Agent Router                          │
│  系统命令 │ 群绑定 Agent │ 规则识别 │ LLM 意图分类 │ 人工收件箱 │
└─────────────┬─────────────┬──────────────┬──────────────┘
              │             │              │
┌─────────────▼───┐ ┌───────▼──────┐ ┌─────▼──────┐ ┌────────▼───────┐
│ 客服工单知识 Agent │ │ 私域社群 Agent │ │ 销售 Agent │ │ 招聘入职 Agent │
└─────────────┬───┘ └───────┬──────┘ └─────┬──────┘ └────────┬───────┘
              │             │              │                 │
┌─────────────▼─────────────▼──────────────▼─────────────────▼───────┐
│                         业务对象中台                                  │
│ Ticket │ Task │ Lead │ Candidate │ KnowledgeItem │ Report │ Action │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│                    任务引擎与审批队列                     │
│  Action 执行 │ AI 草稿 │ 人工确认 │ 编辑后发送 │ 拒绝 │ 超时提醒 │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│                    审计、报表与知识沉淀                   │
│  agent_runs │ audit_logs │ daily_reports │ KB 缺口 │ 复盘分析 │
└─────────────────────────────────────────────────────────┘

共享能力：
LLM Provider │ Prompt Registry │ Tool Registry │ RAG │ 权限 │ 多租户 │ 监控
```

### 3.2 核心设计原则

#### 原则一：先业务闭环，再自动化程度

第一优先级不是让 AI 自动回复，而是保证每一条重要消息能形成闭环：

```text
消息进入系统
  ↓
识别意图和业务实体
  ↓
生成业务对象
  ↓
进入任务、审批或报告
  ↓
人工确认或处理
  ↓
系统留痕
  ↓
复盘和沉淀
```

#### 原则二：AI 默认生成草稿，人类决定对外发送

面向客户、候选人、群成员的消息，默认进入审批队列。系统内部提醒、日报、周报可以配置自动发送。

强制审批场景：

- 投诉、退款、法律相关。
- 价格承诺、折扣承诺、合同条款。
- 招聘 Offer、薪资、录用拒绝。
- 涉及个人隐私或敏感信息。
- LLM 置信度低于阈值。
- 情绪负面或风险等级高。

#### 原则三：先规则后模型

高频、确定、可解释的场景优先用规则：

- “多少钱”“价格”“报价”进入销售或客服流程。
- “退款”“投诉”“坏了”进入客服工单。
- “简历”“面试”“入职”进入招聘入职流程。
- “日报”“总结”“群情况”进入报告流程。

只有规则不确定时再调用 LLM 意图分类。这样成本更低、速度更快、系统更可控。

#### 原则四：飞书优先真实闭环，CSV/Webhook 作为补充入口

早期方案里“先本地导入，再真实 IM”只适合 MVP。现在项目已经进入 `v0.15.x`，飞书是真实验收主线：

- 飞书必须优先保证真实收消息、真实生成业务对象、真实审批、真实发送、真实审计。
- CSV / JSON / Webhook 继续保留，用于回归测试、离线导入、演示数据和非 IM 系统接入。
- 企业微信排在飞书之后，可以先 mock，但配置入口、适配器结构、验签、解密、发送策略必须按真实接入设计。
- 钉钉排在企微之后，不得抢占当前大版本主线。
- 所有真实外发都必须先进入审批队列，不允许绕过审批直接发送。

#### 原则五：每次 AI 行为必须落库

每一次 LLM 调用都要记录：

- 输入消息。
- Prompt 模板版本。
- 模型名称。
- 输出结果。
- 结构化 Action。
- 置信度。
- 耗时。
- Token 用量。
- 是否进入审批。
- 最终是否发送。

这是企业信任、调试 Prompt、排查事故、优化成本的基础。

---

## 4. 核心模块设计

### 4.1 IM Gateway

职责：

- 接收各平台 Webhook 或事件流。
- 校验签名和来源。
- 解析文本、图片、文件、卡片、@消息。
- 下载附件。
- 将平台消息转换为统一 `MessageEvent`。
- 发送文本、富文本、卡片、审批结果。
- 处理重试、幂等、限流。

平台优先级：

| 平台 | 阶段 | 原因 |
|---|---|---|
| 飞书 Bot / Stream / Webhook | 当前主线 v0.15.x | 真实测试环境已具备，优先做正式闭环 |
| CSV / JSON / Adapter 导入 | 已具备，持续保留 | 回归测试、离线导入、演示数据、非 IM 接入 |
| 企业微信 | v0.17.x | 私域和客服价值最高，当前先 mock 和预留真实结构 |
| 钉钉 | v1.x 后续或企微稳定后 | 企业覆盖广，但不是当前上线阻塞项 |
| 通用 Webhook | 持续增强 | 允许外部系统接入 |
| 微信公众号 / 小程序客服 | 后续扩展 | 扩展到更广客户服务场景 |

统一消息模型：

```json
{
  "event_id": "evt_20260520_001",
  "tenant_id": "tenant_demo",
  "channel": "feishu",
  "channel_account_id": "feishu_app_001",
  "conversation_id": "conv_001",
  "external_conversation_id": "oc_group_xxx",
  "conversation_type": "group",
  "sender_id": "user_001",
  "sender_external_id": "ou_xxx",
  "sender_name": "张三",
  "message_id": "msg_001",
  "external_message_id": "om_xxx",
  "message_type": "text",
  "text": "这个方案多少钱？能不能给我发个报价？",
  "mentions": [],
  "attachments": [],
  "timestamp": "2026-05-20T10:30:00+08:00",
  "raw_payload": {}
}
```

### 4.2 Agent Router

路由顺序：

```text
Step 1: 系统命令
  /help /report /pause /bind /settings

Step 2: 会话绑定
  某个群已绑定客服 Agent、销售 Agent 或 HR Agent

Step 3: 关键词规则
  明确关键词直接路由

Step 4: LLM 意图分类
  输出 intent、confidence、entities、risk_level

Step 5: 人工收件箱
  置信度不足或风险过高时进入人工判断
```

路由输出：

```json
{
  "target_agent": "sales_lead_agent",
  "intent": "price_inquiry",
  "confidence": 0.86,
  "risk_level": "medium",
  "reason": "用户询问价格和报价，符合销售线索场景",
  "entities": {
    "product": "AI 客服方案",
    "requested_action": "报价"
  }
}
```

### 4.3 Business Object Center

本项目的关键抽象不是“Agent”，而是“业务对象”。

所有 Agent 最终都要把消息转成以下对象：

| 对象 | 说明 | 来源 |
|---|---|---|
| `Ticket` | 客服工单 | 投诉、退款、售后、技术问题 |
| `Task` | 待办任务 | 跟进、审批、补充信息、人工处理 |
| `Lead` | 销售线索 | 询价、试用、要资料、咨询方案 |
| `Candidate` | 候选人 | 简历、面试、入职 |
| `KnowledgeItem` | 知识条目 | 高频问题、标准答案、SOP |
| `Report` | 报告 | 群日报、销售周报、招聘进度 |
| `Approval` | 审批记录 | AI 回复草稿、外发内容 |
| `AgentRun` | AI 执行记录 | 每次模型调用和工具调用 |

### 4.4 Action Engine

Agent 不应该只返回自然语言，而应该返回结构化 Action：

```json
{
  "action_type": "create_lead",
  "priority": "high",
  "requires_approval": true,
  "reason": "用户询问价格，并要求发送报价",
  "business_object": {
    "type": "lead",
    "fields": {
      "customer_name": "未知",
      "interest": "AI 客服方案",
      "stage": "qualified",
      "score_delta": 30
    }
  },
  "draft_reply": "您好，我可以先给您发一版基础报价和适用场景说明。方便的话也可以了解一下您的团队规模，我再给您推荐更合适的版本。",
  "next_steps": [
    "创建销售线索",
    "生成报价跟进任务",
    "将回复草稿送入审批队列"
  ]
}
```

Action 类型：

| Action | 说明 |
|---|---|
| `create_ticket` | 创建客服工单 |
| `update_ticket_status` | 更新工单状态 |
| `create_lead` | 创建销售线索 |
| `update_lead_stage` | 更新线索阶段 |
| `create_followup_task` | 创建跟进任务 |
| `create_candidate` | 创建候选人 |
| `create_onboarding_task` | 创建入职任务 |
| `send_draft_to_approval` | 回复草稿进入审批 |
| `send_internal_report` | 发送内部报告 |
| `add_to_knowledge_base` | 沉淀知识库 |
| `escalate_to_human` | 转人工 |
| `request_missing_info` | 请求补充信息 |

### 4.5 Human Approval Queue

审批队列是企业级可信使用的核心。

状态机：

```text
pending_review
  ├── approved
  │     └── sent
  ├── edited
  │     └── sent
  ├── rejected
  └── expired
```

审批页面最少要显示：

- 原始消息。
- 识别意图。
- AI 草稿。
- 风险提示。
- 关联业务对象。
- 历史上下文。
- 操作按钮：发送、编辑后发送、忽略、转人工、加入知识库。

---

## 5. 场景 Agent 一：客服工单知识 Agent

### 5.1 产品定位

客服工单知识 Agent 是整个项目最能体现“IM 消息变业务对象”的核心场景。

它不是普通知识库问答机器人，而是：

> 从 IM 消息中识别客户问题、投诉、售后、退款和技术故障，自动创建工单，生成回复草稿，推动人工处理，并把高频问题沉淀为知识库。

适用场景：

- 企业微信客户群客服。
- SaaS 用户支持群。
- 电商售后群。
- 内部 IT 支持群。
- 产品用户反馈群。
- 项目交付支持群。

### 5.2 用户画像

| 用户 | 痛点 |
|---|---|
| 一线客服 | 重复问题多，漏回复，难判断优先级 |
| 客服主管 | 看不到问题积压、响应时间、投诉趋势 |
| 产品经理 | 用户反馈散落在群里，难沉淀成需求 |
| 技术支持 | 故障信息不完整，反复追问 |
| 创业团队负责人 | 不想上重型工单系统，但需要处理闭环 |

### 5.3 MVP 最小版本

第一版不接企微，先做本地导入：

1. 上传 CSV / 粘贴聊天记录。
2. 系统识别消息类型：咨询、投诉、退款、售后、故障、需求反馈。
3. 对需要处理的消息创建 Ticket。
4. AI 生成回复草稿。
5. 人工在审批队列里确认或编辑。
6. 系统生成当天客服日报。
7. 高频问题沉淀为知识库候选条目。

### 5.4 核心功能

#### 5.4.1 工单自动识别

意图分类：

| 意图 | 典型关键词 | 工单优先级 |
|---|---|---|
| `bug_report` | 不好用、报错、打不开、失败 | high |
| `complaint` | 投诉、太差、没人管、骗人 | urgent |
| `refund_request` | 退款、退货、不要了 | urgent |
| `how_to_question` | 怎么用、在哪里、如何设置 | normal |
| `feature_request` | 能不能加、希望支持、建议 | normal |
| `account_issue` | 登录不了、账号、权限 | high |
| `billing_issue` | 发票、扣费、续费、价格 | high |

#### 5.4.2 工单字段抽取

从消息中提取：

```json
{
  "title": "用户反馈小程序无法登录",
  "category": "account_issue",
  "priority": "high",
  "customer_name": "王女士",
  "product": "小程序后台",
  "problem": "登录失败",
  "error_message": "提示账号不存在",
  "expected_response_time": "2小时内",
  "missing_info": ["账号手机号", "截图"],
  "suggested_reply": "您好，我先帮您排查。方便发一下登录手机号和报错截图吗？"
}
```

#### 5.4.3 回复草稿与知识库检索

处理流程：

```text
用户问题
  ↓
识别意图和风险
  ↓
检索知识库
  ├── 命中且置信度高：生成带来源的回复草稿
  ├── 命中但不确定：生成谨慎草稿，提示人工核对
  └── 未命中：创建知识库缺口，转人工
  ↓
进入审批队列
```

#### 5.4.4 知识库缺口报告

每天生成：

```text
今日知识库缺口：
1. 小程序登录失败问题出现 12 次，知识库无标准答案
2. 发票申请流程出现 8 次，现有答案过期
3. 退款时效问题出现 5 次，回答不一致
```

### 5.5 数据模型

```sql
CREATE TABLE tickets (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           INT,
    source_message_id   BIGINT,
    title               VARCHAR(300),
    category            VARCHAR(80),
    priority            VARCHAR(20),
    status              VARCHAR(30) DEFAULT 'open',
    customer_name       VARCHAR(200),
    customer_external_id VARCHAR(200),
    product             VARCHAR(200),
    description         TEXT,
    missing_info_json   JSONB,
    owner_id            INT,
    due_at              TIMESTAMP,
    resolved_at         TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE ticket_events (
    id            BIGSERIAL PRIMARY KEY,
    ticket_id     BIGINT REFERENCES tickets(id),
    event_type    VARCHAR(50),
    content       TEXT,
    actor_id      INT,
    metadata_json JSONB,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE knowledge_gaps (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           INT,
    question            TEXT,
    examples_json       JSONB,
    occurrence_count    INT DEFAULT 1,
    suggested_answer    TEXT,
    status              VARCHAR(30) DEFAULT 'pending',
    created_at          TIMESTAMP DEFAULT NOW()
);
```

### 5.6 开发路线

本节只描述客服 Agent 的能力演进，不作为全项目版本路线。全项目版本路线以第 13 节和 `docs/ROADMAP.md` 为准。

| 阶段 | 功能 |
|---|---|
| 已有基础 | CSV/JSON/飞书消息进入系统，识别工单，生成回复草稿和客服日报 |
| 当前加强 | 飞书真实闭环、审批上下文、发送失败恢复、业务对象时间线 |
| 后续加强 | SLA 提醒、处理记录、负责人、知识引用、企微真实客户群 |
| 正式可用 | 多渠道客服工作台、工单状态流转、团队绩效报表、审计总账 |

---

## 6. 场景 Agent 二：私域社群运营 Agent

### 6.1 产品定位

私域社群运营 Agent 是群消息智能处理台，帮助运营人员：

- 发现重要消息。
- 识别高意向用户。
- 提取未回复问题。
- 生成回复草稿。
- 创建跟进任务。
- 输出群日报。

它不是群聊天机器人，也不是自动水群工具。

### 6.2 MVP 最小版本

1. 上传群聊 CSV / JSON。
2. AI 对消息分类。
3. 识别高意向用户。
4. 标记未回复问题。
5. 创建跟进任务。
6. 生成社群日报。

### 6.3 核心功能

#### 6.3.1 消息意图识别

| 意图 | 关键词规则 | 处理方式 |
|---|---|---|
| `purchase_inquiry` | 多少钱、价格、怎么买、有没有货 | 创建销售跟进 |
| `purchase_intent` | 我要、下单、购买、预定 | 高优先级跟进 |
| `complaint` | 投诉、不满、太差、骗人 | 创建风险任务 |
| `refund` | 退款、退货、不要了 | 创建客服工单 |
| `after_sale` | 坏了、不好用、质量问题 | 创建客服工单 |
| `general_question` | 怎么、可以、能不能 | 检索知识库并生成草稿 |
| `activity_feedback` | 活动、抽奖、签到 | 进入活动反馈统计 |
| `chat` | 其他 | 记录但不处理 |

#### 6.3.2 用户意向评分

```text
明确购买意向       +40
询问价格/库存      +20
要案例/演示/资料    +15
多次互动            +5
主动留联系方式      +30
投诉/退款           不加意向分，但提高风险等级
7 天无互动          -10
```

分数说明：

| 分数 | 状态 |
|---|---|
| 80-100 | 高意向，销售需当天跟进 |
| 50-79 | 中意向，进入跟进池 |
| 20-49 | 低意向，继续观察 |
| <20 | 普通成员 |

#### 6.3.3 群日报

日报内容：

- 今日消息数。
- 活跃成员数。
- 高频问题 Top 5。
- 高意向用户。
- 投诉 / 风险用户。
- 未回复问题。
- 待跟进任务。
- 知识库缺口。
- 明日运营建议。

### 6.4 数据模型

```sql
CREATE TABLE community_groups (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           INT,
    channel_id          INT,
    external_group_id   VARCHAR(200),
    name                VARCHAR(200),
    operator_id         INT,
    product_line        VARCHAR(100),
    enabled             BOOLEAN DEFAULT TRUE,
    config_json         JSONB,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE community_members (
    id                BIGSERIAL PRIMARY KEY,
    group_id          BIGINT REFERENCES community_groups(id),
    external_user_id  VARCHAR(200),
    display_name      VARCHAR(200),
    lead_score        FLOAT DEFAULT 0,
    risk_level        VARCHAR(20) DEFAULT 'low',
    tags_json         JSONB,
    first_seen_at     TIMESTAMP,
    last_active_at    TIMESTAMP
);

CREATE TABLE community_reports (
    id                      BIGSERIAL PRIMARY KEY,
    group_id                BIGINT,
    report_date             DATE,
    summary                 TEXT,
    hot_questions_json      JSONB,
    high_intent_users_json  JSONB,
    risk_users_json         JSONB,
    unresolved_items_json   JSONB,
    suggestions_json        JSONB,
    created_at              TIMESTAMP DEFAULT NOW()
);
```

---

## 7. 场景 Agent 三：销售线索跟进 Agent

### 7.1 产品定位

销售线索跟进 Agent 是轻量 AI 销售助理，不替代 CRM，而是解决：

- 线索散落在 IM 里。
- 销售不爱填 CRM。
- 不知道今天先跟谁。
- 跟进话术弱。
- 主管看不到线索质量和跟进风险。

### 7.2 MVP 最小版本

1. 手动创建线索。
2. 粘贴客户聊天记录。
3. AI 提取客户痛点、预算、时间、决策人、异议。
4. 自动评分。
5. 生成下一步话术。
6. 创建跟进提醒。
7. 展示简单销售漏斗。

### 7.3 核心功能

#### 7.3.1 线索结构化提取

输入：

```text
王总，某教育公司，想了解 AI 客服方案，预算大概 5 万，下周三下午再聊。他们现在客服人手不够，主要想先看能不能接企微。
```

输出：

```json
{
  "customer_name": "王总",
  "company": "某教育公司",
  "interest": "AI 客服方案",
  "pain_points": ["客服人手不够", "希望接入企微"],
  "budget": "5 万",
  "next_followup_time": "下周三下午",
  "intent_level": "high",
  "suggested_next_action": "发送企微接入案例和报价说明"
}
```

#### 7.3.2 意向评分

```text
明确购买意向       +40
要演示/试用        +30
问价格             +20
要资料/案例        +15
给出公司信息       +10
接触到决策人       +15
明确预算           +20
明确时间点         +20
7 天无回复         -20
异议较多           -10
提到竞品           -5
```

#### 7.3.3 销售阶段

| 阶段 | 说明 |
|---|---|
| `potential` | 潜在线索 |
| `contacted` | 已联系 |
| `qualified` | 已确认需求 |
| `proposal` | 已发方案 / 报价 |
| `negotiation` | 商务谈判 |
| `won` | 成交 |
| `lost` | 流失 |

#### 7.3.4 跟进提醒

| 提醒类型 | 触发条件 |
|---|---|
| 到期跟进 | `next_followup_at` 到期 |
| 沉睡线索 | 高分线索超过 X 天无跟进 |
| 决策临近 | 客户提到的决策时间临近 |
| 新高意向 | 新线索评分超过 60 |
| 报价后无反馈 | 报价后 X 天无回复 |

### 7.4 数据模型

```sql
CREATE TABLE leads (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       INT,
    name            VARCHAR(200),
    company         VARCHAR(200),
    title           VARCHAR(100),
    phone           VARCHAR(50),
    email           VARCHAR(200),
    im_external_id  VARCHAR(200),
    source          VARCHAR(100),
    owner_id        INT,
    stage           VARCHAR(50) DEFAULT 'potential',
    score           FLOAT DEFAULT 0,
    next_follow_at  TIMESTAMP,
    last_follow_at  TIMESTAMP,
    lost_reason     TEXT,
    won_amount      DECIMAL(12,2),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE lead_events (
    id           BIGSERIAL PRIMARY KEY,
    lead_id      BIGINT REFERENCES leads(id),
    event_type   VARCHAR(50),
    raw_content  TEXT,
    ai_summary   TEXT,
    occurred_at  TIMESTAMP,
    created_by   INT
);

CREATE TABLE lead_insights (
    id                    BIGSERIAL PRIMARY KEY,
    lead_id               BIGINT REFERENCES leads(id),
    lead_event_id         BIGINT,
    pain_points_json      JSONB,
    objections_json       JSONB,
    budget_level          VARCHAR(20),
    urgency_level         VARCHAR(20),
    decision_role         VARCHAR(50),
    suggested_next_action TEXT,
    confidence            FLOAT,
    created_at            TIMESTAMP DEFAULT NOW()
);
```

---

## 8. 场景 Agent 四：招聘与入职 Agent

### 8.1 产品定位

招聘与入职 Agent 是轻量 AI HR 助手，面向没有复杂 ATS 的小团队和创业公司。

它解决四个高频问题：

- 简历筛选慢。
- 面试问题临时想。
- 面试评价不结构化。
- 入职材料和 FAQ 重复沟通。

### 8.2 MVP 最小版本

1. 粘贴 JD。
2. 粘贴简历文本。
3. AI 输出匹配分、证据、风险点、缺失项。
4. 生成面试题。
5. 输入面试反馈。
6. 生成候选人评估报告。
7. 生成入职 Checklist。

### 8.3 核心功能

#### 8.3.1 JD 解析

输出：

```json
{
  "role": "AI 产品运营",
  "must_have_skills": ["用户运营", "Agent 理解", "PRD 写作"],
  "nice_to_have_skills": ["SaaS 经验", "数据分析"],
  "experience_level": "1-3 年",
  "risk_keywords": ["需要独立推进", "跨部门协作"]
}
```

#### 8.3.2 简历解析

提取：

- 姓名。
- 联系方式。
- 工作年限。
- 教育经历。
- 项目经历。
- 技能关键词。
- 行业经验。
- 简历亮点。
- 风险点。
- 空窗期。

#### 8.3.3 JD 匹配评分

评分必须带证据：

```json
{
  "score": 82,
  "recommendation": "interview",
  "matched": [
    {
      "requirement": "熟悉用户运营",
      "evidence": "曾负责 3 个社群的用户增长和活动运营"
    }
  ],
  "missing": [
    "缺少明确 SaaS 商业化经验"
  ],
  "interview_focus": [
    "重点追问是否独立写过 PRD",
    "验证对 Agent 产品边界的理解"
  ]
}
```

#### 8.3.4 入职流程

```text
候选人状态变为 hired
  ↓
选择岗位/部门入职模板
  ↓
生成入职任务清单
  ├── HR：合同、账号、设备、材料
  ├── 主管：导师、工位、目标、团队介绍
  └── 新员工：资料提交、制度阅读、工具配置
  ↓
入职当天 IM 推送
  ↓
进度追踪和超时提醒
  ↓
30/60/90 天试用期跟进
```

### 8.4 数据模型

```sql
CREATE TABLE jobs (
    id                 BIGSERIAL PRIMARY KEY,
    tenant_id          INT,
    title              VARCHAR(200),
    department         VARCHAR(100),
    headcount          INT DEFAULT 1,
    jd_text            TEXT,
    must_have_json     JSONB,
    nice_to_have_json  JSONB,
    status             VARCHAR(20) DEFAULT 'open',
    created_at         TIMESTAMP DEFAULT NOW()
);

CREATE TABLE candidates (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           INT,
    name                VARCHAR(200),
    email               VARCHAR(200),
    phone               VARCHAR(50),
    source              VARCHAR(100),
    resume_file_url     VARCHAR(500),
    resume_raw_text     TEXT,
    resume_parsed_json  JSONB,
    status              VARCHAR(50) DEFAULT 'screening',
    job_id              BIGINT REFERENCES jobs(id),
    owner_id            INT,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE candidate_matches (
    id                      BIGSERIAL PRIMARY KEY,
    candidate_id            BIGINT REFERENCES candidates(id),
    job_id                  BIGINT REFERENCES jobs(id),
    score                   FLOAT,
    matched_evidence_json   JSONB,
    missing_requirements    JSONB,
    interview_focus_json    JSONB,
    recommendation          VARCHAR(20),
    created_at              TIMESTAMP DEFAULT NOW()
);

CREATE TABLE onboarding_cases (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       INT,
    employee_name   VARCHAR(200),
    candidate_id    BIGINT,
    job_id          BIGINT,
    start_date      DATE,
    probation_end   DATE,
    mentor_id       INT,
    hr_owner_id     INT,
    status          VARCHAR(20) DEFAULT 'in_progress',
    im_user_id      VARCHAR(200)
);
```

---

## 9. 统一数据模型

### 9.1 底座表

```sql
CREATE TABLE tenants (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(200),
    plan            VARCHAR(50) DEFAULT 'community',
    settings_json   JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE users (
    id                 BIGSERIAL PRIMARY KEY,
    tenant_id          INT REFERENCES tenants(id),
    name               VARCHAR(200),
    email              VARCHAR(200),
    role               VARCHAR(50), -- admin / operator / viewer
    status             VARCHAR(20) DEFAULT 'active',
    created_at         TIMESTAMP DEFAULT NOW()
);

CREATE TABLE channels (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           INT REFERENCES tenants(id),
    type                VARCHAR(30), -- csv / feishu / wecom / dingtalk / webhook
    name                VARCHAR(100),
    config_json         JSONB,
    status              VARCHAR(20) DEFAULT 'enabled',
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE conversations (
    id                          BIGSERIAL PRIMARY KEY,
    tenant_id                   INT REFERENCES tenants(id),
    channel_id                  INT REFERENCES channels(id),
    external_conversation_id    VARCHAR(200),
    type                        VARCHAR(20), -- group / private
    name                        VARCHAR(200),
    bound_agent                 VARCHAR(50),
    owner_id                    INT,
    last_message_at             TIMESTAMP,
    created_at                  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE messages (
    id                    BIGSERIAL PRIMARY KEY,
    tenant_id             INT REFERENCES tenants(id),
    channel_id            INT REFERENCES channels(id),
    conversation_id       INT REFERENCES conversations(id),
    external_message_id   VARCHAR(200),
    sender_external_id    VARCHAR(200),
    sender_name           VARCHAR(200),
    message_type          VARCHAR(30),
    text                  TEXT,
    normalized_json       JSONB,
    raw_json              JSONB,
    received_at           TIMESTAMP DEFAULT NOW()
);
```

### 9.2 AI 审计与审批

```sql
CREATE TABLE agent_runs (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           INT REFERENCES tenants(id),
    message_id          BIGINT REFERENCES messages(id),
    agent_type          VARCHAR(80),
    status              VARCHAR(30), -- running / success / failed
    prompt_version      VARCHAR(80),
    prompt_json         JSONB,
    model_provider      VARCHAR(80),
    model_name          VARCHAR(100),
    model_output_json   JSONB,
    action_json         JSONB,
    confidence          FLOAT,
    risk_level          VARCHAR(20),
    latency_ms          INT,
    tokens_used         INT,
    cost_usd            DECIMAL(12,6),
    error_message       TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE approvals (
    id             BIGSERIAL PRIMARY KEY,
    tenant_id      INT REFERENCES tenants(id),
    agent_run_id   BIGINT REFERENCES agent_runs(id),
    status         VARCHAR(30) DEFAULT 'pending_review',
    draft_content  TEXT,
    final_content  TEXT,
    operator_id    INT,
    operated_at    TIMESTAMP,
    sent_at        TIMESTAMP,
    reject_reason  TEXT,
    created_at     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE audit_logs (
    id             BIGSERIAL PRIMARY KEY,
    tenant_id      INT REFERENCES tenants(id),
    actor_id       INT,
    action         VARCHAR(100),
    target_type    VARCHAR(80),
    target_id      BIGINT,
    before_json    JSONB,
    after_json     JSONB,
    created_at     TIMESTAMP DEFAULT NOW()
);
```

### 9.3 知识库与报告

```sql
CREATE TABLE kb_documents (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     INT REFERENCES tenants(id),
    scope         VARCHAR(50), -- global / support / community / sales / hr
    title         VARCHAR(500),
    source_file   VARCHAR(500),
    content       TEXT,
    chunk_index   INT,
    embedding_id  VARCHAR(200),
    metadata_json JSONB,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE reports (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     INT REFERENCES tenants(id),
    report_type   VARCHAR(80),
    scope_type    VARCHAR(80),
    scope_id      BIGINT,
    report_date   DATE,
    content       TEXT,
    stats_json    JSONB,
    sent_at       TIMESTAMP,
    created_at    TIMESTAMP DEFAULT NOW()
);
```

---

## 10. 技术选型

### 10.1 分阶段技术策略

不要第一天就上全套复杂技术。技术栈应分为启动版、生产版和生态版。

| 层 | 启动版 | 生产版 | 生态版 |
|---|---|---|---|
| 后端 | FastAPI | FastAPI + 后台任务 | 模块化插件系统 |
| 数据库 | SQLite + SQLModel | PostgreSQL + Alembic | 多租户隔离 |
| 前端 | React + Vite + Ant Design | React + 权限路由 | 插件式页面 |
| LLM | OpenAI-compatible wrapper | LiteLLM | 多模型策略路由 |
| RAG | 简单关键词 + 文档片段 | Qdrant + LlamaIndex | 多知识库权限 |
| 定时任务 | APScheduler | Celery + Redis Beat | 分布式任务 |
| 消息队列 | 无 | Redis / RabbitMQ | Kafka 可选 |
| 部署 | 本地运行 | Docker Compose | Helm / K8s |

### 10.2 推荐基础技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 语言 | Python 3.11+ | AI 生态完善，小白友好 |
| Web 框架 | FastAPI | 适合 Webhook、API、异步处理 |
| ORM | SQLModel | 和 FastAPI / Pydantic 配合好 |
| 启动数据库 | SQLite | 零配置，适合本地开发、真实飞书验收和早期私有化试用 |
| 正式数据库 | PostgreSQL | 稳定、标准、支持 JSONB |
| 前端 | React + Vite | 简洁、快速、生态成熟 |
| UI | Ant Design | 企业后台组件成熟 |
| 图表 | ECharts | 中文场景友好 |
| LLM 兼容 | OpenAI-compatible API | 可接 OpenAI、DeepSeek、Qwen、Moonshot、Ollama |
| 飞书 | lark-oapi | 官方 SDK |
| 企业微信 | wechatpy / 原生 API | 社区可用，必要时原生调用 |
| 钉钉 | dingtalk-stream | 官方 Stream 模式 |
| 文件解析 | pdfplumber、python-docx | 简历和知识文档处理 |
| 容器 | Docker Compose | 开源项目部署门槛低 |

### 10.3 国产模型建议

| 模型 | 适合场景 |
|---|---|
| DeepSeek Chat | 通用对话、结构化提取、成本友好 |
| Qwen Turbo | 高频意图分类、低成本任务 |
| Qwen Plus | 简历分析、长文本总结、复杂推理 |
| Moonshot / Kimi | 超长上下文文档 |
| Ollama 本地模型 | 私有化、离线演示、敏感数据场景 |

### 10.4 仓库结构

```text
workagent-cn/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── CHANGELOG.md
├── docker-compose.yml
├── docker-compose.dev.yml
├── .env.example
│
├── docs/
│   ├── MASTER_PLAN.md
│   ├── product-plan.md
│   ├── architecture.md
│   ├── data-model.md
│   ├── agent-runtime.md
│   ├── approval-audit.md
│   ├── roadmap.md
│   └── deployment-guide.md
│
├── apps/
│   ├── api/
│   │   ├── main.py
│   │   ├── modules/
│   │   │   ├── channels/
│   │   │   ├── messages/
│   │   │   ├── routing/
│   │   │   ├── actions/
│   │   │   ├── approvals/
│   │   │   ├── knowledge/
│   │   │   ├── reports/
│   │   │   └── scenarios/
│   │   │       ├── support/
│   │   │       ├── community/
│   │   │       ├── sales/
│   │   │       └── hr/
│   │   └── shared/
│   │       ├── llm/
│   │       ├── prompts/
│   │       ├── tools/
│   │       └── security/
│   │
│   └── web/
│       ├── src/
│       │   ├── pages/
│       │   │   ├── dashboard/
│       │   │   ├── inbox/
│       │   │   ├── tickets/
│       │   │   ├── community/
│       │   │   ├── sales/
│       │   │   ├── hr/
│       │   │   └── settings/
│       │   └── components/
│       └── package.json
│
├── packages/
│   ├── im-gateway/
│   ├── agent-sdk/
│   └── prompt-registry/
│
└── examples/
    ├── demo-community-chat.csv
    ├── demo-sales-conversation.txt
    ├── demo-resume.txt
    └── demo-support-chat.csv
```

---

## 11. Prompt 工程

### 11.1 意图分类 Prompt

```text
你是企业 IM 消息分析助手。请分析以下消息的业务意图。

消息内容：
{message_text}

发送者：
{sender_name}

会话背景：
{conversation_context}

可选意图：
- support_ticket：客服、售后、投诉、退款、故障
- community_ops：社群运营、活动、群反馈、高意向用户
- sales_lead：询价、试用、报价、销售咨询、客户跟进
- recruiting_hr：简历、面试、候选人、入职、HR 问题
- knowledge_question：知识库问答、制度、流程、产品说明
- system_command：系统命令
- chat：闲聊或无需处理

请只返回 JSON：
{
  "intent": "意图名",
  "confidence": 0.0到1.0,
  "risk_level": "low|medium|high|critical",
  "requires_approval": true或false,
  "entities": {},
  "reason": "一句话说明判断理由"
}
```

### 11.2 工单抽取 Prompt

```text
你是客服工单分析助手。请从以下客户消息中提取工单信息。

客户消息：
{message_text}

历史上下文：
{conversation_history}

请只返回 JSON：
{
  "should_create_ticket": true或false,
  "category": "bug_report|complaint|refund_request|how_to_question|feature_request|account_issue|billing_issue|other",
  "priority": "low|normal|high|urgent",
  "title": "不超过30字的工单标题",
  "problem_summary": "问题摘要",
  "missing_info": ["还需要追问的信息"],
  "suggested_reply": "谨慎、友好的回复草稿",
  "knowledge_gap": true或false,
  "confidence": 0.0到1.0
}
```

### 11.3 销售线索抽取 Prompt

```text
你是销售数据分析师。请从销售对话中提取线索信息。

对话记录：
{conversation_text}

请只返回 JSON：
{
  "customer_name": "客户姓名或null",
  "company": "公司或null",
  "interest": "客户感兴趣的产品/方案",
  "pain_points": ["痛点"],
  "budget": "预算或null",
  "urgency_level": "low|medium|high|unknown",
  "decision_role": "decision_maker|influencer|user|unknown",
  "objections": ["异议"],
  "next_action": "具体下一步建议",
  "follow_up_date": "YYYY-MM-DD或null",
  "score_delta": 分数变化整数,
  "confidence": 0.0到1.0
}
```

### 11.4 简历匹配 Prompt

```text
你是资深 HR。请评估候选人与岗位 JD 的匹配度。

岗位 JD：
{jd_text}

候选人简历：
{resume_text}

要求：
1. 必须给出具体证据。
2. 不要只给主观评价。
3. 不确定的地方要标为风险或待验证。

请只返回 JSON：
{
  "score": 0到100,
  "recommendation": "interview|maybe|reject",
  "matched": [
    {"requirement": "岗位要求", "evidence": "简历证据"}
  ],
  "missing": ["缺失项"],
  "risks": ["风险点"],
  "interview_focus": ["面试重点"],
  "summary": "一句话总结"
}
```

### 11.5 日报生成 Prompt

```text
你是业务运营分析师。请根据今日数据生成一份简洁、可执行的日报。

场景：
{scenario}

统计数据：
{stats_json}

重点事项：
{important_items}

要求：
1. 分为：数据概览、风险事项、待跟进、明日建议。
2. 必须使用具体数字。
3. 建议必须可执行。
4. 不要写空话。

只输出日报正文。
```

---

## 12. 权限、安全与合规

### 12.1 权限模型

角色：

| 角色 | 权限 |
|---|---|
| Owner | 系统配置、渠道配置、用户管理、所有数据 |
| Admin | 业务配置、审批、报表、知识库 |
| Operator | 处理任务、审批草稿、编辑回复 |
| Viewer | 只读查看报表和记录 |
| Agent | 系统内部身份，用于记录自动操作 |

### 12.2 数据安全

必须实现：

- IM 平台凭证必须通过前端配置中心录入和管理。
- 模型供应商、Base URL、API Key、Model、Timeout 必须通过前端配置中心录入和管理。
- `.env` 不提交仓库。
- LLM API Key 不明文展示，只显示是否已配置。
- 用户隐私字段脱敏显示。
- 原始消息和 AI 输出都可追踪。
- 支持本地部署和私有化部署。
- 飞书、企微、钉钉的发送策略必须可配置，真实发送必须有审批和安全提示。
- 所有时间显示和记录默认使用北京时间。

后续实现：

- 密钥加密存储。
- 字段级权限。
- 多租户数据隔离。
- 审计日志不可篡改。
- 敏感信息检测。
- 数据保留策略。

### 12.3 AI 安全策略

默认策略：

- AI 不直接对外发送高风险消息。
- 低置信度必须转人工。
- 外部回复默认审批。
- 模型输出必须经过 JSON Schema 校验。
- 工具调用必须经过权限检查。
- Prompt 模板版本化。

---

## 13. 长期路线图

早期 Phase 0-5 方案已经不再作为执行路线。当前按大版本推进，目标是尽快做成可正式投入使用的私有化产品，而不是持续做演示版本。

### v0.15.x：飞书正式闭环加固

目标：让飞书从“能真实测试”变成“能持续真实运行”。

当前已完成到 `v0.15.5`：

- Docker Compose 增加 `feishu-worker`
- 飞书诊断页增加正式运行检查
- 配置中心显示 worker 本地/Docker 启动命令
- 审批详情增加发送预检和发送历史
- 支持飞书 encrypted callback
- 飞书 webhook/stream 解析失败可记录为 ChannelEvent
- 失败飞书接收事件增加重试入口
- 审批发送失败增加最大次数和退避策略
- 飞书 worker 持续心跳、最近事件、最近错误和恢复指引
- 飞书互动审批卡片支持发送、回调审计、通过/拒绝/查看详情
- 飞书图片、文件、富文本消息已进入可追踪 MessageEvent 闭环
- 飞书诊断页新增 acceptance traces 和 acceptance summary
- 新增 `scripts/run_feishu_acceptance.py` 与 `npm run check:feishu-acceptance`

v0.15.x 完成条件：

- API、Web、Feishu worker 可以用明确命令启动。
- 飞书真实消息进入系统稳定。
- 飞书消息重复投递不会重复生成业务对象。
- 审批通过后真实发送可追踪、可重试、防重复。
- 飞书诊断页能告诉用户当前是否可真实运行，以及不能运行的原因。
- 所有关键节点进入 AgentRun、ChannelEvent、Approval、业务对象时间线。

当前状态：以上条件已满足，`v0.15.x` 已完成，项目进入 `v0.16.x`。

### v0.16.x：团队工作台与权限

目标：从“系统能处理消息”升级到“团队成员能分工处理事情”。

要做：

- 本地用户体系
- 登录或本地身份切换
- 角色权限：管理员、审批人、处理人、只读成员
- 我的待办
- 我的审批
- 我的逾期
- 团队工作台
- 负责人从文本字段升级为用户引用
- 操作审计总账
- 配置变更审计
- 发送操作审计

当前状态：以上条件已满足，`v0.16.x` 已完成，项目进入 `v0.17.x`。

已完成：

- 新增 `LocalUser` 本地用户模型和默认 `local_admin`
- 新增 `GET /api/auth/me`、`GET/POST/PATCH /api/users`
- 前端新增团队成员页与侧边栏当前操作人切换
- 审批操作限制为管理员 / 审批人
- 任务负责人从纯文本升级为用户引用
- 新增 `GET /api/workbench/me`
- 工作台新增我的待办、我的审批、我的逾期、待认领任务
- 新增统一审计总账 `GET /api/audit-logs`
- 处理记录、任务更新、审批决策/发送、配置修改进入审计
- 配置中心后端增加管理员权限校验，普通成员不能改系统配置

完成条件：

- 一个真实团队能区分不同操作者。
- 每个业务对象都有负责人和处理状态。
- 审批人和处理人不是同一个模糊“本地账号”。
- 管理员能看到团队运行状态。
- 谁处理、谁审批、谁发送、谁改配置都可查。

### v0.17.x：企业微信真实接入

目标：把企微从 mock 骨架推进到真实可用。

要做：

- 企业微信配置中心 smoke test
- 回调验签
- AES 解密
- XML/JSON 事件解析
- access_token 获取和缓存
- 应用消息接收
- 客户群或外部联系人消息接入方案
- 企业微信文本发送
- 用户、群、客户映射
- 企业微信审批发送仍走 WorkBuddy 审批策略

当前状态：代码主线已完成，项目进入 `v0.18.x`。

已完成：

- 配置中心保留企微真实凭证入口
- 新增 `GET /api/channels/wecom/status`
- 新增 `GET /api/channels/wecom/diagnostics/full`
- 新增 `GET /api/channels/wecom/webhook` URL 校验
- 新增 `POST /api/channels/wecom/webhook`，支持 XML 回调、加密回调、JSON 调试 payload
- 新增企微回调验签
- 新增企微 AES 解密
- 新增企微 XML/JSON 标准化进入 `MessageEvent`
- 新增企微 access_token 获取与内存缓存
- 审批发送预检支持识别企微发送目标
- 审批通过后支持企微文本发送到用户或 ChatId 群聊
- 企微发送诊断、业务链路、acceptance traces、acceptance summary
- 新增 `scripts/check_wecom_runtime.py`
- 新增 `scripts/run_wecom_acceptance.py`
- 新增 `npm run check:wecom-runtime`
- 新增 `npm run check:wecom-acceptance`
- 前端新增企微诊断页

完成条件：

- 企微真实消息能进入 `MessageEvent`
- 企微消息能生成业务对象
- 审批通过后可真实发企微文本消息
- 企微诊断页能判断配置、回调、发送是否就绪

### v0.18.x：部署、数据和后台任务正式化

目标：让系统可以长期运行，而不是开发机手动跑。

当前状态：代码主线已完成，项目已进入 `v0.19.x`。当前机器没有 Docker 命令，因此完整 Compose 实跑仍需要在 Docker-capable host 上做人工验收。

已完成：

- `/health` 升级为结构化运行态接口，返回数据库、Redis、后台任务和版本信息
- 新增共享 runtime stack 状态服务，供健康检查和配置中心复用
- 配置中心开始展示数据库后端、连接状态、Redis 状态、后台任务状态和 Compose 启动建议
- 新增 `scripts/check_runtime_stack.py`
- 新增 `npm run check:runtime-stack`
- Docker Compose 开始切到 `postgres + redis + api + web + feishu-worker` 栈
- API requirements 补齐 `psycopg[binary]`，为 PostgreSQL 接入做准备
- 新增 Alembic 基线和 `npm run db:migrate`
- 新增后台任务 worker：`npm run dev:runtime-jobs`
- 后台任务 worker 已支持失败发送重试扫描、逾期任务扫描、陈旧工单扫描
- Docker Compose 新增 `runtime-jobs` service
- 新增数据库备份、备份校验和 SQLite 恢复预案
- 新增结构化日志、日志检查和日志 tail 命令
- 新增 v0.18 runtime runbook
- 后台任务 worker 已支持计划日报生成，并按北京时间日期去重
- 部署检查会验证数据库、备份、日志、后台任务和 Compose 服务声明

完成条件：

- 新机器可以按文档启动完整本地/私有化环境。
- 数据库迁移不靠手工改表。
- 后台任务不靠人工盯。
- 出错后能通过日志和诊断定位。
- 有基础自动测试守住核心流程。

边界：本机无 Docker，Compose full-stack boot 需要在有 Docker 的机器上验收；当前代码和 runbook 已准备好。

### v0.19.x：知识库与 RAG 正式化

目标：让知识库从“知识条目列表”变成正式可用的知识系统。

要做：

- 知识详情页
- 来源引用
- 知识版本
- 编辑、审核、发布
- 命中记录（`v0.19.2` 已开始落地：客服工单知识推荐会写入 KnowledgeHit，知识详情展示命中统计）
- 知识图谱（`v0.19.3` 必做：参考 公开项目文档 图谱视图，把知识条目、缺口、来源消息、工单、AgentRun、命中记录连成可点击关系图）
- 知识过期提醒
- 文档/FAQ 导入
- 向量索引
- RAG 检索
- Agent 回复引用知识来源
- 知识缺口到知识条目的完整闭环

完成条件：

- 客服、社群、销售、招聘 Agent 能引用知识来源。
- 知识变更可审计、可回滚。
- 知识命中和缺口能形成持续优化闭环。
- 知识之间、知识与来源对象之间能通过图谱视图理解关系。

### v0.20.x：发布候选与开源准备

目标：从内部可用走向可交付、可安装、可维护。

要做：

- 安装文档
- 部署文档
- 飞书配置文档
- 企微配置文档
- 环境检查脚本
- 示例数据和空环境初始化
- License、贡献指南、隐私和安全说明
- Demo 与真实模式明确隔离
- release checklist

完成条件：

- 一个新用户能按文档在本地启动。
- 一个真实团队能按文档接入飞书。
- 敏感配置不会被误提交。
- 开源仓库不会暴露本地密钥和演示脏数据。

### v1.0.0：私有化正式可用版

目标：达到“可以让真实团队长期使用”的质量线。

v1.0.0 不追求功能无限多，而追求主链路稳：

- 飞书正式可用
- 企微正式可用
- 业务对象闭环正式可用
- 审批、审计、权限正式可用
- 部署、备份、恢复正式可用
- 知识库和 RAG 基础正式可用
- 有自动测试守住核心链路
- 有清晰文档和验收步骤

---

## 14. 开源与发布策略

当前原则：不要急着开源发布。先把本地产品和私有化产品做完整，再进入开源准备。

### 14.1 现在不做什么

当前阶段不做：

- 不急着做正式开源发布；但开发提交要同步 push 到 GitHub，保持远端备份和交接可用。
- 不为了 README 截图牺牲产品闭环。
- 不把 Demo 数据、真实密钥、真实飞书配置混进开源仓库。
- 不为了开源传播优先做好看的演示页。
- 不提前承诺企微、钉钉、RAG、插件生态已经生产可用。

### 14.2 什么时候准备开源

进入 `v0.20.x 发布候选与开源准备` 后，再集中处理：

- 安装文档
- 部署文档
- 飞书配置文档
- 企微配置文档
- 环境检查脚本
- 示例数据和空环境初始化
- License
- 贡献指南
- 隐私和安全说明
- Demo 与真实模式隔离
- release checklist

### 14.3 README 到时必须讲清楚

README 第一屏必须包含：

1. 一句话定位。
2. 当前支持状态，不夸大未完成能力。
3. 支持的平台：飞书真实优先，CSV/JSON/Webhook 已支持，企微按当时真实状态标注，钉钉按当时真实状态标注。
4. 支持的模型：OpenAI-compatible 配置中心，按真实 smoke test 状态说明。
5. 核心业务闭环截图：消息事件、业务对象、审批、审计、配置中心。
6. 本地启动方式和 Docker Compose 启动方式。
7. Roadmap 和已知限制。

### 14.4 Demo 数据

可以内置 Demo 数据，但必须和真实数据隔离。Demo 的目的只是帮助理解产品，不得替代真实验收。

Demo 文件：

```text
examples/
├── demo-support-chat.csv
├── demo-community-chat.csv
├── demo-sales-conversation.txt
├── demo-jd.txt
├── demo-resume.txt
└── demo-knowledge.md
```

### 14.5 文档拆分建议

最终仓库中建议把本文档拆成：

```text
docs/
├── MASTER_PLAN.md
├── 00-vision.md
├── 01-market-gap.md
├── 02-product-architecture.md
├── 03-system-architecture.md
├── 04-core-domain-model.md
├── 05-agent-runtime.md
├── 06-human-approval-audit.md
├── 07-scenario-support-ticket.md
├── 08-scenario-community-agent.md
├── 09-scenario-sales-agent.md
├── 10-scenario-hr-agent.md
├── 11-roadmap.md
└── 12-open-source-strategy.md
```

---

## 15. 当前开发优先级和执行纪律

早期“第一版开发优先级”已经完成大半，不再作为当前路线。当前路线以大版本为准。

### 15.1 当前只做 v0.18.x 主线

当前只做：

- PostgreSQL 支持
- Alembic 迁移
- Docker Compose 一键启动完善
- 后台任务队列
- 健康检查与结构化日志
- 失败重试、日报生成、SLA 扫描等后台任务
- 自动化测试与 CI 基线

当前不做：

- 不回头打断已完成的企微相关能力，除非是阻塞性 bug
- 不做正式 RAG，留给 v0.19.x
- 不做开源发布，留给 v0.20.x

### 15.2 小版本补丁池规则

大版本开发过程中，如果发现以下问题，先写入 `docs/ROADMAP.md`：

- UI 体验小问题
- 表格列宽、搜索、横向滚动、文案、空状态问题
- 非阻塞错误提示优化
- 历史数据清理
- 低风险接口补充
- 真实运行中发现但不阻塞当前验收的问题

只有阻塞当前大版本验收的问题，才立即处理。

### 15.3 每次版本结束必须做

每个版本结束必须：

- 说明本版做了什么。
- 分清本版新增、优化、修复分别是什么。
- 说明最终结果和当前可用状态。
- 给出人工验收步骤。
- 给出下个版本规划。
- 更新 release 文档。
- 更新 公开项目文档 记忆库。
- 跑必要验证命令。
- 本地 git commit。
- push 到 GitHub `origin/main`，除非用户当次明确要求不要 push。

---

## 16. 简历与项目包装

项目描述：

```text
WorkBuddy OSS：面向中国团队的开源 IM Agent 工作流中台。
项目支持将飞书、企业微信、钉钉和聊天记录中的非结构化消息转化为工单、线索、任务、候选人和知识库条目，并通过 AI 草稿、人工审批、审计留痕和业务报表形成企业级闭环。
```

简历要点：

- 设计并实现统一 IM Agent Gateway，支持 CSV、飞书、企业微信、钉钉等消息来源。
- 建立统一 MessageEvent 和 Business Object 模型，将非结构化 IM 消息转化为工单、线索、任务、候选人和知识条目。
- 实现 Agent Router，结合规则识别和 LLM 意图分类完成业务 Agent 路由。
- 设计 AI 草稿到人工审批再到发送留痕的企业级安全工作流。
- 实现客服工单知识 Agent、私域社群运营 Agent、销售线索跟进 Agent、招聘与入职 Agent。
- 基于 OpenAI-compatible API 支持 DeepSeek、Qwen、Moonshot、OpenAI、Ollama 等模型。
- 使用 FastAPI、SQLModel、SQLite/PostgreSQL、React、Docker Compose 构建可私有化部署的开源系统。

---

## 17. 最终建议

最终建议采用以下路线：

1. 以 `WorkBuddy OSS` 作为 GitHub 仓库名，保证技术定位清晰。
2. 以 `WorkBuddy OSS` 作为产品品牌，增强亲和力和传播性。
3. 用本文档作为唯一顶层准线，不参考旧方案。
4. 当前继续推进 `v0.18.x 部署、数据和后台任务正式化`。
5. `v0.18.x` 做完后进入 `v0.19.x 知识库与 RAG 正式化`。
6. 再进入 `v0.20.x 发布候选与开源准备`。
7. 到 `v1.0.0` 后停止堆大功能，进入维护模式。

最终停止开发标准：

- 飞书和企微都能在真实团队中连续运行至少 2 周。
- 核心消息链路没有 P0/P1 阻塞问题。
- 审批外发没有重复发送或误发送。
- 业务对象处理闭环能覆盖客服、销售、社群、招聘、知识库。
- 新团队能按文档完成部署和接入。
- 管理员能处理常见故障，不需要开发者手工查数据库。
- 已知小问题都进入补丁池并完成优先级排序。
- 用户确认当前版本已经能满足正式使用目标。

一句话收束：

> WorkBuddy OSS 的长期价值，不是让 AI 多说几句话，而是让中国企业每天散落在 IM 里的消息，变成可执行、可跟踪、可审批、可沉淀的业务资产。
