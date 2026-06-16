import React from "react";
import ReactDOM from "react-dom/client";
import { App as AntdApp, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#2563eb",
          borderRadius: 6,
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
        },
        components: {
          Layout: {
            siderBg: "#182230",
            headerBg: "#ffffff",
            bodyBg: "#f4f6f8"
          },
          Menu: {
            darkItemBg: "#182230",
            darkSubMenuItemBg: "#182230",
            darkItemSelectedBg: "#2563eb"
          },
          Card: {
            borderRadiusLG: 8
          }
        }
      }}
    >
      <AntdApp>
        <App />
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>
);
