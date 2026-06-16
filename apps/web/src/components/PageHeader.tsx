import { Space, Typography } from "antd";
import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  extra?: ReactNode;
}

export function PageHeader({ title, extra }: PageHeaderProps) {
  return (
    <div className="page-header">
      <Typography.Title level={3}>{title}</Typography.Title>
      {extra ? <Space>{extra}</Space> : null}
    </div>
  );
}
