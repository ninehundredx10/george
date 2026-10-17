import copy
import os
import unittest
from unittest.mock import patch
import george as g


class Memory:
    def __init__(self):
        self.data = {'ledger': {}, 'owner': '123', 'paused': False, 'next_wake': 0,
                     'inbox': ['hello'], 'history': [], 'notes': '', 'candidates': {}, 'offset': 0}
        self.saved = []
    def save(self):
        self.saved.append(copy.deepcopy(self.data))


class GeorgeTests(unittest.TestCase):
    def test_cap_exact_and_never_exceeded(self):
        s = Memory()
        for _ in range(100):
            self.assertTrue(g.reserve(s))
        self.assertFalse(g.reserve(s))
        self.assertEqual(s.data['ledger'][g.month()], 500)

    def test_checkpoint_failure_prevents_paid_call(self):
        s = Memory()
        with patch.object(s, 'save', side_effect=RuntimeError), patch.object(g, 'api') as api:
            with self.assertRaises(RuntimeError):
                g.think(s, {})
            api.assert_not_called()

    def test_api_failure_keeps_reservation(self):
        s = Memory()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fake'}), patch.object(g, 'api', side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                g.think(s, {})
        self.assertEqual(s.saved[-1]['ledger'][g.month()], 5)

    def test_new_month_new_bucket(self):
        s = Memory()
        s.data['ledger']['2000-01'] = 500
        self.assertTrue(g.reserve(s))
        self.assertEqual(s.data['ledger']['2000-01'], 500)

    def test_private_network_and_mixed_dns_blocked(self):
        for addr in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1'):
            with patch.object(g.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', (addr, 443))]):
                with self.assertRaises(ValueError):
                    g.public_addresses('example.com')

    def test_unsafe_url_schemes_and_credentials(self):
        for url in ('file:///etc/passwd', 'http://example.com', 'https://user:pass@example.com', 'https://example.com:8080'):
            with self.assertRaises(ValueError):
                g.read_web(url)

    def test_unpaired_and_paused_never_call_model(self):
        for owner, paused in ((None, False), ('123', True)):
            s = Memory()
            s.data.update(owner=owner, paused=paused)
            with patch.object(g, 'think') as think:
                g.awaken(s, True)
                think.assert_not_called()

    def test_unknown_chat_cannot_control_owner(self):
        s = Memory()
        update = {'update_id': 1, 'message': {'chat': {'id': 456, 'type': 'private'}, 'text': '/pause'}}
        with patch.object(g, 'telegram', return_value=[update]):
            g.poll(s)
        self.assertFalse(s.data['paused'])
        self.assertEqual(s.data['inbox'], ['hello'])

    def test_pairing_requires_code_from_authorized_dispatch(self):
        s = Memory()
        s.data.pop('owner')
        update = {'update_id': 1, 'message': {'chat': {'id': 456, 'type': 'private'}, 'text': '/start'}}
        with patch.object(g, 'telegram', return_value=[update]), patch.object(g, 'send') as send:
            g.poll(s)
            self.assertNotIn('owner', s.data)
            code = send.call_args[0][1].split()[-1]
            with self.assertRaises(RuntimeError):
                g.pair(s, 'wrong')
            g.pair(s, code)
        self.assertEqual(s.data['owner'], '456')

    def test_sleep_and_budget_notice_no_paid_requests(self):
        s = Memory()
        s.data['ledger'][g.month()] = 500
        with patch.object(g, 'send') as send, patch.object(g, 'api') as api:
            g.awaken(s, True)
            g.awaken(s, True)
            self.assertEqual(send.call_count, 1)
            api.assert_not_called()

    def test_model_cannot_raise_cap_or_execute(self):
        s = Memory()
        bad = {'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': '{"action":"execute", "cap":9999}'}]}]}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fake'}), patch.object(g, 'api', return_value=bad):
            with self.assertRaises(ValueError):
                g.think(s, {})
        self.assertEqual(g.CAP_CENTS, 500)


if __name__ == '__main__':
    unittest.main()
