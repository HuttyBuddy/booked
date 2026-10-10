"""SQLite storage for Booked: conversations and bookings."""
import sqlite3
import threading
import time

DB = "booked.db"
_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS conversations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business TEXT, started_at REAL, summary TEXT DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conv_id INTEGER, role TEXT, content TEXT, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS bookings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conv_id INTEGER, customer_name TEXT DEFAULT '', customer_phone TEXT DEFAULT '',
            slot TEXT DEFAULT '', amount_usd TEXT DEFAULT '',
            paypal_order_id TEXT DEFAULT '', deposit_status TEXT DEFAULT 'none',
            created_at REAL)""")


def new_conversation(business: str) -> int:
    with _lock, _conn() as c:
        cur = c.execute("INSERT INTO conversations(business, started_at) VALUES(?,?)",
                        (business, time.time()))
        return cur.lastrowid


def add_message(conv_id: int, role: str, content: str):
    with _lock, _conn() as c:
        c.execute("INSERT INTO messages(conv_id, role, content, ts) VALUES(?,?,?,?)",
                  (conv_id, role, content, time.time()))


def new_booking(conv_id: int, amount_usd: str) -> int:
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO bookings(conv_id, amount_usd, deposit_status, created_at) VALUES(?,?,?,?)",
            (conv_id, amount_usd, "pending", time.time()))
        return cur.lastrowid


def update_booking(booking_id: int, **fields):
    sets = ", ".join(f"{k}=?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE bookings SET {sets} WHERE id=?", (*fields.values(), booking_id))


def get_booking(booking_id: int):
    with _lock, _conn() as c:
        return c.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()


def find_booking_by_order(order_id: str):
    with _lock, _conn() as c:
        return c.execute("SELECT * FROM bookings WHERE paypal_order_id=?", (order_id,)).fetchone()


def recent_conversations(limit: int = 20):
    with _lock, _conn() as c:
        return c.execute(
            "SELECT * FROM conversations ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()


def recent_bookings(limit: int = 20):
    with _lock, _conn() as c:
        return c.execute(
            """SELECT b.*, conv.business FROM bookings b
               JOIN conversations conv ON conv.id=b.conv_id
               ORDER BY b.created_at DESC LIMIT ?""", (limit,)).fetchall()


def conversation_messages(conv_id: int):
    with _lock, _conn() as c:
        return c.execute(
            "SELECT role, content FROM messages WHERE conv_id=? ORDER BY ts", (conv_id,)).fetchall()
