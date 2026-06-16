import { App as AntdApp, Button, Card, Checkbox, Col, Descriptions, Input, Modal, Progress, Row, Select, Space, Tabs, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { BusinessObjectDetailDrawer } from "../components/BusinessObjectDetailDrawer";
import { PageHeader } from "../components/PageHeader";
import { ReloadButton } from "../components/ReloadButton";
import { ResizableTable } from "../components/ResizableTable";
import { StatusTag } from "../components/StatusTag";
import { useAsyncData } from "../components/useAsyncData";
import type { Candidate, CandidateMatchAnalysis } from "../types";
import { formatTime, shortText } from "../utils/format";
import { hashTarget, isTargetId } from "../utils/navigation";
import { filterBySearch } from "../utils/search";
import { useHashId } from "../utils/useHashId";

const fallbackStageOptions = [
  { value: "screening", label: "筛选", next: ["interview", "rejected"] },
  { value: "interview", label: "面试", next: ["offer", "rejected", "screening"] },
  { value: "offer", label: "Offer", next: ["onboarding", "rejected", "interview"] },
  { value: "onboarding", label: "入职", next: ["hired", "rejected"] },
  { value: "hired", label: "已入职", next: [] },
  { value: "rejected", label: "淘汰", next: ["screening"] }
];

export function CandidatesPage() {
  const { message } = AntdApp.useApp();
  const [stage, setStage] = useState<string>();
  const [activeCandidate, setActiveCandidate] = useState<Candidate>();
  const [detailCandidate, setDetailCandidate] = useState<Candidate>();
  const [analysis, setAnalysis] = useState<CandidateMatchAnalysis>();
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [search, setSearch] = useState("");
  const loadCandidates = useCallback(() => api.getCandidates({ stage }), [stage]);
  const { data, error, loading, reload } = useAsyncData(loadCandidates);
  const workflow = useAsyncData(api.getCandidateWorkflow);
  const targetId = useHashId();
  const stageOptions = workflow.data?.stages?.length ? workflow.data.stages : fallbackStageOptions;
  const transitions = workflow.data?.transitions ?? Object.fromEntries(fallbackStageOptions.map((item) => [item.value, item.next]));
  const stageLabels = useMemo(() => Object.fromEntries(stageOptions.map((item) => [item.value, item.label])), [stageOptions]);
  const rows = useMemo(() => filterBySearch((data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "id",
    "name",
    "role",
    "stage",
    "match_score",
    "summary",
    "source_message_id",
    "interview_questions_json",
    "onboarding_checklist_json"
  ]) as unknown as Candidate[], [data?.items, search]);

  const summary = useMemo(() => {
    const candidates = rows;
    return {
      highMatch: candidates.filter((candidate) => (candidate.match_score ?? 0) >= 70).length,
      screening: candidates.filter((candidate) => candidate.stage === "screening").length,
      interview: candidates.filter((candidate) => candidate.stage === "interview").length,
      offer: candidates.filter((candidate) => candidate.stage === "offer").length,
      onboarding: candidates.filter((candidate) => candidate.stage === "onboarding").length,
      risk: candidates.filter((candidate) => (candidate.match_score ?? 0) < 60 || candidate.stage === "rejected").length
    };
  }, [rows]);

  const updateCandidateStage = async (candidate: Candidate, nextStage: string) => {
    try {
      await api.updateCandidate(candidate.id, { stage: nextStage });
      message.success("候选人阶段已更新");
      await reload();
      if (activeCandidate?.id === candidate.id) {
        await openAssistant({ ...candidate, stage: nextStage });
      }
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "更新候选人失败");
    }
  };

  const openAssistant = async (candidate: Candidate) => {
    setActiveCandidate(candidate);
    setAnalysis(undefined);
    setAnalysisLoading(true);
    try {
      setAnalysis(await api.getCandidateMatchAnalysis(candidate.id));
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "候选人分析加载失败");
    } finally {
      setAnalysisLoading(false);
    }
  };

  const updateChecklist = async (itemIndex: number, completed: boolean) => {
    if (!activeCandidate) return;
    try {
      const updated = await api.updateCandidateChecklistItem(activeCandidate.id, itemIndex, completed);
      setActiveCandidate(updated);
      setAnalysis(await api.getCandidateMatchAnalysis(activeCandidate.id));
      message.success(completed ? "入职事项已完成" : "入职事项已恢复待办");
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "更新入职清单失败");
    }
  };

  const columns = useMemo<ColumnsType<Candidate>>(() => [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "候选人", dataIndex: "name", width: 140, render: (value) => value ?? "未知候选人" },
    {
      title: "岗位",
      dataIndex: "role",
      width: 180,
      render: (value) => (
        <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 160 }}>
          {value ?? "待确认岗位"}
        </Typography.Text>
      )
    },
    { title: "阶段", dataIndex: "stage", width: 120, render: (value) => <StatusTag value={value} /> },
    {
      title: "匹配分",
      dataIndex: "match_score",
      width: 130,
      render: (value) => <Progress percent={Number(value ?? 0)} size="small" />
    },
    {
      title: "面试题",
      dataIndex: "interview_questions_json",
      width: 100,
      render: (items: Candidate["interview_questions_json"]) => `${items?.length ?? 0} 条`
    },
    {
      title: "入职清单",
      dataIndex: "onboarding_checklist_json",
      width: 110,
      render: (items: Candidate["onboarding_checklist_json"]) => {
        const done = (items ?? []).filter((item) => item.completed === true || item.status === "done").length;
        return `${done}/${items?.length ?? 0}`;
      }
    },
    { title: "摘要", dataIndex: "summary", width: 280, render: (value) => shortText(value, 90) },
    {
      title: "来源消息",
      dataIndex: "source_message_id",
      width: 120,
      render: (value) => value ? <a href={hashTarget("messages", value)}>消息#{value}</a> : "-"
    },
    { title: "创建时间", dataIndex: "created_at", width: 160, render: formatTime },
    {
      title: "推进",
      width: 220,
      fixed: "right",
      render: (_, row) => {
        const nextStages = transitions[row.stage ?? ""] ?? [];
        return (
          <Space size={4} wrap>
            {nextStages.length ? nextStages.map((next) => (
              <Button key={next} size="small" onClick={() => updateCandidateStage(row, next)}>
                {stageLabels[next] ?? next}
              </Button>
            )) : <Typography.Text type="secondary">已结束</Typography.Text>}
          </Space>
        );
      }
    },
    {
      title: "助手",
      width: 190,
      fixed: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => setDetailCandidate(row)}>详情</Button>
          <Button size="small" onClick={() => openAssistant(row)}>匹配/入职</Button>
        </Space>
      )
    }
  ], [stageLabels, transitions]);

  return (
    <>
      <PageHeader
        title="候选人与入职"
        extra={
          <Space wrap>
            <Select allowClear placeholder="阶段" value={stage} onChange={setStage} style={{ width: 130 }} options={stageOptions} />
            <Input.Search allowClear placeholder="搜索候选人/岗位/摘要/面试题" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 280 }} />
            <ReloadButton loading={loading} onReload={reload} />
          </Space>
        }
      />
      <ApiErrorAlert error={error} />
      <Row gutter={[12, 12]} className="dashboard-lower">
        {[
          { label: "高匹配", value: summary.highMatch, status: "high" },
          { label: "筛选中", value: summary.screening, status: "screening" },
          { label: "待面试", value: summary.interview, status: "interview" },
          { label: "Offer", value: summary.offer, status: "offer" },
          { label: "入职准备", value: summary.onboarding, status: "onboarding" },
          { label: "风险/淘汰", value: summary.risk, status: "urgent" }
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
        scroll={{ x: 1610 }}
        pagination={{ pageSize: 12, total: rows.length }}
      />
      <BusinessObjectDetailDrawer
        objectType="candidate"
        objectId={detailCandidate?.id}
        open={Boolean(detailCandidate)}
        onClose={() => setDetailCandidate(undefined)}
        onChanged={reload}
      />
      <Modal
        title="招聘与入职助手"
        open={Boolean(activeCandidate)}
        onCancel={() => setActiveCandidate(undefined)}
        width={820}
        footer={<Button onClick={() => setActiveCandidate(undefined)}>关闭</Button>}
      >
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Descriptions size="small" column={2}>
            <Descriptions.Item label="候选人">{activeCandidate?.name}</Descriptions.Item>
            <Descriptions.Item label="岗位">{activeCandidate?.role}</Descriptions.Item>
            <Descriptions.Item label="阶段"><StatusTag value={activeCandidate?.stage} /></Descriptions.Item>
            <Descriptions.Item label="匹配分">{activeCandidate?.match_score}</Descriptions.Item>
            <Descriptions.Item label="建议">{analysis?.recommendation ?? "-"}</Descriptions.Item>
          </Descriptions>
          <Tabs
            items={[
              {
                key: "match",
                label: "匹配分析",
                children: (
                  <Card size="small" loading={analysisLoading}>
                    <Row gutter={[12, 12]}>
                      {Object.entries(analysis?.dimensions ?? {}).map(([key, value]) => (
                        <Col xs={12} md={8} key={key}>
                          <Typography.Text type="secondary">{dimensionLabel(key)}</Typography.Text>
                          <div className="metric-number">{value}</div>
                        </Col>
                      ))}
                    </Row>
                    <AnalysisList title="优势" items={analysis?.strengths} />
                    <AnalysisList title="风险" items={analysis?.risks} />
                    <AnalysisList title="缺口" items={analysis?.gaps} />
                  </Card>
                )
              },
              {
                key: "questions",
                label: "面试问题",
                children: (
                  <Space direction="vertical" size={8} style={{ width: "100%" }}>
                    {(analysis?.interview_questions ?? []).map((item, index) => (
                      <Card key={`${String(item.question)}-${index}`} size="small">
                        <Space direction="vertical" size={4}>
                          <Space>
                            <StatusTag value={String(item.category ?? "question")} />
                            <Typography.Text strong>{String(item.question ?? item.title ?? "-")}</Typography.Text>
                          </Space>
                          <Typography.Text type="secondary">{String(item.purpose ?? "-")}</Typography.Text>
                          {item.signal ? <Typography.Text type="secondary">观察信号：{String(item.signal)}</Typography.Text> : null}
                        </Space>
                      </Card>
                    ))}
                  </Space>
                )
              },
              {
                key: "onboarding",
                label: "入职 Checklist",
                children: (
                  <Space direction="vertical" size={8} style={{ width: "100%" }}>
                    {(analysis?.onboarding_checklist ?? []).map((item, index) => {
                      const completed = item.completed === true || item.status === "done";
                      return (
                        <Card key={`${String(item.title)}-${index}`} size="small">
                          <Space align="start">
                            <Checkbox checked={completed} onChange={(event) => updateChecklist(index, event.target.checked)} />
                            <Space direction="vertical" size={2}>
                              <Typography.Text delete={completed}>{String(item.title ?? "-")}</Typography.Text>
                              <Typography.Text type="secondary">{String(item.owner ?? "HR")} / {String(item.phase ?? "onboarding")}</Typography.Text>
                            </Space>
                          </Space>
                        </Card>
                      );
                    })}
                  </Space>
                )
              }
            ]}
          />
        </Space>
      </Modal>
    </>
  );
}

function dimensionLabel(key: string) {
  const labels: Record<string, string> = {
    role_fit: "岗位匹配",
    experience_depth: "经验深度",
    collaboration: "协作推进",
    motivation: "动机匹配",
    risk: "风险可控"
  };
  return labels[key] ?? key;
}

function AnalysisList({ title, items }: { title: string; items?: string[] }) {
  return (
    <Space direction="vertical" size={4} style={{ width: "100%", marginTop: 12 }}>
      <Typography.Text strong>{title}</Typography.Text>
      {(items?.length ? items : ["暂无"]).map((item) => (
        <Typography.Text key={item} type={item === "暂无" ? "secondary" : undefined}>{item}</Typography.Text>
      ))}
    </Space>
  );
}
