"""Report export as Markdown and PDF."""
import io
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

FONTS = Path(__file__).resolve().parent / 'fonts'
REGULAR, BOLD = 'Helvetica', 'Helvetica-Bold'
if (FONTS / 'Montserrat-Regular.ttf').exists():
    pdfmetrics.registerFont(TTFont('SermonRegular', str(FONTS / 'Montserrat-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('SermonBold', str(FONTS / 'Montserrat-Bold.ttf')))
    REGULAR, BOLD = 'SermonRegular', 'SermonBold'

LABELS = {
    'en': {'central': 'Central message', 'summary': 'Summary', 'scripture': 'Scripture', 'points': 'Main points',
           'quotes': 'Key quotes', 'applications': 'Application', 'prayer': 'Prayer points',
           'questions': 'Discussion questions', 'note': 'Note on the transcript', 'translation': 'Full text',
           'preacher': 'Preacher', 'generated': 'Created with Sermon Intelligence (AI-assisted) — please review before publishing.'},
    'fr': {'central': 'Message central', 'summary': 'Résumé', 'scripture': 'Écritures', 'points': 'Points principaux',
           'quotes': 'Citations clés', 'applications': 'Application', 'prayer': 'Sujets de prière',
           'questions': 'Questions de discussion', 'note': 'Remarque sur la transcription', 'translation': 'Texte intégral',
           'preacher': 'Prédicateur', 'generated': 'Créé avec Sermon Intelligence (assisté par IA) — à relire avant publication.'},
    'de': {'central': 'Kernbotschaft', 'summary': 'Zusammenfassung', 'scripture': 'Bibelstellen', 'points': 'Hauptpunkte',
           'quotes': 'Kernzitate', 'applications': 'Anwendung', 'prayer': 'Gebetsanliegen',
           'questions': 'Fragen für Kleingruppen', 'note': 'Hinweis zum Transkript', 'translation': 'Volltext',
           'preacher': 'Prediger', 'generated': 'Erstellt mit Sermon Intelligence (KI-gestützt) – bitte vor Veröffentlichung prüfen.'},
}


def _date(value: str) -> str:
    try:
        return datetime.strptime(value[:10], '%Y-%m-%d').strftime('%d.%m.%Y')
    except ValueError:
        return value


def markdown(sermon: dict, report: dict, language: str, translation: str | None = None) -> str:
    t = LABELS[language]
    meta = ' · '.join(x for x in (_date(sermon['sermon_date']), sermon.get('preacher') and f"{t['preacher']}: {sermon['preacher']}") if x)
    out = [f"# {report['title']}", f'_{meta}_', '', f"## {t['central']}", report['central_message'], '',
           f"## {t['summary']}", report['summary'], '']
    if report['scripture_references']:
        out += [f"## {t['scripture']}", *[f"- **{s['reference']}** — {s['context']}" for s in report['scripture_references']], '']
    if report['main_points']:
        out.append(f"## {t['points']}")
        for i, p in enumerate(report['main_points'], 1):
            refs = f" _({', '.join(p['scriptures'])})_" if p['scriptures'] else ''
            out += [f"### {i}. {p['heading']}{refs}", p['explanation'], '']
    for key, label in (('key_quotes', 'quotes'), ('applications', 'applications'), ('prayer_points', 'prayer'),
                       ('discussion_questions', 'questions')):
        if report[key]:
            bullet = '> ' if key == 'key_quotes' else '- '
            out += [f'## {t[label]}', *[bullet + item for item in report[key]], '']
    if report['transcript_quality_note']:
        out += [f"_{t['note']}: {report['transcript_quality_note']}_", '']
    if translation:
        out += [f"## {t['translation']}", translation, '']
    out += ['---', f"_{t['generated']}_", '']
    return '\n'.join(out)


def pdf(sermon: dict, report: dict, language: str, translation: str | None = None) -> bytes:
    t = LABELS[language]
    navy, blue, muted = HexColor('#0b2a55'), HexColor('#1764d8'), HexColor('#5f7593')
    body = ParagraphStyle('body', fontName=REGULAR, fontSize=10.5, leading=15.5, textColor=HexColor('#15304f'), spaceAfter=6)
    styles = {
        'title': ParagraphStyle('title', parent=body, fontName=BOLD, fontSize=22, leading=27, textColor=navy, spaceAfter=4),
        'meta': ParagraphStyle('meta', parent=body, textColor=muted, fontSize=10, spaceAfter=14),
        'h2': ParagraphStyle('h2', parent=body, fontName=BOLD, fontSize=13.5, leading=18, textColor=blue, spaceBefore=12, spaceAfter=6),
        'h3': ParagraphStyle('h3', parent=body, fontName=BOLD, fontSize=11, leading=15, textColor=navy, spaceBefore=6, spaceAfter=3),
        'lead': ParagraphStyle('lead', parent=body, fontName=BOLD, fontSize=11.5, leading=17, textColor=navy),
        'quote': ParagraphStyle('quote', parent=body, leftIndent=10, textColor=HexColor('#3c5577'), borderPadding=(0, 0, 0, 6)),
        'small': ParagraphStyle('small', parent=body, fontSize=8.5, textColor=muted),
    }

    def p(text, style='body'):
        return Paragraph(escape(str(text)).replace('\n', '<br/>'), styles.get(style, body))

    def bullets(items):
        return ListFlowable([ListItem(p(i), leftIndent=12, value='•') for i in items], bulletType='bullet', start='•', leftIndent=12)

    meta = ' · '.join(x for x in (_date(sermon['sermon_date']), sermon.get('preacher') and f"{t['preacher']}: {sermon['preacher']}") if x)
    story = [p(report['title'], 'title'), p(meta, 'meta'),
             p(t['central'], 'h2'), p(report['central_message'], 'lead'),
             p(t['summary'], 'h2'), *[p(par) for par in report['summary'].split('\n\n') if par.strip()]]
    if report['scripture_references']:
        story += [p(t['scripture'], 'h2'), bullets(f"{s['reference']} — {s['context']}" for s in report['scripture_references'])]
    if report['main_points']:
        story.append(p(t['points'], 'h2'))
        for i, point in enumerate(report['main_points'], 1):
            refs = f" ({', '.join(point['scriptures'])})" if point['scriptures'] else ''
            story += [p(f"{i}. {point['heading']}{refs}", 'h3'), p(point['explanation'])]
    if report['key_quotes']:
        story += [p(t['quotes'], 'h2'), *[p(f'“{q}”', 'quote') for q in report['key_quotes']]]
    for key, label in (('applications', 'applications'), ('prayer_points', 'prayer'), ('discussion_questions', 'questions')):
        if report[key]:
            story += [p(t[label], 'h2'), bullets(report[key])]
    if report['transcript_quality_note']:
        story += [Spacer(1, 8), p(f"{t['note']}: {report['transcript_quality_note']}", 'small')]
    if translation:
        story += [p(t['translation'], 'h2'), *[p(par) for par in translation.split('\n\n') if par.strip()]]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(REGULAR, 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(18 * mm, 10 * mm, t['generated'])
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, str(doc.page))
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=report['title'], author=sermon.get('preacher') or 'CMGI')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
