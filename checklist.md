# Project Checklist

## ✅ Completed
- [x] Design Qt-based interface for entering Amazon Business credentials and options.
- [x] Implement encrypted storage for credentials via `.env.enc` and runtime `.env` handling.
- [x] Load existing encrypted credentials and paths directly in the Qt frontend.
- [x] Automate Amazon Business invoice retrieval with Selenium and optional headless mode.
- [x] Parse downloaded PDFs to capture totals and payment references for database storage.
- [x] Display downloaded invoices in a searchable table with running total.
- [x] Reload worker environment configuration on every run so GUI updates take effect immediately.
- [x] Harden amount parsing with locale-aware normalization and doctest coverage for German and English formats.
- [x] Strengthen encrypted configuration storage with salted PBKDF2 key derivation and surfaced save/load errors in the GUI.
- [x] Replace brittle Selenium sleeps with DOM-aware waits and sanitize generated filenames for cross-platform safety.
- [x] Resolve user-supplied paths like `~/Downloads` and create missing directories before the worker connects to SQLite or writes invoices.
- [x] Close the GUI usability gaps by enabling table sorting, persisting the log history, localising totals, hardening amount parsing, and deduplicating invoice downloads.
- [x] Document the database schema and add versioned migrations that preserve legacy invoice data.
## 🔄 In Progress / Planned
- [ ] Provide packaged application binaries for Windows/macOS/Linux users.
- [ ] Add automated tests or CI pipeline to catch regressions in GUI and worker logic.
- [ ] Support multi-factor authentication flows beyond the current username/password login.
- [ ] Improve error messaging and localisation for non-German language settings.
- [ ] Allow manual refresh of Amazon authentication cookies without a full relogin.
- [ ] Add export options (CSV/Excel) for downloaded invoice metadata.

## 🐞 Known Issues To Fix
- [ ] (Keine offenen Fehler nach aktuellem Stand dokumentiert.)

## 🧪 Manual Regression Tests
- [ ] Run a browser-mode download after a requests-mode download using the same invoice and confirm that both saved filenames include amount, currency, and payment reference metadata.
