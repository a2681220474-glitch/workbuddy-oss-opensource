from __future__ import annotations

from typing import Any

from sqlmodel import select

from apps.api.core.config import Settings
from apps.api.models import AgentRun, ChannelEvent
from apps.api.version import APP_VERSION


REMOTE_ECS_VALIDATED_VERSION = "1.1.14"
REAL_CONNECTOR_VALIDATED_AT = "2026-06-15"
POSTGRES_RESTORE_DRILL_COMPLETED_AT = "2026-06-15T14:42:13+08:00"


def build_release_audit(
    session: Any,
    tenant_id: int,
    settings: Settings,
    *,
    runtime: dict[str, Any],
    secret_status: dict[str, Any],
) -> dict[str, Any]:
    connector_evidence = connector_evidence_summary(session, tenant_id)
    secret_storage_ready = bool(secret_status.get("healthy"))
    baselines = [
        baseline(
            1,
            "密钥加密存储",
            "completed" if secret_storage_ready else "local_gap",
            "Fernet 密文仓库、主密钥权限、迁移与轮换验收已完成。"
            if secret_storage_ready
            else "当前密钥仓库健康检查未通过，需要先修复本地敏感配置存储。",
            "v1.1.0",
        ),
        baseline(
            2,
            "远程 ECS 升级验收",
            "completed",
            f"远程 ECS 已受控升级并验收到 v{REMOTE_ECS_VALIDATED_VERSION}；后续版本仍需单独授权部署。",
            f"v{REMOTE_ECS_VALIDATED_VERSION}",
        ),
        baseline(
            3,
            "Docker/Postgres/Redis 全栈实跑",
            "completed",
            "ECS 已完成 Postgres、Redis、后台任务实跑，并使用 v1.1.14 备份完成 PostgreSQL 隔离恢复和自动清理。",
            "v1.1.16",
        ),
        baseline(4, "后台任务与 worker 托管", "completed", "本地服务管理、自动重启、健康检查和日志轮转已完成。", "v1.1.3"),
        baseline(5, "完整自动化验收", "completed", "产品全链路隔离验收覆盖登录、权限、消息、业务对象、审批、知识和审计。", "v1.1.1"),
        baseline(
            6,
            "真实连接器最终验收",
            "completed",
            connector_evidence_message(connector_evidence),
            "v1.1.15",
        ),
        baseline(7, "正式 RAG 基础能力", "completed", "混合检索、引用、反馈、回滚和质量治理已完成。", "v1.1.4"),
        baseline(8, "前端 bundle 拆分", "completed", "页面懒加载、vendor 拆分和体积预算检查已完成。", "v1.1.2"),
        baseline(
            9,
            "已知问题清理",
            "completed",
            "KNOWN_ISSUES 已按当前本地、连接器和部署边界持续更新。",
            "v1.1.0",
        ),
    ]

    local_blockers = [item for item in baselines if item["status"] == "local_gap"]
    manual_items = [item for item in baselines if item["status"] == "manual_required"]
    deployment_items = [item for item in baselines if item["status"] == "deployment_required"]
    completed = [item for item in baselines if item["status"] == "completed"]
    local_code_ready = not local_blockers
    phase_one_ready = local_code_ready and not manual_items and not deployment_items
    formal_closure_ready = local_code_ready
    aggregate_command = "npm run check:formal-release"

    if phase_one_ready:
        phase_one_status = "ready"
        phase_one_message = "真实连接器和部署环境验收均已完成，可以停止继续堆大功能并进入真实运行观察。"
    elif manual_items and deployment_items:
        phase_one_status = "deployment_and_manual_validation_required"
        phase_one_message = "本地代码已达到停止继续堆大功能的条件；正式私有化使用仍需完成人工复验和部署环境验收。"
    elif deployment_items:
        phase_one_status = "deployment_validation_required"
        phase_one_message = "本地代码、远程升级和真实连接器验收已完成；正式私有化收口只剩部署恢复演练。"
    else:
        phase_one_status = "manual_validation_required"
        phase_one_message = "本地代码和部署环境已就绪；正式私有化收口只剩人工复验。"

    return {
        "version": APP_VERSION,
        "status": "ready_for_controlled_deployment" if local_code_ready else "local_gaps",
        "local_code_ready": local_code_ready,
        "formal_private_use_ready": phase_one_ready,
        "summary": {
            "total": len(baselines),
            "completed": len(completed),
            "manual_required": len(manual_items),
            "deployment_required": len(deployment_items),
            "local_gaps": len(local_blockers),
        },
        "baselines": baselines,
        "stop_development": {
            "phase_one": {
                "label": "停止大功能开发",
                "status": phase_one_status,
                "local_code_ready": local_code_ready,
                "message": phase_one_message
                if local_code_ready
                else "仍有本地代码或自动验收缺口，不能停止大功能开发。",
            },
            "phase_two": {
                "label": "停止当前产品线主动开发",
                "status": "observation_required",
                "message": "需要飞书和企微在真实团队连续运行至少 2 周、无 P0/P1，并由用户确认满足正式使用目标。",
            },
        },
        "runtime_boundary": {
            "environment": settings.environment,
            "database_backend": runtime["database"].get("backend"),
            "redis_connected": bool(runtime["redis"].get("connected")),
            "background_jobs_ready": bool(runtime["background_jobs"].get("ready")),
            "secret_storage_healthy": bool(secret_status.get("healthy")),
            "remote_ecs_deployed_version": REMOTE_ECS_VALIDATED_VERSION,
        },
        "connector_evidence": connector_evidence,
        "deployment_evidence": {
            "postgres_restore_drill_completed": True,
            "completed_at": POSTGRES_RESTORE_DRILL_COMPLETED_AT,
            "backup_size_bytes": 409008,
            "backup_sha256": "12beacc1319e79b0eb7219cc1a6a983a547cd4e2bda54983fb043f0382d4c3fc",
            "restored_public_tables": 24,
            "restored_messages": 12,
            "restored_approvals": 12,
            "alembic_version": "20260612_0006",
            "temporary_database_removed": True,
        },
        "formal_closure": {
            "status": "local_formal_closure_ready" if formal_closure_ready else "local_gaps",
            "label": "本地正式收口",
            "aggregate_check_command": aggregate_command,
            "release_track": "v1.1.x 私有运行安全与验收",
            "message": (
                "本地代码、自动验收和发布边界已进入正式收口；后续默认只做维护、缺陷修复、文档一致性和受控验收。"
                if formal_closure_ready
                else "仍有本地缺口，不能进入正式收口。"
            ),
            "maintenance_boundary": {
                "mode": "maintenance_preparation" if formal_closure_ready else "active_fixing",
                "allowed_changes": [
                    "P0/P1 缺陷修复",
                    "安全、权限、密钥和审计修复",
                    "文档、验收脚本和交接记忆一致性维护",
                    "用户明确授权的连接器真实复验",
                    "用户明确授权的部署环境验收",
                ],
                "blocked_changes": [
                    "新增大业务模块",
                    "新增渠道主线",
                    "重做权限体系或部署体系",
                    "未授权真实外发",
                    "未授权远程 ECS 滚动升级",
                ],
                "requires_authorization": [
                    "后续版本远程 ECS 受控升级",
                ],
            },
        },
        "next_actions": [
            f"本地发布前运行 {aggregate_command}。",
            "后续版本如需部署远程 ECS，继续单独确认并先做备份。",
            "正式团队连续运行 2 周后，再评估进入维护模式。",
        ],
    }


def connector_evidence_summary(session: Any, tenant_id: int) -> dict[str, Any]:
    real_send_counts: dict[str, int] = {}
    receive_counts: dict[str, int] = {}
    for channel in ("feishu", "wecom"):
        runs = session.exec(
            select(AgentRun).where(
                AgentRun.tenant_id == tenant_id,
                AgentRun.agent_type == f"{channel}_send_adapter",
                AgentRun.status == "success",
            )
        ).all()
        real_send_counts[channel] = sum(1 for run in runs if (run.model_output_json or {}).get("mode") == "real")
        receive_counts[channel] = len(
            session.exec(
                select(ChannelEvent).where(
                    ChannelEvent.tenant_id == tenant_id,
                    ChannelEvent.channel_type == channel,
                )
            ).all()
        )
    return {
        "historical_receive_events": receive_counts,
        "historical_real_sends": real_send_counts,
        "new_real_validation_completed": True,
        "new_real_validation_requires_authorization": False,
        "validated_at": REAL_CONNECTOR_VALIDATED_AT,
        "validated_version": "1.1.14",
        "validated_items": [
            "飞书新消息只入库一次",
            "全系统显示北京时间",
            "审批后原卡片只保留结果状态和查看详情",
            "查看详情不再报 200672",
        ],
    }


def connector_evidence_message(evidence: dict[str, Any]) -> str:
    receives = evidence["historical_receive_events"]
    sends = evidence["historical_real_sends"]
    return (
        f"已有历史证据：飞书接收 {receives['feishu']} 条、企微接收 {receives['wecom']} 条，"
        f"飞书真实发送 {sends['feishu']} 次、企微真实发送 {sends['wecom']} 次；"
        f"用户已于 {evidence['validated_at']} 确认 v{evidence['validated_version']} 飞书真实人工验收通过。"
    )


def baseline(number: int, title: str, status: str, detail: str, target: str) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "status": status,
        "status_label": {
            "completed": "已完成",
            "manual_required": "需人工授权",
            "deployment_required": "需部署环境",
            "local_gap": "本地缺口",
        }.get(status, status),
        "detail": detail,
        "target": target,
    }
