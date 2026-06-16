import { ApiOutlined, CheckCircleOutlined, CloudSyncOutlined, ExperimentOutlined, ReloadOutlined, SafetyCertificateOutlined, SettingOutlined } from "@ant-design/icons";
import { Alert, App as AntdApp, Button, Card, Col, Descriptions, Form, Input, InputNumber, Row, Select, Space, Switch, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { PageHeader } from "../components/PageHeader";
import { ResizableTable } from "../components/ResizableTable";
import { StatusTag } from "../components/StatusTag";
import { useAsyncData } from "../components/useAsyncData";
import type { ChannelStatus, LLMSmokeTestResult } from "../types";
import { getStoredWorkBuddyUserRole } from "../utils/currentUser";
import { formatTime, shortText } from "../utils/format";
import { hashTarget } from "../utils/navigation";

const capabilityLabels: Record<string, string> = {
  receive_event: "接收事件",
  normalize_message: "标准化消息",
  send_message: "发送消息",
  resolve_user: "解析用户",
  resolve_conversation: "解析会话"
};

export function ConfigCenterPage() {
  const { message, modal } = AntdApp.useApp();
  const { data, error, loading, reload } = useAsyncData(api.getConfigStatus);
  const isAdmin = getStoredWorkBuddyUserRole() === "admin";
  const feishu = data?.channels?.find((channel) => channel.channel === "feishu");
  const wecom = data?.channels?.find((channel) => channel.channel === "wecom");
  const dingtalk = data?.channels?.find((channel) => channel.channel === "dingtalk");
  const runtimeStack = data?.runtime_stack;
  const releaseAudit = data?.release_audit;
  const [llmForm] = Form.useForm();
  const [policyForm] = Form.useForm();
  const [feishuForm] = Form.useForm();
  const [wecomForm] = Form.useForm();
  const [dingtalkForm] = Form.useForm();
  const [savingMode, setSavingMode] = useState(false);
  const [safeModeSaving, setSafeModeSaving] = useState(false);
  const [savingRuntime, setSavingRuntime] = useState<string | null>(null);
  const [smokeTesting, setSmokeTesting] = useState(false);
  const [secretOperation, setSecretOperation] = useState<"migrate" | "rotate" | null>(null);
  const [llmSmoke, setLlmSmoke] = useState<LLMSmokeTestResult>();

  useEffect(() => {
    if (!data) return;
    llmForm.setFieldsValue({
      provider: data.llm?.provider ?? "mock",
      base_url: data.llm?.base_url ?? "",
      model: data.llm?.model ?? "workbuddy-demo",
      timeout_seconds: data.llm?.timeout_seconds ?? 30,
      api_key: ""
    });
    policyForm.setFieldsValue({
      enable_real_im_adapters: Boolean(data.global_policy?.enable_real_im_adapters),
      enable_external_send: Boolean(data.global_policy?.enable_external_send)
    });
    feishuForm.setFieldsValue({
      app_id: runtimeString(feishu, "app_id"),
      api_base_url: runtimeString(feishu, "api_base_url") || "https://open.feishu.cn",
      approval_chat_id: runtimeString(feishu, "approval_chat_id"),
      app_secret: "",
      verification_token: "",
      encrypt_key: ""
    });
    wecomForm.setFieldsValue({
      corp_id: runtimeString(wecom, "corp_id"),
      agent_id: runtimeString(wecom, "agent_id"),
      secret: "",
      token: "",
      encoding_aes_key: ""
    });
    dingtalkForm.setFieldsValue({
      client_id: runtimeString(dingtalk, "client_id"),
      robot_code: runtimeString(dingtalk, "robot_code"),
      client_secret: "",
      webhook_secret: ""
    });
  }, [data, dingtalk, dingtalkForm, feishu, feishuForm, llmForm, policyForm, wecom, wecomForm]);

  const saveRuntime = async (name: string, action: () => Promise<{ restart_hint?: string }>) => {
    setSavingRuntime(name);
    try {
      const result = await action();
      message.success(result.restart_hint ? `配置已保存：${result.restart_hint}` : "配置已保存并已重新加载");
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "保存配置失败");
    } finally {
      setSavingRuntime(null);
    }
  };

  const saveLlmRuntime = (values: Record<string, unknown>) =>
    saveRuntime("llm", () =>
      api.updateLlmRuntime({
        provider: String(values.provider ?? "mock"),
        base_url: String(values.base_url ?? ""),
        model: String(values.model ?? "workbuddy-demo"),
        api_key: optionalSecret(values.api_key),
        timeout_seconds: Number(values.timeout_seconds ?? 30)
      })
    );

  const smokeTestLlm = async () => {
    setSmokeTesting(true);
    try {
      const values = llmForm.getFieldsValue();
      const result = await api.smokeTestLlmRuntime({
        provider: String(values.provider ?? data?.llm?.provider ?? "mock"),
        base_url: String(values.base_url ?? ""),
        model: String(values.model ?? data?.llm?.model ?? "workbuddy-demo"),
        api_key: optionalSecret(values.api_key),
        timeout_seconds: Number(values.timeout_seconds ?? data?.llm?.timeout_seconds ?? 30)
      });
      setLlmSmoke(result);
      if (result.ok) {
        message.success(`模型 smoke test 通过，耗时 ${result.latency_ms ?? 0}ms`);
      } else {
        message.warning(result.message || "模型 smoke test 未通过");
      }
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "模型 smoke test 失败");
    } finally {
      setSmokeTesting(false);
    }
  };

  const savePolicyRuntime = (values: Record<string, unknown>) =>
    saveRuntime("policy", () =>
      api.updateRuntimePolicy({
        enable_real_im_adapters: Boolean(values.enable_real_im_adapters),
        enable_external_send: Boolean(values.enable_external_send)
      })
    );

  const saveFeishuRuntime = (values: Record<string, unknown>) =>
    saveRuntime("feishu", () =>
      api.updateChannelRuntime("feishu", {
        app_id: String(values.app_id ?? ""),
        app_secret: optionalSecret(values.app_secret),
        verification_token: optionalSecret(values.verification_token),
        encrypt_key: optionalSecret(values.encrypt_key),
        api_base_url: String(values.api_base_url ?? "https://open.feishu.cn"),
        approval_chat_id: String(values.approval_chat_id ?? "")
      })
    );

  const saveWeComRuntime = (values: Record<string, unknown>) =>
    saveRuntime("wecom", () =>
      api.updateChannelRuntime("wecom", {
        corp_id: String(values.corp_id ?? ""),
        agent_id: String(values.agent_id ?? ""),
        secret: optionalSecret(values.secret),
        token: optionalSecret(values.token),
        encoding_aes_key: optionalSecret(values.encoding_aes_key)
      })
    );

  const saveDingTalkRuntime = (values: Record<string, unknown>) =>
    saveRuntime("dingtalk", () =>
      api.updateChannelRuntime("dingtalk", {
        client_id: String(values.client_id ?? ""),
        client_secret: optionalSecret(values.client_secret),
        robot_code: String(values.robot_code ?? ""),
        webhook_secret: optionalSecret(values.webhook_secret)
      })
    );

  const updateMode = async (mode: "mock" | "real") => {
    setSavingMode(true);
    try {
      await api.updateDefaultSendMode(mode);
      message.success("默认发送模式已更新");
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "更新默认发送模式失败");
    } finally {
      setSavingMode(false);
    }
  };

  const enableSafeDemoMode = async () => {
    setSafeModeSaving(true);
    try {
      const result = await api.enableSafeDemoMode();
      message.success(`已切换到安全演示模式，更新 ${result.updated_conversation_count ?? 0} 个会话`);
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "切换安全演示模式失败");
    } finally {
      setSafeModeSaving(false);
    }
  };

  const runSecretOperation = async (operation: "migrate" | "rotate") => {
    setSecretOperation(operation);
    try {
      const result = operation === "migrate"
        ? await api.migrateRuntimeSecrets()
        : await api.rotateRuntimeSecretKey();
      const changedCount = operation === "migrate"
        ? result.migrated_keys?.length ?? 0
        : result.rotated_keys?.length ?? 0;
      message.success(operation === "migrate"
        ? `敏感配置迁移完成，共 ${changedCount} 项`
        : `主密钥轮换完成，共重新加密 ${changedCount} 项`);
      await reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "密钥存储操作失败");
    } finally {
      setSecretOperation(null);
    }
  };

  const confirmSecretOperation = (operation: "migrate" | "rotate") => {
    const isMigration = operation === "migrate";
    modal.confirm({
      title: isMigration ? "迁移明文敏感配置？" : "轮换本地主密钥？",
      content: isMigration
        ? "系统会先生成仅本机可读的备份，再把 .env.local 中的敏感值写入加密仓库并移除明文行。"
        : "系统会生成新主密钥，并使用新密钥重新加密全部本地敏感配置。请勿在操作期间关闭 API。",
      okText: isMigration ? "确认迁移" : "确认轮换",
      cancelText: "取消",
      okButtonProps: { danger: !isMigration },
      onOk: () => runSecretOperation(operation)
    });
  };

  const columns: ColumnsType<ChannelStatus> = [
    {
      title: "渠道",
      width: 150,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{row.label ?? row.channel}</Typography.Text>
          <Typography.Text type="secondary">{row.channel}</Typography.Text>
        </Space>
      )
    },
    {
      title: "配置",
      width: 140,
      render: (_, row) => (
        <Tag color={row.configured ? "green" : row.adapter_status === "ready_to_configure" ? "blue" : "red"}>
          {row.configured ? "已配置" : row.adapter_status === "ready_to_configure" ? "待填密钥" : "未配置"}
        </Tag>
      )
    },
    {
      title: "Adapter 状态",
      dataIndex: "adapter_status",
      width: 160,
      render: (value) => <StatusTag value={value} />
    },
    {
      title: "能力",
      width: 360,
      render: (_, row) => (
        <Space wrap>
          {Object.entries(row.capabilities ?? {}).map(([key, value]) => (
            <Tag key={key} color={value === true ? "green" : value === "mock_only" ? "blue" : "default"}>
              {capabilityLabels[key] ?? key}: {capabilityText(value)}
            </Tag>
          ))}
        </Space>
      )
    },
    {
      title: "最近活动",
      width: 280,
      render: (_, row) => {
        const lastMessage = row.recent?.last_message?.text;
        const lastEvent = row.recent?.last_event?.event_type;
        return row.channel === "feishu" ? (
          <Space direction="vertical" size={0}>
            <Typography.Text>{shortText(String(lastMessage ?? "-"), 42)}</Typography.Text>
            <Typography.Text type="secondary">{String(lastEvent ?? "-")}</Typography.Text>
          </Space>
        ) : row.channel === "wecom" ? (
          <Space direction="vertical" size={0}>
            <Typography.Text>{shortText(String(lastMessage ?? "-"), 42)}</Typography.Text>
            <Typography.Text type="secondary">{String(lastEvent ?? row.setup_status ?? "-")}</Typography.Text>
          </Space>
        ) : (
          <Space direction="vertical" size={0}>
            <Typography.Text type="secondary">{row.setup_status ?? "待配置"}</Typography.Text>
            <Typography.Text code>{row.webhook_path ?? "-"}</Typography.Text>
          </Space>
        );
      }
    },
    {
      title: "配置键",
      width: 300,
      render: (_, row) => (
        <Typography.Text type="secondary">
          {(row.config_keys ?? []).join(" / ") || "-"}
        </Typography.Text>
      )
    },
    {
      title: "操作",
      width: 180,
      render: (_, row) => (
        <Space>
          {row.channel === "feishu" ? (
            <>
              <a href={hashTarget("feishu")}>诊断</a>
              <a href={hashTarget("conversations")}>会话</a>
            </>
          ) : row.channel === "wecom" ? (
            <>
              <a href={hashTarget("wecom")}>诊断</a>
              <a href={hashTarget("adapter-test")}>测试 Payload</a>
            </>
          ) : (
            <Space direction="vertical" size={0}>
              <a href={hashTarget("adapter-test")}>测试 Payload</a>
              <Typography.Text type="secondary">按 .env 配置后联调</Typography.Text>
            </Space>
          )}
        </Space>
      )
    }
  ];

  return (
    <>
      <PageHeader
        title="配置中心"
        extra={
          <Button icon={<ReloadOutlined />} loading={loading} onClick={reload}>
            刷新
          </Button>
        }
      />
      <ApiErrorAlert error={error} />

      <Alert
        className="api-alert"
        type="info"
        showIcon
        message="配置中心承担本地运行态检查"
        description="新保存的模型和渠道密钥进入本地加密仓库；页面只显示是否已配置，不回显密钥值。输入框留空表示不修改，审计只记录配置键名。"
      />
      {!isAdmin ? (
        <Alert
          className="api-alert"
          type="warning"
          showIcon
          message="当前账号不是管理员"
          description="可以查看配置与诊断状态，但不能修改模型、渠道或发送策略。"
        />
      ) : null}

      <Card
        className="dashboard-lower"
        title={<Space><SafetyCertificateOutlined />敏感配置加密存储</Space>}
        extra={
          <Space wrap>
            <Button
              disabled={!isAdmin || !data?.secret_storage?.migration_required}
              loading={secretOperation === "migrate"}
              onClick={() => confirmSecretOperation("migrate")}
            >
              迁移现有明文
            </Button>
            <Button
              disabled={!isAdmin || !data?.secret_storage?.encrypted_key_count}
              loading={secretOperation === "rotate"}
              onClick={() => confirmSecretOperation("rotate")}
            >
              轮换主密钥
            </Button>
          </Space>
        }
      >
        <Descriptions size="small" column={{ xs: 1, md: 2, xl: 4 }}>
          <Descriptions.Item label="存储状态">
            <Tag color={data?.secret_storage?.healthy ? "green" : "red"}>
              {data?.secret_storage?.healthy ? "正常" : "异常"}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="已加密条目">
            {data?.secret_storage?.encrypted_key_count ?? 0}
          </Descriptions.Item>
          <Descriptions.Item label="残留明文">
            <Tag color={data?.secret_storage?.migration_required ? "orange" : "green"}>
              {data?.secret_storage?.migration_required
                ? `${data?.secret_storage?.plaintext_key_count ?? 0} 项待迁移`
                : "无"}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="主密钥权限">
            <Tag color={data?.secret_storage?.key_permissions_secure ? "green" : "red"}>
              {data?.secret_storage?.key_exists
                ? (data?.secret_storage?.key_permissions_secure ? "仅本机用户可读" : "需要加固")
                : "尚未生成"}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="密文仓库">
            <Typography.Text code>{data?.secret_storage?.store_path ?? "apps/api/data/runtime_secrets.json"}</Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label="主密钥文件">
            <Typography.Text code>{data?.secret_storage?.key_path ?? "apps/api/data/runtime_secret.key"}</Typography.Text>
          </Descriptions.Item>
        </Descriptions>
        {data?.secret_storage?.migration_required ? (
          <Alert
            style={{ marginTop: 12 }}
            type="warning"
            showIcon
            message="检测到旧版明文敏感配置"
            description="点击“迁移现有明文”后会先创建本地备份，再移除 .env.local 中对应的敏感行；普通运行参数不会受影响。"
          />
        ) : null}
        {data?.secret_storage?.error ? (
          <Alert style={{ marginTop: 12 }} type="error" showIcon message={data.secret_storage.error} />
        ) : null}
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="大模型配置">
            <Form form={llmForm} layout="vertical" onFinish={saveLlmRuntime}>
              <Row gutter={12}>
                <Col xs={24} md={12}>
                  <Form.Item label="模型服务商" name="provider" rules={[{ required: true, message: "请选择模型服务商" }]}>
                    <Select
                      options={[
                        { value: "mock", label: "Mock 本地演示" },
                        { value: "deepseek", label: "DeepSeek" },
                        { value: "openai_compatible", label: "OpenAI-compatible" },
                        { value: "openai", label: "OpenAI" },
                        { value: "qwen", label: "通义千问 / Qwen" },
                        { value: "moonshot", label: "Moonshot" }
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="模型名" name="model" rules={[{ required: true, message: "请输入模型名" }]}>
                    <Input placeholder="deepseek-chat / gpt-4.1-mini / qwen-plus" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="Base URL" name="base_url">
                    <Input placeholder="https://api.deepseek.com/v1" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label={`API Key${data?.llm?.api_key_configured ? "（已配置，留空不修改）" : ""}`} name="api_key">
                    <Input.Password placeholder={data?.llm?.api_key_configured ? "已配置，留空保持原值" : "请输入 API Key"} autoComplete="new-password" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="超时秒数" name="timeout_seconds">
                    <InputNumber min={1} max={300} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
              <Space>
                <Button type="primary" htmlType="submit" loading={savingRuntime === "llm"} disabled={!isAdmin}>
                  保存大模型配置
                </Button>
                <Button icon={<ExperimentOutlined />} loading={smokeTesting} onClick={smokeTestLlm} disabled={!isAdmin}>
                  测试模型调用
                </Button>
                <Typography.Text type="secondary">保存后配置中心会立即刷新状态。</Typography.Text>
              </Space>
              {llmSmoke ? <LlmSmokeResult result={llmSmoke} /> : null}
            </Form>
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card title="全局运行策略">
            <Form form={policyForm} layout="vertical" onFinish={savePolicyRuntime}>
              <Row gutter={12}>
                <Col xs={24} md={12}>
                  <Form.Item label="启用真实 IM Adapter" name="enable_real_im_adapters" valuePropName="checked">
                    <Switch checkedChildren="启用" unCheckedChildren="关闭" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="允许外部真实发送" name="enable_external_send" valuePropName="checked">
                    <Switch checkedChildren="允许" unCheckedChildren="关闭" />
                  </Form.Item>
                </Col>
              </Row>
              <Space>
                <Button type="primary" htmlType="submit" loading={savingRuntime === "policy"} disabled={!isAdmin}>
                  保存运行策略
                </Button>
                <Typography.Text type="secondary">真实发送仍会经过审批队列。</Typography.Text>
              </Space>
            </Form>
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card title="飞书配置">
            <Form form={feishuForm} layout="vertical" onFinish={saveFeishuRuntime}>
              <Row gutter={12}>
                <Col xs={24} md={12}>
                  <Form.Item label="App ID" name="app_id">
                    <Input placeholder="cli_xxx" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label={`App Secret${runtimeBool(feishu, "app_secret_configured") ? "（已配置，留空不修改）" : ""}`} name="app_secret">
                    <Input.Password placeholder={runtimeBool(feishu, "app_secret_configured") ? "已配置，留空保持原值" : "请输入 App Secret"} autoComplete="new-password" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label={`Verification Token${runtimeBool(feishu, "verification_token_configured") ? "（已配置，留空不修改）" : ""}`} name="verification_token">
                    <Input.Password placeholder="事件订阅校验 token，可选" autoComplete="new-password" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label={`Encrypt Key${runtimeBool(feishu, "encrypt_key_configured") ? "（已配置，留空不修改）" : ""}`} name="encrypt_key">
                    <Input.Password placeholder="长连接 Worker 当前建议留空" autoComplete="new-password" />
                  </Form.Item>
                </Col>
                <Col xs={24}>
                  <Form.Item label="API Base URL" name="api_base_url">
                    <Input placeholder="https://open.feishu.cn" />
                  </Form.Item>
                </Col>
                <Col xs={24}>
                  <Form.Item label="审批通知 Chat ID" name="approval_chat_id">
                    <Input placeholder="oc_xxx；用于发送 WorkBuddy 内部审批卡片，避免误发到客户会话" />
                  </Form.Item>
                </Col>
              </Row>
              <Space wrap>
                <Button type="primary" htmlType="submit" loading={savingRuntime === "feishu"} disabled={!isAdmin}>
                  保存飞书配置
                </Button>
                <Typography.Text type="secondary">保存后 API 立即生效；飞书长连接 Worker 需要重启。</Typography.Text>
              </Space>
            </Form>
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card title="企业微信配置">
            <Form form={wecomForm} layout="vertical" onFinish={saveWeComRuntime}>
              <Row gutter={12}>
                <Col xs={24} md={12}>
                  <Form.Item label="Corp ID" name="corp_id">
                    <Input placeholder="ww_xxx" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="Agent ID" name="agent_id">
                    <Input placeholder="1000002" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label={`Secret${runtimeBool(wecom, "secret_configured") ? "（已配置，留空不修改）" : ""}`} name="secret">
                    <Input.Password placeholder={runtimeBool(wecom, "secret_configured") ? "已配置，留空保持原值" : "请输入 Secret"} autoComplete="new-password" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label={`Token${runtimeBool(wecom, "token_configured") ? "（已配置，留空不修改）" : ""}`} name="token">
                    <Input.Password placeholder="回调 Token，可选" autoComplete="new-password" />
                  </Form.Item>
                </Col>
                <Col xs={24}>
                  <Form.Item label={`EncodingAESKey${runtimeBool(wecom, "encoding_aes_key_configured") ? "（已配置，留空不修改）" : ""}`} name="encoding_aes_key">
                    <Input.Password placeholder="回调加密 Key，可选" autoComplete="new-password" />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" htmlType="submit" loading={savingRuntime === "wecom"} disabled={!isAdmin}>
                保存企业微信配置
              </Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card title="钉钉配置">
            <Form form={dingtalkForm} layout="vertical" onFinish={saveDingTalkRuntime}>
              <Row gutter={12}>
                <Col xs={24} md={12}>
                  <Form.Item label="Client ID" name="client_id">
                    <Input placeholder="dingxxxx" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label={`Client Secret${runtimeBool(dingtalk, "client_secret_configured") ? "（已配置，留空不修改）" : ""}`} name="client_secret">
                    <Input.Password placeholder={runtimeBool(dingtalk, "client_secret_configured") ? "已配置，留空保持原值" : "请输入 Client Secret"} autoComplete="new-password" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="Robot Code" name="robot_code">
                    <Input placeholder="机器人编码" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label={`Webhook Secret${runtimeBool(dingtalk, "webhook_secret_configured") ? "（已配置，留空不修改）" : ""}`} name="webhook_secret">
                    <Input.Password placeholder="Webhook 签名密钥，可选" autoComplete="new-password" />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" htmlType="submit" loading={savingRuntime === "dingtalk"} disabled={!isAdmin}>
                保存钉钉配置
              </Button>
            </Form>
          </Card>
        </Col>
      </Row>

      <Card className="dashboard-lower" title={<Space><SafetyCertificateOutlined />发布前综合差距审计</Space>}>
        <Space direction="vertical" size={14} style={{ width: "100%" }}>
          <Space wrap>
            <Tag color={releaseAudit?.local_code_ready ? "green" : "red"}>
              本地代码：{releaseAudit?.local_code_ready ? "已就绪" : "有缺口"}
            </Tag>
            <Tag color={releaseAudit?.formal_private_use_ready ? "green" : "gold"}>
              正式私有化：{releaseAudit?.formal_private_use_ready ? "可投入" : "待人工/部署验收"}
            </Tag>
            <Tag color="green">已完成 {releaseAudit?.summary?.completed ?? 0}</Tag>
            <Tag color="gold">需人工 {releaseAudit?.summary?.manual_required ?? 0}</Tag>
            <Tag color="blue">需部署环境 {releaseAudit?.summary?.deployment_required ?? 0}</Tag>
            <Tag color={(releaseAudit?.summary?.local_gaps ?? 0) > 0 ? "red" : "default"}>
              本地缺口 {releaseAudit?.summary?.local_gaps ?? 0}
            </Tag>
          </Space>
          <Alert
            showIcon
            type={releaseAudit?.local_code_ready ? "success" : "error"}
            message={releaseAudit?.stop_development?.phase_one?.label ?? "停止大功能开发"}
            description={releaseAudit?.stop_development?.phase_one?.message ?? "正在生成审计结论。"}
          />
          <Alert
            showIcon
            type="info"
            message={releaseAudit?.stop_development?.phase_two?.label ?? "停止当前产品线主动开发"}
            description={releaseAudit?.stop_development?.phase_two?.message ?? "需要真实团队运行观察。"}
          />
          <Alert
            showIcon
            type={releaseAudit?.formal_closure?.status === "local_formal_closure_ready" ? "success" : "warning"}
            message={releaseAudit?.formal_closure?.label ?? "本地正式收口"}
            description={releaseAudit?.formal_closure?.message ?? "等待正式收口审计结果。"}
          />
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="聚合检查命令">
              <Typography.Text code>{releaseAudit?.formal_closure?.aggregate_check_command ?? "npm run check:formal-release"}</Typography.Text>
            </Descriptions.Item>
            <Descriptions.Item label="允许维护">
              <Space wrap>
                {(releaseAudit?.formal_closure?.maintenance_boundary?.allowed_changes ?? []).map((item) => (
                  <Tag key={item} color="green">{item}</Tag>
                ))}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="冻结范围">
              <Space wrap>
                {(releaseAudit?.formal_closure?.maintenance_boundary?.blocked_changes ?? []).map((item) => (
                  <Tag key={item} color="red">{item}</Tag>
                ))}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="需明确授权">
              <Space wrap>
                {(releaseAudit?.formal_closure?.maintenance_boundary?.requires_authorization ?? []).map((item) => (
                  <Tag key={item} color="gold">{item}</Tag>
                ))}
              </Space>
            </Descriptions.Item>
          </Descriptions>
          {(releaseAudit?.baselines ?? []).map((item) => (
            <Alert
              key={item.number}
              showIcon
              type={releaseAuditAlertType(item.status)}
              message={`${item.number}. ${item.title ?? "-"} · ${item.status_label ?? item.status ?? "-"}`}
              description={`${item.detail ?? "-"}（阶段：${item.target ?? "-"}）`}
            />
          ))}
          <Typography.Text type="secondary">
            远程 ECS 当前已验收版本：v{releaseAudit?.runtime_boundary?.remote_ecs_deployed_version ?? "1.1.14"}。本页只审计，不会部署远程或触发真实外发。
          </Typography.Text>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card>
            <Descriptions size="small" column={1} title={<Space><SettingOutlined />应用配置</Space>}>
              <Descriptions.Item label="应用">{data?.app?.name ?? "WorkBuddy OSS"}</Descriptions.Item>
              <Descriptions.Item label="环境">{data?.app?.environment ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="数据库">{data?.app?.database ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="持久化">{data?.app?.database_persistence ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="数据库连接">
                <Tag color={data?.app?.database_connected ? "green" : "red"}>
                  {data?.app?.database_connected ? "正常" : "失败"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Redis">
                <Tag color={data?.app?.redis_connected ? "green" : data?.app?.redis_configured ? "orange" : "default"}>
                  {data?.app?.redis_connected ? "已连接" : data?.app?.redis_configured ? "待恢复" : "未配置"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="部署模式">{data?.app?.deployment_mode ?? "-"}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card>
            <Descriptions size="small" column={1} title={<Space><ApiOutlined />模型运行时</Space>}>
              <Descriptions.Item label="Provider">
                <Tag color={data?.llm?.mode === "real" ? "green" : "blue"}>{data?.llm?.provider ?? "mock"}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="模型">{data?.llm?.model ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={data?.llm?.configured ? "green" : "red"}>
                  {data?.llm?.mode === "real" ? (data?.llm?.configured ? "真实可用" : "缺少配置") : "Mock 可用"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="真实 LLM">
                <Tag color={data?.llm?.real_configured ? "green" : "default"}>
                  {data?.llm?.real_configured ? "已配置" : "未配置"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Base URL">{data?.llm?.base_url_configured ? "已配置" : "未配置"}</Descriptions.Item>
              <Descriptions.Item label="API Key">{data?.llm?.api_key_configured ? "已配置" : "未配置"}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card>
            <Descriptions size="small" column={1} title={<Space><ApiOutlined />全局策略</Space>}>
              <Descriptions.Item label="真实 IM Adapter">
                <Tag color={data?.global_policy?.enable_real_im_adapters ? "green" : "default"}>
                  {data?.global_policy?.enable_real_im_adapters ? "已启用" : "未启用"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="外部发送">
                <Tag color={data?.global_policy?.enable_external_send ? "orange" : "blue"}>
                  {data?.global_policy?.enable_external_send ? "已开启" : "已关闭"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="后台任务">
                <Tag color={data?.global_policy?.enable_background_jobs ? "green" : "default"}>
                  {data?.global_policy?.enable_background_jobs ? "已启用" : "未启用"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="任务队列驱动">{data?.global_policy?.background_queue_driver ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="默认发送模式">{sendModeText(data?.global_policy?.default_send_mode)}</Descriptions.Item>
              <Descriptions.Item label="编辑默认模式">
                <Select
                  size="small"
                  value={(data?.global_policy?.default_send_mode === "real" ? "real" : "mock") as "mock" | "real"}
                  loading={savingMode}
                  disabled={!isAdmin}
                  style={{ width: 130 }}
                  onChange={updateMode}
                  options={[
                    { value: "mock", label: "模拟发送" },
                    { value: "real", label: "真实发送" }
                  ]}
                />
              </Descriptions.Item>
              <Descriptions.Item label="实际生效模式">
                <Tag color={data?.global_policy?.effective_send_mode === "real" ? "orange" : "blue"}>
                  {data?.global_policy?.effective_send_mode === "real" ? "真实发送" : "模拟发送"}
                </Tag>
              </Descriptions.Item>
              {data?.global_policy?.real_send_requires_env ? (
                <Descriptions.Item label="提示">
                  <Typography.Text type="warning">当前不会真实发送：还需要 ENABLE_EXTERNAL_SEND=true</Typography.Text>
                </Descriptions.Item>
              ) : null}
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card>
            <Descriptions size="small" column={1} title={<Space><CloudSyncOutlined />飞书运行态</Space>}>
              <Descriptions.Item label="Worker">
                <Tag color={feishu?.worker?.running ? "green" : "red"} icon={<CheckCircleOutlined />}>
                  {feishu?.worker?.running ? "在线" : "离线"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="最近心跳">{formatTime(String(feishu?.worker?.updated_at ?? ""))}</Descriptions.Item>
              <Descriptions.Item label="接收状态">
                <Tag color={feishu?.worker?.receiving_real_messages ? "green" : "orange"}>
                  {feishu?.worker?.receiving_real_messages ? "真实接收中" : "未实时接收"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="启动命令">
                <Typography.Text code>{String(feishu?.worker?.run_command ?? "npm run dev:feishu-stream")}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Docker 启动">
                <Typography.Text code>{String(feishu?.worker?.compose_command ?? "docker compose up feishu-worker")}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="发送开关">
                {feishu?.external_send_enabled ? "允许真实发送" : "默认模拟发送"}
              </Descriptions.Item>
              {feishu?.worker?.health_message ? (
                <Descriptions.Item label="健康提示">
                  <Typography.Text type={feishu.worker.health_level === "error" ? "danger" : "secondary"}>
                    {String(feishu.worker.health_message)}
                  </Typography.Text>
                </Descriptions.Item>
              ) : null}
              {feishu?.worker?.last_error ? (
                <Descriptions.Item label="最近错误">
                  <Typography.Text type="danger">{String(feishu.worker.last_error)}</Typography.Text>
                </Descriptions.Item>
              ) : null}
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card>
            <Descriptions size="small" column={1} title={<Space><SafetyCertificateOutlined />部署与后台任务</Space>}>
              <Descriptions.Item label="总体状态">
                <Tag color={runtimeStack?.status === "ok" ? "green" : "orange"}>
                  {runtimeStack?.status === "ok" ? "运行正常" : "待加固"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="数据库 URL">
                <Typography.Text code>{runtimeStack?.database?.url_masked ?? "-"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Redis URL">
                <Typography.Text code>{runtimeStack?.redis?.url_masked || "-"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="后台任务状态">
                <Tag color={runtimeStack?.background_jobs?.ready ? "green" : runtimeStack?.background_jobs?.enabled ? "red" : "default"}>
                  {runtimeStack?.background_jobs?.enabled
                    ? (runtimeStack?.background_jobs?.ready ? "队列就绪" : "队列未就绪")
                    : "当前关闭"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="后台任务 Worker">
                <Tag color={runtimeStack?.background_jobs?.worker?.running ? "green" : "red"}>
                  {runtimeStack?.background_jobs?.worker?.running ? "在线" : "离线"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="计划任务">
                <Typography.Text>{(runtimeStack?.background_jobs?.scheduled_jobs ?? []).join(" / ") || "-"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="备份状态">
                <Tag color={runtimeStack?.backup?.ready ? "green" : "red"}>
                  {runtimeStack?.backup?.ready ? "可备份" : "不可备份"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="备份目录">
                <Typography.Text code>{runtimeStack?.backup?.backup_dir ?? "apps/api/data/backups"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="最近备份">
                <Typography.Text>{runtimeStack?.backup?.latest_backup ?? "暂无"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="创建备份">
                <Typography.Text code>{runtimeStack?.backup?.create_command ?? "npm run backup:create"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="恢复预案">
                <Typography.Text code>{runtimeStack?.backup?.restore_plan_command ?? "npm run backup:restore-plan -- <backup-path>"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="日志状态">
                <Tag color={runtimeStack?.logs?.ready ? "green" : "orange"}>
                  {runtimeStack?.logs?.ready ? "可排障" : "待生成"}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="日志目录">
                <Typography.Text code>{runtimeStack?.logs?.log_dir ?? "apps/api/data/logs"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="最近日志">
                <Typography.Text>{(runtimeStack?.logs?.files ?? []).map((file) => file.name).slice(0, 3).join(" / ") || "暂无"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="查看日志">
                <Typography.Text code>{runtimeStack?.logs?.tail_command ?? "npm run logs:tail"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="本地启动">
                <Typography.Text code>{runtimeStack?.deployment?.local_runtime_jobs_command ?? "npm run dev:runtime-jobs"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Compose 启动">
                <Typography.Text code>{runtimeStack?.deployment?.compose_up_command ?? "docker compose up --build"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="提示">
                <Typography.Text type={runtimeStack?.status === "ok" ? "secondary" : "warning"}>
                  {runtimeStack?.background_jobs?.advice ?? runtimeStack?.database?.advice ?? "-"}
                </Typography.Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      {feishu?.worker?.receiving_real_messages ? null : (
        <Alert
          className="dashboard-lower"
          type={feishu?.worker?.health_level === "error" ? "error" : "warning"}
          showIcon
          message="飞书真实接收 worker 当前不可依赖"
          description={
            <Space direction="vertical" size={4}>
              {(Array.isArray(feishu?.worker?.recovery_steps) ? feishu.worker.recovery_steps : []).map((step) => (
                <Typography.Text key={String(step)}>{String(step)}</Typography.Text>
              ))}
            </Space>
          }
        />
      )}

      <Card className="dashboard-lower" title={<Space><SafetyCertificateOutlined />真实运行检查清单</Space>}>
        <Space wrap>
          <RiskTag ok={Boolean(data?.llm?.real_configured)} text="真实 LLM 已配置" />
          <RiskTag ok={Boolean(data?.app?.database_connected)} text="数据库连接正常" />
          <RiskTag ok={!data?.global_policy?.enable_background_jobs || Boolean(data?.app?.redis_connected)} text="后台任务依赖满足" />
          <RiskTag ok={Boolean(data?.global_policy?.enable_external_send)} text="ENABLE_EXTERNAL_SEND=true" />
          <RiskTag ok={Boolean(data?.global_policy?.enable_background_jobs)} text="后台任务已启用" />
          <RiskTag ok={data?.global_policy?.default_send_mode === "real"} text="默认模式=真实发送" />
          <RiskTag ok={data?.global_policy?.effective_send_mode === "real"} text="实际生效=真实发送" />
          <RiskTag ok={Boolean(feishu?.configured)} text="飞书密钥已配置" />
          <RiskTag ok={Boolean(feishu?.worker?.running)} text="Worker 在线" />
          <Button size="small" loading={safeModeSaving} onClick={enableSafeDemoMode} disabled={!isAdmin}>
            一键切到安全演示模式
          </Button>
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          密钥优先从本地加密仓库读取，旧版环境文件仅用于兼容迁移；页面只展示配置状态。飞书测试环境可以打开真实发送，但仍建议通过审批队列验证每一次外发。
        </Typography.Paragraph>
      </Card>

      <Typography.Paragraph type="secondary" className="table-ux-hint">
        表格可横向滚动；按住表头右侧边缘可调整列宽。
      </Typography.Paragraph>
      <ResizableTable
        className="dashboard-lower"
        size="small"
        loading={loading}
        rowKey={(row) => String(row.channel)}
        dataSource={data?.channels ?? []}
        columns={columns}
        scroll={{ x: 1500 }}
        pagination={false}
      />
    </>
  );
}

function capabilityText(value: boolean | string | undefined) {
  if (value === true) return "可用";
  if (value === "mock_only") return "仅模拟";
  return "待实现";
}

function sendModeText(value?: string) {
  if (value === "real") return "真实发送";
  if (value === "mock") return "模拟发送";
  return value ?? "-";
}

function optionalSecret(value: unknown) {
  const text = typeof value === "string" ? value.trim() : "";
  return text ? text : undefined;
}

function runtimeString(channel: ChannelStatus | undefined, key: string) {
  const value = channel?.runtime_values?.[key];
  return typeof value === "string" ? value : "";
}

function runtimeBool(channel: ChannelStatus | undefined, key: string) {
  return channel?.runtime_values?.[key] === true;
}

function RiskTag({ ok, text }: { ok: boolean; text: string }) {
  return <Tag color={ok ? "green" : "default"}>{text}: {ok ? "通过" : "未满足"}</Tag>;
}

function releaseAuditAlertType(status?: string): "success" | "warning" | "info" | "error" {
  if (status === "completed") return "success";
  if (status === "manual_required") return "warning";
  if (status === "deployment_required") return "info";
  return "error";
}

function LlmSmokeResult({ result }: { result: LLMSmokeTestResult }) {
  return (
    <Alert
      showIcon
      type={result.ok ? "success" : "warning"}
      style={{ marginTop: 14 }}
      message={result.ok ? "模型 smoke test 通过" : "模型 smoke test 未通过"}
      description={(
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <Descriptions size="small" column={2}>
            <Descriptions.Item label="Provider">{result.provider ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="模型">{result.model ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="模式">{result.mode ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="耗时">{result.latency_ms == null ? "-" : `${result.latency_ms}ms`}</Descriptions.Item>
            <Descriptions.Item label="Token">{result.usage?.total_tokens ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="错误类型">{result.error_type ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="证书包" span={2}>
              {result.certificate?.certifi_available ? result.certificate.ca_bundle ?? "certifi 可用" : result.certificate?.advice ?? "-"}
            </Descriptions.Item>
          </Descriptions>
          <Typography.Text>{result.message ?? "-"}</Typography.Text>
          {result.error ? <Typography.Text type="danger">{result.error}</Typography.Text> : null}
          {result.advice ? <Typography.Text type="secondary">{result.advice}</Typography.Text> : null}
        </Space>
      )}
    />
  );
}
