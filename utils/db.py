import pymongo
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DATABASE_NAME = "hrms_db"

client = pymongo.MongoClient(MONGO_URI)
db = client[DATABASE_NAME]

# Collections
users = db["users"]
leaves = db["leaves"]
salaries = db["salaries"]
timetable = db["timetable"]
messages = db["messages"]

def init_db():
    # Create unique index for username
    users.create_index("username", unique=True)
    # Create default admin if not exists
    if not users.find_one({"role": "admin"}):
        from flask_bcrypt import generate_password_hash
        admin_data = {
            "username": "admin",
            "password": generate_password_hash("admin123").decode('utf-8'),
            "role": "admin",
            "name": "System Administrator",
            "email": "admin@college.edu"
        }
        users.insert_one(admin_data)
        print("Default admin created: admin / admin123")
    
    # Create default lecturer if not exists
    if not users.find_one({"role": "lecturer"}):
        from flask_bcrypt import generate_password_hash
        lecturer_data = {
            "username": "lecturer",
            "password": generate_password_hash("lect123").decode('utf-8'),
            "role": "lecturer",
            "name": "Dr. Rajesh Kumar",
            "email": "rajesh@college.edu",
            "department": "Computer Science"
        }
        users.insert_one(lecturer_data)
        print("Default lecturer created: lecturer / lect123")
