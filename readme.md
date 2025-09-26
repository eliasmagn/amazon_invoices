# Amazon Invoices Downloader

Amazon Invoices Downloader is a desktop application that automates the retrieval and organisation of Amazon Business invoices. A PySide6 user interface lets you manage credentials, choose download destinations, and trigger the worker that navigates the Amazon Business reports portal. Downloaded PDFs are parsed for payment information and stored alongside metadata in an SQLite database for easy lookup and reconciliation.

## Features

- Securely store Amazon credentials by encrypting them into an `.env.enc` file that is only decrypted during a download run, using a salted PBKDF2-derived Fernet key for brute-force resistance.
- Headless-friendly Selenium workflow that logs into the Amazon Business reports page and discovers newly available invoice PDFs.
- Optional switch to use the active Selenium session cookies with `requests` for fast, reliable downloads.
- Automatic PDF parsing to capture totals and payment references, saved to an SQLite database with filenames sanitised for all supported operating systems.
- Smarter Selenium navigation that waits for invoice tables instead of relying on arbitrary sleep timers, increasing reliability without slowing downloads down.
- Locale-aware normalization of invoice totals so German and English formatted amounts are interpreted consistently.
- Qt-based table view that supports searching, sorting, and locale-aware running totals over the downloaded invoices.
- Reload encrypted credentials and directory settings directly within the GUI for repeated runs.
- Worker reloads environment configuration on every invocation, so updated credentials or directories entered in the GUI are used immediately.
- Scrollable log history in the GUI that preserves worker progress messages across a full download run.

## Requirements

- Python 3.11 or newer.
- Google Chrome or Chromium installed locally.
- Matching ChromeDriver available on your `PATH` (Selenium launches it automatically).
- Amazon Business account with access to the invoice reports portal.

Python dependencies are listed in `requirements.txt` and include PySide6, Selenium 4, Requests, python-dotenv, pdfminer.six, and cryptography.

## Installation

1. (Optional) Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
   ```
2. Install project dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Ensure ChromeDriver compatible with your Chrome installation is accessible. You can manage this manually or via tools like `webdriver-manager`.

## Usage

1. Launch the GUI:
   ```bash
   python amazon_invoices_gui_qt.py
   ```
2. Enter your Amazon Business username and password. Choose the download directory for PDFs and the SQLite database file used for metadata. Paths may include `~` to reference your home directory; the worker expands them and creates missing folders automatically before a run.
3. Provide an encryption password. Credentials and settings are encrypted into `.env.enc` and only decrypted into a temporary `.env` file during downloads.
4. If you already have an `.env.enc`, click **Konfiguration laden** to decrypt and prefill the stored credentials, directory, and database path. The entered password is reused for the next download run.
5. (Optional) Enable **Per Browser herunterladen (--browser)** to force Selenium to perform the PDF downloads directly. Enable **Browserfenster anzeigen (--no-headless)** if you need to watch the automated browser.
6. Click **Download starten**. The worker logs into Amazon Business, discovers new invoice links, downloads PDF files, parses totals and payment references, renames the PDFs with that metadata, and stores the enriched filenames and metadata in the SQLite database.
7. Use **Datenbank neu laden** or the search field to refresh and filter the table. The **Summe** label shows the total of the currently displayed invoices.

The GUI deletes the temporary `.env` file when the worker finishes. Existing `invoices.db` files will be migrated automatically if an outdated schema is detected; older data is preserved by renaming the legacy table.

## Data Storage

- **PDF files** are saved to the configured download directory, defaulting to `invoices/`.
- **Metadata** is stored in the configured SQLite database. The `invoices` table tracks invoice IDs, filenames, totals, currencies, payment references, and timestamps.
- **Credentials** are stored encrypted in `.env.enc`. Never commit this file or the decrypted `.env` to version control.

## Troubleshooting

- Verify that ChromeDriver matches your Chrome version if Selenium fails to start.
- Amazon may require multi-factor authentication or additional verification steps; these are not yet automated and may need manual intervention.
- If downloads stall, try running with the visible browser option to observe potential modal dialogs or errors.
- Use the scrolling log panel at the bottom of the GUI window to review worker status messages throughout the run.

## Known Issues

- Multi-factor authentication flows that require additional verification steps still need manual intervention.
- Packaged binaries for Windows, macOS, or Linux are not yet available; run the tool from source for now.

## Development

- The GUI emits log messages and errors through Qt signals, making it easier to adapt the interface or connect additional logging sinks.
- `amazon_invoices_worker.py` encapsulates download logic; you can run it programmatically by creating an `.env` file with the required keys (`AMZ_USER`, `AMZ_PW`, `DOWNLOAD_DIR`, `DB_PATH`) and calling `amazon_invoices_worker.run()`.
- Future enhancements and outstanding work are tracked in `checklist.md`.

## Testing

Basic doctest coverage exists for the amount normalisation helper:

```bash
python -m doctest amazon_invoices_worker.py
```

### Manual regression checklist

- Execute a run with **Per Browser herunterladen (--browser)** disabled to download via `requests`, note the metadata-enriched filename, then repeat the download with browser mode enabled and confirm the saved filename still includes the amount, currency, and payment reference.
