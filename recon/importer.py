import csv
import io
import re
from datetime import date
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ParseError

from .airtable import get_client as get_airtable_client, sync_needs_review
from .matching import find_matches
from .models import BankTransaction, LineItem, Match, Organization

REQUIRED_COLUMNS = ['date', 'description', 'amount', 'type', 'reference']

DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
# 25000.00, 25,000.00, -25.00 (commas only as thousands separators)
AMOUNT_RE = re.compile(r'[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d{1,2})?')
MAX_AMOUNT = Decimal('1000000000000')  # fits max_digits=14


class RowError(Exception):
    pass


def parse_date(value):
    if not DATE_RE.fullmatch(value):
        raise RowError(f'Invalid date "{value}", expected YYYY-MM-DD.')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise RowError(f'Invalid date "{value}", not a real calendar date.')


def parse_amount(value):
    if not AMOUNT_RE.fullmatch(value):
        raise RowError(f'Invalid amount "{value}".')
    amount = Decimal(value.replace(',', ''))
    if amount == 0:
        raise RowError('Amount cannot be zero.')
    if abs(amount) >= MAX_AMOUNT:
        raise RowError(f'Amount "{value}" is too large.')
    return amount


def parse_row(row):
    values = {col: (row.get(col) or '').strip() for col in REQUIRED_COLUMNS}

    empty = [col for col in REQUIRED_COLUMNS if not values[col]]
    if empty:
        raise RowError(f'Missing value for {", ".join(empty)}.')

    txn_date = parse_date(values['date'])
    amount = parse_amount(values['amount'])

    txn_type = values['type'].lower()
    if txn_type not in ('credit', 'debit'):
        raise RowError(f'Invalid type "{values["type"]}", expected credit or debit.')
    if txn_type == 'credit' and amount < 0:
        raise RowError('Credit amount must be positive.')
    if txn_type == 'debit' and amount > 0:
        raise RowError('Debit amount must be negative.')

    if len(values['reference']) > 100:
        raise RowError('Reference is longer than 100 characters.')

    return {
        'date': txn_date,
        'description': values['description'],
        'amount': amount,
        'reference': values['reference'],
    }


def read_rows(uploaded_file):
    """Returns [(line_number, row_dict)]. Raises ParseError if the file itself is bad."""
    try:
        text = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ParseError('File must be a UTF-8 encoded CSV.')

    reader = csv.DictReader(io.StringIO(text))
    header = [name.strip().lower() for name in (reader.fieldnames or [])]
    missing = [col for col in REQUIRED_COLUMNS if col not in header]
    if missing:
        raise ParseError(f'Missing column(s): {", ".join(missing)}. Nothing was imported.')
    reader.fieldnames = header

    try:
        # line_num counts physical lines, so blank lines don't shift the numbers (header is line 1)
        return [(reader.line_num, row) for row in reader]
    except csv.Error as e:
        raise ParseError(f'Could not read CSV: {e}')


def import_statement(org, uploaded_file):
    rows = read_rows(uploaded_file)
    summary = {'imported': 0, 'duplicates': 0, 'duplicate_rows': [], 'errors': []}

    valid = []
    for line, row in rows:
        try:
            valid.append((line, parse_row(row)))
        except RowError as e:
            summary['errors'].append({'line': line, 'message': str(e)})

    with transaction.atomic():
        # lock the org so two uploads for the same org can't race on the duplicate check
        Organization.objects.select_for_update().get(pk=org.pk)

        seen = set(
            BankTransaction.objects
            .filter(organization=org, bank_reference__in=[data['reference'] for _, data in valid])
            .values_list('bank_reference', flat=True)
        )
        line_items = list(
            LineItem.objects.filter(capital_call__organization=org).select_related('capital_call', 'investor')
        )

        new_txns = []
        new_matches = []
        for line, data in valid:
            if data['reference'] in seen:
                summary['duplicate_rows'].append({'line': line, 'reference': data['reference']})
                continue
            seen.add(data['reference'])

            txn = BankTransaction(
                organization=org,
                date=data['date'],
                description=data['description'],
                amount=data['amount'],
                bank_reference=data['reference'],
            )
            if txn.amount < 0:
                txn.status = BankTransaction.IGNORED
            else:
                txn.status, txn.review_reason, matches = find_matches(txn, line_items)
                new_matches += [(txn, item, reason) for item, reason in matches]
            new_txns.append(txn)

        BankTransaction.objects.bulk_create(new_txns)
        Match.objects.bulk_create([
            Match(transaction=txn, line_item=item, reason=reason) for txn, item, reason in new_matches
        ])

    # outside the DB transaction, so an Airtable problem can't undo the import
    sync_needs_review(new_txns, get_airtable_client())

    summary['imported'] = len(new_txns)
    summary['duplicates'] = len(summary['duplicate_rows'])
    return summary
