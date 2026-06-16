import { InboxOutlined } from "@ant-design/icons";
import { Alert, App as AntdApp, Button, Card, Col, Form, Input, Row, Select, Table, Upload } from "antd";
import type { UploadProps } from "antd";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import type { ImportPayload, ImportResult, KnowledgeImportConfirmResult, KnowledgeImportPayload, KnowledgeImportPreviewResult } from "../types";
import { detectSourceType, previewRows } from "../utils/importPreview";

const { Dragger } = Upload;

export function ImportPage() {
  const { message } = AntdApp.useApp();
  const [form] = Form.useForm<ImportPayload>();
  const [filename, setFilename] = useState<string>();
  const [content, setContent] = useState("");
  const [sourceType, setSourceType] = useState<ImportPayload["source_type"]>("json");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ImportResult>();
  const [knowledgeForm] = Form.useForm<KnowledgeImportPayload>();
  const [knowledgeFilename, setKnowledgeFilename] = useState<string>();
  const [knowledgeSourceType, setKnowledgeSourceType] = useState<KnowledgeImportPayload["source_type"]>("markdown");
  const [knowledgePreview, setKnowledgePreview] = useState<KnowledgeImportPreviewResult>();
  const [knowledgeResult, setKnowledgeResult] = useState<KnowledgeImportConfirmResult>();
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);

  const rows = useMemo(() => previewRows(content, sourceType), [content, sourceType]);

  const uploadProps: UploadProps = {
    multiple: false,
    accept: ".csv,.json,.txt,application/json,text/csv,text/plain",
    showUploadList: false,
    beforeUpload: async (file) => {
      const text = await file.text();
      const detected = detectSourceType(file.name, text);
      setFilename(file.name);
      setContent(text);
      setSourceType(detected);
      form.setFieldsValue({ filename: file.name, content: text, source_type: detected });
      return false;
    }
  };

  const knowledgeUploadProps: UploadProps = {
    multiple: false,
    accept: ".md,.markdown,.csv,.txt,text/markdown,text/csv,text/plain",
    showUploadList: false,
    beforeUpload: async (file) => {
      const text = await file.text();
      const detected = detectKnowledgeSourceType(file.name, text);
      setKnowledgeFilename(file.name);
      setKnowledgeSourceType(detected);
      knowledgeForm.setFieldsValue({ filename: file.name, content: text, source_type: detected });
      setKnowledgePreview(undefined);
      setKnowledgeResult(undefined);
      return false;
    }
  };

  async function submitImport(values: ImportPayload) {
    setSubmitting(true);
    setResult(undefined);
    try {
      const detected = values.source_type ?? detectSourceType(values.filename, values.content);
      const response = await api.importMessages({
        source_type: detected,
        filename: values.filename || filename,
        content: values.content
      });
      setResult(response);
      message.success("导入请求已提交");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "导入失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function previewKnowledge(values: KnowledgeImportPayload) {
    setKnowledgeLoading(true);
    setKnowledgePreview(undefined);
    setKnowledgeResult(undefined);
    try {
      const payload = normalizeKnowledgePayload(values, knowledgeFilename);
      const response = await api.previewKnowledgeImport(payload);
      setKnowledgePreview(response);
      message.success("知识导入预览已生成");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "知识预览失败");
    } finally {
      setKnowledgeLoading(false);
    }
  }

  async function confirmKnowledgeImport() {
    const values = knowledgeForm.getFieldsValue();
    setKnowledgeLoading(true);
    try {
      const payload = normalizeKnowledgePayload(values, knowledgeFilename);
      const response = await api.confirmKnowledgeImport(payload);
      setKnowledgeResult(response);
      setKnowledgePreview(response.preview);
      message.success("知识导入已确认");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "知识导入失败");
    } finally {
      setKnowledgeLoading(false);
    }
  }

  return (
    <>
      <PageHeader title="消息导入" />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card>
            <Dragger {...uploadProps}>
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">拖入 CSV / JSON / TXT，或点击选择文件</p>
            </Dragger>
            <Form
              form={form}
              layout="vertical"
              className="import-form"
              initialValues={{ source_type: sourceType, content }}
              onFinish={submitImport}
            >
              <Form.Item name="source_type" label="格式" rules={[{ required: true }]}>
                <Select
                  value={sourceType}
                  onChange={(value) => {
                    setSourceType(value);
                    form.setFieldValue("source_type", value);
                  }}
                  options={[
                    { label: "JSON 文件", value: "json" },
                    { label: "CSV", value: "csv" },
                    { label: "文本粘贴", value: "text" }
                  ]}
                />
              </Form.Item>
              <Form.Item name="filename" label="文件名">
                <Input placeholder="demo-messages.json" onChange={(event) => setFilename(event.target.value)} />
              </Form.Item>
              <Form.Item name="content" label="内容" rules={[{ required: true, message: "请输入或上传聊天记录" }]}>
                <Input.TextArea
                  rows={14}
                  placeholder='[{"sender_name":"张三","text":"这个方案多少钱？","timestamp":"2026-05-20T10:30:00+08:00"}]'
                  onChange={(event) => {
                    const nextContent = event.target.value;
                    setContent(nextContent);
                    if (!filename) {
                      const detected = detectSourceType(undefined, nextContent);
                      setSourceType(detected);
                      form.setFieldValue("source_type", detected);
                    }
                  }}
                />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={submitting} block>
                导入并运行智能体路由
              </Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          {result ? (
            <Alert
              className="import-result"
              type="success"
              showIcon
              message="导入完成"
              description={`消息 ${result.imported_count ?? result.message_count ?? 0} 条，工单 ${result.created_tickets ?? 0} 个，线索 ${result.created_leads ?? 0} 个，审批 ${result.created_approvals ?? 0} 条。`}
            />
          ) : null}
          <Card title="本地预览">
            <Table
              size="small"
              rowKey={(_, index) => String(index)}
              dataSource={rows}
              pagination={false}
              columns={[
                { title: "渠道", dataIndex: "channel", width: 100 },
                { title: "发送人", dataIndex: "sender_name", width: 140 },
                { title: "时间", dataIndex: "timestamp", width: 200 },
                { title: "内容", dataIndex: "text" }
              ]}
            />
          </Card>
        </Col>
      </Row>
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={10}>
          <Card title="知识库导入">
            <Dragger {...knowledgeUploadProps}>
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">拖入 Markdown / FAQ TXT / CSV，或点击选择文件</p>
            </Dragger>
            <Form
              form={knowledgeForm}
              layout="vertical"
              className="import-form"
              initialValues={{ source_type: knowledgeSourceType, default_category: "general", default_mode: "item", publish: false, content: "" }}
              onFinish={previewKnowledge}
            >
              <Form.Item name="source_type" label="格式" rules={[{ required: true }]}>
                <Select
                  value={knowledgeSourceType}
                  onChange={(value) => {
                    setKnowledgeSourceType(value);
                    knowledgeForm.setFieldValue("source_type", value);
                  }}
                  options={[
                    { label: "Markdown", value: "markdown" },
                    { label: "FAQ 文本", value: "faq" },
                    { label: "CSV", value: "csv" }
                  ]}
                />
              </Form.Item>
              <Form.Item name="filename" label="来源文件名">
                <Input placeholder="faq.md" onChange={(event) => setKnowledgeFilename(event.target.value)} />
              </Form.Item>
              <Form.Item name="default_category" label="默认分类" rules={[{ required: true }]}>
                <Input placeholder="support" />
              </Form.Item>
              <Form.Item name="default_mode" label="默认导入为">
                <Select options={[
                  { label: "KnowledgeItem", value: "item" },
                  { label: "KnowledgeGap", value: "gap" }
                ]} />
              </Form.Item>
              <Form.Item name="publish" label="条目状态">
                <Select options={[
                  { label: "草稿", value: false },
                  { label: "已发布", value: true }
                ]} />
              </Form.Item>
              <Form.Item name="content" label="内容" rules={[{ required: true, message: "请输入或上传知识内容" }]}>
                <Input.TextArea
                  rows={12}
                  placeholder={"# 登录失败\n用户登录失败时，先确认账号状态和最近错误码。\n\nQ: 如何重置密码？\nA: 在设置页点击重置密码。"}
                  onChange={(event) => {
                    const nextContent = event.target.value;
                    if (!knowledgeFilename) {
                      const detected = detectKnowledgeSourceType(undefined, nextContent);
                      setKnowledgeSourceType(detected);
                      knowledgeForm.setFieldValue("source_type", detected);
                    }
                    setKnowledgePreview(undefined);
                    setKnowledgeResult(undefined);
                  }}
                />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={knowledgeLoading} block>
                生成知识导入预览
              </Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          {knowledgeResult ? (
            <Alert
              className="import-result"
              type="success"
              showIcon
              message="知识导入完成"
              description={`知识条目 ${knowledgeResult.created_items?.length ?? 0} 条，知识缺口 ${knowledgeResult.created_gaps?.length ?? 0} 条。`}
            />
          ) : null}
          <Card
            title="知识导入预览"
            extra={
              <Button type="primary" disabled={!knowledgePreview?.rows?.length} loading={knowledgeLoading} onClick={confirmKnowledgeImport}>
                确认导入
              </Button>
            }
          >
            <Table
              size="small"
              rowKey="row_index"
              dataSource={knowledgePreview?.rows ?? []}
              pagination={{ pageSize: 8 }}
              columns={[
                { title: "行", dataIndex: "row_index", width: 70 },
                { title: "类型", dataIndex: "mode", width: 110 },
                { title: "标题/问题", dataIndex: "title", width: 220 },
                { title: "分类", dataIndex: "category", width: 120 },
                { title: "状态", dataIndex: "status", width: 110 },
                { title: "答案", dataIndex: "answer" },
                { title: "提示", dataIndex: "warnings", width: 180, render: (value: string[]) => value?.join("；") || "-" }
              ]}
            />
          </Card>
        </Col>
      </Row>
    </>
  );
}

function detectKnowledgeSourceType(filename = "", content = ""): KnowledgeImportPayload["source_type"] {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".csv")) return "csv";
  if (/^(q|question|问|问题)[:：]/im.test(content)) return "faq";
  return "markdown";
}

function normalizeKnowledgePayload(values: KnowledgeImportPayload, fallbackFilename?: string): KnowledgeImportPayload {
  return {
    source_type: values.source_type ?? "markdown",
    filename: values.filename || fallbackFilename,
    content: values.content,
    default_category: values.default_category || "general",
    default_mode: values.default_mode || "item",
    publish: Boolean(values.publish)
  };
}
