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
import type { EntityId, FeishuAgentRun, FeishuChannelEvent, FeishuDiagnostics } from "../types";
import { entityKey, formatTime, shortText } from "../utils/format";
import { hashTarget, type NavTarget } from "../utils/navigation";

export function FeishuDiagnosticsPage() {
  const { message } = AntdApp.useApp();
  const [checkToken, setCheckToken] = useState(false);
  const [activeJson, setActiveJson] = useState<{ title: string; payload: unknown }>();
  const [mockLoading, setMockLoading] = useState(false);
  const [realLoading, setRealLoading] = useState(false);
  const [realModalOpen, setRealModalOpen] = useState(false);
  const [chatId, setChatId] = useState("");
  const [testText, setTestText] = useState("WorkBuddy OSS 飞书真实发送测试");
  const [authorizationPhrase, setAuthorizationPhrase] = useState("");
  const loadDiagnostics = useCallback(() => api.getFeishuDiagnostics(checkToken), [checkToken]);
  const { data, error, loading, reload } = useAsyncData(loadDiagnostics);

  const lastChatId = useMemo(() => {
    const recentChat = data?.recent?.last_send?.chat_id ?? data?.recent?.last_event?.conversation_external_id;
    return typeof recentChat === "string" ? recentChat : "";
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
      await api.mockFeishuSend({
        chat_id: lastChatId || "diagnostics-mock-chat",
        text: "WorkBuddy OSS 飞书模拟发送测试"
      });
      message.success("模拟发送测试已记录，不会触达飞书");
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
      await api.realFeishuTestSend({
        chat_id: chatId,
        text: testText,
        confirm_real_send: true,
        authorization_phrase: authorizationPhrase
      });
      message.success("真实发送测试成功");
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
    { title: "事件", dataIndex: "event_type", width: 280 },
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
      width: 190,
      render: (_, row) => String(row.action_json?.action_type ?? row.prompt_json?.source ?? "-")
    },
    {
      title: "结果",
      width: 220,
      render: (_, row) => {
        const output = row.model_output_json ?? {};
        const messageId = typeof output.feishu_message_id === "string" ? output.feishu_message_id : "";
        const error = row.error_message || (typeof output.error === "string" ? output.error : "");
        return error ? <Typography.Text type="danger">{shortText(error, 46)}</Typography.Text> : shortText(messageId || JSON.stringify(output), 46);
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
    },
    {
      title: "链路",
      width: 210,
      render: (_, row) => <RunLinks run={row} />
    }
  ];

  return (
    <>
      <PageHeader
        title="飞书诊断"
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
              title="Worker"
              value={data?.stream_worker?.running ? "在线" : "离线"}
              prefix={<CloudSyncOutlined />}
              valueStyle={{ color: data?.stream_worker?.running ? "#15803d" : "#b91c1c" }}
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

      <Card title="飞书正式运行检查" className="dashboard-lower">
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
      <Card title="卡片按钮回调" className="dashboard-lower">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Alert
            showIcon
            type={data?.card_callback?.ready ? "success" : "warning"}
            message={data?.card_callback?.ready ? "飞书卡片回调地址已可生成" : "飞书卡片按钮需要公网 HTTP 回调"}
            description={data?.card_callback?.diagnosis ?? "长连接 worker 不能接收飞书卡片按钮点击。"}
          />
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="飞书报错含义">
              <Typography.Text type="secondary">
                {data?.card_callback?.feishu_error_when_offline ?? "目标回调服务当前未在线"} = 飞书后台当前配置的卡片交互回调地址无法访问当前 WorkBuddy API。
              </Typography.Text>
            </Descriptions.Item>
            <Descriptions.Item label="应配置地址">
              {data?.card_callback?.callback_url ? (
                <Typography.Text code>{data.card_callback.callback_url}</Typography.Text>
              ) : (
                <Typography.Text type="secondary">
                  先配置 WORKBUDDY_PUBLIC_BASE_URL，例如 https://your-domain.example.com
                </Typography.Text>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="本地路径">
              <Typography.Text code>{data?.card_callback?.webhook_path ?? "/api/channels/feishu/webhook"}</Typography.Text>
            </Descriptions.Item>
          </Descriptions>
          <Row gutter={[12, 12]}>
            <Col xs={24} md={12}>
              <Typography.Title level={5}>前置条件</Typography.Title>
              {(data?.card_callback?.requirements ?? data?.card_callback_requirements ?? []).map((item) => (
                <Typography.Paragraph key={item} className="feishu-check-item">
                  <CheckCircleOutlined /> {item}
                </Typography.Paragraph>
              ))}
            </Col>
            <Col xs={24} md={12}>
              <Typography.Title level={5}>处理步骤</Typography.Title>
              {(data?.card_callback?.next_steps ?? []).map((item) => (
                <Typography.Paragraph key={item} className="feishu-check-item">
                  <CheckCircleOutlined /> {item}
                </Typography.Paragraph>
              ))}
            </Col>
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
                    setChatId(lastChatId);
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
              <Descriptions.Item label="配置状态">{data?.configured ? "已配置" : "缺少 App ID / Secret"}</Descriptions.Item>
              <Descriptions.Item label="API 地址">{data?.api_base_url ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="最近心跳">{formatTime(String(data?.stream_worker?.updated_at ?? ""))}</Descriptions.Item>
              <Descriptions.Item label="最近事件">
                <Space wrap>
                  <span>{String(data?.recent?.last_event?.event_type ?? "-")}</span>
                  {data?.recent?.last_event ? (
                    <Button
                      type="link"
                      size="small"
                      onClick={() => setActiveJson({ title: "最近飞书事件", payload: data.recent?.last_event })}
                    >
                      查看事件详情
                    </Button>
                  ) : null}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="最近消息">
                <Space wrap>
                  <span>{shortText(String(data?.recent?.last_message?.text ?? "-"), 80)}</span>
                  {navLink("messages", entityId(data?.recent?.last_message?.id), "查看消息")}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="会话策略">
                <Space wrap>
                  <Tag>{agentPolicyLabel(data?.business_trace?.conversation?.bound_agent)}</Tag>
                  <Tag color={sendModeColor(data?.business_trace?.conversation?.send_mode)}>
                    {sendModeLabel(data?.business_trace?.conversation?.send_mode)}
                  </Tag>
                  {data?.business_trace?.conversation?.id ? <a href={hashTarget("conversations", data.business_trace.conversation.id)}>管理会话</a> : null}
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
          <Card title="发送前置条件">
            {(data?.send_requirements ?? []).map((item) => (
              <Typography.Paragraph key={item} className="feishu-check-item">
                <CheckCircleOutlined /> {item}
              </Typography.Paragraph>
            ))}
            <Typography.Title level={5}>接收前置条件</Typography.Title>
            {(data?.receive_requirements ?? []).map((item) => (
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

      <Card title="Worker 状态与恢复" className="dashboard-lower">
        {renderWorkerRecovery(data)}
      </Card>

      <Card title="业务链路" className="dashboard-lower">
        <BusinessTrace data={data} />
      </Card>

      <Card title="飞书验收链路" className="dashboard-lower">
        <AcceptanceTraceBoard data={data} />
      </Card>

      <Card title="最近飞书事件" className="dashboard-lower">
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

      <Card title="最近飞书运行记录" className="dashboard-lower">
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
          scroll={{ x: 1230 }}
        />
      </Card>

      <Modal
        title="真实飞书测试发送"
        open={realModalOpen}
        okText="确认真实发送"
        cancelText="取消"
        okButtonProps={{
          danger: true,
          disabled: !chatId || !testText || authorizationPhrase !== data?.safe_acceptance?.authorization_phrase
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
          message="这会真正向飞书会话发送一条消息"
          description="建议使用最近一条测试消息的 chat_id，或从飞书诊断页复制最近事件里的会话 ID。"
        />
        <Typography.Paragraph className="feishu-form-label">chat_id</Typography.Paragraph>
        <Input value={chatId} onChange={(event) => setChatId(event.target.value)} placeholder="oc_xxx" />
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

function tokenLabel(data?: FeishuDiagnostics) {
  if (!data?.token?.checked) return "未检查";
  if (data.token.status === "ok") return "正常";
  if (data.token.status === "failed") return "失败";
  return data.token.status ?? "未知";
}

function messageTypeLabel(value?: string) {
  const labels: Record<string, string> = {
    text: "文本",
    image: "图片",
    file: "文件",
    audio: "语音",
    media: "视频",
    post: "富文本",
    interactive: "互动卡片",
    share_chat: "分享会话",
    sticker: "表情"
  };
  return labels[value ?? ""] ?? value ?? "-";
}

function messageTypeColor(value?: string) {
  if (value === "image") return "blue";
  if (value === "file") return "purple";
  if (value === "post") return "gold";
  if (value === "interactive") return "orange";
  if (value === "audio" || value === "media") return "cyan";
  return "default";
}

function renderLastSend(data?: FeishuDiagnostics) {
  const lastSend = data?.recent?.last_send;
  if (!lastSend) return <Tag>无记录</Tag>;
  const mode = String(lastSend.mode ?? data?.send_mode ?? "-");
  const status = String(lastSend.status ?? "-");
  const messageId = String(lastSend.feishu_message_id ?? "");
  return (
    <Space wrap>
      <StatusTag value={status} />
      <Tag color={mode === "real" ? "green" : "blue"}>{mode === "real" ? "真实发送" : "模拟发送"}</Tag>
      {messageId ? <Typography.Text code>{shortText(messageId, 28)}</Typography.Text> : null}
      {navLink("agent-runs", lastSend.id as EntityId | undefined, "查看发送审计")}
    </Space>
  );
}

function renderWorkerRecovery(data?: FeishuDiagnostics) {
  const worker = data?.stream_worker;
  const recentEvents = worker?.recent_events ?? [];
  const recentErrors = worker?.recent_errors ?? [];
  if (!worker) return <Typography.Text type="secondary">暂无 worker 状态。</Typography.Text>;
  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Alert
        showIcon
        type={worker.health_level === "ok" ? "success" : worker.health_level === "warning" ? "warning" : "error"}
        message={worker.health_message ?? "Worker 状态未知"}
        description={worker.last_error ? `最近错误：${worker.last_error}` : worker.note}
      />
      <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }}>
        <Descriptions.Item label="状态">{worker.status ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="进程">{worker.running ? "运行中" : "未运行"}</Descriptions.Item>
        <Descriptions.Item label="真实接收">{worker.receiving_real_messages ? "可接收" : "不可接收"}</Descriptions.Item>
        <Descriptions.Item label="最近心跳">{formatTime(worker.last_heartbeat_at ?? worker.updated_at ?? "")}</Descriptions.Item>
        <Descriptions.Item label="心跳间隔">{worker.seconds_since_heartbeat ?? "-"} 秒前</Descriptions.Item>
        <Descriptions.Item label="心跳次数">{worker.heartbeat_count ?? 0}</Descriptions.Item>
        <Descriptions.Item label="最近成功">{formatTime(worker.last_success_at ?? "")}</Descriptions.Item>
        <Descriptions.Item label="最近失败">{formatTime(worker.last_failure_at ?? "")}</Descriptions.Item>
      </Descriptions>
      <Space wrap>
        {worker.check_command ? <Typography.Text code>{worker.check_command}</Typography.Text> : null}
        {worker.run_command ? <Typography.Text code>{worker.run_command}</Typography.Text> : null}
        {worker.compose_command ? <Typography.Text code>{worker.compose_command}</Typography.Text> : null}
      </Space>
      {(worker.recovery_steps ?? []).length ? (
        <div>
          <Typography.Title level={5}>恢复步骤</Typography.Title>
          {(worker.recovery_steps ?? []).map((step) => (
            <Typography.Paragraph key={step} className="feishu-check-item">
              <CheckCircleOutlined /> {step}
            </Typography.Paragraph>
          ))}
        </div>
      ) : null}
      {recentErrors.length ? (
        <div>
          <Typography.Title level={5}>最近错误</Typography.Title>
          <Space direction="vertical" size={8} style={{ width: "100%" }}>
            {recentErrors.slice(0, 4).map((item, index) => (
              <Alert
                key={`${String(item.occurred_at ?? index)}-${String(item.payload_hash ?? "")}`}
                type="error"
                showIcon
                message={`${String(item.event_type ?? "-")} / ${formatTime(String(item.occurred_at ?? ""))}`}
                description={shortText(String(item.error ?? item.recovery_hint ?? "-"), 180)}
              />
            ))}
          </Space>
        </div>
      ) : null}
      {recentEvents.length ? (
        <div>
          <Typography.Title level={5}>最近处理事件</Typography.Title>
          <Space wrap>
            {recentEvents.slice(0, 8).map((item, index) => (
              <Tag key={`${String(item.occurred_at ?? index)}-${String(item.kind ?? "")}`} color={item.status === "success" ? "green" : item.status === "ignored" ? "default" : "red"}>
                {String(item.event_type ?? "-")} / {String(item.kind ?? "-")} / {formatTime(String(item.occurred_at ?? ""))}
              </Tag>
            ))}
          </Space>
        </div>
      ) : null}
    </Space>
  );
}

function BusinessTrace({ data }: { data?: FeishuDiagnostics }) {
  const trace = data?.business_trace;
  if (!trace?.message && !trace?.agent_run && !trace?.business_objects?.length && !trace?.approvals?.length && !trace?.send_run) {
    return <Typography.Text type="secondary">暂无可关联的飞书业务链路，给机器人发送一条测试消息后会在这里出现。</Typography.Text>;
  }

  return (
    <Space wrap className="trace-links">
      {navLink("messages", trace?.message?.id, `飞书消息#${trace?.message?.id}`)}
      <Typography.Text type="secondary">→</Typography.Text>
      {trace?.conversation ? (
        <Space size={4}>
          <a href={hashTarget("conversations", trace.conversation.id)}>会话策略</a>
          <Tag>{agentPolicyLabel(trace.conversation.bound_agent)}</Tag>
          <Tag color={sendModeColor(trace.conversation.send_mode)}>{sendModeLabel(trace.conversation.send_mode)}</Tag>
        </Space>
      ) : null}
      <Typography.Text type="secondary">→</Typography.Text>
      {navLink("agent-runs", trace?.agent_run?.id, `运行日志#${trace?.agent_run?.id}`)}
      <Typography.Text type="secondary">→</Typography.Text>
      {(trace?.business_objects ?? []).length ? (
        (trace?.business_objects ?? []).map((item) => (
          <span key={`${item.type}-${item.id}`}>
            {navLink(objectNavTarget(item.target), item.id, objectLinkLabel(item.type, item.id))}
          </span>
        ))
      ) : (
        <Typography.Text type="secondary">暂无业务对象</Typography.Text>
      )}
      <Typography.Text type="secondary">→</Typography.Text>
      {(trace?.approvals ?? []).length ? (
        (trace?.approvals ?? []).map((approval) => (
          <span key={String(approval.id)}>{navLink("approvals", approval.id, `查看审批#${approval.id}`)}</span>
        ))
      ) : (
        <Typography.Text type="secondary">暂无审批</Typography.Text>
      )}
      <Typography.Text type="secondary">→</Typography.Text>
      {navLink("agent-runs", trace?.send_run?.id, `查看发送审计#${trace?.send_run?.id}`)}
    </Space>
  );
}

function AcceptanceTraceBoard({ data }: { data?: FeishuDiagnostics }) {
  const traces = data?.acceptance_traces ?? [];
  const summary = data?.acceptance_summary;
  if (!traces.length) {
    return <Typography.Text type="secondary">暂无飞书验收样本，发送真实飞书消息后会在这里显示完整链路检查。</Typography.Text>;
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
              <Tag color={messageTypeColor(trace.message?.message_type)}>{trace.message?.message_type_label ?? messageTypeLabel(trace.message?.message_type)}</Tag>
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

function RunLinks({ run }: { run: FeishuAgentRun }) {
  const links = run.links ?? {};
  return (
    <Space wrap size={2}>
      {navLink("agent-runs", run.id, "运行")}
      {navLink("messages", links.message_id ?? run.message_id, "消息")}
      {navLink("approvals", links.approval_id, "审批")}
      {navLink("leads", links.lead_id, "线索")}
      {navLink("tickets", links.ticket_id, "工单")}
      {navLink("tasks", links.task_id, "任务")}
    </Space>
  );
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

function agentPolicyLabel(value?: string) {
  const labels: Record<string, string> = {
    auto: "自动判断",
    support_ticket_agent: "固定客服工单",
    sales_lead_agent: "固定销售线索",
    community_ops_agent: "固定私域社群",
    recruiting_hr_agent: "固定招聘入职"
  };
  return labels[value ?? "auto"] ?? value ?? "自动判断";
}

function sendModeLabel(value?: string) {
  const labels: Record<string, string> = {
    inherit: "跟随全局发送",
    mock: "只模拟发送",
    real: "允许真实发送",
    disabled: "禁止发送"
  };
  return labels[value ?? "inherit"] ?? value ?? "跟随全局发送";
}

function sendModeColor(value?: string) {
  if (value === "real") return "green";
  if (value === "mock") return "blue";
  if (value === "disabled") return "red";
  return "default";
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
