import { CheckOutlined, CloseOutlined, EditOutlined, SendOutlined } from "@ant-design/icons";
import { Alert, App as AntdApp, Button, Drawer, Input, Modal, Select, Space, Spin, Tag, Timeline, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { PageHeader } from "../components/PageHeader";
import { ReloadButton } from "../components/ReloadButton";
import { ResizableTable } from "../components/ResizableTable";
import { StatusTag } from "../components/StatusTag";
import { useAsyncData } from "../components/useAsyncData";
import type { Approval, ApprovalCardPreview, ApprovalContext, ApprovalDecision } from "../types";
import { canOperateApprovals } from "../utils/currentUser";
import { formatTime, shortText } from "../utils/format";
import { isTargetId } from "../utils/navigation";
import { filterBySearch } from "../utils/search";
import { useHashId } from "../utils/useHashId";

export function ApprovalsPage() {
  const { message, modal } = AntdApp.useApp();
  const [status, setStatus] = useState<string>();
  const [targetAgent, setTargetAgent] = useState<string>();
  const [businessObjectType, setBusinessObjectType] = useState<string>();
  const loadApprovals = useCallback(() => api.getApprovals({
    status,
    target_agent: targetAgent,
    business_object_type: businessObjectType
  }), [businessObjectType, status, targetAgent]);
  const { data, error, loading, reload } = useAsyncData(loadApprovals);
  const targetId = useHashId();
  const [activeApproval, setActiveApproval] = useState<Approval>();
  const [detailApproval, setDetailApproval] = useState<Approval>();
  const [approvalContext, setApprovalContext] = useState<ApprovalContext>();
  const [contextLoading, setContextLoading] = useState(false);
  const [finalContent, setFinalContent] = useState("");
  const [decision, setDecision] = useState<ApprovalDecision>("edited");
  const [submitting, setSubmitting] = useState(false);
  const [search, setSearch] = useState("");
  const rows = useMemo(() => filterBySearch((data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "id",
    "status",
    "action_type",
    "original_message",
    "original_sender_name",
    "original_sender_display_name",
    "original_conversation_display_name",
    "draft_content",
    "final_content",
    "intent",
    "target_agent",
    "risk_level",
    "business_object_type",
    "business_object_label",
    "delivery_status",
    "delivery_channel"
  ]) as unknown as Approval[], [data?.items, search]);

  const openDecision = (approval: Approval, nextDecision: ApprovalDecision) => {
    setActiveApproval(approval);
    setDecision(nextDecision);
    setFinalContent(approval.final_content ?? approval.draft_content ?? "");
  };

  useEffect(() => {
    if (!detailApproval?.id) {
      setApprovalContext(undefined);
      return;
    }
    setContextLoading(true);
    api.getApprovalContext(detailApproval.id)
      .then(setApprovalContext)
      .catch((caught) => message.error(caught instanceof Error ? caught.message : "审批上下文加载失败"))
      .finally(() => setContextLoading(false));
  }, [detailApproval?.id]);

  const submitDecision = async () => {
    if (!activeApproval) return;
    setSubmitting(true);
    try {
      await api.decideApproval(activeApproval.id, decision, finalContent);
      message.success("审批已更新");
      setActiveApproval(undefined);
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "审批失败");
    } finally {
      setSubmitting(false);
    }
  };

  const sendApproval = async (approval: Approval) => {
    if (hasSuccessfulDelivery(approval)) {
      message.info("这条审批已经发送成功，不需要重复发送");
      await reload();
      return;
    }
    setSubmitting(true);
    try {
      const preview = await api.previewApprovalSend(approval.id);
      if (!preview.sendable) {
        modal.warning({
          title: preview.title ?? "当前审批不能发送",
          content: (
            <Space direction="vertical" size={10} style={{ width: "100%" }}>
              <Typography.Text>{preview.message ?? "请先检查审批状态和渠道策略。"}</Typography.Text>
              {deliveryRetrySummary(preview)}
            </Space>
          )
        });
        return;
      }
      modal.confirm({
        title: preview.title ?? "确认发送审批回复",
        okText: preview.mode === "real" ? "确认真实发送" : "确认模拟发送",
        cancelText: "取消",
        okButtonProps: { danger: preview.mode === "real" },
        content: (
          <Space direction="vertical" size={10} style={{ width: "100%" }}>
            <Alert
              type={preview.mode === "real" ? "warning" : "info"}
              showIcon
              message={preview.message}
            />
            <Space wrap>
              <Tag color={preview.mode === "real" ? "orange" : "blue"}>{sendModeLabel(preview.mode)}</Tag>
              <Tag>{channelLabel(preview.channel)}</Tag>
              {preview.delivery_attempts ? <Tag>已尝试 {preview.delivery_attempts} 次</Tag> : null}
              {preview.next_attempt ? <Tag color="geekblue">下次第 {preview.next_attempt} 次</Tag> : null}
            </Space>
            {deliveryRetrySummary(preview)}
            <Typography.Paragraph className="detail-text">{shortText(preview.content_preview, 180)}</Typography.Paragraph>
            <pre className="json-block">{JSON.stringify(preview.policy ?? {}, null, 2)}</pre>
          </Space>
        ),
        onOk: () => executeSendApproval(approval)
      });
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "发送预检失败");
    } finally {
      setSubmitting(false);
    }
  };

  const executeSendApproval = async (approval: Approval) => {
    setSubmitting(true);
    try {
      await api.sendApproval(approval.id);
      message.success("已发送，外部发送开关关闭时会记录为模拟发送");
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "发送失败");
    } finally {
      setSubmitting(false);
    }
  };

  const sendApprovalCard = async (approval: Approval) => {
    setSubmitting(true);
    try {
      const preview = await api.previewApprovalCard(approval.id);
      modal.confirm({
        title: "发送飞书审批卡片",
        okText: preview.mode === "real" ? "确认发送卡片" : "记录模拟卡片",
        cancelText: "取消",
        okButtonProps: { danger: preview.mode === "real", disabled: preview.mode === "real" && !preview.sendable },
        content: <ApprovalCardPreviewContent preview={preview} />,
        onOk: async () => {
          await api.sendApprovalCard(approval.id, preview.mode === "real");
          message.success(preview.mode === "real" ? "飞书审批卡片已发送" : "已记录模拟审批卡片");
          await reload();
        }
      });
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "审批卡片预检失败");
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ColumnsType<Approval> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "状态", dataIndex: "status", width: 130, render: (value) => <StatusTag value={value} /> },
    { title: "动作", dataIndex: "action_type", width: 170, render: (value) => actionLabel(value) },
    {
      title: "原始消息",
      dataIndex: "original_message",
      width: 210,
      render: (value, row) => textPreview(value, () => setDetailApproval(row))
    },
    {
      title: "AI 草稿",
      dataIndex: "draft_content",
      width: 230,
      render: (value, row) => textPreview(value, () => setDetailApproval(row))
    },
    { title: "意图", dataIndex: "intent", width: 140, render: (value) => value ?? "-" },
    { title: "风险", dataIndex: "risk_level", width: 100, render: (value) => <StatusTag value={value} /> },
    { title: "对象", width: 150, render: (_, row) => objectLabel(row) },
    { title: "发送", width: 190, render: (_, row) => deliveryLabel(row) },
    {
      title: "发送尝试",
      width: 120,
      render: (_, row) => row.delivery_attempts ? `${row.delivery_attempts} 次` : "-"
    },
    { title: "创建时间", dataIndex: "created_at", width: 160, render: formatTime },
    {
      title: "操作",
      fixed: "right",
      width: 430,
      render: (_, row) => (
        <Space>
          <Button icon={<CheckOutlined />} size="small" disabled={!canOperateApprovals() || !canDecideApproval(row)} onClick={() => openDecision(row, "approved")}>通过</Button>
          <Button icon={<EditOutlined />} size="small" disabled={!canOperateApprovals() || !canDecideApproval(row)} onClick={() => openDecision(row, "edited")}>编辑</Button>
          <Button icon={<CloseOutlined />} size="small" danger disabled={!canOperateApprovals() || !canDecideApproval(row)} onClick={() => openDecision(row, "rejected")}>拒绝</Button>
          <Button
            icon={<SendOutlined />}
            size="small"
            disabled={!canOperateApprovals() || !canSendApproval(row)}
            loading={submitting}
            onClick={() => sendApproval(row)}
          >
            {row.delivery_status === "failed" ? "重试" : "发送"}
          </Button>
          <Button size="small" disabled={!canOperateApprovals() || !canSendApprovalCard(row)} loading={submitting} onClick={() => sendApprovalCard(row)}>
            飞书卡片
          </Button>
        </Space>
      )
    }
  ];

  return (
    <>
      <PageHeader
        title="审批队列"
        extra={
          <Space wrap>
            <Select allowClear placeholder="状态" value={status} onChange={setStatus} style={{ width: 130 }} options={[
              { value: "pending_review", label: "待审核" },
              { value: "approved", label: "已通过" },
              { value: "edited", label: "已编辑" },
              { value: "rejected", label: "已拒绝" },
              { value: "sent", label: "已发送" }
            ]} />
            <Select allowClear placeholder="Agent" value={targetAgent} onChange={setTargetAgent} style={{ width: 170 }} options={agentOptions()} />
            <Select allowClear placeholder="业务对象" value={businessObjectType} onChange={setBusinessObjectType} style={{ width: 140 }} options={[
              { value: "ticket", label: "工单" },
              { value: "lead", label: "线索" },
              { value: "task", label: "任务" },
              { value: "candidate", label: "候选人" },
              { value: "knowledge_gap", label: "知识缺口" }
            ]} />
            <Input.Search allowClear placeholder="搜索消息/草稿/发送人/对象" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 260 }} />
            <ReloadButton loading={loading} onReload={reload} />
          </Space>
        }
      />
      {!canOperateApprovals() ? (
        <Alert
          type="warning"
          showIcon
          message="当前账号没有审批权限"
          description="请切换到管理员或审批人账号，再执行通过、拒绝、发送和飞书卡片操作。"
          style={{ marginBottom: 16 }}
        />
      ) : null}
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
        scroll={{ x: 1810 }}
        pagination={{ pageSize: 10, total: rows.length }}
      />
      <Modal
        title={decision === "rejected" ? "拒绝审批" : decision === "approved" ? "通过审批" : "编辑后通过"}
        open={Boolean(activeApproval)}
        okText="提交"
        cancelText="取消"
        confirmLoading={submitting}
        onOk={submitDecision}
        onCancel={() => setActiveApproval(undefined)}
      >
        <Input.TextArea
          rows={8}
          value={finalContent}
          disabled={decision === "rejected"}
          onChange={(event) => setFinalContent(event.target.value)}
        />
      </Modal>
      <Drawer title="审批详情" width={760} open={Boolean(detailApproval)} onClose={() => setDetailApproval(undefined)}>
        <Spin spinning={contextLoading}>
        <Typography.Title level={5}>上下文</Typography.Title>
        <Typography.Paragraph>
          <Typography.Text type="secondary">发送人：</Typography.Text>
          {detailApproval?.original_sender_display_name ?? detailApproval?.original_sender_name ?? "-"}
        </Typography.Paragraph>
        <Typography.Paragraph>
          <Typography.Text type="secondary">会话：</Typography.Text>
          {detailApproval?.original_conversation_display_name ?? "-"}
        </Typography.Paragraph>
        <Typography.Title level={5}>原始消息</Typography.Title>
        <Typography.Paragraph className="detail-text">{detailApproval?.original_message ?? "-"}</Typography.Paragraph>
        <Typography.Title level={5}>AI 草稿</Typography.Title>
        <Typography.Paragraph className="detail-text">{detailApproval?.draft_content ?? "-"}</Typography.Paragraph>
        {(approvalContext?.knowledge_references ?? []).length ? (
          <>
            <Typography.Title level={5}>知识引用</Typography.Title>
            <Space direction="vertical" size="small" style={{ width: "100%" }}>
              {(approvalContext?.knowledge_references ?? []).map((reference) => (
                <Alert
                  key={`${reference.type}-${reference.id}-${reference.hit_id}`}
                  type="success"
                  showIcon
                  message={`KnowledgeItem#${reference.id} ${reference.title ?? ""}`}
                  description={
                    <Space direction="vertical" size={2}>
                      <Typography.Text>{shortText(reference.snippet || "-", 180)}</Typography.Text>
                      <Typography.Text type="secondary">
                        分类 {reference.category ?? "general"} / score={reference.score ?? 0} / hit#{reference.hit_id ?? "-"} / {(reference.reasons ?? []).join(", ") || "-"}
                      </Typography.Text>
                    </Space>
                  }
                />
              ))}
            </Space>
          </>
        ) : null}
        <Typography.Title level={5}>Agent 判断</Typography.Title>
        <Space wrap>
          <Tag>{agentLabel(detailApproval?.target_agent)}</Tag>
          <Tag>意图 {detailApproval?.intent ?? "-"}</Tag>
          <Tag>置信度 {detailApproval?.confidence ?? "-"}</Tag>
          <Tag>风险 {detailApproval?.risk_level ?? "-"}</Tag>
        </Space>
        {approvalContext?.business_object ? (
          <>
            <Typography.Title level={5}>关联业务对象</Typography.Title>
            <Alert
              type="info"
              showIcon
              message={`${objectTypeLabel(approvalContext.business_object.object_type)} #${approvalContext.business_object.object_id} ${approvalContext.business_object.label ?? ""}`}
              description={shortText(String(approvalContext.business_object.object?.summary ?? approvalContext.business_object.source_message?.text ?? "-"), 180)}
            />
            <Typography.Title level={5}>对象时间线</Typography.Title>
            <Timeline
              items={(approvalContext.business_object.timeline ?? []).map((item) => ({
                children: (
                  <Space direction="vertical" size={2}>
                    <Typography.Text strong>{item.title}</Typography.Text>
                    <Typography.Text type="secondary">{formatTime(item.created_at)}</Typography.Text>
                    <Typography.Text className="detail-text">{shortText(item.description, 120)}</Typography.Text>
                  </Space>
                )
              }))}
            />
          </>
        ) : null}
        <Typography.Title level={5}>发送结果</Typography.Title>
        {deliveryLabel(detailApproval)}
        {detailApproval?.delivery_attempts ? (
          <Typography.Paragraph>
            <Typography.Text type="secondary">发送尝试：</Typography.Text>
            {detailApproval.delivery_attempts} 次
            {detailApproval.last_delivery_at ? ` / 最近 ${formatTime(detailApproval.last_delivery_at)}` : ""}
          </Typography.Paragraph>
        ) : null}
        {approvalContext?.send_preview ? deliveryRetrySummary(approvalContext.send_preview) : null}
        {detailApproval?.delivery_chat_id ? (
          <Typography.Paragraph>
            <Typography.Text type="secondary">会话：</Typography.Text>
            <Typography.Text code>{detailApproval.delivery_chat_id}</Typography.Text>
          </Typography.Paragraph>
        ) : null}
        {detailApproval?.delivery_feishu_message_id ? (
          <Typography.Paragraph>
            <Typography.Text type="secondary">飞书消息：</Typography.Text>
            <Typography.Text code>{detailApproval.delivery_feishu_message_id}</Typography.Text>
          </Typography.Paragraph>
        ) : null}
        {detailApproval?.delivery_request_uuid ? (
          <Typography.Paragraph>
            <Typography.Text type="secondary">请求 ID：</Typography.Text>
            <Typography.Text code>{detailApproval.delivery_request_uuid}</Typography.Text>
          </Typography.Paragraph>
        ) : null}
        {detailApproval?.delivery_error ? (
          <Typography.Paragraph type="danger" className="detail-text">{detailApproval.delivery_error}</Typography.Paragraph>
        ) : null}
        {detailApproval?.delivery_advice ? (
          <Typography.Paragraph className="detail-text">{detailApproval.delivery_advice}</Typography.Paragraph>
        ) : null}
        {(approvalContext?.delivery_history ?? []).length ? (
          <>
            <Typography.Title level={5}>发送历史</Typography.Title>
            <Timeline
              items={(approvalContext?.delivery_history ?? []).map((item) => ({
                color: item.status === "success" ? "green" : item.status === "failed" ? "red" : "gray",
                children: (
                  <Space direction="vertical" size={2}>
                    <Space wrap>
                      <Typography.Text strong>尝试 {item.attempt ?? "-"}</Typography.Text>
                      <StatusTag value={item.status} />
                      <Tag>{channelLabel(item.channel)}</Tag>
                      <Tag>{sendModeLabel(item.mode)}</Tag>
                    </Space>
                    <Typography.Text type="secondary">{formatTime(item.created_at)}</Typography.Text>
                    {item.target_id ? <Typography.Text code>{item.target_type ? `${item.target_type}:${item.target_id}` : item.target_id}</Typography.Text> : null}
                    {item.feishu_message_id ? <Typography.Text code>{item.feishu_message_id}</Typography.Text> : null}
                    {item.error ? <Typography.Text type="danger" className="detail-text">{item.error}</Typography.Text> : null}
                    {item.advice ? <Typography.Text className="detail-text">{item.advice}</Typography.Text> : null}
                  </Space>
                )
              }))}
            />
          </>
        ) : null}
        <Typography.Title level={5}>飞书审批卡片</Typography.Title>
        <ApprovalCardPreviewContent preview={approvalContext?.card_preview} compact />
        {(approvalContext?.card_history ?? []).length ? (
          <>
            <Typography.Title level={5}>卡片操作历史</Typography.Title>
            <Timeline
              items={(approvalContext?.card_history ?? []).map((item) => ({
                color: item.status === "success" ? "green" : item.status === "failed" ? "red" : "gray",
                children: (
                  <Space direction="vertical" size={2}>
                    <Space wrap>
                      <Typography.Text strong>{item.callback ? cardDecisionLabel(item.decision) : "发送审批卡片"}</Typography.Text>
                      <StatusTag value={item.status} />
                      <Tag>{item.callback ? "回调" : "发送"}</Tag>
                      {item.mode ? <Tag>{sendModeLabel(item.mode)}</Tag> : null}
                    </Space>
                    <Typography.Text type="secondary">{formatTime(item.created_at)}</Typography.Text>
                    {item.chat_id ? <Typography.Text code>{item.chat_id}</Typography.Text> : null}
                    {item.request_uuid ? <Typography.Text code>{item.request_uuid}</Typography.Text> : null}
                    {item.toast ? <Typography.Text className="detail-text">{item.toast}</Typography.Text> : null}
                    {item.error ? <Typography.Text type="danger" className="detail-text">{item.error}</Typography.Text> : null}
                  </Space>
                )
              }))}
            />
          </>
        ) : null}
        </Spin>
      </Drawer>
    </>
  );
}

function ApprovalCardPreviewContent({ preview, compact = false }: { preview?: ApprovalCardPreview; compact?: boolean }) {
  const missing = preview?.missing ?? [];
  const cardMode = preview?.mode === "real" ? "真实发送模式" : "模拟模式";
  const alertType = preview?.mode === "real" ? (preview?.sendable ? "info" : "warning") : "info";
  const message = preview?.mode === "real"
    ? preview?.sendable
      ? "将真实发送到内部审批 Chat ID"
      : "当前不能真实发送审批卡片，请先补齐飞书配置"
    : preview?.config_ready
      ? "当前是模拟模式，只记录内部审批卡片，不会真实发到飞书"
      : "未配置审批 Chat ID，将只生成/记录模拟卡片";
  const description = preview?.target_chat_id
    ? `目标会话：${preview.target_chat_id}`
    : missing.length
      ? `缺少：${missing.join("、")}`
      : undefined;
  return (
    <Space direction="vertical" size={10} style={{ width: "100%" }}>
      <Alert
        type={alertType}
        showIcon
        message={message}
        description={description}
      />
      <Space wrap>
        <Tag color={preview?.mode === "real" ? "orange" : "blue"}>{cardMode}</Tag>
        <Tag>通过 / 拒绝 / 查看详情</Tag>
      </Space>
      {compact ? null : <pre className="json-block">{JSON.stringify(preview?.card ?? {}, null, 2)}</pre>}
    </Space>
  );
}

function textPreview(value: string | undefined, onOpen: () => void) {
  return (
    <Space direction="vertical" size={2}>
      <Typography.Text className="table-compact-text">{shortText(value, 42)}</Typography.Text>
      <Button type="link" size="small" onClick={onOpen}>查看</Button>
    </Space>
  );
}

function deliveryLabel(row?: Approval) {
  if (!row?.delivery_status) return <Tag>未发送</Tag>;
  const channel = row.delivery_channel === "feishu" ? "飞书" : row.delivery_channel ?? "本地";
  if (row.delivery_error || row.delivery_status === "failed") return <Tag color="red">{channel}发送失败，可重试</Tag>;
  if (row.delivery_mode === "mock") return <Tag color="blue">模拟发送成功</Tag>;
  return <Tag color="green">真实发送成功</Tag>;
}

function hasSuccessfulDelivery(row?: Approval) {
  return row?.delivery_status === "success";
}

function deliveryRetrySummary(preview?: ApprovalContext["send_preview"]) {
  if (!preview) return null;
  if (!preview.delivery_attempts && preview.retry_allowed !== false) return null;
  const retryAfter = preview.retry_after_seconds ?? 0;
  const lines = [
    preview.delivery_attempts ? `已尝试 ${preview.delivery_attempts}/${preview.max_delivery_attempts ?? "-"} 次` : "",
    preview.next_attempt ? `下次发送为第 ${preview.next_attempt} 次` : "",
    retryAfter ? `还需等待 ${retryAfter} 秒` : "",
    preview.next_retry_at ? `下次可重试：${formatTime(preview.next_retry_at)}` : ""
  ].filter(Boolean).join(" / ");
  return (
    <Alert
      type={preview.retry_allowed === false ? "warning" : "info"}
      showIcon
      message={preview.retry_message ?? (preview.retry_allowed === false ? "当前重试被策略拦截" : "发送重试策略")}
      description={lines || undefined}
    />
  );
}

function canSendApproval(row: Approval) {
  return ["approved", "edited"].includes(row.status ?? "") && !hasSuccessfulDelivery(row);
}

function canSendApprovalCard(row: Approval) {
  return ["pending_review", "edited"].includes(row.status ?? "") && !hasSuccessfulDelivery(row);
}

function canDecideApproval(row: Approval) {
  return !["sent", "rejected"].includes(row.status ?? "") && !hasSuccessfulDelivery(row);
}

function cardDecisionLabel(value?: string) {
  if (value === "approved") return "卡片通过";
  if (value === "rejected") return "卡片拒绝";
  if (value === "detail") return "查看详情";
  return "审批卡片";
}

function objectLabel(row: Approval) {
  if (!row.business_object_type) return "-";
  const labels: Record<string, string> = {
    ticket: "工单",
    lead: "线索",
    task: "任务",
    candidate: "候选人",
    knowledge_gap: "知识缺口"
  };
  return `${labels[row.business_object_type] ?? row.business_object_type}#${row.business_object_id ?? "-"}`;
}

function agentOptions() {
  return [
    { value: "support_ticket_agent", label: "客服工单知识" },
    { value: "sales_lead_agent", label: "销售线索跟进" },
    { value: "community_ops_agent", label: "私域社群运营" },
    { value: "recruiting_hr_agent", label: "招聘与入职" },
    { value: "report_agent", label: "报告 Agent" }
  ];
}

function agentLabel(value?: string) {
  return agentOptions().find((item) => item.value === value)?.label ?? value ?? "-";
}

function objectTypeLabel(value?: string) {
  const labels: Record<string, string> = {
    ticket: "工单",
    lead: "线索",
    task: "任务",
    candidate: "候选人",
    knowledge_gap: "知识缺口",
    knowledge_item: "知识条目"
  };
  return labels[value ?? ""] ?? value ?? "业务对象";
}

function actionLabel(value?: string) {
  const labels: Record<string, string> = {
    send_draft_to_approval: "回复草稿审批",
    create_ticket: "创建工单",
    create_lead: "创建线索",
    create_followup_task: "创建跟进任务",
    escalate_to_human: "转人工处理"
  };
  return labels[value ?? "send_draft_to_approval"] ?? value ?? "回复草稿审批";
}

function sendModeLabel(value?: string) {
  const labels: Record<string, string> = {
    real: "真实发送",
    mock: "模拟发送",
    disabled: "禁止发送",
    blocked: "不可发送",
    sent: "已发送"
  };
  return labels[value ?? ""] ?? value ?? "-";
}

function channelLabel(value?: string | null) {
  const labels: Record<string, string> = {
    feishu: "飞书",
    csv: "CSV",
    local: "本地",
    wecom: "企业微信",
    dingtalk: "钉钉"
  };
  return labels[value ?? ""] ?? value ?? "-";
}
