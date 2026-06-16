import { App as AntdApp, Button, Card, Col, Descriptions, Drawer, Input, Modal, Row, Space, Tabs, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { PageHeader } from "../components/PageHeader";
import { ReloadButton } from "../components/ReloadButton";
import { ResizableTable } from "../components/ResizableTable";
import { StatusTag } from "../components/StatusTag";
import { useAsyncData } from "../components/useAsyncData";
import type { CommunityOverview, EntityId } from "../types";
import { entityKey, formatTime, shortText } from "../utils/format";
import { hashTarget } from "../utils/navigation";
import { filterBySearch } from "../utils/search";

type CommunityConversation = NonNullable<CommunityOverview["conversations"]>[number];
type CommunityLead = NonNullable<CommunityOverview["high_intent_users"]>[number];
type CommunityGap = NonNullable<CommunityOverview["unanswered_questions"]>[number];
type CommunityRiskMessage = NonNullable<CommunityOverview["risk_messages"]>[number];
type CommunityTask = NonNullable<CommunityOverview["tasks"]>[number];

export function CommunityPage() {
  const { message } = AntdApp.useApp();
  const { data, error, loading, reload } = useAsyncData(api.getCommunityOverview);
  const [replyMessage, setReplyMessage] = useState<CommunityRiskMessage>();
  const [draftText, setDraftText] = useState("");
  const [activeRisk, setActiveRisk] = useState<CommunityRiskMessage>();
  const [activeTask, setActiveTask] = useState<CommunityTask>();
  const [completingTaskId, setCompletingTaskId] = useState<EntityId>();
  const [search, setSearch] = useState("");
  const conversationRows = useMemo(() => filterBySearch((data?.conversations ?? []) as unknown as Record<string, unknown>[], search, [
    "conversation_id", "name", "latest_message", "activity_score", "message_count"
  ]) as unknown as CommunityConversation[], [data?.conversations, search]);
  const leadRows = useMemo(() => filterBySearch((data?.high_intent_users ?? []) as unknown as Record<string, unknown>[], search, [
    "id", "customer_name", "interest", "stage", "next_step", "source_message_id"
  ]) as unknown as CommunityLead[], [data?.high_intent_users, search]);
  const gapRows = useMemo(() => filterBySearch((data?.unanswered_questions ?? []) as unknown as Record<string, unknown>[], search, [
    "id", "question", "suggested_answer", "status", "source_message_id"
  ]) as unknown as CommunityGap[], [data?.unanswered_questions, search]);
  const riskRows = useMemo(() => filterBySearch((data?.risk_messages ?? []) as unknown as Record<string, unknown>[], search, [
    "id", "sender_name", "conversation_name", "text", "risk_level"
  ]) as unknown as CommunityRiskMessage[], [data?.risk_messages, search]);
  const taskRows = useMemo(() => filterBySearch((data?.tasks ?? []) as unknown as Record<string, unknown>[], search, [
    "id", "title", "status", "priority", "due_hint", "summary", "related_object_type", "related_object_id"
  ]) as unknown as CommunityTask[], [data?.tasks, search]);

  const completeTask = async (id?: EntityId) => {
    if (id === undefined) return;
    setCompletingTaskId(id);
    try {
      await api.completeCommunityTask(id);
      message.success("社群任务已完成");
      setActiveTask((current) => current?.id === id ? { ...current, status: "done", completed_at: new Date().toISOString() } : current);
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "更新任务失败");
    } finally {
      setCompletingTaskId(undefined);
    }
  };

  const openReplyDraft = (row: CommunityRiskMessage) => {
    setReplyMessage(row);
    setDraftText(defaultDraft(row));
  };

  const createApprovalDraft = async () => {
    if (!replyMessage?.id) return;
    try {
      await api.createCommunityApprovalDraft(replyMessage.id, { draft_content: draftText });
      message.success("社群回复草稿已进入审批队列");
      setReplyMessage(undefined);
      setDraftText("");
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "生成审批草稿失败");
    }
  };

  const conversationColumns: ColumnsType<CommunityConversation> = [
    { title: "群/会话", dataIndex: "name", width: 180, render: (value, row) => value ?? `会话#${row.conversation_id}` },
    { title: "活跃", dataIndex: "activity_score", width: 90, render: (value) => value ?? 0 },
    { title: "消息", dataIndex: "message_count", width: 90, render: (value) => value ?? 0 },
    { title: "高意向", dataIndex: "high_intent_count", width: 100, render: (value) => value ?? 0 },
    { title: "未回复", dataIndex: "unanswered_count", width: 100, render: (value) => value ?? 0 },
    { title: "风险", dataIndex: "risk_count", width: 90, render: (value) => <StatusTag value={Number(value ?? 0) > 0 ? "high" : "low"} /> },
    { title: "最新消息", dataIndex: "latest_message", width: 360, render: (value) => shortText(value, 90) },
    { title: "时间", dataIndex: "latest_at", width: 160, render: formatTime }
  ];

  const leadColumns: ColumnsType<CommunityLead> = [
    { title: "用户", dataIndex: "customer_name", width: 150 },
    { title: "评分", dataIndex: "score", width: 90 },
    { title: "阶段", dataIndex: "stage", width: 110, render: (value) => <StatusTag value={value} /> },
    { title: "下一步", dataIndex: "next_step", width: 360, render: (value) => shortText(value, 100) },
    { title: "来源", dataIndex: "source_message_id", width: 110, render: (value) => value ? <a href={hashTarget("messages", value)}>消息#{value}</a> : "-" }
  ];

  const gapColumns: ColumnsType<CommunityGap> = [
    { title: "问题", dataIndex: "question", width: 420, render: (value) => shortText(value, 110) },
    { title: "状态", dataIndex: "status", width: 110, render: (value) => <StatusTag value={value} /> },
    { title: "次数", dataIndex: "occurrence_count", width: 80 },
    { title: "建议答案", dataIndex: "suggested_answer", width: 360, render: (value) => shortText(value, 90) },
    { title: "来源", dataIndex: "source_message_id", width: 110, render: (value) => value ? <a href={hashTarget("messages", value)}>消息#{value}</a> : "-" }
  ];

  const riskColumns: ColumnsType<CommunityRiskMessage> = [
    { title: "发送人", dataIndex: "sender_name", width: 140 },
    { title: "群/会话", dataIndex: "conversation_name", width: 170 },
    { title: "风险", dataIndex: "risk_level", width: 100, render: (value) => <StatusTag value={value} /> },
    { title: "内容", dataIndex: "text", width: 440, render: (value) => shortText(value, 120) },
    { title: "时间", dataIndex: "received_at", width: 160, render: formatTime },
    {
      title: "动作",
      width: 190,
      fixed: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => setActiveRisk(row)}>详情</Button>
          <Button size="small" onClick={() => openReplyDraft(row)}>生成回复</Button>
        </Space>
      )
    }
  ];

  const taskColumns: ColumnsType<CommunityTask> = [
    { title: "任务", dataIndex: "title", width: 320, render: (value) => shortText(value, 100) },
    { title: "状态", dataIndex: "status", width: 110, render: (value) => <StatusTag value={value} /> },
    { title: "优先级", dataIndex: "priority", width: 100, render: (value) => <StatusTag value={value} /> },
    { title: "时间提示", dataIndex: "due_hint", width: 110, render: (value) => value ?? "-" },
    { title: "摘要", dataIndex: "summary", width: 360, render: (value) => shortText(value, 90) },
    {
      title: "来源",
      width: 120,
      render: (_, row) => row.source_message_id ? <a href={hashTarget("messages", row.source_message_id)}>消息#{row.source_message_id}</a> : "-"
    },
    {
      title: "动作",
      width: 150,
      fixed: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => setActiveTask(row)}>详情</Button>
          <Button size="small" loading={completingTaskId === row.id} disabled={row.status === "done"} onClick={() => completeTask(row.id)}>完成</Button>
        </Space>
      )
    }
  ];

  return (
    <>
      <PageHeader title="社群运营" extra={
        <Space wrap>
          <Input.Search allowClear placeholder="搜索群/用户/问题/风险/任务" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 280 }} />
          <ReloadButton loading={loading} onReload={reload} />
        </Space>
      } />
      <ApiErrorAlert error={error} />
      <Row gutter={[12, 12]} className="dashboard-lower">
        {[
          { label: "社群消息", value: data?.summary?.community_messages ?? 0, status: "received" },
          { label: "群/会话", value: data?.summary?.community_conversations ?? 0, status: "normal" },
          { label: "高意向用户", value: data?.summary?.high_intent_users ?? 0, status: "high" },
          { label: "未回复问题", value: data?.summary?.unanswered_questions ?? 0, status: "pending" },
          { label: "风险消息", value: data?.summary?.risk_messages ?? 0, status: "urgent" },
          { label: "待办任务", value: data?.summary?.open_tasks ?? 0, status: "todo" }
        ].map((item) => (
          <Col xs={12} md={8} xl={4} key={item.label}>
            <Card size="small">
              <Space>
                <StatusTag value={item.status} />
                <Typography.Text>{item.label}</Typography.Text>
              </Space>
              <div className="metric-number">{item.value}</div>
            </Card>
          </Col>
        ))}
      </Row>
      <Tabs
        items={[
          {
            key: "conversations",
            label: "社群会话",
            children: <CommunityTable loading={loading} rowKey={(row) => entityKey(row.conversation_id)} dataSource={conversationRows} columns={conversationColumns} scrollX={1350} />
          },
          {
            key: "high-intent",
            label: "高意向用户",
            children: <CommunityTable loading={loading} rowKey={(row) => entityKey(row.id)} dataSource={leadRows} columns={leadColumns} scrollX={1130} />
          },
          {
            key: "questions",
            label: "未回复问题",
            children: <CommunityTable loading={loading} rowKey={(row) => entityKey(row.id)} dataSource={gapRows} columns={gapColumns} scrollX={1180} />
          },
          {
            key: "risks",
            label: "风险消息",
            children: <CommunityTable loading={loading} rowKey={(row) => entityKey(row.id)} dataSource={riskRows} columns={riskColumns} scrollX={1240} />
          },
          {
            key: "tasks",
            label: "社群任务",
            children: <CommunityTable loading={loading} rowKey={(row) => entityKey(row.id)} dataSource={taskRows} columns={taskColumns} scrollX={1400} />
          }
        ]}
      />
      <RiskMessageDrawer risk={activeRisk} onClose={() => setActiveRisk(undefined)} onCreateDraft={openReplyDraft} />
      <TaskDetailDrawer task={activeTask} completing={completingTaskId === activeTask?.id} onClose={() => setActiveTask(undefined)} onComplete={completeTask} />
      <Modal
        title="社群回复草稿"
        open={Boolean(replyMessage)}
        onCancel={() => setReplyMessage(undefined)}
        footer={[
          <Button key="cancel" onClick={() => setReplyMessage(undefined)}>取消</Button>,
          <Button key="approval" type="primary" onClick={createApprovalDraft}>送入审批队列</Button>
        ]}
      >
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Typography.Text type="secondary">{replyMessage?.text}</Typography.Text>
          <Input.TextArea rows={4} value={draftText} onChange={(event) => setDraftText(event.target.value)} />
        </Space>
      </Modal>
    </>
  );
}

function CommunityTable<T extends object>({
  loading,
  rowKey,
  dataSource,
  columns,
  scrollX
}: {
  loading: boolean;
  rowKey: (row: T) => string;
  dataSource: T[];
  columns: ColumnsType<T>;
  scrollX: number;
}) {
  return (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      <Typography.Paragraph type="secondary" className="table-ux-hint">
        表格可横向滚动；按住表头右侧边缘可调整列宽。
      </Typography.Paragraph>
      <ResizableTable
        size="small"
        loading={loading}
        rowKey={rowKey}
        dataSource={dataSource}
        columns={columns}
        scroll={{ x: scrollX }}
        pagination={{ pageSize: 8, total: dataSource.length }}
      />
    </Space>
  );
}

function RiskMessageDrawer({ risk, onClose, onCreateDraft }: { risk?: CommunityRiskMessage; onClose: () => void; onCreateDraft: (row: CommunityRiskMessage) => void }) {
  return (
    <Drawer title={`风险消息 #${risk?.id ?? ""}`} width={680} open={Boolean(risk)} onClose={onClose}>
      <Descriptions size="small" column={2}>
        <Descriptions.Item label="发送人">{risk?.sender_name ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="风险"><StatusTag value={risk?.risk_level} /></Descriptions.Item>
        <Descriptions.Item label="群/会话">{risk?.conversation_name ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="时间">{formatTime(risk?.received_at)}</Descriptions.Item>
        <Descriptions.Item label="来源" span={2}>{risk?.id ? <a href={hashTarget("messages", risk.id)}>消息#{risk.id}</a> : "-"}</Descriptions.Item>
      </Descriptions>
      <Typography.Title level={5}>原文</Typography.Title>
      <Typography.Paragraph className="detail-text">{risk?.text ?? "-"}</Typography.Paragraph>
      <Typography.Title level={5}>建议处理</Typography.Title>
      <Typography.Paragraph className="detail-text">{risk ? defaultDraft(risk) : "-"}</Typography.Paragraph>
      <Space>
        {risk ? <Button type="primary" onClick={() => onCreateDraft(risk)}>生成回复草稿</Button> : null}
        {risk?.id ? <Button href={hashTarget("messages", risk.id)}>查看消息事件</Button> : null}
      </Space>
    </Drawer>
  );
}

function TaskDetailDrawer({ task, completing, onClose, onComplete }: { task?: CommunityTask; completing: boolean; onClose: () => void; onComplete: (id?: EntityId) => void }) {
  return (
    <Drawer title={`社群任务 #${task?.id ?? ""}`} width={680} open={Boolean(task)} onClose={onClose}>
      <Descriptions size="small" column={2}>
        <Descriptions.Item label="状态"><StatusTag value={task?.status} /></Descriptions.Item>
        <Descriptions.Item label="优先级"><StatusTag value={task?.priority} /></Descriptions.Item>
        <Descriptions.Item label="时间提示">{task?.due_hint ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{formatTime(task?.created_at)}</Descriptions.Item>
        <Descriptions.Item label="更新时间">{formatTime(task?.updated_at)}</Descriptions.Item>
        <Descriptions.Item label="完成时间">{formatTime(task?.completed_at)}</Descriptions.Item>
        <Descriptions.Item label="来源消息">{task?.source_message_id ? <a href={hashTarget("messages", task.source_message_id)}>消息#{task.source_message_id}</a> : "-"}</Descriptions.Item>
        <Descriptions.Item label="关联对象">{relatedObjectLabel(task)}</Descriptions.Item>
      </Descriptions>
      <Typography.Title level={5}>任务</Typography.Title>
      <Typography.Paragraph>{task?.title ?? "-"}</Typography.Paragraph>
      <Typography.Title level={5}>处理摘要</Typography.Title>
      <Typography.Paragraph className="detail-text">{task?.summary ?? "-"}</Typography.Paragraph>
      <Space>
        <Button type="primary" loading={completing} disabled={!task?.id || task.status === "done"} onClick={() => onComplete(task?.id)}>
          标记完成
        </Button>
        {task?.source_message_id ? <Button href={hashTarget("messages", task.source_message_id)}>查看来源消息</Button> : null}
      </Space>
    </Drawer>
  );
}

function relatedObjectLabel(task?: CommunityTask) {
  if (!task?.related_object_type && !task?.related_object_id) return "-";
  return `${task.related_object_type ?? "object"}#${task.related_object_id ?? "-"}`;
}

function defaultDraft(row: CommunityRiskMessage) {
  if (row.risk_level === "high") {
    return "您好，已收到您的反馈。我们会由人工同事优先核实，并尽快给出明确处理结果。";
  }
  return "您好，消息已收到。我先帮您记录，确认后给您回复。";
}
