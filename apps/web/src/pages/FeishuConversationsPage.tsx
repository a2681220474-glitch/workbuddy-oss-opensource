import { CommentOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, App as AntdApp, Button, Input, Select, Space, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Key } from "react";
import { useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { PageHeader } from "../components/PageHeader";
import { ResizableTable } from "../components/ResizableTable";
import { useAsyncData } from "../components/useAsyncData";
import type { FeishuConversation } from "../types";
import { entityKey, formatTime, shortText } from "../utils/format";
import { hashTarget, isTargetId } from "../utils/navigation";
import { filterBySearch } from "../utils/search";
import { useHashId } from "../utils/useHashId";

const agentOptions = [
  { value: "auto", label: "自动判断" },
  { value: "support_ticket_agent", label: "固定客服工单" },
  { value: "sales_lead_agent", label: "固定销售线索" },
  { value: "community_ops_agent", label: "固定私域社群" },
  { value: "recruiting_hr_agent", label: "固定招聘入职" }
];

const sendModeOptions = [
  { value: "inherit", label: "跟随全局" },
  { value: "mock", label: "只模拟发送" },
  { value: "real", label: "允许真实发送" },
  { value: "disabled", label: "禁止发送" }
];

export function FeishuConversationsPage() {
  const { message } = AntdApp.useApp();
  const [channelFilter, setChannelFilter] = useState("all");
  const [bulkSendMode, setBulkSendMode] = useState("mock");
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [search, setSearch] = useState("");
  const loadConversations = useCallback(() => api.getConversations(channelFilter), [channelFilter]);
  const { data, error, loading, reload } = useAsyncData(loadConversations);
  const targetId = useHashId();
  const [savingKey, setSavingKey] = useState<string>();
  const [bulkSaving, setBulkSaving] = useState(false);
  const rows = useMemo(() => filterBySearch((data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "id",
    "channel",
    "name",
    "type",
    "external_conversation_id",
    "short_id",
    "bound_agent",
    "send_mode",
    "latest_message.text",
    "latest_message.sender_name"
  ]) as unknown as FeishuConversation[], [data?.items, search]);

  const updatePolicy = async (row: FeishuConversation, payload: { bound_agent?: string; send_mode?: string }) => {
    setSavingKey(`${row.id}:${Object.keys(payload).join(",")}`);
    try {
      await api.updateConversationPolicy(row.id, payload);
      message.success("会话策略已更新");
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "更新会话策略失败");
    } finally {
      setSavingKey(undefined);
    }
  };

  const bulkUpdateSendMode = async () => {
    setBulkSaving(true);
    try {
      const result = await api.bulkUpdateConversationPolicy({
        channel: channelFilter,
        ids: selectedRowKeys.map((key) => typeof key === "number" ? key : String(key)),
        send_mode: bulkSendMode
      });
      message.success(`已更新 ${result.updated_count ?? 0} 个会话`);
      setSelectedRowKeys([]);
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "批量更新失败");
    } finally {
      setBulkSaving(false);
    }
  };

  const columns = useMemo<ColumnsType<FeishuConversation>>(() => [
    {
      title: "会话",
      width: 260,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Space>
            <CommentOutlined />
            <Typography.Text strong>{row.name ?? "渠道会话"}</Typography.Text>
            <Tag color={channelColor(row.channel)}>{channelLabel(row.channel)}</Tag>
            <Tag>{row.type === "private" ? "私聊" : "群聊"}</Tag>
          </Space>
          <Typography.Text type="secondary">{row.short_id ?? shortText(row.external_conversation_id, 24)}</Typography.Text>
        </Space>
      )
    },
    {
      title: "最近消息",
      width: 260,
      render: (_, row) => row.latest_message ? (
        <Space direction="vertical" size={0}>
          <a href={hashTarget("messages", row.latest_message.id)}>查看消息</a>
          <Typography.Text>{shortText(row.latest_message.text, 56)}</Typography.Text>
        </Space>
      ) : "-"
    },
    { title: "消息数", dataIndex: "message_count", width: 90, render: (value) => value ?? 0 },
    {
      title: "绑定智能体",
      dataIndex: "bound_agent",
      width: 180,
      render: (value, row) => (
        <Select
          size="small"
          value={value ?? "auto"}
          options={agentOptions}
          loading={savingKey === `${row.id}:bound_agent`}
          style={{ width: 160 }}
          onChange={(next) => updatePolicy(row, { bound_agent: next })}
        />
      )
    },
    {
      title: "发送策略",
      dataIndex: "send_mode",
      width: 170,
      render: (value, row) => (
        <Select
          size="small"
          value={value ?? "inherit"}
          options={sendModeOptions}
          loading={savingKey === `${row.id}:send_mode`}
          style={{ width: 150 }}
          onChange={(next) => updatePolicy(row, { send_mode: next })}
        />
      )
    },
    { title: "最近活跃", dataIndex: "last_message_at", width: 160, render: formatTime },
    {
      title: "操作",
      width: 160,
      render: (_, row) => (
        <Space>
          {row.latest_message?.id ? <a href={hashTarget("messages", row.latest_message.id)}>消息事件</a> : null}
          {row.channel === "feishu" ? <a href={hashTarget("feishu")}>诊断</a> : null}
        </Space>
      )
    }
  ], [savingKey]);

  return (
    <>
      <PageHeader
        title="渠道会话"
        extra={
          <>
            <Select
              value={channelFilter}
              style={{ width: 130 }}
              onChange={setChannelFilter}
              options={[
                { value: "all", label: "全部渠道" },
                { value: "feishu", label: "飞书" },
                { value: "wecom", label: "企业微信" },
                { value: "dingtalk", label: "钉钉" },
                { value: "csv", label: "CSV" }
              ]}
            />
            <Select
              value={bulkSendMode}
              style={{ width: 140 }}
              onChange={setBulkSendMode}
              options={sendModeOptions}
            />
            <Input.Search allowClear placeholder="搜索会话/消息/策略/ID" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 260 }} />
            <Button loading={bulkSaving} onClick={bulkUpdateSendMode}>
              {selectedRowKeys.length ? `批量切换 ${selectedRowKeys.length} 个` : "按筛选批量切换"}
            </Button>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={reload}>
              刷新
            </Button>
          </>
        }
      />
      <ApiErrorAlert error={error} />
      <Alert
        type="info"
        showIcon
        className="api-alert"
        message="会话策略已升级为通用渠道策略"
        description="飞书、企业微信、钉钉未来都会复用同一套绑定智能体和发送策略。当前飞书可真实运行，企微/钉钉仍是 v0.4 骨架。"
      />
      <Typography.Paragraph type="secondary" className="table-ux-hint">
        表格可横向滚动；按住表头右侧边缘可调整列宽。
      </Typography.Paragraph>
      <ResizableTable
        size="small"
        loading={loading}
        rowKey={(row) => entityKey(row.id)}
        rowSelection={{
          selectedRowKeys,
          preserveSelectedRowKeys: false,
          onChange: setSelectedRowKeys
        }}
        rowClassName={(row) => isTargetId(row.id, targetId) ? "row-highlight" : ""}
        dataSource={rows}
        columns={columns}
        scroll={{ x: 1280 }}
        pagination={{ pageSize: 12, total: rows.length }}
      />
    </>
  );
}

function channelLabel(value?: string) {
  const labels: Record<string, string> = {
    feishu: "飞书",
    wecom: "企业微信",
    dingtalk: "钉钉",
    local_csv: "CSV",
    local: "本地"
  };
  return labels[value ?? ""] ?? value ?? "-";
}

function channelColor(value?: string) {
  if (value === "feishu") return "blue";
  if (value === "wecom") return "green";
  if (value === "dingtalk") return "orange";
  return "default";
}
