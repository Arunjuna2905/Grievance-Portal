import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "replace-this-before-deployment")

    # MySQL Database
    MYSQL_HOST     = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT     = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER     = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "grievance_db")

    UPLOAD_FOLDER = BASE_DIR / "static" / "uploads" / "complaints"
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    ADMIN_BOOTSTRAP_NAME     = os.getenv("SMARTGOV_ADMIN_NAME")
    ADMIN_BOOTSTRAP_EMAIL    = os.getenv("SMARTGOV_ADMIN_EMAIL")
    ADMIN_BOOTSTRAP_PASSWORD = os.getenv("SMARTGOV_ADMIN_PASSWORD")

