"""Administración local: uv run python -m app.cli --help."""
import argparse
import getpass
import os

import pyotp

from app.core.database import SessionLocal, init_db
from app.services import security


def password_prompt() -> str:
    password = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
    if password != getpass.getpass("Repetí la contraseña: "):
        raise ValueError("Las contraseñas no coinciden")
    security.validate_password(password)
    return password


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Administración local de usuarios de Origo")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("create-user", "set-password", "enable-totp", "disable-totp"):
        commands.add_parser(command).add_argument("username")
    commands.add_parser("list-users")
    args = parser.parse_args()
    init_db()
    try:
        with SessionLocal() as db:
            if args.command == "list-users":
                for user in security.list_users(db):
                    print(f"{user.username}\t{user.role}\tTOTP: {'sí' if user.totp_secret else 'no'}")
                return
            if args.command == "create-user":
                security.create_user(db, args.username, password_prompt())
            else:
                user = security.find_user(db, args.username)
                if not user:
                    raise ValueError("No existe ese usuario")
                if args.command == "set-password":
                    security.set_password(db, user, password_prompt())
                elif args.command == "disable-totp":
                    security.set_totp(db, user, None)
                else:
                    secret = pyotp.random_base32()
                    totp = pyotp.TOTP(secret)
                    print("Guardá este secreto en tu autenticador; no lo compartas:")
                    print(totp.provisioning_uri(user.username, issuer_name="Origo"))
                    if not totp.verify(getpass.getpass("Código del autenticador: ").strip(), valid_window=1):
                        raise ValueError("Código incorrecto; TOTP no se activó")
                    security.set_totp(db, user, secret)
            print("Listo.")
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
