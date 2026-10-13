from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
import sqlite3
from pathlib import Path
from functools import wraps
from datetime import datetime
from decimal import Decimal, InvalidOperation
from werkzeug.security import generate_password_hash, check_password_hash
import csv
import io

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "banking.db"
app = Flask(__name__)
app.secret_key = "dev-only-change-this-secret-before-deployment"
STARTING_BALANCE = 10000.00


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                balance REAL NOT NULL DEFAULT 10000,
                successful_transactions INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                recipient TEXT,
                amount REAL NOT NULL,
                balance_after REAL NOT NULL,
                status TEXT NOT NULL,
                note TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                target REAL NOT NULL,
                saved REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        # Migrate the earlier single-account Phase 3 database if present.
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(account)").fetchall()]
        if cols:
            # Old Phase 3 database exists. It is left intact rather than mixed into a new user's account.
            pass


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def parse_amount(raw):
    try:
        amount = Decimal(raw)
        if not amount.is_finite() or amount <= 0 or amount > Decimal("1000000000"):
            return None
        return round(float(amount), 2)
    except (InvalidOperation, TypeError, ValueError):
        return None


def record_tx(conn, user_id, kind, amount, recipient, balance, status, note=""):
    conn.execute("""
        INSERT INTO transactions
        (user_id, created_at, transaction_type, recipient, amount, balance_after, status, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, datetime.now().strftime("%d %b %Y, %I:%M:%S %p"),
          kind, recipient, amount, balance, status, note))


def get_account(conn, user_id):
    return conn.execute("SELECT * FROM accounts WHERE user_id=?", (user_id,)).fetchone()


@app.route("/")
def home():
    return redirect(url_for("dashboard" if session.get("user_id") else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(name) < 2 or len(name) > 60:
            flash("Please enter a name between 2 and 60 characters.", "error")
        elif "@" not in email or len(email) > 150:
            flash("Please enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Choose a password with at least 8 characters.", "error")
        elif not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            flash("For this demo, password must include at least one letter and one number.", "error")
        elif password != confirm:
            flash("The passwords do not match. Please try again.", "error")
        else:
            try:
                with connect_db() as conn:
                    cur = conn.execute(
                        "INSERT INTO users (name,email,password_hash,created_at) VALUES (?,?,?,?)",
                        (name, email, generate_password_hash(password),
                         datetime.now().strftime("%d %b %Y, %I:%M %p"))
                    )
                    user_id = cur.lastrowid
                    conn.execute("INSERT INTO accounts (user_id,balance) VALUES (?,?)",
                                 (user_id, STARTING_BALANCE))
                session.clear()
                session["user_id"] = user_id
                session["user_name"] = name
                session["user_email"] = email
                flash("Your account is ready! Welcome to your cozy banking space. ✿", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("That email is already registered. Please sign in instead.", "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        attempts = session.get("login_attempts", 0)
        if attempts >= 5:
            flash("Too many attempts in this browser session. Please restart the session to try again.", "error")
        else:
            with connect_db() as conn:
                user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["user_name"] = user["name"]
                session["user_email"] = user["email"]
                return redirect(url_for("dashboard"))
            attempts += 1
            session["login_attempts"] = attempts
            flash(f"Email or password is incorrect. {max(0, 5-attempts)} attempt(s) left.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You are signed out. See you soon! ♡", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    with connect_db() as conn:
        account = get_account(conn, uid)
        recent = conn.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 6", (uid,)).fetchall()
        stats = conn.execute("""
          SELECT COUNT(*) total,
          SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) successful,
          SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) failed
          FROM transactions WHERE user_id=?
        """, (uid,)).fetchone()
        goals = conn.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC LIMIT 3", (uid,)).fetchall()
        total_deposits = conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND transaction_type='DEPOSIT' AND status='SUCCESS'", (uid,)).fetchone()[0]
        total_out = conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND transaction_type IN ('WITHDRAW','TRANSFER') AND status='SUCCESS'", (uid,)).fetchone()[0]
    return render_template("dashboard.html", account=account, recent=recent, stats=stats,
                           goals=goals, total_deposits=total_deposits, total_out=total_out)


@app.route("/transaction/<kind>", methods=["POST"])
@login_required
def transact(kind):
    kind = kind.lower()
    if kind not in {"deposit", "withdraw", "transfer"}:
        flash("Unknown transaction type.", "error")
        return redirect(url_for("dashboard"))
    uid = session["user_id"]
    amount = parse_amount(request.form.get("amount", ""))
    recipient = request.form.get("recipient", "").strip() if kind == "transfer" else ""
    note = request.form.get("note", "").strip()[:120]
    if amount is None:
        flash("Please enter a valid amount greater than ₹0.00.", "error")
        return redirect(url_for("dashboard"))
    if kind == "transfer" and not recipient:
        flash("Please enter the receiver name or demo account label.", "error")
        return redirect(url_for("dashboard"))
    if len(recipient) > 80:
        flash("Receiver details must be 80 characters or fewer.", "error")
        return redirect(url_for("dashboard"))
    with connect_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        account = get_account(conn, uid)
        balance = float(account["balance"])
        label = {"deposit": "DEPOSIT", "withdraw": "WITHDRAW", "transfer": "TRANSFER"}[kind]
        if kind in {"withdraw", "transfer"} and amount > balance:
            record_tx(conn, uid, label, amount, recipient, balance, "FAILED", "Insufficient balance")
            flash(f"Not enough demo balance. Available: ₹{balance:,.2f}", "error")
        else:
            new_balance = balance + amount if kind == "deposit" else balance - amount
            conn.execute("UPDATE accounts SET balance=?, successful_transactions=successful_transactions+1 WHERE user_id=?",
                         (new_balance, uid))
            record_tx(conn, uid, label, amount, recipient, new_balance, "SUCCESS", note)
            flash(f"{label.title()} successful — ₹{amount:,.2f}. ✿", "success")
    return redirect(url_for("dashboard"))


@app.route("/history")
@login_required
def history():
    uid = session["user_id"]
    search = request.args.get("q", "").strip()[:80]
    status = request.args.get("status", "").upper()
    kind = request.args.get("kind", "").upper()
    sql = "SELECT * FROM transactions WHERE user_id=?"
    params = [uid]
    if search:
        sql += " AND (transaction_type LIKE ? OR recipient LIKE ? OR note LIKE ?)"
        params.extend([f"%{search}%"] * 3)
    if status in {"SUCCESS", "FAILED"}:
        sql += " AND status=?"
        params.append(status)
    if kind in {"DEPOSIT", "WITHDRAW", "TRANSFER"}:
        sql += " AND transaction_type=?"
        params.append(kind)
    sql += " ORDER BY id DESC"
    with connect_db() as conn:
        transactions = conn.execute(sql, params).fetchall()
        account = get_account(conn, uid)
    return render_template("history.html", transactions=transactions, account=account,
                           search=search, selected_status=status, selected_kind=kind)


@app.route("/goals", methods=["GET", "POST"])
@login_required
def goals_page():
    uid = session["user_id"]
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        target = parse_amount(request.form.get("target", ""))
        if not title or len(title) > 70 or target is None:
            flash("Enter a goal name and a valid target amount.", "error")
        else:
            with connect_db() as conn:
                conn.execute("INSERT INTO goals (user_id,title,target,saved,created_at) VALUES (?,?,?,?,?)",
                             (uid, title, target, 0, datetime.now().strftime("%d %b %Y")))
            flash("Your new savings goal has been created! ✿", "success")
        return redirect(url_for("goals_page"))
    with connect_db() as conn:
        goals = conn.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    return render_template("goals.html", goals=goals)


@app.route("/goals/<int:goal_id>/add", methods=["POST"])
@login_required
def add_goal_savings(goal_id):
    uid = session["user_id"]
    amount = parse_amount(request.form.get("amount", ""))
    if amount is None:
        flash("Enter a valid amount to add to your goal.", "error")
        return redirect(url_for("goals_page"))
    with connect_db() as conn:
        goal = conn.execute("SELECT * FROM goals WHERE id=? AND user_id=?", (goal_id, uid)).fetchone()
        account = get_account(conn, uid)
        if not goal:
            flash("Savings goal not found.", "error")
        elif amount > float(account["balance"]):
            flash("You do not have enough demo balance for that amount.", "error")
        else:
            new_balance = round(float(account["balance"]) - amount, 2)
            conn.execute("UPDATE accounts SET balance=?, successful_transactions=successful_transactions+1 WHERE user_id=?", (new_balance, uid))
            conn.execute("UPDATE goals SET saved=saved+? WHERE id=? AND user_id=?", (amount, goal_id, uid))
            record_tx(conn, uid, "SAVINGS", amount, goal["title"], new_balance, "SUCCESS", "Moved into savings goal")
            flash(f"₹{amount:,.2f} added to “{goal['title']}”. This is a demo ledger entry.", "success")
    return redirect(url_for("goals_page"))


@app.route("/summary")
@login_required
def summary():
    uid = session["user_id"]
    with connect_db() as conn:
        account = get_account(conn, uid)
        rows = conn.execute("""
          SELECT transaction_type,status,COUNT(*) count,COALESCE(SUM(amount),0) total
          FROM transactions WHERE user_id=? GROUP BY transaction_type,status ORDER BY transaction_type,status
        """, (uid,)).fetchall()
        total_logs = conn.execute("SELECT COUNT(*) FROM transactions WHERE user_id=?", (uid,)).fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM transactions WHERE user_id=? AND status='FAILED'", (uid,)).fetchone()[0]
        income = conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND transaction_type='DEPOSIT' AND status='SUCCESS'", (uid,)).fetchone()[0]
        outflow = conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND transaction_type IN ('WITHDRAW','TRANSFER','SAVINGS') AND status='SUCCESS'", (uid,)).fetchone()[0]
    return render_template("summary.html", account=account, rows=rows, total_logs=total_logs, failed=failed, income=income, outflow=outflow)


@app.route("/export.csv")
@login_required
def export_csv():
    uid = session["user_id"]
    with connect_db() as conn:
        rows = conn.execute("SELECT id,created_at,transaction_type,recipient,amount,balance_after,status,note FROM transactions WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Date & Time", "Type", "Receiver", "Amount INR", "Balance After INR", "Status", "Note"])
    for row in rows:
        writer.writerow(list(row))
    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=smartbank_transactions.csv"
    return response


init_db()
if __name__ == "__main__":
    app.run(debug=True)
