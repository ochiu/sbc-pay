# Copyright © 2023 Province of British Columbia
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Model to handle EFT file processing."""
from datetime import datetime
from _decimal import Decimal
from attrs import define

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY

from .base_model import BaseModel
from .db import db
from ..utils.util import cents_to_decimal


class EFTTransaction(BaseModel):  # pylint: disable=too-many-instance-attributes
    """This class manages the file data for EFT transactions."""

    __tablename__ = 'eft_transactions'
    # this mapper is used so that new and old versions of the service can be run simultaneously,
    # making rolling upgrades easier
    # This is used by SQLAlchemy to explicitly define which fields we're interested
    # so it doesn't freak out and say it can't map the structure if other fields are present.
    # This could occur from a failed deploy or during an upgrade.
    # The other option is to tell SQLAlchemy to ignore differences, but that is ambiguous
    # and can interfere with Alembic upgrades.
    #
    # NOTE: please keep mapper names in alpha-order, easier to track that way
    #       Exception, id is always first, _fields first
    __mapper_args__ = {
        'include_properties': [
            'id',
            'batch_number',
            'completed_on',
            'created_on',
            'deposit_amount_cents',
            'deposit_date',
            'error_messages',
            'file_id',
            'last_updated_on',
            'line_number',
            'line_type',
            'jv_type',
            'jv_number',
            'sequence_number',
            'short_name_id',
            'status_code',
            'transaction_date'
        ]
    }

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_number = db.Column('batch_number', db.String(10), nullable=True)
    completed_on = db.Column('completed_on', db.DateTime, nullable=True)
    created_on = db.Column('created_on', db.DateTime, nullable=False, default=datetime.now)
    error_messages = db.Column(ARRAY(String, dimensions=1), nullable=True)
    file_id = db.Column(db.Integer, ForeignKey('eft_files.id'), nullable=False, index=True)
    last_updated_on = db.Column('last_updated_on', db.DateTime, nullable=False, default=datetime.now)
    line_number = db.Column('line_number', db.Integer, nullable=False)
    line_type = db.Column('line_type', db.String(), nullable=False)
    jv_type = db.Column('jv_type', db.String(1), nullable=True)
    jv_number = db.Column('jv_number', db.String(10), nullable=True)
    sequence_number = db.Column('sequence_number', db.String(3), nullable=True)
    short_name_id = db.Column(db.Integer, ForeignKey('eft_short_names.id'), nullable=True)
    status_code = db.Column(db.String, ForeignKey('eft_process_status_codes.code'), nullable=False)
    deposit_amount_cents = db.Column('deposit_amount_cents', db.BigInteger, nullable=True)
    deposit_date = db.Column('deposit_date', db.DateTime, nullable=True)
    transaction_date = db.Column('transaction_date', db.DateTime, nullable=True)


@define
class EFTTransactionSchema:  # pylint: disable=too-few-public-methods
    """Main schema used to serialize a EFT Transaction."""

    id: int
    short_name_id: int
    transaction_date: datetime
    deposit_date: datetime
    deposit_amount: Decimal

    @classmethod
    def from_row(cls, row: EFTTransaction):
        """From row is used so we don't tightly couple to our database class.

        https://www.attrs.org/en/stable/init.html
        """
        return cls(id=row.id,
                   short_name_id=row.short_name_id,
                   transaction_date=getattr(row, 'transaction_date', None),
                   deposit_date=getattr(row, 'deposit_date', None),
                   deposit_amount=cents_to_decimal(getattr(row, 'deposit_amount_cents', None)))
