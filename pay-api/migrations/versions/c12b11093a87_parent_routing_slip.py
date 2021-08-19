"""parent routing slip

Revision ID: c12b11093a87
Revises: 03b2c7caed21
Create Date: 2021-08-13 11:08:06.831666

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c12b11093a87'
down_revision = '03b2c7caed21'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('routing_slips', sa.Column('parent_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'routing_slips', 'routing_slips', ['parent_id'], ['id'])
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'routing_slips', type_='foreignkey')
    op.drop_column('routing_slips', 'parent_id')
    # ### end Alembic commands ###
