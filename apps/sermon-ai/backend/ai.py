"""External AI services: OpenAI for speech-to-text, Claude for reports and translations.

Kept separate from the API so tests can replace these functions without network access.
"""
import json
import os
from pathlib import Path

import anthropic
import openai

CLAUDE_MODEL = os.getenv('SERMON_CLAUDE_MODEL', 'claude-opus-5-5')
TRANSCRIBE_MODEL = os.getenv('SERMON_TRANSCRIBE_MODEL', 'whisper-1')
LANGUAGES = {'en': 'English', 'fr': 'French', 'de': 'German'}


class AIError(Exception):
    """A failure worth showing to the user as-is."""


def status():
    return {
        'transcription_configured': bool(os.getenv('OPENAI_API_KEY')),
        'analysis_configured': bool(os.getenv('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_AUTH_TOKEN')),
        'claude_model': CLAUDE_MODEL,
        'transcribe_model': TRANSCRIBE_MODEL,
    }


# ---------------------------------------------------------------- transcription

def transcribe(path: Path, mime: str, language: str | None, previous_text: str = '') -> str:
    """Transcribe one audio segment. `previous_text` keeps names and wording consistent across segments."""
    prompt = 'Christian sermon. Bible references such as John 3:16 or 1 Corinthians 13. ' + previous_text[-600:]
    try:
        client = openai.OpenAI(timeout=600, max_retries=2)
        with open(path, 'rb') as audio:
            result = client.audio.transcriptions.create(
                model=TRANSCRIBE_MODEL,
                file=(path.name, audio, mime),
                language=language or openai.NOT_GIVEN,
                prompt=prompt,
                response_format='text',
            )
    except openai.AuthenticationError:
        raise AIError('OpenAI API key is missing or invalid (OPENAI_API_KEY).')
    except openai.RateLimitError:
        raise AIError('OpenAI rate limit or quota reached. Check your OpenAI billing, then retry.')
    except openai.APIStatusError as e:
        raise AIError(f'OpenAI transcription failed ({e.status_code}): {e.message}')
    except openai.APIConnectionError:
        raise AIError('Could not reach OpenAI. Check the server internet connection and retry.')
    except openai.OpenAIError as e:  # e.g. no API key configured at all
        raise AIError(f'OpenAI is not configured: {e}')
    return (result if isinstance(result, str) else result.text).strip()


# ---------------------------------------------------------------- Claude

REPORT_SCHEMA = {
    'type': 'object',
    'properties': {
        'title': {'type': 'string'},
        'central_message': {'type': 'string'},
        'summary': {'type': 'string'},
        'scripture_references': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'reference': {'type': 'string'}, 'context': {'type': 'string'}},
            'required': ['reference', 'context'], 'additionalProperties': False}},
        'main_points': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'heading': {'type': 'string'}, 'explanation': {'type': 'string'},
                           'scriptures': {'type': 'array', 'items': {'type': 'string'}}},
            'required': ['heading', 'explanation', 'scriptures'], 'additionalProperties': False}},
        'key_quotes': {'type': 'array', 'items': {'type': 'string'}},
        'applications': {'type': 'array', 'items': {'type': 'string'}},
        'prayer_points': {'type': 'array', 'items': {'type': 'string'}},
        'discussion_questions': {'type': 'array', 'items': {'type': 'string'}},
        'transcript_quality_note': {'type': 'string'},
    },
    'required': ['title', 'central_message', 'summary', 'scripture_references', 'main_points', 'key_quotes',
                 'applications', 'prayer_points', 'discussion_questions', 'transcript_quality_note'],
    'additionalProperties': False,
}

SYSTEM = """You support the media and teaching team of a Christian church (CMGI). You work from automatic \
transcripts of sermons recorded during services. Transcripts can contain recognition errors, especially in \
names and Bible references; correct obvious ones from context, but never invent content the preacher did not say.

Write in a clear, warm and faithful register that a church member would recognise as their pastor's message."""


def _transcript_block(transcript: str, meta: dict) -> dict:
    header = '\n'.join(f'{k}: {v}' for k, v in (('Title', meta.get('title')), ('Preacher', meta.get('preacher')),
                                                ('Date', meta.get('sermon_date'))) if v)
    # Identical for every language of the same sermon, so later requests read it from the prompt cache.
    return {'type': 'text', 'text': f'<sermon>\n{header}\n\n<transcript>\n{transcript}\n</transcript>\n</sermon>',
            'cache_control': {'type': 'ephemeral'}}


def _call_claude(transcript: str, meta: dict, instruction: str, effort: str, output_format: dict | None = None) -> str:
    output_config = {'effort': effort}
    if output_format:
        output_config['format'] = output_format
    try:
        client = anthropic.Anthropic(timeout=900, max_retries=2)
        with client.beta.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=64000,
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',  # if a safety classifier declines, the API retries on a suitable model
            thinking={'type': 'adaptive'},
            output_config=output_config,
            system=SYSTEM,
            messages=[{'role': 'user', 'content': [_transcript_block(transcript, meta),
                                                   {'type': 'text', 'text': instruction}]}],
        ) as stream:
            message = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise AIError('Anthropic API key is missing or invalid (ANTHROPIC_API_KEY).')
    except anthropic.RateLimitError:
        raise AIError('Anthropic rate limit reached. Please retry in a few minutes.')
    except anthropic.APIStatusError as e:
        raise AIError(f'Claude request failed ({e.status_code}): {e.message}')
    except anthropic.APIConnectionError:
        raise AIError('Could not reach the Anthropic API. Check the server internet connection and retry.')
    except anthropic.AnthropicError as e:  # e.g. no credentials configured at all
        raise AIError(f'Claude is not configured: {e}')

    if message.stop_reason == 'refusal':
        raise AIError('Claude declined to process this transcript.')
    if message.stop_reason == 'max_tokens':
        raise AIError('The result was too long and got cut off. Try a shorter recording.')
    text = ''.join(b.text for b in message.content if b.type == 'text').strip()
    if not text:
        raise AIError('Claude returned an empty result.')
    return text


def generate_report(transcript: str, meta: dict, language: str) -> dict:
    name = LANGUAGES[language]
    instruction = f"""Write a structured report of this sermon in {name}, whatever language it was preached in.

- title: a fitting title (keep the given title if there is one, translated if needed).
- central_message: the main message in one or two sentences.
- summary: 2–4 paragraphs.
- scripture_references: every passage the preacher read or cited, with the book name in {name} and a short note on how it was used. Only passages actually mentioned.
- main_points: the sermon's points in order, each with an explanation and its scriptures.
- key_quotes: 3–6 memorable sentences, close to the preacher's words (translated if needed).
- applications, prayer_points, discussion_questions (for small groups): 3–6 each, drawn from the sermon.
- transcript_quality_note: one sentence on gaps or unclear passages in the transcript, or an empty string if it was clear."""
    text = _call_claude(transcript, meta, instruction, effort='high',
                        output_format={'type': 'json_schema', 'schema': REPORT_SCHEMA})
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise AIError('Claude returned a report that could not be read. Please retry.')


def translate(transcript: str, meta: dict, language: str) -> str:
    name = LANGUAGES[language]
    instruction = f"""Translate the complete transcript into {name}.

Keep everything the preacher said, in order, including stories, repetitions and calls to the congregation; do not summarise. \
Split the text into readable paragraphs. Render Bible quotations in the wording of a widely used {name} Bible translation. \
Output only the translation, without any introduction or notes."""
    return _call_claude(transcript, meta, instruction, effort='medium')
