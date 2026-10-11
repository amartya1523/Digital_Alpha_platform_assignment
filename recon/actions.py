from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException

from .matching import money
from .models import BankTransaction, LineItem, Match


class Conflict(APIException):
    status_code = 409
    default_detail = 'This action conflicts with the current state.'


def _lock_match(org, match_id):
    """Locks the match and its transaction (always transaction first, then match)."""
    match = get_object_or_404(Match, pk=match_id, transaction__organization=org)
    txn = BankTransaction.objects.select_for_update().get(pk=match.transaction_id)
    match = Match.objects.select_for_update().get(pk=match.pk)
    return txn, match


@transaction.atomic
def approve_match(org, match_id):
    txn, match = _lock_match(org, match_id)
    if match.status != Match.PROPOSED:
        raise Conflict(f'Match is already {match.status}.')

    # re-check against the latest remaining amount, another payment may have been approved since import
    line_item = LineItem.objects.select_for_update().get(pk=match.line_item_id)
    if txn.amount > line_item.amount_remaining:
        raise Conflict(
            f'Amount {money(txn.amount)} is more than the remaining {money(line_item.amount_remaining)} '
            f'on {line_item.expected_reference}.'
        )

    line_item.add_funding(txn.amount)
    line_item.save()

    match.status = Match.APPROVED
    match.save()
    txn.matches.exclude(pk=match.pk).update(status=Match.REJECTED)

    txn.status = BankTransaction.RECONCILED
    txn.save()
    return txn


@transaction.atomic
def reject_match(org, match_id):
    txn, match = _lock_match(org, match_id)
    if match.status != Match.PROPOSED:
        raise Conflict(f'Match is already {match.status}.')

    match.status = Match.REJECTED
    match.save()

    if not txn.matches.filter(status=Match.PROPOSED).exists():
        txn.status = BankTransaction.NEEDS_REVIEW
        txn.review_reason = 'All suggested matches were rejected.'
        txn.save()
    return txn


@transaction.atomic
def ignore_transaction(org, txn_id):
    txn = get_object_or_404(BankTransaction.objects.select_for_update(), pk=txn_id, organization=org)
    if txn.status not in (BankTransaction.SUGGESTED, BankTransaction.NEEDS_REVIEW):
        raise Conflict(f'Cannot ignore a {txn.status} transaction.')

    txn.matches.filter(status=Match.PROPOSED).update(status=Match.REJECTED)
    txn.status = BankTransaction.IGNORED
    txn.save()
    return txn
