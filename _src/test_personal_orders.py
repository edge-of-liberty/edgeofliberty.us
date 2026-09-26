import unittest
from unittest.mock import patch, MagicMock
import personal_orders as personal
import order_email_review as review

class PersonalTests(unittest.TestCase):
    def test_auth_selects_separate_files_and_readonly_scope(self):
        with patch('sys.argv', ['personal_orders.py','auth']), patch.object(personal,'get_credentials') as auth:
            personal.main()
        auth.assert_called_once_with({'account_hint':'nancy.calafati@gmail.com'}, interactive=True,
            scopes=('https://www.googleapis.com/auth/gmail.readonly',),
            token_name='token-orders-personal.json', client_name='credentials-personal.json')

    def test_exact_subject_excludes_replies_and_malformed_ids(self):
        g=MagicMock()
        g.users().messages().list().execute.return_value={'messages':[{'id':str(i)} for i in range(4)]}
        subjects=['New Order #R123','Re: New Order #R123','New Order #Rabc','New Order #R456 extra']
        g.users().messages().get().execute.side_effect=[{'payload':{'headers':[{'name':'Subject','value':s}]}} for s in subjects]
        self.assertEqual(review.message_ids(g),['0'])
        self.assertEqual(g.users().messages().list.call_args.kwargs['q'],'subject:"New Order"')

if __name__=='__main__':unittest.main()
