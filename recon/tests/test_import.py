from decimal import Decimal

from recon.models import BankTransaction

from .utils import ReconTestCase


class MissingColumnTests(ReconTestCase):
    def test_missing_column_rejects_file_and_saves_nothing(self):
        res = self.upload(
            '2026-04-03,WIRE RAHUL SHAH TRUST CC-1002,25000.00,credit\n',
            header='date,description,amount,type\n',
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('reference', res.data['detail'])
        self.assertEqual(BankTransaction.objects.count(), 0)

    def test_header_names_are_trimmed_and_case_insensitive(self):
        res = self.upload('2026-04-03,WIRE X,100.00,credit,R1\n', header=' Date , DESCRIPTION,amount,Type,reference\n')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['imported'], 1)


class RowParsingTests(ReconTestCase):
    def test_thousands_separator_is_stored_as_decimal(self):
        self.upload('2026-04-03,WIRE X,"25,000.00",credit,R1\n')
        txn = BankTransaction.objects.get(bank_reference='R1')
        txn.refresh_from_db()
        self.assertIsInstance(txn.amount, Decimal)
        self.assertEqual(txn.amount, Decimal('25000.00'))

    def test_invalid_rows_are_skipped_and_reported_with_line_numbers(self):
        rows = (
            '2026-04-03,WIRE OK,100.00,credit,R1\n'          # line 2, valid
            '2026-04-03,WIRE X,-100.00,credit,R2\n'          # line 3, credit must be positive
            '2026-04-03,FEE,25.00,debit,R3\n'                # line 4, debit must be negative
            '2026-02-30,WIRE X,100.00,credit,R4\n'           # line 5, not a real date
            '2026/04/03,WIRE X,100.00,credit,R5\n'           # line 6, wrong format
            '2026-04-03,WIRE X,0.00,credit,R6\n'             # line 7, zero
            '2026-04-03,WIRE X,abc,credit,R7\n'              # line 8, not a number
            '2026-04-03,WIRE X,100.00,refund,R8\n'           # line 9, bad type
            '2026-04-03,   ,100.00,credit,R9\n'              # line 10, no description
            '2026-04-03,WIRE X,100.00,credit,  \n'           # line 11, no reference
        )
        res = self.upload(rows)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['imported'], 1)
        self.assertEqual([e['line'] for e in res.data['errors']], [3, 4, 5, 6, 7, 8, 9, 10, 11])
        self.assertIn('positive', res.data['errors'][0]['message'])
        self.assertIn('negative', res.data['errors'][1]['message'])
        self.assertEqual(BankTransaction.objects.count(), 1)

    def test_values_are_trimmed_and_type_is_case_insensitive(self):
        res = self.upload('  2026-04-03 ,  wire x  , 100.00 , CREDIT ,  R1  \n')
        self.assertEqual(res.data['imported'], 1)
        txn = BankTransaction.objects.get()
        self.assertEqual(txn.description, 'wire x')
        self.assertEqual(txn.bank_reference, 'R1')

    def test_blank_lines_do_not_shift_line_numbers(self):
        res = self.upload('2026-04-03,WIRE X,100.00,credit,R1\n\n2026-04-31,WIRE X,100.00,credit,R2\n')
        self.assertEqual(res.data['errors'][0]['line'], 4)

    def test_debit_is_stored_as_ignored(self):
        self.upload('2026-04-05,BANK FEE,-25.00,DEBIT,FEE1\n')
        txn = BankTransaction.objects.get()
        self.assertEqual(txn.status, BankTransaction.IGNORED)
        self.assertEqual(txn.amount, Decimal('-25.00'))


class DuplicateTests(ReconTestCase):
    rows = '2026-04-03,WIRE X,100.00,credit,R1\n2026-04-04,WIRE Y,200.00,credit,R2\n'

    def test_reupload_skips_everything_as_duplicates(self):
        self.upload(self.rows)
        res = self.upload(self.rows)
        self.assertEqual(res.data['imported'], 0)
        self.assertEqual(res.data['duplicates'], 2)
        self.assertEqual(BankTransaction.objects.count(), 2)

    def test_duplicate_inside_same_file(self):
        res = self.upload(self.rows + '2026-04-03,WIRE X AGAIN,100.00,credit,R1\n')
        self.assertEqual(res.data['imported'], 2)
        self.assertEqual(res.data['duplicates'], 1)
        self.assertEqual(res.data['duplicate_rows'], [{'line': 4, 'reference': 'R1'}])

    def test_same_reference_is_allowed_in_another_org(self):
        self.upload(self.rows, org='northwind')
        res = self.upload(self.rows, org='bluebird')
        self.assertEqual(res.data['imported'], 2)
        self.assertEqual(BankTransaction.objects.count(), 4)
