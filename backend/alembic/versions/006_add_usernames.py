"""Add usernames for login

Revision ID: 006
"""
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
    conn.exec_driver_sql("""
WITH candidates AS (
    SELECT
        ctid,
        lower(regexp_replace(COALESCE(NULLIF(split_part(email, '@', 1), ''), regexp_replace(id, '^user-', '')), '[^a-z0-9_.-]+', '-', 'g')) AS base
    FROM users
), normalized AS (
    SELECT
        ctid,
        CASE
            WHEN base IS NULL OR length(trim(both '-.' from base)) < 3 THEN 'user'
            ELSE trim(both '-.' from base)
        END AS base
    FROM candidates
), ranked AS (
    SELECT ctid, base, row_number() OVER (PARTITION BY base ORDER BY ctid) AS rn
    FROM normalized
)
UPDATE users AS u
SET username = CASE
    WHEN ranked.rn = 1 THEN left(ranked.base, 63)
    ELSE left(ranked.base, 58) || '-' || ranked.rn::text
END
FROM ranked
WHERE u.ctid = ranked.ctid AND u.username IS NULL
""")
    conn.exec_driver_sql("ALTER TABLE users ALTER COLUMN username SET NOT NULL")
    conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")


def downgrade():
    conn = op.get_bind()
    conn.exec_driver_sql("DROP INDEX IF EXISTS idx_users_username")
    conn.exec_driver_sql("ALTER TABLE users DROP COLUMN IF EXISTS username")
