import { Alert, App as AntdApp, Button, Descriptions, Drawer, Input, Popconfirm, Select, Space, Tag, Tooltip, Typography } from "antd";
import { EyeOutlined, FileSearchOutlined, ReloadOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import { AgentRunDetailDrawer } from "../components/AgentRunDetailDrawer";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { PageHeader } from "../components/PageHeader";
import { ReplayComparisonModal } from "../components/ReplayComparisonModal";
import { ReloadButton } from "../components/ReloadButton";
import { ResizableTable } from "../components/ResizableTable";
import { StatusTag } from "../components/StatusTag";
import { useAsyncData } from "../components/useAsyncData";
import type { AgentRun, MessageEvent, MessageRerunResult } from "../types";
import { entityKey, formatTime, shortText } from "../utils/format";
import { hashTarget, isTargetId } from "../utils/navigation";
import { matchesSearch } from "../utils/search";
import { useHashId } from "../utils/useHashId";

function agentLabel(value: string) {
  const labels: Record<string, string> = {
    support_ticket_agent: "客服工单智能体",
    sales_lead_agent: "销售线索智能体",
    community_ops_agent: "私域社群智能体",
    recruiting_hr_agent: "招聘入职智能体",
    system_command_agent: "系统命令",
    manual_inbox_agent: "人工收件箱",
    chat_agent: "人工收件箱"
  };
  return labels[value] ?? (value || "-");
}

function objectLabels(objects: MessageEvent["related_objects"]) {
  if (!objects?.length) return "-";
  const labels: Record<string, string> = {
    ticket: "工单",
    lead: "线索",
    task: "任务",
    candidate: "候选人",
    knowledge_gap: "知识缺口"
  };
  return objects.map((item) => `${labels[item.type] ?? item.type}#${item.id}`).join(" / ");
}

export function MessagesPage() {
  const { message: antdMessage } = AntdApp.useApp();
  const { data, error, loading, reload } = useAsyncData(api.getMessages);
  const targetId = useHashId();
  const [rerunningId, setRerunningId] = useState<string>();
  const [loadingRunId, setLoadingRunId] = useState<string>();
  const [activeRun, setActiveRun] = useState<AgentRun>();
  const [activeMessage, setActiveMessage] = useState<MessageEvent>();
  const [replayResult, setReplayResult] = useState<MessageRerunResult>();
  const [source, setSource] = useState<string>();
  const [messageType, setMessageType] = useState<string>();
  const [agent, setAgent] = useState<string>();
  const [risk, setRisk] = useState<string>();
  const [hasObject, setHasObject] = useState<string>();
  const [search, setSearch] = useState("");

  const rows = useMemo(() => {
    return (data?.items ?? []).filter((item) => {
      const itemSource = String(item.normalized_json?.channel ?? item.channel_label ?? "");
      if (source && itemSource !== source && item.channel_label !== sourceLabel(source)) return false;
      if (messageType && item.message_type !== messageType) return false;
      if (agent && item.target_agent !== agent) return false;
      if (risk && item.risk_level !== risk) return false;
      if (hasObject === "yes" && !item.has_related_objects) return false;
      if (hasObject === "no" && item.has_related_objects) return false;
      if (!matchesSearch(item as unknown as Record<string, unknown>, search, [
        "id",
        "event_id",
        "message_id",
        "text",
        "sender_name",
        "sender_display_name",
        "conversation_display_name",
        "channel_label",
        "intent",
        "target_agent",
        "risk_level",
        "related_objects.label",
        "normalized_json"
      ])) return false;
      return true;
    });
  }, [agent, data?.items, hasObject, messageType, risk, search, source]);

  const handleRerun = useCallback(async (row: MessageEvent) => {
    if (row.id == null) return;
    const rowId = String(row.id);
    setRerunningId(rowId);
    try {
      const result = await api.rerunMessage(row.id);
      antdMessage.success(rerunSummary(result));
      setReplayResult(result);
      await reload();
    } catch (err) {
      antdMessage.error(err instanceof Error ? err.message : "重跑路由失败");
    } finally {
      setRerunningId(undefined);
    }
  }, [reload]);

  const openRunDetail = useCallback(async (row: MessageEvent) => {
    if (row.agent_run_id == null) return;
    const runId = String(row.agent_run_id);
    setLoadingRunId(runId);
    try {
      setActiveRun(await api.getAgentRun(row.agent_run_id));
    } catch (err) {
      antdMessage.error(err instanceof Error ? err.message : "运行详情加载失败");
    } finally {
      setLoadingRunId(undefined);
    }
  }, []);

  const columns = useMemo<ColumnsType<MessageEvent>>(() => [
    { title: "时间", dataIndex: "timestamp", width: 160, render: (value, row) => formatTime(value ?? row.received_at) },
    {
      title: "渠道",
      dataIndex: "channel",
      width: 100,
      render: (_, row) => <Tag>{row.channel_label ?? sourceLabel(String(row.normalized_json?.channel ?? ""))}</Tag>
    },
    {
      title: "类型",
      dataIndex: "message_type",
      width: 110,
      render: (_, row) => <Tag color={messageTypeColor(row.message_type)}>{row.message_type_label ?? messageTypeLabel(row.message_type)}</Tag>
    },
    {
      title: "会话",
      dataIndex: "conversation_display_name",
      width: 190,
      ellipsis: true,
      render: (_, row) => identityLabel(row.conversation_display_name, row.conversation_short_id)
    },
    { title: "发送人", dataIndex: "sender_display_name", width: 160, render: (_, row) => identityLabel(row.sender_display_name ?? row.sender_name, row.sender_short_id) },
    {
      title: "消息",
      dataIndex: "text",
      width: 400,
      render: (value, row) => (
        <Space direction="vertical" size={2}>
          <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 380 }}>
            {shortText(value, 120)}
          </Typography.Text>
          {row.traceable_non_text ? <Typography.Text type="secondary">{shortText(nonTextHint(row), 88)}</Typography.Text> : null}
        </Space>
      )
    },
    { title: "意图", dataIndex: "intent", width: 140, render: (value, row) => value ?? row.normalized_json?.intent ?? "-" },
    { title: "智能体", dataIndex: "target_agent", width: 160, render: (value, row) => agentLabel(String(value ?? row.normalized_json?.target_agent ?? "")) },
    { title: "风险", dataIndex: "risk_level", width: 110, render: (value) => <StatusTag value={value} /> },
    { title: "置信度", dataIndex: "confidence", width: 90, render: (value) => value == null ? "-" : Number(value).toFixed(2) },
    { title: "关联对象", width: 180, render: (_, row) => objectLabels(row.related_objects) },
    {
      title: "操作",
      key: "actions",
      width: 168,
      fixed: "right",
      render: (_, row) => (
        <Space size={4}>
          <Tooltip title="查看消息追踪详情">
            <Button
              size="small"
              icon={<FileSearchOutlined />}
              onClick={() => setActiveMessage(row)}
            />
          </Tooltip>
          <Tooltip title="查看运行详情">
            <Button
              size="small"
              icon={<EyeOutlined />}
              loading={loadingRunId === String(row.agent_run_id)}
              disabled={row.agent_run_id == null}
              onClick={() => openRunDetail(row)}
            />
          </Tooltip>
          <Popconfirm
            title="重跑路由"
            description="会替换这条消息当前自动生成的业务对象和待审批草稿。"
            okText="重跑"
            cancelText="取消"
            onConfirm={() => handleRerun(row)}
          >
            <Tooltip title="按当前 Agent Router 重跑">
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={rerunningId === String(row.id)}
                disabled={row.id == null}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      )
    }
  ], [handleRerun, loadingRunId, openRunDetail, rerunningId]);

  return (
    <>
      <PageHeader
        title="消息事件"
        extra={
          <Space wrap>
            <Select allowClear placeholder="来源" value={source} onChange={setSource} style={{ width: 120 }} options={[
              { value: "feishu", label: "飞书" },
              { value: "csv", label: "CSV" },
              { value: "local_json", label: "JSON" }
            ]} />
            <Select allowClear placeholder="类型" value={messageType} onChange={setMessageType} style={{ width: 120 }} options={[
              { value: "text", label: "文本" },
              { value: "image", label: "图片" },
              { value: "file", label: "文件" },
              { value: "post", label: "富文本" },
              { value: "audio", label: "语音" },
              { value: "media", label: "视频" },
              { value: "interactive", label: "互动卡片" }
            ]} />
            <Select allowClear placeholder="智能体" value={agent} onChange={setAgent} style={{ width: 160 }} options={[
              { value: "support_ticket_agent", label: "客服工单" },
              { value: "sales_lead_agent", label: "销售线索" },
              { value: "community_ops_agent", label: "私域社群" },
              { value: "recruiting_hr_agent", label: "招聘入职" },
              { value: "manual_inbox_agent", label: "人工收件箱" },
              { value: "chat_agent", label: "人工收件箱" }
            ]} />
            <Select allowClear placeholder="风险" value={risk} onChange={setRisk} style={{ width: 110 }} options={[
              { value: "low", label: "低" },
              { value: "medium", label: "中" },
              { value: "high", label: "高" },
              { value: "critical", label: "严重" }
            ]} />
            <Select allowClear placeholder="业务对象" value={hasObject} onChange={setHasObject} style={{ width: 120 }} options={[
              { value: "yes", label: "已生成" },
              { value: "no", label: "未生成" }
            ]} />
            <Input.Search allowClear placeholder="搜索消息/发送人/会话/Agent" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 260 }} />
            <ReloadButton loading={loading} onReload={reload} />
          </Space>
        }
      />
      <ApiErrorAlert error={error} />
      <Typography.Paragraph type="secondary" className="table-ux-hint">
        表格可横向滚动；按住表头右侧边缘可调整列宽。
      </Typography.Paragraph>
      <ResizableTable
        size="small"
        loading={loading}
        rowKey={(row) => entityKey(row.id ?? row.event_id ?? row.message_id)}
        rowClassName={(row) => isTargetId(row.id, targetId) ? "row-highlight" : ""}
        dataSource={rows}
        columns={columns}
        scroll={{ x: 1770 }}
        pagination={{ pageSize: 12, total: rows.length }}
      />
      <AgentRunDetailDrawer open={Boolean(activeRun)} run={activeRun} onClose={() => setActiveRun(undefined)} />
      <Drawer
        title={activeMessage?.traceable_non_text ? "飞书消息追踪详情" : "消息详情"}
        width={720}
        open={Boolean(activeMessage)}
        onClose={() => setActiveMessage(undefined)}
      >
        {activeMessage ? <MessageTraceContent message={activeMessage} /> : null}
      </Drawer>
      <ReplayComparisonModal open={Boolean(replayResult)} result={replayResult} onClose={() => setReplayResult(undefined)} />
    </>
  );
}

function rerunSummary(result: Awaited<ReturnType<typeof api.rerunMessage>>) {
  const objects = result.related_objects?.map((item) => `${objectTypeLabel(item.type)}#${item.id}`).join(" / ");
  const agent = agentLabel(result.target_agent ?? "");
  return objects ? `已重跑：${agent}，生成 ${objects}` : `已重跑：${agent}，进入人工处理`;
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

function sourceLabel(value: string) {
  const labels: Record<string, string> = {
    feishu: "飞书",
    csv: "CSV",
    local_json: "JSON",
    json: "JSON"
  };
  return labels[value] ?? value ?? "-";
}

function messageTypeLabel(value?: string) {
  const labels: Record<string, string> = {
    text: "文本",
    image: "图片",
    file: "文件",
    audio: "语音",
    media: "视频",
    post: "富文本",
    interactive: "互动卡片",
    share_chat: "分享会话",
    sticker: "表情"
  };
  return labels[value ?? ""] ?? value ?? "-";
}

function messageTypeColor(value?: string) {
  if (value === "text") return "default";
  if (value === "image") return "blue";
  if (value === "file") return "purple";
  if (value === "post") return "gold";
  if (value === "interactive") return "orange";
  if (value === "audio" || value === "media") return "cyan";
  return "default";
}

function nonTextHint(message: MessageEvent) {
  return String(message.non_text_summary ?? trackingDetails(message)?.content_preview ?? "已记录非文本消息追踪信息");
}

function MessageTraceContent({ message }: { message: MessageEvent }) {
  const tracking = trackingDetails(message);
  const mentions = Array.isArray(tracking?.mentions) ? tracking?.mentions : [];
  const contentKeys = Array.isArray(message.message_tracking?.content_keys) ? message.message_tracking?.content_keys : [];
  return (
    <Space direction="vertical" size={14} style={{ width: "100%" }}>
      {message.traceable_non_text ? (
        <Alert
          showIcon
          type="info"
          message="这条飞书非文本消息已进入可追踪链路"
          description="可以继续查看运行详情、重跑路由，或从关联对象继续推进审批和处理。"
        />
      ) : null}
      <Descriptions size="small" column={1}>
        <Descriptions.Item label="类型">
          <Tag color={messageTypeColor(message.message_type)}>{message.message_type_label ?? messageTypeLabel(message.message_type)}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="时间">{formatTime(message.timestamp ?? message.received_at)}</Descriptions.Item>
        <Descriptions.Item label="发送人">{message.sender_display_name ?? message.sender_name ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="会话">{message.conversation_display_name ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="消息摘要">{message.text ?? "-"}</Descriptions.Item>
        {message.agent_run_id ? (
          <Descriptions.Item label="运行日志">
            <a href={hashTarget("agent-runs", message.agent_run_id)}>查看运行日志#{message.agent_run_id}</a>
          </Descriptions.Item>
        ) : null}
      </Descriptions>
      {tracking ? (
        <>
          <Typography.Title level={5}>追踪元数据</Typography.Title>
          <Descriptions size="small" column={1}>
            {tracking.title ? <Descriptions.Item label="标题">{String(tracking.title)}</Descriptions.Item> : null}
            {tracking.file_name ? <Descriptions.Item label="文件名">{String(tracking.file_name)}</Descriptions.Item> : null}
            {tracking.image_key ? <Descriptions.Item label="图片 Key"><Typography.Text code>{String(tracking.image_key)}</Typography.Text></Descriptions.Item> : null}
            {tracking.file_key ? <Descriptions.Item label="文件 Key"><Typography.Text code>{String(tracking.file_key)}</Typography.Text></Descriptions.Item> : null}
            {tracking.post_title ? <Descriptions.Item label="富文本标题">{String(tracking.post_title)}</Descriptions.Item> : null}
            {tracking.content_preview ? <Descriptions.Item label="内容预览">{String(tracking.content_preview)}</Descriptions.Item> : null}
            {mentions.length ? <Descriptions.Item label="@ 提及">{mentions.join(" / ")}</Descriptions.Item> : null}
            {contentKeys.length ? <Descriptions.Item label="内容字段">{contentKeys.join(", ")}</Descriptions.Item> : null}
          </Descriptions>
          <pre className="json-block">{JSON.stringify(message.message_tracking ?? {}, null, 2)}</pre>
        </>
      ) : (
        <Typography.Text type="secondary">当前没有额外追踪元数据。</Typography.Text>
      )}
    </Space>
  );
}

function trackingDetails(message: MessageEvent) {
  const tracking = message.message_tracking;
  if (!tracking || typeof tracking !== "object") return undefined;
  const details = tracking.details;
  if (!details || typeof details !== "object") return undefined;
  return details as Record<string, unknown>;
}

function identityLabel(name?: string, shortId?: string) {
  return (
    <Space direction="vertical" size={0}>
      <span>{name || "-"}</span>
      {shortId ? <Typography.Text type="secondary">{shortId}</Typography.Text> : null}
    </Space>
  );
}
