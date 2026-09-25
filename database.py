import sqlite3
from datetime import datetime

DB_NAME = "finance_bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # តារាងអ្នកប្រើប្រាស់ (User Registration)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # តារាងកត់ត្រាចំណូល-ចំណាយ
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT CHECK(type IN ('income', 'expense')),
            amount REAL,
            category TEXT,
            description TEXT,
            date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    conn.commit()
    conn.close()

def register_user(user_id, username, full_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)", 
                   (user_id, username, full_name))
    conn.commit()
    conn.close()

def is_registered(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def add_transaction(user_id, trans_type, amount, category, description, date_str=None):
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO transactions (user_id, type, amount, category, description, date)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, trans_type, amount, category, description, date_str))
    trans_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trans_id

def update_transaction(trans_id, user_id, amount=None, category=None, description=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    updates = []
    params = []
    if amount is not None:
        updates.append("amount = ?")
        params.append(amount)
    if category is not None:
        updates.append("category = ?")
        params.append(category)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
        
    if not updates:
        return False
        
    params.extend([trans_id, user_id])
    query = f"UPDATE transactions SET {', '.join(updates)} WHERE id = ? AND user_id = ?"
    cursor.execute(query, params)
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def delete_transaction(trans_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (trans_id, user_id))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def get_report(user_id, start_date, end_date):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT type, category, SUM(amount), COUNT(id)
        FROM transactions
        WHERE user_id = ? AND date BETWEEN ? AND ?
        GROUP BY type, category
    """, (user_id, start_date, end_date))
    rows = cursor.fetchall()
    conn.close()
    return rows

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
