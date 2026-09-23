import contextlib
import bcrypt
from . import connection

def authenticate(username, password):
    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash, role, is_active, rework FROM public.app_users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()

    password_hash, tag_name, is_active, rework = row
    permission = tag_name

    if row is None:
        return None
    if not is_active:
        return "not_active"
    if not rework:
        return "no_rework"

    is_valid = bcrypt.checkpw(
        password.encode('utf-8'),
        password_hash.encode('utf-8'))
    if not is_valid:
        return None

    return permission, tag_name
