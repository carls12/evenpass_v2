"""Outgoing email over SMTP (e.g. Brevo, Gmail app password, church mail server).

Mail is optional: without EVENTPASS_SMTP_HOST and EVENTPASS_MAIL_FROM nothing is sent and
registration works as before (badge download on the success page).
"""
import os, smtplib, ssl
from email.message import EmailMessage
from email.utils import make_msgid

SMTP_HOST = os.getenv('EVENTPASS_SMTP_HOST', '').strip()
SMTP_PORT = int(os.getenv('EVENTPASS_SMTP_PORT', '587'))
SMTP_USER = os.getenv('EVENTPASS_SMTP_USER', '').strip()
SMTP_PASSWORD = os.getenv('EVENTPASS_SMTP_PASSWORD', '')
SMTP_SECURITY = os.getenv('EVENTPASS_SMTP_SECURITY', 'starttls').lower()  # starttls | ssl | none
MAIL_FROM = os.getenv('EVENTPASS_MAIL_FROM', '').strip()  # e.g. "CMGI EventPass <events@example.org>"
MAIL_REPLY_TO = os.getenv('EVENTPASS_MAIL_REPLY_TO', '').strip()


def enabled():
    return bool(SMTP_HOST and MAIL_FROM)


def build(to, subject, text, html, attachments=(), inline_png=None):
    """attachments: (filename, bytes, maintype, subtype); inline_png is referenced as cid:qr in the html."""
    msg = EmailMessage()
    msg['From'] = MAIL_FROM
    msg['To'] = to
    msg['Subject'] = subject
    msg['Message-ID'] = make_msgid(domain=MAIL_FROM.rsplit('@', 1)[-1].strip('> ') or None)
    if MAIL_REPLY_TO: msg['Reply-To'] = MAIL_REPLY_TO
    msg.set_content(text)
    msg.add_alternative(html, subtype='html')
    if inline_png:
        msg.get_payload()[1].add_related(inline_png, 'image', 'png', cid='<qr>', filename='qr.png')
    for name, data, maintype, subtype in attachments:
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return msg


def deliver(msg):
    context = ssl.create_default_context()
    if SMTP_SECURITY == 'ssl':
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    with server:
        if SMTP_SECURITY == 'starttls': server.starttls(context=context)
        if SMTP_USER: server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
