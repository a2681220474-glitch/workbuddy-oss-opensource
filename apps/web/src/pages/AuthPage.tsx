import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { Alert, App as AntdApp, Button, Card, Form, Input, Space, Typography } from "antd";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AuthBootstrapStatus, LocalUser } from "../types";
import { getStoredWorkBuddyUsername, setStoredWorkBuddyUser } from "../utils/currentUser";

interface Props {
  bootstrapStatus?: AuthBootstrapStatus;
  onAuthenticated?: (user: LocalUser) => void | Promise<void>;
}

export function AuthPage({ bootstrapStatus, onAuthenticated }: Props) {
  const { message } = AntdApp.useApp();
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();
  const needsBootstrap = Boolean(bootstrapStatus?.needs_bootstrap);

  useEffect(() => {
    form.setFieldsValue({
      username: needsBootstrap ? (bootstrapStatus?.bootstrap_username ?? "local_admin") : getStoredWorkBuddyUsername(),
    });
  }, [bootstrapStatus?.bootstrap_username, form, needsBootstrap]);

  const submit = async (values: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      if (needsBootstrap) {
        const result = await api.bootstrapAuth({
          username: String(values.username ?? "local_admin").trim(),
          display_name: String(values.display_name ?? "").trim(),
          password: String(values.password ?? ""),
        });
        if (!result.user) throw new Error("初始化后未返回登录用户");
        setStoredWorkBuddyUser(result.user);
        message.success("管理员登录已初始化");
        await onAuthenticated?.(result.user);
      } else {
        const result = await api.login({
          username: String(values.username ?? "").trim(),
          password: String(values.password ?? ""),
        });
        if (!result.user) throw new Error("登录成功后未返回用户信息");
        setStoredWorkBuddyUser(result.user);
        message.success(`欢迎回来，${result.user.display_name ?? result.user.username ?? "WorkBuddy 用户"}`);
        await onAuthenticated?.(result.user);
      }
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24, background: "#f5f7fb" }}>
      <Card style={{ width: "100%", maxWidth: 420 }}>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <div>
            <Typography.Title level={3} style={{ marginBottom: 8 }}>
              WorkBuddy OSS
            </Typography.Title>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {needsBootstrap ? "先为本地管理员设置登录密码，再进入工作台。" : "请输入本地账号和密码进入工作台。"}
            </Typography.Paragraph>
          </div>
          {needsBootstrap ? (
            <Alert
              type="info"
              showIcon
              message="首次登录初始化"
              description="当前租户还没有配置任何本地登录密码。初始化完成后，后续访问将使用正式登录。"
            />
          ) : null}
          <Form layout="vertical" form={form} onFinish={(values) => void submit(values)}>
            <Form.Item label="用户名" name="username" rules={[{ required: true, message: "请输入用户名" }]}>
              <Input prefix={<UserOutlined />} autoComplete="username" />
            </Form.Item>
            {needsBootstrap ? (
              <Form.Item label="显示名" name="display_name">
                <Input placeholder="默认沿用现有显示名" />
              </Form.Item>
            ) : null}
            <Form.Item
              label="密码"
              name="password"
              extra={needsBootstrap ? "首次初始化密码至少 8 位。" : undefined}
              rules={[
                { required: true, message: "请输入密码" },
                ...(needsBootstrap ? [{ min: 8, message: "密码至少需要 8 位" }] : []),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} autoComplete={needsBootstrap ? "new-password" : "current-password"} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={submitting} block>
              {needsBootstrap ? "初始化并登录" : "登录"}
            </Button>
          </Form>
        </Space>
      </Card>
    </div>
  );
}
