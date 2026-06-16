from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "1.1.16"
ADMIN_PASSWORD = "AcceptanceAdmin#2026"
APPROVER_PASSWORD = "AcceptanceApprover#2026"
HANDLER_PASSWORD = "AcceptanceHandler#2026"


def main() -> int:
    original_cwd = Path.cwd()
    checks: list[tuple[str, bool, str]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="workbuddy-product-acceptance-") as temp_dir:
            temp_root = Path(temp_dir)
            configure_isolated_runtime(temp_root)
            os.chdir(temp_root)
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))

            from fastapi.testclient import TestClient

            from apps.api.main import app
            from apps.api.shared.timezone import as_beijing

            with TestClient(app) as admin:
                health = expect_json(admin.get("/health"), 200, "health")
                record(checks, "health_version", health.get("version") == EXPECTED_VERSION, f"API reports {EXPECTED_VERSION}.")

                bootstrap_status = expect_json(admin.get("/api/auth/bootstrap-status"), 200, "bootstrap status")
                record(checks, "bootstrap_required", bootstrap_status.get("needs_bootstrap") is True, "Fresh database requires admin bootstrap.")

                bootstrap = expect_json(
                    admin.post(
                        "/api/auth/bootstrap",
                        json={
                            "username": "local_admin",
                            "display_name": "验收管理员",
                            "password": ADMIN_PASSWORD,
                        },
                    ),
                    200,
                    "bootstrap admin",
                )
                record(checks, "bootstrap_admin", bootstrap.get("user", {}).get("role") == "admin", "Admin bootstrap creates an authenticated admin.")

                me = expect_json(admin.get("/api/auth/me"), 200, "current user")
                record(checks, "session_cookie", me.get("username") == "local_admin", "Session cookie authenticates /api/auth/me.")

                with TestClient(app) as invalid_login:
                    invalid = invalid_login.post(
                        "/api/auth/login",
                        json={"username": "local_admin", "password": "wrong-password"},
                    )
                    record(checks, "invalid_login", invalid.status_code == 401, "Incorrect password is rejected.")

                approver = create_user(admin, "acceptance_approver", "验收审批人", "approver", APPROVER_PASSWORD)
                handler = create_user(admin, "acceptance_handler", "验收处理人", "handler", HANDLER_PASSWORD)
                users = expect_json(admin.get("/api/users"), 200, "list users")
                record(checks, "user_management", len(users) == 3, "Admin can create and list role-based users.")

                with authenticated_client(app, "acceptance_handler", HANDLER_PASSWORD) as handler_client:
                    forbidden = handler_client.post("/api/config/safe-demo-mode")
                    record(checks, "handler_rbac", forbidden.status_code == 403, "Handler cannot mutate administrator configuration.")

                secret_save = expect_json(
                    admin.patch(
                        "/api/config/runtime/llm",
                        json={
                            "provider": "mock",
                            "base_url": "",
                            "model": "workbuddy-acceptance",
                            "api_key": "temporary-acceptance-secret",
                            "timeout_seconds": 5,
                        },
                    ),
                    200,
                    "save encrypted runtime secret",
                )
                config_status = expect_json(admin.get("/api/config/status"), 200, "config status")
                secret_status = config_status.get("secret_storage") or {}
                record(checks, "secret_save_masked", secret_save.get("secrets_masked") is True, "Runtime secret response remains masked.")
                record(
                    checks,
                    "secret_storage_status",
                    secret_status.get("healthy") is True
                    and secret_status.get("encrypted_key_count") == 1
                    and secret_status.get("plaintext_key_count") == 0,
                    "Temporary runtime secret is encrypted with no plaintext residue.",
                )

                expect_json(
                    admin.patch(
                        "/api/config/runtime/policy",
                        json={
                            "enable_real_im_adapters": True,
                            "enable_external_send": True,
                        },
                    ),
                    200,
                    "save runtime policy",
                )
                expect_json(
                    admin.patch(
                        "/api/config/runtime/channels/feishu",
                        json={
                            "app_id": "cli_acceptance",
                            "app_secret": "temporary-feishu-secret",
                            "api_base_url": "https://open.feishu.cn",
                            "approval_chat_id": "oc_acceptance",
                        },
                    ),
                    200,
                    "save Feishu runtime configuration",
                )
                persisted_config = expect_json(admin.get("/api/config/status"), 200, "persisted config status")
                persisted_policy = persisted_config.get("global_policy") or {}
                persisted_feishu = next(
                    (item for item in persisted_config.get("channels") or [] if item.get("channel") == "feishu"),
                    {},
                )
                feishu_values = persisted_feishu.get("runtime_values") or {}
                record(
                    checks,
                    "runtime_policy_persistence",
                    persisted_policy.get("enable_real_im_adapters") is True
                    and persisted_policy.get("enable_external_send") is True,
                    "Saved runtime policy overrides false deployment defaults after settings reload.",
                )
                record(
                    checks,
                    "feishu_runtime_persistence",
                    persisted_feishu.get("configured") is True
                    and feishu_values.get("app_id") == "cli_acceptance"
                    and feishu_values.get("approval_chat_id") == "oc_acceptance"
                    and feishu_values.get("app_secret_configured") is True,
                    "Saved Feishu credentials and approval chat are visible after settings reload.",
                )

                knowledge_import = expect_json(
                    admin.post(
                        "/api/imports/knowledge/confirm",
                        json={
                            "source_type": "faq",
                            "filename": "acceptance-faq.md",
                            "content": (
                                "Q: 登录失败或系统无法使用时怎么处理？\n"
                                "A: 请先确认账号状态和网络连接，再记录报错时间与截图，由支持人员继续排查。"
                            ),
                            "default_category": "support",
                            "default_mode": "item",
                            "publish": True,
                        },
                    ),
                    200,
                    "knowledge import",
                )
                created_items = knowledge_import.get("created_items") or []
                record(
                    checks,
                    "knowledge_publish",
                    len(created_items) == 1 and created_items[0].get("status") == "published",
                    "Knowledge import creates one published item.",
                )

                search_result = expect_json(
                    admin.post(
                        "/api/knowledge/search",
                        json={
                            "query": "登录失败无法使用",
                            "limit": 5,
                            "record_hit": True,
                            "source_object_type": "acceptance",
                        },
                    ),
                    200,
                    "knowledge search",
                )
                record(checks, "knowledge_search", bool(search_result.get("matches")), "Published knowledge is searchable with a recorded hit.")

                message_import = expect_json(
                    admin.post(
                        "/api/imports/messages",
                        json={
                            "source_type": "json",
                            "filename": "acceptance-message.json",
                            "content": json.dumps(
                                [
                                    {
                                        "text": "登录失败，系统无法使用，已经影响工作，请尽快处理。",
                                        "sender_name": "验收客户",
                                        "sender_external_id": "acceptance-customer",
                                        "conversation_id": "acceptance-conversation",
                                        "conversation_name": "验收会话",
                                        "conversation_type": "p2p",
                                        "channel": "local_json",
                                        "external_message_id": "acceptance-message-001",
                                    }
                                ],
                                ensure_ascii=False,
                            ),
                        },
                    ),
                    200,
                    "message import",
                )
                record(
                    checks,
                    "message_routing",
                    message_import.get("message_count") == 1
                    and message_import.get("created_tickets") == 1
                    and message_import.get("created_approvals") == 1
                    and message_import.get("agent_runs") == 1,
                    "Message import creates one routed run, ticket, and approval.",
                )

                messages = expect_json(admin.get("/api/messages/enriched"), 200, "enriched messages")
                record(
                    checks,
                    "message_trace",
                    len(messages) == 1 and bool(messages[0].get("related_objects")),
                    "Enriched message exposes its generated business object.",
                )

                object_center = expect_json(admin.get("/api/business-objects"), 200, "business object center")
                ticket_count = (object_center.get("counts") or {}).get("tickets")
                recent_tickets = (object_center.get("recent") or {}).get("tickets") or []
                ticket_id = int(recent_tickets[0]["id"]) if recent_tickets else 0
                record(checks, "business_object_center", ticket_count == 1 and ticket_id > 0, "Business object center contains the generated ticket.")

                ticket_detail = expect_json(admin.get(f"/api/business-objects/ticket/{ticket_id}"), 200, "ticket detail")
                record(
                    checks,
                    "business_object_timeline",
                    bool(ticket_detail.get("source_message"))
                    and bool(ticket_detail.get("agent_run"))
                    and bool(ticket_detail.get("approvals"))
                    and len(ticket_detail.get("timeline") or []) >= 3,
                    "Ticket detail links source message, agent run, approval, and timeline.",
                )

                with authenticated_client(app, "acceptance_handler", HANDLER_PASSWORD) as handler_client:
                    processing = expect_json(
                        handler_client.post(
                            f"/api/business-objects/ticket/{ticket_id}/records",
                            json={
                                "action_type": "note",
                                "status": "in_progress",
                                "assignee_user_id": handler.get("id"),
                                "next_step": "继续排查登录失败原因",
                                "note": "v1.1.3 自动化验收处理记录",
                            },
                        ),
                        200,
                        "processing record",
                    )
                    record(
                        checks,
                        "handler_processing",
                        processing.get("operator_username") == "acceptance_handler",
                        "Handler can append an auditable processing record.",
                    )

                approvals = expect_json(admin.get("/api/approvals/enriched"), 200, "approvals")
                approval_id = int(approvals[0]["id"]) if approvals else 0
                record(
                    checks,
                    "beijing_time_serialization",
                    bool(approvals)
                    and str(approvals[0].get("created_at") or "").endswith("+08:00")
                    and as_beijing(
                        datetime.fromisoformat("2026-06-13T05:25:00"),
                        "postgresql+psycopg://workbuddy@example/workbuddy",
                    ).isoformat()
                    == "2026-06-13T13:25:00+08:00",
                    "API timestamps use explicit Beijing time, including naive PostgreSQL UTC values.",
                )
                approval_context = expect_json(admin.get(f"/api/approvals/{approval_id}/context"), 200, "approval context")
                record(
                    checks,
                    "approval_knowledge_reference",
                    approval_id > 0 and bool(approval_context.get("knowledge_references")),
                    "Approval context carries knowledge references from routing.",
                )

                with authenticated_client(app, "acceptance_approver", APPROVER_PASSWORD) as approver_client:
                    decision = expect_json(
                        approver_client.post(
                            f"/api/approvals/{approval_id}/decision",
                            json={"decision": "approved"},
                        ),
                        200,
                        "approval decision",
                    )
                    sent = expect_json(
                        approver_client.post(f"/api/approvals/{approval_id}/mock-send"),
                        200,
                        "approval mock send",
                    )
                    record(
                        checks,
                        "approval_flow",
                        decision.get("status") == "approved" and sent.get("status") == "sent",
                        "Approver can approve and complete a mock delivery.",
                    )

                audit_logs = expect_json(admin.get("/api/audit-logs?limit=100"), 200, "audit logs")
                audit_actions = {str(item.get("action_type")) for item in audit_logs}
                required_audits = {
                    "local_auth_bootstrapped",
                    "local_user_created",
                    "runtime_llm_updated",
                    "runtime_policy_updated",
                    "channel_runtime_updated",
                    "knowledge_import_confirmed",
                    "processing_record_created",
                    "approval_decided",
                    "approval_mock_sent",
                }
                record(
                    checks,
                    "audit_coverage",
                    required_audits.issubset(audit_actions),
                    "Critical authentication, configuration, knowledge, processing, and approval actions are audited.",
                )

                record(
                    checks,
                    "isolated_artifacts",
                    (temp_root / "acceptance.db").exists()
                    and (temp_root / "apps/api/data/runtime.env").exists()
                    and (temp_root / "apps/api/data/runtime_secrets.json").exists()
                    and not (ROOT / "acceptance.db").exists(),
                    "Acceptance data, runtime settings, and encrypted secrets stay inside the temporary directory.",
                )
                runtime_env = (temp_root / "apps/api/data/runtime.env").read_text(encoding="utf-8")
                record(
                    checks,
                    "runtime_secret_separation",
                    "ENABLE_REAL_IM_ADAPTERS=true" in runtime_env
                    and "FEISHU_APP_ID=cli_acceptance" in runtime_env
                    and "temporary-feishu-secret" not in runtime_env,
                    "Persistent runtime settings contain non-secrets only; Feishu secret remains encrypted.",
                )
    except Exception as exc:
        print(f"[fatal] product_workflow: {exc}", file=sys.stderr)
        return 1
    finally:
        os.chdir(original_cwd)

    failed = [check for check in checks if not check[1]]
    for name, ok, message in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {message}")
    if failed:
        print(f"\n{len(failed)} product workflow check(s) failed.", file=sys.stderr)
        return 1
    print(f"\nProduct workflow checks passed ({len(checks)} checks).")
    return 0


def configure_isolated_runtime(temp_root: Path) -> None:
    os.environ.update(
        {
            "WORKBUDDY_ENVIRONMENT": "local",
            "WORKBUDDY_DATABASE_URL": f"sqlite:///{temp_root / 'acceptance.db'}",
            "WORKBUDDY_AUTH_SECRET_PATH": str(temp_root / "auth_secret.txt"),
            "WORKBUDDY_LLM_PROVIDER": "mock",
            "WORKBUDDY_LLM_MODEL": "workbuddy-acceptance",
            "WORKBUDDY_LLM_API_KEY": "",
            "WORKBUDDY_LLM_BASE_URL": "",
            "WORKBUDDY_ENABLE_EXTERNAL_SEND": "false",
            "WORKBUDDY_ENABLE_REAL_IM_ADAPTERS": "false",
            "WORKBUDDY_ENABLE_BACKGROUND_JOBS": "false",
        }
    )


def create_user(client: Any, username: str, display_name: str, role: str, password: str) -> dict[str, Any]:
    return expect_json(
        client.post(
            "/api/users",
            json={
                "username": username,
                "display_name": display_name,
                "role": role,
                "password": password,
            },
        ),
        200,
        f"create user {username}",
    )


@contextmanager
def authenticated_client(app: Any, username: str, password: str):
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        expect_json(response, 200, f"login {username}")
        yield client


def expect_json(response: Any, expected_status: int, label: str) -> Any:
    if response.status_code != expected_status:
        raise RuntimeError(f"{label} returned {response.status_code}: {response.text[:500]}")
    return response.json()


def record(checks: list[tuple[str, bool, str]], name: str, ok: bool, message: str) -> None:
    checks.append((name, bool(ok), message))


if __name__ == "__main__":
    raise SystemExit(main())
