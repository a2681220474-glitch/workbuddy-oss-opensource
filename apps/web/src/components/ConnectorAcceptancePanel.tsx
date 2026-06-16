import { Alert, Card, Space, Tag, Typography } from "antd";
import type { ConnectorSafeAcceptance } from "../types";


export function ConnectorAcceptancePanel({ data }: { data?: ConnectorSafeAcceptance }) {
  return (
    <Card title="发布前安全复验" className="dashboard-lower">
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={data?.safe_verified ? "green" : "gold"}>
            自动安全复验{data?.safe_verified ? "已通过" : "待完成"}
          </Tag>
          <Tag color="blue">自动真实外发：禁止</Tag>
          <Tag color={data?.real_send_evidence ? "green" : "default"}>
            真实外发证据：{data?.real_send_evidence ? "已有" : "待人工"}
          </Tag>
        </Space>
        {(data?.checks ?? []).map((item) => (
          <Alert
            key={item.key}
            showIcon
            type={item.ok ? "success" : "warning"}
            message={item.label}
            description={item.message}
          />
        ))}
        <Typography.Text type="secondary">
          {data?.next_action ?? "安全复验只允许接收、诊断、Mock 发送和重试检查，不会自动触发真实外发。"}
        </Typography.Text>
      </Space>
    </Card>
  );
}
