from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "1.1.16"
VISIBLE_VERSION = "v1.1.16 部署恢复收口"

ROUTES: dict[str, str] = {
    "dashboard": "DashboardPage",
    "import": "ImportPage",
    "messages": "MessagesPage",
    "objects": "BusinessObjectsPage",
    "audit": "AuditPage",
    "team": "TeamPage",
    "approvals": "ApprovalsPage",
    "tickets": "TicketsPage",
    "community": "CommunityPage",
    "leads": "LeadsPage",
    "tasks": "TasksPage",
    "candidates": "CandidatesPage",
    "knowledge": "KnowledgePage",
    "reports": "ReportsPage",
    "demo": "DemoModePage",
    "config": "ConfigCenterPage",
    "conversations": "FeishuConversationsPage",
    "feishu-conversations": "FeishuConversationsPage",
    "channel-events": "ChannelEventsPage",
    "adapter-test": "AdapterTestPage",
    "feishu": "FeishuDiagnosticsPage",
    "wecom": "WeComDiagnosticsPage",
    "agent-runs": "AgentRunsPage",
}

REQUIRED_NAV_LABELS = [
    "工作台",
    "消息事件",
    "审批队列",
    "知识库",
    "配置中心",
    "飞书诊断",
    "企微诊断",
]


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    package_json = read_json("package.json")
    app_tsx = read_text("apps/web/src/App.tsx")
    navigation_ts = read_text("apps/web/src/utils/navigation.ts")
    index_html = read_text("apps/web/index.html")
    release_doc = read_text(f"docs/release/v{EXPECTED_VERSION}.md")
    known_issues = read_text("docs/KNOWN_ISSUES.md")

    page_imports = set(re.findall(r'import\("\./pages/([^"]+)"\)', app_tsx))
    package_scripts = package_json.get("scripts") or {}

    missing_page_files = sorted(
        {
            page_import
            for page_import in page_imports
            if not (ROOT / "apps/web/src/pages" / f"{page_import}.tsx").exists()
        }
    )
    missing_routes = [
        route
        for route, component in ROUTES.items()
        if route not in navigation_ts or component not in app_tsx or f"<{component}" not in app_tsx
    ]
    missing_labels = [label for label in REQUIRED_NAV_LABELS if label not in app_tsx]

    record(
        checks,
        "version_sync",
        package_json.get("version") == EXPECTED_VERSION
        and f'"{EXPECTED_VERSION}"' in read_text("apps/api/version.py")
        and read_json("apps/web/package.json").get("version") == EXPECTED_VERSION,
        "Root, web, and API versions are synced.",
    )
    record(
        checks,
        "visible_version",
        VISIBLE_VERSION in app_tsx,
        f"Top bar exposes {VISIBLE_VERSION}.",
    )
    record(
        checks,
        "route_manifest",
        not missing_routes and len(ROUTES) >= 23,
        "Every maintained hash route maps to a lazy page component."
        + ("" if not missing_routes else f" Missing: {', '.join(missing_routes)}"),
    )
    record(
        checks,
        "lazy_page_files",
        bool(page_imports) and not missing_page_files,
        "Every lazy page import resolves to an existing page file."
        + ("" if not missing_page_files else f" Missing files: {', '.join(missing_page_files)}"),
    )
    record(
        checks,
        "nav_labels",
        not missing_labels,
        "High-signal navigation labels are present."
        + ("" if not missing_labels else f" Missing labels: {', '.join(missing_labels)}"),
    )
    record(
        checks,
        "favicon",
        (ROOT / "apps/web/public/favicon.svg").exists()
        and 'href="/favicon.svg"' in index_html
        and "WB" in read_text("apps/web/public/favicon.svg"),
        "Browser tab favicon uses the WB brand mark.",
    )
    record(
        checks,
        "package_scripts",
        package_scripts.get("check:ui-smoke") == ".venv/bin/python scripts/check_ui_smoke.py"
        and "check:ui-smoke" in package_scripts.get("check:formal-release", ""),
        "UI smoke check is exposed and included in the formal release aggregate.",
    )
    record(
        checks,
        "release_docs",
        "隔离恢复" in release_doc
        and "npm run check:ui-smoke" in release_doc
        and "v1.1.16" in known_issues,
        "Release and known issues record the v1.1.16 deployment boundary.",
    )

    failed = [item for item in checks if not item[1]]
    for name, ok, message in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {message}")
    if failed:
        print(f"\n{len(failed)} UI smoke check(s) failed.", file=sys.stderr)
        return 1
    print(f"\nUI smoke checks passed ({len(checks)} checks, {len(ROUTES)} routes).")
    return 0


def read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def read_text(path: str) -> str:
    full_path = ROOT / path
    return full_path.read_text(encoding="utf-8") if full_path.exists() else ""


def record(checks: list[tuple[str, bool, str]], name: str, ok: bool, message: str) -> None:
    checks.append((name, bool(ok), message))


if __name__ == "__main__":
    raise SystemExit(main())
