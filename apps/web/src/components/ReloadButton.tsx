import { ReloadOutlined } from "@ant-design/icons";
import { Button } from "antd";

interface ReloadButtonProps {
  loading?: boolean;
  onReload: () => void;
}

export function ReloadButton({ loading, onReload }: ReloadButtonProps) {
  return (
    <Button icon={<ReloadOutlined />} loading={loading} onClick={onReload}>
      刷新
    </Button>
  );
}
