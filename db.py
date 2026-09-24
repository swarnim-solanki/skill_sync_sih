import sqlite3
import hashlib
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "skillsync.db")

def _get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)

def init_db():
    """Initialize the SQLite database and create tables if they don't exist."""
    conn = _get_conn()
    with conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                metadata_json TEXT,
                status TEXT DEFAULT 'PENDING',
                proof_path TEXT
            )
        ''')
    conn.close()

def _hash_password(password):
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def register_user(name, email, password, role, metadata, proof_path=None):
    """
    Register a new user.
    Students default to 'PENDING', other roles default to 'APPROVED'.
    Returns True if successful, False if email already exists.
    """
    password_hash = _hash_password(password)
    metadata_json = json.dumps(metadata)
    
    status = 'PENDING' if role == 'Student' else 'APPROVED'
    
    conn = _get_conn()
    try:
        with conn:
            conn.execute('''
                INSERT INTO users (name, email, password_hash, role, metadata_json, status, proof_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, email, password_hash, role, metadata_json, status, proof_path))
        success = True
    except sqlite3.IntegrityError:
        # Email already exists
        success = False
    finally:
        conn.close()
        
    return success

def authenticate_user(email, password):
    """
    Authenticate a user. Returns a dictionary of user data if successful, None otherwise.
    """
    password_hash = _hash_password(password)
    
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, email, role, metadata_json, status, proof_path 
        FROM users 
        WHERE email = ? AND password_hash = ?
    ''', (email, password_hash))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

def get_pending_students():
    """Retrieve all students with status='PENDING'."""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, email, metadata_json, proof_path, status 
        FROM users 
        WHERE role = 'Student' AND status = 'PENDING'
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def approve_student(user_id):
    """Update a student's status to 'APPROVED'."""
    conn = _get_conn()
    try:
        with conn:
            conn.execute('''
                UPDATE users 
                SET status = 'APPROVED' 
                WHERE id = ?
            ''', (user_id,))
    finally:
        conn.close()

def get_user_by_id(user_id):
    """Retrieve a user by their ID."""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, email, role, metadata_json, status, proof_path 
        FROM users 
        WHERE id = ?
    ''', (user_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None
