import {
  CheckCircleOutlined,
  CloudSyncOutlined,
  ExperimentOutlined,
  SendOutlined,
  WarningOutlined
} from "@ant-design/icons";
import { Alert, App as AntdApp, Button, Card, Col, Descriptions, Divider, Row, Space, Steps, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { PageHeader } from "../components/PageHeader";
import { ReloadButton } from "../components/ReloadButton";
import { useAsyncData } from "../components/useAsyncData";
import type { DemoPrepareResult, FeishuConversation } from "../types";
import { formatTime, shortText } from "../utils/format";
import { hashTarget, type NavTarget } from "../utils/navigation";

const suggestedSteps: Array<{ title: string; description: string; target: NavTarget }> = [
  { title: "消息导入", description: "导入客服、销售、社群、招聘样例消息，形成 MessageEvent。", target: "import" },
  { title: "路由审计", description: "检查消息事件里的意图、风险、目标 Agent 和 AgentRun。", target: "messages" },
  { title: "业务对象", description: "统一查看 Ticket、Lead、Task、Candidate、Knowledge 和 Report。", target: "objects" },
  { title: "工单流转", description: "筛选高优先级工单，推进处理中、解决或关闭。", target: "tickets" },
  { title: "线索推进", description: "查看销售漏斗，并把线索推进到已联系、方案或成交。", target: "leads" },
  { title: "社群运营", description: "查看高意向用户、风险消息、社群任务和群日报。", target: "community" },
  { title: "候选入职", description: "查看匹配分析、面试问题和入职 Checklist。", target: "candidates" },
  { title: "知识沉淀", description: "采纳或忽略 KnowledgeGap，并发布或归档 KnowledgeItem。", target: "knowledge" },
  { title: "报告生成", description: "生成客服、销售、社群、招聘、知识缺口和业务运营报告。", target: "reports" },
  { title: "审批审计", description: "确认对外回复进入审批队列，发送行为留有审计记录。", target: "agent-runs" }
];

const quickLinks: Array<{ label: string; target: NavTarget }> = [
  { label: "业务对象", target: "objects" },
  { label: "客服工单", target: "tickets" },
  { label: "销售线索", target: "leads" },
  { label: "社群运营", target: "community" },
  { label: "知识沉淀", target: "knowledge" },
  { label: "报告中心", target: "reports" },
  { label: "候选入职", target: "candidates" },
  { label: "运行日志", target: "agent-runs" }
];

const objectLabels: Record<string, string> = {
  messages: "消息事件",
  tickets: "客服工单",
  leads: "销售线索",
  tasks: "跟进任务",
  candidates: "候选入职",
  knowledge_gaps: "知识缺口",
  knowledge_items: "知识条目",
  reports: "报告",
  approvals: "审批",
  agent_runs: "运行日志"
};

const reportLabels: Record<string, string> = {
  operations_daily: "业务运营日报",
  support_daily: "客服日报",
  sales_daily: "销售日报",
  community_daily: "社群日报",
  recruiting_progress: "招聘进度报告",
  knowledge_gap: "知识缺口报告"
};

export function DemoModePage() {
  const { message } = AntdApp.useApp();
  const { data: dashboard, error: dashboardError, loading: dashboardLoading, reload: reloadDashboard } = useAsyncData(api.getDashboard);
  const { data: businessObjects, error: businessError, loading: businessLoading, reload: reloadBusinessObjects } = useAsyncData(api.getBusinessObjects);
  const { data: feishuStatus, reload: reloadFeishu } = useAsyncData(api.getFeishuStatus);
  const { data: conversations, reload: reloadConversations } = useAsyncData(api.getFeishuConversations);
  const [prepareResult, setPrepareResult] = useState<DemoPrepareResult>();
  const [preparing, setPreparing] = useState(false);
  const [mockingId, setMockingId] = useState<string | number>();

  const riskyConversations = useMemo(
    () => (conversations?.items ?? []).filter((item) => item.send_mode === "real"),
    [conversations]
  );
  const businessCounts = businessObjects?.counts ?? {};
  const businessObjectTotal = sumCounts(businessCounts, ["tickets", "leads", "tasks", "candidates", "knowledge_gaps", "knowledge_items", "reports"]);

  const reloadAll = async () => {
    await Promise.all([reloadDashboard(), reloadBusinessObjects(), reloadFeishu(), reloadConversations()]);
  };

  const prepareDemo = async () => {
    setPreparing(true);
    try {
      const result = await api.prepareDemo();
      setPrepareResult(result);
      message.success("v0.10 Beta 验收环境已准备好");
      await reloadAll();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "准备演示环境失败");
    } finally {
      setPreparing(false);
    }
  };

  const forceMockConversation = async (conversation: FeishuConversation) => {
    setMockingId(conversation.id);
    try {
      await api.updateConversationPolicy(conversation.id, { send_mode: "mock" });
      message.success("当前会话已切换为只模拟发送");
      await Promise.all([reloadConversations(), reloadFeishu()]);
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "切换会话发送策略失败");
    } finally {
      setMockingId(undefined);
    }
  };

  return (
    <>
      <PageHeader
        title="演示模式"
        extra={
          <>
            <Button icon={<ExperimentOutlined />} type="primary" loading={preparing} onClick={prepareDemo}>
              一键准备 Beta 验收
            </Button>
            <ReloadButton loading={dashboardLoading || businessLoading} onReload={() => { void reloadAll(); }} />
          </>
        }
      />
      <ApiErrorAlert error={dashboardError ?? businessError} />

      <Alert
        className="api-alert"
        type={feishuStatus?.external_send_enabled ? "warning" : "info"}
        showIcon
        message={feishuStatus?.external_send_enabled ? "当前全局外部发送已开启" : "当前为安全演示模式"}
        description={feishuStatus?.external_send_enabled
          ? "演示前建议确认本轮是否真的要回复飞书用户；如果只是展示流程，请把当前测试会话切到只模拟发送。"
          : "全局外部发送关闭时，审批发送会生成发送审计，但不会触达飞书。"}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={8}>
          <Card title="当前演示状态">
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="阶段">v0.14.0 Agent Runtime</Descriptions.Item>
              <Descriptions.Item label="飞书 Worker">
                <Tag color={feishuStatus?.stream_worker?.running ? "green" : "red"} icon={<CloudSyncOutlined />}>
                  {feishuStatus?.stream_worker?.running ? "在线" : "离线"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="最近心跳">{formatTime(feishuStatus?.stream_worker?.updated_at)}</Descriptions.Item>
              <Descriptions.Item label="全局发送模式">
                <Tag color={feishuStatus?.send_mode === "real" ? "orange" : "blue"} icon={<SendOutlined />}>
                  {feishuStatus?.send_mode === "real" ? "真实发送" : "模拟发送"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="外部发送开关">
                {feishuStatus?.external_send_enabled ? "ENABLE_EXTERNAL_SEND=true" : "ENABLE_EXTERNAL_SEND=false"}
              </Descriptions.Item>
              <Descriptions.Item label="最近飞书消息">
                {shortText(String(feishuStatus?.recent?.last_message?.text ?? "-"), 54)}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="当前数据">
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="业务对象合计">{businessObjectTotal}</Descriptions.Item>
              <Descriptions.Item label="消息事件">{dashboard?.message_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="待审批">{dashboard?.pending_approval_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="客服工单">{dashboard?.ticket_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="销售线索">{dashboard?.lead_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="跟进任务">{dashboard?.task_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="候选入职">{dashboard?.candidate_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="知识缺口">{dashboard?.knowledge_gap_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="知识条目">{dashboard?.knowledge_item_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="报告">{dashboard?.report_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="运行日志">{dashboard?.agent_run_count ?? 0}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="Alpha 验收入口">
            <Space wrap>
              {quickLinks.map((link) => (
                <Button key={link.target} href={hashTarget(link.target)}>
                  {link.label}
                </Button>
              ))}
            </Space>
            <Divider />
            <Typography.Text type="secondary">下一条测试消息</Typography.Text>
            <Typography.Paragraph copyable>
              {prepareResult?.next_message ?? "群里有人吗？我想报名训练营，怎么买？"}
            </Typography.Paragraph>
            <Space wrap>
              <Button href={hashTarget("feishu")}>飞书诊断</Button>
              <Button href={hashTarget("conversations")}>会话策略</Button>
            </Space>
          </Card>
        </Col>
      </Row>

      {riskyConversations.length > 0 ? (
        <Alert
          className="dashboard-lower"
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          message="有会话被设置为允许真实发送"
          description={
            <Space direction="vertical" size={8}>
              {riskyConversations.map((conversation) => (
                <Space key={String(conversation.id)} wrap>
                  <Typography.Text strong>{conversation.name ?? conversation.short_id ?? conversation.id}</Typography.Text>
                  <Typography.Text type="secondary">{conversation.short_id}</Typography.Text>
                  <Button
                    size="small"
                    loading={mockingId === conversation.id}
                    onClick={() => forceMockConversation(conversation)}
                  >
                    切换为只模拟发送
                  </Button>
                </Space>
              ))}
            </Space>
          }
        />
      ) : null}

      <Row gutter={[16, 16]} className="dashboard-lower">
        <Col xs={24} xl={14}>
          <Card title="v0.10 真实验收路径">
            <Steps
              direction="vertical"
              current={-1}
              items={suggestedSteps.map((step) => ({
                title: step.title,
                description: (
                  <Space direction="vertical" size={4}>
                    <Typography.Text>{step.description}</Typography.Text>
                    <a href={hashTarget(step.target)}>打开页面</a>
                  </Space>
                )
              }))}
            />
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title="准备结果">
            {prepareResult ? (
              <>
                <Space wrap>
                  <Tag color="green" icon={<CheckCircleOutlined />}>已准备</Tag>
                  <Typography.Text type="secondary">本地 Alpha 数据已恢复，飞书历史保留</Typography.Text>
                </Space>
                <Divider />
                <Descriptions size="small" column={1}>
                  <Descriptions.Item label="导入批次">{prepareResult.imported_batches?.length ?? 0}</Descriptions.Item>
                  <Descriptions.Item label="业务对象合计">{prepareResult.business_object_total ?? 0}</Descriptions.Item>
                  <Descriptions.Item label="知识条目沉淀">{prepareResult.promoted_knowledge_items?.length ?? 0}</Descriptions.Item>
                  <Descriptions.Item label="生成报告">{prepareResult.generated_reports?.length ?? 0}</Descriptions.Item>
                  <Descriptions.Item label="恢复会话策略">{prepareResult.restored_conversations?.length ?? 0}</Descriptions.Item>
                </Descriptions>
                <Divider />
                {prepareResult.validation_report ? (
                  <>
                    <Typography.Text strong>{prepareResult.validation_report.title}</Typography.Text>
                    <Descriptions size="small" column={1}>
                      <Descriptions.Item label="通过项">
                        {prepareResult.validation_report.passed ?? 0}/{prepareResult.validation_report.total ?? 0}
                      </Descriptions.Item>
                      <Descriptions.Item label="Beta 状态">
                        <Tag color={prepareResult.validation_report.ready_for_beta ? "green" : "orange"}>
                          {prepareResult.validation_report.ready_for_beta ? "可验收" : "需补齐"}
                        </Tag>
                      </Descriptions.Item>
                    </Descriptions>
                    <Space direction="vertical" size={4} style={{ width: "100%" }}>
                      {(prepareResult.validation_report.checks ?? []).map((check) => (
                        <Space key={check.key} style={{ justifyContent: "space-between", width: "100%" }}>
                          <Typography.Text>{check.label}</Typography.Text>
                          <Space>
                            <Typography.Text type="secondary">{check.detail}</Typography.Text>
                            <Tag color={check.status === "passed" ? "green" : "red"}>{check.status === "passed" ? "通过" : "失败"}</Tag>
                          </Space>
                        </Space>
                      ))}
                    </Space>
                    <Divider />
                  </>
                ) : null}
                <Divider />
                <Typography.Text strong>本次导入生成</Typography.Text>
                <Descriptions size="small" column={1}>
                  {Object.entries(prepareResult.created_from_import ?? {}).map(([key, value]) => (
                    <Descriptions.Item key={key} label={objectLabels[key] ?? key}>{value}</Descriptions.Item>
                  ))}
                </Descriptions>
                <Divider />
                <Typography.Text strong>报告</Typography.Text>
                <Space wrap className="demo-report-list">
                  {(prepareResult.generated_reports ?? []).map((report) => (
                    <Tag key={String(report.id)}>{reportLabels[String(report.report_type)] ?? report.title ?? report.report_type}</Tag>
                  ))}
                </Space>
                <Divider />
                <Typography.Text strong>推荐链路</Typography.Text>
                <Typography.Paragraph type="secondary">
                  {(prepareResult.recommended_flow ?? []).map((item) => item.label).join(" -> ")}
                </Typography.Paragraph>
              </>
            ) : (
              <Typography.Text type="secondary">
                点击“一键准备 Beta 验收”后，这里会显示本次恢复了哪些对象、生成了哪些报告，以及下一步验收建议。
              </Typography.Text>
            )}
          </Card>
        </Col>
      </Row>
    </>
  );
}

function sumCounts(counts: Record<string, number>, keys: string[]) {
  return keys.reduce((total, key) => total + (counts[key] ?? 0), 0);
}
