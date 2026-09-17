"""SQLAlchemy persistence. Source text is not stored; test artifacts are stored."""

import os
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    source_hash: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), index=True)
    generation_seconds: Mapped[float] = mapped_column(Float)
    execution_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_tests: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cases: Mapped[list["TestCase"]] = relationship(
        cascade="all, delete-orphan", back_populates="run"
    )


class TestCase(Base):
    __tablename__ = "test_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    duration_seconds: Mapped[float] = mapped_column(Float)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    run: Mapped[Run] = relationship(back_populates="cases")


class RunRepository:
    def __init__(self, url: str | None = None):
        self.url = url or os.getenv("DATABASE_URL", "sqlite:///./testgen.db")
        self.engine = create_engine(self.url, pool_pre_ping=True)

    def migrate(self):
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "migrations"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def close(self):
        self.engine.dispose()

    def save(self, record: dict):
        record = dict(record)
        execution = record.get("execution")
        cases = [] if not execution else execution.get("tests", [])
        if execution:
            record["execution"] = {k: v for k, v in execution.items() if k != "tests"}
        with Session(self.engine) as session, session.begin():
            run = Run(**record)
            run.cases = [
                TestCase(
                    name=c["name"],
                    status=c["status"],
                    duration_seconds=c["duration_seconds"],
                    message=c.get("message"),
                )
                for c in cases
            ]
            session.add(run)

    @staticmethod
    def serialize(run, detail=False):
        date = run.created_at
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        data = {
            key: getattr(run, key)
            for key in (
                "id",
                "source_hash",
                "provider",
                "model",
                "prompt_version",
                "status",
                "generation_seconds",
                "execution_seconds",
                "token_usage",
                "error",
            )
        }
        data["created_at"] = date.isoformat()
        if detail:
            data.update(
                generated_tests=run.generated_tests,
                execution=run.execution,
                tests=[
                    {
                        "name": c.name,
                        "status": c.status,
                        "duration_seconds": c.duration_seconds,
                        "message": c.message,
                    }
                    for c in run.cases
                ],
            )
        return data

    def list(self, limit=20, offset=0, status=None):
        with Session(self.engine) as session:
            query = select(Run)
            count = select(func.count()).select_from(Run)
            if status:
                query = query.where(Run.status == status)
                count = count.where(Run.status == status)
            rows = session.scalars(
                query.order_by(Run.created_at.desc(), Run.id).offset(offset).limit(limit)
            )
            return {
                "total": session.scalar(count),
                "items": [self.serialize(row) for row in rows],
                "limit": limit,
                "offset": offset,
            }

    def get(self, run_id):
        with Session(self.engine) as session:
            run = session.get(Run, run_id)
            return self.serialize(run, detail=True) if run else None

    def metrics(self):
        with Session(self.engine) as session:
            counts = dict(
                session.execute(select(Run.status, func.count()).group_by(Run.status)).all()
            )
            mean_generation, mean_execution = session.execute(
                select(func.avg(Run.generation_seconds), func.avg(Run.execution_seconds))
            ).one()
            return {
                "total_runs": sum(counts.values()),
                "by_status": counts,
                "mean_generation_seconds": mean_generation,
                "mean_execution_seconds": mean_execution,
            }
