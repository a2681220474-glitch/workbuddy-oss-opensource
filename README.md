# WorkBuddy OSS

WorkBuddy OSS 是面向中国团队的开源 IM Agent 工作流中台。它把飞书、企业微信、钉钉、Webhook、CSV/JSON 聊天记录里的非结构化消息，转成可处理、可审批、可审计、可复盘的业务对象。

当前主线版本：`v1.1.16 部署恢复收口`

公开版默认不包含任何私有部署、真实租户、真实 IM 应用或运行数据。部署到公网前，请先复制 `.env.example` 并填写自己的域名和应用凭据。

## 当前定位

WorkBuddy OSS 不是通用聊天机器人，也不是 Dify/Coze/RAGFlow 这类 AI 应用搭建平台。它的核心目标是：

```text
IM / CSV / Webhook 消息
  -> MessageEvent
  -> Agent Router
  -> Ticket / Lead / Task / Candidate / Knowledge / Report
  -> Approval / ProcessingRecord / AuditLog
  -> 外发、日报、知识沉淀和团队协作
```

所有面向客户、候选人、社群成员或外部用户的 AI 回复，必须先进入审批队列。审批、发送、配置变更和关键处理动作都会写入审计。

## 当前能力

- 本地正式登录、密码哈希、会话门禁和 RBAC 写操作边界。
- 本地敏感配置加密存储，支持 DeepSeek、飞书、企微等密钥迁移与主密钥轮换。
- 飞书真实接收、消息标准化、业务路由、审批、发送预检、失败重试和诊断页。
- 企业微信真实加密回调、消息标准化、审批后发送和诊断页。
- 钉钉 Adapter mock/test 边界。
- 客服工单、销售线索、私域社群、招聘入职、知识库和报告中心。
- 知识条目来源引用、版本、回滚、命中记录、质量反馈和本地混合检索。
- 本地服务托管：API、Web、runtime-jobs 默认可由 `npm run services:start` 管理；飞书 worker 需显式启动。
- Docker Compose、PostgreSQL、Redis、Alembic、备份恢复、结构化日志和私有部署文件已具备。

## 快速启动

推荐本地开发使用统一服务管理器：

```bash
npm run services:start
open http://localhost:5173
```

查看状态：

```bash
npm run services:status
```

重启：

```bash
npm run services:restart
```

停止：

```bash
npm run services:stop
```

默认托管服务包括：

- API：`http://127.0.0.1:8000`
- Web：`http://127.0.0.1:5173`
- runtime-jobs

飞书长连接 worker 默认不随 `services:start` 启动，避免未确认时影响真实消息接收。需要真实飞书接收时单独执行：

```bash
npm run dev:feishu-stream
```

## 首次登录

首次打开本地 Web 时，如果还没有本地管理员，会进入初始化页面：

1. 设置用户名、显示名和至少 8 位密码。
2. 初始化后进入工作台。
3. 后续访问使用正式登录。

## 配置与密钥

配置中心入口：

```text
http://localhost:5173/#config
```

从 `v1.1.0` 开始，模型、飞书、企微等敏感配置会保存到本地加密仓库：

- 密文仓库：`apps/api/data/runtime_secrets.json`
- 主密钥：`apps/api/data/runtime_secret.key`

这两个文件均被 Git 忽略，且仅本机用户可读。不要把真实密钥写进文档、截图或提交。

配置中心保存的普通运行参数会写入：

- `apps/api/data/runtime.env`

该文件同样被 Git 忽略；Docker 部署时与加密密钥共用 `api-data` 持久卷，因此重建 API/Worker 容器后仍然保留。手工启动时，`.env.local` 仍可作为部署默认值，但配置中心保存值优先生效。

例如：

```env
ENABLE_REAL_IM_ADAPTERS=true
ENABLE_EXTERNAL_SEND=false
WORKBUDDY_PUBLIC_BASE_URL=https://your-public-domain.example.com
```

## 飞书接入

本地消息接收推荐使用飞书长连接 worker，不需要公网回调地址：

```bash
npm run dev:feishu-stream
npm run check:feishu-stream
```

诊断页：

```text
http://localhost:5173/#feishu
```

飞书审批卡片按钮是另一条链路：点击卡片里的“通过 / 拒绝 / 查看详情”时，飞书会请求一个公网 HTTP 回调地址。长连接 worker 不能接收这个按钮点击。

如果飞书客户端提示：

```text
目标回调服务当前未在线
```

含义是飞书后台当前配置的卡片交互回调地址无法访问当前 WorkBuddy API。处理方式：

1. 启动可公网访问的 HTTPS 地址，可以是正式域名、部署服务器，或本地 HTTPS tunnel。
2. 设置：

```env
WORKBUDDY_PUBLIC_BASE_URL=https://你的公网域名
```

3. 重启 API。
4. 打开 `#feishu`，复制“卡片按钮回调”区块显示的完整地址。
5. 在飞书开发者后台把卡片交互/机器人回调地址配置为：

```text
https://你的公网域名/api/channels/feishu/webhook
```

当前阿里云 ECS 可直接使用：

```text
https://workbuddy.example.com/api/channels/feishu/webhook
```

6. 再发送 WorkBuddy 审批卡片并点击“通过 / 拒绝”验收。

更多步骤见：

- `docs/FEISHU_SETUP.md`
- `docs/FEISHU_PHASE1.md`

## 企业微信接入

企业微信使用 HTTP 回调模式，需要公网 HTTPS 地址：

```text
https://你的公网域名/api/channels/wecom/webhook
```

配置和验收见：

- `docs/WECOM_SETUP.md`

## 安全默认值

- 默认模型模式为 mock/local。
- 默认 `ENABLE_EXTERNAL_SEND=false`，不会真实外发。
- 真实诊断发送需要全局开关、手工确认和精确授权短语。
- 外发前必须经过审批。
- 所有 Agent 运行、审批、发送和配置变更都写入审计。
- 远程 ECS 已按用户授权受控升级到 `v1.1.14`；后续仍不随本地小版本自动升级。

## 自动验收

常用聚合检查：

```bash
npm run check:formal-release
```

常用专项检查：

```bash
npm run check:secret-storage
npm run check:product-workflow
npm run check:rag-workflow
npm run check:connector-acceptance
npm run check:frontend-maintenance
npm run check:ui-smoke
npm run check:local-services
npm run check:web-bundle
```

当前 `v1.1.16` 的正式发布检查新增 PostgreSQL 隔离恢复安全检查；连接器验收继续覆盖飞书一次性卡片、详情链接和消息 ID 幂等。

## 当前仍需人工验收

- 新一轮飞书/企微真实接收和真实外发复验。
- Docker/PostgreSQL/Redis 全栈实跑验收。
- 新一轮飞书卡片按钮真实点击验收。
- 真实团队连续运行至少 2 周。

以上事项都需要用户明确授权后执行。

## 文档入口

- `MASTER_PLAN_FINAL.md`：唯一总规划。
- `docs/KNOWN_ISSUES.md`：当前已知问题和限制。
- `docs/release/v1.1.16.md`：当前版本说明。
- `docs/PRODUCT_TRAINER_GUIDE_CN.md`：产品全景讲解、用户培训与部署介绍。
- `docs/AI_VIDEO_PROMPT_AND_SCRIPT_CN.md`：可交给 Codex 的产品视频提示词、分镜与旁白脚本。
- `docs/FEISHU_SETUP.md`：飞书配置与验收。
- `docs/WECOM_SETUP.md`：企业微信配置与验收。
- `docs/PRIVATE_DEPLOYMENT.md`：私有化部署说明。
- `docs/RELEASE_CANDIDATE_CHECKLIST.md`：发布候选验收清单。

## 仓库结构

```text
apps/
  api/              FastAPI backend
  web/              React + Vite admin console
docs/               产品、部署、验收和 release 文档
examples/           演示导入数据和知识材料
scripts/            本地服务、验收、备份、部署辅助脚本
deploy/             私有化部署文件
```

## License

See `LICENSE`.
