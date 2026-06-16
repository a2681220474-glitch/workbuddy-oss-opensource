import { Alert, App as AntdApp, Button, DatePicker, Descriptions, Drawer, Form, Input, Select, Space, Spin, Tag, Timeline, Typography } from "antd";
import type { FormInstance } from "antd/es/form";
import type { Dayjs } from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useAsyncData } from "../components/useAsyncData";
import type { BusinessObjectDetail, EntityId } from "../types";
import { canWriteProcessingRecords, getStoredWorkBuddyUserDisplayName } from "../utils/currentUser";
import { formatTime, shortText } from "../utils/format";
import { hashTarget } from "../utils/navigation";
import { StatusTag } from "./StatusTag";

interface Props {
  objectType?: string;
  objectId?: EntityId;
  open: boolean;
  onClose: () => void;
  onChanged?: () => void | Promise<void>;
}

const STATUS_OPTIONS: Record<string, Array<{ value: string; label: string }>> = {
  ticket: [
    { value: "open", label: "待处理" },
    { value: "in_progress", label: "处理中" },
    { value: "waiting_customer", label: "等客户" },
    { value: "resolved", label: "已解决" },
    { value: "closed", label: "已关闭" }
  ],
  lead: [
    { value: "new", label: "新线索" },
    { value: "potential", label: "潜在线索" },
    { value: "contacted", label: "已联系" },
    { value: "qualified", label: "已确认" },
    { value: "proposal", label: "已发方案" },
    { value: "negotiation", label: "谈判中" },
    { value: "won", label: "赢单" },
    { value: "lost", label: "输单" }
  ],
  task: [
    { value: "todo", label: "待处理" },
    { value: "in_progress", label: "处理中" },
    { value: "waiting", label: "等待中" },
    { value: "done", label: "已完成" },
    { value: "cancelled", label: "已取消" }
  ],
  candidate: [
    { value: "screening", label: "筛选" },
    { value: "interview", label: "面试" },
    { value: "offer", label: "Offer" },
    { value: "onboarding", label: "入职" },
    { value: "hired", label: "已入职" },
    { value: "rejected", label: "淘汰" }
  ],
  knowledge_gap: [
    { value: "pending", label: "待处理" },
    { value: "accepted", label: "已采纳" },
    { value: "ignored", label: "已忽略" }
  ],
  knowledge_item: [
    { value: "draft", label: "草稿" },
    { value: "published", label: "已发布" },
    { value: "archived", label: "已归档" }
  ]
};

export function BusinessObjectDetailDrawer({ objectType, objectId, open, onClose, onChanged }: Props) {
  const { message } = AntdApp.useApp();
  const [detail, setDetail] = useState<BusinessObjectDetail>();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<ProcessingFormValues>();
  const { data: usersData } = useAsyncData(api.getLocalUsers);

  const normalizedType = useMemo(() => normalizeObjectType(objectType), [objectType]);
  const userOptions = useMemo(() => (usersData?.items ?? [])
    .filter((user) => user.status === "active")
    .map((user) => ({
      value: user.id,
      label: `${user.display_name} (@${user.username})`
    })), [usersData?.items]);

  const loadDetail = async () => {
    if (!open || !normalizedType || objectId === undefined) return;
    setLoading(true);
    try {
      setDetail(await api.getBusinessObjectDetail(normalizedType, objectId));
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "加载对象详情失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDetail();
  }, [open, normalizedType, objectId]);

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({
      operator_name: getStoredWorkBuddyUserDisplayName()
    });
  }, [form, open]);

  const submitRecord = async (values: ProcessingFormValues) => {
    if (!normalizedType || objectId === undefined) return;
    setSubmitting(true);
    try {
      await api.createProcessingRecord(normalizedType, objectId, {
        action_type: values.status ? "status_change" : "note",
        status: values.status,
        assignee_user_id: values.assignee_user_id,
        assignee_name: values.assignee_name,
        due_hint: values.due_hint,
        due_at: values.due_at?.format("YYYY-MM-DDTHH:mm:ss[+08:00]") ?? null,
        next_step: values.next_step,
        note: values.note
      });
      message.success("处理记录已保存");
      form.resetFields();
      await loadDetail();
      await onChanged?.();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "保存处理记录失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      title={`${objectTypeLabel(detail?.object_type ?? normalizedType)} #${detail?.object_id ?? objectId ?? ""}`}
      width={840}
      open={open}
      onClose={onClose}
    >
      <Spin spinning={loading}>
        {detail ? (
          <Space direction="vertical" size="large" style={{ width: "100%" }}>
            <ObjectSummary detail={detail} />
            <AgentDefinition detail={detail} />
            <TimelineSection detail={detail} />
            <ProcessingForm
              objectType={String(detail.object_type ?? normalizedType)}
              form={form}
              userOptions={userOptions}
              submitting={submitting}
              onSubmit={submitRecord}
            />
          </Space>
        ) : (
          <Typography.Text type="secondary">选择一个业务对象查看详情。</Typography.Text>
        )}
      </Spin>
    </Drawer>
  );
}

function ObjectSummary({ detail }: { detail: BusinessObjectDetail }) {
  const object = detail.object ?? {};
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Descriptions size="small" column={2}>
        <Descriptions.Item label="对象">{detail.label ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="状态">{renderStatus(object.status ?? object.stage)}</Descriptions.Item>
        <Descriptions.Item label="负责人">{assigneeLabel(detail)}</Descriptions.Item>
        <Descriptions.Item label="下一步">{String(object.next_step ?? latestRecordValue(detail, "next_step") ?? "-")}</Descriptions.Item>
        <Descriptions.Item label="截止时间">{formatTime(String(object.due_at ?? latestRecordValue(detail, "due_at") ?? ""))}</Descriptions.Item>
        <Descriptions.Item label="逾期">{object.is_overdue ? <StatusTag value="urgent" /> : "-"}</Descriptions.Item>
        <Descriptions.Item label="来源消息">{sourceLink(detail.source_message?.id)}</Descriptions.Item>
        <Descriptions.Item label="AgentRun">{agentRunLink(detail.agent_run?.id)}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{formatTime(String(object.created_at ?? ""))}</Descriptions.Item>
        <Descriptions.Item label="更新时间">{formatTime(String(object.updated_at ?? ""))}</Descriptions.Item>
        <Descriptions.Item label="当前操作人">{getStoredWorkBuddyUserDisplayName()}</Descriptions.Item>
      </Descriptions>
      <Typography.Title level={5}>内容摘要</Typography.Title>
      <Typography.Paragraph className="detail-text">
        {String(object.summary ?? object.text ?? object.question ?? object.answer ?? detail.source_message?.text ?? "-")}
      </Typography.Paragraph>
      {detail.related_objects?.length ? (
        <Space wrap>
          <Typography.Text type="secondary">关联对象：</Typography.Text>
          {detail.related_objects.map((item) => (
            <Tag key={`${item.type}-${item.id}`}>{objectTypeLabel(item.type)}#{item.id} {item.label}</Tag>
          ))}
        </Space>
      ) : null}
    </Space>
  );
}

function AgentDefinition({ detail }: { detail: BusinessObjectDetail }) {
  const agent = detail.agent_definition;
  const run = detail.agent_run;
  return (
    <Alert
      type="info"
      showIcon
      message={agent?.name ?? "Agent 工作流"}
      description={
        <Space direction="vertical" size={6} style={{ width: "100%" }}>
          <Typography.Text>{agent?.responsibility}</Typography.Text>
          <Space wrap>
            <Tag>输入：{agent?.inputs?.join(" / ")}</Tag>
            <Tag>输出：{agent?.outputs?.join(" / ")}</Tag>
          </Space>
          <Typography.Text type="secondary">大模型使用：{agent?.llm_usage}</Typography.Text>
          <Typography.Text type="secondary">失败处理：{agent?.failure_handling}</Typography.Text>
          <Typography.Text type="secondary">审批策略：{agent?.approval_policy}</Typography.Text>
          {run ? (
            <Space wrap>
              <Tag>{run.agent_type}</Tag>
              <Tag>置信度 {run.confidence ?? "-"}</Tag>
              <Tag>风险 {run.risk_level ?? "-"}</Tag>
              <Tag>{run.model_provider ?? "local"} / {run.model_name ?? "rule-engine"}</Tag>
            </Space>
          ) : null}
        </Space>
      }
    />
  );
}

function TimelineSection({ detail }: { detail: BusinessObjectDetail }) {
  return (
    <div>
      <Typography.Title level={5}>统一时间线</Typography.Title>
      <Timeline
        items={(detail.timeline ?? []).map((item) => ({
          color: timelineColor(item.type),
          children: (
            <Space direction="vertical" size={2}>
              <Space wrap>
                <Typography.Text strong>{item.title}</Typography.Text>
                <Typography.Text type="secondary">{formatTime(item.created_at)}</Typography.Text>
                {item.target?.type && item.target.id ? linkForTarget(item.target.type, item.target.id) : null}
              </Space>
              <Typography.Text className="detail-text">{shortText(item.description, 160)}</Typography.Text>
              {item.metadata?.status ? <StatusTag value={String(item.metadata.status)} /> : null}
            </Space>
          )
        }))}
      />
      {detail.approvals?.length ? (
        <Space direction="vertical" size={4} style={{ width: "100%" }}>
          <Typography.Text strong>审批上下文</Typography.Text>
          {detail.approvals.map((approval) => (
            <Alert
              key={String(approval.id)}
              type={approval.status === "rejected" ? "warning" : "success"}
              showIcon
              message={`审批 #${approval.id} / ${approval.status ?? "-"}`}
              description={shortText(approval.final_content ?? approval.draft_content, 180)}
            />
          ))}
        </Space>
      ) : null}
    </div>
  );
}

function ProcessingForm({ objectType, form, userOptions, submitting, onSubmit }: {
  objectType: string;
  form: FormInstance<ProcessingFormValues>;
  userOptions: Array<{ value: EntityId; label: string }>;
  submitting: boolean;
  onSubmit: (values: ProcessingFormValues) => void;
}) {
  return (
    <div>
      <Typography.Title level={5}>新增处理记录</Typography.Title>
      {!canWriteProcessingRecords() ? (
        <Alert type="warning" showIcon message="当前账号是只读角色，不能新增处理记录。" style={{ marginBottom: 12 }} />
      ) : null}
      <Form layout="vertical" form={form} onFinish={onSubmit}>
        <Form.Item label="状态" name="status">
          <Select allowClear options={STATUS_OPTIONS[objectType] ?? []} />
        </Form.Item>
        <Form.Item label="负责人" name="assignee_user_id">
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            options={userOptions}
            placeholder="选择团队成员作为负责人"
          />
        </Form.Item>
        <Form.Item label="截止或时间提示" name="due_hint">
          <Input placeholder="例如：今天 18:00 前 / 明天上午 / 本周五" />
        </Form.Item>
        <Form.Item label="正式截止时间" name="due_at">
          <DatePicker showTime format="YYYY-MM-DD HH:mm" style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="下一步" name="next_step">
          <Input placeholder="下一步要做什么" />
        </Form.Item>
        <Form.Item label="处理备注" name="note">
          <Input.TextArea rows={3} placeholder="写清楚已经处理了什么、为什么这样处理、还有什么风险" />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting} disabled={!canWriteProcessingRecords()}>保存处理记录</Button>
      </Form>
    </div>
  );
}

interface ProcessingFormValues {
  status?: string;
  assignee_user_id?: EntityId;
  assignee_name?: string;
  due_hint?: string;
  due_at?: Dayjs;
  next_step?: string;
  note?: string;
  operator_name?: string;
}

function renderStatus(value: unknown) {
  return value ? <StatusTag value={String(value)} /> : "-";
}

function latestRecordValue(detail: BusinessObjectDetail, key: "assignee_name" | "next_step" | "due_at") {
  return (detail.processing_records ?? []).find((record) => record[key])?.[key];
}

function assigneeLabel(detail: BusinessObjectDetail) {
  const object = detail.object ?? {};
  const record = (detail.processing_records ?? []).find((item) => item.assignee_user?.display_name || item.assignee_name);
  if (record?.assignee_user?.display_name) {
    return `${record.assignee_user.display_name} (@${record.assignee_user.username ?? "-"})`;
  }
  if (object.assignee_name) return String(object.assignee_name);
  if (record?.assignee_name) return record.assignee_name;
  return "-";
}

function sourceLink(id?: EntityId) {
  return id ? <a href={hashTarget("messages", id)}>消息#{id}</a> : "-";
}

function agentRunLink(id?: EntityId) {
  return id ? <a href={hashTarget("agent-runs", id)}>运行#{id}</a> : "-";
}

function linkForTarget(type: string, id: EntityId) {
  if (type === "message") return <a href={hashTarget("messages", id)}>消息#{id}</a>;
  if (type === "agent_run") return <a href={hashTarget("agent-runs", id)}>运行#{id}</a>;
  if (type === "approval") return <a href={hashTarget("approvals", id)}>审批#{id}</a>;
  return null;
}

function timelineColor(type?: string) {
  const colors: Record<string, string> = {
    message: "blue",
    agent_run: "purple",
    business_object: "green",
    approval: "orange",
    processing_record: "gray"
  };
  return colors[type ?? ""] ?? "blue";
}

function normalizeObjectType(value?: string) {
  const aliases: Record<string, string> = {
    tickets: "ticket",
    leads: "lead",
    tasks: "task",
    candidates: "candidate",
    knowledge_gaps: "knowledge_gap",
    knowledge_items: "knowledge_item",
    reports: "report"
  };
  return value ? aliases[value] ?? value : undefined;
}

function objectTypeLabel(value?: string) {
  const labels: Record<string, string> = {
    ticket: "工单",
    lead: "线索",
    task: "任务",
    candidate: "候选人",
    knowledge_gap: "知识缺口",
    knowledge_item: "知识条目",
    report: "报告"
  };
  return labels[value ?? ""] ?? value ?? "业务对象";
}
