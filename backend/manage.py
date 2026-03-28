#!/usr/bin/env python3
"""
Plugo CLI management commands.

Usage:
    python manage.py create-admin              # Create admin account (interactive)
    python manage.py create-admin -u admin -p secret123  # Non-interactive
    python manage.py reset-password            # Reset password (interactive)
    python manage.py reset-password -u admin -p newpass123
    python manage.py list-users                # List all users
"""

import sys
import asyncio
import argparse
import getpass

from dotenv import load_dotenv
load_dotenv()

from database import init_db, async_session
from auth import hash_password, verify_password
from repositories import get_repos


async def create_admin(username: str, password: str):
    """Create an admin user."""
    await init_db()
    repos = await get_repos()

    # Check if username already exists
    existing = await repos.users.get_by_username(username)
    if existing:
        print(f"Error: User '{username}' already exists.")
        return False

    await repos.users.create({
        "username": username,
        "password_hash": hash_password(password),
        "role": "admin",
    })

    print(f"Admin user '{username}' created successfully.")
    return True


async def reset_password(username: str, new_password: str):
    """Reset a user's password."""
    await init_db()
    repos = await get_repos()

    user = await repos.users.get_by_username(username)
    if not user:
        print(f"Error: User '{username}' not found.")
        return False

    # Update password via raw SQL since repos may not have an update method for users
    from sqlalchemy import update
    from models.user import User
    async with async_session() as db:
        await db.execute(
            update(User)
            .where(User.username == username)
            .values(password_hash=hash_password(new_password))
        )
        await db.commit()

    print(f"Password for '{username}' has been reset.")
    return True


async def list_users():
    """List all users."""
    await init_db()
    repos = await get_repos()

    # Get all users through the repo
    from sqlalchemy import select
    from models.user import User
    async with async_session() as db:
        result = await db.execute(select(User).order_by(User.created_at))
        users = result.scalars().all()

    if not users:
        print("No users found. Run 'python manage.py create-admin' to create one.")
        return

    print(f"\n{'Username':<20} {'Role':<10} {'Created At'}")
    print("-" * 55)
    for u in users:
        created = u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "N/A"
        print(f"{u.username:<20} {u.role:<10} {created}")
    print(f"\nTotal: {len(users)} user(s)")


def prompt_password(confirm: bool = True) -> str:
    """Prompt for password with optional confirmation."""
    while True:
        password = getpass.getpass("Password (min 8 chars): ")
        if len(password) < 8:
            print("Error: Password must be at least 8 characters.")
            continue
        if confirm:
            password2 = getpass.getpass("Confirm password: ")
            if password != password2:
                print("Error: Passwords do not match.")
                continue
        return password


def main():
    parser = argparse.ArgumentParser(
        description="Plugo management commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage.py create-admin
  python manage.py create-admin -u admin -p mypassword123
  python manage.py reset-password -u admin
  python manage.py reset-password -u admin -p newpassword123
  python manage.py list-users
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # create-admin
    create_parser = subparsers.add_parser("create-admin", help="Create an admin user")
    create_parser.add_argument("-u", "--username", help="Admin username")
    create_parser.add_argument("-p", "--password", help="Admin password (min 8 chars)")

    # reset-password
    reset_parser = subparsers.add_parser("reset-password", help="Reset a user's password")
    reset_parser.add_argument("-u", "--username", help="Username to reset")
    reset_parser.add_argument("-p", "--password", help="New password (min 8 chars)")

    # list-users
    subparsers.add_parser("list-users", help="List all users")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "create-admin":
        username = args.username or input("Username: ").strip()
        if not username or len(username) < 3:
            print("Error: Username must be at least 3 characters.")
            sys.exit(1)
        password = args.password or prompt_password()
        if len(password) < 8:
            print("Error: Password must be at least 8 characters.")
            sys.exit(1)
        success = asyncio.run(create_admin(username, password))
        sys.exit(0 if success else 1)

    elif args.command == "reset-password":
        username = args.username or input("Username: ").strip()
        if not username:
            print("Error: Username is required.")
            sys.exit(1)
        password = args.password or prompt_password()
        if len(password) < 8:
            print("Error: Password must be at least 8 characters.")
            sys.exit(1)
        success = asyncio.run(reset_password(username, password))
        sys.exit(0 if success else 1)

    elif args.command == "list-users":
        asyncio.run(list_users())


if __name__ == "__main__":
    main()
