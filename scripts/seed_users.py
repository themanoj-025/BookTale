"""
seed_users.py — Generate 5,000 realistic users for the Library Management System

NOTE: Seeded accounts receive a randomly generated password that is never
printed (deliberate — we do not advertise known credentials, CWE-798). They are
intended for data-volume/demo purposes; log in with the admin account or create
your own user to interact with them.

Usage:
    python seed_users.py          # Generate fresh 5,000 users
    python seed_users.py --keep   # Keep existing users and add 5,000 more
"""

import os
import random
import sys
from datetime import datetime, timedelta

# Ensure we can import project modules
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from app.config.settings import Config
from app.db.storage_adapter import create_storage
from app.models.user import User
from app.services.auth.auth import hash_password
import logging

from scripts.seed_data import (
    BIOS,
    CITIES,
    EMAIL_DOMAINS,
    FIRST_NAMES_FEMALE,
    FIRST_NAMES_MALE,
    GENRES,
    LAST_NAMES,
    PHONE_PREFIXES,
)

logger = logging.getLogger(__name__)


def generate_name() -> tuple:
    """Generate a realistic Indian name. Returns (first_name, last_name, gender)."""
    gender = random.choice(["male", "female"])
    if gender == "male":
        first = random.choice(FIRST_NAMES_MALE)
    else:
        first = random.choice(FIRST_NAMES_FEMALE)
    last = random.choice(LAST_NAMES)
    return first, last, gender


def generate_email(first: str, last: str, user_id: str) -> str:
    """Generate a realistic email address."""
    domain = random.choice(EMAIL_DOMAINS)
    pattern = random.choice(
        [
            lambda f, l, uid: f"{f.lower()}.{l.lower()}@{domain}",
            lambda f, l, uid: f"{f.lower()}{l.lower()}{uid[-4:]}@{domain}",
            lambda f, l, uid: f"{f.lower()}_{l.lower()}@{domain}",
            lambda f, l, uid: f"{f[0].lower()}{l.lower()}@{domain}",
            lambda f, l, uid: f"{f.lower()}{random.randint(1, 99)}@{domain}",
            lambda f, l, uid: f"{l.lower()}.{f.lower()}@{domain}",
        ]
    )
    return pattern(first, last, user_id)


def generate_phone() -> str:
    """Generate a realistic Indian phone number."""
    prefix = random.choice(PHONE_PREFIXES)
    suffix = "".join([str(random.randint(0, 9)) for _ in range(5)])
    return f"+91{prefix}{suffix}"


def generate_user_id(index: int) -> str:
    """Generate a unique user ID."""
    return f"USR{index:05d}"


def generate_location() -> dict:
    """Generate a city, state location."""
    city, state = random.choice(CITIES)
    return {"city": city, "state": state}


def generate_bio() -> str:
    """Generate a random bio."""
    return random.choice(BIOS)


def generate_favorite_genres() -> list:
    """Generate 2-5 favorite genres."""
    return random.sample(GENRES, random.randint(2, 5))


def generate_registration_date(index: int) -> str:
    """Generate a registration date spread over the last 3 years."""
    days_ago = random.randint(1, 1095)  # Up to 3 years ago
    reg_date = datetime.now() - timedelta(days=days_ago)
    return reg_date.isoformat()


def generate_membership_expiry(reg_date_str: str) -> str:
    """Generate membership expiry (1 year from registration or expired)."""
    try:
        reg_date = datetime.fromisoformat(reg_date_str)
        r = random.random()
        if r < 0.80:
            if random.random() < 0.7:
                return (datetime.now() + timedelta(days=random.randint(30, 365))).isoformat()
            else:
                return (reg_date + timedelta(days=365)).isoformat()
        elif r < 0.95:
            return (reg_date + timedelta(days=365)).isoformat()
        else:
            return (datetime.now() + timedelta(days=random.randint(-30, 30))).isoformat()
    except (ValueError, TypeError):
        return (datetime.now() + timedelta(days=365)).isoformat()


def generate_membership_status(reg_date_str: str, expiry_str: str) -> str:
    """Determine membership status based on dates."""
    status_roll = random.random()
    if status_roll < 0.02:
        return "Blocked"
    try:
        expiry = datetime.fromisoformat(expiry_str)
        if datetime.now() > expiry:
            return "Expired"
    except (ValueError, TypeError):
        pass
    return "Active"


def generate_website(name: str) -> str:
    """Generate a personal website/blog URL."""
    first_lower = name.split(maxsplit=1)[0].lower()
    return random.choice(
        [
            f"https://{first_lower}.blogspot.com",
            f"https://{first_lower}.wordpress.com",
            "",
            f"https://{first_lower}reads.wordpress.com",
            f"https://{first_lower}-books.medium.com",
            "",
            f"https://{first_lower}library.wordpress.com",
        ]
    )


def generate_users(count: int = 5000) -> dict[str, User]:
    """Generate `count` fake users."""
    users: dict[str, User] = {}
    used_ids = set()
    used_emails = set()
    import secrets as _secrets

    default_password = _secrets.token_urlsafe(12)
    hashed_pw = hash_password(default_password)

    logger.info(f"  Generating {count} users...")
    for i in range(count):
        while True:
            uid = generate_user_id(i + 1)
            if uid not in used_ids:
                used_ids.add(uid)
                break

        first, last, _gender = generate_name()
        name = f"{first} {last}"

        while True:
            email = generate_email(first, last, uid)
            if email not in used_emails:
                used_emails.add(email)
                break

        phone = generate_phone()

        role_roll = random.random()
        role = "librarian" if role_roll < 0.002 else "user"

        registered_on = generate_registration_date(i)
        membership_expiry = generate_membership_expiry(registered_on)
        membership_status = generate_membership_status(registered_on, membership_expiry)

        bio = generate_bio()
        location_info = generate_location()
        location = f"{location_info['city']}, {location_info['state']}"
        website = generate_website(name)
        favorite_genres = generate_favorite_genres()
        profile_picture = ""

        unpaid_fine = round(random.uniform(10, 200), 2) if random.random() < 0.1 else 0.0
        books_issued = []

        user = User(
            user_id=uid,
            name=name,
            email=email,
            phone=phone,
            role=role,
            password_hash=hashed_pw,
            membership_status=membership_status,
            membership_expiry=membership_expiry,
            books_issued=books_issued,
            unpaid_fine=unpaid_fine,
            registered_on=registered_on,
            bio=bio,
            profile_picture=profile_picture,
            website=website,
            location=location,
            favorite_genres=favorite_genres,
        )
        users[uid] = user

        if (i + 1) % 1000 == 0:
            logger.info(f"    Generated {i + 1}/{count} users...")

    logger.info(f"  ✅ Generated {len(users)} users")
    return users


def main() -> None:
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("  📚 LibraryMS - User Data Seeder")
    logger.info("  Generating 5,000 realistic users")
    logger.info("=" * 60)

    keep_existing = "--keep" in sys.argv

    storage = create_storage()
    existing_users = storage.load_users()
    logger.info(f"\n  Existing users in database: {len(existing_users)}")

    if keep_existing:
        logger.info("  Keeping existing users and adding 5,000 more...")
    else:
        logger.info("  Overwriting all users (--keep to preserve existing)...")

    new_users = generate_users(5000)

    all_users = {**existing_users, **new_users} if keep_existing else new_users

    storage.save_users(all_users)
    logger.info(f"\n  ✅ Saved {len(all_users)} users to {Config.USERS_FILE}")

    roles = {}
    statuses = {}
    for u in all_users.values():
        roles[u.role] = roles.get(u.role, 0) + 1
        statuses[u.membership_status] = statuses.get(u.membership_status, 0) + 1

    logger.info("\n  📊 User Statistics:")
    logger.info(f"     Total users:  {len(all_users)}")
    logger.info(f"     Admins:       {roles.get('admin', 0)}")
    logger.info(f"     Librarians:   {roles.get('librarian', 0)}")
    logger.info(f"     Users:        {roles.get('user', 0)}")
    logger.info(f"     Active:       {statuses.get('Active', 0)}")
    logger.info(f"     Expired:      {statuses.get('Expired', 0)}")
    logger.info(f"     Blocked:      {statuses.get('Blocked', 0)}")
    logger.info("  💡 Admin login: ADMIN001 (password generated on first boot)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
