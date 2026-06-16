import { EyeOutlined, ReloadOutlined } from "@ant-design/icons";
import { App as AntdApp, Button, Drawer, Input, Select, Space, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { PageHeader } from "../components/PageHeader";
import { ResizableTable } from "../components/ResizableTable";
import { StatusTag } from "../components/StatusTag";
import { useAsyncData } from "../components/useAsyncData";
import type { FeishuChannelEvent } from "../types";
import { entityKey, formatTime, shortText } from "../utils/format";
import { hashTarget } from "../utils/navigation";
import { filterBySearch } from "../utils/search";

export function ChannelEventsPage() {
  const { message } = AntdApp.useApp();
  const [channel, setChannel] = useState("all");
  const [status, setStatus] = useState("all");
  const [relation, setRelation] = useState("all");
  const [activeEvent, setActiveEvent] = useState<FeishuChannelEvent>();
  const [retryingId, setRetryingId] = useState<string | number>();
  const [search, setSearch] = useState("");
  const loadEvents = useCallback(() => api.getChannelEvents({ channel, status, relation, limit: 100 }), [channel, relation, status]);
  const { data, error, loading, reload } = useAsyncData(loadEvents);
  const rows = useMemo(() => filterBySearch((data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "id",
    "channel_type",
    "channel_label",
    "event_type",
    "external_event_id",
    "status",
    "conversation_external_id",
    "actor_external_id",
    "related_message.text",
    "related_conversation.name",
    "raw_json"
  ]) as unknown as FeishuChannelEvent[], [data?.items, search]);

  const retryEvent = useCallback(async (row: FeishuChannelEvent) => {
    if (!row.id) return;
    setRetryingId(row.id);
    try {
      const result = await api.retryChannelEvent(row.id);
      message.success(`重试完成：${String(result.status ?? "-")}`);
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "重试失败");
    } finally {
      setRetryingId(undefined);
    }
  }, [reload]);

  const columns = useMemo<ColumnsType<FeishuChannelEvent>>(() => [
    { title: "ID", dataIndex: "id", width: 80 },
    {
      title: "渠道",
      dataIndex: "channel_label",
      width: 120,
      render: (value, row) => <Tag color={channelColor(row.channel_type)}>{value ?? row.channel_type}</Tag>
    },
    { title: "事件", dataIndex: "event_type", width: 280, render: (value) => shortText(value, 48) },
    { title: "状态", dataIndex: "status", width: 120, render: (value) => <StatusTag value={value} /> },
    {
      title: "会话",
      dataIndex: "conversation_external_id",
      width: 220,
      render: (value) => <Typography.Text code>{shortText(value, 28)}</Typography.Text>
    },
    {
      title: "用户",
      dataIndex: "actor_external_id",
      width: 220,
      render: (value) => <Typography.Text code>{shortText(value, 28)}</Typography.Text>
    },
    { title: "时间", dataIndex: "created_at", width: 170, render: formatTime },
    {
      title: "重试",
      width: 140,
      render: (_, row) => row.retry?.retryable ? (
        <Button size="small" loading={retryingId === row.id} onClick={() => retryEvent(row)}>
          重试接收
        </Button>
      ) : row.status === "retried" ? <Tag color="green">已重试</Tag> : <Tag>不可重试</Tag>
    },
    {
      title: "详情",
      fixed: "right",
      width: 90,
      render: (_, row) => (
        <Button icon={<EyeOutlined />} size="small" onClick={() => setActiveEvent(row)}>
          查看
        </Button>
      )
    }
  ], [retryEvent, retryingId]);

  return (
    <>
      <PageHeader
        title="渠道事件"
        extra={
          <>
            <Select
              value={channel}
              style={{ width: 140 }}
              onChange={setChannel}
              options={[
                { value: "all", label: "全部渠道" },
                { value: "feishu", label: "飞书" },
                { value: "wecom", label: "企业微信" },
                { value: "dingtalk", label: "钉钉" }
              ]}
            />
            <Select
              value={status}
              style={{ width: 130 }}
              onChange={setStatus}
              options={[
                { value: "all", label: "全部状态" },
                { value: "received", label: "已接收" },
                { value: "failed", label: "失败" },
                { value: "ignored", label: "已忽略" },
                { value: "retried", label: "已重试" }
              ]}
            />
            <Select
              value={relation}
              style={{ width: 150 }}
              onChange={setRelation}
              options={[
                { value: "all", label: "全部关联" },
                { value: "has_message", label: "有消息" },
                { value: "has_conversation", label: "有会话" },
                { value: "has_agent_run", label: "有运行记录" },
                { value: "unlinked", label: "未关联" }
              ]}
            />
            <Input.Search allowClear placeholder="搜索事件/会话/用户/原始JSON" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 280 }} />
            <Button icon={<ReloadOutlined />} loading={loading} onClick={reload}>
              刷新
            </Button>
          </>
        }
      />
      <ApiErrorAlert error={error} />
      <Typography.Paragraph type="secondary" className="table-ux-hint">
        表格可横向滚动；按住表头右侧边缘可调整列宽。
      </Typography.Paragraph>
      <ResizableTable
        size="small"
        loading={loading}
        rowKey={(row) => entityKey(row.id)}
        dataSource={rows}
        columns={columns}
        scroll={{ x: 1440 }}
        pagination={{ pageSize: 12, total: rows.length }}
      />
      <Drawer title={`渠道事件 #${activeEvent?.id ?? ""}`} width={680} open={Boolean(activeEvent)} onClose={() => setActiveEvent(undefined)}>
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Typography.Text>
            {activeEvent?.channel_label} / {activeEvent?.event_type}
          </Typography.Text>
          <Typography.Text type="secondary">外部事件 ID：{activeEvent?.external_event_id ?? "-"}</Typography.Text>
          {activeEvent?.retry ? (
            <Space wrap>
              <Tag color={activeEvent.retry.retryable ? "orange" : "default"}>
                {activeEvent.retry.retryable ? "可重试" : "不可重试"}
              </Tag>
              <Typography.Text type="secondary">已尝试 {activeEvent.retry.attempts ?? 0} 次</Typography.Text>
              {activeEvent.retry.reason ? <Typography.Text type="danger">{shortText(activeEvent.retry.reason, 120)}</Typography.Text> : null}
            </Space>
          ) : null}
          <Space wrap>
            {activeEvent?.links?.message_id ? <a href={hashTarget("messages", activeEvent.links.message_id)}>查看消息</a> : null}
            {activeEvent?.links?.conversation_id ? <a href={hashTarget("conversations", activeEvent.links.conversation_id)}>查看会话</a> : null}
            {(activeEvent?.links?.agent_run_ids ?? []).map((id) => (
              <a key={String(id)} href={hashTarget("agent-runs", id)}>运行日志#{id}</a>
            ))}
          </Space>
          {activeEvent?.related_message ? (
            <Typography.Paragraph>
              <Typography.Text strong>关联消息：</Typography.Text>
              {shortText(activeEvent.related_message.text, 80)}
            </Typography.Paragraph>
          ) : null}
          {activeEvent?.related_conversation ? (
            <Typography.Paragraph>
              <Typography.Text strong>关联会话：</Typography.Text>
              {activeEvent.related_conversation.name}
            </Typography.Paragraph>
          ) : null}
          <pre className="json-block">{JSON.stringify(activeEvent?.raw_json ?? {}, null, 2)}</pre>
        </Space>
      </Drawer>
    </>
  );
}

function channelColor(value?: string) {
  if (value === "feishu") return "blue";
  if (value === "wecom") return "green";
  if (value === "dingtalk") return "orange";
  return "default";
}
