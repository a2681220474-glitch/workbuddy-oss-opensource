from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "1.1.16"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    package_json = read_json("package.json")
    web_package_json = read_json("apps/web/package.json")
    app_version = read_text("apps/api/version.py")
    main_tsx = read_text("apps/web/src/main.tsx")
    app_tsx = read_text("apps/web/src/App.tsx")
    auth_page = read_text("apps/web/src/pages/AuthPage.tsx")
    config_page = read_text("apps/web/src/pages/ConfigCenterPage.tsx")
    source_files = sorted((ROOT / "apps/web/src").rglob("*.tsx"))
    source_texts = {path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8") for path in source_files}
    known_issues = read_text("docs/KNOWN_ISSUES.md")
    handoff = read_text("docs/HANDOFF_NEXT_CHAT.md")
    release_doc = read_text(f"docs/release/v{EXPECTED_VERSION}.md")

    record(
        checks,
        "version_sync",
        package_json.get("version") == EXPECTED_VERSION
        and web_package_json.get("version") == EXPECTED_VERSION
        and f'"{EXPECTED_VERSION}"' in app_version,
        "Root, web, and API versions are synced.",
    )
    record(
        checks,
        "antd_app_provider",
        "App as AntdApp" in main_tsx and "<AntdApp>" in main_tsx and "</AntdApp>" in main_tsx,
        "Frontend root wraps the app with Ant Design App provider.",
    )
    record(
        checks,
        "root_message_context",
        "AntdApp.useApp()" in app_tsx and "message } from \"antd\"" not in app_tsx,
        "Root app uses Ant Design message from context.",
    )
    record(
        checks,
        "auth_message_context",
        "AntdApp.useApp()" in auth_page and "message } from \"antd\"" not in auth_page,
        "Auth page uses Ant Design message from context.",
    )
    record(
        checks,
        "config_message_modal_context",
        "AntdApp.useApp()" in config_page
        and "modal.confirm(" in config_page
        and "Modal.confirm(" not in config_page
        and "message } from \"antd\"" not in config_page,
        "Config center uses Ant Design message and modal from context.",
    )
    static_message_imports = [
        path for path, text in source_texts.items()
        if re.search(r'import\s*\{[^}]*\bmessage\b[^}]*\}\s*from\s+"antd"', text, re.S)
    ]
    static_modal_calls = [
        path for path, text in source_texts.items()
        if re.search(r'\bModal\.(confirm|warning|error|info|success)\s*\(', text)
    ]
    feedback_without_context = [
        path for path, text in source_texts.items()
        if re.search(r'\b(?:message|antdMessage)\.(success|error|warning|info|loading|open)\s*\(', text)
        and "AntdApp.useApp()" not in text
    ]
    modal_without_context = [
        path for path, text in source_texts.items()
        if re.search(r'\bmodal\.(confirm|warning|error|info|success)\s*\(', text)
        and "AntdApp.useApp()" not in text
    ]
    record(
        checks,
        "no_static_message_imports",
        not static_message_imports,
        "No web source imports static Ant Design message."
        + ("" if not static_message_imports else f" Offenders: {', '.join(static_message_imports)}"),
    )
    record(
        checks,
        "no_static_modal_calls",
        not static_modal_calls,
        "No web source calls static Ant Design Modal helpers."
        + ("" if not static_modal_calls else f" Offenders: {', '.join(static_modal_calls)}"),
    )
    record(
        checks,
        "feedback_context_coverage",
        not feedback_without_context and not modal_without_context,
        "Every page/component feedback call is backed by Ant Design App context."
        + (
            ""
            if not feedback_without_context and not modal_without_context
            else f" Offenders: {', '.join(feedback_without_context + modal_without_context)}"
        ),
    )
    record(
        checks,
        "deprecated_modal_prop_removed",
        "destroyOnClose" not in app_tsx and "destroyOnHidden" in app_tsx,
        "Deprecated Modal destroyOnClose prop is replaced.",
    )
    record(
        checks,
        "visible_version",
        "v1.1.16 部署恢复收口" in app_tsx,
        f"Top bar exposes the v{EXPECTED_VERSION} maintenance label.",
    )
    record(
        checks,
        "known_issue_cleared",
        "Ant Design" in known_issues and ("v1.1.12" in known_issues or "`v1.1.12`" in known_issues),
        "Known issues records the cleared browser warnings.",
    )
    record(
        checks,
        "handoff_release_doc",
        "v1.1.16" in handoff
        and "check:frontend-maintenance" in handoff
        and "隔离恢复" in release_doc
        and "npm run check:frontend-maintenance" in release_doc,
        "Handoff and release notes document the maintenance check.",
    )

    failed = [item for item in checks if not item[1]]
    for name, ok, message in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {message}")
    if failed:
        print(f"\n{len(failed)} frontend maintenance check(s) failed.", file=sys.stderr)
        return 1
    print(f"\nFrontend maintenance checks passed ({len(checks)} checks).")
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
