import { Alert, Descriptions, Drawer, List, Space, Tag, Typography } from "antd";
import type { ReactNode } from "react";
import type { AgentRun } from "../types";
import { formatTime } from "../utils/format";
import { hashTarget } from "../utils/navigation";
import { StatusTag } from "./StatusTag";

interface AgentRunDetailDrawerProps {
  run?: AgentRun;
  open: boolean;
  onClose: () => void;
}

export function AgentRunDetailDrawer({ run, open, onClose }: AgentRunDetailDrawerProps) {
  const prompt = asRecord(run?.prompt_json);
  const output = asRecord(run?.model_output_json);
  const route = asRecord(prompt.route ?? output.route);
  const classifier = asRecord(output.classifier ?? prompt.classifier);
  const llmRequest = asRecord(prompt.llm_request ?? classifier.request);
  const actions = Array.isArray(asRecord(run?.action_json).actions) ? asRecord(run?.action_json).actions as unknown[] : [];
  const error = run?.error_message || asString(classifier.error) || asString(asRecord(classifier.raw).error);

  return (
    <Drawer title={`运行详情 #${run?.id ?? ""}`} width={760} open={open} onClose={onClose}>
      <Space wrap style={{ marginBottom: 12 }}>
        <Tag>{agentLabel(run?.agent_type ?? route.target_agent as string | undefined)}</Tag>
        <StatusTag value={run?.status} />
        <StatusTag value={run?.risk_level ?? route.risk_level as string | undefined} />
        {run?.message_id ? <a href={hashTarget("messages", run.message_id)}>消息 #{run.message_id}</a> : <Typography.Text type="secondary">无消息绑定</Typography.Text>}
      </Space>

      {error ? <Alert type="warning" showIcon message="模型或运行提示" description={error} style={{ marginBottom: 14 }} /> : null}

      <Descriptions size="small" column={2}>
        <Descriptions.Item label="目标 Agent">{agentLabel(asString(route.target_agent) || run?.agent_type)}</Descriptions.Item>
        <Descriptions.Item label="意图">{asString(route.intent) || "-"}</Descriptions.Item>
        <Descriptions.Item label="置信度">{formatConfidence(route.confidence ?? run?.confidence)}</Descriptions.Item>
        <Descriptions.Item label="审批">{requiresApproval(actions) ? "需要" : "不需要"}</Descriptions.Item>
        <Descriptions.Item label="模型 Provider">{run?.model_provider ?? asString(classifier.provider) ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="模型">{run?.model_name ?? asString(classifier.model) ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="Token">{tokenUsage(run, classifier)}</Descriptions.Item>
        <Descriptions.Item label="耗时">{run?.latency_ms ? `${run.latency_ms}ms` : "-"}</Descriptions.Item>
        <Descriptions.Item label="创建时间" span={2}>{formatTime(run?.created_at)}</Descriptions.Item>
      </Descriptions>

      <Section title="路由原因">
        <Typography.Paragraph>{asString(route.reason) || "未记录路由原因"}</Typography.Paragraph>
        <pre className="json-block">{JSON.stringify(route, null, 2)}</pre>
      </Section>

      <Section title="LLM 请求">
        <pre className="json-block">{JSON.stringify(llmRequest, null, 2)}</pre>
      </Section>

      <Section title="模型输出">
        <pre className="json-block">{JSON.stringify(output, null, 2)}</pre>
      </Section>

      <Section title="生成动作">
        {actions.length ? (
          <List
            size="small"
            dataSource={actions}
            renderItem={(action, index) => {
              const item = asRecord(action);
              const object = asRecord(item.business_object);
              return (
                <List.Item>
                  <List.Item.Meta
                    title={`${index + 1}. ${asString(item.action_type) || "action"} / ${asString(object.type) || "object"}`}
                    description={(
                      <>
                        <Typography.Paragraph>{asString(item.reason) || "-"}</Typography.Paragraph>
                        <pre className="json-block">{JSON.stringify(item, null, 2)}</pre>
                      </>
                    )}
                  />
                </List.Item>
              );
            }}
          />
        ) : (
          <Typography.Text type="secondary">没有结构化动作。</Typography.Text>
        )}
      </Section>
    </Drawer>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <Typography.Title level={5}>{title}</Typography.Title>
      {children}
    </>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

function formatConfidence(value: unknown) {
  if (typeof value === "number") return value.toFixed(2);
  if (typeof value === "string") return value;
  return "-";
}

function requiresApproval(actions: unknown[]) {
  return actions.some((action) => JSON.stringify(action).includes("send_draft_to_approval"));
}

function tokenUsage(run: AgentRun | undefined, classifier: Record<string, unknown>) {
  const usage = asRecord(classifier.usage);
  const token = run?.tokens_used ?? (usage.total_tokens as string | number | undefined);
  return token ?? "-";
}

function agentLabel(value?: string) {
  const labels: Record<string, string> = {
    support_ticket_agent: "客服工单知识",
    sales_lead_agent: "销售线索跟进",
    community_ops_agent: "私域社群运营",
    recruiting_hr_agent: "招聘与入职",
    report_agent: "报告 Agent",
    chat_agent: "人工收件箱",
    manual_inbox_agent: "人工收件箱",
    import_pipeline: "导入管道",
    feishu_stream_worker: "飞书长连接",
    feishu_send_adapter: "飞书发送适配器",
  };
  return labels[value ?? ""] ?? value ?? "-";
}
