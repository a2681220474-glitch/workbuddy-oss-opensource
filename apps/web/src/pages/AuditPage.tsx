import { Input, Select, Space, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { PageHeader } from "../components/PageHeader";
import { ReloadButton } from "../components/ReloadButton";
import { ResizableTable } from "../components/ResizableTable";
import { useAsyncData } from "../components/useAsyncData";
import type { AuditLog } from "../types";
import { entityKey, formatTime, shortText } from "../utils/format";
import { filterBySearch } from "../utils/search";

export function AuditPage() {
  const [search, setSearch] = useState("");
  const [scopeType, setScopeType] = useState<string>();
  const [actionType, setActionType] = useState<string>();

  const loadLogs = useCallback(() => api.getAuditLogs({ scope_type: scopeType, action_type: actionType, limit: 200 }), [actionType, scopeType]);
  const { data, error, loading, reload } = useAsyncData(loadLogs);

  const rows = useMemo(() => filterBySearch((data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "action_type",
    "scope_type",
    "status",
    "summary",
    "operator_name",
    "operator_username"
  ]) as unknown as AuditLog[], [data?.items, search]);

  const actionOptions = useMemo(() => {
    const values = new Set<string>();
    (data?.items ?? []).forEach((row) => {
      if (row.action_type) values.add(row.action_type);
    });
    return Array.from(values).sort().map((value) => ({ value, label: value }));
  }, [data?.items]);

  const scopeOptions = useMemo(() => {
    const values = new Set<string>();
    (data?.items ?? []).forEach((row) => {
      if (row.scope_type) values.add(row.scope_type);
    });
    return Array.from(values).sort().map((value) => ({ value, label: value }));
  }, [data?.items]);

  const columns = useMemo<ColumnsType<AuditLog>>(() => [
    { title: "时间", dataIndex: "created_at", width: 170, render: formatTime },
    {
      title: "操作人",
      width: 180,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{row.operator_user?.display_name ?? row.operator_name ?? "-"}</Typography.Text>
          <Typography.Text type="secondary">@{row.operator_user?.username ?? row.operator_username ?? "-"}</Typography.Text>
        </Space>
      )
    },
    { title: "动作", dataIndex: "action_type", width: 200 },
    { title: "范围", dataIndex: "scope_type", width: 120, render: (value) => <Tag>{value ?? "-"}</Tag> },
    { title: "状态", dataIndex: "status", width: 120, render: (value) => value ? <Tag color="blue">{value}</Tag> : "-" },
    { title: "摘要", dataIndex: "summary", width: 360, render: (value) => shortText(value, 120) },
    {
      title: "对象",
      width: 150,
      render: (_, row) => row.object_type && row.object_id ? `${row.object_type}#${row.object_id}` : "-"
    }
  ], []);

  return (
    <>
      <PageHeader
        title="操作审计"
        extra={(
          <Space wrap>
            <Select allowClear placeholder="范围" value={scopeType} onChange={setScopeType} style={{ width: 140 }} options={scopeOptions} />
            <Select allowClear placeholder="动作" value={actionType} onChange={setActionType} style={{ width: 220 }} options={actionOptions} />
            <Input.Search allowClear placeholder="搜索操作人/摘要/动作" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 260 }} />
            <ReloadButton loading={loading} onReload={reload} />
          </Space>
        )}
      />
      <ApiErrorAlert error={error} />
      <Typography.Paragraph type="secondary" className="table-ux-hint">
        审计总账统一记录成员处理、审批、发送、配置变更，便于回溯“是谁在什么时间做了什么”。
      </Typography.Paragraph>
      <ResizableTable
        size="small"
        rowKey={(row) => entityKey(row.id)}
        loading={loading}
        dataSource={rows}
        columns={columns}
        scroll={{ x: 1320 }}
        pagination={{ pageSize: 12, total: rows.length }}
      />
    </>
  );
}
