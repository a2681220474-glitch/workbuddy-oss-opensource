from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect recent WeCom acceptance traces from WorkBuddy OSS.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000", help="WorkBuddy API base URL")
    parser.add_argument("--user", default="local_admin", help="Local WorkBuddy username for the acceptance request")
    parser.add_argument("--message-id", type=int, default=None, help="Only inspect one message ID")
    parser.add_argument("--contains", default="", help="Filter traces by message text substring")
    parser.add_argument(
        "--require-status",
        default="ready",
        choices=["complete", "ready", "needs_action", "blocked"],
        help="Minimum expected acceptance status",
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a text report")
    args = parser.parse_args()

    diagnostics = fetch_json(f"{args.api_base.rstrip('/')}/api/channels/wecom/diagnostics/full", args.user)
    traces = diagnostics.get("acceptance_traces") if isinstance(diagnostics, dict) else []
    if not isinstance(traces, list):
        print("No acceptance traces returned from WeCom diagnostics endpoint.", file=sys.stderr)
        return 2

    filtered = [trace for trace in traces if trace_matches(trace, args.message_id, args.contains)]
    if not filtered:
        print("No WeCom acceptance trace matched the requested filter.", file=sys.stderr)
        return 1

    status_rank = {"blocked": 0, "needs_action": 1, "ready": 2, "complete": 3}
    expected_rank = status_rank[args.require_status]
    selected = max(
        filtered,
        key=lambda trace: (
            status_rank.get(str(trace.get("status") or "blocked"), 0),
            int(((trace.get("message") or {}).get("id") or 0)),
        ),
    )
    selected_rank = status_rank.get(str(selected.get("status") or "blocked"), 0)

    if args.json:
        print(json.dumps({"selected": selected, "summary": diagnostics.get("acceptance_summary")}, ensure_ascii=False, indent=2))
    else:
        print(render_report(diagnostics.get("acceptance_summary"), selected))

    return 0 if selected_rank >= expected_rank else 1


def fetch_json(url: str, user: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "X-WorkBuddy-User": user},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to reach {url}: {exc}") from exc


def trace_matches(trace: dict[str, Any], message_id: int | None, contains: str) -> bool:
    message = trace.get("message") if isinstance(trace.get("message"), dict) else {}
    if message_id is not None and int(message.get("id") or 0) != message_id:
        return False
    if contains:
        haystack = f"{message.get('text') or ''} {trace.get('next_action') or ''}"
        if contains not in haystack:
            return False
    return True


def render_report(summary: Any, trace: dict[str, Any]) -> str:
    message = trace.get("message") if isinstance(trace.get("message"), dict) else {}
    checklist = trace.get("checklist") if isinstance(trace.get("checklist"), dict) else {}
    lines = []
    if isinstance(summary, dict):
        lines.append(
            "Acceptance summary: "
            f"total={summary.get('total', 0)} "
            f"complete={summary.get('complete', 0)} "
            f"ready={summary.get('ready', 0)} "
            f"needs_attention={summary.get('needs_attention', 0)}"
        )
    lines.append(
        f"Selected trace: message#{message.get('id')} "
        f"[{message.get('message_type_label') or message.get('message_type') or '-'}] "
        f"status={trace.get('status') or '-'}"
    )
    lines.append(f"Message: {message.get('text') or '-'}")
    lines.append(f"Next action: {trace.get('next_action') or '-'}")
    lines.append("Checklist:")
    for key in [
        "message_tracked",
        "routed",
        "business_object_created",
        "approval_created",
        "timeline_ready",
        "send_completed",
    ]:
        lines.append(f"  - {key}: {'yes' if checklist.get(key) else 'no'}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
