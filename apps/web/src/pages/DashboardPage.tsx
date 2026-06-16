import { Alert, App as AntdApp, Button, Card, Col, Descriptions, Row, Space, Statistic, Table, Tag, Typography } from "antd";
import {
  AuditOutlined,
  CheckSquareOutlined,
  FileTextOutlined,
  ImportOutlined,
  MessageOutlined,
  PhoneOutlined,
  ReadOutlined,
  ScheduleOutlined,
  TeamOutlined,
  ToolOutlined
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useCallback } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { PageHeader } from "../components/PageHeader";
import { ReloadButton } from "../components/ReloadButton";
import { StatusTag } from "../components/StatusTag";
import { useAsyncData } from "../components/useAsyncData";
import type { Approval, AuditLog, FollowupTask } from "../types";
import { entityKey, formatTime, shortText } from "../utils/format";
import { hashTarget } from "../utils/navigation";

const demoFlow = [
  { key: "1", step: "接收消息", output: "飞书 / CSV / Webhook 进入统一 MessageEvent" },
  { key: "2", step: "路由判断", output: "Router 识别场景并生成 AgentRun" },
  { key: "3", step: "生成对象", output: "Ticket / Lead / Task / Candidate / KnowledgeGap" },
  { key: "4", step: "审批与发送", output: "对外草稿进入审批，再按策略发送" },
  { key: "5", step: "人工处理", output: "负责人跟进、留痕、更新时间线和审计" }
];

export function DashboardPage() {
  const { message } = AntdApp.useApp();
  const { data, error, loading, reload } = useAsyncData(api.getDashboard);
  const { data: operations, error: operationsError, loading: operationsLoading, reload: reloadOperations } = useAsyncData(api.getOperationsSummary);
  const { data: workbench, error: workbenchError, loading: workbenchLoading, reload: reloadWorkbench } = useAsyncData(api.getWorkbenchSummary);
  const loadAuditLogs = useCallback(() => api.getAuditLogs({ limit: 10 }), []);
  const { data: auditLogs, error: auditError, loading: auditLoading, reload: reloadAudit } = useAsyncData(loadAuditLogs);
  const { data: feishuStatus, reload: reloadFeishu } = useAsyncData(api.getFeishuStatus);

  const resetDemo = async () => {
    try {
      await api.resetDemo();
      message.success("Demo 数据已重置");
      await Promise.all([reload(), reloadOperations(), reloadWorkbench(), reloadAudit(), reloadFeishu()]);
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "重置 Demo 数据失败");
    }
  };

  const taskColumns: ColumnsType<FollowupTask> = [
    { title: "任务", dataIndex: "title", width: 220, render: (value) => shortText(value, 80) },
    { title: "状态", dataIndex: "status", width: 110, render: (value) => <StatusTag value={value} /> },
    { title: "优先级", dataIndex: "priority", width: 110, render: (value) => <StatusTag value={value} /> },
    {
      title: "截止",
      dataIndex: "due_at",
      width: 160,
      render: (value, row) => value ? (
        <Space>
          <span>{formatTime(value)}</span>
          {row.is_overdue ? <Tag color="red">逾期</Tag> : null}
        </Space>
      ) : (row.due_hint ?? "-")
    },
    {
      title: "入口",
      width: 100,
      render: (_, row) => <a href={hashTarget("tasks", row.id)}>查看</a>
    }
  ];

  const approvalColumns: ColumnsType<Approval> = [
    { title: "审批", width: 220, render: (_, row) => shortText(row.business_object_label ?? row.original_message ?? `审批#${row.id}`, 70) },
    { title: "Agent", dataIndex: "target_agent", width: 150, render: (value) => value ?? "-" },
    { title: "风险", dataIndex: "risk_level", width: 100, render: (value) => <StatusTag value={value} /> },
    { title: "创建时间", dataIndex: "created_at", width: 160, render: formatTime },
    { title: "入口", width: 100, render: (_, row) => <a href={hashTarget("approvals", row.id)}>审批</a> }
  ];

  const auditColumns: ColumnsType<AuditLog> = [
    { title: "时间", dataIndex: "created_at", width: 160, render: formatTime },
    { title: "操作人", width: 160, render: (_, row) => row.operator_user?.display_name ?? row.operator_name ?? "-" },
    { title: "动作", dataIndex: "action_type", width: 180 },
    { title: "摘要", dataIndex: "summary", render: (value) => shortText(value, 120) }
  ];

  return (
    <>
      <PageHeader
        title="工作台"
        extra={
          <>
            <Button onClick={resetDemo}>重置 Demo 数据</Button>
            <ReloadButton
              loading={loading || operationsLoading || workbenchLoading || auditLoading}
              onReload={() => {
                void Promise.all([reload(), reloadOperations(), reloadWorkbench(), reloadAudit(), reloadFeishu()]);
              }}
            />
          </>
        }
      />
      <ApiErrorAlert error={error ?? operationsError ?? workbenchError ?? auditError} />
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card><Statistic title="消息" value={data?.message_count ?? 0} prefix={<MessageOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card><Statistic title="待审批" value={data?.pending_approval_count ?? 0} prefix={<CheckSquareOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card><Statistic title="工单" value={data?.ticket_count ?? 0} prefix={<ToolOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card><Statistic title="线索" value={data?.lead_count ?? 0} prefix={<PhoneOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card><Statistic title="跟进任务" value={data?.task_count ?? 0} prefix={<ScheduleOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card><Statistic title="候选人" value={data?.candidate_count ?? 0} prefix={<TeamOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card><Statistic title="知识缺口" value={data?.knowledge_gap_count ?? 0} prefix={<ReadOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card><Statistic title="报告" value={data?.report_count ?? 0} prefix={<FileTextOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card><Statistic title="运行日志" value={data?.agent_run_count ?? 0} prefix={<AuditOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card><Statistic title="今日导入" value={data?.today_import_count ?? 0} prefix={<ImportOutlined />} /></Card>
        </Col>
      </Row>
      <Row gutter={[16, 16]} className="dashboard-lower">
        <Col xs={24} lg={10}>
          <Card title="我的工作台">
            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              <Alert
                type="info"
                showIcon
                message={`当前操作人：${workbench?.current_user?.display_name ?? "本地管理员"}`}
                description={(
                  <Space wrap>
                    <span>@{workbench?.current_user?.username ?? "local_admin"}</span>
                    <span>角色 {workbench?.current_user?.role ?? "admin"}</span>
                    <span>这块数据跟着左下角当前操作人切换</span>
                  </Space>
                )}
              />
              <Row gutter={12}>
                <Col span={8}><Statistic title="我的待办" value={workbench?.summary?.my_open_tasks ?? 0} /></Col>
                <Col span={8}><Statistic title="我的逾期" value={workbench?.summary?.my_overdue_tasks ?? 0} /></Col>
                <Col span={8}><Statistic title="我的审批" value={workbench?.summary?.my_pending_approvals ?? 0} /></Col>
              </Row>
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="未分配任务">{workbench?.summary?.unassigned_tasks ?? 0}</Descriptions.Item>
                <Descriptions.Item label="最近动作">{workbench?.summary?.recent_actions ?? 0}</Descriptions.Item>
                <Descriptions.Item label="建议入口">
                  <Space wrap>
                    <a href={hashTarget("tasks")}>处理任务</a>
                    <a href={hashTarget("approvals")}>审批队列</a>
                    <a href={hashTarget("team")}>团队成员</a>
                  </Space>
                </Descriptions.Item>
              </Descriptions>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="四大 Agent 总览">
            <Row gutter={[12, 12]}>
              {(operations?.agent_overview ?? []).map((agent) => (
                <Col xs={24} md={12} xl={6} key={agent.agent_type}>
                  <Card size="small">
                    <Space direction="vertical" size={8} style={{ width: "100%" }}>
                      <Space style={{ justifyContent: "space-between", width: "100%" }}>
                        <Typography.Text strong>{agent.label}</Typography.Text>
                        <a href={agent.entry ?? "#dashboard"}>进入</a>
                      </Space>
                      <Row gutter={8}>
                        <Col span={12}><Statistic title="对象" value={agent.object_count ?? 0} /></Col>
                        <Col span={12}><Statistic title="待处理" value={agent.pending_count ?? 0} /></Col>
                      </Row>
                      <Space wrap>
                        <Tag color={(agent.risk_count ?? 0) > 0 ? "red" : "green"}>风险 {agent.risk_count ?? 0}</Tag>
                        <Tag color="blue">审批 {agent.approval_count ?? 0}</Tag>
                        <Tag>报告 {agent.report_count ?? 0}</Tag>
                      </Space>
                    </Space>
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
        <Col xs={24}>
          <Alert
            type={(operations?.risk_inbox?.total ?? 0) > 0 ? "warning" : "success"}
            showIcon
            message={`待处理风险聚合：${operations?.risk_inbox?.total ?? 0} 项`}
            description={(
              <Space wrap>
                <span>工单 {(operations?.risk_inbox?.support_risks ?? []).length}</span>
                <span>线索 {(operations?.risk_inbox?.sales_risks ?? []).length}</span>
                <span>知识 {(operations?.risk_inbox?.knowledge_risks ?? []).length}</span>
                <span>审批 {(operations?.risk_inbox?.approval_risks ?? []).length}</span>
                <a href={hashTarget("approvals")}>查看审批</a>
                <a href={hashTarget("audit")}>查看审计</a>
              </Space>
            )}
          />
        </Col>
        <Col xs={24} lg={12}>
          <Card title="我的待办与逾期" extra={<a href={hashTarget("tasks")}>全部任务</a>}>
            <Table
              size="small"
              rowKey={(row) => entityKey(row.id)}
              pagination={false}
              dataSource={(workbench?.my_tasks ?? []).slice(0, 6)}
              columns={taskColumns}
              scroll={{ x: 760 }}
              locale={{ emptyText: "当前操作人还没有待办任务" }}
            />
            {(workbench?.my_overdue_tasks?.length ?? 0) > 0 ? (
              <Typography.Paragraph type="warning" style={{ marginTop: 12, marginBottom: 0 }}>
                有 {workbench?.my_overdue_tasks?.length ?? 0} 条任务已逾期，建议先处理。
              </Typography.Paragraph>
            ) : null}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="我的审批" extra={<a href={hashTarget("approvals")}>审批队列</a>}>
            <Table
              size="small"
              rowKey={(row) => entityKey(row.id)}
              pagination={false}
              dataSource={(workbench?.my_pending_approvals ?? []).slice(0, 6)}
              columns={approvalColumns}
              scroll={{ x: 760 }}
              locale={{ emptyText: "当前账号没有可处理审批" }}
            />
          </Card>
        </Col>
        <Col xs={24}>
          <Card title="待认领任务" extra={<a href={hashTarget("tasks")}>任务池</a>}>
            <Table
              size="small"
              rowKey={(row) => entityKey(row.id)}
              pagination={false}
              dataSource={(workbench?.unassigned_tasks ?? []).slice(0, 6)}
              columns={taskColumns}
              scroll={{ x: 760 }}
              locale={{ emptyText: "当前没有未分配任务" }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="统一操作审计" extra={<a href={hashTarget("audit")}>查看总账</a>}>
            <Table
              size="small"
              rowKey={(row) => entityKey(row.id)}
              pagination={false}
              dataSource={auditLogs?.items ?? []}
              columns={auditColumns}
              scroll={{ x: 820 }}
              locale={{ emptyText: "还没有审计记录" }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="飞书连接" extra={<Tag color={feishuStatus?.stream_worker?.running ? "green" : "red"}>{feishuStatus?.stream_worker?.running ? "在线" : "离线"}</Tag>}>
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="发送模式">{feishuStatus?.send_mode === "real" ? "真实发送" : "模拟发送"}</Descriptions.Item>
              <Descriptions.Item label="外部发送">{feishuStatus?.external_send_enabled ? "已开启" : "已关闭"}</Descriptions.Item>
              <Descriptions.Item label="最近心跳">{formatTime(feishuStatus?.stream_worker?.updated_at)}</Descriptions.Item>
              <Descriptions.Item label="最近事件">{String(feishuStatus?.recent?.last_event?.event_type ?? "-")}</Descriptions.Item>
              <Descriptions.Item label="最近消息">{shortText(String(feishuStatus?.recent?.last_message?.text ?? "-"), 36)}</Descriptions.Item>
              <Descriptions.Item label="最近发送">
                <Space>
                  <span>{String(feishuStatus?.recent?.last_send?.channel ?? "-")}</span>
                  <Tag>{String(feishuStatus?.recent?.last_send?.mode ?? "未发送")}</Tag>
                </Space>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="正式工作流闭环">
            <Table
              size="small"
              pagination={false}
              dataSource={demoFlow}
              columns={[
                { title: "环节", dataIndex: "step", width: 120 },
                { title: "产物", dataIndex: "output" }
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="运营概览">
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="待处理工单">{operations?.support?.open_tickets ?? 0}</Descriptions.Item>
              <Descriptions.Item label="高优先级工单">{operations?.support?.high_priority_open_tickets ?? 0}</Descriptions.Item>
              <Descriptions.Item label="超时风险">{operations?.support?.stale_open_tickets ?? 0}</Descriptions.Item>
              <Descriptions.Item label="Top Lead">{operations?.sales?.top_leads?.[0]?.customer_name ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="待处理知识缺口">{operations?.knowledge?.pending_gaps ?? 0}</Descriptions.Item>
              <Descriptions.Item label="最近报告">
                {(operations?.reports?.latest ?? []).slice(0, 2).map((report) => (
                  <div key={String(report.id)}>{reportLabel(report.report_type)} #{report.id}</div>
                ))}
              </Descriptions.Item>
            </Descriptions>
          </Card>
          <Alert
            style={{ marginTop: 16 }}
            type="info"
            showIcon
            message="当前为正式产品主线中的团队工作台"
            description="这里现在不仅看总数，还按当前操作人展示待办、审批、逾期和统一审计，开始具备真实团队分工的基本面。"
          />
        </Col>
      </Row>
    </>
  );
}

function reportLabel(value?: string) {
  const labels: Record<string, string> = {
    operations_daily: "业务运营",
    support_daily: "客服日报",
    sales_daily: "销售日报",
    community_daily: "社群日报",
    recruiting_progress: "招聘进度",
    knowledge_gap: "知识缺口"
  };
  return labels[value ?? ""] ?? value ?? "报告";
}
