# WorkBuddy OSS v0.12.0 视频制作文案

用途：把 `docs/assets/screenshots/` 里的截图直接交给视频生成工具，制作一条 2-3 分钟的开源项目介绍与演示视频。

建议成片比例：16:9 横屏。  
建议风格：产品演示、清晰、克制、偏 B2B SaaS，不要做夸张营销片。  
建议语速：中文普通话，稳定、专业、略带开源项目介绍感。

## 一句话定位

WorkBuddy OSS 是面向中国团队的开源 IM Agent 工作流中台，把飞书、企业微信、钉钉、Webhook、CSV/JSON 聊天记录里的非结构化消息，转成可跟踪、可审批、可复盘的业务对象。

## 视频结构

### 片头：问题与定位

截图：

- `docs/assets/screenshots/00_dashboard.png`

旁白：

> 在真实团队里，客户咨询、销售线索、社群问题、候选人沟通，往往都散落在 IM 消息里。WorkBuddy OSS 要解决的不是再做一个聊天机器人，而是把这些消息变成可管理的业务流程。

屏幕字幕：

```text
WorkBuddy OSS
开源 IM Agent 工作流中台
MessageEvent -> Agent Router -> Business Objects -> Approval -> Audit
```

镜头建议：

- 从工作台全景开始。
- 轻微推进到四大 Agent 概览和风险聚合区域。

### 第一段：一键准备 Beta 验收

截图：

- `docs/assets/screenshots/01_demo_mode.png`

旁白：

> 开源用户第一次启动后，可以直接进入演示模式，点击一键准备 Beta 验收。系统会导入客服、销售、社群、招聘样例消息，自动生成业务对象、知识条目、报告、审批和运行日志。

屏幕字幕：

```text
一键准备 Beta 验收
8/8 检查：消息导入、四大 Agent、知识、报告、审批、审计
```

镜头建议：

- 标注「一键准备 Beta 验收」按钮。
- 标注当前数据和验收入口。

### 第二段：消息进入统一事件层

截图：

- `docs/assets/screenshots/02_import.png`
- `docs/assets/screenshots/03_messages.png`

旁白：

> WorkBuddy 先把 CSV、JSON、Webhook 或 IM Adapter 输入标准化为 MessageEvent。每条消息都会留下来源、发送人、会话、路由结果、关联对象和风险信息，后续所有 Agent 都从这层开始工作。

屏幕字幕：

```text
MessageEvent
统一消息输入、保留来源、可追踪路由
```

镜头建议：

- 先展示导入页。
- 切到消息事件表，轻微横向移动展示路由和关联对象。

### 第三段：业务对象中心

截图：

- `docs/assets/screenshots/04_business_objects.png`

旁白：

> 消息不会只停留在聊天记录里。它们会被转成 Ticket、Lead、Task、Candidate、Knowledge 和 Report。业务对象中心让用户能统一查看每类对象的数量、来源和跳转路径。

屏幕字幕：

```text
Business Object Center
Ticket / Lead / Task / Candidate / Knowledge / Report
```

镜头建议：

- 标注对象数量卡片。
- 标注对象列表里的跳转入口。

### 第四段：客服工单知识 Agent

截图：

- `docs/assets/screenshots/06_tickets.png`
- `docs/assets/screenshots/07_ticket_knowledge_modal.png`

旁白：

> 客服工单 Agent 支持状态机、优先级、SLA 配置和知识命中检查。遇到知识未覆盖的问题，可以直接从工单沉淀为知识缺口或发布为知识条目。

屏幕字幕：

```text
客服工单知识 Agent
状态机 / SLA / 知识命中 / 工单沉淀知识
```

镜头建议：

- 先展示工单列表。
- 切到知识命中弹窗，突出「沉淀为缺口」和「发布为知识」。

### 第五段：销售线索跟进 Agent

截图：

- `docs/assets/screenshots/10_leads.png`
- `docs/assets/screenshots/11_lead_assistant_modal.png`

旁白：

> 销售线索 Agent 会识别试用、报价、采购、私有部署等信号，生成线索阶段、评分维度、下一步动作和外发话术草稿。面向客户的回复不会直接发出，而是进入审批队列。

屏幕字幕：

```text
销售线索跟进 Agent
评分拆解 / 下一步建议 / 回复草稿审批
```

镜头建议：

- 展示漏斗指标和线索表。
- 切到销售助手弹窗，突出评分卡和草稿。

### 第六段：私域社群运营 Agent

截图：

- `docs/assets/screenshots/08_community.png`
- `docs/assets/screenshots/09_community_action.png`

旁白：

> 社群运营 Agent 聚合高意向用户、未回复问题、风险消息和社群任务，帮助运营人员从群聊里发现需要跟进的人和问题，并生成社群日报。

屏幕字幕：

```text
私域社群运营 Agent
高意向 / 未回复 / 风险 / 社群任务 / 群日报
```

镜头建议：

- 用一个平移镜头扫过统计卡片和列表。

### 第七段：招聘与入职 Agent

截图：

- `docs/assets/screenshots/13_candidates.png`
- `docs/assets/screenshots/14_candidate_assistant_modal.png`

旁白：

> 招聘与入职 Agent 会把候选人沟通转成 Candidate，提供 JD 和简历文本匹配、面试问题、风险点和入职 Checklist。招聘进度也能生成结构化报告。

屏幕字幕：

```text
招聘与入职 Agent
Candidate / 匹配分析 / 面试问题 / 入职 Checklist
```

镜头建议：

- 展示候选人状态机。
- 切到候选人助手，突出匹配分析和 Checklist。

### 第八段：知识与报告

截图：

- `docs/assets/screenshots/15_knowledge.png`
- `docs/assets/screenshots/16_reports.png`

旁白：

> 工单和社群问题可以沉淀为 KnowledgeGap 和 KnowledgeItem。系统还可以生成客服日报、销售日报、社群日报、招聘进度报告和知识缺口报告，帮助团队复盘每天发生了什么。

屏幕字幕：

```text
Knowledge + Report
从问题沉淀知识，从流程生成报告
```

镜头建议：

- 先看知识沉淀。
- 再切报告中心，标注多种报告类型。

### 第九段：审批与审计

截图：

- `docs/assets/screenshots/05_approvals.png`
- `docs/assets/screenshots/05b_approval_edit_modal.png`
- `docs/assets/screenshots/22_agent_runs.png`
- `docs/assets/screenshots/23_agent_run_detail.png`

旁白：

> WorkBuddy 的默认安全边界是：所有对外回复先进入审批队列，所有 Agent 行为写入 AgentRun。用户可以查看 prompt、输出、结构化动作和关联业务对象，避免黑箱式自动化。

屏幕字幕：

```text
Human Approval + AgentRun Audit
先审批，再发送；每次 Agent 行为可追踪
```

镜头建议：

- 展示审批列表。
- 切审批编辑弹窗。
- 再切运行日志和运行详情抽屉。

### 第十段：渠道与 Adapter

截图：

- `docs/assets/screenshots/17_config.png`
- `docs/assets/screenshots/18_conversations.png`
- `docs/assets/screenshots/19_channel_events.png`
- `docs/assets/screenshots/20_adapter_test.png`
- `docs/assets/screenshots/20b_adapter_preview_result.png`
- `docs/assets/screenshots/21_feishu_diagnostics.png`

旁白：

> 当前版本保留飞书现有能力，同时为企业微信和钉钉提供 Adapter 边界和测试台。真实外发默认关闭，演示时会以模拟发送和审计日志为主，避免误触达外部用户。

屏幕字幕：

```text
Channel Adapter
Feishu ready / WeCom & DingTalk mock boundary / Safe send by default
```

镜头建议：

- 展示配置中心风险检查。
- 展示渠道会话与渠道事件。
- 展示 Adapter 预览结果。
- 最后展示飞书诊断。

### 结尾：开源发布候选

截图：

- `docs/assets/screenshots/00_dashboard.png`
- `docs/assets/screenshots/01_demo_mode.png`

旁白：

> v0.12.0 是 WorkBuddy OSS 的开源发布候选版本。它已经跑通从空库启动、一键准备 Demo 数据，到四大 Agent、知识、报告、审批和审计的完整本地闭环。下一步，开发者可以基于这个骨架接入真实业务系统和更多 IM 渠道。

屏幕字幕：

```text
WorkBuddy OSS v0.12.0 Release Candidate
Open-source IM Agent workflow console for Chinese teams
```

镜头建议：

- 回到工作台全景。
- 最后一帧停留在演示模式 8/8 验收结果。

## 素材顺序清单

```text
00_dashboard.png
01_demo_mode.png
02_import.png
03_messages.png
04_business_objects.png
06_tickets.png
07_ticket_knowledge_modal.png
10_leads.png
11_lead_assistant_modal.png
08_community.png
09_community_action.png
13_candidates.png
14_candidate_assistant_modal.png
15_knowledge.png
16_reports.png
05_approvals.png
05b_approval_edit_modal.png
22_agent_runs.png
23_agent_run_detail.png
17_config.png
18_conversations.png
19_channel_events.png
20_adapter_test.png
20b_adapter_preview_result.png
21_feishu_diagnostics.png
```

## 生成视频时的提示词

```text
请根据这些 WorkBuddy OSS 产品截图生成一条 2-3 分钟中文产品介绍与演示视频。视频应为 16:9 横屏，风格专业、清晰、开源项目发布候选介绍。请按照文案顺序组织镜头，使用截图作为全屏画面，适当添加轻微推近和平移，突出业务对象、四大 Agent、审批、审计和渠道 Adapter。不要夸张营销，不要虚构截图中没有出现的功能。旁白使用中文普通话，字幕简洁同步。
```
