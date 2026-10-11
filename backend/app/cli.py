"""Comandi da terminale. Uso: python -m app.cli create-user <nome>"""

import argparse
import getpass
import sys

from app.auth.service import create_user
from app.db import SessionLocal


def _create_user(username: str, admin: bool) -> int:
    password = getpass.getpass("Password (non viene mostrata mentre scrivi): ")
    if password != getpass.getpass("Ripeti la password: "):
        print("Le due password non coincidono.", file=sys.stderr)
        return 1
    try:
        with SessionLocal() as db:
            user = create_user(db, username, password, is_admin=admin)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Utente '{user.username}' creato.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="crea un utente")
    create.add_argument("username")
    create.add_argument("--admin", action="store_true", help="può vedere la pagina di amministrazione")
    args = parser.parse_args()
    if args.command == "create-user":
        return _create_user(args.username, args.admin)
    return 1


if __name__ == "__main__":
    sys.exit(main())
