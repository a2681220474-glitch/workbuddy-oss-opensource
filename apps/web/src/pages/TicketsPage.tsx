import dayjs from "dayjs";
import { App as AntdApp, Button, Card, Col, Descriptions, Input, InputNumber, Modal, Row, Select, Space, Tooltip, Typography } from "antd";
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
import type { Ticket, TicketKnowledgeSuggestion } from "../types";
import { formatTime, shortText } from "../utils/format";
import { hashTarget, isTargetId } from "../utils/navigation";
import { filterBySearch } from "../utils/search";
import { useHashId } from "../utils/useHashId";

export function TicketsPage() {
  const { message } = AntdApp.useApp();
  const [status, setStatus] = useState<string>();
  const [priority, setPriority] = useState<string>();
  const [slaDraft, setSlaDraft] = useState<Record<string, number>>({});
  const [knowledgeTicket, setKnowledgeTicket] = useState<Ticket>();
  const [knowledgeSuggestion, setKnowledgeSuggestion] = useState<TicketKnowledgeSuggestion>();
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [detailTicket, setDetailTicket] = useState<Ticket>();
  const [search, setSearch] = useState("");
  const loadTickets = useCallback(() => api.getTickets({ status, priority }), [priority, status]);
  const { data, error, loading, reload } = useAsyncData(loadTickets);
  const workflow = useAsyncData(api.getTicketWorkflow);
  const targetId = useHashId();
  const transitions = workflow.data?.transitions ?? {};
  const statusLabels = useMemo(() => {
    return Object.fromEntries((workflow.data?.statuses ?? []).map((item) => [item.value, item.label]));
  }, [workflow.data?.statuses]);
  const slaHours = workflow.data?.sla_hours ?? { critical: 2, high: 4, medium: 24, low: 48 };
  const rows = useMemo(() => filterBySearch((data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "id",
    "title",
    "customer_name",
    "category",
    "status",
    "priority",
    "summary",
    "source_message_id"
  ]) as unknown as Ticket[], [data?.items, search]);

  useEffect(() => {
    setSlaDraft(slaHours);
  }, [slaHours.critical, slaHours.high, slaHours.medium, slaHours.low]);

  const updateTicket = async (ticket: Ticket, nextStatus: string) => {
    try {
      await api.updateTicket(ticket.id, { status: nextStatus });
      message.success("工单状态已更新");
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "更新工单失败");
    }
  };

  const saveSlaConfig = async () => {
    try {
      await api.updateSlaConfig(slaDraft);
      message.success("SLA 配置已更新");
      await workflow.reload();
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "更新 SLA 配置失败");
    }
  };

  const openKnowledge = async (ticket: Ticket) => {
    setKnowledgeTicket(ticket);
    setKnowledgeSuggestion(undefined);
    setKnowledgeLoading(true);
    try {
      const suggestion = await api.getTicketKnowledgeSuggestions(ticket.id);
      setKnowledgeSuggestion(suggestion);
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "知识命中检查失败");
    } finally {
      setKnowledgeLoading(false);
    }
  };

  const createKnowledge = async (mode: "gap" | "item") => {
    if (!knowledgeTicket) return;
    try {
      await api.createKnowledgeFromTicket(knowledgeTicket.id, {
        mode,
        category: knowledgeTicket.category || "support",
        answer: knowledgeSuggestion?.suggested_answer,
        publish: mode === "item"
      });
      message.success(mode === "item" ? "已沉淀为知识条目" : "已创建知识缺口");
      setKnowledgeTicket(undefined);
      setKnowledgeSuggestion(undefined);
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "知识沉淀失败");
    }
  };

  const columns = useMemo<ColumnsType<Ticket>>(() => [
    { title: "ID", dataIndex: "id", width: 80 },
    {
      title: "标题",
      dataIndex: "title",
      width: 320,
      render: (value, row) => (
        <Typography.Text ellipsis={{ tooltip: value ?? row.summary }} style={{ maxWidth: 300 }}>
          {value ?? shortText(row.summary, 60)}
        </Typography.Text>
      )
    },
    { title: "客户", dataIndex: "customer_name", width: 140, render: (value) => value ?? "-" },
    { title: "优先级", dataIndex: "priority", width: 110, render: (value) => <StatusTag value={value} /> },
    { title: "状态", dataIndex: "status", width: 120, render: (value) => <StatusTag value={value} /> },
    { title: "SLA", width: 120, render: (_, row) => slaLabel(row, slaHours) },
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
        const nextStatuses = transitions[row.status ?? ""] ?? [];
        return (
          <Space size={4} wrap>
            {nextStatuses.length ? nextStatuses.map((next) => (
              <Button key={next} size="small" onClick={() => updateTicket(row, next)}>
                {statusLabels[next] ?? next}
              </Button>
            )) : <Typography.Text type="secondary">已结束</Typography.Text>}
          </Space>
        );
      }
    },
    {
      title: "知识",
      width: 170,
      fixed: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => setDetailTicket(row)}>详情</Button>
          <Button size="small" onClick={() => openKnowledge(row)}>
            命中检查
          </Button>
        </Space>
      )
    }
  ], [reload, slaHours, statusLabels, transitions]);

  return (
    <>
      <PageHeader
        title="客服工单"
        extra={
          <Space wrap>
            <Select allowClear placeholder="状态" value={status} onChange={setStatus} style={{ width: 130 }} options={[
              { value: "open", label: "待处理" },
              { value: "in_progress", label: "处理中" },
              { value: "waiting_customer", label: "等客户" },
              { value: "resolved", label: "已解决" },
              { value: "closed", label: "已关闭" }
            ]} />
            <Select allowClear placeholder="优先级" value={priority} onChange={setPriority} style={{ width: 120 }} options={[
              { value: "high", label: "高" },
              { value: "medium", label: "中" },
              { value: "low", label: "低" },
              { value: "critical", label: "严重" }
            ]} />
            <Input.Search allowClear placeholder="搜索标题/客户/摘要/来源消息" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 260 }} />
            <ReloadButton loading={loading} onReload={reload} />
          </Space>
        }
      />
      <ApiErrorAlert error={error} />
      <Card className="api-alert" title="客服 SLA 配置">
        <Row gutter={[12, 12]} align="middle">
          {[
            { key: "critical", label: "严重" },
            { key: "high", label: "高" },
            { key: "medium", label: "中" },
            { key: "low", label: "低" }
          ].map((item) => (
            <Col xs={12} md={6} key={item.key}>
              <Space>
                <StatusTag value={item.key} />
                <InputNumber
                  min={1}
                  max={240}
                  value={slaDraft[item.key]}
                  addonAfter="h"
                  onChange={(value) => setSlaDraft((current) => ({ ...current, [item.key]: Number(value ?? 1) }))}
                />
              </Space>
            </Col>
          ))}
          <Col xs={24}>
            <Button type="primary" onClick={saveSlaConfig}>保存 SLA</Button>
          </Col>
        </Row>
      </Card>
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
        scroll={{ x: 1340 }}
        pagination={{ pageSize: 12, total: rows.length }}
      />
      <BusinessObjectDetailDrawer
        objectType="ticket"
        objectId={detailTicket?.id}
        open={Boolean(detailTicket)}
        onClose={() => setDetailTicket(undefined)}
        onChanged={reload}
      />
      <Modal
        title="工单知识命中"
        open={Boolean(knowledgeTicket)}
        onCancel={() => setKnowledgeTicket(undefined)}
        footer={[
          <Button key="gap" onClick={() => createKnowledge("gap")}>沉淀为缺口</Button>,
          <Button key="item" type="primary" onClick={() => createKnowledge("item")}>发布为知识</Button>
        ]}
      >
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="工单">{knowledgeTicket?.title}</Descriptions.Item>
            <Descriptions.Item label="命中状态">
              {knowledgeLoading ? "检查中" : <StatusTag value={knowledgeSuggestion?.status === "hit" ? "success" : "failed"} />}
            </Descriptions.Item>
            <Descriptions.Item label="建议答案">{knowledgeSuggestion?.suggested_answer ?? "-"}</Descriptions.Item>
          </Descriptions>
          <div>
            <Typography.Text strong>匹配知识</Typography.Text>
            <Space direction="vertical" size={6} style={{ width: "100%", marginTop: 8 }}>
              {(knowledgeSuggestion?.matches ?? []).map((item) => (
                <Card key={String(item.id)} size="small">
                  <Space direction="vertical" size={2}>
                    <Typography.Text>{item.title}</Typography.Text>
                    <Typography.Text type="secondary">score {item.score} / {item.category}</Typography.Text>
                  </Space>
                </Card>
              ))}
              {knowledgeSuggestion?.matches?.length ? null : <Typography.Text type="secondary">当前知识库未命中，可沉淀为缺口。</Typography.Text>}
            </Space>
          </div>
        </Space>
      </Modal>
    </>
  );
}

function slaLabel(row: Ticket, slaHours: Record<string, number>) {
  if (!row.created_at || ["resolved", "closed"].includes(row.status ?? "")) return "-";
  const hours = dayjs().diff(dayjs(row.created_at), "hour");
  const threshold = slaHours[row.priority ?? "medium"] ?? 24;
  const danger = hours >= threshold;
  const warning = hours >= Math.max(1, Math.floor(threshold / 2));
  const label = `${hours}h`;
  if (danger) return <Tooltip title="超过建议响应时限"><StatusTag value="urgent" /></Tooltip>;
  if (warning) return <Tooltip title={`已等待 ${label}`}><StatusTag value="in_progress" /></Tooltip>;
  return <Tooltip title={`已等待 ${label}`}><StatusTag value="normal" /></Tooltip>;
}
