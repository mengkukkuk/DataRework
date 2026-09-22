import contextlib

import bcrypt

from . import connection

def authenticate(username, password):
    with contextlib.closing(connection.get_connection()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password, permission, tag_name, rework FROM public.user_access WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()

    password_hash, permission, tag_name, rework = row

    if password != password_hash or row is None:
        return None
    if not rework:
        return "no_rework"

    """
    is_valid = bcrypt.checkpw(
        password.encode('utf-8'),
        password_hash.encode('utf-8')
    )
    """

    return permission, tag_name
