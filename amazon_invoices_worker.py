# amazon_invoices_worker.py

import os
import re
import io
import time
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin


def _normalize_amount_string(amount_str: str) -> float | None:
    """Normalize a localized amount string into a float value.

    The helper keeps the final decimal separator and only removes thousands
    separators that differ from the last occurring decimal symbol. This makes
    it work for both German and English formatted totals.

    >>> _normalize_amount_string("1.234,56")
    1234.56
    >>> _normalize_amount_string("1,234.56")
    1234.56
    """

    cleaned = amount_str.strip()
    if not cleaned:
        return None

    last_comma = cleaned.rfind(",")
    last_dot = cleaned.rfind(".")
    if last_comma == -1 and last_dot == -1:
        decimal_sep = None
    elif last_comma > last_dot:
        decimal_sep = ","
    else:
        decimal_sep = "."

    if decimal_sep is None:
        normalized = cleaned.replace(",", "").replace(".", "")
    else:
        other_sep = "." if decimal_sep == "," else ","
        normalized = cleaned.replace(other_sep, "")
        normalized = normalized.replace(decimal_sep, ".")

    try:
        return float(Decimal(normalized))
    except (InvalidOperation, ValueError):
        return None

import requests
from dotenv import load_dotenv
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    WebDriverException,
)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pdfminer.high_level import extract_text

def run(
    browser=False,
    no_headless=False,
    log_callback=None
):
    """
    Main worker function.
    browser: Use browser for download (else requests)
    no_headless: Show browser window
    log_callback: function to call for log output (default: print)
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    USE_REQUESTS = not browser

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s")
    load_dotenv(dotenv_path=".env", override=True)
    USER, PW = os.getenv("AMZ_USER"), os.getenv("AMZ_PW")
    if not USER or not PW:
        log("Bitte AMZ_USER und AMZ_PW in der .env setzen")
        return

    DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR") or "invoices")
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = Path(os.getenv("DB_PATH") or "invoices.db")
    REPORT_URL = (
        "https://www.amazon.de/b2b/aba/reports"
        "?reportType=items_report_1"
        "&dateSpanSelection=PAST_12_WEEKS"
        "&ref=hpr_redirect_report"
        "&language=de-DE"
    )

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
            log("Altes Rechnungs-Tabellenschema erkannt – wird zu 'invoices_legacy' umbenannt.")
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
            log("Invoice-Tabelle angelegt (aktuelles Schema).")
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

    options = webdriver.ChromeOptions()
    if not no_headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    if not USE_REQUESTS:
        prefs = {
            "download.default_directory": str(DOWNLOAD_DIR.resolve()),
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
        }
        options.add_experimental_option("prefs", prefs)

    try:
        driver = webdriver.Chrome(options=options)
    except WebDriverException as exc:
        log(f"Chromedriver konnte nicht gestartet werden: {exc}")
        return
    wait = WebDriverWait(driver, 120)

    def login_if_needed() -> None:
        driver.get(REPORT_URL)
        if "ap/signin" not in driver.current_url:
            log("Bereits eingeloggt.")
            return
        log("Login erforderlich.")
        wait.until(EC.presence_of_element_located((By.ID, "ap_email"))).send_keys(USER)
        driver.find_element(By.ID, "continue").click()
        wait.until(EC.presence_of_element_located((By.ID, "ap_password"))).send_keys(PW)
        driver.find_element(By.ID, "signInSubmit").click()
        wait.until(EC.url_contains("/b2b/aba/reports"))
        log("Login erfolgreich.")

    PDF_LINK_LOCATOR = (By.CSS_SELECTOR, 'a[href*="/b2b/aba/receipt/v2/"][href$=".pdf"]')
    BASE_URL = "https://www.amazon.de"

    def _wait_for_pdf_links(timeout: int = 60) -> None:
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.find_elements(*PDF_LINK_LOCATOR) or "Keine Rechnungen" in d.page_source
            )
        except TimeoutException:
            logging.getLogger(__name__).warning("Keine PDF-Links innerhalb des Zeitlimits gefunden.")

    def extract_links_current_page() -> list[str]:
        _wait_for_pdf_links()
        links: list[str] = []
        for elem in driver.find_elements(*PDF_LINK_LOCATOR):
            href = (elem.get_attribute("href") or "").strip()
            if not href:
                continue
            if href.startswith("http"):
                links.append(href)
            else:
                links.append(urljoin(BASE_URL, href))
        return links

    def collect_links_all_pages(conn: sqlite3.Connection) -> list[str]:
        all_new_links: list[str] = []
        page = 1
        next_btn_locator = (By.CSS_SELECTOR, 'button[data-testid="next-button"]')

        while True:
            log(f"Scanne Seite {page} …")
            links = extract_links_current_page()
            for url in links:
                invoice_id = Path(url).stem
                if is_already_downloaded(conn, invoice_id):
                    # log(f"{invoice_id} bereits vorhanden – übersprungen")
                    pass
                else:
                    all_new_links.append(url)
            try:
                next_btn = wait.until(EC.presence_of_element_located(next_btn_locator))
            except TimeoutException:
                log("Weiter-Schaltfläche nicht gefunden – breche ab.")
                break
            disabled = (
                next_btn.get_attribute("disabled") is not None
                or next_btn.get_attribute("status") == "disabled"
            )
            if disabled:
                log("Letzte Seite erreicht.")
                break
            previous_html = driver.page_source
            try:
                wait.until(EC.element_to_be_clickable(next_btn_locator)).click()
            except TimeoutException:
                log("Weiter-Schaltfläche reagiert nicht – breche ab.")
                break
            except ElementClickInterceptedException:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", next_btn
                )
                driver.execute_script("arguments[0].click();", next_btn)
            try:
                wait.until(lambda d: d.page_source != previous_html)
            except TimeoutException:
                log("Seitenwechsel nicht erkannt – breche ab.")
                break
            page += 1
        return sorted(all_new_links)

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
            log(f"PDF-Text konnte nicht extrahiert werden: {exc}")
            return None, None, None
        amount_val: float | None = None
        currency: str | None = None
        payment_ref: str | None = None
        for pat in AMOUNT_PATTERNS:
            if m := pat.search(text):
                amount_str = m.group(1)
                normalized = _normalize_amount_string(amount_str)
                if normalized is not None:
                    amount_val = round(normalized, 2)
                    currency = "EUR"
                    break
        for pat in PAYMENT_REF_PATTERNS:
            if m := pat.search(text):
                payment_ref = m.group(1)
                break
        return amount_val, currency, payment_ref

    INVALID_FILENAME_CHARS = set('<>:"/\\|?*')

    def _sanitize_filename_part(part: str) -> str:
        cleaned = []
        for ch in part:
            if ch in INVALID_FILENAME_CHARS or ord(ch) < 32:
                cleaned.append("_")
            else:
                cleaned.append(ch)
        sanitized = "".join(cleaned)
        sanitized = re.sub(r"\s+", "_", sanitized.strip())
        sanitized = sanitized.strip(".")
        return sanitized

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
        safe_parts: list[str] = []
        for idx, raw in enumerate(parts):
            safe = _sanitize_filename_part(raw)
            if not safe:
                safe = "rechnung" if idx == 0 else "teil"
            safe_parts.append(safe[:80])
        return "_".join(safe_parts) + ".pdf"

    def download_with_requests(conn: sqlite3.Connection, links: list[str]) -> None:
        session = requests.Session()
        try:
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
                log(f"Download (requests): {invoice_id}")
                try:
                    resp = session.get(url, stream=True, timeout=60)
                except requests.RequestException as exc:
                    log(f"Download fehlgeschlagen ({exc}) – übersprungen: {url}")
                    continue
                if resp.status_code != 200:
                    log(f"HTTP-{resp.status_code} bei {url}")
                    resp.close()
                    continue
                data = io.BytesIO()
                for chunk in resp.iter_content(8192):
                    if chunk:
                        data.write(chunk)
                data.seek(0)
                resp.close()
                if not data.getvalue().startswith(b"%PDF"):
                    log(f"Kein PDF-Header – übersprungen: {url}")
                    continue
                amount, currency, payment_ref = parse_pdf_info(data.getvalue())
                final_name = build_final_filename(invoice_id, amount, currency, payment_ref)
                dest_path = DOWNLOAD_DIR / final_name
                if dest_path.exists():
                    log(f"{final_name} existiert bereits – wird übersprungen")
                    mark_as_downloaded(
                        conn, invoice_id, final_name, amount, currency, payment_ref
                    )
                    continue
                with open(dest_path, "wb") as f:
                    f.write(data.getvalue())
                log(f"Gespeichert (Requests): {dest_path.name}")
                mark_as_downloaded(
                    conn, invoice_id, final_name, amount, currency, payment_ref
                )
        finally:
            session.close()

    def _wait_for_download(invoice_id: str, before: set[str]) -> Path | None:
        deadline = time.time() + 120
        expected = DOWNLOAD_DIR / f"{invoice_id}.pdf"
        while time.time() < deadline:
            temp_path = expected.with_suffix(expected.suffix + ".crdownload")
            if temp_path.exists():
                time.sleep(0.5)
                continue
            if expected.exists() and expected.stat().st_size > 0:
                return expected
            current = {p.name: p for p in DOWNLOAD_DIR.iterdir() if p.is_file()}
            new_pdf = [
                p for name, p in current.items()
                if name not in before and p.suffix.lower() == ".pdf" and p.stat().st_size > 0
            ]
            if new_pdf:
                newest = max(new_pdf, key=lambda p: p.stat().st_mtime)
                temp = newest.with_suffix(newest.suffix + ".crdownload")
                if temp.exists():
                    time.sleep(0.5)
                    continue
                return newest
            time.sleep(0.5)
        return None

    def download_with_browser(conn: sqlite3.Connection, links: list[str]) -> None:
        for url in links:
            invoice_id = Path(url).stem
            log(f"Download (Browser): {invoice_id}")
            before = {p.name for p in DOWNLOAD_DIR.iterdir() if p.is_file()}
            try:
                driver.get(url)
            except WebDriverException as exc:
                log(f"Download im Browser fehlgeschlagen ({exc}) – übersprungen: {url}")
                continue
            downloaded = _wait_for_download(invoice_id, before)
            if downloaded is None:
                log(f"Download im Browser für {invoice_id} nicht gefunden – übersprungen")
                continue
            try:
                data = downloaded.read_bytes()
            except OSError as exc:
                log(f"PDF konnte nicht gelesen werden ({exc}) – übersprungen: {downloaded.name}")
                continue
            if not data.startswith(b"%PDF"):
                log(f"Kein PDF-Header – übersprungen: {downloaded.name}")
                try:
                    downloaded.unlink()
                except OSError:
                    pass
                continue
            amount, currency, payment_ref = parse_pdf_info(data)
            final_name = build_final_filename(invoice_id, amount, currency, payment_ref)
            dest_path = DOWNLOAD_DIR / final_name
            if dest_path.exists():
                log(f"{dest_path.name} existiert bereits – wird übersprungen")
                try:
                    if downloaded != dest_path:
                        downloaded.unlink()
                except OSError:
                    pass
                mark_as_downloaded(conn, invoice_id, dest_path.name, amount, currency, payment_ref)
                continue
            try:
                if downloaded != dest_path:
                    downloaded.rename(dest_path)
            except OSError as exc:
                log(f"Zieldatei konnte nicht erstellt werden ({exc}) – übersprungen: {downloaded.name}")
                continue
            log(f"Gespeichert (Browser): {dest_path.name}")
            mark_as_downloaded(conn, invoice_id, dest_path.name, amount, currency, payment_ref)

    # Main-Flow
    conn: sqlite3.Connection | None = None
    try:
        conn = init_db()
        login_if_needed()
        log("Bericht geöffnet – sammle neue Links …")
        links = collect_links_all_pages(conn)
        if not links:
            log("Keine neuen Rechnungen gefunden – fertig.")
            return
        log(f"Neue PDFs zum Download: {len(links)}")
        if USE_REQUESTS:
            download_with_requests(conn, links)
        else:
            download_with_browser(conn, links)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        if conn is not None:
            conn.close()
        log("Worker abgeschlossen.")
