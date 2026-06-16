import {
  AuditOutlined,
  BranchesOutlined,
  CheckSquareOutlined,
  CloudSyncOutlined,
  CommentOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  ImportOutlined,
  LockOutlined,
  LogoutOutlined,
  MessageOutlined,
  PhoneOutlined,
  ReadOutlined,
  ScheduleOutlined,
  SettingOutlined,
  TeamOutlined,
  ToolOutlined,
  UserOutlined
} from "@ant-design/icons";
import { App as AntdApp, Button, Form, Input, Layout, Menu, Modal, Space, Spin, Tag, Typography } from "antd";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { AuthBootstrapStatus, LocalUser } from "./types";
import { setStoredWorkBuddyUser } from "./utils/currentUser";
import { hashTarget, parseHashNavigation, type NavTarget } from "./utils/navigation";

type NavKey = NavTarget;

const AdapterTestPage = lazy(() => import("./pages/AdapterTestPage").then(({ AdapterTestPage }) => ({ default: AdapterTestPage })));
const AgentRunsPage = lazy(() => import("./pages/AgentRunsPage").then(({ AgentRunsPage }) => ({ default: AgentRunsPage })));
const ApprovalsPage = lazy(() => import("./pages/ApprovalsPage").then(({ ApprovalsPage }) => ({ default: ApprovalsPage })));
const AuthPage = lazy(() => import("./pages/AuthPage").then(({ AuthPage }) => ({ default: AuthPage })));
const AuditPage = lazy(() => import("./pages/AuditPage").then(({ AuditPage }) => ({ default: AuditPage })));
const BusinessObjectsPage = lazy(() => import("./pages/BusinessObjectsPage").then(({ BusinessObjectsPage }) => ({ default: BusinessObjectsPage })));
const CandidatesPage = lazy(() => import("./pages/CandidatesPage").then(({ CandidatesPage }) => ({ default: CandidatesPage })));
const ChannelEventsPage = lazy(() => import("./pages/ChannelEventsPage").then(({ ChannelEventsPage }) => ({ default: ChannelEventsPage })));
const CommunityPage = lazy(() => import("./pages/CommunityPage").then(({ CommunityPage }) => ({ default: CommunityPage })));
const ConfigCenterPage = lazy(() => import("./pages/ConfigCenterPage").then(({ ConfigCenterPage }) => ({ default: ConfigCenterPage })));
const DashboardPage = lazy(() => import("./pages/DashboardPage").then(({ DashboardPage }) => ({ default: DashboardPage })));
const DemoModePage = lazy(() => import("./pages/DemoModePage").then(({ DemoModePage }) => ({ default: DemoModePage })));
const FeishuConversationsPage = lazy(() => import("./pages/FeishuConversationsPage").then(({ FeishuConversationsPage }) => ({ default: FeishuConversationsPage })));
const FeishuDiagnosticsPage = lazy(() => import("./pages/FeishuDiagnosticsPage").then(({ FeishuDiagnosticsPage }) => ({ default: FeishuDiagnosticsPage })));
const ImportPage = lazy(() => import("./pages/ImportPage").then(({ ImportPage }) => ({ default: ImportPage })));
const KnowledgePage = lazy(() => import("./pages/KnowledgePage").then(({ KnowledgePage }) => ({ default: KnowledgePage })));
const LeadsPage = lazy(() => import("./pages/LeadsPage").then(({ LeadsPage }) => ({ default: LeadsPage })));
const MessagesPage = lazy(() => import("./pages/MessagesPage").then(({ MessagesPage }) => ({ default: MessagesPage })));
const ReportsPage = lazy(() => import("./pages/ReportsPage").then(({ ReportsPage }) => ({ default: ReportsPage })));
const TasksPage = lazy(() => import("./pages/TasksPage").then(({ TasksPage }) => ({ default: TasksPage })));
const TeamPage = lazy(() => import("./pages/TeamPage").then(({ TeamPage }) => ({ default: TeamPage })));
const TicketsPage = lazy(() => import("./pages/TicketsPage").then(({ TicketsPage }) => ({ default: TicketsPage })));
const WeComDiagnosticsPage = lazy(() => import("./pages/WeComDiagnosticsPage").then(({ WeComDiagnosticsPage }) => ({ default: WeComDiagnosticsPage })));

const mainNavItems = [
  {
    key: "workspace",
    icon: <DashboardOutlined />,
    label: "业务工作台",
    children: [
      { key: "dashboard", icon: <DashboardOutlined />, label: "工作台" },
      { key: "objects", icon: <DatabaseOutlined />, label: "业务对象" },
      { key: "audit", icon: <AuditOutlined />, label: "操作审计" },
      { key: "team", icon: <TeamOutlined />, label: "团队成员" }
    ]
  },
  {
    key: "message-flow",
    icon: <MessageOutlined />,
    label: "消息闭环",
    children: [
      { key: "import", icon: <ImportOutlined />, label: "消息导入" },
      { key: "messages", icon: <MessageOutlined />, label: "消息事件" },
      { key: "approvals", icon: <CheckSquareOutlined />, label: "审批队列" }
    ]
  },
  {
    key: "scenario-agents",
    icon: <ToolOutlined />,
    label: "场景 Agent",
    children: [
      { key: "tickets", icon: <ToolOutlined />, label: "客服工单与知识" },
      { key: "community", icon: <CommentOutlined />, label: "社群运营" },
      { key: "leads", icon: <PhoneOutlined />, label: "销售线索" },
      { key: "tasks", icon: <ScheduleOutlined />, label: "跟进任务" },
      { key: "candidates", icon: <TeamOutlined />, label: "招聘入职" },
      { key: "knowledge", icon: <ReadOutlined />, label: "知识库" },
      { key: "reports", icon: <FileTextOutlined />, label: "报告中心" }
    ]
  }
];

const utilityNavItems = [
  { key: "demo", icon: <ExperimentOutlined />, label: "演示模式" },
  {
    key: "system",
    icon: <SettingOutlined />,
    label: "系统与渠道",
    children: [
      { key: "config", icon: <SettingOutlined />, label: "配置中心" },
      { key: "conversations", icon: <CommentOutlined />, label: "渠道会话" },
      { key: "channel-events", icon: <BranchesOutlined />, label: "渠道事件" },
      { key: "adapter-test", icon: <CloudSyncOutlined />, label: "Adapter 测试台" },
      { key: "feishu", icon: <CloudSyncOutlined />, label: "飞书诊断" },
      { key: "wecom", icon: <CloudSyncOutlined />, label: "企微诊断" },
      { key: "agent-runs", icon: <AuditOutlined />, label: "运行日志" }
    ]
  }
];

const navItems = [...mainNavItems, ...utilityNavItems];
const navLabels = flattenNavLabels(navItems);

function renderPage(activeKey: NavKey, currentUser?: LocalUser, reloadCurrentUser?: () => void | Promise<void>) {
  switch (activeKey) {
    case "import":
      return <ImportPage />;
    case "messages":
      return <MessagesPage />;
    case "objects":
      return <BusinessObjectsPage />;
    case "team":
      return <TeamPage activeUser={currentUser} onUserChanged={reloadCurrentUser} />;
    case "audit":
      return <AuditPage />;
    case "approvals":
      return <ApprovalsPage />;
    case "tickets":
      return <TicketsPage />;
    case "community":
      return <CommunityPage />;
    case "leads":
      return <LeadsPage />;
    case "tasks":
      return <TasksPage />;
    case "candidates":
      return <CandidatesPage />;
    case "knowledge":
      return <KnowledgePage />;
    case "reports":
      return <ReportsPage />;
    case "demo":
      return <DemoModePage />;
    case "config":
      return <ConfigCenterPage />;
    case "conversations":
    case "feishu-conversations":
      return <FeishuConversationsPage />;
    case "channel-events":
      return <ChannelEventsPage />;
    case "adapter-test":
      return <AdapterTestPage />;
    case "feishu":
      return <FeishuDiagnosticsPage />;
    case "wecom":
      return <WeComDiagnosticsPage />;
    case "agent-runs":
      return <AgentRunsPage />;
    case "dashboard":
    default:
      return <DashboardPage />;
  }
}

export default function App() {
  const { message } = AntdApp.useApp();
  const [activeKey, setActiveKey] = useState<NavKey>(() => parseHashNavigation().target);
  const [mainOpenKeys, setMainOpenKeys] = useState<string[]>([]);
  const [utilityOpenKeys, setUtilityOpenKeys] = useState<string[]>([]);
  const [currentUser, setCurrentUser] = useState<LocalUser>();
  const [users, setUsers] = useState<LocalUser[]>([]);
  const [authMode, setAuthMode] = useState<"loading" | "login" | "bootstrap" | "ready">("loading");
  const [bootstrapStatus, setBootstrapStatus] = useState<AuthBootstrapStatus>();
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordForm] = Form.useForm();
  const selectedLabel = useMemo(() => navLabels[activeKey] ?? "工作台", [activeKey]);
  const visibleUtilityNavItems = useMemo(() => filterNavItemsByRole(utilityNavItems, currentUser?.role), [currentUser?.role]);

  const loadAuthenticatedContext = async () => {
    const me = await api.getCurrentUser();
    const localUsers = await api.getLocalUsers();
    setCurrentUser(me);
    setUsers(localUsers.items ?? []);
    setStoredWorkBuddyUser(me);
    setAuthMode("ready");
  };

  const resolveAuthState = async () => {
    try {
      await loadAuthenticatedContext();
      return;
    } catch (caught) {
      const status = typeof caught === "object" && caught && "status" in caught ? Number((caught as { status?: unknown }).status) : undefined;
      if (status === 401) {
        try {
          const nextBootstrapStatus = await api.getAuthBootstrapStatus();
          setBootstrapStatus(nextBootstrapStatus);
          setCurrentUser(undefined);
          setUsers([]);
          setStoredWorkBuddyUser(null);
          setAuthMode(nextBootstrapStatus.needs_bootstrap ? "bootstrap" : "login");
          return;
        } catch (innerCaught) {
          message.error(innerCaught instanceof Error ? innerCaught.message : "加载登录状态失败");
          setAuthMode("login");
          return;
        }
      }
      message.error(caught instanceof Error ? caught.message : "加载本地账号失败");
      setAuthMode("login");
    }
  };

  const loadCurrentUser = async () => {
    await resolveAuthState();
  };

  useEffect(() => {
    const syncFromHash = () => setActiveKey(parseHashNavigation().target);
    window.addEventListener("hashchange", syncFromHash);
    syncFromHash();
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, []);

  useEffect(() => {
    void loadCurrentUser();
  }, []);

  useEffect(() => {
    const handleAuthExpired = () => {
      setStoredWorkBuddyUser(null);
      setCurrentUser(undefined);
      setUsers([]);
      setPasswordModalOpen(false);
      message.warning("登录状态已过期，请重新登录");
      void resolveAuthState();
    };
    window.addEventListener("workbuddy:auth-expired", handleAuthExpired);
    return () => window.removeEventListener("workbuddy:auth-expired", handleAuthExpired);
  }, []);

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // Even if the cookie is already gone, continue to the login screen.
    }
    setStoredWorkBuddyUser(null);
    setCurrentUser(undefined);
    setUsers([]);
    setPasswordModalOpen(false);
    await resolveAuthState();
  };

  const changePassword = async (values: Record<string, unknown>) => {
    setChangingPassword(true);
    try {
      await api.changePassword({
        current_password: String(values.current_password ?? ""),
        new_password: String(values.new_password ?? ""),
      });
      message.success("登录密码已更新");
      setPasswordModalOpen(false);
      passwordForm.resetFields();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "修改密码失败");
    } finally {
      setChangingPassword(false);
    }
  };

  if (authMode !== "ready") {
    if (authMode === "loading") {
      return (
        <div style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
          <Typography.Text type="secondary">正在检查登录状态…</Typography.Text>
        </div>
      );
    }
    return (
      <Suspense fallback={<PageLoading fullHeight />}>
        <AuthPage bootstrapStatus={bootstrapStatus} onAuthenticated={() => loadAuthenticatedContext()} />
      </Suspense>
    );
  }

  return (
    <Layout className="app-shell">
      <Layout.Sider width={248} breakpoint="lg" collapsedWidth={72}>
        <div className="sider-content">
          <div className="brand">
            <div className="brand-mark">WB</div>
            <div className="brand-text">
              <Typography.Text>WorkBuddy OSS</Typography.Text>
              <Typography.Text type="secondary">Agent Runtime</Typography.Text>
            </div>
          </div>
          <Menu
            className="main-menu"
            theme="dark"
            mode="inline"
            openKeys={mainOpenKeys}
            onOpenChange={(keys) => setMainOpenKeys([...keys])}
            selectedKeys={[activeKey]}
            items={mainNavItems}
            onClick={({ key }) => {
              window.location.hash = hashTarget(key as NavKey);
              setActiveKey(key as NavKey);
            }}
          />
          <div className="sider-footer">
            <div className="account-pill">
              <UserOutlined />
              <div className="account-pill-content">
                <Space size={6} wrap>
                  <span>{currentUser?.display_name ?? "本地管理员"}</span>
                  <Tag color={roleColor(currentUser?.role)}>{roleLabel(currentUser?.role)}</Tag>
                </Space>
                <Typography.Text type="secondary">@{currentUser?.username ?? "local_admin"}</Typography.Text>
              </div>
            </div>
            <Menu
              theme="dark"
              mode="inline"
              openKeys={utilityOpenKeys}
              onOpenChange={(keys) => setUtilityOpenKeys([...keys])}
              selectedKeys={[activeKey]}
              items={visibleUtilityNavItems}
              onClick={({ key }) => {
                window.location.hash = hashTarget(key as NavKey);
                setActiveKey(key as NavKey);
              }}
            />
          </div>
        </div>
      </Layout.Sider>
      <Layout>
        <Layout.Header className="topbar">
          <Space>
            <Typography.Text strong>{selectedLabel}</Typography.Text>
            <Typography.Text type="secondary">v1.1.16 部署恢复收口</Typography.Text>
          </Space>
          <Space>
            <Typography.Text type="secondary">@{currentUser?.username ?? "local_admin"}</Typography.Text>
            <Tag color={roleColor(currentUser?.role)}>{roleLabel(currentUser?.role)}</Tag>
            <Button size="small" icon={<LockOutlined />} onClick={() => setPasswordModalOpen(true)}>修改密码</Button>
            <Button size="small" icon={<LogoutOutlined />} onClick={() => void logout()}>退出</Button>
          </Space>
        </Layout.Header>
        <Layout.Content className="content">
          <Suspense fallback={<PageLoading />}>
            {renderPage(activeKey, currentUser, loadCurrentUser)}
          </Suspense>
        </Layout.Content>
      </Layout>
      <Modal
        title="修改登录密码"
        open={passwordModalOpen}
        onCancel={() => {
          setPasswordModalOpen(false);
          passwordForm.resetFields();
        }}
        footer={null}
        destroyOnHidden
      >
        <Form layout="vertical" form={passwordForm} onFinish={(values) => void changePassword(values)}>
          <Form.Item label="当前密码" name="current_password" rules={[{ required: true, message: "请输入当前密码" }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Form.Item label="新密码" name="new_password" rules={[{ required: true, message: "请输入新密码" }, { min: 8, message: "至少 8 位" }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={changingPassword}>
            保存新密码
          </Button>
        </Form>
      </Modal>
    </Layout>
  );
}

function PageLoading({ fullHeight = false }: { fullHeight?: boolean }) {
  return (
    <div className={fullHeight ? "page-loading page-loading-full" : "page-loading"}>
      <Spin size="large" />
    </div>
  );
}

function flattenNavLabels(items: Array<{ key: string; label: string; children?: Array<{ key: string; label: string }> }>) {
  const labels: Record<string, string> = {};
  items.forEach((item) => {
    labels[item.key] = item.label;
    item.children?.forEach((child) => {
      labels[child.key] = child.label;
    });
  });
  return labels;
}

function filterNavItemsByRole(items: typeof utilityNavItems, role?: string) {
  if (role === "admin") return items;
  return items
    .map((item) => {
      if (!item.children) return item.key === "demo" ? null : item;
      return {
        ...item,
        children: item.children.filter((child) => !["config", "adapter-test", "channel-events"].includes(child.key))
      };
    })
    .filter((item): item is typeof utilityNavItems[number] => Boolean(item));
}

function roleLabel(value?: string) {
  const labels: Record<string, string> = {
    admin: "管理员",
    approver: "审批人",
    handler: "处理人",
    readonly: "只读"
  };
  return labels[value ?? ""] ?? value ?? "管理员";
}

function roleColor(value?: string) {
  const colors: Record<string, string> = {
    admin: "red",
    approver: "gold",
    handler: "blue",
    readonly: "default"
  };
  return colors[value ?? ""] ?? "default";
}
