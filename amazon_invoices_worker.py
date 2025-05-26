#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Amazon B2B Invoice Downloader – Worker Script
"""

import os
import re
import io
import time
import logging
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from selenium.common.exceptions import ElementClickInterceptedException
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pdfminer.high_level import extract_text

###############################################################################
# Argument-Parsing
###############################################################################
parser = argparse.ArgumentParser(
    description="Amazon B2B-Rechnungen automatisch herunterladen"
)
parser.add_argument("--browser", action="store_true",
                    help="PDFs per Chrome-Download statt per requests laden")
parser.add_argument("--no-headless", action="store_true",
                    help="Browserfenster anzeigen")
args = parser.parse_args()
USE_REQUESTS = not args.browser

###############################################################################
# Konfiguration & Logging
###############################################################################
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")

load_dotenv()
USER, PW = os.getenv("AMZ_USER"), os.getenv("AMZ_PW")
if not USER or not PW:
    raise SystemExit("Bitte AMZ_USER und AMZ_PW in der .env setzen")

DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR") or "invoices")
DOWNLOAD_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.getenv("DB_PATH") or "invoices.db")

REPORT_URL = (
    "https://www.amazon.de/b2b/aba/reports"
    "?reportType=items_report_1"
    "&dateSpanSelection=PAST_12_WEEKS"
    "&ref=hpr_redirect_report"
    "&language=de-DE"
)

###############################################################################
# Datenbankfunktionen
###############################################################################
def _schema_current(conn: sqlite3.Connection) -> bool:
    cur = conn.execute("PRAGMA table_info(invoices)")
    cols = {row[1] for row in cur.fetchall()}
    expected = {
        "invoice_id", "filename", "amount",
        "currency", "payment_ref", "downloaded_at",
    }
    return expected.issubset(cols)

def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)

    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='invoices'"
    )
    exists = cur.fetchone() is not None

    if exists and not _schema_current(conn):
        logging.warning(
            "Altes Rechnungs-Tabellenschema erkannt – wird zu "
            "'invoices_legacy' umbenannt."
        )
        conn.execute("ALTER TABLE invoices RENAME TO invoices_legacy")
        exists = False

    if not exists:
        conn.execute(
            """
            CREATE TABLE invoices (
                invoice_id      TEXT PRIMARY KEY,
                filename        TEXT NOT NULL,
                amount          REAL,
                currency        TEXT,
                payment_ref     TEXT,
                downloaded_at   TEXT NOT NULL
            )
            """
        )
        conn.commit()
        logging.info("Invoice-Tabelle angelegt (aktuelles Schema).")
    return conn

def is_already_downloaded(conn: sqlite3.Connection, invoice_id: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM invoices WHERE invoice_id = ? LIMIT 1", (invoice_id,)
    )
    return cur.fetchone() is not None

def mark_as_downloaded(
    conn: sqlite3.Connection,
    invoice_id: str,
    filename: str,
    amount: float | None,
    currency: str | None,
    payment_ref: str | None,
):
    conn.execute(
        """
        INSERT OR IGNORE INTO invoices
        (invoice_id, filename, amount, currency, payment_ref, downloaded_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            invoice_id,
            filename,
            amount,
            currency,
            payment_ref,
            datetime.utcnow().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()

###############################################################################
# Selenium Setup
###############################################################################
options = webdriver.ChromeOptions()
if not args.no_headless:
    options.add_argument("--headless=new")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")

if not USE_REQUESTS:  # Browser-Download braucht Download-Prefs
    prefs = {
        "download.default_directory": str(DOWNLOAD_DIR.resolve()),
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    }
    options.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 120)

###############################################################################
# Web-Hilfsfunktionen
###############################################################################
def login_if_needed() -> None:
    driver.get(REPORT_URL)
    if "ap/signin" not in driver.current_url:
        logging.info("Bereits eingeloggt.")
        return
    logging.info("Login erforderlich.")
    wait.until(EC.presence_of_element_located((By.ID, "ap_email"))).send_keys(USER)
    driver.find_element(By.ID, "continue").click()
    wait.until(EC.presence_of_element_located((By.ID, "ap_password"))).send_keys(PW)
    driver.find_element(By.ID, "signInSubmit").click()
    wait.until(EC.url_contains("/b2b/aba/reports"))
    logging.info("Login erfolgreich.")

def extract_links_current_page() -> list[str]:
    time.sleep(15)
    html = driver.page_source
    hrefs = re.findall(r'href="(/b2b/aba/receipt/v2/[^\"]+\.pdf)"', html)
    base = "https://www.amazon.de"
    return [base + h for h in hrefs]

def collect_links_all_pages(conn: sqlite3.Connection) -> list[str]:
    all_new_links: list[str] = []
    page = 1
    next_btn_locator = (By.CSS_SELECTOR, 'button[data-testid="next-button"]')

    while True:
        time.sleep(8)
        logging.info("Scanne Seite %d …", page)
        links = extract_links_current_page()
        for url in links:
            invoice_id = Path(url).stem
            if is_already_downloaded(conn, invoice_id):
                logging.debug("%s bereits vorhanden – übersprungen", invoice_id)
            else:
                all_new_links.append(url)
        next_btn = wait.until(EC.presence_of_element_located(next_btn_locator))
        disabled = (
            next_btn.get_attribute("disabled") is not None
            or next_btn.get_attribute("status") == "disabled"
        )
        if disabled:
            logging.info("Letzte Seite erreicht.")
            break
        try:
            wait.until(EC.element_to_be_clickable(next_btn_locator)).click()
        except ElementClickInterceptedException:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", next_btn
            )
            driver.execute_script("arguments[0].click();", next_btn)
        page += 1
        time.sleep(2)
    return sorted(all_new_links)

###############################################################################
# PDF-Parsing-Funktionen
###############################################################################
AMOUNT_PATTERNS = [
    re.compile(r"Zahlbetrag\s+([\d.,]+)\s*€", re.I),
    re.compile(r"Total\s+Amount[^\d]*([\d.,]+)", re.I),
]

PAYMENT_REF_PATTERNS = [
    re.compile(r"Zahlungsreferenznummer\s+(\S+)", re.I),
    re.compile(r"Payment\s+Reference\s+Number\s*[:#]?\s*(\S+)", re.I),
]

def parse_pdf_info(pdf_bytes: bytes) -> tuple[float | None, str | None, str | None]:
    try:
        text = extract_text(io.BytesIO(pdf_bytes))
    except Exception as exc:
        logging.warning("PDF-Text konnte nicht extrahiert werden: %s", exc)
        return None, None, None
    amount_val: float | None = None
    currency: str | None = None
    payment_ref: str | None = None
    for pat in AMOUNT_PATTERNS:
        if m := pat.search(text):
            amount_str = m.group(1)
            amount_clean = amount_str.replace(".", "").replace(",", ".")
            amount_val = round(float(amount_clean), 2)
            currency = "EUR"
            break
    for pat in PAYMENT_REF_PATTERNS:
        if m := pat.search(text):
            payment_ref = m.group(1)
            break
    return amount_val, currency, payment_ref

###############################################################################
# Download-Funktionen
###############################################################################
def build_final_filename(
    invoice_id: str,
    amount: float | None,
    currency: str | None,
    payment_ref: str | None
) -> str:
    parts = [invoice_id]
    if amount is not None and currency:
        parts.append(f"{amount:0.2f}_{currency}")
    if payment_ref:
        parts.append(payment_ref)
    return "_".join(parts) + ".pdf"

def download_with_requests(conn: sqlite3.Connection, links: list[str]) -> None:
    session = requests.Session()
    for ck in driver.get_cookies():
        session.cookies.set(ck["name"], ck["value"], domain=ck.get("domain"))
    user_agent = driver.execute_script("return navigator.userAgent;")
    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
        "Referer": REPORT_URL,
        "Accept-Language": driver.execute_script("return navigator.language;"),
    })
    for url in links:
        invoice_id = Path(url).stem
        logging.info("Download (requests): %s", invoice_id)
        resp = session.get(url, stream=True)
        if resp.status_code != 200:
            logging.error("HTTP-%s bei %s", resp.status_code, url)
            continue
        data = io.BytesIO()
        for chunk in resp.iter_content(8192):
            data.write(chunk)
        data.seek(0)
        if not data.getvalue().startswith(b"%PDF"):
            logging.warning("Kein PDF-Header – übersprungen: %s", url)
            continue
        amount, currency, payment_ref = parse_pdf_info(data.getvalue())
        final_name = build_final_filename(invoice_id, amount, currency, payment_ref)
        dest_path = DOWNLOAD_DIR / final_name
        if dest_path.exists():
            logging.info("%s existiert bereits – wird übersprungen", final_name)
            mark_as_downloaded(
                conn, invoice_id, final_name, amount, currency, payment_ref
            )
            continue
        with open(dest_path, "wb") as f:
            f.write(data.getvalue())
        logging.info("Gespeichert: %s", dest_path.name)
        mark_as_downloaded(
            conn, invoice_id, final_name, amount, currency, payment_ref
        )

def download_with_browser(conn: sqlite3.Connection, links: list[str]) -> None:
    for url in links:
        invoice_id = Path(url).stem
        logging.info("Download (Browser): %s", invoice_id)
        driver.get(url)
        time.sleep(2)
        mark_as_downloaded(conn, invoice_id, f"{invoice_id}.pdf", None, None, None)

###############################################################################
# Main-Flow
###############################################################################
def main() -> None:
    conn = init_db()
    try:
        login_if_needed()
        logging.info("Bericht geöffnet – sammle neue Links …")
        links = collect_links_all_pages(conn)
        if not links:
            logging.info("Keine neuen Rechnungen gefunden – fertig.")
            return
        logging.info("Neue PDFs zum Download: %d", len(links))
        if USE_REQUESTS:
            download_with_requests(conn, links)
        else:
            download_with_browser(conn, links)
    finally:
        driver.quit()
        conn.close()

if __name__ == "__main__":
    main()
