"""service_fees

Revision ID: 1ad89abae65d
Revises: 06f6e75c18d8
Create Date: 2020-05-27 14:35:04.818636

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '1ad89abae65d'
down_revision = '06f6e75c18d8'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('corp_type', 'transaction_fee_code', new_column_name='service_fee_code')
    op.alter_column('invoice', 'transaction_fees', new_column_name='service_fees')
    op.execute('update corp_type set service_fee_code=\'TRF01\' where code=\'VS\'')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('corp_type', 'service_fee_code', new_column_name='transaction_fee_code')
    op.alter_column('invoice', 'service_fees', new_column_name='transaction_fees')
    # ### end Alembic commands ###
