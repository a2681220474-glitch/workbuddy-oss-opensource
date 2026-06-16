import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudSyncOutlined,
  ReloadOutlined,
  SendOutlined,
  WarningOutlined
} from "@ant-design/icons";
import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Input,
  Modal,
  Row,
  Space,
  Statistic,
  Tag,
  Typography
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { ConnectorAcceptancePanel } from "../components/ConnectorAcceptancePanel";
import { PageHeader } from "../components/PageHeader";
import { ResizableTable } from "../components/ResizableTable";
import { StatusTag } from "../components/StatusTag";
import { useAsyncData } from "../components/useAsyncData";
import type { EntityId, FeishuAgentRun, FeishuChannelEvent, WeComDiagnostics } from "../types";
import { entityKey, formatTime, shortText } from "../utils/format";
import { hashTarget, type NavTarget } from "../utils/navigation";

export function WeComDiagnosticsPage() {
  const { message } = AntdApp.useApp();
  const [checkToken, setCheckToken] = useState(false);
  const [activeJson, setActiveJson] = useState<{ title: string; payload: unknown }>();
  const [mockLoading, setMockLoading] = useState(false);
  const [realLoading, setRealLoading] = useState(false);
  const [realModalOpen, setRealModalOpen] = useState(false);
  const [targetType, setTargetType] = useState<"user" | "chat">("user");
  const [targetId, setTargetId] = useState("");
  const [testText, setTestText] = useState("WorkBuddy OSS 企业微信真实发送测试");
  const [authorizationPhrase, setAuthorizationPhrase] = useState("");
  const loadDiagnostics = useCallback(() => api.getWeComDiagnostics(checkToken), [checkToken]);
  const { data, error, loading, reload } = useAsyncData(loadDiagnostics);

  const lastTarget = useMemo(() => {
    const lastSend = data?.recent?.last_send as Record<string, unknown> | undefined;
    const lastMessage = data?.recent?.last_message as Record<string, unknown> | undefined;
    const lastEvent = data?.recent?.last_event as Record<string, unknown> | undefined;
    const latestTargetType: "user" | "chat" =
      typeof lastSend?.target_type === "string" && lastSend.target_type === "chat" ? "chat" : "user";
    const latestTargetId =
      (typeof lastSend?.target_id === "string" && lastSend.target_id)
      || (typeof lastMessage?.sender_external_id === "string" && lastMessage.sender_external_id)
      || (typeof lastEvent?.actor_external_id === "string" && lastEvent.actor_external_id)
      || "";
    return {
      type: latestTargetType,
      id: latestTargetId,
    };
  }, [data]);

  const runTokenCheck = async () => {
    if (checkToken) {
      await reload();
      return;
    }
    setCheckToken(true);
  };

  const runMockSend = async () => {
    setMockLoading(true);
    try {
      await api.mockWeComSend({
        target_type: lastTarget.type,
        target_id: lastTarget.id || "wecom-demo-user",
        text: "WorkBuddy OSS 企业微信模拟发送测试"
      });
      message.success("模拟发送测试已记录，不会触达企业微信");
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "模拟发送失败");
    } finally {
      setMockLoading(false);
    }
  };

  const runRealSend = async () => {
    setRealLoading(true);
    try {
      await api.realWeComTestSend({
        target_type: targetType,
        target_id: targetId,
        text: testText,
        confirm_real_send: true,
        authorization_phrase: authorizationPhrase
      });
      message.success("企业微信真实发送测试成功");
      setRealModalOpen(false);
      setAuthorizationPhrase("");
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "真实发送失败");
    } finally {
      setRealLoading(false);
    }
  };

  const eventColumns: ColumnsType<FeishuChannelEvent> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "事件", dataIndex: "event_type", width: 260 },
    { title: "状态", dataIndex: "status", width: 120, render: (value) => <StatusTag value={value} /> },
    {
      title: "会话",
      dataIndex: "conversation_external_id",
      width: 220,
      render: (value) => <Typography.Text code>{shortText(value, 28)}</Typography.Text>
    },
    {
      title: "用户",
      dataIndex: "actor_external_id",
      width: 220,
      render: (value) => <Typography.Text code>{shortText(value, 28)}</Typography.Text>
    },
    { title: "时间", dataIndex: "created_at", width: 170, render: formatTime },
    {
      title: "详情",
      width: 90,
      render: (_, row) => (
        <Button type="link" size="small" onClick={() => setActiveJson({ title: `事件 #${row.id}`, payload: row.raw_json })}>
          查看
        </Button>
      )
    }
  ];

  const runColumns: ColumnsType<FeishuAgentRun> = [
    { title: "ID", dataIndex: "id", width: 80, render: (value) => navLink("agent-runs", value, `#${value}`) },
    { title: "类型", dataIndex: "agent_type", width: 190 },
    { title: "状态", dataIndex: "status", width: 110, render: (value) => <StatusTag value={value} /> },
    { title: "消息", dataIndex: "message_id", width: 110, render: (value) => navLink("messages", value, `消息#${value}`) },
    {
      title: "动作",
      width: 220,
      render: (_, row) => String(row.action_json?.target_type ?? row.action_json?.delivery_channel ?? row.prompt_json?.source ?? "-")
    },
    {
      title: "结果",
      width: 240,
      render: (_, row) => {
        const output = row.model_output_json ?? {};
        const error = row.error_message || (typeof output.error === "string" ? output.error : "");
        return error ? <Typography.Text type="danger">{shortText(error, 46)}</Typography.Text> : shortText(JSON.stringify(output), 46);
      }
    },
    { title: "时间", dataIndex: "created_at", width: 170, render: formatTime },
    {
      title: "详情",
      width: 90,
      render: (_, row) => (
        <Button type="link" size="small" onClick={() => setActiveJson({ title: `运行 #${row.id}`, payload: row })}>
          查看
        </Button>
      )
    }
  ];

  return (
    <>
      <PageHeader
        title="企微诊断"
        extra={
          <>
            <Button icon={<CheckCircleOutlined />} loading={loading && checkToken} onClick={runTokenCheck}>
              检查 Token
            </Button>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={reload}>
              刷新
            </Button>
          </>
        }
      />
      <ApiErrorAlert error={error} />

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic
              title="接收链路"
              value={data?.production_readiness?.receive_ready ? "可验收" : "待配置"}
              prefix={<CloudSyncOutlined />}
              valueStyle={{ color: data?.production_readiness?.receive_ready ? "#15803d" : "#b91c1c" }}
            />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic
              title="发送模式"
              value={data?.send_mode === "real" ? "真实发送" : "模拟发送"}
              prefix={<SendOutlined />}
              valueStyle={{ color: data?.send_mode === "real" ? "#b45309" : "#2563eb" }}
            />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic
              title="Token"
              value={tokenLabel(data)}
              prefix={data?.token?.status === "failed" ? <WarningOutlined /> : <ApiOutlined />}
              valueStyle={{ color: data?.token?.status === "failed" ? "#b91c1c" : "#15803d" }}
            />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic
              title="外部发送"
              value={data?.external_send_enabled ? "已开启" : "已关闭"}
              valueStyle={{ color: data?.external_send_enabled ? "#b45309" : "#2563eb" }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="企业微信正式运行检查" className="dashboard-lower">
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <Space wrap>
            <Tag color={data?.production_readiness?.receive_ready ? "green" : "red"}>
              接收链路{data?.production_readiness?.receive_ready ? "可验收" : "未就绪"}
            </Tag>
            <Tag color={data?.production_readiness?.send_ready ? "green" : "orange"}>
              发送链路{data?.production_readiness?.send_ready ? "可真实发送" : "默认模拟/待配置"}
            </Tag>
            <Tag color={data?.production_readiness?.ready ? "green" : "orange"}>
              总体{data?.production_readiness?.ready ? "就绪" : "待加固"}
            </Tag>
          </Space>
          <Row gutter={[12, 12]}>
            {(data?.production_readiness?.checks ?? []).map((item) => (
              <Col xs={24} md={12} xl={8} key={String(item.key)}>
                <Alert
                  showIcon
                  type={item.ok ? "success" : item.severity === "warning" ? "warning" : "error"}
                  message={item.label}
                  description={item.message}
                />
              </Col>
            ))}
          </Row>
        </Space>
      </Card>
      <ConnectorAcceptancePanel data={data?.safe_acceptance} />

      <Row gutter={[16, 16]} className="dashboard-lower">
        <Col xs={24} xl={14}>
          <Card
            title="连接概览"
            extra={
              <Space>
                <Button loading={mockLoading} onClick={runMockSend}>
                  安全模拟发送
                </Button>
                <Button
                  danger
                  type="primary"
                  disabled={data?.send_mode !== "real"}
                  onClick={() => {
                    setTargetType(lastTarget.type);
                    setTargetId(lastTarget.id);
                    setAuthorizationPhrase("");
                    setRealModalOpen(true);
                  }}
                >
                  真实测试发送
                </Button>
              </Space>
            }
          >
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="配置状态">{data?.configured ? "已配置" : "缺少 Corp ID / Agent ID / Secret"}</Descriptions.Item>
              <Descriptions.Item label="Webhook">{data?.webhook_path ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="回调模式">{data?.callback_mode === "encrypted" ? "安全模式" : "普通/兼容模式"}</Descriptions.Item>
              <Descriptions.Item label="最近事件">
                <Space wrap>
                  <span>{String((data?.recent?.last_event as Record<string, unknown> | undefined)?.event_type ?? "-")}</span>
                  {data?.recent?.last_event ? (
                    <Button
                      type="link"
                      size="small"
                      onClick={() => setActiveJson({ title: "最近企微事件", payload: data.recent?.last_event })}
                    >
                      查看事件详情
                    </Button>
                  ) : null}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="最近消息">
                <Space wrap>
                  <span>{shortText(String((data?.recent?.last_message as Record<string, unknown> | undefined)?.text ?? "-"), 80)}</span>
                  {navLink("messages", entityId((data?.recent?.last_message as Record<string, unknown> | undefined)?.id), "查看消息")}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="最近发送">{renderLastSend(data)}</Descriptions.Item>
              <Descriptions.Item label="Token 检查">
                <Space>
                  <Tag color={data?.token?.status === "ok" ? "green" : data?.token?.status === "failed" ? "red" : "default"}>
                    {tokenLabel(data)}
                  </Tag>
                  {data?.token?.masked ? <Typography.Text code>{data.token.masked}</Typography.Text> : null}
                </Space>
              </Descriptions.Item>
            </Descriptions>
            {data?.token?.error ? (
              <Alert type="error" showIcon className="feishu-alert" message={data.token.error} description={data.token.advice} />
            ) : null}
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title="接入前置条件">
            <Typography.Title level={5}>回调接收</Typography.Title>
            {(data?.callback_requirements ?? []).map((item) => (
              <Typography.Paragraph key={item} className="feishu-check-item">
                <CheckCircleOutlined /> {item}
              </Typography.Paragraph>
            ))}
            <Typography.Title level={5}>发送前置条件</Typography.Title>
            {(data?.send_requirements ?? []).map((item) => (
              <Typography.Paragraph key={item} className="feishu-check-item">
                <CheckCircleOutlined /> {item}
              </Typography.Paragraph>
            ))}
            {(data?.production_notes ?? []).length ? (
              <>
                <Typography.Title level={5}>运行提示</Typography.Title>
                {(data?.production_notes ?? []).map((item) => (
                  <Typography.Paragraph key={item} type="secondary" className="feishu-check-item">
                    {item}
                  </Typography.Paragraph>
                ))}
              </>
            ) : null}
          </Card>
        </Col>
      </Row>

      <Card title="业务链路" className="dashboard-lower">
        <BusinessTrace data={data} />
      </Card>

      <Card title="企微验收链路" className="dashboard-lower">
        <AcceptanceTraceBoard data={data} />
      </Card>

      <Card title="最近企微事件" className="dashboard-lower">
        <Typography.Paragraph type="secondary" className="table-ux-hint">
          表格可横向滚动；按住表头右侧边缘可调整列宽。
        </Typography.Paragraph>
        <ResizableTable
          size="small"
          loading={loading}
          rowKey={(row) => entityKey(row.id)}
          dataSource={data?.recent_channel_events ?? []}
          columns={eventColumns}
          pagination={false}
          scroll={{ x: 1170 }}
        />
      </Card>

      <Card title="最近企微运行记录" className="dashboard-lower">
        <Typography.Paragraph type="secondary" className="table-ux-hint">
          表格可横向滚动；按住表头右侧边缘可调整列宽。
        </Typography.Paragraph>
        <ResizableTable
          size="small"
          loading={loading}
          rowKey={(row) => entityKey(row.id)}
          dataSource={data?.recent_agent_runs ?? []}
          columns={runColumns}
          pagination={false}
          scroll={{ x: 1210 }}
        />
      </Card>

      <Modal
        title="真实企业微信测试发送"
        open={realModalOpen}
        okText="确认真实发送"
        cancelText="取消"
        okButtonProps={{
          danger: true,
          disabled: !targetId || !testText || authorizationPhrase !== data?.safe_acceptance?.authorization_phrase
        }}
        confirmLoading={realLoading}
        onOk={runRealSend}
        onCancel={() => {
          setRealModalOpen(false);
          setAuthorizationPhrase("");
        }}
      >
        <Alert
          type="warning"
          showIcon
          message="这会真正向企业微信目标发送一条消息"
          description="建议先用应用单聊用户做正式验收；如果你已经确认 ChatId 可用，也可以切到群聊模式。"
        />
        <Typography.Paragraph className="feishu-form-label">目标类型</Typography.Paragraph>
        <Space>
          <Button type={targetType === "user" ? "primary" : "default"} onClick={() => setTargetType("user")}>用户</Button>
          <Button type={targetType === "chat" ? "primary" : "default"} onClick={() => setTargetType("chat")}>群聊</Button>
        </Space>
        <Typography.Paragraph className="feishu-form-label">目标 ID</Typography.Paragraph>
        <Input value={targetId} onChange={(event) => setTargetId(event.target.value)} placeholder={targetType === "chat" ? "wrxxxx / appchat id" : "zhangsan"} />
        <Typography.Paragraph className="feishu-form-label">发送内容</Typography.Paragraph>
        <Input.TextArea rows={4} value={testText} onChange={(event) => setTestText(event.target.value)} />
        <Typography.Paragraph className="feishu-form-label">手工授权短语</Typography.Paragraph>
        <Input
          value={authorizationPhrase}
          onChange={(event) => setAuthorizationPhrase(event.target.value)}
          placeholder={data?.safe_acceptance?.authorization_phrase ?? "CONFIRM WORKBUDDY REAL SEND"}
        />
      </Modal>

      <Drawer title={activeJson?.title} width={720} open={Boolean(activeJson)} onClose={() => setActiveJson(undefined)}>
        <pre className="json-block">{JSON.stringify(activeJson?.payload ?? {}, null, 2)}</pre>
      </Drawer>
    </>
  );
}

function tokenLabel(data?: WeComDiagnostics) {
  if (!data?.token?.checked) return "未检查";
  if (data.token.status === "ok") return "正常";
  if (data.token.status === "failed") return "失败";
  return data.token.status ?? "未知";
}

function renderLastSend(data?: WeComDiagnostics) {
  const lastSend = data?.recent?.last_send as Record<string, unknown> | undefined;
  if (!lastSend) return <Tag>无记录</Tag>;
  const mode = String(lastSend.mode ?? data?.send_mode ?? "-");
  const status = String(lastSend.status ?? "-");
  const targetType = String(lastSend.target_type ?? "-");
  const targetId = String(lastSend.target_id ?? "");
  return (
    <Space wrap>
      <StatusTag value={status} />
      <Tag color={mode === "real" ? "green" : "blue"}>{mode === "real" ? "真实发送" : "模拟发送"}</Tag>
      <Tag>{targetType === "chat" ? "群聊" : "用户"}</Tag>
      {targetId ? <Typography.Text code>{shortText(targetId, 28)}</Typography.Text> : null}
      {navLink("agent-runs", entityId(lastSend.id), "查看发送审计")}
    </Space>
  );
}

function BusinessTrace({ data }: { data?: WeComDiagnostics }) {
  const trace = data?.business_trace;
  if (!trace?.message && !trace?.agent_run && !trace?.business_objects?.length && !trace?.approvals?.length && !trace?.send_run) {
    return <Typography.Text type="secondary">暂无可关联的企微业务链路，给企微应用发一条测试消息后会在这里出现。</Typography.Text>;
  }

  return (
    <Space wrap className="trace-links">
      {navLink("messages", trace?.message?.id, `企微消息#${trace?.message?.id}`)}
      <Typography.Text type="secondary">→</Typography.Text>
      {trace?.conversation?.id ? <a href={hashTarget("conversations", trace.conversation.id)}>会话策略</a> : null}
      <Typography.Text type="secondary">→</Typography.Text>
      {navLink("agent-runs", trace?.agent_run?.id, `运行日志#${trace?.agent_run?.id}`)}
      <Typography.Text type="secondary">→</Typography.Text>
      {(trace?.business_objects ?? []).length ? (
        (trace?.business_objects ?? []).map((item) => (
          <span key={`${item?.type}-${item?.id}`}>
            {navLink(objectNavTarget(item?.target), item?.id, objectLinkLabel(item?.type, item?.id))}
          </span>
        ))
      ) : (
        <Typography.Text type="secondary">暂无业务对象</Typography.Text>
      )}
      <Typography.Text type="secondary">→</Typography.Text>
      {(trace?.approvals ?? []).length ? (
        (trace?.approvals ?? []).map((approval) => (
          <span key={String(approval?.id)}>{navLink("approvals", approval?.id, `查看审批#${approval?.id}`)}</span>
        ))
      ) : (
        <Typography.Text type="secondary">暂无审批</Typography.Text>
      )}
      <Typography.Text type="secondary">→</Typography.Text>
      {navLink("agent-runs", trace?.send_run?.id, `查看发送审计#${trace?.send_run?.id}`)}
    </Space>
  );
}

function AcceptanceTraceBoard({ data }: { data?: WeComDiagnostics }) {
  const traces = data?.acceptance_traces ?? [];
  const summary = data?.acceptance_summary;
  if (!traces.length) {
    return <Typography.Text type="secondary">暂无企微验收样本，发送真实企微消息后会在这里显示完整链路检查。</Typography.Text>;
  }

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Space wrap>
        <Tag color="blue">最近样本 {summary?.total ?? traces.length}</Tag>
        <Tag color="green">已闭环 {summary?.complete ?? 0}</Tag>
        <Tag color="gold">待发送/待确认 {summary?.ready ?? 0}</Tag>
        <Tag color="red">需处理 {summary?.needs_attention ?? 0}</Tag>
      </Space>
      {traces.map((trace, index) => (
        <Alert
          key={`${String(trace.message?.id ?? index)}-${String(trace.message?.received_at ?? "")}`}
          showIcon
          type={trace.status === "complete" ? "success" : trace.status === "ready" ? "info" : trace.status === "needs_action" ? "warning" : "error"}
          message={
            <Space wrap>
              <Typography.Text strong>{trace.message?.sender_name ?? "未知用户"}</Typography.Text>
              <Tag>{trace.message?.message_type_label ?? trace.message?.message_type ?? "-"}</Tag>
              <Tag color={acceptanceStatusColor(trace.status)}>{acceptanceStatusLabel(trace.status)}</Tag>
              {trace.message?.id ? navLink("messages", trace.message.id, `消息#${trace.message.id}`) : null}
            </Space>
          }
          description={
            <Space direction="vertical" size={6} style={{ width: "100%" }}>
              <Typography.Text>{shortText(String(trace.message?.text ?? trace.message_tracking?.summary ?? "-"), 160)}</Typography.Text>
              <Space wrap>
                <TraceCheck ok={trace.checklist?.message_tracked} label="消息可追踪" />
                <TraceCheck ok={trace.checklist?.routed} label="已路由" />
                <TraceCheck ok={trace.checklist?.business_object_created} label="已生成对象" />
                <TraceCheck ok={trace.checklist?.approval_created} label="已生成审批" />
                <TraceCheck ok={trace.checklist?.timeline_ready} label="时间线齐全" />
                <TraceCheck ok={trace.checklist?.send_completed} label="已发送/已闭环" />
              </Space>
              <Space wrap>
                {trace.agent_run?.id ? navLink("agent-runs", trace.agent_run.id, "运行日志") : null}
                {(trace.business_objects ?? []).map((item) => (
                  <span key={`${item?.type}-${item?.id}`}>{navLink(objectNavTarget(item?.target), item?.id, objectLinkLabel(item?.type, item?.id))}</span>
                ))}
                {(trace.approvals ?? []).map((approval) => (
                  <span key={String(approval?.id)}>{navLink("approvals", approval?.id, `审批#${approval?.id}`)}</span>
                ))}
              </Space>
              <Typography.Text type="secondary">{trace.next_action ?? "-"}</Typography.Text>
            </Space>
          }
        />
      ))}
    </Space>
  );
}

function TraceCheck({ ok, label }: { ok?: boolean; label: string }) {
  return <Tag color={ok ? "green" : "default"}>{label}{ok ? " 已完成" : " 未完成"}</Tag>;
}

function navLink(target: NavTarget, id?: EntityId, label?: string) {
  if (id === undefined || id === null || id === "") return null;
  return <a href={hashTarget(target, id)}>{label ?? String(id)}</a>;
}

function entityId(value: unknown): EntityId | undefined {
  if (typeof value === "string" || typeof value === "number") return value;
  return undefined;
}

function objectNavTarget(value?: string): NavTarget {
  if (value === "tickets" || value === "leads" || value === "tasks" || value === "candidates" || value === "knowledge" || value === "reports") return value;
  if (value === "candidate") return "candidates";
  if (value === "knowledge_gap") return "knowledge";
  if (value === "report") return "reports";
  return "messages";
}

function objectLinkLabel(type?: string, id?: EntityId) {
  const labels: Record<string, string> = {
    ticket: "查看工单",
    lead: "查看线索",
    task: "查看任务",
    candidate: "查看候选人",
    knowledge_gap: "查看知识缺口",
    report: "查看报告"
  };
  return `${labels[type ?? ""] ?? "查看对象"}#${id ?? "-"}`;
}

function acceptanceStatusLabel(value?: string) {
  if (value === "complete") return "已闭环";
  if (value === "ready") return "待发送验收";
  if (value === "needs_action") return "需补链路";
  if (value === "blocked") return "已阻塞";
  return value ?? "未知";
}

function acceptanceStatusColor(value?: string) {
  if (value === "complete") return "green";
  if (value === "ready") return "blue";
  if (value === "needs_action") return "gold";
  if (value === "blocked") return "red";
  return "default";
}
