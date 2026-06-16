import { Tag } from "antd";
import { statusColor } from "../utils/format";

interface StatusTagProps {
  value?: string;
}

export function StatusTag({ value }: StatusTagProps) {
  return <Tag color={statusColor(value)}>{statusLabel(value)}</Tag>;
}

function statusLabel(value?: string) {
  if (!value) return "-";
  const labels: Record<string, string> = {
    pending_review: "待审核",
    pending: "待处理",
    approved: "已通过",
    edited: "已编辑",
    rejected: "已拒绝",
    sent: "已发送",
    expired: "已过期",
    open: "待处理",
    in_progress: "处理中",
    waiting_customer: "等客户",
    closed: "已关闭",
    resolved: "已解决",
    success: "成功",
    completed: "已完成",
    failed: "失败",
    running: "运行中",
    stream_ready: "长连接就绪",
    configured: "已配置",
    skeleton: "骨架",
    ignored: "已忽略",
    received: "已接收",
    todo: "待跟进",
    done: "已完成",
    canceled: "已取消",
    low: "低",
    medium: "中",
    high: "高",
    critical: "严重",
    urgent: "紧急",
    normal: "普通",
    new: "新线索",
    potential: "潜在线索",
    contacted: "已联系",
    qualified: "已确认",
    proposal: "已发方案",
    negotiation: "谈判中",
    won: "已成交",
    lost: "已流失",
    screening: "筛选中",
    interview: "面试中",
    offer: "Offer",
    onboarding: "入职中",
    hired: "已入职",
    accepted: "已采纳",
    archived: "已归档",
    published: "已发布",
    draft: "草稿",
    healthy: "健康",
    needs_review: "待复审",
    needs_optimization: "待优化",
    archive_suggested: "建议归档"
  };
  return labels[value] ?? value;
}
