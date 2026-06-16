# 企业微信 Debug Payload

v0.17.x 已支持真实企微回调骨架。下面这个 payload 仍然保留，用于本地快速造一条企微样本，验证业务链路、审批和时间线。

打开：

```text
http://localhost:5173/#adapter-test
```

选择 `企业微信`，粘贴：

```json
{
  "event_type": "mock.message.receive",
  "message_id": "wecom_mock_001",
  "user_id": "wm_preview_user",
  "sender_name": "企微客户",
  "chat_id": "wr_preview_group",
  "chat_name": "企微售后测试群",
  "chat_type": "group",
  "text": "客户想了解售后响应 SLA，能否安排客服跟进？"
}
```

预期标准化结果：

- `channel`: `wecom`
- `text`: 客户原始消息
- `sender_external_id`: `wm_preview_user`
- `conversation_id`: `wr_preview_group`
- `conversation_name`: `企微售后测试群`

点击“一键导入为 MessageEvent”会在本地写入 MessageEvent，并触发正常的 Agent Router / Approval 流水线。它不会发送任何真实企业微信消息。
