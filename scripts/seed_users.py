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
sys.path.insert(0, BASE_DIR)

from app.config.settings import Config
from app.db.storage_adapter import create_storage
from app.models.user import User
from app.services.auth.auth import hash_password

# ─

FIRST_NAMES_MALE = [
    "Aarav",
    "Vivaan",
    "Aditya",
    "Vihaan",
    "Arjun",
    "Sai",
    "Rohit",
    "Aryan",
    "Raj",
    "Amit",
    "Suresh",
    "Ramesh",
    "Vikram",
    "Anil",
    "Sunil",
    "Manoj",
    "Sanjay",
    "Rajesh",
    "Deepak",
    "Ashok",
    "Vijay",
    "Kishore",
    "Ravi",
    "Prakash",
    "Ganesh",
    "Dinesh",
    "Mahesh",
    "Vinod",
    "Harish",
    "Naveen",
    "Prasad",
    "Siddharth",
    "Karan",
    "Harsh",
    "Yash",
    "Om",
    "Rohan",
    "Kunal",
    "Abhishek",
    "Nikhil",
    "Shubham",
    "Varun",
    "Rahul",
    "Aniket",
    "Pranav",
    "Dhruv",
    "Tanmay",
    "Ishaan",
    "Shaurya",
    "Yash",
    "Reyansh",
    "Dhruv",
    "Kabir",
    "Rudra",
    "Ayaan",
    "Krishna",
    "Shiv",
    "Daksh",
    "Atharv",
    "Laksh",
    "Shlok",
    "Parth",
    "Arnav",
    "Neil",
    "Hrithik",
    "Ranbir",
    "Akshay",
    "Shahid",
    "Aamir",
    "Salman",
    "Irrfan",
    "Nawazuddin",
    "Rajkummar",
    "Ayushmann",
    "Vicky",
    "Rajiv",
    "Arvind",
    "Mohan",
    "Shankar",
    "Babu",
    "Murali",
    "Srinivas",
    "Venkatesh",
    "Narayana",
    "Subramaniam",
    "Padmanabhan",
    "Balaji",
    "Prithvi",
    "Chandan",
    "Hemant",
    "Jagdish",
    "Kamal",
    "Lalit",
    "Murugan",
    "Natarajan",
    "Pandian",
    "Ramachandran",
    "Selvam",
    "Thirumalai",
    "Uday",
    "Velayudham",
    "Yogesh",
    "Chandrasekhar",
    "Venugopal",
    "Sridhar",
]

FIRST_NAMES_FEMALE = [
    "Aanya",
    "Aadhya",
    "Ananya",
    "Diya",
    "Ishita",
    "Janvi",
    "Kavya",
    "Neha",
    "Priya",
    "Riya",
    "Saanvi",
    "Tanvi",
    "Varsha",
    "Yashvi",
    "Aishwarya",
    "Deepika",
    "Katrina",
    "Anushka",
    "Shraddha",
    "Alia",
    "Kareena",
    "Madhuri",
    "Kajol",
    "Rani",
    "Vidya",
    "Priyanka",
    "Sonam",
    "Anupama",
    "Lata",
    "Asha",
    "Mira",
    "Anita",
    "Sunita",
    "Kavita",
    "Nalini",
    "Vasundhara",
    "Lakshmi",
    "Saraswati",
    "Durga",
    "Kali",
    "Parvati",
    "Sita",
    "Radha",
    "Ganga",
    "Yamuna",
    "Shakti",
    "Devi",
    "Mala",
    "Geeta",
    "Seeta",
    "Rekha",
    "Hema",
    "Jaya",
    "Shabana",
    "Waheeda",
    "Meena",
    "Kumari",
    "Selvi",
    "Bhavani",
    "Padmini",
    "Rohini",
    "Shobana",
    "Urmila",
    "Chandrika",
    "Nandini",
    "Padma",
    "Revathi",
    "Shyamala",
    "Thulasi",
    "Vijayalakshmi",
    "Yamini",
    "Swati",
    "Mrunal",
    "Tara",
    "Zara",
    "Inaya",
    "Myra",
    "Anaya",
    "Kyra",
    "Naira",
    "Alisha",
    "Eshani",
    "Gauri",
    "Harini",
    "Jasmine",
    "Kriti",
    "Lavanya",
    "Navya",
    "Ojaswini",
    "Pooja",
    "Rashmi",
    "Shreya",
]

LAST_NAMES = [
    "Sharma",
    "Verma",
    "Gupta",
    "Kumar",
    "Singh",
    "Patel",
    "Reddy",
    "Rao",
    "Nair",
    "Menon",
    "Iyer",
    "Iyengar",
    "Joshi",
    "Deshmukh",
    "Kulkarni",
    "Desai",
    "Shah",
    "Mehta",
    "Patil",
    "Pawar",
    "Yadav",
    "Jha",
    "Mishra",
    "Tiwari",
    "Pandey",
    "Dubey",
    "Saxena",
    "Srivastava",
    "Agarwal",
    "Kapoor",
    "Malhotra",
    "Chopra",
    "Bajaj",
    "Bhalla",
    "Gandhi",
    "Modi",
    "Trivedi",
    "Bhatt",
    "Pandya",
    "Solanki",
    "Chauhan",
    "Rathore",
    "Shekhawat",
    "Purohit",
    "Soni",
    "Arya",
    "Rawat",
    "Bisht",
    "Negi",
    "Rana",
    "Thapa",
    "Gurung",
    "Tamang",
    "Sherpa",
    "Lama",
    "Ghai",
    "Sood",
    "Batra",
    "Khanna",
    "Sethi",
    "Arora",
    "Sachdev",
    "Juneja",
    "Bhasin",
    "Chadha",
    "Dhawan",
    "Gulati",
    "Kohli",
    "Malik",
    "Narang",
    "Oberoi",
    "Purie",
    "Sabharwal",
    "Tandon",
    "Uppal",
    "Vohra",
    "Wahi",
    "Bansal",
    "Garg",
    "Mittal",
    "Singhal",
    "Goyal",
    "Poddar",
    "Lodha",
    "Chordia",
    "Kothari",
    "Bothra",
    "Daga",
    "Somani",
    "Kedia",
    "Bhardwaj",
    "Mukherjee",
    "Banerjee",
    "Chatterjee",
    "Ghosh",
    "Das",
    "Bose",
    "Sen",
    "Roy",
    "Chakraborty",
    "Sarkar",
    "Pal",
    "Majumdar",
    "Dutta",
    "Saha",
    "Bhowmik",
    "Dey",
    "Bhowmick",
]

CITIES = [
    ("Mumbai", "Maharashtra"),
    ("Delhi", "Delhi"),
    ("Bangalore", "Karnataka"),
    ("Hyderabad", "Telangana"),
    ("Ahmedabad", "Gujarat"),
    ("Chennai", "Tamil Nadu"),
    ("Kolkata", "West Bengal"),
    ("Pune", "Maharashtra"),
    ("Jaipur", "Rajasthan"),
    ("Lucknow", "Uttar Pradesh"),
    ("Surat", "Gujarat"),
    ("Nagpur", "Maharashtra"),
    ("Indore", "Madhya Pradesh"),
    ("Bhopal", "Madhya Pradesh"),
    ("Patna", "Bihar"),
    ("Vadodara", "Gujarat"),
    ("Coimbatore", "Tamil Nadu"),
    ("Chandigarh", "Chandigarh"),
    ("Mysore", "Karnataka"),
    ("Thiruvananthapuram", "Kerala"),
    ("Guwahati", "Assam"),
    ("Ranchi", "Jharkhand"),
    ("Bhubaneswar", "Odisha"),
    ("Vishakhapatnam", "Andhra Pradesh"),
    ("Agra", "Uttar Pradesh"),
    ("Varanasi", "Uttar Pradesh"),
    ("Udaipur", "Rajasthan"),
    ("Kochi", "Kerala"),
    ("Goa", "Goa"),
    ("Shimla", "Himachal Pradesh"),
    ("Darjeeling", "West Bengal"),
    ("Pondicherry", "Puducherry"),
    ("Amritsar", "Punjab"),
    ("Jodhpur", "Rajasthan"),
    ("Nasik", "Maharashtra"),
    ("Aurangabad", "Maharashtra"),
    ("Madurai", "Tamil Nadu"),
    ("Trichy", "Tamil Nadu"),
    ("Salem", "Tamil Nadu"),
    ("Vellore", "Tamil Nadu"),
    ("Mangalore", "Karnataka"),
    ("Hubli", "Karnataka"),
    ("Guntur", "Andhra Pradesh"),
    ("Tirupati", "Andhra Pradesh"),
    ("Warangal", "Telangana"),
    ("Noida", "Uttar Pradesh"),
    ("Gurgaon", "Haryana"),
    ("Faridabad", "Haryana"),
    ("Dehradun", "Uttarakhand"),
    ("Haridwar", "Uttarakhand"),
]

GENRES = [
    "Fiction",
    "Non-Fiction",
    "Science",
    "Technology",
    "History",
    "Philosophy",
    "Art",
    "Biography",
    "Poetry",
    "Drama",
    "Comics",
    "Self-Help",
    "Cooking",
    "Travel",
    "Music",
    "Sports",
    "Education",
    "Reference",
    "Religion",
    "Children",
]

BIOS = [
    "Avid reader and lifelong learner. Love exploring different genres.",
    "Book lover who believes every story has something to teach us.",
    "Reading is my escape from reality. Currently on a fantasy kick.",
    "I read to travel without moving. 50+ books a year and counting.",
    "Book collector, tea drinker, and amateur philosopher.",
    "Always looking for book recommendations! Let's connect.",
    "Lost in the pages of a good book. Fiction is my first love.",
    "Reading is my superpower. Especially love Indian authors.",
    "From sci-fi to history, I read it all. Knowledge is power.",
    "Nothing beats the feeling of a new book. Let's read together!",
    "Bibliophile with a passion for literature and learning.",
    "I read so I can live a thousand lives. Book discussions welcome!",
    "On a mission to read 100 books this year. Join me!",
    "Books, coffee, and quiet mornings. That's my happy place.",
    "Curious mind, ever-expanding bookshelf. All genres welcome.",
    "Reading gives us someplace to go when we have to stay where we are.",
    "I judge books by their covers AND their content. No shame.",
    "Professional over-thinker and amateur book reviewer.",
    "My bookshelf is my greatest treasure. Love sharing finds.",
    "Exploring worlds one page at a time. #Bookstagrammer",
    "Book nerd by day, dreamer by night. Let's chat about books!",
    "I love the smell of old books and the promise of new ones.",
    "Reading is my therapy. A library card is my prescription.",
    "Every book is a new adventure waiting to happen.",
]

EMAIL_DOMAINS = [
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "rediffmail.com",
    "protonmail.com",
    "zoho.com",
    "icloud.com",
    "live.com",
    "fastmail.com",
    "gmx.com",
    "yandex.com",
    "mail.com",
    "bookmail.com",
    "readermail.com",
]

PHONE_PREFIXES = [
    "98765",
    "98754",
    "98123",
    "98234",
    "98345",
    "98456",
    "98567",
    "98678",
    "98989",
    "98760",
    "99887",
    "99776",
    "99665",
    "99554",
    "99443",
    "99332",
    "91234",
    "91345",
    "91456",
    "91567",
    "91678",
    "91789",
    "91890",
    "91901",
]

HOBBIES = [
    "reading",
    "writing",
    "photography",
    "cooking",
    "gardening",
    "painting",
    "traveling",
    "hiking",
    "cycling",
    "swimming",
    "yoga",
    "meditation",
    "music",
    "dancing",
    "bird watching",
    "stargazing",
    "blogging",
    "chess",
]


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
        # 80% chance of active, 15% expired, 5% blocked
        r = random.random()
        if r < 0.80:  # Active
            if random.random() < 0.7:  # Recently renewed
                return (datetime.now() + timedelta(days=random.randint(30, 365))).isoformat()
            else:
                return (reg_date + timedelta(days=365)).isoformat()
        elif r < 0.95:  # Expired
            return (reg_date + timedelta(days=365)).isoformat()
        else:  # Blocked
            return (datetime.now() + timedelta(days=random.randint(-30, 30))).isoformat()
    except (ValueError, TypeError):
        return (datetime.now() + timedelta(days=365)).isoformat()


def generate_membership_status(reg_date_str: str, expiry_str: str) -> str:
    """Determine membership status based on dates."""
    status_roll = random.random()
    if status_roll < 0.02:  # 2% blocked
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
    # Seed accounts use a randomly generated per-run password. It is not
    # printed to avoid advertising known credentials (CWE-798).
    import secrets as _secrets

    default_password = _secrets.token_urlsafe(12)
    hashed_pw = hash_password(default_password)

    print(f"  Generating {count} users...")
    for i in range(count):
        # Generate unique user_id
        while True:
            uid = generate_user_id(i + 1)
            if uid not in used_ids:
                used_ids.add(uid)
                break

        # Generate name
        first, last, _gender = generate_name()
        name = f"{first} {last}"

        # Generate unique email
        while True:
            email = generate_email(first, last, uid)
            if email not in used_emails:
                used_emails.add(email)
                break

        # Generate phone
        phone = generate_phone()

        # Determine role (mostly users, 2% librarians, 0.2% admin - but keep existing admins)
        role_roll = random.random()
        role = "librarian" if role_roll < 0.002 else "user"

        # Registration date spread over last 3 years
        registered_on = generate_registration_date(i)

        # Membership
        membership_expiry = generate_membership_expiry(registered_on)
        membership_status = generate_membership_status(registered_on, membership_expiry)

        # Social profile
        bio = generate_bio()
        location_info = generate_location()
        location = f"{location_info['city']}, {location_info['state']}"
        website = generate_website(name)
        favorite_genres = generate_favorite_genres()
        profile_picture = ""

        # 10% have a small unpaid fine
        unpaid_fine = round(random.uniform(10, 200), 2) if random.random() < 0.1 else 0.0

        # Books issued (0-2 for most, 3 for active readers, rarely max)
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
            print(f"    Generated {i + 1}/{count} users...")

    print(f"  ✅ Generated {len(users)} users")
    return users


def main() -> None:
    """Main entry point."""
    print("=" * 60)
    print("  📚 LibraryMS - User Data Seeder")
    print("  Generating 5,000 realistic users")
    print("=" * 60)

    keep_existing = "--keep" in sys.argv

    # Initialize storage (relational layer by default)
    storage = create_storage()

    # Load existing users
    existing_users = storage.load_users()
    print(f"\n  Existing users in database: {len(existing_users)}")

    if keep_existing:
        print("  Keeping existing users and adding 5,000 more...")
    else:
        print("  Overwriting all users (--keep to preserve existing)...")

    # Generate new users
    new_users = generate_users(5000)

    # Merge
    all_users = {**existing_users, **new_users} if keep_existing else new_users
        # Ensure admin exists
        # Check if we need to preserve the default admin
        # Actually, let the web_app.py recreation handle it

    # Save
    storage.save_users(all_users)
    print(f"\n  ✅ Saved {len(all_users)} users to {Config.USERS_FILE}")

    # Quick stats
    roles = {}
    statuses = {}
    for u in all_users.values():
        roles[u.role] = roles.get(u.role, 0) + 1
        statuses[u.membership_status] = statuses.get(u.membership_status, 0) + 1

    print("\n  📊 User Statistics:")
    print(f"     Total users:  {len(all_users)}")
    print(f"     Admins:       {roles.get('admin', 0)}")
    print(f"     Librarians:   {roles.get('librarian', 0)}")
    print(f"     Users:        {roles.get('user', 0)}")
    print(f"     Active:       {statuses.get('Active', 0)}")
    print(f"     Expired:      {statuses.get('Expired', 0)}")
    print(f"     Blocked:      {statuses.get('Blocked', 0)}")
    # (Seed-user default password intentionally redacted from output for security.)
    print("  💡 Admin login: ADMIN001 (password generated on first boot)")
    print("=" * 60)


if __name__ == "__main__":
    main()
