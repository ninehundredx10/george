"""Read-only, no-model diagnostics. Never print memory, conversation, IDs, or keys."""
import base64
import datetime
import json
import os
import sys
import george


def inspect():
    store = george.Store()
    s = store.data
    utc = lambda value: datetime.datetime.fromtimestamp(value, datetime.timezone.utc).isoformat()
    summary = {
        'last_completed_awakening_utc': s.get('last_awake_utc'),
        'next_chosen_wake_utc': utc(s['next_wake']),
        'last_poll_utc': s.get('last_poll_utc'),
        'paused': s['paused'],
        'notes_characters': len(s['notes']),
        'conversation_entries': len(s['history']),
        'pending_inbox': len(s['inbox']),
        'pending_outbox': len(s.get('outbox', [])),
        'monthly_reserved_cents': s['ledger'].get(george.month(), 0),
    }
    base = 'https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY']
    commits = george.api(base + '/commits?path=state.enc&per_page=100', headers=store.headers)
    start = os.environ.get('INSPECT_SINCE', '2026-10-17T12:46:40Z')
    end = os.environ.get('INSPECT_UNTIL', '2026-10-17T12:47:30Z')
    selected = [c for c in commits if start <= c['commit']['committer']['date'] <= end]
    before = next((c for c in commits if c['commit']['committer']['date'] < start), None)
    snapshots = []
    for commit in ([before] if before else []) + list(reversed(selected)):
        obj = george.api(base + '/contents/state.enc?ref=' + commit['sha'], headers=store.headers)
        data = json.loads(store.cipher.decrypt(base64.b64decode(obj['content'])))
        snapshots.append((commit['commit']['committer']['date'], data))
    events = []
    for (oldtime, old), (stamp, new) in zip(snapshots, snapshots[1:]):
        ledger_delta = sum(new['ledger'].values()) - sum(old['ledger'].values())
        events.append({'checkpoint_utc': stamp,
            'new_call_reservations': ledger_delta // george.RESERVATION_CENTS,
            'notes_changed': old['notes'] != new['notes'],
            'notes_characters': len(new['notes']),
            'new_conversation_reply': new['history'] != old['history'] and
                bool(new['history']) and 'george' in new['history'][-1],
            'next_wake_changed': old['next_wake'] != new['next_wake'],
            'next_wake_utc': utc(new['next_wake'])})
    print(json.dumps({'current_state': summary, 'examined_window_utc': [start, end],
                      'checkpoint_events': events}, indent=2))
    if os.environ.get('REPORT_PUBLIC_KEY'):
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.fernet import Fernet
        public = serialization.load_pem_public_key(os.environ['REPORT_PUBLIC_KEY'].encode())
        key = Fernet.generate_key()
        report = {'current_notes': s['notes'], 'notes_snapshots':
                  [{'utc': stamp, 'notes': data['notes']} for stamp, data in snapshots]}
        payload = Fernet(key).encrypt(json.dumps(report).encode())
        wrapped = public.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                                  algorithm=hashes.SHA256(), label=None))
        envelope = json.dumps({'key': base64.b64encode(wrapped).decode(),
                               'payload': payload.decode()}).encode()
        print('SEALED_REPORT:' + base64.b64encode(envelope).decode())


if __name__ == '__main__':
    try:
        inspect()
    except Exception as exc:
        print('Inspection failed safely: ' + type(exc).__name__)
        sys.exit(1)
