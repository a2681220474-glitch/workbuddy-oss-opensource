import { App as AntdApp, Button, Input, InputNumber, Popconfirm, Select, Space, Tag, Tooltip, Typography } from "antd";
import { EyeOutlined, ReloadOutlined } from "@ant-design/icons";
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
import type { AgentRun, MessageRerunResult } from "../types";
import { formatTime, shortText } from "../utils/format";
import { hashTarget, isTargetId } from "../utils/navigation";
import { filterBySearch } from "../utils/search";
import { useHashId } from "../utils/useHashId";

export function AgentRunsPage() {
  const { message: antdMessage } = AntdApp.useApp();
  const [agentType, setAgentType] = useState<string>();
  const [status, setStatus] = useState<string>();
  const [objectType, setObjectType] = useState<string>();
  const [objectId, setObjectId] = useState<number>();
  const loadRuns = useCallback(() => api.getAgentRuns({
    agent_type: agentType,
    status,
    business_object_type: objectType,
    business_object_id: objectId
  }), [agentType, objectId, objectType, status]);
  const { data, error, loading, reload } = useAsyncData(loadRuns);
  const targetId = useHashId();
  const [activeRun, setActiveRun] = useState<AgentRun>();
  const [replayingId, setReplayingId] = useState<string>();
  const [replayResult, setReplayResult] = useState<MessageRerunResult>();
  const [search, setSearch] = useState("");
  const rows = useMemo(() => filterBySearch((data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "id",
    "agent_type",
    "agent_name",
    "target_agent",
    "status",
    "message_id",
    "risk_level",
    "intent",
    "confidence",
    "model_provider",
    "model_name",
    "error_message",
    "prompt_json",
    "model_output_json",
    "action_json"
  ]) as unknown as AgentRun[], [data?.items, search]);

  const handleReplay = useCallback(async (row: AgentRun) => {
    if (row.id == null) return;
    setReplayingId(String(row.id));
    try {
      const result = await api.replayAgentRun(row.id);
      antdMessage.success(replaySummary(result));
      setReplayResult(result);
      await reload();
    } catch (err) {
      antdMessage.error(err instanceof Error ? err.message : "运行重放失败");
    } finally {
      setReplayingId(undefined);
    }
  }, [reload]);

  const columns: ColumnsType<AgentRun> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "智能体", dataIndex: "agent_name", width: 180, render: (value, row) => agentLabel(value ?? row.agent_type ?? row.target_agent) },
    { title: "状态", dataIndex: "status", width: 110, render: (value) => <StatusTag value={value} /> },
    {
      title: "消息",
      dataIndex: "message_id",
      width: 100,
      render: (value) => value ? <a href={hashTarget("messages", value)}>#{value}</a> : "-"
    },
    { title: "风险", dataIndex: "risk_level", width: 100, render: (value) => <StatusTag value={value} /> },
    { title: "意图", dataIndex: "intent", width: 140, render: (value) => value ?? "-" },
    { title: "置信度", dataIndex: "confidence", width: 100, render: (value) => value ?? "-" },
    { title: "模型", dataIndex: "model_name", width: 140, render: (value) => value ?? "mock" },
    {
      title: "审批",
      dataIndex: "requires_approval",
      width: 90,
      render: (value, row) => {
        const actions = (row.action_json as { actions?: unknown[] } | undefined)?.actions ?? [];
        const requiresApproval = value ?? actions.some((action) => JSON.stringify(action).includes("send_draft_to_approval"));
        return <Tag color={requiresApproval ? "blue" : "default"}>{requiresApproval ? "是" : "否"}</Tag>;
      }
    },
    {
      title: "输入",
      dataIndex: "input_text",
      render: (value, row) => shortText(value ?? JSON.stringify(row.prompt_json ?? {}), 80)
    },
    { title: "耗时", dataIndex: "latency_ms", width: 90, render: (value) => value ? `${value}ms` : "-" },
    { title: "创建时间", dataIndex: "created_at", width: 160, render: formatTime },
    {
      title: "操作",
      width: 120,
      render: (_, row) => (
        <Space size={4}>
          <Tooltip title="查看运行详情">
            <Button size="small" icon={<EyeOutlined />} onClick={() => setActiveRun(row)} />
          </Tooltip>
          <Popconfirm
            title="重放运行"
            description="会用当前 Router 重放这条运行关联的消息，并替换该消息自动生成的业务对象和待审批草稿。"
            okText="重放"
            cancelText="取消"
            onConfirm={() => handleReplay(row)}
          >
            <Tooltip title={row.message_id == null ? "无关联消息，不能重放" : "按当前 Router 重放"}>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={replayingId === String(row.id)}
                disabled={row.message_id == null}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <>
      <PageHeader
        title="运行日志"
        extra={
          <Space wrap>
            <Select allowClear placeholder="Agent" value={agentType} onChange={setAgentType} style={{ width: 170 }} options={agentOptions()} />
            <Select allowClear placeholder="状态" value={status} onChange={setStatus} style={{ width: 120 }} options={[
              { value: "success", label: "成功" },
              { value: "failed", label: "失败" },
              { value: "running", label: "运行中" }
            ]} />
            <Select allowClear placeholder="业务对象" value={objectType} onChange={setObjectType} style={{ width: 140 }} options={objectOptions()} />
            <InputNumber min={1} placeholder="对象 ID" value={objectId} onChange={(value) => setObjectId(value === null ? undefined : Number(value))} style={{ width: 120 }} />
            <Input.Search allowClear placeholder="搜索Agent/模型/意图/错误/JSON" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 280 }} />
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
        rowKey="id"
        rowClassName={(row) => isTargetId(row.id, targetId) ? "row-highlight" : ""}
        dataSource={rows}
        columns={columns}
        scroll={{ x: 1380 }}
        pagination={{ pageSize: 12, total: rows.length }}
      />
      <AgentRunDetailDrawer open={Boolean(activeRun)} run={activeRun} onClose={() => setActiveRun(undefined)} />
      <ReplayComparisonModal open={Boolean(replayResult)} result={replayResult} onClose={() => setReplayResult(undefined)} />
    </>
  );
}

function replaySummary(result: MessageRerunResult) {
  const agent = agentLabel(result.target_agent ?? "");
  return `已重放为 ${agent}，新运行 #${result.agent_run_id ?? "-"}`;
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

function agentOptions() {
  return [
    { value: "support_ticket_agent", label: "客服工单知识" },
    { value: "sales_lead_agent", label: "销售线索跟进" },
    { value: "community_ops_agent", label: "私域社群运营" },
    { value: "recruiting_hr_agent", label: "招聘与入职" },
    { value: "report_agent", label: "报告 Agent" },
    { value: "manual_inbox_agent", label: "人工收件箱" },
    { value: "chat_agent", label: "旧版人工收件箱" }
  ];
}

function objectOptions() {
  return [
    { value: "ticket", label: "工单" },
    { value: "lead", label: "线索" },
    { value: "task", label: "任务" },
    { value: "candidate", label: "候选人" },
    { value: "knowledge_gap", label: "知识缺口" }
  ];
}
