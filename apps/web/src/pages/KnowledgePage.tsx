import { BranchesOutlined, CheckCircleOutlined, EditOutlined, FileDoneOutlined, SendOutlined } from "@ant-design/icons";
import { App as AntdApp, Button, Card, Descriptions, Drawer, Form, Input, InputNumber, List, Modal, Select, Space, Tabs, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ReactNode } from "react";
import { useCallback, useMemo, useState } from "react";
import { api } from "../api/client";
import { ApiErrorAlert } from "../components/ApiErrorAlert";
import { BusinessObjectDetailDrawer } from "../components/BusinessObjectDetailDrawer";
import { PageHeader } from "../components/PageHeader";
import { ReloadButton } from "../components/ReloadButton";
import { ResizableTable } from "../components/ResizableTable";
import { StatusTag } from "../components/StatusTag";
import { useAsyncData } from "../components/useAsyncData";
import type {
  KnowledgeGap,
  KnowledgeGapDetail as KnowledgeGapDetailPayload,
  KnowledgeGraphNode,
  KnowledgeGraphResponse,
  KnowledgeItem,
  KnowledgeItemDetail as KnowledgeItemDetailPayload,
  KnowledgeObsidianExport,
  KnowledgeQualityDashboard,
  KnowledgeQualityItem,
  KnowledgeSearchResponse
} from "../types";
import { formatTime, shortText } from "../utils/format";
import { hashTarget, isTargetId } from "../utils/navigation";
import { filterBySearch } from "../utils/search";
import { useHashId } from "../utils/useHashId";

const knowledgeItemStatusOptions = [
  { label: "草稿", value: "draft" },
  { label: "待审核", value: "pending_review" },
  { label: "已发布", value: "published" },
  { label: "已归档", value: "archived" }
];

const knowledgeQualityStatusOptions = [
  { label: "健康", value: "healthy" },
  { label: "待复审", value: "needs_review" },
  { label: "已过期", value: "expired" },
  { label: "待优化", value: "needs_optimization" },
  { label: "建议归档", value: "archive_suggested" }
];

export function KnowledgePage() {
  const { message } = AntdApp.useApp();
  const [gapStatus, setGapStatus] = useState<string>();
  const [itemStatus, setItemStatus] = useState<string>();
  const [category, setCategory] = useState<string>();
  const [search, setSearch] = useState("");
  const [activeDetail, setActiveDetail] = useState<KnowledgeDetail>();
  const [workflowDetail, setWorkflowDetail] = useState<{ type: "knowledge_gap" | "knowledge_item"; id: KnowledgeGap["id"] }>();
  const [editingItem, setEditingItem] = useState<KnowledgeItem>();
  const [obsidianExport, setObsidianExport] = useState<KnowledgeObsidianExport>();
  const [retrievalQuery, setRetrievalQuery] = useState("");
  const [retrievalResult, setRetrievalResult] = useState<KnowledgeSearchResponse>();
  const [retrievalLoading, setRetrievalLoading] = useState(false);
  const [editForm] = Form.useForm();
  const loadGaps = useCallback(() => api.getKnowledgeGaps(gapStatus, category), [category, gapStatus]);
  const gaps = useAsyncData(loadGaps);
  const loadItems = useCallback(() => api.getKnowledgeItems(itemStatus, category), [category, itemStatus]);
  const items = useAsyncData(loadItems);
  const loadGraph = useCallback(() => api.getKnowledgeGraph(category, itemStatus), [category, itemStatus]);
  const graph = useAsyncData(loadGraph);
  const loadQuality = useCallback(() => api.getKnowledgeQuality(category), [category]);
  const quality = useAsyncData(loadQuality);
  const targetId = useHashId();
  const gapRows = useMemo(() => filterBySearch((gaps.data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "id", "category", "question", "suggested_answer", "status", "source_message_id", "examples_json"
  ]) as unknown as KnowledgeGap[], [gaps.data?.items, search]);
  const itemRows = useMemo(() => filterBySearch((items.data?.items ?? []) as unknown as Record<string, unknown>[], search, [
    "id", "source_gap_id", "title", "answer", "category", "status"
  ]) as unknown as KnowledgeItem[], [items.data?.items, search]);
  const categoryOptions = useMemo(() => {
    const values = new Set<string>();
    gaps.data?.items.forEach((item) => {
      if (item.category) values.add(item.category);
    });
    items.data?.items.forEach((item) => {
      if (item.category) values.add(item.category);
    });
    return Array.from(values).map((value) => ({ label: value, value }));
  }, [gaps.data?.items, items.data?.items]);

  const acceptGap = async (id: KnowledgeGap["id"]) => {
    try {
      await api.acceptKnowledgeGap(id);
      message.success("已采纳为知识条目");
      await gaps.reload();
      await items.reload();
      await graph.reload();
      await quality.reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "采纳失败");
    }
  };

  const ignoreGap = async (id: KnowledgeGap["id"]) => {
    try {
      await api.ignoreKnowledgeGap(id);
      message.success("已忽略知识缺口");
      await gaps.reload();
      await graph.reload();
      await quality.reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "忽略失败");
    }
  };

  const updateItemStatus = async (id: KnowledgeItem["id"], status: string) => {
    try {
      await api.updateKnowledgeItem(id, { status, change_summary: statusSummary(status) });
      message.success("知识条目状态已更新");
      await items.reload();
      await graph.reload();
      await quality.reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "更新失败");
    }
  };

  const openItemEditor = (item: KnowledgeItem) => {
    setEditingItem(item);
    editForm.setFieldsValue({
      title: item.title,
      answer: item.answer,
      category: item.category ?? "general",
      status: item.status ?? "draft",
      review_due_at: item.review_due_at ?? "",
      quality_status: item.quality_status ?? "healthy",
      quality_score: item.quality_score ?? 80,
      change_summary: ""
    });
  };

  const saveItemEdit = async () => {
    if (!editingItem) return;
    try {
      const values = normalizeKnowledgeItemFormValues(await editForm.validateFields());
      await api.updateKnowledgeItem(editingItem.id, values);
      message.success("知识条目已更新");
      setEditingItem(undefined);
      await items.reload();
      await graph.reload();
      await quality.reload();
    } catch (caught) {
      if (caught instanceof Error) message.error(caught.message);
    }
  };

  const openGraphNode = (node: KnowledgeGraphNode) => {
    if (node.object_type === "knowledge_item" && node.object_id) {
      const item = items.data?.items.find((row) => String(row.id) === String(node.object_id));
      setActiveDetail({ type: "item", data: item ?? graphNodeToItem(node) });
      return;
    }
    if (node.object_type === "knowledge_gap" && node.object_id) {
      const gap = gaps.data?.items.find((row) => String(row.id) === String(node.object_id));
      setActiveDetail({ type: "gap", data: gap ?? graphNodeToGap(node) });
      return;
    }
    const target = graphNodeTarget(node);
    if (target) window.location.hash = target;
    if (!target && node.category) setCategory(node.category);
  };

  const openObsidianExport = async () => {
    try {
      setObsidianExport(await api.exportKnowledgeObsidianDraft(category));
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "导出草案失败");
    }
  };

  const markItemReviewed = async (item: KnowledgeItem) => {
    try {
      await api.updateKnowledgeItem(item.id, {
        last_reviewed_at: new Date().toISOString(),
        review_due_at: futureDateIso(90),
        quality_status: "healthy",
        quality_score: Math.max(item.quality_score ?? 80, 80),
        change_summary: "完成知识复审，质量状态恢复健康"
      });
      message.success("已标记为完成复审");
      await items.reload();
      await graph.reload();
      await quality.reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "复审更新失败");
    }
  };

  const runKnowledgeSearch = async (query = retrievalQuery) => {
    if (!query.trim()) {
      message.warning("请输入检索问题");
      return;
    }
    setRetrievalLoading(true);
    try {
      const response = await api.searchKnowledge({
        query: query.trim(),
        category,
        limit: 8,
        include_drafts: false,
        record_hit: true
      });
      setRetrievalQuery(query.trim());
      setRetrievalResult(response);
      await quality.reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "知识检索失败");
    } finally {
      setRetrievalLoading(false);
    }
  };

  const submitRetrievalFeedback = async (hitId: string | number, status: "useful" | "not_useful") => {
    try {
      await api.updateKnowledgeHitFeedback(hitId, status);
      message.success(status === "useful" ? "已记录为有帮助" : "已记录为无帮助并进入复审");
      await quality.reload();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "反馈提交失败");
    }
  };

  const rebuildKnowledgeIndex = async () => {
    try {
      const result = await api.rebuildKnowledgeIndex();
      message.success(`已重建 ${result.indexed_items} 条知识向量索引`);
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "索引重建失败");
    }
  };

  const gapColumns: ColumnsType<KnowledgeGap> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "分类", dataIndex: "category", width: 120, render: (value) => value ?? "general" },
    { title: "问题", dataIndex: "question", width: 300, render: (value) => shortText(value, 90) },
    { title: "建议答案", dataIndex: "suggested_answer", width: 340, render: (value) => shortText(value, 90) },
    { title: "次数", dataIndex: "occurrence_count", width: 80, render: (value) => value ?? 1 },
    { title: "状态", dataIndex: "status", width: 120, render: (value) => <StatusTag value={value} /> },
    {
      title: "来源",
      dataIndex: "source_message_id",
      width: 120,
      render: (value) => value ? <a href={hashTarget("messages", value)}>消息#{value}</a> : "-"
    },
    {
      title: "操作",
      width: 270,
      fixed: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => setActiveDetail({ type: "gap", data: row })}>
            详情
          </Button>
          <Button size="small" onClick={() => setWorkflowDetail({ type: "knowledge_gap", id: row.id })}>
            处理
          </Button>
          <Button size="small" disabled={row.status === "accepted"} onClick={() => acceptGap(row.id)}>
            采纳
          </Button>
          <Button size="small" disabled={row.status === "ignored" || row.status === "accepted"} onClick={() => ignoreGap(row.id)}>
            忽略
          </Button>
        </Space>
      )
    }
  ];

  const itemColumns: ColumnsType<KnowledgeItem> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "标题", dataIndex: "title", width: 300, render: (value) => shortText(value, 90) },
    { title: "分类", dataIndex: "category", width: 120 },
    { title: "答案", dataIndex: "answer", width: 420, render: (value) => shortText(value, 100) },
    { title: "状态", dataIndex: "status", width: 120, render: (value) => <StatusTag value={value} /> },
    { title: "质量", dataIndex: "quality_status", width: 120, render: (value) => <StatusTag value={value} /> },
    { title: "质量分", dataIndex: "quality_score", width: 90, render: (value) => value ?? 80 },
    { title: "复审日期", dataIndex: "review_due_at", width: 160, render: (value) => value ? formatTime(value) : "-" },
    {
      title: "来源缺口",
      dataIndex: "source_gap_id",
      width: 120,
      render: (value) => value ? `Gap#${value}` : "-"
    },
    { title: "创建时间", dataIndex: "created_at", width: 160, render: formatTime },
    {
      title: "操作",
      width: 420,
      fixed: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => setActiveDetail({ type: "item", data: row })}>
            详情
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openItemEditor(row)}>
            编辑
          </Button>
          <Button size="small" onClick={() => setWorkflowDetail({ type: "knowledge_item", id: row.id })}>
            处理
          </Button>
          <Button size="small" icon={<SendOutlined />} disabled={row.status !== "draft"} onClick={() => updateItemStatus(row.id, "pending_review")}>
            提审
          </Button>
          <Button size="small" icon={<CheckCircleOutlined />} disabled={row.status !== "pending_review"} onClick={() => updateItemStatus(row.id, "published")}>
            发布
          </Button>
          <Button size="small" icon={<FileDoneOutlined />} disabled={row.status === "archived"} onClick={() => updateItemStatus(row.id, "archived")}>
            归档
          </Button>
          <Button size="small" onClick={() => markItemReviewed(row)}>
            已复审
          </Button>
        </Space>
      )
    }
  ];

  return (
    <>
      <PageHeader
        title="知识沉淀"
        extra={
          <Space>
            <Typography.Text type="secondary">
              缺口 {gaps.data?.total ?? 0} / 条目 {items.data?.total ?? 0}
            </Typography.Text>
            <ReloadButton loading={gaps.loading || items.loading} onReload={() => {
              void gaps.reload();
              void items.reload();
              void graph.reload();
              void quality.reload();
            }} />
          </Space>
        }
      />
      <ApiErrorAlert error={gaps.error ?? items.error ?? graph.error ?? quality.error} />
      <Card>
        <Tabs
          tabBarExtraContent={
            <Space wrap>
              <Select
                allowClear
                placeholder="分类"
                style={{ width: 150 }}
                value={category}
                options={categoryOptions}
                onChange={setCategory}
              />
              <Input.Search allowClear placeholder="搜索问题/答案/标题/分类" value={search} onChange={(event) => setSearch(event.target.value)} style={{ width: 280 }} />
            </Space>
          }
          items={[
            {
              key: "gaps",
              label: "KnowledgeGap",
              children: (
                <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                  <Select
                    allowClear
                    placeholder="缺口状态"
                    style={{ width: 160 }}
                    value={gapStatus}
                    options={[
                      { label: "待处理", value: "pending" },
                      { label: "已采纳", value: "accepted" },
                      { label: "已忽略", value: "ignored" }
                    ]}
                    onChange={setGapStatus}
                  />
                  <Typography.Paragraph type="secondary" className="table-ux-hint">
                    表格可横向滚动；按住表头右侧边缘可调整列宽。
                  </Typography.Paragraph>
                  <ResizableTable
                    size="small"
                    loading={gaps.loading}
                    rowKey="id"
                    rowClassName={(row) => isTargetId(row.id, targetId) ? "row-highlight" : ""}
                    dataSource={gapRows}
                    columns={gapColumns}
                    scroll={{ x: 1500 }}
                    pagination={{ pageSize: 10, total: gapRows.length }}
                  />
                </Space>
              )
            },
            {
              key: "items",
              label: "KnowledgeItem",
              children: (
                <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                  <Select
                    allowClear
                    placeholder="条目状态"
                    style={{ width: 160 }}
                    value={itemStatus}
                    options={[
                      { label: "草稿", value: "draft" },
                      { label: "待审核", value: "pending_review" },
                      { label: "已发布", value: "published" },
                      { label: "已归档", value: "archived" }
                    ]}
                    onChange={setItemStatus}
                  />
                  <Typography.Paragraph type="secondary" className="table-ux-hint">
                    表格可横向滚动；按住表头右侧边缘可调整列宽。
                  </Typography.Paragraph>
                  <ResizableTable
                    size="small"
                    loading={items.loading}
                    rowKey="id"
                    rowClassName={(row) => isTargetId(row.id, targetId) ? "row-highlight" : ""}
                    dataSource={itemRows}
                    columns={itemColumns}
                    scroll={{ x: 1950 }}
                    pagination={{ pageSize: 10, total: itemRows.length }}
                  />
                </Space>
              )
            },
            {
              key: "quality",
              label: "质量治理",
              children: (
                <KnowledgeQualityPanel
                  data={quality.data}
                  loading={quality.loading}
                  onOpenItem={(item) => setActiveDetail({ type: "item", data: item })}
                  onMarkReviewed={markItemReviewed}
                  onArchive={(item) => updateItemStatus(item.id, "archived")}
                  onReload={() => quality.reload()}
                />
              )
            },
            {
              key: "retrieval",
              label: "RAG 检索",
              children: (
                <KnowledgeSearchPanel
                  query={retrievalQuery}
                  result={retrievalResult}
                  loading={retrievalLoading}
                  category={category}
                  onQueryChange={setRetrievalQuery}
                  onSearch={runKnowledgeSearch}
                  onOpenItem={(item) => setActiveDetail({ type: "item", data: item })}
                  onFeedback={submitRetrievalFeedback}
                  onRebuildIndex={rebuildKnowledgeIndex}
                />
              )
            },
            {
              key: "graph",
              label: "知识图谱",
              children: (
                <KnowledgeGraph
                  graph={graph.data}
                  loading={graph.loading}
                  onNodeClick={openGraphNode}
                  onReload={() => graph.reload()}
                  onExport={openObsidianExport}
                />
              )
            }
          ]}
        />
      </Card>
      <Modal
        title={editingItem ? `编辑知识条目 #${editingItem.id}` : "编辑知识条目"}
        open={Boolean(editingItem)}
        onCancel={() => setEditingItem(undefined)}
        onOk={saveItemEdit}
        okText="保存"
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, message: "请输入标题" }]}>
            <Input maxLength={240} />
          </Form.Item>
          <Form.Item name="answer" label="答案" rules={[{ required: true, message: "请输入答案" }]}>
            <Input.TextArea rows={5} />
          </Form.Item>
          <Form.Item name="category" label="分类" rules={[{ required: true, message: "请输入分类" }]}>
            <Input maxLength={80} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={knowledgeItemStatusOptions} />
          </Form.Item>
          <Form.Item name="review_due_at" label="复审日期">
            <Input placeholder="例如 2026-09-03T00:00:00+08:00" />
          </Form.Item>
          <Form.Item name="quality_status" label="质量状态">
            <Select options={knowledgeQualityStatusOptions} />
          </Form.Item>
          <Form.Item name="quality_score" label="质量分">
            <InputNumber min={0} max={100} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="change_summary" label="变更说明" rules={[{ required: true, message: "请填写变更说明" }]}>
            <Input.TextArea rows={2} maxLength={500} />
          </Form.Item>
        </Form>
      </Modal>
      <KnowledgeDetailDrawer
        detail={activeDetail}
        onClose={() => setActiveDetail(undefined)}
        onChanged={async () => {
          await items.reload();
          await graph.reload();
          await quality.reload();
        }}
      />
      <Modal
        title="Obsidian Markdown 导出草案"
        open={Boolean(obsidianExport)}
        onCancel={() => setObsidianExport(undefined)}
        footer={<Button onClick={() => setObsidianExport(undefined)}>关闭</Button>}
        width={760}
      >
        <Typography.Paragraph type="secondary">
          共 {obsidianExport?.file_count ?? 0} 个 Markdown 草案文件。
        </Typography.Paragraph>
        <List
          size="small"
          dataSource={obsidianExport?.files ?? []}
          renderItem={(file) => (
            <List.Item>
              <List.Item.Meta title={file.path} description={<pre className="json-block">{file.content.slice(0, 1200)}</pre>} />
            </List.Item>
          )}
        />
      </Modal>
      <BusinessObjectDetailDrawer
        objectType={workflowDetail?.type}
        objectId={workflowDetail?.id}
        open={Boolean(workflowDetail)}
        onClose={() => setWorkflowDetail(undefined)}
        onChanged={async () => {
          await gaps.reload();
          await items.reload();
          await graph.reload();
          await quality.reload();
        }}
      />
    </>
  );
}

type KnowledgeDetail =
  | { type: "gap"; data: KnowledgeGap }
  | { type: "item"; data: KnowledgeItem };

function KnowledgeSearchPanel({
  query,
  result,
  loading,
  category,
  onQueryChange,
  onSearch,
  onOpenItem,
  onFeedback,
  onRebuildIndex
}: {
  query: string;
  result?: KnowledgeSearchResponse;
  loading: boolean;
  category?: string;
  onQueryChange: (value: string) => void;
  onSearch: (query?: string) => void;
  onOpenItem: (item: KnowledgeItem) => void;
  onFeedback: (hitId: string | number, status: "useful" | "not_useful") => void;
  onRebuildIndex: () => void;
}) {
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Space wrap>
        <Input.Search
          allowClear
          placeholder="输入客户问题、关键词或错误描述"
          value={query}
          loading={loading}
          style={{ width: 420 }}
          onChange={(event) => onQueryChange(event.target.value)}
          onSearch={(value) => onSearch(value)}
        />
        <Button loading={loading} onClick={() => onSearch(query)}>检索并记录命中</Button>
        <Button onClick={onRebuildIndex}>重建索引</Button>
        <Typography.Text type="secondary">
          {category ? `当前分类：${category}` : "全部分类"} / 候选 {result?.total_candidates ?? 0}
        </Typography.Text>
      </Space>
      <List
        size="small"
        dataSource={result?.matches ?? []}
        locale={{ emptyText: result ? "未命中知识。" : "输入问题后查看检索结果。" }}
        renderItem={(match) => (
          <List.Item actions={[
            <Button key="detail" size="small" onClick={() => onOpenItem(match.item)}>详情</Button>,
            <Button
              key="useful"
              size="small"
              disabled={!match.recorded_hit_id}
              onClick={() => match.recorded_hit_id && onFeedback(match.recorded_hit_id, "useful")}
            >
              有帮助
            </Button>,
            <Button
              key="not-useful"
              size="small"
              danger
              disabled={!match.recorded_hit_id}
              onClick={() => match.recorded_hit_id && onFeedback(match.recorded_hit_id, "not_useful")}
            >
              无帮助
            </Button>
          ]}>
            <List.Item.Meta
              title={
                <Space wrap>
                  <span>{`KnowledgeItem#${match.item.id} ${match.item.title ?? ""}`}</span>
                  <StatusTag value={match.item.status} />
                  <Typography.Text type="secondary">
                    {`${match.citation ?? ""} 综合 ${match.score} / 关键词 ${match.keyword_score ?? 0} / 语义 ${Math.round((match.semantic_score ?? 0) * 100)}`}
                  </Typography.Text>
                </Space>
              }
              description={
                <Space direction="vertical" size={2}>
                  <Typography.Text>{match.snippet || match.item.answer || "-"}</Typography.Text>
                  <Typography.Text type="secondary">
                    分类 {match.item.category ?? "general"} / 命中原因 {(match.reasons ?? []).join(", ") || "-"} / hit#{match.recorded_hit_id ?? "-"}
                  </Typography.Text>
                </Space>
              }
            />
          </List.Item>
        )}
      />
    </Space>
  );
}

function KnowledgeQualityPanel({
  data,
  loading,
  onOpenItem,
  onMarkReviewed,
  onArchive,
  onReload
}: {
  data?: KnowledgeQualityDashboard;
  loading: boolean;
  onOpenItem: (item: KnowledgeItem) => void;
  onMarkReviewed: (item: KnowledgeItem) => void;
  onArchive: (item: KnowledgeItem) => void;
  onReload: () => void;
}) {
  const summary = data?.summary;
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Space wrap>
        <Button loading={loading} onClick={onReload}>刷新质量面板</Button>
        <Typography.Text type="secondary">
          条目 {summary?.total_items ?? 0} / 已发布 {summary?.published_items ?? 0} / 平均质量分 {summary?.average_quality_score ?? 0}
        </Typography.Text>
      </Space>
      <Descriptions size="small" column={4} bordered>
        <Descriptions.Item label="过期">{summary?.expired_items ?? 0}</Descriptions.Item>
        <Descriptions.Item label="即将复审">{summary?.review_due_soon ?? 0}</Descriptions.Item>
        <Descriptions.Item label="待优化">{summary?.optimization_candidates ?? 0}</Descriptions.Item>
        <Descriptions.Item label="建议归档">{summary?.archive_suggestions ?? 0}</Descriptions.Item>
        <Descriptions.Item label="待处理缺口">{summary?.pending_gaps ?? 0}</Descriptions.Item>
        <Descriptions.Item label="重复缺口">{summary?.repeated_gaps ?? 0}</Descriptions.Item>
      </Descriptions>
      <QualityList
        title="过期知识"
        rows={data?.expired_items ?? []}
        empty="暂无过期知识。"
        onOpenItem={onOpenItem}
        onMarkReviewed={onMarkReviewed}
        onArchive={onArchive}
      />
      <QualityList
        title="待优化知识"
        rows={data?.optimization_candidates ?? []}
        empty="暂无待优化知识。"
        onOpenItem={onOpenItem}
        onMarkReviewed={onMarkReviewed}
        onArchive={onArchive}
      />
      <QualityList
        title="归档建议"
        rows={data?.archive_suggestions ?? []}
        empty="暂无归档建议。"
        onOpenItem={onOpenItem}
        onMarkReviewed={onMarkReviewed}
        onArchive={onArchive}
      />
      <QualityList
        title="即将复审"
        rows={data?.review_due_soon ?? []}
        empty="暂无即将复审的知识。"
        onOpenItem={onOpenItem}
        onMarkReviewed={onMarkReviewed}
        onArchive={onArchive}
      />
      <Typography.Title level={5}>缺口质量</Typography.Title>
      <List
        size="small"
        dataSource={data?.gap_quality?.repeated_gaps ?? []}
        locale={{ emptyText: "暂无重复知识缺口。" }}
        renderItem={(gap) => (
          <List.Item actions={[gap.source_message_id ? <a key="message" href={hashTarget("messages", gap.source_message_id)}>来源消息</a> : null]}>
            <List.Item.Meta
              title={`KnowledgeGap#${gap.id} / ${gap.category ?? "general"} / 出现 ${gap.occurrence_count ?? 1} 次`}
              description={shortText(gap.question || "-", 160)}
            />
          </List.Item>
        )}
      />
      {data?.rules ? (
        <Typography.Paragraph type="secondary" className="table-ux-hint">
          规则：{Object.values(data.rules).join(" ")}
        </Typography.Paragraph>
      ) : null}
    </Space>
  );
}

function QualityList({
  title,
  rows,
  empty,
  onOpenItem,
  onMarkReviewed,
  onArchive
}: {
  title: string;
  rows: KnowledgeQualityItem[];
  empty: string;
  onOpenItem: (item: KnowledgeItem) => void;
  onMarkReviewed: (item: KnowledgeItem) => void;
  onArchive: (item: KnowledgeItem) => void;
}) {
  return (
    <>
      <Typography.Title level={5}>{title}</Typography.Title>
      <List
        size="small"
        dataSource={rows}
        locale={{ emptyText: empty }}
        renderItem={(row) => (
          <List.Item
            actions={[
              <Button key="detail" size="small" onClick={() => onOpenItem(row.item)}>详情</Button>,
              <Button key="review" size="small" onClick={() => onMarkReviewed(row.item)}>已复审</Button>,
              <Button key="archive" size="small" disabled={row.item.status === "archived"} onClick={() => onArchive(row.item)}>归档</Button>
            ]}
          >
            <List.Item.Meta
              title={
                <Space wrap>
                  <span>{`KnowledgeItem#${row.item.id} ${row.item.title ?? ""}`}</span>
                  <StatusTag value={row.computed_quality_status ?? row.item.quality_status} />
                </Space>
              }
              description={
                <Space direction="vertical" size={2}>
                  <Typography.Text>{row.reason ?? "-"}</Typography.Text>
                  <Typography.Text type="secondary">
                    命中 {row.hit_count ?? 0} / 平均分 {row.average_hit_score ?? 0} / 质量分 {row.item.quality_score ?? 80} / 复审 {row.item.review_due_at ? formatTime(row.item.review_due_at) : "-"}
                  </Typography.Text>
                </Space>
              }
            />
          </List.Item>
        )}
      />
    </>
  );
}

function KnowledgeGraph({
  graph,
  loading,
  onNodeClick,
  onReload,
  onExport
}: {
  graph?: KnowledgeGraphResponse;
  loading: boolean;
  onNodeClick: (node: KnowledgeGraphNode) => void;
  onReload: () => void;
  onExport: () => void;
}) {
  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];
  const positions = useMemo(() => graphLayout(nodes), [nodes]);
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Space wrap>
        <Button icon={<BranchesOutlined />} loading={loading} onClick={onReload}>
          刷新图谱
        </Button>
        <Button icon={<FileDoneOutlined />} onClick={onExport}>导出 Obsidian 草案</Button>
        <Typography.Text type="secondary">
          节点 {graph?.summary?.node_count ?? nodes.length} / 关系 {graph?.summary?.edge_count ?? edges.length} / 命中 {graph?.summary?.hits ?? 0}
        </Typography.Text>
      </Space>
      <div className="knowledge-graph-shell">
        {nodes.length ? (
          <svg className="knowledge-graph-svg" viewBox="0 0 1040 620" role="img" aria-label="知识图谱">
            <g>
              {edges.map((edge) => {
                const source = positions.get(edge.source);
                const target = positions.get(edge.target);
                if (!source || !target) return null;
                return (
                  <line
                    key={edge.id}
                    x1={source.x}
                    y1={source.y}
                    x2={target.x}
                    y2={target.y}
                    className={`knowledge-graph-edge edge-${edge.type}`}
                  />
                );
              })}
            </g>
            <g>
              {nodes.map((node) => {
                const point = positions.get(node.id) ?? { x: 520, y: 310 };
                const radius = nodeRadius(node.kind);
                return (
                  <g
                    key={node.id}
                    className="knowledge-graph-node"
                    transform={`translate(${point.x}, ${point.y})`}
                    onClick={() => onNodeClick(node)}
                  >
                    <title>{`${node.kind} / ${node.label}${node.summary ? ` / ${node.summary}` : ""}`}</title>
                    <circle r={radius} fill={nodeColor(node.kind)} />
                    <text y={radius + 13} textAnchor="middle">
                      {shortText(node.label, node.kind === "Category" ? 18 : 24)}
                    </text>
                    {node.score !== undefined ? (
                      <text y={4} textAnchor="middle" className="knowledge-graph-score">
                        {node.score}
                      </text>
                    ) : null}
                  </g>
                );
              })}
            </g>
          </svg>
        ) : (
          <div className="knowledge-graph-empty">
            <Typography.Text type="secondary">{loading ? "图谱加载中" : "暂无可展示的知识关系"}</Typography.Text>
          </div>
        )}
      </div>
    </Space>
  );
}

function graphLayout(nodes: KnowledgeGraphNode[]) {
  const width = 1040;
  const height = 620;
  const center = { x: width / 2, y: height / 2 };
  const groups: Record<string, KnowledgeGraphNode[]> = {
    Category: [],
    KnowledgeItem: [],
    KnowledgeGap: [],
    outer: []
  };
  nodes.forEach((node) => {
    if (node.kind === "Category") groups.Category.push(node);
    else if (node.kind === "KnowledgeItem") groups.KnowledgeItem.push(node);
    else if (node.kind === "KnowledgeGap") groups.KnowledgeGap.push(node);
    else groups.outer.push(node);
  });
  const positions = new Map<string, { x: number; y: number }>();
  placeRing(groups.Category, 76, -0.2, positions, center);
  placeRing(groups.KnowledgeItem, 190, 0.12, positions, center);
  placeRing(groups.KnowledgeGap, 260, 0.36, positions, center);
  placeRing(groups.outer, 314, -0.48, positions, center);
  return positions;
}

function placeRing(
  nodes: KnowledgeGraphNode[],
  radius: number,
  offset: number,
  positions: Map<string, { x: number; y: number }>,
  center: { x: number; y: number }
) {
  if (!nodes.length) return;
  nodes.forEach((node, index) => {
    const angle = offset + (Math.PI * 2 * index) / nodes.length;
    positions.set(node.id, {
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius
    });
  });
}

function nodeColor(kind: string) {
  if (kind === "KnowledgeItem") return "#3b82f6";
  if (kind === "KnowledgeGap") return "#f59e0b";
  if (kind === "SourceMessage") return "#14b8a6";
  if (kind === "Ticket") return "#ef4444";
  if (kind === "AgentRun") return "#8b5cf6";
  if (kind === "Category") return "#111827";
  if (kind === "Hit") return "#10b981";
  return "#64748b";
}

function nodeRadius(kind: string) {
  if (kind === "Category") return 18;
  if (kind === "KnowledgeItem" || kind === "KnowledgeGap") return 15;
  return 11;
}

function KnowledgeDetailDrawer({
  detail,
  onClose,
  onChanged
}: {
  detail?: KnowledgeDetail;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const open = Boolean(detail);
  const title = detail?.type === "gap" ? `知识缺口 #${detail.data.id}` : `知识条目 #${detail?.data.id ?? ""}`;
  const loadDetail = useCallback(async () => {
    if (!detail) return undefined;
    if (detail.type === "gap") return api.getKnowledgeGapDetail(detail.data.id);
    return api.getKnowledgeItemDetail(detail.data.id);
  }, [detail]);
  const detailData = useAsyncData(loadDetail);
  return (
    <Drawer title={title} open={open} onClose={onClose} width={720}>
      <ApiErrorAlert error={detailData.error} />
      {detail?.type === "gap" ? (
        <KnowledgeGapDetail gap={detail.data} detail={detailData.data as KnowledgeGapDetailPayload | undefined} />
      ) : null}
      {detail?.type === "item" ? (
        <KnowledgeItemDetail
          item={(detailData.data as KnowledgeItemDetailPayload | undefined)?.item ?? detail.data}
          detail={detailData.data as KnowledgeItemDetailPayload | undefined}
          onChanged={async () => {
            await detailData.reload();
            await onChanged();
          }}
        />
      ) : null}
    </Drawer>
  );
}

function KnowledgeGapDetail({ gap, detail }: { gap: KnowledgeGap; detail?: KnowledgeGapDetailPayload }) {
  const sourceReferences = detail?.source_references ?? [];
  const timeline = detail?.timeline ?? [];
  return (
    <>
      <Descriptions size="small" column={2}>
        <Descriptions.Item label="分类">{gap.category ?? "general"}</Descriptions.Item>
        <Descriptions.Item label="状态"><StatusTag value={gap.status} /></Descriptions.Item>
        <Descriptions.Item label="出现次数">{gap.occurrence_count ?? 1}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{formatTime(gap.created_at)}</Descriptions.Item>
        <Descriptions.Item label="更新时间">{formatTime(gap.updated_at)}</Descriptions.Item>
        <Descriptions.Item label="来源">{sourceLinks(gap.source_message_id, gap.agent_run_id)}</Descriptions.Item>
      </Descriptions>
      <DetailSection title="问题">{gap.question || "-"}</DetailSection>
      <DetailSection title="建议答案">{gap.suggested_answer || "待补充"}</DetailSection>
      <ReferenceList references={sourceReferences} />
      <TimelineList events={timeline} />
      <Typography.Title level={5}>关联知识条目</Typography.Title>
      {detail?.related_items?.length ? (
        <List
          size="small"
          dataSource={detail.related_items}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta title={`KnowledgeItem#${item.id} ${item.title ?? ""}`} description={`${item.status ?? "-"} / ${item.category ?? "general"}`} />
            </List.Item>
          )}
        />
      ) : (
        <Typography.Text type="secondary">暂无关联知识条目。</Typography.Text>
      )}
      <Typography.Title level={5}>引用示例</Typography.Title>
      {gap.examples_json?.length ? (
        <List
          size="small"
          dataSource={gap.examples_json}
          renderItem={(example, index) => (
            <List.Item>
              <List.Item.Meta title={`示例 ${index + 1}`} description={<pre className="json-block">{JSON.stringify(example, null, 2)}</pre>} />
            </List.Item>
          )}
        />
      ) : (
        <Typography.Text type="secondary">暂无示例。</Typography.Text>
      )}
    </>
  );
}

function KnowledgeItemDetail({
  item,
  detail,
  onChanged
}: {
  item: KnowledgeItem;
  detail?: KnowledgeItemDetailPayload;
  onChanged: () => Promise<void>;
}) {
  const { message, modal } = AntdApp.useApp();
  const sourceReferences = detail?.source_references ?? [];
  const versions = detail?.versions ?? [];
  const hits = detail?.hits ?? [];
  const hitSummary = detail?.hit_summary;
  const timeline = detail?.timeline ?? [];
  const submitFeedback = async (hitId: string | number, status: "useful" | "not_useful") => {
    try {
      await api.updateKnowledgeHitFeedback(hitId, status);
      message.success(status === "useful" ? "已记录为有帮助" : "已记录为无帮助并进入复审");
      await onChanged();
    } catch (caught) {
      message.error(caught instanceof Error ? caught.message : "反馈提交失败");
    }
  };
  const rollbackVersion = (versionId: string | number, versionNo?: number) => {
    modal.confirm({
      title: `回滚到 v${versionNo ?? "-"}`,
      content: "当前内容会保留在版本历史中，回滚动作也会写入审计记录。",
      okText: "确认回滚",
      cancelText: "取消",
      onOk: async () => {
        await api.rollbackKnowledgeVersion(item.id, versionId, `人工回滚至知识版本 v${versionNo ?? "-"}`);
        message.success("知识版本已回滚");
        await onChanged();
      }
    });
  };
  return (
    <>
      <Descriptions size="small" column={2}>
        <Descriptions.Item label="分类">{item.category ?? "general"}</Descriptions.Item>
        <Descriptions.Item label="状态"><StatusTag value={item.status} /></Descriptions.Item>
        <Descriptions.Item label="质量状态"><StatusTag value={item.quality_status ?? "healthy"} /></Descriptions.Item>
        <Descriptions.Item label="质量分">{item.quality_score ?? 80}</Descriptions.Item>
        <Descriptions.Item label="复审日期">{item.review_due_at ? formatTime(item.review_due_at) : "-"}</Descriptions.Item>
        <Descriptions.Item label="最近复审">{item.last_reviewed_at ? formatTime(item.last_reviewed_at) : "-"}</Descriptions.Item>
        <Descriptions.Item label="来源缺口">{item.source_gap_id ? `KnowledgeGap#${item.source_gap_id}` : "-"}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{formatTime(item.created_at)}</Descriptions.Item>
        <Descriptions.Item label="更新时间">{formatTime(item.updated_at)}</Descriptions.Item>
      </Descriptions>
      <DetailSection title="标题">{item.title || "-"}</DetailSection>
      <DetailSection title="答案">{item.answer || "-"}</DetailSection>
      <ReferenceList references={sourceReferences} />
      <Typography.Title level={5}>命中记录</Typography.Title>
      <Descriptions size="small" column={3}>
        <Descriptions.Item label="总命中">{hitSummary?.total ?? 0}</Descriptions.Item>
        <Descriptions.Item label="平均分">{hitSummary?.average_score ?? 0}</Descriptions.Item>
        <Descriptions.Item label="最近命中">{hitSummary?.latest_at ? formatTime(hitSummary.latest_at) : "-"}</Descriptions.Item>
      </Descriptions>
      {hits.length ? (
        <List
          size="small"
          dataSource={hits}
          renderItem={(hit) => (
            <List.Item actions={hit.id ? [
              <Button key="useful" size="small" disabled={hit.status === "useful"} onClick={() => submitFeedback(hit.id!, "useful")}>有帮助</Button>,
              <Button key="not-useful" size="small" danger disabled={hit.status === "not_useful"} onClick={() => submitFeedback(hit.id!, "not_useful")}>无帮助</Button>
            ] : undefined}>
              <List.Item.Meta
                title={`${hit.source_object_type ?? "source"}#${hit.source_object_id ?? "-"} / score=${hit.score ?? 0} / ${hit.status ?? "retrieved"} / ${formatTime(hit.created_at)}`}
                description={
                  <Space direction="vertical" size={2}>
                    <Typography.Text>{shortText(hit.query_text || "-", 140)}</Typography.Text>
                    <Typography.Text type="secondary">{shortText(hit.answer_snapshot || "-", 160)}</Typography.Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      ) : (
        <Typography.Text type="secondary">暂无命中记录。</Typography.Text>
      )}
      <Typography.Title level={5}>版本历史</Typography.Title>
      {versions.length ? (
        <List
          size="small"
          dataSource={versions}
          renderItem={(version) => (
            <List.Item actions={version.id ? [
              <Button key="rollback" size="small" onClick={() => rollbackVersion(version.id!, version.version_no)}>回滚</Button>
            ] : undefined}>
              <List.Item.Meta
                title={`v${version.version_no ?? "-"} / ${version.status ?? "-"} / ${version.change_type ?? "snapshot"}`}
                description={
                  <Space direction="vertical" size={2}>
                    <Typography.Text>{version.change_summary || version.title || "-"}</Typography.Text>
                    <Typography.Text type="secondary">{formatTime(version.created_at)}</Typography.Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      ) : (
        <Typography.Text type="secondary">暂无版本快照。</Typography.Text>
      )}
      <TimelineList events={timeline} />
    </>
  );
}

function ReferenceList({ references }: { references: NonNullable<KnowledgeGapDetailPayload["source_references"]> }) {
  return (
    <>
      <Typography.Title level={5}>来源引用</Typography.Title>
      {references.length ? (
        <List
          size="small"
          dataSource={references}
          renderItem={(reference) => (
            <List.Item>
              <List.Item.Meta
                title={`${reference.label ?? reference.type ?? "来源"}${reference.created_at ? ` / ${formatTime(reference.created_at)}` : ""}`}
                description={reference.summary || "-"}
              />
            </List.Item>
          )}
        />
      ) : (
        <Typography.Text type="secondary">暂无来源引用。</Typography.Text>
      )}
    </>
  );
}

function TimelineList({ events }: { events: NonNullable<KnowledgeGapDetailPayload["timeline"]> }) {
  return (
    <>
      <Typography.Title level={5}>时间线</Typography.Title>
      {events.length ? (
        <List
          size="small"
          dataSource={events}
          renderItem={(event) => (
            <List.Item>
              <List.Item.Meta title={`${event.title ?? event.type ?? "事件"} / ${formatTime(event.created_at)}`} description={event.description || "-"} />
            </List.Item>
          )}
        />
      ) : (
        <Typography.Text type="secondary">暂无时间线。</Typography.Text>
      )}
    </>
  );
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <Typography.Title level={5}>{title}</Typography.Title>
      <Typography.Paragraph className="detail-text">{children}</Typography.Paragraph>
    </>
  );
}

function statusSummary(status: string) {
  if (status === "pending_review") return "提交知识条目进入审核";
  if (status === "published") return "审核通过并发布知识条目";
  if (status === "archived") return "归档知识条目";
  if (status === "draft") return "退回草稿继续编辑";
  return "更新知识条目状态";
}

function normalizeKnowledgeItemFormValues(values: Record<string, unknown>) {
  return {
    ...values,
    review_due_at: typeof values.review_due_at === "string" && values.review_due_at.trim() ? values.review_due_at.trim() : undefined,
    quality_score: typeof values.quality_score === "number" ? values.quality_score : Number(values.quality_score ?? 80)
  };
}

function futureDateIso(days: number) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString();
}

function graphNodeToItem(node: KnowledgeGraphNode): KnowledgeItem {
  return {
    id: node.object_id ?? node.id,
    title: node.label,
    answer: node.summary ?? "",
    category: node.category,
    status: node.status,
    created_at: node.created_at,
    updated_at: node.created_at
  };
}

function graphNodeToGap(node: KnowledgeGraphNode): KnowledgeGap {
  return {
    id: node.object_id ?? node.id,
    question: node.label,
    suggested_answer: node.summary ?? "",
    category: node.category,
    status: node.status,
    created_at: node.created_at,
    updated_at: node.created_at
  };
}

function graphNodeTarget(node: KnowledgeGraphNode) {
  if (!node.object_id) return "";
  if (node.object_type === "message") return hashTarget("messages", node.object_id);
  if (node.object_type === "ticket") return hashTarget("tickets", node.object_id);
  if (node.object_type === "agent_run") return hashTarget("agent-runs", node.object_id);
  return "";
}

function sourceLinks(sourceMessageId?: KnowledgeGap["source_message_id"], agentRunId?: KnowledgeGap["agent_run_id"]) {
  const links: ReactNode[] = [];
  if (sourceMessageId) links.push(<a key="message" href={hashTarget("messages", sourceMessageId)}>消息#{sourceMessageId}</a>);
  if (agentRunId) links.push(<a key="run" href={hashTarget("agent-runs", agentRunId)}>运行#{agentRunId}</a>);
  return links.length ? <Space>{links}</Space> : "-";
}
