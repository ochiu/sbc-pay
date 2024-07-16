# Copyright © 2024 Province of British Columbia
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

"""Tests to assure the eft payment end-point.

Test-Suite to ensure that the EFT payment endpoint is working as expected.
"""

import json
from decimal import Decimal
from typing import List, Tuple

from pay_api.models import EFTCredit as EFTCreditModel
from pay_api.models import EFTShortnames as EFTShortnamesModel
from pay_api.models import PaymentAccount as PaymentAccountModel
from pay_api.services.eft_short_names import EFTShortnames as EFTShortnamesService
from pay_api.utils.enums import EFTPaymentActions, PaymentMethod, Role, StatementFrequency
from pay_api.utils.errors import Error
from tests.utilities.base_test import (
    factory_eft_file, factory_eft_shortname, factory_eft_shortname_link, factory_invoice, factory_payment_account,
    factory_statement, factory_statement_invoices, factory_statement_settings, get_claims, token_header)


def setup_account_shortname_data() -> Tuple[PaymentAccountModel, EFTShortnamesModel]:
    """Set up test data for payment account and short name."""
    account = factory_payment_account(payment_method_code=PaymentMethod.EFT.value,
                                      auth_account_id='1234').save()
    short_name = factory_eft_shortname(short_name='TESTSHORTNAME').save()
    factory_eft_shortname_link(
        short_name_id=short_name.id,
        auth_account_id=account.auth_account_id,
        updated_by='IDIR/JSMITH'
    ).save()

    return account, short_name


def setup_statement_data(account: PaymentAccountModel, invoice_totals: List[Decimal]):
    """Set up test data for statement."""
    statement_settings = factory_statement_settings(payment_account_id=account.id,
                                                    frequency=StatementFrequency.MONTHLY.value)
    statement = factory_statement(payment_account_id=account.id,
                                  frequency=StatementFrequency.MONTHLY.value,
                                  statement_settings_id=statement_settings.id)

    for invoice_total in invoice_totals:
        invoice = factory_invoice(account, payment_method_code=PaymentMethod.EFT.value,
                                  total=invoice_total, paid=0).save()
        factory_statement_invoices(statement_id=statement.id, invoice_id=invoice.id)

    return statement


def setup_eft_credits(short_name: EFTShortnamesModel, credit_amounts: List[Decimal] = [100]):
    """Set up EFT Credit data."""
    eft_file = factory_eft_file('test.txt')
    eft_credits = []

    for credit_amount in credit_amounts:
        eft_credit = EFTCreditModel()
        eft_credit.eft_file_id = eft_file.id
        eft_credit.amount = credit_amount
        eft_credit.remaining_amount = credit_amount
        eft_credit.short_name_id = short_name.id
        eft_credit.save()
        eft_credits.append(eft_credit)

    return eft_credits


def test_eft_apply_credits_action(db, session, client, jwt, app):
    """Assert that EFT payment apply credits action works."""
    token = jwt.create_jwt(get_claims(roles=[Role.MANAGE_EFT.value]), token_header)
    headers = {'Authorization': f'Bearer {token}', 'content-type': 'application/json'}

    account, short_name = setup_account_shortname_data()
    setup_statement_data(account=account, invoice_totals=[50, 50, 100])

    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/payment',
                     data=json.dumps({'action': EFTPaymentActions.APPLY_CREDITS.value}),
                     headers=headers)
    assert rv.status_code == 400
    assert rv.json['type'] == Error.EFT_PAYMENT_ACTION_ACCOUNT_ID_REQUIRED.name

    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/payment',
                     data=json.dumps({'action': EFTPaymentActions.APPLY_CREDITS.value,
                                      'accountId': account.auth_account_id}),
                     headers=headers)
    assert rv.status_code == 400
    assert rv.json['type'] == Error.EFT_INSUFFICIENT_CREDITS.name

    eft_credits = setup_eft_credits(short_name=short_name, credit_amounts=[50, 25, 125])

    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/payment',
                     data=json.dumps({'action': EFTPaymentActions.APPLY_CREDITS.value,
                                      'accountId': account.auth_account_id}),
                     headers=headers)
    assert rv.status_code == 204
    assert all(eft_credit.remaining_amount == 0 for eft_credit in eft_credits)
    assert EFTShortnamesService.get_eft_credit_balance(short_name.id) == 0

    # Assert we can't pay twice, based on pending invoice links
    # Add new credit to confirm it is not used
    eft_credits_2 = setup_eft_credits(short_name=short_name, credit_amounts=[300])
    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/payment',
                     data=json.dumps({'action': EFTPaymentActions.APPLY_CREDITS.value,
                                      'accountId': account.auth_account_id}),
                     headers=headers)
    assert rv.status_code == 204
    assert eft_credits_2[0].remaining_amount == 300
    assert EFTShortnamesService.get_eft_credit_balance(short_name.id) == 300


def test_eft_cancel_payment_action(session, client, jwt, app):
    """Assert that EFT payment cancel action works."""
    token = jwt.create_jwt(get_claims(roles=[Role.MANAGE_EFT.value]), token_header)
    headers = {'Authorization': f'Bearer {token}', 'content-type': 'application/json'}

    account, short_name = setup_account_shortname_data()
    setup_statement_data(account=account, invoice_totals=[50, 50, 100])
    eft_credits = setup_eft_credits(short_name=short_name, credit_amounts=[50, 25, 125])

    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/payment',
                     data=json.dumps({'action': EFTPaymentActions.CANCEL.value}),
                     headers=headers)
    assert rv.status_code == 400
    assert rv.json['type'] == Error.EFT_PAYMENT_ACTION_ACCOUNT_ID_REQUIRED.name

    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/payment',
                     data=json.dumps({'action': EFTPaymentActions.CANCEL.value,
                                      'accountId': account.auth_account_id}),
                     headers=headers)
    assert rv.status_code == 204

    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/payment',
                     data=json.dumps({'action': EFTPaymentActions.APPLY_CREDITS.value,
                                      'accountId': account.auth_account_id}),
                     headers=headers)
    assert rv.status_code == 204
    assert all(eft_credit.remaining_amount == 0 for eft_credit in eft_credits)
    assert EFTShortnamesService.get_eft_credit_balance(short_name.id) == 0

    credit_offset = 100
    eft_credits[1].remaining_amount += credit_offset
    eft_credits[1].save()
    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/payment',
                     data=json.dumps({'action': EFTPaymentActions.CANCEL.value,
                                      'accountId': account.auth_account_id}),
                     headers=headers)

    assert rv.status_code == 400
    assert rv.json['type'] == Error.EFT_CREDIT_AMOUNT_UNEXPECTED.name
    eft_credits[1].remaining_amount -= credit_offset
    eft_credits[1].save()
    # Assert no change and rollback was successful
    assert all(eft_credit.remaining_amount == 0 for eft_credit in eft_credits)
    assert EFTShortnamesService.get_eft_credit_balance(short_name.id) == 0

    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/payment',
                     data=json.dumps({'action': EFTPaymentActions.CANCEL.value,
                                      'accountId': account.auth_account_id}),
                     headers=headers)

    # Confirm credits have been restored
    assert rv.status_code == 204
    assert all(eft_credit.remaining_amount == eft_credit.amount for eft_credit in eft_credits)
    assert EFTShortnamesService.get_eft_credit_balance(short_name.id) == 200


def test_eft_payment_action_schema(db, session, client, jwt, app):
    """Assert that EFT payment schema is validated."""
    token = jwt.create_jwt(get_claims(roles=[Role.MANAGE_EFT.value]), token_header)
    headers = {'Authorization': f'Bearer {token}', 'content-type': 'application/json'}

    account, short_name = setup_account_shortname_data()

    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/payment',
                     data=json.dumps({}),
                     headers=headers)
    result = rv.json
    assert rv.status_code == 400
    assert result['invalidParams'][0] == "'action' is a required property"


def test_eft_payment_action_not_found(db, session, client, jwt, app):
    """Assert that EFT payment schema is validated."""
    token = jwt.create_jwt(get_claims(roles=[Role.MANAGE_EFT.value]), token_header)
    headers = {'Authorization': f'Bearer {token}', 'content-type': 'application/json'}

    rv = client.post('/api/v1/eft-shortnames/22222/payment',
                     data=json.dumps({}),
                     headers=headers)
    assert rv.status_code == 404


def test_eft_reverse_payment_action(db, session, client, jwt, app):
    """Assert that EFT payment reverse action works."""
    token = jwt.create_jwt(get_claims(roles=[Role.MANAGE_EFT.value]), token_header)
    headers = {'Authorization': f'Bearer {token}', 'content-type': 'application/json'}

    account, short_name = setup_account_shortname_data()
    setup_statement_data(account=account, invoice_totals=[50, 50, 100])

    rv = client.post(f'/api/v1/eft-shortnames/{short_name.id}/payment',
                     data=json.dumps({'action': EFTPaymentActions.REVERSE.value}),
                     headers=headers)
    assert rv.status_code == 400
    assert rv.json['type'] == Error.EFT_PAYMENT_ACTION_STATEMENT_ID_REQUIRED.name
