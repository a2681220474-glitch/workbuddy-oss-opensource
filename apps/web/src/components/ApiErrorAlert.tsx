import { Alert } from "antd";
import { API_BASE_URL } from "../api/client";

interface ApiErrorAlertProps {
  error?: Error;
}

export function ApiErrorAlert({ error }: ApiErrorAlertProps) {
  if (!error) return null;

  return (
    <Alert
      className="api-alert"
      type="warning"
      showIcon
      message="后端接口暂不可用"
      description={`${API_BASE_URL} 返回异常：${error.message}`}
    />
  );
}
