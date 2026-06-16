from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from apps.api.core.config import get_settings
from apps.api.models import LocalUser, Tenant, utc_now


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=not settings.database_url.startswith("sqlite"),
)


def init_db() -> None:
    ensure_database_schema_ready()
    with Session(engine) as session:
        tenant = session.exec(select(Tenant).where(Tenant.key == settings.demo_tenant_key)).first()
        if tenant is None:
            session.add(Tenant(key=settings.demo_tenant_key, name=settings.demo_tenant_name))
            session.commit()
            tenant = session.exec(select(Tenant).where(Tenant.key == settings.demo_tenant_key)).first()
        ensure_default_local_user(session, tenant.id if tenant else None)


def ensure_database_schema_ready() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "tenants" not in tables:
        if settings.database_url.startswith("sqlite"):
            SQLModel.metadata.create_all(engine)
            tables = set(inspector.get_table_names())
        else:
            raise RuntimeError(
                "Database schema is not initialized. Run `npm run db:migrate` or `.venv/bin/python scripts/run_migrations.py` before starting the API."
            )
    if settings.database_url.startswith("sqlite"):
        SQLModel.metadata.create_all(engine)
    ensure_sqlite_columns()


def ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    with engine.begin() as connection:
        if "conversations" in tables and not has_column(inspector, "conversations", "send_mode"):
            connection.execute(text("ALTER TABLE conversations ADD COLUMN send_mode VARCHAR(30) DEFAULT 'inherit'"))
        if "followup_tasks" in tables and not has_column(inspector, "followup_tasks", "due_at"):
            connection.execute(text("ALTER TABLE followup_tasks ADD COLUMN due_at DATETIME"))
        if "followup_tasks" in tables and not has_column(inspector, "followup_tasks", "assignee_user_id"):
            connection.execute(text("ALTER TABLE followup_tasks ADD COLUMN assignee_user_id INTEGER"))
        if "followup_tasks" in tables and not has_column(inspector, "followup_tasks", "assignee_username"):
            connection.execute(text("ALTER TABLE followup_tasks ADD COLUMN assignee_username VARCHAR(80)"))
        if "processing_records" in tables and not has_column(inspector, "processing_records", "due_at"):
            connection.execute(text("ALTER TABLE processing_records ADD COLUMN due_at DATETIME"))
        if "processing_records" in tables and not has_column(inspector, "processing_records", "assignee_user_id"):
            connection.execute(text("ALTER TABLE processing_records ADD COLUMN assignee_user_id INTEGER"))
        if "processing_records" in tables and not has_column(inspector, "processing_records", "assignee_username"):
            connection.execute(text("ALTER TABLE processing_records ADD COLUMN assignee_username VARCHAR(80)"))
        if "processing_records" in tables and not has_column(inspector, "processing_records", "operator_user_id"):
            connection.execute(text("ALTER TABLE processing_records ADD COLUMN operator_user_id INTEGER"))
        if "processing_records" in tables and not has_column(inspector, "processing_records", "operator_username"):
            connection.execute(text("ALTER TABLE processing_records ADD COLUMN operator_username VARCHAR(80)"))


def has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def ensure_default_local_user(session: Session, tenant_id: int | None) -> None:
    if tenant_id is None:
        return
    user = session.exec(
        select(LocalUser).where(LocalUser.tenant_id == tenant_id, LocalUser.username == "local_admin")
    ).first()
    if user is not None:
        return
    session.add(
        LocalUser(
            tenant_id=tenant_id,
            username="local_admin",
            display_name="本地管理员",
            role="admin",
            status="active",
            updated_at=utc_now(),
        )
    )
    session.commit()
