import contextlib

import bcrypt

from . import connection


def authenticate(username, password):
    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password, permission FROM public.user_access WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()

    if row is None:
        return None

    password_hash, permission = row
    if not password_hash:
        return None
    """
    # Verify cross-platform
    is_valid = bcrypt.checkpw(
        password.encode('utf-8'),
        password_hash.encode('utf-8')
    )
    """
    return permission
