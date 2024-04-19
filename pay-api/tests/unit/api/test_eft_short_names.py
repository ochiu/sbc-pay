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

"""Tests to assure the accounts end-point.

Test-Suite to ensure that the /accounts endpoint is working as expected.
"""

import json
from datetime import datetime

import pytest
from flask import current_app

from pay_api.models import EFTCredit as EFTCreditModel
from pay_api.models import EFTFile as EFTFileModel
from pay_api.models import EFTShortnames as EFTShortnamesModel
from pay_api.models import EFTTransaction as EFTTransactionModel
from pay_api.models import Payment as PaymentModel
from pay_api.models import Receipt as ReceiptModel
from pay_api.utils.enums import (
    EFTFileLineType, EFTProcessStatus, EFTShortnameStatus, InvoiceStatus, PaymentMethod, PaymentStatus, Role)
from tests.utilities.base_test import (
    factory_eft_file, factory_eft_shortname, factory_eft_shortname_link, factory_invoice, factory_payment_account,
    get_claims, token_header)


def test_create_eft_short_name_link(session, client, jwt, app):
    """Assert that an EFT short name link can be created."""
    token = jwt.create_jwt(get_claims(roles=[Role.MANAGE_EFT.value],
                                      username='IDIR/JSMITH'), token_header)
    headers = {'Authorization': f'Bearer {token}', 'content-type': 'application/json'}
    factory_payment_account(payment_method_code=PaymentMethod.EFT.value,
                            auth_account_id='1234').save()

    short_name = factory_eft_shortname(short_name='TESTSHORTNAME').save()
    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/links',
                     data=json.dumps({'accountId': '1234'}),
                     headers=headers)
    link_dict = rv.json
    assert rv.status_code == 200
    assert link_dict is not None
    assert link_dict['id'] is not None
    assert link_dict['shortNameId'] == short_name.id
    assert link_dict['statusCode'] == EFTShortnameStatus.PENDING.value
    assert link_dict['accountId'] == '1234'
    assert link_dict['updatedBy'] == 'IDIR/JSMITH'

    date_format = '%Y-%m-%dT%H:%M:%S.%f'
    assert datetime.strptime(link_dict['updatedOn'], date_format).date() == datetime.now().date()


def test_create_eft_short_name_link_validation(session, client, jwt, app):
    """Assert that invalid request is returned for existing short name link."""
    token = jwt.create_jwt(get_claims(roles=[Role.MANAGE_EFT.value],
                                      username='IDIR/JSMITH'), token_header)
    headers = {'Authorization': f'Bearer {token}', 'content-type': 'application/json'}
    short_name = factory_eft_shortname(short_name='TESTSHORTNAME').save()
    factory_eft_shortname_link(
        short_name_id=short_name.id,
        auth_account_id='1234',
        updated_by='IDIR/JSMITH'
    ).save()

    # Assert requires an auth account id for mapping
    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/links',
                     data=json.dumps({}),
                     headers=headers)

    link_dict = rv.json
    assert rv.status_code == 400
    assert link_dict['type'] == 'EFT_SHORT_NAME_ACCOUNT_ID_REQUIRED'

    # Assert cannot create link to an existing mapped account id
    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/links',
                     data=json.dumps({'accountId': '1234'}),
                     headers=headers)

    link_dict = rv.json
    assert rv.status_code == 400
    assert link_dict['type'] == 'EFT_SHORT_NAME_ALREADY_MAPPED'


def test_get_eft_short_name_links(session, client, jwt, app):
    """Assert that short name links can be retrieved."""
    token = jwt.create_jwt(get_claims(roles=[Role.MANAGE_EFT.value],
                                      username='IDIR/JSMITH'), token_header)
    headers = {'Authorization': f'Bearer {token}', 'content-type': 'application/json'}
    short_name = factory_eft_shortname(short_name='TESTSHORTNAME').save()

    # Assert an empty result set is properly returned
    rv = client.get(f'/api/v1/eft-shortnames/{short_name.id}/links',
                    headers=headers)

    link_dict = rv.json
    assert rv.status_code == 200
    assert link_dict is not None
    assert link_dict['items'] is not None
    assert len(link_dict['items']) == 0

    # Create a short name link
    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/links',
                     data=json.dumps({'accountId': '1234'}),
                     headers=headers)

    link_dict = rv.json
    assert rv.status_code == 200

    # Assert link is returned in the result
    rv = client.get(f'/api/v1/eft-shortnames/{short_name.id}/links',
                    headers=headers)

    link_list_dict = rv.json
    assert rv.status_code == 200
    assert link_list_dict is not None
    assert link_list_dict['items'] is not None
    assert len(link_list_dict['items']) == 1

    link = link_list_dict['items'][0]
    assert link['accountId'] == '1234'
    assert link['id'] == link_dict['id']
    assert link['shortNameId'] == short_name.id
    assert link['statusCode'] == EFTShortnameStatus.PENDING.value
    assert link['updatedBy'] == 'IDIR/JSMITH'


def assert_short_name(result_dict: dict, short_name: EFTShortnamesModel, transaction: EFTTransactionModel,
                      expected_status: str):
    """Assert short name result."""
    date_format = '%Y-%m-%dT%H:%M:%S'
    assert result_dict['shortName'] == short_name.short_name
    assert result_dict['statusCode'] == expected_status
    assert result_dict['depositAmount'] == transaction.deposit_amount_cents / 100
    assert datetime.strptime(result_dict['depositDate'], date_format) == transaction.deposit_date
    assert result_dict['transactionId'] == transaction.id
    assert datetime.strptime(result_dict['transactionDate'], date_format) == transaction.transaction_date


def test_search_eft_short_names(session, client, jwt, app):
    """Assert that EFT short names can be searched."""
    token = jwt.create_jwt(get_claims(roles=[Role.MANAGE_EFT.value]), token_header)
    headers = {'Authorization': f'Bearer {token}', 'content-type': 'application/json'}

    # Assert initial search returns empty items
    rv = client.get('/api/v1/eft-shortnames', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 0

    # create test data
    payment_account = factory_payment_account(payment_method_code=PaymentMethod.EFT.value,
                                              auth_account_id='1234',
                                              name='ABC-123',
                                              branch_name='123').save()

    eft_file: EFTFileModel = factory_eft_file()
    short_name_1 = factory_eft_shortname(short_name='TESTSHORTNAME1').save()
    short_name_2 = factory_eft_shortname(short_name='TESTSHORTNAME2').save()
    factory_eft_shortname_link(
        short_name_id=short_name_2.id,
        auth_account_id='1234',
        updated_by='IDIR/JSMITH'
    ).save()

    # short_name_1 transactions to test getting first payment
    s1_transaction1: EFTTransactionModel = EFTTransactionModel(
        line_type=EFTFileLineType.TRANSACTION.value,
        line_number=1,
        file_id=eft_file.id,
        status_code=EFTProcessStatus.COMPLETED.value,
        transaction_date=datetime(2024, 1, 5, 2, 30),
        deposit_date=datetime(2024, 1, 6, 10, 5),
        deposit_amount_cents=10150,
        short_name_id=short_name_1.id

    ).save()

    # Identical to transaction 1 should not return duplicate short name rows - partitioned by transaction date, id
    EFTTransactionModel(
        line_type=EFTFileLineType.TRANSACTION.value,
        line_number=1,
        file_id=eft_file.id,
        status_code=EFTProcessStatus.COMPLETED.value,
        transaction_date=datetime(2024, 1, 5, 2, 30),
        deposit_date=datetime(2024, 1, 6, 10, 5),
        deposit_amount_cents=10250,
        short_name_id=short_name_1.id

    ).save()

    EFTTransactionModel(
        line_type=EFTFileLineType.TRANSACTION.value,
        line_number=1,
        file_id=eft_file.id,
        status_code=EFTProcessStatus.COMPLETED.value,
        transaction_date=datetime(2024, 1, 10, 2, 30),
        deposit_date=datetime(2024, 1, 11, 10, 5),
        deposit_amount_cents=30150,
        short_name_id=short_name_1.id
    ).save()

    # short_name_2 transactions - to test date filters
    s2_transaction1: EFTTransactionModel = EFTTransactionModel(
        line_type=EFTFileLineType.TRANSACTION.value,
        line_number=1,
        file_id=eft_file.id,
        status_code=EFTProcessStatus.COMPLETED.value,
        transaction_date=datetime(2024, 1, 15, 2, 30),
        deposit_date=datetime(2024, 1, 16, 10, 5),
        deposit_amount_cents=30250,
        short_name_id=short_name_2.id

    ).save()

    # Assert search returns unlinked short names
    rv = client.get('/api/v1/eft-shortnames?state=UNLINKED', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 1
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert result_dict['items'][0]['shortName'] == 'TESTSHORTNAME1'
    assert_short_name(result_dict['items'][0], short_name_1, s1_transaction1, EFTShortnameStatus.UNLINKED.value)

    # Assert search returns linked short names with payment account name that has a branch
    rv = client.get('/api/v1/eft-shortnames?state=LINKED', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 1
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert result_dict['items'][0]['shortName'] == 'TESTSHORTNAME2'
    assert result_dict['items'][0]['accountName'] == 'ABC'
    assert result_dict['items'][0]['accountBranch'] == '123'
    assert_short_name(result_dict['items'][0], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)

    # Assert search account name
    rv = client.get('/api/v1/eft-shortnames?state=LINKED&accountName=BC', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 1
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert result_dict['items'][0]['accountName'] == 'ABC'
    assert_short_name(result_dict['items'][0], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)

    # Assert search account branch
    rv = client.get('/api/v1/eft-shortnames?state=LINKED&accountBranch=2', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 1
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert result_dict['items'][0]['accountName'] == 'ABC'
    assert result_dict['items'][0]['accountBranch'] == '123'
    assert_short_name(result_dict['items'][0], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)

    # Update payment account to not have a branch name
    payment_account.name = 'ABC'
    payment_account.branch_name = None
    payment_account.save()

    # Assert search returns linked short names with payment account name that has no branch
    rv = client.get('/api/v1/eft-shortnames?state=LINKED', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 1
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert result_dict['items'][0]['shortName'] == 'TESTSHORTNAME2'
    assert result_dict['items'][0]['accountName'] == 'ABC'
    assert result_dict['items'][0]['accountBranch'] is None
    assert_short_name(result_dict['items'][0], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)

    # Assert search account name
    rv = client.get('/api/v1/eft-shortnames?state=LINKED&accountName=BC', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 1
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert result_dict['items'][0]['accountName'] == 'ABC'
    assert_short_name(result_dict['items'][0], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)

    # Assert search query by no state will return all records
    rv = client.get('/api/v1/eft-shortnames', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 2
    assert result_dict['total'] == 2
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 2
    assert_short_name(result_dict['items'][0], short_name_1, s1_transaction1, EFTShortnameStatus.UNLINKED.value)
    assert_short_name(result_dict['items'][1], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)

    # Assert search pagination - page 1 works
    rv = client.get('/api/v1/eft-shortnames?page=1&limit=1', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 2
    assert result_dict['total'] == 2
    assert result_dict['limit'] == 1
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert_short_name(result_dict['items'][0], short_name_1, s1_transaction1, EFTShortnameStatus.UNLINKED.value)

    # Assert search pagination - page 2 works
    rv = client.get('/api/v1/eft-shortnames?page=2&limit=1', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 2
    assert result_dict['stateTotal'] == 2
    assert result_dict['total'] == 2
    assert result_dict['limit'] == 1
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert_short_name(result_dict['items'][0], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)

    # Assert search text brings back both short names
    rv = client.get('/api/v1/eft-shortnames?shortName=SHORT', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 2
    assert result_dict['total'] == 2
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 2
    assert_short_name(result_dict['items'][0], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)
    assert_short_name(result_dict['items'][1], short_name_1, s1_transaction1, EFTShortnameStatus.UNLINKED.value)

    # Assert search text brings back one short name
    rv = client.get('/api/v1/eft-shortnames?shortName=name1', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 2
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert_short_name(result_dict['items'][0], short_name_1, s1_transaction1, EFTShortnameStatus.UNLINKED.value)

    # Assert search transaction date
    rv = client.get('/api/v1/eft-shortnames?transactionStartDate=2024-01-04&transactionEndDate=2024-01-14',
                    headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 2
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert_short_name(result_dict['items'][0], short_name_1, s1_transaction1, EFTShortnameStatus.UNLINKED.value)

    # Assert search transaction date
    rv = client.get('/api/v1/eft-shortnames?transactionStartDate=2024-01-04&transactionEndDate=2024-01-15',
                    headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 2
    assert result_dict['total'] == 2
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 2
    assert_short_name(result_dict['items'][0], short_name_1, s1_transaction1, EFTShortnameStatus.UNLINKED.value)
    assert_short_name(result_dict['items'][1], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)

    # Assert search transaction date
    rv = client.get('/api/v1/eft-shortnames?depositStartDate=2024-01-16&depositEndDate=2024-01-16', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 2
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert_short_name(result_dict['items'][0], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)

    # Assert search deposit amount
    rv = client.get('/api/v1/eft-shortnames?depositAmount=101.50', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 2
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert_short_name(result_dict['items'][0], short_name_1, s1_transaction1, EFTShortnameStatus.UNLINKED.value)

    # Assert search account id
    rv = client.get('/api/v1/eft-shortnames?state=LINKED&accountId=1234', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 1
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert_short_name(result_dict['items'][0], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)

    # Assert search account id list
    rv = client.get('/api/v1/eft-shortnames?accountIdList=1,1234', headers=headers)
    assert rv.status_code == 200

    result_dict = rv.json
    assert result_dict is not None
    assert result_dict['page'] == 1
    assert result_dict['stateTotal'] == 2
    assert result_dict['total'] == 1
    assert result_dict['limit'] == 10
    assert result_dict['items'] is not None
    assert len(result_dict['items']) == 1
    assert result_dict['items'][0]['shortName'] == 'TESTSHORTNAME2'
    assert result_dict['items'][0]['accountName'] == 'ABC'
    assert result_dict['items'][0]['accountBranch'] is None
    assert_short_name(result_dict['items'][0], short_name_2, s2_transaction1, EFTShortnameStatus.PENDING.value)


@pytest.mark.skip(reason='This needs to be re-thought, the create cfs invoice job should be handling receipt creation'
                         'and creating invoice references when payments are mapped, '
                         'it should wait until 6 pm before marking invoices as PAID'
                         'Otherwise calls to CFS could potentially fail and the two systems would go out of sync.')
def test_apply_eft_short_name_credits(session, client, jwt, app):
    """Assert that credits are applied to invoices when short name is mapped to an account."""
    token = jwt.create_jwt(get_claims(roles=[Role.STAFF.value, Role.MANAGE_EFT.value]), token_header)
    headers = {'Authorization': f'Bearer {token}', 'content-type': 'application/json'}
    short_name = factory_eft_shortname(short_name='TESTSHORTNAME').save()

    payment_account = factory_payment_account(payment_method_code=PaymentMethod.EFT.value,
                                              auth_account_id='1234').save()
    invoice_1 = factory_invoice(payment_account, payment_method_code=PaymentMethod.EFT.value,
                                total=50, paid=0).save()
    invoice_2 = factory_invoice(payment_account, payment_method_code=PaymentMethod.EFT.value,
                                total=200, paid=0).save()
    eft_file = factory_eft_file('test.txt')

    eft_credit_1 = EFTCreditModel()
    eft_credit_1.eft_file_id = eft_file.id
    eft_credit_1.payment_account_id = payment_account.id
    eft_credit_1.amount = 50
    eft_credit_1.remaining_amount = 50
    eft_credit_1.short_name_id = short_name.id
    eft_credit_1.save()

    eft_credit_2 = EFTCreditModel()
    eft_credit_2.eft_file_id = eft_file.id
    eft_credit_2.payment_account_id = payment_account.id
    eft_credit_2.amount = 150
    eft_credit_2.remaining_amount = 150
    eft_credit_2.short_name_id = short_name.id
    eft_credit_2.save()

    rv = client.patch(f'/api/v1/eft-shortnames/{short_name.id}',
                      data=json.dumps({'accountId': '1234'}),
                      headers=headers)
    shortname_dict = rv.json
    assert rv.status_code == 200
    assert shortname_dict is not None
    assert shortname_dict['id'] is not None
    assert shortname_dict['shortName'] == 'TESTSHORTNAME'
    assert shortname_dict['accountId'] == '1234'

    # Assert credits have the correct remaining values
    assert eft_credit_1.remaining_amount == 0
    assert eft_credit_1.payment_account_id == payment_account.id
    assert eft_credit_2.remaining_amount == 0
    assert eft_credit_2.payment_account_id == payment_account.id

    today = datetime.now().date()

    # Assert details of fully paid invoice
    invoice_1_paid = 50
    assert invoice_1.payment_method_code == PaymentMethod.EFT.value
    assert invoice_1.invoice_status_code == InvoiceStatus.PAID.value
    assert invoice_1.payment_date is not None
    assert invoice_1.payment_date.date() == today
    assert invoice_1.paid == invoice_1_paid
    assert invoice_1.total == invoice_1_paid

    receipt: ReceiptModel = ReceiptModel.find_by_invoice_id_and_receipt_number(invoice_1.id, invoice_1.id)
    assert receipt is not None
    assert receipt.receipt_number == str(invoice_1.id)
    assert receipt.receipt_amount == invoice_1_paid

    payment: PaymentModel = PaymentModel.find_payment_for_invoice(invoice_1.id)
    assert payment is not None
    assert payment.payment_date.date() == today
    assert payment.invoice_number == f'{current_app.config["EFT_INVOICE_PREFIX"]}{invoice_1.id}'
    assert payment.payment_account_id == payment_account.id
    assert payment.payment_status_code == PaymentStatus.COMPLETED.value
    assert payment.payment_method_code == PaymentMethod.EFT.value
    assert payment.invoice_amount == invoice_1_paid
    assert payment.paid_amount == invoice_1_paid

    assert not invoice_1.references

    # Assert details of partially paid invoice
    invoice_2_paid = 150
    assert invoice_2.payment_method_code == PaymentMethod.EFT.value
    assert invoice_2.invoice_status_code == InvoiceStatus.PARTIAL.value
    assert invoice_2.payment_date is not None
    assert invoice_2.payment_date.date() == today
    assert invoice_2.paid == 150
    assert invoice_2.total == 200

    receipt: ReceiptModel = ReceiptModel.find_by_invoice_id_and_receipt_number(invoice_2.id, invoice_2.id)
    assert receipt is not None
    assert receipt.receipt_number == str(invoice_2.id)
    assert receipt.receipt_amount == invoice_2_paid

    payment: PaymentModel = PaymentModel.find_payment_for_invoice(invoice_2.id)
    assert payment is not None
    assert payment.payment_date.date() == today
    assert payment.invoice_number == f'{current_app.config["EFT_INVOICE_PREFIX"]}{invoice_2.id}'
    assert payment.payment_account_id == payment_account.id
    assert payment.payment_status_code == PaymentStatus.COMPLETED.value
    assert payment.payment_method_code == PaymentMethod.EFT.value
    assert payment.invoice_amount == 200
    assert payment.paid_amount == invoice_2_paid

    assert not invoice_2.references
