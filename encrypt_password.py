"""Encrypt a database password for pasting into the external .env.

Usage:  python encrypt_password.py
Prompts without echo, then prints a DB_PASSWORD=enc:... line.
"""
import getpass
import sys

import envcrypt


def main():
    password = getpass.getpass("Database password: ")
    if not password:
        print("Empty password; nothing to encrypt.", file=sys.stderr)
        return 1
    if password != getpass.getpass("Repeat: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1
    print(f"DB_PASSWORD={envcrypt.encrypt(password)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
