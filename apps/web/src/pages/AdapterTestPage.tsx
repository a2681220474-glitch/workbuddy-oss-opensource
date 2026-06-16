import { ImportOutlined, ExperimentOutlined, PlayCircleOutlined, UploadOutlined } from "@ant-design/icons";
import { Alert, App as AntdApp, Button, Card, Col, Input, Row, Select, Space, Tag, Typography, Upload } from "antd";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import type { AdapterImportResult, AdapterPreviewResult } from "../types";
import { hashTarget, type NavTarget } from "../utils/navigation";

const examples: Record<string, string> = {
  feishu: JSON.stringify({
    schema: "2.0",
    header: {
      event_id: "evt_preview_001",
      event_type: "im.message.receive_v1",
      create_time: "1779358448142"
    },
    event: {
      sender: { sender_id: { open_id: "ou_preview_user" }, sender_type: "user" },
      message: {
        message_id: "om_preview_001",
        chat_id: "oc_preview_chat",
        chat_type: "p2p",
        message_type: "text",
        create_time: "1779358448142",
        content: "{\"text\":\"想了解报价和试用流程\"}"
      }
    }
  }, null, 2),
  wecom: JSON.stringify({
    event_type: "mock.message.receive",
    message_id: "wecom_mock_001",
    user_id: "wm_preview_user",
    chat_id: "wr_preview_group",
    chat_name: "企微测试群",
    text: "客户想了解售后响应 SLA"
  }, null, 2),
  dingtalk: JSON.stringify({
    event_type: "mock.message.receive",
    message_id: "ding_mock_001",
    user_id: "ding_preview_user",
    chat_id: "ding_preview_group",
    chat_name: "钉钉测试群",
    text: "想预约演示并了解价格"
  }, null, 2)
};

const feishuPresets: Array<{ key: string; label: string; payload: string }> = [
  { key: "text", label: "文本", payload: examples.feishu },
  {
    key: "file",
    label: "文件",
    payload: JSON.stringify({
      schema: "2.0",
      header: {
        event_id: "evt_preview_file_001",
        event_type: "im.message.receive_v1",
        create_time: "1779358448142"
      },
      event: {
        sender: { sender_id: { open_id: "ou_preview_file_user" }, sender_name: "飞书测试用户A", sender_type: "user" },
        message: {
          message_id: "om_preview_file_001",
          chat_id: "oc_preview_file_chat",
          chat_type: "p2p",
          message_type: "file",
          create_time: "1779358448142",
          content: JSON.stringify({
            file_key: "file_preview_001",
            file_name: "报价方案-v0.15.pdf"
          })
        }
      }
    }, null, 2)
  },
  {
    key: "post",
    label: "富文本",
    payload: JSON.stringify({
      schema: "2.0",
      header: {
        event_id: "evt_preview_post_001",
        event_type: "im.message.receive_v1",
        create_time: "1779358448142"
      },
      event: {
        sender: { sender_id: { open_id: "ou_preview_post_user" }, sender_name: "飞书测试用户B", sender_type: "user" },
        message: {
          message_id: "om_preview_post_001",
          chat_id: "oc_preview_post_chat",
          chat_type: "p2p",
          message_type: "post",
          create_time: "1779358448142",
          content: JSON.stringify({
            zh_cn: {
              title: "候选人简历摘要",
              content: [
                [
                  { tag: "text", text: "候选人王宁，应聘销售岗位，5 年 SaaS 销售经验，希望安排面试。" }
                ]
              ]
            }
          })
        }
      }
    }, null, 2)
  },
  {
    key: "image",
    label: "图片",
    payload: JSON.stringify({
      schema: "2.0",
      header: {
        event_id: "evt_preview_image_001",
        event_type: "im.message.receive_v1",
        create_time: "1779358448142"
      },
      event: {
        sender: { sender_id: { open_id: "ou_preview_image_user" }, sender_name: "飞书测试用户C", sender_type: "user" },
        message: {
          message_id: "om_preview_image_001",
          chat_id: "oc_preview_image_chat",
          chat_type: "group",
          message_type: "image",
          create_time: "1779358448142",
          content: JSON.stringify({
            image_key: "img_preview_001"
          })
        }
      }
    }, null, 2)
  }
];

export function AdapterTestPage() {
  const { message } = AntdApp.useApp();
  const [channel, setChannel] = useState("feishu");
  const [payloadText, setPayloadText] = useState(examples.feishu);
  const [preview, setPreview] = useState<AdapterPreviewResult>();
  const [importResult, setImportResult] = useState<AdapterImportResult>();
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);

  const parsedPayload = useMemo(() => {
    try {
      return JSON.parse(payloadText) as Record<string, unknown>;
    } catch {
      return undefined;
    }
  }, [payloadText]);

  const runPreview = async () => {
    if (!parsedPayload) {
      message.error("请输入合法 JSON");
      return;
    }
    setLoading(true);
    try {
      setPreview(await api.previewAdapterPayload({ channel, payload: parsedPayload }));
      message.success("已生成 MessageEvent 预览");
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "预览失败");
    } finally {
      setLoading(false);
    }
  };

  const importPayload = async () => {
    if (!parsedPayload) {
      message.error("请输入合法 JSON");
      return;
    }
    setImporting(true);
    try {
      const result = await api.importAdapterPayload({ channel, payload: parsedPayload });
      setImportResult(result);
      const firstMessage = result.messages?.[0];
      message.success(result.status === "imported" ? "已导入 MessageEvent，并触发 Agent 流水线" : "消息已存在，本次跳过导入");
      if (firstMessage?.id) {
        window.location.hash = `#messages?id=${firstMessage.id}`;
      }
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "导入失败");
    } finally {
      setImporting(false);
    }
  };

  const switchChannel = (next: string) => {
    setChannel(next);
    setPayloadText(examples[next] ?? "{}");
    setPreview(undefined);
    setImportResult(undefined);
  };

  return (
    <>
      <PageHeader
        title="Adapter 测试台"
        extra={
          <>
            <Button icon={<ImportOutlined />} loading={importing} onClick={importPayload}>
              一键导入为 MessageEvent
            </Button>
            <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={runPreview}>
              预览标准化
            </Button>
          </>
        }
      />
      <Alert
        className="api-alert"
        showIcon
        type="info"
        message="测试台支持预览，也支持安全导入为 MessageEvent"
        description="飞书使用真实明文事件解析器；企业微信和钉钉使用 mock parser。点击导入会进入 MessageEvent/Agent/Approval 流水线，但不会绕过审批直接外发。"
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card
            title={<Space><ExperimentOutlined />输入 Payload</Space>}
            extra={
              <Space>
                <Upload
                  accept=".json,application/json"
                  showUploadList={false}
                  beforeUpload={(file) => {
                    file.text().then(setPayloadText);
                    return false;
                  }}
                >
                  <Button icon={<UploadOutlined />}>上传 JSON</Button>
                </Upload>
                <Select
                  value={channel}
                  style={{ width: 140 }}
                  onChange={switchChannel}
                  options={[
                    { value: "feishu", label: "飞书" },
                    { value: "wecom", label: "企业微信" },
                    { value: "dingtalk", label: "钉钉" }
                  ]}
                />
              </Space>
            }
          >
            <Input.TextArea
              rows={22}
              value={payloadText}
              status={parsedPayload ? undefined : "error"}
              onChange={(event) => setPayloadText(event.target.value)}
            />
            {channel === "feishu" ? (
              <Space wrap style={{ marginTop: 12 }}>
                {feishuPresets.map((preset) => (
                  <Button
                    key={preset.key}
                    size="small"
                    onClick={() => {
                      setPayloadText(preset.payload);
                      setPreview(undefined);
                      setImportResult(undefined);
                    }}
                  >
                    飞书{preset.label}样例
                  </Button>
                ))}
              </Space>
            ) : null}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="MessageEvent 预览">
            {preview ? (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Space>
                  <Tag color={preview.supported ? "green" : "blue"}>{preview.channel_label}</Tag>
                  <Tag>{preview.mode}</Tag>
                  <Typography.Text type="secondary">{preview.event_type}</Typography.Text>
                </Space>
                <pre className="json-block">{JSON.stringify(preview.message_event_preview ?? {}, null, 2)}</pre>
                {(preview.notes ?? []).map((note) => (
                  <Typography.Paragraph key={note}>{note}</Typography.Paragraph>
                ))}
              </Space>
            ) : (
              <Typography.Text type="secondary">点击“预览标准化”后，这里会显示统一 MessageEvent 输入。</Typography.Text>
            )}
          </Card>
          {importResult ? (
            <Card title="导入链路" className="dashboard-lower">
              <Space direction="vertical" size={10} style={{ width: "100%" }}>
                <Space wrap>
                  <Tag color={importResult.status === "imported" ? "green" : "default"}>{importResult.status}</Tag>
                  <Tag>批次 #{importResult.batch?.id ?? "-"}</Tag>
                </Space>
                {(importResult.traces ?? []).map((trace) => (
                  <Space key={String(trace.message_id)} wrap>
                    {trace.message_id ? <a href={hashTarget("messages", trace.message_id)}>查看消息#{trace.message_id}</a> : null}
                    {trace.agent_run_id ? <a href={hashTarget("agent-runs", trace.agent_run_id)}>查看运行#{trace.agent_run_id}</a> : null}
                    {(trace.approval_ids ?? []).map((id) => (
                      <a key={String(id)} href={hashTarget("approvals", id)}>查看审批#{id}</a>
                    ))}
                    {(trace.related_objects ?? []).map((item) => (
                      <a key={`${item.type}-${item.id}`} href={hashTarget(objectTarget(item.type), item.id)}>
                        查看{objectLabel(item.type)}#{item.id}
                      </a>
                    ))}
                  </Space>
                ))}
                {(importResult.notes ?? []).map((note) => (
                  <Typography.Paragraph key={note}>{note}</Typography.Paragraph>
                ))}
              </Space>
            </Card>
          ) : null}
        </Col>
      </Row>
    </>
  );
}

function objectTarget(type: string): NavTarget {
  if (type === "lead") return "leads";
  if (type === "ticket") return "tickets";
  if (type === "task") return "tasks";
  if (type === "candidate") return "candidates";
  if (type === "knowledge_gap") return "knowledge";
  if (type === "report") return "reports";
  return "messages";
}

function objectLabel(type: string) {
  const labels: Record<string, string> = {
    lead: "线索",
    ticket: "工单",
    task: "任务",
    candidate: "候选人",
    knowledge_gap: "知识缺口",
    report: "报告"
  };
  return labels[type] ?? type;
}
