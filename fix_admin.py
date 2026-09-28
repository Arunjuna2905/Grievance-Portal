"""One-time script to reset admin credentials in the database."""
import pymysql
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv
import os

load_dotenv()

NEW_EMAIL    = os.getenv("SMARTGOV_ADMIN_EMAIL", "admin@gmail.com")
NEW_PASSWORD = os.getenv("SMARTGOV_ADMIN_PASSWORD", "admin123")
NEW_NAME     = os.getenv("SMARTGOV_ADMIN_NAME", "Admin")

conn = pymysql.connect(
    host=os.getenv("MYSQL_HOST", "localhost"),
    port=int(os.getenv("MYSQL_PORT", 3306)),
    user=os.getenv("MYSQL_USER", "root"),
    password=os.getenv("MYSQL_PASSWORD", ""),
    database=os.getenv("MYSQL_DATABASE", "grievance_db"),
    cursorclass=pymysql.cursors.DictCursor,
    charset="utf8mb4",
)

hashed = generate_password_hash(NEW_PASSWORD)

with conn.cursor() as cur:
    # Check if any admin exists
    cur.execute("SELECT id, email FROM users WHERE role='admin'")
    admins = cur.fetchall()

    if admins:
        # Update the existing admin with new email + password
        for admin in admins:
            cur.execute(
                "UPDATE users SET name=%s, email=%s, password_hash=%s WHERE id=%s",
                (NEW_NAME, NEW_EMAIL, hashed, admin["id"])
            )
            print(f"[OK] Updated admin (id={admin['id']}) -> email: {NEW_EMAIL}")
    else:
        # No admin exists, create one
        cur.execute(
            "INSERT INTO users(name, email, password_hash, role) VALUES(%s,%s,%s,'admin')",
            (NEW_NAME, NEW_EMAIL, hashed)
        )
        print(f"[OK] Created new admin -> email: {NEW_EMAIL}")

conn.commit()
conn.close()
print("Done! You can now log in with:")
print(f"  Email   : {NEW_EMAIL}")
print(f"  Password: {NEW_PASSWORD}")
