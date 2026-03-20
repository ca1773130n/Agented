"""Generate an admin API key for Agented.

Usage:
    cd backend && uv run python scripts/generate_key.py [--label LABEL] [--role ROLE]
"""

import argparse
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.migrations import init_db
from app.db.rbac import count_user_roles, create_user_role, generate_api_key


def main():
    parser = argparse.ArgumentParser(description="Generate an Agented API key")
    parser.add_argument("--label", default="Admin", help="Label for the key (default: Admin)")
    parser.add_argument(
        "--role",
        default="admin",
        choices=["viewer", "operator", "editor", "admin"],
        help="Role for the key (default: admin)",
    )
    args = parser.parse_args()

    # Ensure DB is initialized
    init_db()

    key = generate_api_key()
    role_id = create_user_role(api_key=key, label=args.label, role=args.role)

    if not role_id:
        print("ERROR: Failed to create API key (duplicate?)", file=sys.stderr)
        sys.exit(1)

    print(f"\n  API Key:  {key}")
    print(f"  Role:     {args.role}")
    print(f"  Label:    {args.label}")
    print(f"  Role ID:  {role_id}")
    print(f"\n  Save this key — it will not be shown again.\n")


if __name__ == "__main__":
    main()
