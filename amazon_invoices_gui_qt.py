import sys
import os
import base64
import hashlib
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QInputDialog, QAbstractItemView, QSplitter
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
import sqlite3
from cryptography.fernet import Fernet, InvalidToken
import subprocess
import threading

ENV_ENC_FILE = ".env.enc"

def derive_key(password):
    return base64.urlsafe_b64encode(hashlib.sha256(password.encode()).digest())

def encrypt_env(data, password):
    key = derive_key(password)
    f = Fernet(key)
    return f.encrypt(data.encode())

def decrypt_env(token, password):
    key = derive_key(password)
    f = Fernet(key)
    return f.decrypt(token).decode()

def save_encrypted_env(values, password):
    text = (
        f"AMZ_USER={values['user']}\n"
        f"AMZ_PW={values['pw']}\n"
        f"DOWNLOAD_DIR={values['dir']}\n"
        f"DB_PATH={values['dbfile']}\n"
    )
    token = encrypt_env(text, password)
    with open(ENV_ENC_FILE, "wb") as f:
        f.write(token)

def load_encrypted_env(password):
    try:
        with open(ENV_ENC_FILE, "rb") as f:
            token = f.read()
        text = decrypt_env(token, password)
        return dict(line.split("=", 1) for line in text.strip().splitlines())
    except (InvalidToken, ValueError):
        QMessageBox.critical(None, "Fehler", "Falsches Passwort oder beschädigte Datei.")
        return None
    except Exception as e:
        QMessageBox.critical(None, "Fehler", str(e))
        return None

def load_invoices_from_db(db_path, search_term=None):
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    query = "SELECT invoice_id, filename, amount, currency, payment_ref, downloaded_at FROM invoices"
    params = ()
    if search_term:
        query += " WHERE invoice_id LIKE ? OR filename LIKE ? OR payment_ref LIKE ?"
        like = f"%{search_term}%"
        params = (like, like, like)
    query += " ORDER BY downloaded_at DESC"
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows

def sum_amounts_from_db(db_path, search_term=None):
    if not os.path.exists(db_path):
        return 0.0
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    query = "SELECT SUM(amount) FROM invoices"
    params = ()
    if search_term:
        query += " WHERE invoice_id LIKE ? OR filename LIKE ? OR payment_ref LIKE ?"
        like = f"%{search_term}%"
        params = (like, like, like)
    cur.execute(query, params)
    result = cur.fetchone()
    conn.close()
    return result[0] if result and result[0] else 0.0

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Amazon Invoices Downloader (Qt)")
        self.setWindowIcon(QIcon("amazon_invoices.ico") if os.path.exists("amazon_invoices.ico") else QIcon())
        self.resize(1024, 700)
        layout = QVBoxLayout(self)

        # Top Section: Credentials & Options
        form_layout = QHBoxLayout()
        self.user_edit = QLineEdit()
        self.pw_edit = QLineEdit()
        self.pw_edit.setEchoMode(QLineEdit.Password)
        self.dir_edit = QLineEdit("invoices")
        self.db_edit = QLineEdit("invoices.db")
        self.cryptpw_edit = QLineEdit()
        self.cryptpw_edit.setEchoMode(QLineEdit.Password)
        self.browser_cb = QCheckBox("Per Browser herunterladen (--browser)")
        self.headless_cb = QCheckBox("Browserfenster anzeigen (--no-headless)")

        form_layout.addWidget(QLabel("Nutzer:"))
        form_layout.addWidget(self.user_edit)
        form_layout.addWidget(QLabel("Passwort:"))
        form_layout.addWidget(self.pw_edit)
        form_layout.addWidget(QLabel("Speicherort:"))
        form_layout.addWidget(self.dir_edit)
        btn_dir = QPushButton("...")
        btn_dir.clicked.connect(self.choose_dir)
        form_layout.addWidget(btn_dir)
        form_layout.addWidget(QLabel("DB-Datei:"))
        form_layout.addWidget(self.db_edit)
        btn_db = QPushButton("...")
        btn_db.clicked.connect(self.choose_db)
        form_layout.addWidget(btn_db)
        form_layout.addWidget(QLabel("Verschl.-Passwort:"))
        form_layout.addWidget(self.cryptpw_edit)

        layout.addLayout(form_layout)
        layout.addWidget(self.browser_cb)
        layout.addWidget(self.headless_cb)

        # Actions
        actions = QHBoxLayout()
        self.btn_download = QPushButton("Download starten")
        self.btn_download.clicked.connect(self.start_download)
        actions.addWidget(self.btn_download)
        self.btn_reload = QPushButton("Datenbank neu laden")
        self.btn_reload.clicked.connect(self.reload_db)
        actions.addWidget(self.btn_reload)
        self.btn_search = QPushButton("Suche")
        self.btn_search.clicked.connect(self.search_invoices)
        self.search_edit = QLineEdit()
        actions.addWidget(QLabel("Suchbegriff:"))
        actions.addWidget(self.search_edit)
        layout.addLayout(actions)

        # Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Rechnung", "Datei", "Betrag", "Währung", "Ref", "Datum"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)

        # Sum
        self.sum_label = QLabel("Summe: 0.00 EUR")
        layout.addWidget(self.sum_label)

        # Output (Log)
        self.log_box = QLineEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        # Initial DB load
        self.reload_db()

    def choose_dir(self):
        dir_name = QFileDialog.getExistingDirectory(self, "Verzeichnis auswählen", "")
        if dir_name:
            self.dir_edit.setText(dir_name)

    def choose_db(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Datenbank auswählen", "invoices.db", "DB Dateien (*.db)")
        if file_name:
            self.db_edit.setText(file_name)

    def reload_db(self):
        db_path = self.db_edit.text()
        self.show_invoices(load_invoices_from_db(db_path))
        self.update_sum(db_path)

    def show_invoices(self, rows):
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(value) if value is not None else ""))
        self.table.resizeRowsToContents()

    def update_sum(self, db_path, search_term=None):
        total = sum_amounts_from_db(db_path, search_term)
        self.sum_label.setText(f"Summe: {total:,.2f} EUR")

    def search_invoices(self):
        search_term = self.search_edit.text()
        db_path = self.db_edit.text()
        rows = load_invoices_from_db(db_path, search_term)
        self.show_invoices(rows)
        self.update_sum(db_path, search_term)

    def start_download(self):
        user = self.user_edit.text()
        pw = self.pw_edit.text()
        directory = self.dir_edit.text() or "invoices"
        db_path = self.db_edit.text() or "invoices.db"
        cryptpw = self.cryptpw_edit.text()
        if not user or not pw or not cryptpw:
            QMessageBox.critical(self, "Fehler", "Bitte Zugangsdaten und Verschlüsselungs-Passwort eingeben.")
            return
        if not db_path.lower().endswith('.db'):
            db_path += '.db'
            self.db_edit.setText(db_path)
        save_encrypted_env({
            "user": user,
            "pw": pw,
            "dir": directory,
            "dbfile": db_path
        }, cryptpw)
        args = []
        if self.browser_cb.isChecked():
            args.append('--browser')
        if self.headless_cb.isChecked():
            args.append('--no-headless')
        self.log_box.setText("Download läuft...")
        threading.Thread(target=self.run_worker, args=(args, cryptpw), daemon=True).start()

    def run_worker(self, args, password):
        # Save .env temporarily for the worker script
        env_vars = load_encrypted_env(password)
        if not env_vars:
            self.log_box.setText("Abbruch: Passwort falsch.")
            return
        tmp_env_path = ".env"
        with open(tmp_env_path, "w", encoding="utf-8") as f:
            for k, v in env_vars.items():
                f.write(f"{k}={v}\n")
        cmd = ["python3", "amazon_invoices_worker.py"] + args
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            for line in process.stdout:
                self.log_box.setText(line.strip())
            process.wait()
        except Exception as e:
            self.log_box.setText(str(e))
        os.remove(tmp_env_path)
        self.log_box.setText("Download abgeschlossen.")
        self.reload_db()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
