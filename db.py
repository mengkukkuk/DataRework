import contextlib
import os

import bcrypt
import psycopg2

#DB_HOST = "26.252.139.132"
DB_HOST = "localhost"
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASSWORD = os.environ.get("DB_PASSWORD", "P@ssw0rd")

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )

def verify_user(username, password):
    with contextlib.closing(get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password FROM public.users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()

    if row is None:
        return False

    password = row[0]
    if not password:
        return False
    return password

    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except (ValueError, TypeError):
        return False
