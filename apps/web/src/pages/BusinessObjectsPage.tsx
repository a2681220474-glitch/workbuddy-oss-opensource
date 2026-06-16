import { Button, Card, Col, Input, Row, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { BusinessObjectDetailDrawer } from "../components/BusinessObjectDetailDrawer";
import { PageHeader } from "../components/PageHeader";
import { ReloadButton } from "../components/ReloadButton";
import { useAsyncData } from "../components/useAsyncData";
import type { BusinessObjectCenter, EntityId } from "../types";
import { entityKey, formatTime } from "../utils/format";
import { hashTarget } from "../utils/navigation";
import { filterBySearch } from "../utils/search";

const objectMeta: Array<{ key: string; label: string; target: string }> = [
  { key: "tickets", label: "Ticket 工单", target: "tickets" },
  { key: "leads", label: "Lead 线索", target: "leads" },
  { key: "tasks", label: "Task 任务", target: "tasks" },
  { key: "candidates", label: "Candidate 候选人", target: "candidates" },
  { key: "knowledge_gaps", label: "KnowledgeGap", target: "knowledge" },
  { key: "knowledge_items", label: "KnowledgeItem", target: "knowledge" },
  { key: "reports", label: "Report 报告", target: "reports" },
  { key: "pending_approvals", label: "待审批", target: "approvals" }
];

interface RecentRow {
  type: string;
  object_type?: string;
  id?: EntityId;
  label?: string;
  created_at?: string;
}

export function BusinessObjectsPage() {
  const { data, error, loading, reload } = useAsyncData(api.getBusinessObjects);
  const [search, setSearch] = useState("");
  const [detailObject, setDetailObject] = useState<RecentRow>();
  const rows = useMemo(() => filterBySearch(flattenRecent(data) as unknown as Record<string, unknown>[], search, [
    "type",
    "id",
    "label",
    "created_at"
  ]) as unknown as RecentRow[], [data, search]);
  const recentColumns: ColumnsType<RecentRow> = [
    { title: "对象", dataIndex: "type", width: 150 },
    { title: "ID", dataIndex: "id", width: 90 },
    {
      title: "名称",
      dataIndex: "label",
      render: (value, row) => row.id ? <a href={targetFor(row)}>{value}</a> : value ?? "-"
    },
    { title: "创建时间", dataIndex: "created_at", width: 170, render: formatTime },
    {
      title: "处理闭环",
      width: 110,
      render: (_, row) => row.object_type && row.id ? <Button size="small" onClick={() => setDetailObject(row)}>详情</Button> : "-"
    }
  ];

  return (
    <>
      <PageHeader title="业务对象中心" extra={<ReloadButton loading={loading} onReload={reload} />} />
      <ApiErrorAlert error={error} />
      <Row gutter={[16, 16]}>
        {objectMeta.map((item) => (
          <Col xs={12} md={8} xl={6} key={item.key}>
            <Card size="small">
              <Typography.Text type="secondary">{item.label}</Typography.Text>
              <Typography.Title level={3}>{data?.counts?.[item.key] ?? 0}</Typography.Title>
              <a href={hashTarget(item.target as Parameters<typeof hashTarget>[0])}>查看列表</a>
            </Card>
          </Col>
        ))}
      </Row>
      <Card title="最近业务对象" className="section-card" extra={(
        <Input.Search
          allowClear
          placeholder="搜索对象类型/名称/ID"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          style={{ width: 260 }}
        />
      )}>
        <Table
          size="small"
          loading={loading}
          rowKey={(row) => `${row.type}-${entityKey(row.id)}`}
          dataSource={rows}
          columns={recentColumns}
          pagination={{ pageSize: 12 }}
        />
      </Card>
      <BusinessObjectDetailDrawer
        objectType={detailObject?.object_type}
        objectId={detailObject?.id}
        open={Boolean(detailObject)}
        onClose={() => setDetailObject(undefined)}
        onChanged={reload}
      />
    </>
  );
}

function flattenRecent(data?: BusinessObjectCenter): RecentRow[] {
  const recent = data?.recent ?? {};
  return Object.entries(recent).flatMap(([type, rows]) =>
    rows.map((row) => ({
      type: typeLabel(type),
      object_type: singularObjectType(type),
      ...row
    }))
  );
}

function typeLabel(type: string) {
  const labels: Record<string, string> = {
    tickets: "工单",
    leads: "线索",
    tasks: "任务",
    candidates: "候选人",
    knowledge_gaps: "知识缺口",
    reports: "报告"
  };
  return labels[type] ?? type;
}

function singularObjectType(type: string) {
  const labels: Record<string, string> = {
    tickets: "ticket",
    leads: "lead",
    tasks: "task",
    candidates: "candidate",
    knowledge_gaps: "knowledge_gap",
    knowledge_items: "knowledge_item",
    reports: "report"
  };
  return labels[type] ?? type;
}

function targetFor(row: RecentRow) {
  const targetByType: Record<string, Parameters<typeof hashTarget>[0]> = {
    工单: "tickets",
    线索: "leads",
    任务: "tasks",
    候选人: "candidates",
    知识缺口: "knowledge",
    报告: "reports"
  };
  return hashTarget(targetByType[row.type] ?? "objects", row.id);
}
