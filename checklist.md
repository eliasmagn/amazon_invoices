# Project Checklist

## ✅ Completed
- [x] Design Qt-based interface for entering Amazon Business credentials and options.
- [x] Implement encrypted storage for credentials via `.env.enc` and runtime `.env` handling.
- [x] Automate Amazon Business invoice retrieval with Selenium and optional headless mode.
- [x] Parse downloaded PDFs to capture totals and payment references for database storage.
- [x] Display downloaded invoices in a searchable, sortable table with running total.
- [x] Reload worker environment configuration on every run so GUI updates take effect immediately.

## 🔄 In Progress / Planned
- [ ] Provide packaged application binaries for Windows/macOS/Linux users.
- [ ] Add automated tests or CI pipeline to catch regressions in GUI and worker logic.
- [ ] Support multi-factor authentication flows beyond the current username/password login.
- [ ] Improve error messaging and localisation for non-German language settings.
- [ ] Allow manual refresh of Amazon authentication cookies without a full relogin.
- [ ] Document the database schema and provide migration tooling for future changes.
- [ ] Add export options (CSV/Excel) for downloaded invoice metadata.
