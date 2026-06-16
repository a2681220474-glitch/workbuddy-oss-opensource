import { EditOutlined, PlusOutlined } from "@ant-design/icons";
import { Alert, App as AntdApp, Button, Card, Drawer, Form, Input, Select, Space, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { PageHeader } from "../components/PageHeader";
import { ReloadButton } from "../components/ReloadButton";
import { ResizableTable } from "../components/ResizableTable";
import { useAsyncData } from "../components/useAsyncData";
import type { LocalUser } from "../types";
import { formatTime } from "../utils/format";

interface Props {
  activeUser?: LocalUser;
  onUserChanged?: () => void | Promise<void>;
}

const roleOptions = [
  { value: "admin", label: "管理员" },
  { value: "approver", label: "审批人" },
  { value: "handler", label: "处理人" },
  { value: "readonly", label: "只读" }
];

export function TeamPage({ activeUser, onUserChanged }: Props) {
  const { message } = AntdApp.useApp();
  const { data, error, loading, reload } = useAsyncData(api.getLocalUsers);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<LocalUser>();
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    if (!drawerOpen) {
      form.resetFields();
      return;
    }
    form.setFieldsValue({
      username: editingUser?.username ?? "",
      display_name: editingUser?.display_name ?? "",
      role: editingUser?.role ?? "handler",
      status: editingUser?.status ?? "active"
    });
  }, [drawerOpen, editingUser, form]);

  const openCreate = () => {
    setEditingUser(undefined);
    setDrawerOpen(true);
  };

  const openEdit = (user: LocalUser) => {
    setEditingUser(user);
    setDrawerOpen(true);
  };

  const submit = async (values: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      if (editingUser?.id !== undefined) {
        await api.updateLocalUser(editingUser.id, {
          display_name: String(values.display_name ?? ""),
          role: String(values.role ?? "handler"),
          status: String(values.status ?? "active"),
          password: String(values.password ?? "").trim() || undefined
        });
        message.success("成员已更新");
      } else {
        await api.createLocalUser({
          username: String(values.username ?? "").trim(),
          display_name: String(values.display_name ?? "").trim(),
          role: String(values.role ?? "handler"),
          password: String(values.password ?? "")
        });
        message.success("成员已创建");
      }
      setDrawerOpen(false);
      await reload();
      await onUserChanged?.();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "保存成员失败");
    } finally {
      setSubmitting(false);
    }
  };

  const rows = useMemo(() => data?.items ?? [], [data?.items]);

  const columns: ColumnsType<LocalUser> = [
    {
      title: "成员",
      width: 220,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{row.display_name}</Typography.Text>
          <Typography.Text type="secondary">@{row.username}</Typography.Text>
        </Space>
      )
    },
    {
      title: "角色",
      width: 140,
      render: (_, row) => <Tag color={roleColor(row.role)}>{roleLabel(row.role)}</Tag>
    },
    {
      title: "状态",
      width: 120,
      render: (_, row) => <Tag color={row.status === "active" ? "green" : "default"}>{row.status === "active" ? "启用" : "停用"}</Tag>
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 180,
      render: formatTime
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      width: 180,
      render: formatTime
    },
    {
      title: "操作",
      fixed: "right",
      width: 120,
      render: (_, row) => (
        <Space>
          <Button icon={<EditOutlined />} size="small" disabled={activeUser?.role !== "admin"} onClick={() => openEdit(row)}>编辑</Button>
        </Space>
      )
    }
  ];

  return (
    <>
      <PageHeader
        title="团队成员"
        extra={(
          <>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} disabled={activeUser?.role !== "admin"}>新增成员</Button>
            <ReloadButton loading={loading} onReload={() => void reload()} />
          </>
        )}
      />
      <ApiErrorAlert error={error} />
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Alert
          type="info"
          showIcon
          message={`当前操作人：${activeUser?.display_name ?? "本地管理员"}`}
          description={(
            <Space wrap>
              <span>账号 @{activeUser?.username ?? "local_admin"}</span>
              <span>角色 {roleLabel(activeUser?.role)}</span>
              <span>当前已改为正式登录，切换身份请退出后重新登录对应账号</span>
            </Space>
          )}
        />
        {activeUser?.role !== "admin" ? (
          <Alert type="warning" showIcon message="当前账号不是管理员，只能查看成员，不能新增或修改。" />
        ) : null}
        <Card>
          <Typography.Paragraph type="secondary" className="table-ux-hint">
            v1.0.2 开始进入正式本地登录：账号、角色和密码都在这里管理，审批和处理记录继续按真实登录身份写入。
          </Typography.Paragraph>
          <ResizableTable
            rowKey="id"
            loading={loading}
            scroll={{ x: 940 }}
            columns={columns}
            dataSource={rows}
            pagination={false}
          />
        </Card>
      </Space>
      <Drawer
        title={editingUser ? `编辑成员 #${editingUser.id}` : "新增成员"}
        width={420}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <Form layout="vertical" form={form} onFinish={(values) => void submit(values)}>
          <Form.Item label="用户名" name="username" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input disabled={Boolean(editingUser)} placeholder="例如：zhangsan" />
          </Form.Item>
          <Form.Item label="显示名" name="display_name" rules={[{ required: true, message: "请输入显示名" }]}>
            <Input placeholder="例如：张三" />
          </Form.Item>
          <Form.Item label="角色" name="role" rules={[{ required: true, message: "请选择角色" }]}>
            <Select options={roleOptions} />
          </Form.Item>
          <Form.Item
            label={editingUser ? "重置密码" : "初始密码"}
            name="password"
            rules={[
              ...(editingUser ? [] : [{ required: true, message: "请输入初始密码" }]),
              { min: 8, message: "密码至少需要 8 位" }
            ]}
            extra={editingUser ? "留空表示不修改现有密码。" : "至少 8 位。"}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          {editingUser ? (
            <Form.Item label="状态" name="status" rules={[{ required: true, message: "请选择状态" }]}>
              <Select options={[
                { value: "active", label: "启用" },
                { value: "disabled", label: "停用" }
              ]} />
            </Form.Item>
          ) : null}
          <Button type="primary" htmlType="submit" loading={submitting}>
            {editingUser ? "保存变更" : "创建成员"}
          </Button>
        </Form>
      </Drawer>
    </>
  );
}

function roleLabel(value?: string) {
  const labels: Record<string, string> = {
    admin: "管理员",
    approver: "审批人",
    handler: "处理人",
    readonly: "只读"
  };
  return labels[value ?? ""] ?? value ?? "未设置";
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
