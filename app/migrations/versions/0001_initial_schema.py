"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-29
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS foods_knowledgebase")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE foods_knowledgebase.foodstatus AS ENUM ('draft', 'verified', 'rejected');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS foods_knowledgebase.foods (
            id          VARCHAR(36) PRIMARY KEY,
            name        VARCHAR(200) NOT NULL,
            local_names JSONB        NOT NULL DEFAULT '[]',
            description TEXT         NOT NULL,
            region              VARCHAR(200) NOT NULL,
            region_normalized   VARCHAR(200) NOT NULL,
            price_min_kes FLOAT NOT NULL,
            price_max_kes FLOAT NOT NULL,
            meal_type   JSONB NOT NULL DEFAULT '[]',
            ingredients JSONB NOT NULL DEFAULT '[]',
            common_at   JSONB NOT NULL DEFAULT '[]',
            protein     VARCHAR(10),
            carbs       VARCHAR(10),
            vegetables  VARCHAR(10),
            sub_regions JSONB NOT NULL DEFAULT '[]',
            tags        JSONB NOT NULL DEFAULT '[]',
            status      foods_knowledgebase.foodstatus NOT NULL DEFAULT 'draft',
            embedding   vector(384),
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            approved_at TIMESTAMP
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS foods_knowledgebase.foods")
    op.execute("DROP TYPE IF EXISTS foods_knowledgebase.foodstatus")
    op.execute("DROP SCHEMA IF EXISTS foods_knowledgebase CASCADE")
