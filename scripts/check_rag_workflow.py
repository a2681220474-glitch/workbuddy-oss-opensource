from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ADMIN_PASSWORD = "RagAcceptance#2026"


def main() -> int:
    original_cwd = Path.cwd()
    checks: list[tuple[str, bool, str]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="workbuddy-rag-acceptance-") as temp_dir:
            temp_root = Path(temp_dir)
            configure_isolated_runtime(temp_root)
            os.chdir(temp_root)
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))

            from fastapi.testclient import TestClient

            from apps.api.main import app

            with TestClient(app) as client:
                expect_json(
                    client.post(
                        "/api/auth/bootstrap",
                        json={
                            "username": "rag_admin",
                            "display_name": "RAG 验收管理员",
                            "password": ADMIN_PASSWORD,
                        },
                    ),
                    200,
                    "bootstrap",
                )
                imported = expect_json(
                    client.post(
                        "/api/imports/knowledge/confirm",
                        json={
                            "source_type": "faq",
                            "filename": "rag-acceptance.md",
                            "content": (
                                "Q: 登录失败或账号无法使用时怎么处理？\n"
                                "A: 请先检查账号状态并重置密码；仍无法登录时记录报错截图，由支持人员排查认证日志。\n\n"
                                "Q: 如何申请电子发票？\n"
                                "A: 在订单详情中填写发票抬头和税号，提交后可下载电子发票。"
                            ),
                            "default_category": "support",
                            "default_mode": "item",
                            "publish": True,
                        },
                    ),
                    200,
                    "knowledge import",
                )
                items = imported.get("created_items") or []
                login_item = next((item for item in items if "登录" in str(item.get("title"))), None)
                record(checks, "knowledge_seed", len(items) == 2 and login_item is not None, "Two published knowledge items are isolated in the temporary database.")

                rebuilt = expect_json(client.post("/api/knowledge/index/rebuild"), 200, "index rebuild")
                record(
                    checks,
                    "embedding_index",
                    rebuilt.get("model") == "workbuddy-local-hash-v1"
                    and rebuilt.get("dimensions") == 192
                    and rebuilt.get("indexed_items") == 2,
                    "Local deterministic embeddings are rebuilt without an external model.",
                )

                search = expect_json(
                    client.post(
                        "/api/knowledge/search",
                        json={
                            "query": "账户登不上了，怎样恢复访问？",
                            "limit": 2,
                            "record_hit": True,
                            "source_object_type": "rag_acceptance",
                        },
                    ),
                    200,
                    "hybrid search",
                )
                matches = search.get("matches") or []
                top = matches[0] if matches else {}
                record(
                    checks,
                    "hybrid_ranking",
                    bool(matches)
                    and top.get("item", {}).get("id") == login_item.get("id")
                    and float(top.get("semantic_score") or 0) > 0
                    and top.get("retrieval_mode") == "hybrid",
                    "A paraphrased login question ranks the login article first with semantic evidence.",
                )
                record(
                    checks,
                    "citation_snippet",
                    str(top.get("citation", "")).startswith("[KB-")
                    and bool(top.get("snippet"))
                    and top.get("recorded_hit_id") is not None,
                    "The result contains an auditable citation, evidence snippet, and hit id.",
                )

                item_id = int(login_item["id"])
                hit_id = int(top["recorded_hit_id"])
                before_quality = int(login_item.get("quality_score") or 80)
                feedback = expect_json(
                    client.post(
                        f"/api/knowledge/hits/{hit_id}/feedback",
                        json={"status": "not_useful", "note": "验收：答案需要进一步优化"},
                    ),
                    200,
                    "negative feedback",
                )
                record(
                    checks,
                    "quality_feedback",
                    feedback.get("hit", {}).get("status") == "not_useful"
                    and feedback.get("item", {}).get("quality_status") == "needs_review"
                    and int(feedback.get("item", {}).get("quality_score") or 0) == before_quality - 10,
                    "Negative retrieval feedback lowers quality and sends the item to review.",
                )
                expect_json(
                    client.post(
                        "/api/knowledge/search",
                        json={
                            "query": "账户登不上了，怎样恢复访问？",
                            "limit": 2,
                            "record_hit": True,
                            "source_object_type": "rag_acceptance",
                        },
                    ),
                    200,
                    "repeat hybrid search",
                )
                repeated_feedback = expect_json(
                    client.post(
                        f"/api/knowledge/hits/{hit_id}/feedback",
                        json={"status": "not_useful", "note": "重复反馈不应再次扣分"},
                    ),
                    200,
                    "repeated feedback",
                )
                record(
                    checks,
                    "feedback_idempotency",
                    int(repeated_feedback.get("item", {}).get("quality_score") or 0) == before_quality - 10,
                    "Repeating the same feedback does not change quality twice.",
                )

                original_answer = str(login_item.get("answer") or "")
                edited = expect_json(
                    client.patch(
                        f"/api/knowledge/items/{item_id}",
                        json={
                            "answer": "临时验收答案：只检查浏览器缓存。",
                            "change_summary": "RAG 回滚验收临时编辑",
                        },
                    ),
                    200,
                    "edit item",
                )
                detail = expect_json(client.get(f"/api/knowledge/items/{item_id}"), 200, "item detail")
                versions = detail.get("versions") or []
                target = next((version for version in versions if version.get("answer") == original_answer), None)
                record(
                    checks,
                    "version_snapshot",
                    edited.get("answer") != original_answer and target is not None and len(versions) >= 2,
                    "Editing creates a recoverable knowledge version.",
                )

                rolled_back = expect_json(
                    client.post(
                        f"/api/knowledge/items/{item_id}/versions/{target['id']}/rollback",
                        json={"change_summary": "RAG 自动验收回滚"},
                    ),
                    200,
                    "version rollback",
                )
                detail_after = expect_json(client.get(f"/api/knowledge/items/{item_id}"), 200, "detail after rollback")
                latest_version = (detail_after.get("versions") or [{}])[0]
                record(
                    checks,
                    "version_rollback",
                    rolled_back.get("answer") == original_answer
                    and latest_version.get("change_type") == "rollback",
                    "Rollback restores the selected content and records a new rollback version.",
                )

                audits = expect_json(client.get("/api/audit-logs?limit=100"), 200, "audit logs")
                actions = {str(row.get("action_type")) for row in audits}
                record(
                    checks,
                    "rag_audit",
                    {"knowledge_index_rebuilt", "knowledge_hit_feedback", "knowledge_item_rolled_back"}.issubset(actions),
                    "Index rebuild, feedback, and rollback are all audited.",
                )
                record(
                    checks,
                    "isolated_database",
                    (temp_root / "rag-acceptance.db").exists() and not (ROOT / "rag-acceptance.db").exists(),
                    "RAG acceptance leaves the real local database untouched.",
                )
    except Exception as exc:
        print(f"[fatal] rag_workflow: {exc}", file=sys.stderr)
        return 1
    finally:
        os.chdir(original_cwd)

    failed = [check for check in checks if not check[1]]
    for name, ok, message in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {message}")
    if failed:
        print(f"\n{len(failed)} RAG workflow check(s) failed.", file=sys.stderr)
        return 1
    print(f"\nRAG workflow checks passed ({len(checks)} checks).")
    return 0


def configure_isolated_runtime(temp_root: Path) -> None:
    os.environ.update(
        {
            "WORKBUDDY_ENVIRONMENT": "local",
            "WORKBUDDY_DATABASE_URL": f"sqlite:///{temp_root / 'rag-acceptance.db'}",
            "WORKBUDDY_AUTH_SECRET_PATH": str(temp_root / "auth-secret.txt"),
            "WORKBUDDY_LLM_PROVIDER": "mock",
            "WORKBUDDY_LLM_API_KEY": "",
            "WORKBUDDY_ENABLE_EXTERNAL_SEND": "false",
            "WORKBUDDY_ENABLE_REAL_IM_ADAPTERS": "false",
            "WORKBUDDY_ENABLE_BACKGROUND_JOBS": "false",
        }
    )


def expect_json(response: Any, expected_status: int, label: str) -> Any:
    if response.status_code != expected_status:
        raise RuntimeError(f"{label} returned {response.status_code}: {response.text[:500]}")
    return response.json()


def record(checks: list[tuple[str, bool, str]], name: str, ok: bool, message: str) -> None:
    checks.append((name, bool(ok), message))


if __name__ == "__main__":
    raise SystemExit(main())
