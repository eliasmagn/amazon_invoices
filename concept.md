# Concept

The Amazon Invoices project provides a desktop utility that automates the retrieval and organisation of Amazon Business invoices. The application combines a Qt-based user interface with an automated Selenium worker to authenticate against the Amazon Business reports portal, gather available invoice PDFs, and store metadata for quick reference.

Core ideas:

* Offer a simple desktop front end where business users can enter their Amazon credentials, choose download destinations, and trigger automated invoice retrievals.
* Protect sensitive credentials by encrypting them into an `.env.enc` file that only becomes a plaintext `.env` during a download session, using a salted PBKDF2-derived Fernet key to resist brute-force attacks.
* Use a background worker to navigate the Amazon reports interface, discover invoice download links, and either download the PDFs directly through Selenium or reuse the authenticated session for high-speed `requests` downloads.
* Keep both download paths aligned by parsing every PDF for totals, currency, and payment references, renaming the saved files with sanitized metadata-rich filenames, and recording the same enriched filename in the database.
* Parse downloaded PDFs to extract payment amounts and references, and persist the results in an SQLite database for quick lookup, filtering, and aggregation inside the GUI.
* Normalize localized invoice totals so both German and English number formats are interpreted consistently during parsing.
* Provide an at-a-glance summary of downloaded invoices, including search and sum features, so users can reconcile finance records without manual portal work.
* Ensure each retrieval run refreshes environment-driven credentials so updates in the GUI are respected immediately while handling save/load errors gracefully within the UI.
* Allow users to reload previously encrypted credentials and paths within the GUI so production runs never rely on mock inputs.
