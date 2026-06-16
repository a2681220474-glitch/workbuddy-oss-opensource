import { App as AntdApp, Button, Checkbox, Input, Select, Space, Tag, Typography } from "antd";
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
import type { FollowupTask } from "../types";
import { entityKey, formatTime, shortText } from "../utils/format";
import { isTargetId } from "../utils/navigation";
import { filterBySearch } from "../utils/search";
import { useHashId } from "../utils/useHashId";

export function TasksPage() {
  const { message } = AntdApp.useApp();
  const targetId = useHashId();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string>();
  const [assignee, setAssignee] = useState<string>();
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [detailTask, setDetailTask] = useState<FollowupTask>();
  const loadTasks = useCallback(() => api.getTasks({ status, assignee_name: assignee, overdue: overdueOnly || undefined }), [assignee, overdueOnly, status]);
  const { data, error, loading, reload } = useAsyncData(loadTasks);
  const rows = useMemo(() => filterBySearch((data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "id",
    "title",
    "task_type",
    "status",
    "priority",
    "related_object_type",
    "related_object_id",
    "assignee_name",
    "due_hint",
    "due_at",
    "is_overdue",
    "summary",
    "source_message_id"
  ]) as unknown as FollowupTask[], [data?.items, search]);
  const assigneeOptions = useMemo(() => {
    const values = new Set<string>();
    (data?.items ?? []).forEach((task) => {
      if (task.assignee_name) values.add(task.assignee_name);
    });
    return Array.from(values).map((value) => ({ value, label: value }));
  }, [data?.items]);

  const updateTaskStatus = async (task: FollowupTask, nextStatus: string) => {
    try {
      await api.updateTask(task.id, { status: nextStatus });
      message.success("任务状态已更新");
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "更新任务失败");
    }
  };

  const columns = useMemo<ColumnsType<FollowupTask>>(() => [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "任务", dataIndex: "title", width: 260, render: (value) => shortText(value, 90) },
    { title: "状态", dataIndex: "status", width: 110, render: (value) => <StatusTag value={value} /> },
    { title: "优先级", dataIndex: "priority", width: 110, render: (value) => <StatusTag value={value} /> },
    {
      title: "负责人",
      dataIndex: "assignee_name",
      width: 180,
      render: (_, row) => row.assignee_user?.display_name
        ? `${row.assignee_user.display_name} (@${row.assignee_user.username ?? "-"})`
        : row.assignee_name ?? "-"
    },
    { title: "关联对象", width: 130, render: (_, row) => relatedLabel(row) },
    { title: "时间提示", dataIndex: "due_hint", width: 140, render: (value) => value ?? "-" },
    { title: "截止时间", dataIndex: "due_at", width: 160, render: (value, row) => dueAtLabel(value, row) },
    { title: "摘要", dataIndex: "summary", width: 260, render: (value) => shortText(value, 80) },
    { title: "创建时间", dataIndex: "created_at", width: 160, render: formatTime },
    {
      title: "处理",
      width: 260,
      fixed: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => setDetailTask(row)}>详情</Button>
          <Button size="small" disabled={row.status === "in_progress"} onClick={() => updateTaskStatus(row, "in_progress")}>处理中</Button>
          <Button size="small" disabled={row.status === "done"} onClick={() => updateTaskStatus(row, "done")}>完成</Button>
        </Space>
      )
    }
  ], [reload]);

  return (
    <>
      <PageHeader title="跟进任务" extra={
        <Space wrap>
          <Select allowClear placeholder="状态" value={status} onChange={setStatus} style={{ width: 130 }} options={[
            { value: "todo", label: "待处理" },
            { value: "in_progress", label: "处理中" },
            { value: "waiting", label: "等待中" },
            { value: "done", label: "已完成" },
            { value: "cancelled", label: "已取消" }
          ]} />
          <Select allowClear placeholder="负责人" value={assignee} onChange={setAssignee} style={{ width: 140 }} options={assigneeOptions} />
          <Checkbox checked={overdueOnly} onChange={(event) => setOverdueOnly(event.target.checked)}>只看逾期</Checkbox>
          <Input.Search allowClear placeholder="搜索任务/摘要/对象/负责人" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 260 }} />
          <ReloadButton loading={loading} onReload={reload} />
        </Space>
      } />
      <ApiErrorAlert error={error} />
      <Typography.Paragraph type="secondary" className="table-ux-hint">
        表格可横向滚动；按住表头右侧边缘可调整列宽。
      </Typography.Paragraph>
      <ResizableTable
        size="small"
        loading={loading}
        rowKey={(row) => entityKey(row.id)}
        rowClassName={(row) => isTargetId(row.id, targetId) ? "row-highlight" : ""}
        dataSource={rows}
        columns={columns}
        scroll={{ x: 1790 }}
        pagination={{ pageSize: 12, total: rows.length }}
      />
      <BusinessObjectDetailDrawer
        objectType="task"
        objectId={detailTask?.id}
        open={Boolean(detailTask)}
        onClose={() => setDetailTask(undefined)}
        onChanged={reload}
      />
    </>
  );
}

function dueAtLabel(value: string | undefined, row: FollowupTask) {
  if (!value) return "-";
  return (
    <Space>
      <Typography.Text>{formatTime(value)}</Typography.Text>
      {row.is_overdue ? <Tag color="red">逾期</Tag> : null}
    </Space>
  );
}

function relatedLabel(row: FollowupTask) {
  if (!row.related_object_type) return "-";
  const typeLabel: Record<string, string> = {
    lead: "线索",
    ticket: "工单",
    task: "任务"
  };
  return `${typeLabel[row.related_object_type] ?? row.related_object_type}#${row.related_object_id ?? "-"}`;
}
