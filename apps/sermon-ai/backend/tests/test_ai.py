"""Checks the request shapes sent to Claude and OpenAI, using fake clients (no network, no cost)."""
import json
from types import SimpleNamespace as NS

import pytest

import ai
from conftest import REPORT

# The autouse fixture in conftest replaces ai.transcribe/generate_report/translate; restore the real ones here.
REAL = {name: getattr(ai, name) for name in ('transcribe', 'generate_report', 'translate')}


@pytest.fixture
def real_ai(monkeypatch):
    for name, fn in REAL.items():
        monkeypatch.setattr(ai, name, fn)


class FakeStream:
    def __init__(self, message): self.message = message
    def __enter__(self): return self
    def __exit__(self, *exc): return False
    def get_final_message(self): return self.message


def fake_anthropic(monkeypatch, text, stop_reason='end_turn'):
    sent = {}

    class Client:
        def __init__(self, **kwargs):
            self.beta = NS(messages=NS(stream=self.stream))

        def stream(self, **kwargs):
            sent.update(kwargs)
            content = [NS(type='thinking', thinking=''), NS(type='text', text=text)]
            return FakeStream(NS(stop_reason=stop_reason, content=content))

    monkeypatch.setattr(ai.anthropic, 'Anthropic', Client)
    return sent


def test_report_request_shape(real_ai, monkeypatch):
    sent = fake_anthropic(monkeypatch, json.dumps(REPORT))
    result = ai.generate_report('Long transcript', {'title': 'Sunday', 'preacher': 'Ps. Joe', 'sermon_date': '2026-11-01'}, 'fr')
    assert result == REPORT
    assert sent['model'] == 'claude-opus-5-5'
    assert sent['fallbacks'] == 'default' and sent['betas'] == ['server-side-fallback-2026-07-01']
    assert sent['thinking'] == {'type': 'adaptive'}
    assert sent['output_config']['effort'] == 'high'
    assert sent['output_config']['format']['type'] == 'json_schema'
    transcript_block, instruction = sent['messages'][0]['content']
    assert transcript_block['cache_control'] == {'type': 'ephemeral'} and 'Long transcript' in transcript_block['text']
    assert 'Ps. Joe' in transcript_block['text'] and 'French' in instruction['text']


def test_transcript_block_identical_across_languages(real_ai, monkeypatch):
    sent = fake_anthropic(monkeypatch, json.dumps(REPORT))
    meta = {'title': 'T1', 'preacher': '', 'sermon_date': '2026-11-01'}
    ai.generate_report('Same', meta, 'en'); first = sent['messages'][0]['content'][0]
    ai.translate('Same', meta, 'de'); second = sent['messages'][0]['content'][0]
    assert first == second  # cache prefix reused by every later request for the sermon


def test_translation_is_plain_text(real_ai, monkeypatch):
    sent = fake_anthropic(monkeypatch, 'Übersetzung')
    assert ai.translate('text', {}, 'de') == 'Übersetzung'
    assert 'format' not in sent['output_config'] and sent['output_config']['effort'] == 'medium'


@pytest.mark.parametrize('stop_reason, message', [('refusal', 'declined'), ('max_tokens', 'too long')])
def test_stop_reasons_become_readable_errors(real_ai, monkeypatch, stop_reason, message):
    fake_anthropic(monkeypatch, '{}', stop_reason)
    with pytest.raises(ai.AIError, match=message):
        ai.generate_report('t', {}, 'en')


def test_transcribe_request_shape(real_ai, monkeypatch, tmp_path):
    sent = {}

    class Client:
        def __init__(self, **kwargs):
            self.audio = NS(transcriptions=NS(create=self.create))

        def create(self, **kwargs):
            sent.update(kwargs, filename=kwargs['file'][0], mime=kwargs['file'][2])
            return ' Hello church \n'

    monkeypatch.setattr(ai.openai, 'OpenAI', Client)
    audio = tmp_path / '003.webm'; audio.write_bytes(b'x')
    assert ai.transcribe(audio, 'audio/webm', 'fr', 'earlier words') == 'Hello church'
    assert sent['model'] == 'whisper-1' and sent['language'] == 'fr' and sent['response_format'] == 'text'
    assert sent['filename'] == '003.webm' and sent['mime'] == 'audio/webm' and sent['prompt'].endswith('earlier words')


def test_missing_openai_key_is_a_readable_error(real_ai, monkeypatch, tmp_path):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    audio = tmp_path / '000.webm'; audio.write_bytes(b'x')
    with pytest.raises(ai.AIError, match='OpenAI'):
        ai.transcribe(audio, 'audio/webm', None)
