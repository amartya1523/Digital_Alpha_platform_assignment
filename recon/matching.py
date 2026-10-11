import re

from .models import BankTransaction

NAME_SUFFIXES = {'LLC', 'LP', 'LTD', 'INC'}


def normalize_reference(value):
    # "cc-1003" -> "CC1003"
    return re.sub(r'[^A-Z0-9]', '', value.upper())


def normalize_text(value):
    # "  wire incoming, Meridian  " -> "WIRE INCOMING MERIDIAN"
    return ' '.join(re.sub(r'[^A-Z0-9]', ' ', value.upper()).split())


def normalize_name(value):
    words = normalize_text(value).split()
    if words and words[-1] in NAME_SUFFIXES:
        words = words[:-1]
    return ' '.join(words)


def reference_found(line_item, description, bank_reference):
    ref = normalize_reference(line_item.expected_reference)
    if not ref:
        return False
    return ref in normalize_reference(description) or ref in normalize_reference(bank_reference)


def name_found(investor_name, description):
    name = normalize_name(investor_name)
    if not name:
        return False
    # pad with spaces so we only match whole words
    return f' {name} ' in f' {normalize_text(description)} '


def money(value):
    return f'{value:,.2f}'


def find_matches(txn, line_items):
    """
    Runs the matching rules for one credit.
    Returns (status, review_reason, [(line_item, match_reason), ...]).
    """
    amount, txn_date = txn.amount, txn.date
    eligible = [
        item for item in line_items
        if item.amount_remaining > 0 and item.capital_call.call_date <= txn_date
    ]
    if not eligible:
        return BankTransaction.NEEDS_REVIEW, f'No open line items with a call date on or before {txn_date}.', []

    # Step 1: reference check
    by_reference = [item for item in eligible if reference_found(item, txn.description, txn.bank_reference)]

    if len(by_reference) == 1:
        item = by_reference[0]
        remaining = item.amount_remaining
        if amount > remaining:
            reason = (f'Reference {item.expected_reference} found, but amount {money(amount)} '
                      f'is more than remaining {money(remaining)} (overpayment).')
            return BankTransaction.NEEDS_REVIEW, reason, []

        if amount == remaining:
            reason = f'Reference {item.expected_reference} found; amount equals remaining {money(remaining)}.'
        else:
            reason = (f'Reference {item.expected_reference} found; partial payment of {money(amount)} '
                      f'against remaining {money(remaining)}.')
        return BankTransaction.SUGGESTED, '', [(item, reason)]

    if len(by_reference) > 1:
        refs = ', '.join(item.expected_reference for item in by_reference)
        matches = [
            (item, f'Reference {item.expected_reference} found; remaining {money(item.amount_remaining)}.')
            for item in by_reference
        ]
        return BankTransaction.NEEDS_REVIEW, f'More than one reference found ({refs}).', matches

    # Step 2: investor name + exact remaining amount
    by_name = [
        item for item in eligible
        if amount == item.amount_remaining and name_found(item.investor.name, txn.description)
    ]
    matches = [
        (item, f'Investor "{item.investor.name}" found in description; amount equals remaining {money(amount)}.')
        for item in by_name
    ]

    if len(by_name) == 1:
        return BankTransaction.SUGGESTED, '', matches
    if len(by_name) > 1:
        refs = ', '.join(item.expected_reference for item in by_name)
        return BankTransaction.NEEDS_REVIEW, f'Name and amount match more than one line item ({refs}).', matches

    return BankTransaction.NEEDS_REVIEW, 'No reference found and no investor name with a matching remaining amount.', []
