import { App as AntdApp, Button, Card, Descriptions, Input, List, Select, Space, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { PageHeader } from "../components/PageHeader";
import { ReloadButton } from "../components/ReloadButton";
import { ResizableTable } from "../components/ResizableTable";
import { useAsyncData } from "../components/useAsyncData";
import type { Report } from "../types";
import { formatTime, shortText } from "../utils/format";
import { hashTarget, isTargetId } from "../utils/navigation";
import { filterBySearch } from "../utils/search";
import { useHashId } from "../utils/useHashId";

const reportTypes = [
  { key: "operations_daily", label: "业务运营" },
  { key: "support_daily", label: "客服日报" },
  { key: "sales_daily", label: "销售日报" },
  { key: "community_daily", label: "社群日报" },
  { key: "recruiting_progress", label: "招聘进度" },
  { key: "knowledge_gap", label: "知识缺口" }
];

const columns: ColumnsType<Report> = [
  { title: "ID", dataIndex: "id", width: 80 },
  { title: "标题", dataIndex: "title", width: 180, render: (value) => value ?? "-" },
  { title: "类型", dataIndex: "report_type", width: 150, render: (value) => <Tag>{reportLabel(value)}</Tag> },
  { title: "摘要", dataIndex: "summary", width: 360, render: (value) => shortText(value, 120) },
  { title: "来源消息", dataIndex: "source_message_ids", width: 110, render: (value: Report["source_message_ids"]) => value?.length ?? 0 },
  { title: "创建时间", dataIndex: "created_at", width: 160, render: formatTime }
];

export function ReportsPage() {
  const { message } = AntdApp.useApp();
  const [reportType, setReportType] = useState<string>();
  const [search, setSearch] = useState("");
  const loadReports = useCallback(() => api.getReports(reportType), [reportType]);
  const { data, error, loading, reload } = useAsyncData(loadReports);
  const targetId = useHashId();
  const rows = useMemo(() => filterBySearch((data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "id",
    "report_type",
    "scope_type",
    "scope_id",
    "title",
    "summary",
    "metrics_json",
    "sections_json",
    "source_message_ids"
  ]) as unknown as Report[], [data?.items, search]);

  const generate = async (reportType: string) => {
    try {
      await api.generateReport(reportType);
      message.success(`${reportLabel(reportType)}已生成`);
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "报告生成失败");
    }
  };

  return (
    <>
      <PageHeader
        title="报告中心"
        extra={
          <Space wrap>
            <Select
              allowClear
              placeholder="报告类型"
              style={{ width: 150 }}
              value={reportType}
              options={reportTypes.map((item) => ({ label: item.label, value: item.key }))}
              onChange={setReportType}
            />
            <Input.Search allowClear placeholder="搜索标题/摘要/报告内容/来源消息" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 280 }} />
            {reportTypes.map((item) => (
              <Button key={item.key} size="small" onClick={() => generate(item.key)}>
                生成{item.label}
              </Button>
            ))}
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
        scroll={{ x: 1140 }}
        pagination={{ pageSize: 10, total: rows.length }}
        expandable={{
          expandedRowRender: (row) => <ReportDetail report={row} />
        }}
      />
    </>
  );
}

function ReportDetail({ report }: { report: Report }) {
  return (
    <Card size="small">
      <Descriptions size="small" column={3}>
        <Descriptions.Item label="消息">{String(report.metrics_json?.messages ?? 0)}</Descriptions.Item>
        <Descriptions.Item label="工单">{String(report.metrics_json?.tickets ?? 0)}</Descriptions.Item>
        <Descriptions.Item label="线索">{String(report.metrics_json?.leads ?? 0)}</Descriptions.Item>
        <Descriptions.Item label="任务">{String(report.metrics_json?.tasks ?? 0)}</Descriptions.Item>
        <Descriptions.Item label="候选人">{String(report.metrics_json?.candidates ?? 0)}</Descriptions.Item>
        <Descriptions.Item label="知识缺口">{String(report.metrics_json?.knowledge_gaps ?? 0)}</Descriptions.Item>
      </Descriptions>
      <Descriptions size="small" column={1}>
        <Descriptions.Item label="来源消息">
          <Space wrap>
            {(report.source_message_ids ?? []).slice(0, 10).map((id) => (
              <a key={String(id)} href={hashTarget("messages", id)}>消息#{id}</a>
            ))}
            {report.source_message_ids?.length ? null : "-"}
          </Space>
        </Descriptions.Item>
      </Descriptions>
      <List
        size="small"
        dataSource={report.sections_json ?? []}
        renderItem={(section) => (
          <List.Item>
            <List.Item.Meta
              title={section.title}
              description={(section.items ?? []).slice(0, 5).map((item, index) => <div key={`${section.title}-${index}`}>{item}</div>)}
            />
          </List.Item>
        )}
      />
    </Card>
  );
}

function reportLabel(value?: string) {
  return reportTypes.find((item) => item.key === value)?.label ?? value ?? "-";
}
