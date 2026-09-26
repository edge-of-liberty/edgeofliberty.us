import unittest
from unittest.mock import MagicMock
import order_email_review as review


def raw(body):
    return ('Subject: New Order #R123\nContent-Type: text/html; charset=utf-8\n\n' + body.replace('\n', '<br>\n')).encode()


BODY = '''New order from: Example Customer
customer@example.invalid
+15555555555
VIEW ORDER
Order:
R123 |
Date:
2026-09-18
Payment Method
Pay by Cash
Special Instructions
Example booth
Order Summary
Eggs
SKU: GGS
$4.50 × 2
$9.00
Fair
SKU: 260920
$20.00
Subtotal:
$29.00
Order Total:
$29.00'''


class ReviewTests(unittest.TestCase):
    def test_multiple_items_cash_quantity_and_provenance(self):
        rows = review.parse_message('abc', '1000', raw(BODY))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][6:11], ['Eggs', 'GGS', '2', '4.50', '9.00'])
        self.assertEqual(rows[1][6:11], ['Fair', '260920', '1', '20.00', '20.00'])
        self.assertEqual(rows[0][3], 'Unpaid')
        self.assertEqual(rows[0][13], 'Example booth')
        self.assertEqual(rows[0][16], '')
        self.assertEqual(rows[0][17], 'abc')

    def test_paid_and_mismatch(self):
        rows = review.parse_message('abc', '1000', raw(BODY.replace('Pay by Cash', 'Card').replace('$9.00', '$8.00')))
        self.assertEqual(rows[0][3], 'Paid')
        self.assertIn('differs', rows[0][16])

    def test_malformed_message_kept(self):
        rows = review.parse_message('abc', None, b'broken')
        self.assertEqual(len(rows), 1)
        self.assertIn('No recognizable', rows[0][16])
        self.assertEqual(rows[0][17], 'abc')

    def test_pagination_all_mail_and_duplicate_ids(self):
        gmail = MagicMock()
        gmail.users().messages().get().execute.return_value = {'payload': {'headers': [{'name': 'Subject', 'value': 'New Order #R123'}]}}
        gmail.users().messages().list().execute.side_effect = [
            {'messages': [{'id': '1'}], 'nextPageToken': 'next'},
            {'messages': [{'id': '1'}, {'id': '2'}]}]
        self.assertEqual(review.message_ids(gmail), ['1', '2'])
        calls = gmail.users().messages().list.call_args_list[1:]
        self.assertTrue(all(c.kwargs['includeSpamTrash'] for c in calls))
        self.assertEqual(calls[-1].kwargs['pageToken'], 'next')

    def test_existing_tab_prevents_writes(self):
        sheets = MagicMock()
        sheets.spreadsheets().get().execute.return_value = {'sheets': [{'properties': {'title': review.TITLE, 'sheetId': 1}}]}
        with self.assertRaisesRegex(RuntimeError, 'already exists'):
            review.write_review(sheets, 'test', [])
        sheets.spreadsheets().batchUpdate.assert_not_called()

    def test_atomic_new_tab_only_and_literal_values(self):
        sheets = MagicMock()
        sheets.spreadsheets().get().execute.return_value = {'sheets': [{'properties': {'title': 'DOWNLOAD orders', 'sheetId': 7}}]}
        row = ['=malicious()'] + ['']*23
        sheets.spreadsheets().values().get().execute.return_value = {'values': [review.HEADERS, row]}
        sid = review.write_review(sheets, 'test', [row])
        request = sheets.spreadsheets().batchUpdate.call_args.kwargs['body']['requests']
        self.assertNotEqual(sid, 7)
        self.assertEqual(request[0]['addSheet']['properties']['title'], review.TITLE)
        cells = request[1]['updateCells']
        self.assertEqual(cells['start']['sheetId'], sid)
        self.assertEqual(cells['rows'][1]['values'][0]['userEnteredValue'], {'stringValue': '=malicious()'})
        sheets.spreadsheets().batchUpdate().execute.assert_called_once_with(num_retries=0)


if __name__ == '__main__': unittest.main()
