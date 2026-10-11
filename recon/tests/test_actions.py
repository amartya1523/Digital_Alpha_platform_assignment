import threading
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase

from recon import actions
from recon.importer import import_statement
from recon.models import BankTransaction, LineItem, Match, Organization

from .utils import ReconTestCase, csv_file


class ApproveTests(ReconTestCase):
    def test_approve_updates_funded_amount(self):
        self.upload('2026-04-04,ACH CREDIT HALLER CAPITAL LLC CC-1001,20000.00,credit,B1\n')
        match = Match.objects.get()

        res = self.post(f'/api/matches/{match.pk}/approve/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], 'reconciled')

        item = self.line_item('CC-1001')
        self.assertEqual(item.amount_funded, Decimal('20000.00'))
        self.assertEqual(item.amount_remaining, Decimal('7500.00'))
        self.assertEqual(item.status, LineItem.PARTIALLY_FUNDED)

    def test_second_approval_returns_409_and_does_not_fund_twice(self):
        self.upload('2026-04-04,ACH CREDIT HALLER CAPITAL LLC CC-1001,20000.00,credit,B1\n')
        match = Match.objects.get()

        self.assertEqual(self.post(f'/api/matches/{match.pk}/approve/').status_code, 200)
        self.assertEqual(self.post(f'/api/matches/{match.pk}/approve/').status_code, 409)
        self.assertEqual(self.line_item('CC-1001').amount_funded, Decimal('20000.00'))

    def test_two_payments_complete_the_line_item(self):
        self.upload(
            '2026-04-04,HALLER CAPITAL CC-1001,20000.00,credit,B1\n'
            '2026-04-14,HALLER CAPITAL cc1001,7500.00,credit,B2\n'
        )
        for match in Match.objects.all():
            self.assertEqual(self.post(f'/api/matches/{match.pk}/approve/').status_code, 200)
        item = self.line_item('CC-1001')
        self.assertEqual(item.amount_funded, Decimal('27500.00'))
        self.assertEqual(item.status, LineItem.FUNDED)

    def test_approve_rechecks_remaining_amount(self):
        # both are suggested at import, but only one can fit once the first is approved
        self.upload(
            '2026-04-07,PATEL FAMILY TRUST CC-1003,12500.00,credit,B1\n'
            '2026-04-08,PATEL FAMILY TRUST CC-1003,5000.00,credit,B2\n'
        )
        first, second = Match.objects.order_by('transaction__bank_reference')
        self.assertEqual(self.post(f'/api/matches/{first.pk}/approve/').status_code, 200)
        self.assertEqual(self.post(f'/api/matches/{second.pk}/approve/').status_code, 409)
        self.assertEqual(self.line_item('CC-1003').amount_funded, Decimal('12500.00'))

    def test_approve_rejects_the_other_matches(self):
        self.upload('2026-04-11,WIRE INCOMING OAKRIDGE HOLDINGS LLC,15000.00,credit,B1\n')
        chosen = Match.objects.get(line_item__expected_reference='CC-1005')
        self.post(f'/api/matches/{chosen.pk}/approve/')

        statuses = dict(Match.objects.values_list('line_item__expected_reference', 'status'))
        self.assertEqual(statuses, {'CC-1005': 'approved', 'CC-1006': 'rejected'})
        self.assertEqual(self.line_item('CC-1006').amount_funded, Decimal('0.00'))


class RejectAndIgnoreTests(ReconTestCase):
    def test_rejecting_last_match_moves_to_needs_review(self):
        self.upload('2026-04-11,WIRE INCOMING OAKRIDGE HOLDINGS LLC,15000.00,credit,B1\n')
        first, second = Match.objects.all()

        self.post(f'/api/matches/{first.pk}/reject/')
        self.post(f'/api/matches/{second.pk}/reject/')
        self.assertEqual(BankTransaction.objects.get().status, BankTransaction.NEEDS_REVIEW)

        res = self.post(f'/api/matches/{first.pk}/reject/')
        self.assertEqual(res.status_code, 409)

    def test_ignore_rejects_matches(self):
        self.upload('2026-04-07,WIRE INCOMING PATEL FAMILY TRUST,12500.00,credit,B1\n')
        txn = BankTransaction.objects.get()

        res = self.post(f'/api/transactions/{txn.pk}/ignore/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], 'ignored')
        self.assertEqual(Match.objects.get().status, Match.REJECTED)

    def test_ignore_reconciled_returns_409(self):
        self.upload('2026-04-07,WIRE INCOMING PATEL FAMILY TRUST,12500.00,credit,B1\n')
        txn = BankTransaction.objects.get()
        self.post(f'/api/matches/{Match.objects.get().pk}/approve/')

        self.assertEqual(self.post(f'/api/transactions/{txn.pk}/ignore/').status_code, 409)
        self.assertEqual(BankTransaction.objects.get().status, BankTransaction.RECONCILED)


class ConcurrentApproveTests(TransactionTestCase):
    """Two real DB connections approving the same match at the same moment."""

    def test_same_approval_twice_at_once_funds_only_once(self):
        call_command('seed_demo', stdout=StringIO())
        org = Organization.objects.get(slug='northwind')
        # a partial payment, so without locking both approvals would "fit"
        import_statement(org, csv_file('2026-04-04,HALLER CAPITAL CC-1001,10000.00,credit,B1\n'))
        match = Match.objects.get()

        barrier = threading.Barrier(2)
        results = []

        def approve():
            barrier.wait()
            try:
                actions.approve_match(org, match.pk)
                results.append('ok')
            except actions.Conflict:
                results.append('conflict')
            finally:
                connection.close()

        threads = [threading.Thread(target=approve) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(results), ['conflict', 'ok'])
        self.assertEqual(LineItem.objects.get(expected_reference='CC-1001').amount_funded, Decimal('10000.00'))
