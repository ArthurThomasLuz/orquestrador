# usd_brl_email.py
# Busca cotação USD->BRL/EUR e envia por e-mail via SMTP (Simple Mail Transfer Protocol).
# Requisitos: requests
# Segredos necessários: SMTP_USER, SMTP_PASS, TO_EMAIL
# Opcional: SUBJECT_PREFIX, FROM_NAME, SMTP_HOST, SMTP_PORT
#
# Providers (nessa ordem, com fallback):
# 1) exchangerate.host
# 2) frankfurter.app
# 3) open.er-api.com

import os
import ssl
import smtplib
from email.message import EmailMessage
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

TZ = ZoneInfo("America/Sao_Paulo")

def _get(url, params=None, timeout=20):
    headers = {"User-Agent": "github-actions-usdbrl-bot/1.0"}
    r = requests.get(url, params=params or {}, timeout=timeout, headers=headers)
    # Se o site retornou erro HTML, isso já levanta exceção:
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        # Mostra início do corpo para debug
        preview = r.text[:300].replace("\n", " ")
        raise RuntimeError(f"Resposta não-JSON de {url}: {preview!r}")

def fetch_rates_exchangerate_host():
    data = _get("https://api.exchangerate.host/latest", {"base": "USD", "symbols": "BRL,EUR"})
    if "rates" not in data:
        raise KeyError("Campo 'rates' ausente em exchangerate.host")
    return data.get("date"), float(data["rates"]["BRL"]), float(data["rates"]["EUR"])

def fetch_rates_frankfurter():
    # Ex.: https://api.frankfurter.app/latest?from=USD&to=BRL,EUR
    data = _get("https://api.frankfurter.app/latest", {"from": "USD", "to": "BRL,EUR"})
    if "rates" not in data:
        raise KeyError("Campo 'rates' ausente em frankfurter.app")
    return data.get("date"), float(data["rates"]["BRL"]), float(data["rates"]["EUR"])

def fetch_rates_open_erapi():
    # Ex.: https://open.er-api.com/v6/latest/USD
    data = _get("https://open.er-api.com/v6/latest/USD")
    if data.get("result") != "success" or "rates" not in data:
        raise KeyError("Falha em open.er-api.com")
    # Não tem 'date' padronizado; usamos a string de update
    date_str = data.get("time_last_update_utc") or "unknown"
    return date_str, float(data["rates"]["BRL"]), float(data["rates"]["EUR"])

def fetch_rates():
    errors = []
    for fn in (fetch_rates_exchangerate_host, fetch_rates_frankfurter, fetch_rates_open_erapi):
        try:
            return fn()
        except Exception as e:
            errors.append(f"{fn.__name__}: {e}")
    raise RuntimeError("Falha ao obter cotações de todos os providers:\n- " + "\n- ".join(errors))

def build_email(date_str: str, usd_brl: float, usd_eur: float) -> EmailMessage:
    now = datetime.now(TZ)
    subject_prefix = os.getenv("SUBJECT_PREFIX", "").strip()
    subject = f"Cotação USD → BRL/EUR — {now.strftime('%Y-%m-%d %H:%M %Z')}"
    if subject_prefix:
        subject = f"{subject_prefix} {subject}"

    text = (
        "Cotações\n"
        f"Data base: {date_str}\n"
        f"USD→BRL: {usd_brl:.4f}\n"
        f"USD→EUR: {usd_eur:.4f}\n"
        f"Enviado em {now.isoformat(timespec='seconds')}\n"
    )
    html = f"""<html><body>
      <h3>Cotações USD</h3>
      <p><b>Data base:</b> {date_str}</p>
      <table border="1" cellpadding="6" cellspacing="0">
        <tr><th>Par</th><th>Rate</th></tr>
        <tr><td>USD→BRL</td><td>{usd_brl:.4f}</td></tr>
        <tr><td>USD→EUR</td><td>{usd_eur:.4f}</td></tr>
      </table>
      <p style="font-size:12px;color:#777">
        Enviado {now.strftime('%Y-%m-%d %H:%M %Z')}
      </p>
    </body></html>"""

    from_name = os.getenv("FROM_NAME", "USD/BRL Bot")
    from_email = os.getenv("SMTP_USER")
    to_email = os.getenv("TO_EMAIL")
    if not from_email or not to_email:
        raise RuntimeError("Defina SMTP_USER (remetente) e TO_EMAIL (destinatário) nos segredos/variáveis.")

    msg = EmailMessage()
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg

def send_email_smtp(msg: EmailMessage):
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))  # SSL
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")  # Use App Password do Gmail (2FA ativado)
    if not user or not password:
        raise RuntimeError("Defina SMTP_USER e SMTP_PASS (App Password) para enviar e-mail.")
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=context) as server:
        server.login(user, password)
        server.send_message(msg)
    print("📬 Email enviado para", msg["To"])

def main():
    date_str, usd_brl, usd_eur = fetch_rates()
    print(f"Rates OK: {date_str} | USD->BRL={usd_brl:.4f} | USD->EUR={usd_eur:.4f}")
    msg = build_email(date_str, usd_brl, usd_eur)
    send_email_smtp(msg)

if __name__ == "__main__":
    main()
