# PetalBank — Smart Banking Simulator Phase 3

A cute, floral, responsive banking-simulator website built with Python, Flask, SQLite, HTML and CSS.

## Features
- User registration with a password chosen by the user
- Password hashing using Werkzeug (plain-text passwords are not stored)
- Login and logout, with limited incorrect login attempts per browser session
- Personal account and persistent SQLite balance
- Deposit, withdrawal, and transfer logging
- Timestamped successful and failed transaction records
- Searchable/filterable transaction diary
- Savings goals and demo savings contributions
- Money insights/report page
- CSV export for transaction logs
- Responsive layout, larger typography, pastel colors and floral decoration

## Run on Windows / VS Code
1. Extract this ZIP.
2. Open the `Smart_Banking_Simulator_Phase_3_Cute` folder in VS Code.
3. Open Terminal → New Terminal.
4. Run:
   ```powershell
   py -m venv .venv
   ```
5. Activate:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks it, select Command Prompt terminal and run:
   ```bat
   .venv\Scripts\activate.bat
   ```
6. Install the dependency:
   ```powershell
   python -m pip install -r requirements.txt
   ```
7. Run the website:
   ```powershell
   python app.py
   ```
8. Open http://127.0.0.1:5000 in your browser.
9. Click **Create your account**, choose your own name, email and password, then sign in.

## Data and reset
The `banking.db` SQLite database is created automatically. Users, password hashes, account balances, transactions and goals persist between app restarts. To reset all demo data, stop the server and delete `banking.db`, then restart.

## Important security note
This is a local educational simulator only. It is not connected to a real bank or payment gateway and moves no real money. Do not use a real banking password. Before public deployment, configure a strong secret via environment variables, add CSRF protection, rate limiting and production server settings, and conduct a security review.
