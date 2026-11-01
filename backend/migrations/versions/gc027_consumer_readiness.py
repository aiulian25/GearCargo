"""Distinguish OCR consumer progress from synchronous decoder activity."""
from alembic import op
import sqlalchemy as sa

revision = 'gc027_consumer_readiness'
down_revision = 'gc026_session_authority'
branch_labels = depends_on = None


def upgrade():
    op.add_column('ocr_slots', sa.Column('consumer_seen_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('ocr_slots', 'consumer_seen_at')
