"""Add embedding column with optional pgvector support.

Revision ID: 011
Down Revision: 010
"""

from alembic import op


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    has_vector = conn.exec_driver_sql(
        "SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')"
    ).scalar()
    if has_vector:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        conn.exec_driver_sql("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding vector(1024)")
        conn.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
            ON document_chunks USING hnsw (embedding vector_cosine_ops)
            """
        )
    else:
        conn.exec_driver_sql("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding real[]")


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("DROP INDEX IF EXISTS idx_document_chunks_embedding")
    conn.exec_driver_sql("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
