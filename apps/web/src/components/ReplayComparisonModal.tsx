import { Descriptions, Modal, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { MessageRerunResult, RelatedObject, ReplaySnapshot } from "../types";
import { formatTime } from "../utils/format";
import { StatusTag } from "./StatusTag";

interface ReplayComparisonModalProps {
  result?: MessageRerunResult;
  open: boolean;
  onClose: () => void;
}

interface CompareRow {
  key: string;
  label: string;
  before?: string;
  after?: string;
  changed?: boolean;
}

export function ReplayComparisonModal({ result, open, onClose }: ReplayComparisonModalProps) {
  const before = result?.before ?? {};
  const after = result?.after ?? {};
  const rows = compareRows(before, after, result?.changed ?? {});
  const cleaned = result?.cleaned ?? {};

  return (
    <Modal title="重跑前后对比" open={open} onCancel={onClose} footer={null} width={820}>
      <Descriptions size="small" column={3} style={{ marginBottom: 14 }}>
        <Descriptions.Item label="消息">{result?.message_id ? `#${result.message_id}` : "-"}</Descriptions.Item>
        <Descriptions.Item label="来源运行">{result?.replayed_from_run_id ? `#${result.replayed_from_run_id}` : "-"}</Descriptions.Item>
        <Descriptions.Item label="新运行">{result?.agent_run_id ? `#${result.agent_run_id}` : "-"}</Descriptions.Item>
        <Descriptions.Item label="审批草稿">{result?.approval_count ?? 0}</Descriptions.Item>
        <Descriptions.Item label="重跑时间">{formatTime(new Date().toISOString())}</Descriptions.Item>
        <Descriptions.Item label="清理对象">{cleanedSummary(cleaned)}</Descriptions.Item>
      </Descriptions>

      <Table
        size="small"
        pagination={false}
        rowKey="key"
        columns={columns}
        dataSource={rows}
        style={{ marginBottom: 16 }}
      />

      <Typography.Title level={5}>业务对象</Typography.Title>
      <Descriptions size="small" column={1}>
        <Descriptions.Item label="重跑前">{objectLabels(before.related_objects)}</Descriptions.Item>
        <Descriptions.Item label="重跑后">{objectLabels(after.related_objects)}</Descriptions.Item>
      </Descriptions>

      {before.reason || after.reason ? (
        <>
          <Typography.Title level={5}>路由原因</Typography.Title>
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="重跑前">{before.reason || "-"}</Descriptions.Item>
            <Descriptions.Item label="重跑后">{after.reason || "-"}</Descriptions.Item>
          </Descriptions>
        </>
      ) : null}
    </Modal>
  );
}

const columns: ColumnsType<CompareRow> = [
  { title: "字段", dataIndex: "label", width: 120 },
  { title: "重跑前", dataIndex: "before", render: (value, row) => renderValue(row.key, value) },
  { title: "重跑后", dataIndex: "after", render: (value, row) => renderValue(row.key, value) },
  {
    title: "变化",
    dataIndex: "changed",
    width: 90,
    render: (value) => <Tag color={value ? "blue" : "default"}>{value ? "已变化" : "未变化"}</Tag>
  }
];

function compareRows(before: ReplaySnapshot, after: ReplaySnapshot, changed: Record<string, boolean>): CompareRow[] {
  return [
    { key: "target_agent", label: "目标 Agent", before: agentLabel(before.target_agent), after: agentLabel(after.target_agent), changed: changed.target_agent },
    { key: "intent", label: "意图", before: before.intent || "-", after: after.intent || "-", changed: changed.intent },
    { key: "risk_level", label: "风险", before: before.risk_level || "-", after: after.risk_level || "-", changed: changed.risk_level },
    { key: "confidence", label: "置信度", before: confidence(before.confidence), after: confidence(after.confidence), changed: changed.confidence }
  ];
}

function renderValue(key: string, value?: string) {
  if (key === "risk_level") return <StatusTag value={value} />;
  return value || "-";
}

function objectLabels(objects?: RelatedObject[]) {
  if (!objects?.length) return <Typography.Text type="secondary">无</Typography.Text>;
  return (
    <Space wrap>
      {objects.map((item) => (
        <Tag key={`${item.type}-${item.id}`}>{objectTypeLabel(item.type)}#{item.id}</Tag>
      ))}
    </Space>
  );
}

function cleanedSummary(cleaned: Record<string, number>) {
  const total = Object.values(cleaned).reduce((sum, value) => sum + Number(value || 0), 0);
  return `${total} 项`;
}

function confidence(value?: number) {
  return value == null ? "-" : Number(value).toFixed(2);
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
    feishu_send_adapter: "飞书发送适配器"
  };
  return labels[value ?? ""] ?? value ?? "-";
}

function objectTypeLabel(type: string) {
  const labels: Record<string, string> = {
    ticket: "工单",
    lead: "线索",
    task: "任务",
    candidate: "候选人",
    knowledge_gap: "知识缺口"
  };
  return labels[type] ?? type;
}
