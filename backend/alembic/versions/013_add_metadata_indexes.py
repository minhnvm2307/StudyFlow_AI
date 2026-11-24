"""add metadata indexes

Revision ID: 013
Revises: 012
Create Date: 2026-07-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE INDEX IF NOT EXISTS idx_document_chunks_topic_ids ON document_chunks USING gin (topic_ids)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_document_chunks_metadata ON document_chunks USING gin (metadata)")

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_metadata")
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_topic_ids")
