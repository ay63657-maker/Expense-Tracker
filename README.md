# Expense Tracker — Professional Flask + SQLite

A complete personal finance tracker built with Python Flask and SQLite.

## Features
- Register / Login / Logout
- Password hashing
- Automatic compatibility with the original plain-text user database
- Session authentication
- Dashboard
- Add, edit and delete income/expenses
- Search and filter transactions
- Monthly filter
- Monthly budget
- Category-wise expense report
- Monthly income/expense chart
- CSV export
- Profile update
- Change password
- Responsive UI
- SQLite database

## Run on Windows

Open the project folder in VS Code.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open:

http://127.0.0.1:5000

## Important
Do NOT copy a `.venv` folder into the project. Create your own virtual environment on your computer.

The SQLite file is `expense.db`. The application creates missing tables automatically.
