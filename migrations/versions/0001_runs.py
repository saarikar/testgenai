"""Initial run and test-case storage."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("generation_seconds", sa.Float(), nullable=False),
        sa.Column("execution_seconds", sa.Float()),
        sa.Column("generated_tests", sa.Text()),
        sa.Column("execution", sa.JSON()),
        sa.Column("token_usage", sa.JSON()),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_table(
        "test_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("message", sa.Text()),
    )
    op.create_index("ix_test_cases_run_id", "test_cases", ["run_id"])


def downgrade():
    op.drop_table("test_cases")
    op.drop_table("runs")
