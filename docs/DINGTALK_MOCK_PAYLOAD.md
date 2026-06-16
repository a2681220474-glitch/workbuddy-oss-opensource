# 钉钉 Mock Payload

v0.4.2 不接真实钉钉账号，只在 Adapter 测试台里验证未来标准化字段。

打开：

```text
http://localhost:5173/#adapter-test
```

选择 `钉钉`，粘贴：

```json
{
  "event_type": "mock.message.receive",
  "message_id": "ding_mock_001",
  "user_id": "ding_preview_user",
  "sender_name": "钉钉客户",
  "chat_id": "ding_preview_group",
  "chat_name": "钉钉销售测试群",
  "chat_type": "group",
  "text": "想预约演示并了解私有化部署价格。"
}
```

预期标准化结果：

- `channel`: `dingtalk`
- `text`: 客户原始消息
- `sender_external_id`: `ding_preview_user`
- `conversation_id`: `ding_preview_group`
- `conversation_name`: `钉钉销售测试群`

点击“一键导入为 MessageEvent”会在本地写入 MessageEvent，并触发正常的 Agent Router / Approval 流水线。它不会发送任何真实钉钉消息。
