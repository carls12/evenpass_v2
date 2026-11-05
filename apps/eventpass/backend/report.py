"""Event analysis: who registered, who came on which day, by category -- on screen, as Excel and as PDF."""
import io
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta

PLACEHOLDER_EMAIL = '@eventpass.invalid'  # people added by hand without an email address


def _days(start, end):
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return []
    if last < first or (last - first).days > 60: last = first
    return [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]


def natural(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', text or '')]


def _rate(part, whole):
    return round(100 * part / whole) if whole else 0


def analysis(c, event_id):
    """All numbers of one event; None if it does not exist."""
    event = c.execute('SELECT id,title,location,start_date,end_date,fields FROM events WHERE id=?', (event_id,)).fetchone()
    if not event: return None
    people = c.execute('SELECT id,name,email,category,meal,answers,created_at FROM participants WHERE event_id=?',
                       (event_id,)).fetchall()
    people = sorted(people, key=lambda p: natural(p['name']))  # "Teilnehmer 2" before "Teilnehmer 10"
    scans = c.execute('''SELECT ch.participant_id,ch.day,ch.scanned_at,p.name,p.category FROM checkins ch
                         JOIN participants p ON p.id=ch.participant_id WHERE ch.event_id=? ORDER BY ch.scanned_at''',
                      (event_id,)).fetchall()
    attended = {}
    for s in scans: attended.setdefault(s['participant_id'], set()).add(s['day'])
    days = _days(event['start_date'], event['end_date'])
    for d in sorted({s['day'] for s in scans} - set(days)): days.append(d)  # scans outside the planned dates
    total = len(people)
    came = sum(1 for p in people if p['id'] in attended)
    per_day = [{'day': d, 'count': sum(1 for p in people if d in attended.get(p['id'], ())),} for d in days]
    for row in per_day: row['rate'] = _rate(row['count'], total)

    def grouped(key):
        out = {}
        for p in people:
            g = out.setdefault((p[key] or '–').strip() or '–', {'registered': 0, 'checked_in': 0})
            g['registered'] += 1
            g['checked_in'] += p['id'] in attended
        return [{'name': k, **v, 'rate': _rate(v['checked_in'], v['registered'])}
                for k, v in sorted(out.items(), key=lambda kv: (-kv[1]['registered'], kv[0]))]

    signups = Counter((p['created_at'] or '')[:10] for p in people)
    fields = [f['label'] for f in json.loads(event['fields'] or '[]')]
    rows = []
    for p in people:
        answers = json.loads(p['answers'] or '{}')
        rows.append({'name': p['name'], 'email': '' if p['email'].endswith(PLACEHOLDER_EMAIL) else p['email'],
                     'category': p['category'], 'meal': p['meal'], 'answers': answers,
                     'registered_at': (p['created_at'] or '')[:16].replace('T', ' '),
                     'days': [d in attended.get(p['id'], ()) for d in days],
                     'days_attended': len(attended.get(p['id'], ()))})
    extra = sorted({k for r in rows for k in r['answers']} - set(fields))  # answers to questions removed later
    return {
        'event': {'title': event['title'], 'location': event['location'], 'start_date': event['start_date'], 'end_date': event['end_date']},
        'registered': total, 'checked_in': came, 'not_checked_in': total - came, 'rate': _rate(came, total),
        'days': days, 'per_day': per_day,
        'by_category': grouped('category'), 'by_meal': grouped('meal'),
        'signups_by_date': [{'date': d, 'count': n} for d, n in sorted(signups.items()) if d],
        'questions': fields + extra, 'participants': rows,
        'checkins': [{'name': s['name'], 'category': s['category'], 'day': s['day'], 'time': (s['scanned_at'] or '')[11:16]} for s in scans],
    }


def _safe(value):
    """No formulas from typed answers in Excel."""
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def _show(day):
    try: return datetime.strptime(day, '%Y-%m-%d').strftime('%d.%m.%Y')
    except ValueError: return day


def excel(data):
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    blue, light = PatternFill('solid', fgColor='1764D8'), PatternFill('solid', fgColor='E6F0FF')
    head_font, title_font = Font(bold=True, color='FFFFFF'), Font(bold=True, size=16, color='113F76')
    wb = Workbook()

    def header(ws, row, values):
        for i, v in enumerate(values, 1):
            cell = ws.cell(row=row, column=i, value=v)
            cell.fill, cell.font = blue, head_font
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    def widths(ws, values):
        for i, w in enumerate(values, 1): ws.column_dimensions[get_column_letter(i)].width = w

    # ---- Overview ----
    ws = wb.active; ws.title = 'Übersicht'
    e = data['event']
    ws['A1'] = e['title']; ws['A1'].font = title_font
    ws['A2'] = f"{_show(e['start_date'])} – {_show(e['end_date'])} · {e['location']}"
    ws['A3'] = f"Erstellt am {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    stats = [('Angemeldet', data['registered']), ('Eingecheckt (mind. 1 Tag)', data['checked_in']),
             ('Nicht erschienen', data['not_checked_in']), ('Teilnahmequote', f"{data['rate']} %")]
    for i, (label, value) in enumerate(stats, 5):
        ws.cell(row=i, column=1, value=label).font = Font(bold=True)
        ws.cell(row=i, column=2, value=value).fill = light
    r = 10
    ws.cell(row=r, column=1, value='Anwesenheit pro Tag').font = Font(bold=True, size=12, color='113F76')
    header(ws, r + 1, ['Tag', 'Eingecheckt', 'Quote (%)'])
    for i, d in enumerate(data['per_day'], r + 2):
        ws.cell(row=i, column=1, value=_show(d['day'])); ws.cell(row=i, column=2, value=d['count']); ws.cell(row=i, column=3, value=d['rate'])
    day_end = r + 1 + len(data['per_day'])
    if data['per_day']:
        chart = BarChart(); chart.title = 'Eingecheckt pro Tag'; chart.y_axis.title = 'Personen'; chart.legend = None
        chart.add_data(Reference(ws, min_col=2, min_row=r + 1, max_row=day_end), titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=r + 2, max_row=day_end))
        chart.height, chart.width = 7, 14
        ws.add_chart(chart, 'F5')
    r = max(day_end + 2, 26)
    for title, key in (('Nach Kategorie / Rolle', 'by_category'), ('Nach Verpflegung', 'by_meal')):
        ws.cell(row=r, column=1, value=title).font = Font(bold=True, size=12, color='113F76')
        header(ws, r + 1, ['Gruppe', 'Angemeldet', 'Eingecheckt', 'Quote (%)'])
        for i, g in enumerate(data[key], r + 2):
            for col, v in enumerate((_safe(g['name']), g['registered'], g['checked_in'], g['rate']), 1): ws.cell(row=i, column=col, value=v)
        r += len(data[key]) + 3
    ws.cell(row=r, column=1, value='Anmeldungen pro Tag').font = Font(bold=True, size=12, color='113F76')
    header(ws, r + 1, ['Datum', 'Neue Anmeldungen'])
    for i, s in enumerate(data['signups_by_date'], r + 2):
        ws.cell(row=i, column=1, value=_show(s['date'])); ws.cell(row=i, column=2, value=s['count'])
    widths(ws, [30, 16, 14, 12])

    # ---- Participants (one column per event day) ----
    ws = wb.create_sheet('Teilnehmer')
    cols = ['Name', 'E-Mail', 'Kategorie', 'Verpflegung', *data['questions'], 'Registriert am',
            *[_show(d) for d in data['days']], 'Tage anwesend']
    header(ws, 1, cols)
    for i, p in enumerate(data['participants'], 2):
        values = [p['name'], p['email'], p['category'], p['meal'], *(p['answers'].get(q, '') for q in data['questions']),
                  p['registered_at'], *('✓' if x else '–' for x in p['days']), p['days_attended']]
        for col, v in enumerate(values, 1): ws.cell(row=i, column=col, value=v if isinstance(v, int) else _safe(v))
    ws.freeze_panes = 'B2'
    ws.auto_filter.ref = ws.dimensions
    widths(ws, [26, 28, 14, 14, *([18] * len(data['questions'])), 17, *([11] * len(data['days'])), 13])

    # ---- Check-in log ----
    ws = wb.create_sheet('Check-ins')
    header(ws, 1, ['Name', 'Kategorie', 'Tag', 'Uhrzeit (UTC)'])
    for i, s in enumerate(data['checkins'], 2):
        for col, v in enumerate((_safe(s['name']), _safe(s['category']), _show(s['day']), s['time']), 1): ws.cell(row=i, column=col, value=v)
    ws.freeze_panes = 'A2'
    widths(ws, [28, 16, 14, 14])

    out = io.BytesIO(); wb.save(out)
    return out.getvalue()


def pdf(data, font_bold='Helvetica-Bold', font_regular='Helvetica'):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    W, H = A4
    buf = io.BytesIO(); pdf = canvas.Canvas(buf, pagesize=A4)
    e = data['event']
    pdf.setTitle(f"Auswertung {e['title']}")
    blue, ink, muted, light = HexColor('#1764D8'), HexColor('#15304F'), HexColor('#5F7593'), HexColor('#E6F0FF')

    def new_page():
        pdf.setFillColor(blue); pdf.rect(0, H - 92, W, 92, stroke=0, fill=1)
        pdf.setFillColor(HexColor('#FFFFFF')); pdf.setFont(font_bold, 18)
        pdf.drawString(40, H - 50, e['title'][:60])
        pdf.setFont(font_regular, 10)
        pdf.drawString(40, H - 70, f"Auswertung · {_show(e['start_date'])} – {_show(e['end_date'])} · {e['location'][:60]}")
        pdf.drawRightString(W - 40, H - 70, datetime.now().strftime('%d.%m.%Y %H:%M'))
        return H - 120

    y = new_page()
    # key numbers
    boxes = [('Angemeldet', data['registered']), ('Eingecheckt', data['checked_in']),
             ('Nicht erschienen', data['not_checked_in']), ('Quote', f"{data['rate']} %")]
    bw = (W - 80 - 3 * 10) / 4
    for i, (label, value) in enumerate(boxes):
        x = 40 + i * (bw + 10)
        pdf.setFillColor(light); pdf.roundRect(x, y - 58, bw, 58, 8, stroke=0, fill=1)
        pdf.setFillColor(blue); pdf.setFont(font_bold, 20); pdf.drawString(x + 12, y - 30, str(value))
        pdf.setFillColor(muted); pdf.setFont(font_regular, 9); pdf.drawString(x + 12, y - 47, label)
    y -= 86

    def bars(title, items, label_key, value_key, total, y):
        """Horizontal bars; returns the new y. Long lists continue on a new page."""
        pdf.setFillColor(ink); pdf.setFont(font_bold, 12); pdf.drawString(40, y, title); y -= 18
        for item in items:
            if y < 70: pdf.showPage(); y = new_page(); pdf.setFillColor(ink); pdf.setFont(font_bold, 12); pdf.drawString(40, y, title + ' (Forts.)'); y -= 18
            value = item[value_key]
            pdf.setFillColor(ink); pdf.setFont(font_regular, 9); pdf.drawString(40, y, str(item[label_key])[:28])
            width = (W - 300) * (value / total if total else 0)
            pdf.setFillColor(light); pdf.rect(200, y - 2, W - 300, 11, stroke=0, fill=1)
            pdf.setFillColor(blue); pdf.rect(200, y - 2, max(width, 1), 11, stroke=0, fill=1)
            pdf.setFillColor(ink); pdf.drawString(W - 92, y, f"{value}" + (f"  ({item['rate']} %)" if 'rate' in item else ''))
            y -= 17
        return y - 14

    y = bars('Anwesenheit pro Tag', [{**d, 'label': _show(d['day'])} for d in data['per_day']], 'label', 'count', data['registered'], y)
    y = bars('Eingecheckt nach Kategorie / Rolle', data['by_category'], 'name', 'checked_in',
             max((g['registered'] for g in data['by_category']), default=0), y)
    if any(g['name'] != '–' for g in data['by_meal']):
        y = bars('Verpflegung (angemeldet)', data['by_meal'], 'name', 'registered', data['registered'], y)
    if data['signups_by_date']:
        y = bars('Neue Anmeldungen pro Tag', [{**s, 'label': _show(s['date'])} for s in data['signups_by_date'][-14:]], 'label', 'count',
                 max(s['count'] for s in data['signups_by_date']), y)

    # list of people (name, category, days)
    pdf.showPage(); y = new_page()
    pdf.setFillColor(ink); pdf.setFont(font_bold, 12); pdf.drawString(40, y, 'Teilnehmerliste'); y -= 20
    day_cols = data['days'][:8]
    def row_header(y):
        pdf.setFillColor(muted); pdf.setFont(font_bold, 8)
        pdf.drawString(40, y, 'NAME'); pdf.drawString(250, y, 'KATEGORIE')
        for i, d in enumerate(day_cols): pdf.drawString(340 + i * 28, y, _show(d)[:5])
        return y - 14
    y = row_header(y)
    for p in data['participants']:
        if y < 50: pdf.showPage(); y = row_header(new_page())
        pdf.setFillColor(ink); pdf.setFont(font_regular, 9)
        pdf.drawString(40, y, p['name'][:38]); pdf.drawString(250, y, str(p['category'])[:16])
        for i, here in enumerate(p['days'][:8]):
            x = 346 + i * 28
            if here:  # drawn tick: the fonts have no check mark glyph
                pdf.setStrokeColor(HexColor('#1F7A52')); pdf.setLineWidth(1.6)
                pdf.line(x, y + 3, x + 3, y); pdf.line(x + 3, y, x + 9, y + 7)
            else:
                pdf.setFillColor(HexColor('#B6BEC8')); pdf.drawString(x + 2, y, '–')
        y -= 14
    pdf.showPage(); pdf.save()
    return buf.getvalue()
