from decimal import Decimal

from recon.models import BankTransaction, Match

from .utils import ReconTestCase


class OrganizationHeaderTests(ReconTestCase):
    def test_missing_header_returns_400(self):
        self.assertEqual(self.client.get('/api/transactions/').status_code, 400)

    def test_unknown_org_returns_404(self):
        res = self.client.get('/api/transactions/', HTTP_X_ORGANIZATION='nope')
        self.assertEqual(res.status_code, 404)


class IsolationTests(ReconTestCase):
    def setUp(self):
        self.upload('2026-04-07,WIRE INCOMING PATEL FAMILY TRUST,12500.00,credit,B1\n', org='northwind')
        self.upload('2026-04-16,WIRE INCOMING CEDAR GROVE FUND CC-2001,40000.00,credit,B2\n', org='bluebird')
        self.northwind_match = Match.objects.get(transaction__bank_reference='B1')

    def test_lists_only_show_own_org(self):
        res = self.client.get('/api/transactions/', HTTP_X_ORGANIZATION='bluebird')
        self.assertEqual([t['bank_reference'] for t in res.data], ['B2'])

        res = self.client.get('/api/line-items/', HTTP_X_ORGANIZATION='bluebird')
        self.assertEqual([i['expected_reference'] for i in res.data], ['CC-2001'])

    def test_approving_another_orgs_match_returns_404(self):
        res = self.post(f'/api/matches/{self.northwind_match.pk}/approve/', org='bluebird')
        self.assertEqual(res.status_code, 404)

        self.northwind_match.refresh_from_db()
        self.assertEqual(self.northwind_match.status, Match.PROPOSED)
        self.assertEqual(self.line_item('CC-1003').amount_funded, Decimal('0.00'))

    def test_rejecting_or_ignoring_another_orgs_records_returns_404(self):
        txn = BankTransaction.objects.get(bank_reference='B1')
        self.assertEqual(self.post(f'/api/matches/{self.northwind_match.pk}/reject/', org='bluebird').status_code, 404)
        self.assertEqual(self.post(f'/api/transactions/{txn.pk}/ignore/', org='bluebird').status_code, 404)
        self.assertEqual(BankTransaction.objects.get(pk=txn.pk).status, BankTransaction.SUGGESTED)
