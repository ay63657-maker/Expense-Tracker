from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, g
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date, datetime
import sqlite3
import os
import csv
import io
import re

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
app.config["DATABASE"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expense.db")

CATEGORIES = [
    "Food", "Transport", "Shopping", "Bills", "Education",
    "Health", "Entertainment", "Travel", "Rent", "Salary",
    "Freelance", "Investment", "Other"
]

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    conn = get_db()

    # Keep compatibility with existing database
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "created_at" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        conn.execute("UPDATE users SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            type TEXT NOT NULL CHECK(type IN ('income','expense')),
            transaction_date TEXT NOT NULL,
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            amount REAL NOT NULL DEFAULT 0 CHECK(amount >= 0),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    conn.commit()

# Ensure tables exist on application startup
with app.app_context():
    init_db()

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def get_user(user_id=None):
    user_id = user_id or session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    user = conn.execute(
        "SELECT id, name, email, created_at FROM users WHERE id=?",
        (user_id,)
    ).fetchone()
    return dict(user) if user else None

def get_summary(user_id):
    conn = get_db()
    current_month = date.today().strftime("%Y-%m")

    # All-time finances
    income_row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id=? AND type='income'",
        (user_id,)
    ).fetchone()
    income = float(income_row[0]) if income_row else 0.0

    expense_row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id=? AND type='expense'",
        (user_id,)
    ).fetchone()
    expense = float(expense_row[0]) if expense_row else 0.0

    # Current month finances (for monthly budget tracking)
    month_expense_row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id=? AND type='expense' AND substr(transaction_date, 1, 7)=?",
        (user_id, current_month)
    ).fetchone()
    month_expense = float(month_expense_row[0]) if month_expense_row else 0.0

    month_income_row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id=? AND type='income' AND substr(transaction_date, 1, 7)=?",
        (user_id, current_month)
    ).fetchone()
    month_income = float(month_income_row[0]) if month_income_row else 0.0

    budget_row = conn.execute(
        "SELECT amount FROM budgets WHERE user_id=?", (user_id,)
    ).fetchone()
    budget = float(budget_row["amount"]) if budget_row else 0.0

    balance = round(income - expense, 2)
    month_remaining = round(budget - month_expense, 2)
    used = round((month_expense / budget * 100), 1) if budget > 0 else 0.0
    budget_over = round(max(0.0, month_expense - budget), 2) if budget > 0 else 0.0

    return {
        "income": round(income, 2),
        "expense": round(expense, 2),
        "balance": balance,
        "month_income": round(month_income, 2),
        "month_expense": round(month_expense, 2),
        "budget": round(budget, 2),
        "remaining": month_remaining,
        "used": used,
        "used_bar": min(used, 100.0),
        "budget_over": budget_over,
        "current_month": current_month
    }

def get_category_data(user_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE user_id=? AND type='expense'
        GROUP BY category
        ORDER BY total DESC
    """, (user_id,)).fetchall()

    total = sum(float(row["total"]) for row in rows)
    return [
        {
            "category": row["category"],
            "total": round(float(row["total"]), 2),
            "percent": round((float(row["total"]) / total * 100), 1) if total > 0 else 0.0
        }
        for row in rows
    ]

def get_monthly_data(user_id, limit=12):
    conn = get_db()
    rows = conn.execute("""
        SELECT substr(transaction_date,1,7) AS month,
               COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE 0 END),0) AS income,
               COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END),0) AS expense
        FROM transactions
        WHERE user_id=? AND transaction_date IS NOT NULL AND transaction_date != ''
        GROUP BY month
        ORDER BY month DESC
        LIMIT ?
    """, (user_id, limit)).fetchall()
    return [
        {
            "month": r["month"],
            "income": round(float(r["income"]), 2),
            "expense": round(float(r["expense"]), 2)
        }
        for r in reversed(rows)
    ]

@app.context_processor
def inject_globals():
    return {
        "current_user": get_user(),
        "categories": CATEGORIES,
        "today": str(date.today())
    }

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill all required fields.", "error")
            return redirect(url_for("register"))
        if len(name) < 2:
            flash("Please enter a valid name (at least 2 characters).", "error")
            return redirect(url_for("register"))
        if not EMAIL_REGEX.match(email):
            flash("Please enter a valid email address.", "error")
            return redirect(url_for("register"))
        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "error")
            return redirect(url_for("register"))
        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        conn = get_db()
        exists = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()

        if exists:
            flash("Email is already registered. Please login.", "error")
            return redirect(url_for("login"))

        conn.execute(
            "INSERT INTO users(name,email,password) VALUES(?,?,?)",
            (name, email, generate_password_hash(password))
        )
        conn.commit()

        flash("Account created successfully. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

        valid = False
        if user:
            try:
                valid = check_password_hash(user["password"], password)
            except (ValueError, TypeError):
                valid = False

            # Compatibility with legacy plain-text passwords
            if not valid and user["password"] == password:
                valid = True
                conn.execute(
                    "UPDATE users SET password=? WHERE id=?",
                    (generate_password_hash(password), user["id"])
                )
                conn.commit()

        if valid:
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash("Login successful. Welcome back!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    conn = get_db()
    recent_rows = conn.execute("""
        SELECT * FROM transactions
        WHERE user_id=?
        ORDER BY transaction_date DESC, id DESC
        LIMIT 8
    """, (uid,)).fetchall()
    recent = [dict(r) for r in recent_rows]

    return render_template(
        "dashboard.html",
        summary=get_summary(uid),
        recent=recent,
        category_data=get_category_data(uid)
    )

@app.route("/transactions")
@login_required
def transactions():
    uid = session["user_id"]
    search = request.args.get("search", "").strip()
    selected_type = request.args.get("type", "all").strip().lower()
    selected_category = request.args.get("category", "all").strip()
    selected_month = request.args.get("month", "").strip()

    query = "SELECT * FROM transactions WHERE user_id=?"
    params = [uid]

    if search:
        query += " AND (title LIKE ? OR note LIKE ? OR category LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])

    if selected_type in ("income", "expense"):
        query += " AND type=?"
        params.append(selected_type)

    if selected_category in CATEGORIES:
        query += " AND category=?"
        params.append(selected_category)

    if re.match(r"^\d{4}-\d{2}$", selected_month):
        query += " AND substr(transaction_date,1,7)=?"
        params.append(selected_month)

    query += " ORDER BY transaction_date DESC, id DESC"

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    months_rows = conn.execute("""
        SELECT DISTINCT substr(transaction_date,1,7) AS month
        FROM transactions
        WHERE user_id=? AND transaction_date IS NOT NULL AND transaction_date != ''
        ORDER BY month DESC
    """, (uid,)).fetchall()

    months = [{"month": r["month"]} for r in months_rows if r["month"]]
    transactions_list = [dict(r) for r in rows]

    return render_template(
        "transactions.html",
        transactions=transactions_list,
        search=search,
        selected_type=selected_type,
        selected_category=selected_category,
        selected_month=selected_month,
        months=months
    )

@app.route("/add-transaction", methods=["GET", "POST"])
@login_required
def add_transaction():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        amount_text = request.form.get("amount", "").strip()
        ttype = request.form.get("type", "expense").strip().lower()
        tdate = request.form.get("transaction_date", "").strip() or str(date.today())
        note = request.form.get("note", "").strip()

        try:
            amount = round(float(amount_text), 2)
        except (ValueError, TypeError):
            amount = 0.0

        try:
            parsed_date = datetime.strptime(tdate, "%Y-%m-%d")
            valid_date = 1970 <= parsed_date.year <= 2100
        except ValueError:
            valid_date = False

        if not title:
            flash("Transaction title is required.", "error")
        elif amount <= 0:
            flash("Amount must be greater than zero.", "error")
        elif category not in CATEGORIES:
            flash("Please select a valid category.", "error")
        elif ttype not in ("income", "expense"):
            flash("Invalid transaction type.", "error")
        elif not valid_date:
            flash("Please select a valid date (YYYY-MM-DD).", "error")
        else:
            conn = get_db()
            conn.execute("""
                INSERT INTO transactions
                (user_id,title,category,amount,type,transaction_date,note)
                VALUES(?,?,?,?,?,?,?)
            """, (
                session["user_id"], title, category, amount,
                ttype, tdate, note
            ))
            conn.commit()
            flash("Transaction added successfully.", "success")
            return redirect(url_for("dashboard"))

    return render_template("add_transaction.html")

@app.route("/edit-transaction/<int:transaction_id>", methods=["GET", "POST"])
@login_required
def edit_transaction(transaction_id):
    conn = get_db()
    transaction_row = conn.execute("""
        SELECT * FROM transactions
        WHERE id=? AND user_id=?
    """, (transaction_id, session["user_id"])).fetchone()

    if not transaction_row:
        flash("Transaction not found.", "error")
        return redirect(url_for("transactions"))

    transaction = dict(transaction_row)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        amount_text = request.form.get("amount", "").strip()
        ttype = request.form.get("type", "expense").strip().lower()
        tdate = request.form.get("transaction_date", "").strip()
        note = request.form.get("note", "").strip()

        try:
            amount = round(float(amount_text), 2)
            valid_amount = amount > 0
        except (ValueError, TypeError):
            amount = 0.0
            valid_amount = False

        try:
            parsed_date = datetime.strptime(tdate, "%Y-%m-%d")
            valid_date = 1970 <= parsed_date.year <= 2100
        except ValueError:
            valid_date = False

        if not title:
            flash("Transaction title is required.", "error")
            return redirect(url_for("edit_transaction", transaction_id=transaction_id))
        if not valid_amount:
            flash("Amount must be greater than zero.", "error")
            return redirect(url_for("edit_transaction", transaction_id=transaction_id))
        if category not in CATEGORIES:
            flash("Please select a valid category.", "error")
            return redirect(url_for("edit_transaction", transaction_id=transaction_id))
        if ttype not in ("income", "expense"):
            flash("Invalid transaction type.", "error")
            return redirect(url_for("edit_transaction", transaction_id=transaction_id))
        if not valid_date:
            flash("Please enter a valid date (YYYY-MM-DD).", "error")
            return redirect(url_for("edit_transaction", transaction_id=transaction_id))

        conn.execute("""
            UPDATE transactions
            SET title=?, category=?, amount=?, type=?, transaction_date=?, note=?
            WHERE id=? AND user_id=?
        """, (title, category, amount, ttype, tdate, note, transaction_id, session["user_id"]))
        conn.commit()

        flash("Transaction updated successfully.", "success")
        return redirect(url_for("transactions"))

    return render_template("edit_transaction.html", transaction=transaction)

@app.post("/delete-transaction/<int:transaction_id>")
@login_required
def delete_transaction(transaction_id):
    conn = get_db()
    cursor = conn.execute(
        "DELETE FROM transactions WHERE id=? AND user_id=?",
        (transaction_id, session["user_id"])
    )
    conn.commit()

    if cursor.rowcount:
        flash("Transaction deleted successfully.", "success")
    else:
        flash("Transaction not found.", "error")

    ref = request.referrer
    if ref and (ref.startswith(request.host_url) or ref.startswith("/")):
        return redirect(ref)
    return redirect(url_for("transactions"))

@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    uid = session["user_id"]

    if request.method == "POST":
        try:
            amount = round(float(request.form.get("amount", "0")), 2)
            if amount < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Please enter a valid budget amount.", "error")
            return redirect(url_for("budget"))

        conn = get_db()
        conn.execute("""
            INSERT INTO budgets(user_id,amount)
            VALUES(?,?)
            ON CONFLICT(user_id)
            DO UPDATE SET amount=excluded.amount,
                          updated_at=CURRENT_TIMESTAMP
        """, (uid, amount))
        conn.commit()

        flash("Monthly budget updated successfully.", "success")
        return redirect(url_for("budget"))

    return render_template("budget.html", summary=get_summary(uid))

@app.route("/reports")
@login_required
def reports():
    uid = session["user_id"]
    return render_template(
        "reports.html",
        summary=get_summary(uid),
        category_data=get_category_data(uid),
        monthly=get_monthly_data(uid)
    )

@app.route("/api/chart-data")
@login_required
def chart_data():
    rows = get_monthly_data(session["user_id"])
    return jsonify({
        "months": [r["month"] for r in rows],
        "income": [r["income"] for r in rows],
        "expense": [r["expense"] for r in rows]
    })

@app.route("/export-csv")
@login_required
def export_csv():
    conn = get_db()
    rows = conn.execute("""
        SELECT title, category, amount, type, transaction_date, note
        FROM transactions
        WHERE user_id=?
        ORDER BY transaction_date DESC, id DESC
    """, (session["user_id"],)).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title", "Category", "Amount", "Type", "Date", "Note"])

    for row in rows:
        writer.writerow([
            row["title"], row["category"], row["amount"],
            row["type"], row["transaction_date"], row["note"]
        ])

    # Add UTF-8 BOM so Excel opens non-ASCII and special characters correctly
    csv_data = "\ufeff" + output.getvalue()
    response = Response(csv_data, mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=expense_report.csv"
    return response

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    uid = session["user_id"]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()

        if len(name) < 2:
            flash("Please enter a valid name (at least 2 characters).", "error")
            return redirect(url_for("profile"))
        if not EMAIL_REGEX.match(email):
            flash("Please enter a valid email address.", "error")
            return redirect(url_for("profile"))

        conn = get_db()
        duplicate = conn.execute(
            "SELECT id FROM users WHERE email=? AND id!=?",
            (email, uid)
        ).fetchone()

        if duplicate:
            flash("That email is already in use.", "error")
            return redirect(url_for("profile"))

        conn.execute(
            "UPDATE users SET name=?, email=? WHERE id=?",
            (name, email, uid)
        )
        conn.commit()
        session["user_name"] = name
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    return render_template("profile.html", user=get_user(uid))

@app.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

    valid = False
    try:
        valid = check_password_hash(user["password"], current)
    except (ValueError, TypeError):
        valid = (user["password"] == current)

    if not valid:
        flash("Current password is incorrect.", "error")
        return redirect(url_for("profile"))

    if len(new) < 6:
        flash("New password must be at least 6 characters.", "error")
        return redirect(url_for("profile"))

    if new != confirm:
        flash("New passwords do not match.", "error")
        return redirect(url_for("profile"))

    if new == current:
        flash("New password cannot be identical to the current password.", "error")
        return redirect(url_for("profile"))

    conn.execute(
        "UPDATE users SET password=? WHERE id=?",
        (generate_password_hash(new), session["user_id"])
    )
    conn.commit()

    flash("Password changed successfully.", "success")
    return redirect(url_for("profile"))

@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(error):
    return render_template("404.html"), 500

if __name__ == "__main__":
    app.run(debug=True)
