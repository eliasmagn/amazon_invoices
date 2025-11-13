# Roadmap

## Q2 2024 – Stabilisierung und Produktivbetrieb
- ✅ Versandfertige GUI mit verschlüsselter Konfigurationsablage und Reload-Schaltfläche.
- ✅ Robuster Selenium-Worker mit optionalem Requests-Download und PDF-Parsing.
- ✅ Stärker gehärtete Konfigurationsverschlüsselung (salted PBKDF2) und UI-Fehlerbehandlung beim Speichern/Laden.
- ✅ Selenium-Navigation setzt auf DOM-Waits statt statische Sleeps und erzeugt betriebssichere Dateinamen.
- ✅ Datenbankschema dokumentiert und leichtgewichtige Migrationserläuterung ergänzt (Nutzer-FAQ weiterhin offen).
- ✅ GUI-Usability-Schulden abbauen: Tabellen-Sortierung aktivieren, Log-Historie anzeigen und Summen lokalisieren.
- ✅ Nutzerpfade wie `~/Downloads` werden automatisch aufgelöst und fehlende Verzeichnisse angelegt, sodass Downloads und Datenbankzugriffe nicht mehr scheitern.
- ✅ Rechnungsdatum automatisch aus PDFs extrahieren, lokal nachpflegen und im GUI-Datumsspaltenkopf anzeigen; Downloadzeitpunkt bleibt als separater Wert in SQLite erhalten.
- ✅ Produktnamen aus Rechnungs-PDFs extrahieren, in SQLite speichern und über die GUI-Suche auffindbar machen.
## Q3 2024 – Bedienkomfort & Zuverlässigkeit
- [ ] Paketierte Builds für Windows/macOS/Linux bereitstellen.
- [ ] Automatisierte Tests (GUI-Smoke-Tests, Worker-Integration) und CI-Pipeline aufsetzen.
- [ ] Verbesserte Fehlermeldungen und Lokalisierung für weitere Sprachen.
- [ ] Option für erneutes Laden/Refresh der Amazon-Cookies ohne kompletten Login-Lauf.

## Q4 2024 – Erweiterungen & Integrationen
- ✅ Datenbank-Schema dokumentiert und Migrationspfad mit Versionshistorie etabliert.
- [ ] Exportfunktionen (CSV/Excel) für Rechnungsmetadaten ergänzen.
- [ ] Erweiterte MFA-Unterstützung evaluieren und implementieren.
- [ ] Finanz-Reporting-APIs anbinden, sobald Grundfunktionen stabil laufen.
- 🔄 PDF-Betragserkennung für zusätzliche, bislang nicht unterstützte Formate erweitern.
