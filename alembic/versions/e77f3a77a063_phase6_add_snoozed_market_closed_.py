"""phase6_add_snoozed_market_closed_activated_enum_values

Revision ID: e77f3a77a063
Revises: 6620f3343929
Create Date: 2026-06-29 11:04:38.534164

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e77f3a77a063'
down_revision: Union[str, Sequence[str], None] = '6620f3343929'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TrackingStatus enum — add new statuses for Phase 6
    op.execute("ALTER TYPE trackingstatus ADD VALUE IF NOT EXISTS 'SNOOZED'")
    op.execute("ALTER TYPE trackingstatus ADD VALUE IF NOT EXISTS 'MARKET_CLOSED'")

    # TradeEventType enum — add new event types for Phase 6
    op.execute("ALTER TYPE tradeeventtype ADD VALUE IF NOT EXISTS 'ACTIVATED'")
    op.execute("ALTER TYPE tradeeventtype ADD VALUE IF NOT EXISTS 'MARKET_CLOSED'")

    # Note: TRADE_CLOSED is left in the PostgreSQL enum — ALTER TYPE
    # does not support DROP VALUE. It is no longer used by application code.


def downgrade() -> None:
    # PostgreSQL does not support removing enum values via ALTER TYPE.
    # These values are left in place on downgrade — they are harmless.
    pass
