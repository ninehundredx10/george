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
    def test_reflection_can_continue_but_stops_at_seven_calls(self):
        s = Memory()
        decision = {'action': 'think', 'notes': 'A question of my own.',
                    'decision_summary': 'Consider an unresolved question.', 'next_wake_hours': 3}
        with patch.object(g, 'think', return_value=decision) as think, patch.object(g, 'send'), patch.object(g, 'read_web') as read:
            g.awaken(s, True)
        self.assertEqual(think.call_count, 7)
        read.assert_not_called()
        self.assertEqual(len(s.saved[-1]['last_session']['steps']), 7)
        self.assertEqual(s.data['notes'], 'A question of my own.')

    def test_rest_remains_valid_after_one_call(self):
        s = Memory()
        with patch.object(g, 'think', return_value={'action': 'rest', 'notes': 'No current question.',
                'decision_summary': 'Nothing I want to pursue now.', 'next_wake_hours': 5}) as think:
            g.awaken(s, True)
        self.assertEqual(think.call_count, 1)
        self.assertEqual(s.data['last_session']['steps'][0]['action'], 'rest')

    def test_cap_exact_and_never_exceeded(self):
        s = Memory()
        for _ in range(100):
            self.assertTrue(g.reserve(s))
        self.assertFalse(g.reserve(s))
        self.assertEqual(s.data['ledger'][g.month()], 500)

    def test_failed_send_retains_durable_outbox(self):
        s = Memory()
        s.data['outbox'] = ['hello']
        s.save()
        with patch.object(g, 'send', side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                g.drain_outbox(s)
        self.assertEqual(s.data['outbox'], ['hello'])
        with patch.object(g, 'send'):
            g.drain_outbox(s)
        self.assertEqual(s.saved[-1]['outbox'], [])

    def test_state_encrypted_authenticated_round_trip(self):
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test-high-entropy-token',
                'GITHUB_REPOSITORY': 'example/george', 'GH_STATE_TOKEN': 'fake'}):
            from urllib.error import HTTPError
            with patch.dict(os.environ, {'ALLOW_INITIALIZE': 'true'}), patch.object(g, 'api',
                    side_effect=HTTPError('https://example.com', 404, 'missing', {}, None)):
                store = g.Store()
            plain = b'{"private":"message"}'
            encrypted = store.cipher.encrypt(plain)
            self.assertNotIn(b'message', encrypted)
            self.assertEqual(store.cipher.decrypt(encrypted), plain)
            from cryptography.fernet import InvalidToken
            with self.assertRaises(InvalidToken):
                store.cipher.decrypt(encrypted[:-3] + b'xxx')

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

    def test_human_message_gets_receipt_without_model_call(self):
        s = Memory()
        update = {'update_id': 1, 'message': {'chat': {'id': 123, 'type': 'private'}, 'text': 'Are you there?'}}
        with patch.object(g, 'telegram', return_value=[update]), patch.object(g, 'think') as think:
            g.poll(s)
        think.assert_not_called()
        self.assertIn('Are you there?', s.saved[-1]['inbox'])
        self.assertIn('Message received', s.saved[-1]['outbox'][0])

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
