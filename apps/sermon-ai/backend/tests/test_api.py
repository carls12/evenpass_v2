import pytest
import ai
import main
from conftest import API, upload


def recorded(client, admin, sermon):
    for idx in (0, 1):
        for seq in range(3):
            assert upload(client, admin, sermon, idx, seq, f'{idx}-{seq};'.encode()).status_code == 200
        client.post(f'{API}/sermons/{sermon}/segments/{idx}/complete', headers=admin)
    assert client.post(f'{API}/sermons/{sermon}/finish', headers=admin, json={'duration_s': 1260}).status_code == 200


def test_health_and_auth(client, sermon):
    assert client.get(f'{API}/health').json() == {'ok': True}
    assert client.get(f'{API}/sermons').status_code == 401
    assert client.get(f'{API}/sermons/{sermon}').status_code == 401
    assert upload(client, {}, sermon, 0, 0).status_code == 401


def test_login_rate_limit(client):
    for _ in range(5):
        assert client.post(f'{API}/login', json={'password': 'nope'}).status_code == 401
    assert client.post(f'{API}/login', json={'password': 'test-admin-password'}).status_code == 429


def test_create_validation(client, admin):
    r = client.post(f'{API}/sermons', headers=admin, json={'title': 'X1', 'sermon_date': '2026-11-01', 'language': 'es'})
    assert r.status_code == 422


def test_chunk_upload_is_ordered_and_idempotent(client, admin, sermon):
    assert upload(client, admin, sermon, 0, 0, b'AA').json() == {'next_seq': 1}
    assert upload(client, admin, sermon, 0, 1, b'BB').json() == {'next_seq': 2}
    assert upload(client, admin, sermon, 0, 1, b'BB').json()['duplicate'] is True  # client retry
    assert upload(client, admin, sermon, 0, 3, b'DD').status_code == 409          # gap
    assert upload(client, admin, sermon, 0, 2, b'x', mime='text/plain').status_code == 415
    path = main.segment_path(sermon, 0, 'audio/webm')
    assert path.read_bytes() == b'AABB'
    detail = client.get(f'{API}/sermons/{sermon}', headers=admin).json()
    assert detail['segments'][0]['bytes'] == 4 and detail['status'] == 'recording'
    audio = client.get(f'{API}/sermons/{sermon}/segments/0/audio', headers=admin)
    assert audio.content == b'AABB' and audio.headers['content-type'] == 'audio/webm'


def test_chunk_size_limit(client, admin, sermon, monkeypatch):
    monkeypatch.setattr(main, 'MAX_SEGMENT_BYTES', 10)
    assert upload(client, admin, sermon, 0, 0, b'12345678').status_code == 200
    assert upload(client, admin, sermon, 0, 1, b'12345').status_code == 413


def test_finish_requires_audio_and_blocks_uploads(client, admin, sermon):
    assert client.post(f'{API}/sermons/{sermon}/finish', headers=admin, json={'duration_s': 5}).status_code == 422
    upload(client, admin, sermon, 0, 0)
    assert client.post(f'{API}/sermons/{sermon}/finish', headers=admin, json={'duration_s': 5}).status_code == 200
    assert client.post(f'{API}/sermons/{sermon}/finish', headers=admin, json={'duration_s': 5}).status_code == 200  # repeat is harmless
    assert upload(client, admin, sermon, 0, 1).status_code == 409
    assert client.post(f'{API}/sermons/{sermon}/resume', headers=admin).json() == {'next_segment': 1}
    assert upload(client, admin, sermon, 1, 0).status_code == 200


def test_full_pipeline(client, admin, sermon, offline_ai):
    recorded(client, admin, sermon)
    assert client.post(f'{API}/sermons/{sermon}/transcribe', headers=admin).status_code == 202
    detail = client.get(f'{API}/sermons/{sermon}', headers=admin).json()
    assert detail['status'] == 'transcribed'
    assert detail['transcript'] == 'text of 000.webm\n\ntext of 001.webm'
    assert offline_ai['transcribe'][1] == ('001.webm', 'audio/webm', 'en', 'text of 000.webm')  # context from part 1

    r = client.post(f'{API}/sermons/{sermon}/analyze', headers=admin, json={'languages': ['de', 'fr', 'en'], 'translate': True})
    assert r.status_code == 202
    detail = client.get(f'{API}/sermons/{sermon}', headers=admin).json()
    assert detail['status'] == 'done' and detail['error'] == ''
    assert offline_ai['report'] == ['de', 'fr', 'en']
    assert offline_ai['translate'] == ['de', 'fr']  # no translation into the sermon's own language
    kinds = sorted((o['kind'], o['language']) for o in detail['outputs'])
    assert kinds == [('report', 'de'), ('report', 'en'), ('report', 'fr'), ('translation', 'de'), ('translation', 'fr')]

    md = client.get(f'{API}/sermons/{sermon}/export/de.md', headers=admin)
    assert md.status_code == 200 and 'Kernbotschaft' in md.text and 'translated to de' in md.text
    pdf = client.get(f'{API}/sermons/{sermon}/export/fr.pdf', headers=admin)
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
    assert client.get(f'{API}/sermons/{sermon}/export/en.pdf', headers=admin).content.startswith(b'%PDF')
    assert client.get(f'{API}/sermons/{sermon}/export/en.docx', headers=admin).status_code == 404

    listed = client.get(f'{API}/sermons', headers=admin).json()
    assert next(s for s in listed if s['id'] == sermon)['report_languages']


def test_transcription_error_keeps_finished_parts(client, admin, sermon, offline_ai, monkeypatch):
    recorded(client, admin, sermon)
    calls = []

    def flaky(path, mime, language, previous_text=''):
        calls.append(path.name)
        if path.name == '001.webm' and calls.count('001.webm') == 1:
            raise ai.AIError('OpenAI rate limit or quota reached.')
        return f'ok {path.name}'

    monkeypatch.setattr(ai, 'transcribe', flaky)
    client.post(f'{API}/sermons/{sermon}/transcribe', headers=admin)
    detail = client.get(f'{API}/sermons/{sermon}', headers=admin).json()
    assert detail['status'] == 'recorded' and 'rate limit' in detail['error']
    client.post(f'{API}/sermons/{sermon}/transcribe', headers=admin)
    detail = client.get(f'{API}/sermons/{sermon}', headers=admin).json()
    assert detail['status'] == 'transcribed' and detail['error'] == ''
    assert calls == ['000.webm', '001.webm', '001.webm']  # part 0 was not paid for twice


def test_analysis_error_is_reported(client, admin, sermon, monkeypatch):
    recorded(client, admin, sermon)
    client.post(f'{API}/sermons/{sermon}/transcribe', headers=admin)

    def refuse(*args):
        raise ai.AIError('Claude declined to process this transcript.')

    monkeypatch.setattr(ai, 'generate_report', refuse)
    client.post(f'{API}/sermons/{sermon}/analyze', headers=admin, json={'languages': ['en']})
    detail = client.get(f'{API}/sermons/{sermon}', headers=admin).json()
    assert detail['status'] == 'transcribed' and 'declined' in detail['error']


def test_state_rules(client, admin, sermon):
    assert client.post(f'{API}/sermons/{sermon}/transcribe', headers=admin).status_code == 422  # no audio
    assert client.post(f'{API}/sermons/{sermon}/analyze', headers=admin, json={'languages': ['en']}).status_code == 422
    assert client.post(f'{API}/sermons/{sermon}/analyze', headers=admin, json={'languages': ['xx']}).status_code == 422
    upload(client, admin, sermon, 0, 0)
    assert client.post(f'{API}/sermons/{sermon}/transcribe', headers=admin).status_code == 409  # still recording


def test_manual_transcript_edit(client, admin, sermon):
    upload(client, admin, sermon, 0, 0)
    client.post(f'{API}/sermons/{sermon}/finish', headers=admin, json={'duration_s': 60})
    r = client.patch(f'{API}/sermons/{sermon}', headers=admin, json={'transcript': 'Corrected text', 'preacher': 'Ps. Ann'})
    assert r.status_code == 200
    detail = client.get(f'{API}/sermons/{sermon}', headers=admin).json()
    assert detail['transcript'] == 'Corrected text' and detail['status'] == 'transcribed' and detail['preacher'] == 'Ps. Ann'


def test_delete_removes_audio(client, admin, sermon):
    upload(client, admin, sermon, 0, 0)
    assert main.sermon_dir(sermon).exists()
    assert client.delete(f'{API}/sermons/{sermon}', headers=admin).status_code == 200
    assert not main.sermon_dir(sermon).exists()
    assert client.get(f'{API}/sermons/{sermon}', headers=admin).status_code == 404


def test_restart_recovers_interrupted_jobs(client, admin, sermon):
    upload(client, admin, sermon, 0, 0)
    main.set_state(sermon, status='transcribing', progress='Transcribing part 1 of 1')
    main.init()
    detail = client.get(f'{API}/sermons/{sermon}', headers=admin).json()
    assert detail['status'] == 'recorded' and 'interrupted' in detail['error']


def test_status_reports_configuration(client, admin, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'x')
    s = client.get(f'{API}/status', headers=admin).json()
    assert s['transcription_configured'] is False and s['analysis_configured'] is True
    assert s['claude_model'] == 'claude-opus-5-5'


@pytest.mark.skipif(bool(main.DATABASE_URL), reason='SQLite file test; PostgreSQL is dumped by the platform backup')
def test_backup_includes_db_and_audio(client, admin, sermon, tmp_path):
    import backup
    upload(client, admin, sermon, 0, 0, b'AUDIO')
    target = backup.backup(main.DB, main.AUDIO_DIR, tmp_path)
    assert (target / 'sermon.sqlite3').exists()
    assert (target / 'audio' / sermon / '000.webm').read_bytes() == b'AUDIO'


def recorded_parts(client, headers, parts=(8000,), title='Sunday'):
    """Sermon with uploaded parts of the given byte sizes (4000 bytes = 1 second at 32 kbit/s)."""
    sid = client.post(f'{API}/sermons', headers=headers, json={'title': title, 'sermon_date': '2026-11-01', 'language': 'en'}).json()['id']
    for idx, size in enumerate(parts):
        assert upload(client, headers, sid, idx, 0, data=b'a' * size).status_code == 200
        client.post(f'{API}/sermons/{sid}/segments/{idx}/complete', headers=headers)
    assert client.post(f'{API}/sermons/{sid}/finish', headers=headers, json={'duration_s': 1}).status_code == 200
    return sid


def test_accounts_see_only_their_own_sermons(client, admin, accounts, sermon):
    anna = accounts.add('tok-anna', 'anna')
    ben = accounts.add('tok-ben', 'ben')
    boss = accounts.add('tok-boss', 'boss', is_admin=True)
    sid = client.post(f'{API}/sermons', headers=anna, json={'title': 'Mine', 'sermon_date': '2026-11-01'}).json()['id']
    assert [s['id'] for s in client.get(f'{API}/sermons', headers=anna).json()] == [sid]
    assert client.get(f'{API}/sermons', headers=ben).json() == []
    assert client.get(f'{API}/sermons/{sid}', headers=ben).status_code == 404
    assert client.delete(f'{API}/sermons/{sid}', headers=ben).status_code == 404
    assert {sid, sermon} <= {s['id'] for s in client.get(f'{API}/sermons', headers=boss).json()}
    me = client.get(f'{API}/me', headers=anna).json()
    assert me['billed'] and me['ai_credit_seconds'] == 300 and not me['legacy']
    assert client.get(f'{API}/sermons', headers={'Authorization': 'Bearer unknown'}).status_code == 401


def test_transcription_is_booked_before_and_settled_after(client, accounts, monkeypatch):
    anna = accounts.add('tok-anna', 'anna', seconds=300)
    monkeypatch.setattr(ai, 'transcribe', lambda path, mime, lang, prev='': (f'text {path.name}', 1.2))
    sid = recorded_parts(client, anna, parts=(8000, 20000))  # estimated 2 s + 5 s
    assert client.post(f'{API}/sermons/{sid}/transcribe', headers=anna).status_code == 202
    assert client.get(f'{API}/sermons/{sid}', headers=anna).json()['status'] == 'transcribed'
    # booked 2 s and 5 s up front, OpenAI measured 1.2 s each -> 2 s rounded, so 0 and 3 s back
    assert accounts.by_id['anna']['ai_credit_seconds'] == 300 - 2 - 2
    assert [b[1] for b in accounts.bookings] == [-2, -5, 3]


def test_not_enough_minutes_is_refused_before_openai(client, accounts, offline_ai):
    anna = accounts.add('tok-anna', 'anna', seconds=60)
    sid = recorded_parts(client, anna, parts=(4000 * 90,))  # 90 seconds
    r = client.post(f'{API}/sermons/{sid}/transcribe', headers=anna)
    assert r.status_code == 402 and 'Buy more minutes' in r.json()['detail']
    assert offline_ai['transcribe'] == [] and accounts.bookings == []


def test_start_needs_enough_minutes_for_the_whole_recording(client, accounts, offline_ai):
    anna = accounts.add('tok-anna', 'anna', seconds=100)
    sid = recorded_parts(client, anna, parts=(4000 * 50, 4000 * 50))
    accounts.by_id['anna']['ai_credit_seconds'] = 60  # spent elsewhere in the meantime
    assert client.post(f'{API}/sermons/{sid}/transcribe', headers=anna).status_code == 402
    accounts.by_id['anna']['ai_credit_seconds'] = 100
    assert client.post(f'{API}/sermons/{sid}/transcribe', headers=anna).status_code == 202
    s = client.get(f'{API}/sermons/{sid}', headers=anna).json()
    assert s['status'] == 'transcribed' and accounts.by_id['anna']['ai_credit_seconds'] == 0


def test_credit_runs_out_during_the_run(client, accounts, offline_ai, monkeypatch):
    anna = accounts.add('tok-anna', 'anna', seconds=100)
    sid = recorded_parts(client, anna, parts=(4000 * 40, 4000 * 40))
    real = accounts.consume
    def consume_then_spend(uid, seconds, ref, note=''):
        result = real(uid, seconds, ref, note)
        accounts.by_id[uid]['ai_credit_seconds'] = 0  # e.g. another transcription used the rest
        return result
    monkeypatch.setattr(main.cmgi_auth, 'consume_credit', consume_then_spend)
    assert client.post(f'{API}/sermons/{sid}/transcribe', headers=anna).status_code == 202
    s = client.get(f'{API}/sermons/{sid}', headers=anna).json()
    assert s['status'] == 'recorded' and 'AI minutes are used up' in s['error']
    assert [seg['transcribed'] for seg in s['segments']] == [1, 0] and len(offline_ai['transcribe']) == 1


def test_platform_admins_and_old_sermons_are_not_billed(client, admin, accounts, sermon, offline_ai):
    boss = accounts.add('tok-boss', 'boss', seconds=0, is_admin=True)
    sid = recorded_parts(client, boss, parts=(4000 * 600,))
    assert client.post(f'{API}/sermons/{sid}/transcribe', headers=boss).status_code == 202
    assert accounts.bookings == []
