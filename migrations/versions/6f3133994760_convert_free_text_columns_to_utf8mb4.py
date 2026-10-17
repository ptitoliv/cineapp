"""Convert free text columns to utf8mb4

Revision ID: 6f3133994760
Revises: c4f8a2d91b37
Create Date: 2026-10-04 19:30:00.000000

"""

# revision identifiers, used by Alembic.
revision = '6f3133994760'
down_revision = 'c4f8a2d91b37'

from alembic import op
import sqlalchemy as sa


def upgrade():
    # The utf8 (utf8mb3) charset stores 3 bytes per character at most, so a
    # 4 bytes character like an emoji is rejected by the database (error 1366).
    # Only the columns typed freely by the users are converted : the mark
    # comment, the replies to a mark and the chat messages.
    op.execute("ALTER TABLE marks MODIFY comment VARCHAR(5000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL")
    op.execute("ALTER TABLE mark_comment MODIFY message VARCHAR(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL")
    op.execute("ALTER TABLE chat_messages MODIFY message VARCHAR(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL")


def downgrade():
    # Back to the charset of the tables. This fails (strict mode) as soon as
    # one row holds a 4 bytes character : these rows must be cleaned first.
    op.execute("ALTER TABLE chat_messages MODIFY message VARCHAR(1000) CHARACTER SET utf8 COLLATE utf8_general_ci DEFAULT NULL")
    op.execute("ALTER TABLE mark_comment MODIFY message VARCHAR(1000) CHARACTER SET utf8 COLLATE utf8_general_ci DEFAULT NULL")
    op.execute("ALTER TABLE marks MODIFY comment VARCHAR(5000) CHARACTER SET utf8 COLLATE utf8_general_ci DEFAULT NULL")
