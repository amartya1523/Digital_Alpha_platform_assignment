from django.test import SimpleTestCase

from recon.matching import name_found, normalize_name, normalize_reference
from recon.models import BankTransaction

from .utils import ReconTestCase


class NormalizeTests(SimpleTestCase):
    def test_normalize_reference(self):
        self.assertEqual(normalize_reference('cc-1003'), 'CC1003')
        self.assertEqual(normalize_reference(' CC 1003. '), 'CC1003')

    def test_normalize_name_drops_trailing_suffix_but_keeps_trust(self):
        self.assertEqual(normalize_name('Meridian Partners LP'), 'MERIDIAN PARTNERS')
        self.assertEqual(normalize_name('Oakridge Holdings, LLC'), 'OAKRIDGE HOLDINGS')
        self.assertEqual(normalize_name('Patel Family Trust'), 'PATEL FAMILY TRUST')

    def test_name_must_be_whole_words(self):
        self.assertTrue(name_found('Patel Family Trust', 'wire from patel-family trust'))
        self.assertFalse(name_found('Patel Family Trust', 'WIRE PATEL FAMILY TRUSTEE'))


class MatchingTestCase(ReconTestCase):
    def import_one(self, description, amount, date='2026-04-11', reference='BANK1'):
        self.upload(f'{date},{description},{amount},credit,{reference}\n')
        return BankTransaction.objects.get(bank_reference=reference)

    def proposed_refs(self, txn):
        return sorted(m.line_item.expected_reference for m in txn.matches.filter(status='proposed'))


class ReferenceMatchTests(MatchingTestCase):
    def test_full_payment_by_reference(self):
        txn = self.import_one('WIRE INCOMING RAHUL SHAH TRUST REF CC-1002', '"25,000.00"')
        self.assertEqual(txn.status, BankTransaction.SUGGESTED)
        self.assertEqual(self.proposed_refs(txn), ['CC-1002'])
        self.assertIn('Reference CC-1002 found', txn.matches.get().reason)

    def test_lowercase_reference_without_dash(self):
        txn = self.import_one('ACH CREDIT HALLER CAPITAL cc1001', '27500.00')
        self.assertEqual(txn.status, BankTransaction.SUGGESTED)
        self.assertEqual(self.proposed_refs(txn), ['CC-1001'])

    def test_partial_payment(self):
        txn = self.import_one('ACH CREDIT HALLER CAPITAL LLC CC-1001', '20000.00')
        self.assertEqual(txn.status, BankTransaction.SUGGESTED)
        self.assertEqual(self.proposed_refs(txn), ['CC-1001'])
        self.assertIn('partial', txn.matches.get().reason)

    def test_reference_in_bank_reference_column(self):
        txn = self.import_one('INCOMING WIRE', '1000.00', reference='CC-1004-PART')
        self.assertEqual(self.proposed_refs(txn), ['CC-1004'])

    def test_more_than_one_reference_proposes_all(self):
        txn = self.import_one('WIRE CC-1001 AND CC-1002', '1000.00')
        self.assertEqual(txn.status, BankTransaction.NEEDS_REVIEW)
        self.assertEqual(self.proposed_refs(txn), ['CC-1001', 'CC-1002'])

    def test_reference_wins_over_name(self):
        # name says Patel, but the reference points to Meridian, step 3 is skipped
        txn = self.import_one('PATEL FAMILY TRUST CC-1004', '12500.00')
        self.assertEqual(self.proposed_refs(txn), ['CC-1004'])

    def test_line_item_called_after_transaction_date_is_not_eligible(self):
        txn = self.import_one('WIRE OAKRIDGE HOLDINGS LLC REF CC-1006', '15000.00', date='2026-03-20')
        self.assertEqual(txn.status, BankTransaction.NEEDS_REVIEW)
        self.assertEqual(txn.matches.count(), 0)

    def test_other_org_reference_is_not_matched(self):
        txn = self.import_one('WIRE INCOMING CEDAR GROVE FUND CC-2001', '40000.00')
        self.assertEqual(txn.status, BankTransaction.NEEDS_REVIEW)
        self.assertEqual(txn.matches.count(), 0)


class OverpaymentTests(MatchingTestCase):
    def test_overpayment_needs_review_with_no_match(self):
        txn = self.import_one('WIRE INCOMING PATEL FAMILY TRUST CC-1003', '13000.00')
        self.assertEqual(txn.status, BankTransaction.NEEDS_REVIEW)
        self.assertEqual(txn.matches.count(), 0)
        self.assertIn('overpayment', txn.review_reason)


class NameAndAmountTests(MatchingTestCase):
    def test_name_and_amount_match(self):
        txn = self.import_one('WIRE INCOMING PATEL FAMILY TRUST', '12500.00')
        self.assertEqual(txn.status, BankTransaction.SUGGESTED)
        self.assertEqual(self.proposed_refs(txn), ['CC-1003'])

    def test_name_without_suffix_and_messy_spacing(self):
        txn = self.import_one('"  wire incoming meridian partners  "', '15000.00')
        self.assertEqual(self.proposed_refs(txn), ['CC-1004'])

    def test_more_than_one_candidate_needs_review(self):
        txn = self.import_one('WIRE INCOMING OAKRIDGE HOLDINGS LLC', '15000.00')
        self.assertEqual(txn.status, BankTransaction.NEEDS_REVIEW)
        self.assertEqual(self.proposed_refs(txn), ['CC-1005', 'CC-1006'])
        self.assertTrue(txn.review_reason)

    def test_name_with_different_amount_needs_review(self):
        txn = self.import_one('WIRE INCOMING PATEL FAMILY TRUST', '12000.00')
        self.assertEqual(txn.status, BankTransaction.NEEDS_REVIEW)
        self.assertEqual(txn.matches.count(), 0)

    def test_unknown_wire_needs_review(self):
        txn = self.import_one('UNKNOWN INCOMING WIRE', '9999.99')
        self.assertEqual(txn.status, BankTransaction.NEEDS_REVIEW)
        self.assertEqual(txn.matches.count(), 0)
        self.assertTrue(txn.review_reason)
