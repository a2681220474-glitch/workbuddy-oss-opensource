import { App as AntdApp, Button, Card, Col, Descriptions, Input, Modal, Progress, Row, Select, Space, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { BusinessObjectDetailDrawer } from "../components/BusinessObjectDetailDrawer";
import { PageHeader } from "../components/PageHeader";
import { ReloadButton } from "../components/ReloadButton";
import { ResizableTable } from "../components/ResizableTable";
import { StatusTag } from "../components/StatusTag";
import { useAsyncData } from "../components/useAsyncData";
import type { Lead, LeadDraft, LeadScorecard } from "../types";
import { formatTime } from "../utils/format";
import { isTargetId } from "../utils/navigation";
import { filterBySearch } from "../utils/search";
import { useHashId } from "../utils/useHashId";

const fallbackStageOptions = [
  { value: "new", label: "新线索", next: ["contacted", "proposal", "lost"] },
  { value: "potential", label: "潜在线索", next: ["contacted", "proposal", "lost"] },
  { value: "qualified", label: "已确认", next: ["contacted", "proposal", "negotiation", "lost"] },
  { value: "contacted", label: "已联系", next: ["proposal", "negotiation", "lost"] },
  { value: "proposal", label: "已发方案", next: ["negotiation", "won", "lost"] },
  { value: "negotiation", label: "谈判中", next: ["won", "lost", "proposal"] },
  { value: "won", label: "赢单", next: [] },
  { value: "lost", label: "输单", next: ["contacted"] }
];

const priorityOptions = [
  { value: "critical", label: "严重" },
  { value: "high", label: "高" },
  { value: "medium", label: "中" },
  { value: "low", label: "低" }
];

export function LeadsPage() {
  const { message } = AntdApp.useApp();
  const [stage, setStage] = useState<string>();
  const [priority, setPriority] = useState<string>();
  const [activeLead, setActiveLead] = useState<Lead>();
  const [scorecard, setScorecard] = useState<LeadScorecard>();
  const [draft, setDraft] = useState<LeadDraft>();
  const [draftText, setDraftText] = useState("");
  const [nextStepText, setNextStepText] = useState("");
  const [detailLead, setDetailLead] = useState<Lead>();
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [search, setSearch] = useState("");
  const loadLeads = useCallback(() => api.getLeads({ stage, priority }), [priority, stage]);
  const { data, error, loading, reload } = useAsyncData(loadLeads);
  const workflow = useAsyncData(api.getLeadWorkflow);
  const targetId = useHashId();
  const stageOptions = workflow.data?.stages?.length ? workflow.data.stages : fallbackStageOptions;
  const transitions = workflow.data?.transitions ?? Object.fromEntries(fallbackStageOptions.map((item) => [item.value, item.next]));
  const stageLabels = useMemo(() => Object.fromEntries(stageOptions.map((item) => [item.value, item.label])), [stageOptions]);
  const rows = useMemo(() => filterBySearch((data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "id",
    "customer_name",
    "company",
    "interest",
    "stage",
    "score",
    "priority",
    "next_step",
    "summary",
    "source_message_id"
  ]) as unknown as Lead[], [data?.items, search]);

  const salesSummary = useMemo(() => {
    const leads = rows;
    return {
      highIntent: leads.filter((lead) => (lead.score ?? 0) >= 70).length,
      needFollowup: leads.filter((lead) => ["new", "potential", "qualified", "contacted"].includes(lead.stage ?? "")).length,
      stalled: leads.filter((lead) => isStalledLead(lead)).length,
      proposal: leads.filter((lead) => lead.stage === "proposal").length,
      negotiation: leads.filter((lead) => lead.stage === "negotiation").length,
      won: leads.filter((lead) => lead.stage === "won").length
    };
  }, [rows]);

  useEffect(() => {
    setDraftText(draft?.draft_content ?? "");
    setNextStepText(draft?.next_step ?? "");
  }, [draft]);

  const updateLeadStage = async (lead: Lead, nextStage: string) => {
    try {
      await api.updateLead(lead.id, { stage: nextStage });
      message.success("线索阶段已更新");
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "更新线索失败");
    }
  };

  const openSalesAssistant = async (lead: Lead) => {
    setActiveLead(lead);
    setScorecard(undefined);
    setDraft(undefined);
    setAssistantLoading(true);
    try {
      const [nextScorecard, nextDraft] = await Promise.all([
        api.getLeadScorecard(lead.id),
        api.getLeadDraft(lead.id)
      ]);
      setScorecard(nextScorecard);
      setDraft(nextDraft);
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "销售助手加载失败");
    } finally {
      setAssistantLoading(false);
    }
  };

  const createApprovalDraft = async () => {
    if (!activeLead) return;
    try {
      await api.createLeadApprovalDraft(activeLead.id, {
        draft_content: draftText,
        next_step: nextStepText
      });
      message.success("销售回复草稿已进入审批队列");
      setActiveLead(undefined);
      setScorecard(undefined);
      setDraft(undefined);
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "生成审批草稿失败");
    }
  };

  const columns = useMemo<ColumnsType<Lead>>(() => [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "客户", dataIndex: "customer_name", width: 130, render: (value) => value ?? "未知客户" },
    { title: "公司", dataIndex: "company", width: 150, render: (value) => value ?? "-" },
    {
      title: "兴趣点",
      dataIndex: "interest",
      width: 220,
      render: (value) => (
        <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 200 }}>
          {value ?? "-"}
        </Typography.Text>
      )
    },
    { title: "阶段", dataIndex: "stage", width: 120, render: (value) => <StatusTag value={value} /> },
    {
      title: "评分",
      dataIndex: "score",
      width: 130,
      render: (value) => <Progress percent={Number(value ?? 0)} size="small" />
    },
    { title: "优先级", dataIndex: "priority", width: 100, render: (value) => <StatusTag value={value} /> },
    {
      title: "下一步",
      dataIndex: "next_step",
      width: 260,
      render: (value) => (
        <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 240 }}>
          {value || "待补充"}
        </Typography.Text>
      )
    },
    { title: "创建时间", dataIndex: "created_at", width: 160, render: formatTime },
    {
      title: "推进",
      width: 230,
      fixed: "right",
      render: (_, row) => {
        const nextStages = transitions[row.stage ?? ""] ?? [];
        return (
          <Space size={4} wrap>
            {nextStages.length ? nextStages.map((next) => (
              <Button key={next} size="small" onClick={() => updateLeadStage(row, next)}>
                {stageLabels[next] ?? next}
              </Button>
            )) : <Typography.Text type="secondary">已结束</Typography.Text>}
          </Space>
        );
      }
    },
    {
      title: "销售助手",
      width: 180,
      fixed: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => setDetailLead(row)}>详情</Button>
          <Button size="small" onClick={() => openSalesAssistant(row)}>评分/话术</Button>
        </Space>
      )
    }
  ], [stageLabels, transitions]);

  return (
    <>
      <PageHeader
        title="销售线索"
        extra={
          <Space wrap>
            <Select allowClear placeholder="阶段" value={stage} onChange={setStage} style={{ width: 130 }} options={stageOptions} />
            <Select allowClear placeholder="优先级" value={priority} onChange={setPriority} style={{ width: 120 }} options={priorityOptions} />
            <Input.Search allowClear placeholder="搜索客户/公司/兴趣点/下一步" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 260 }} />
            <ReloadButton loading={loading} onReload={reload} />
          </Space>
        }
      />
      <ApiErrorAlert error={error} />
      <Row gutter={[12, 12]} className="dashboard-lower">
        {[
          { label: "高意向", value: salesSummary.highIntent, status: "high" },
          { label: "今日应跟进", value: salesSummary.needFollowup, status: "todo" },
          { label: "停滞线索", value: salesSummary.stalled, status: "urgent" },
          { label: "已发方案", value: salesSummary.proposal, status: "proposal" },
          { label: "谈判中", value: salesSummary.negotiation, status: "negotiation" },
          { label: "赢单", value: salesSummary.won, status: "won" }
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
        scroll={{ x: 1560 }}
        pagination={{ pageSize: 12, total: rows.length }}
      />
      <BusinessObjectDetailDrawer
        objectType="lead"
        objectId={detailLead?.id}
        open={Boolean(detailLead)}
        onClose={() => setDetailLead(undefined)}
        onChanged={reload}
      />
      <Modal
        title="销售线索助手"
        open={Boolean(activeLead)}
        onCancel={() => setActiveLead(undefined)}
        width={760}
        footer={[
          <Button key="cancel" onClick={() => setActiveLead(undefined)}>取消</Button>,
          <Button key="approval" type="primary" loading={assistantLoading} onClick={createApprovalDraft}>送入审批队列</Button>
        ]}
      >
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Descriptions size="small" column={2}>
            <Descriptions.Item label="客户">{activeLead?.customer_name}</Descriptions.Item>
            <Descriptions.Item label="阶段"><StatusTag value={activeLead?.stage} /></Descriptions.Item>
            <Descriptions.Item label="兴趣点">{activeLead?.interest}</Descriptions.Item>
            <Descriptions.Item label="推荐阶段"><StatusTag value={draft?.recommended_stage} /></Descriptions.Item>
          </Descriptions>
          <Card size="small" title="评分拆解" loading={assistantLoading}>
            <Row gutter={[12, 12]}>
              {Object.entries(scorecard?.dimensions ?? {}).map(([key, value]) => (
                <Col xs={12} md={8} key={key}>
                  <Typography.Text type="secondary">{scoreLabel(key)}</Typography.Text>
                  <div className="metric-number">{value}</div>
                </Col>
              ))}
            </Row>
            <Space direction="vertical" size={4} style={{ marginTop: 12 }}>
              {(scorecard?.reasons ?? []).map((reason) => <Typography.Text key={reason}>{reason}</Typography.Text>)}
            </Space>
          </Card>
          <div>
            <Typography.Text strong>下一步动作</Typography.Text>
            <Input value={nextStepText} onChange={(event) => setNextStepText(event.target.value)} />
          </div>
          <div>
            <Typography.Text strong>外发回复草稿</Typography.Text>
            <Input.TextArea rows={4} value={draftText} onChange={(event) => setDraftText(event.target.value)} />
          </div>
        </Space>
      </Modal>
    </>
  );
}

function scoreLabel(key: string) {
  const labels: Record<string, string> = {
    budget: "预算",
    timing: "时机",
    need: "需求",
    decision_role: "决策人",
    risk: "风险"
  };
  return labels[key] ?? key;
}

function isStalledLead(lead: Lead) {
  if (["proposal", "negotiation", "won", "lost"].includes(lead.stage ?? "")) return false;
  if (!lead.updated_at) return false;
  return Date.now() - new Date(lead.updated_at).getTime() >= 24 * 60 * 60 * 1000;
}
