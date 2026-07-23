# db_manager.py
import json
import os
import datetime
import uuid
from config import DB_FILE, ROLE_ADMIN, ROLE_LECTURER, ROLE_COURSE_REP


class DatabaseManager:
    def __init__(self):
        self.db_file = DB_FILE
        self._initialize_db()

    def _initialize_db(self):
        """Create DB file if it doesn’t exist."""
        if not os.path.exists(self.db_file):
            with open(self.db_file, "w") as f:
                initial = {
                    "users": [
                        {"username": "admin", "password": "password", "role": ROLE_ADMIN, "assigned_courses": []},
                        {"username": "rep1", "password": "password", "role": ROLE_COURSE_REP, "assigned_courses": []},
                        {"username": "lect1", "password": "password", "role": ROLE_LECTURER,
                         "assigned_courses": ["Database Systems"]}
                    ],
                    "students": [],
                    "attendance_records": [],
                    "courses": []
                }
                json.dump(initial, f, indent=4)

    def _load_db(self):
        with open(self.db_file, "r") as f:
            return json.load(f)

    def _save_db(self, data):
        with open(self.db_file, "w") as f:
            json.dump(data, f, indent=4)

    # ---------------- Users ----------------
    def get_user(self, username, password):
        for u in self._load_db()["users"]:
            if u["username"] == username and u["password"] == password:
                return u
        return None

    def get_all_users(self):
        return self._load_db()["users"]

    def add_user(self, username, password, role, assigned_courses):
        db = self._load_db()
        if any(u["username"] == username for u in db["users"]):
            return False, "User already exists."

        if role == ROLE_ADMIN:
            assigned_courses = []

        if role == ROLE_LECTURER:
            taken = set()
            for u in db["users"]:
                if u["role"] == ROLE_LECTURER:
                    taken.update(u["assigned_courses"])
            for c in assigned_courses:
                if c in taken:
                    return False, f"Course {c} already has a lecturer"

        if role == ROLE_COURSE_REP:
            assigned_courses = assigned_courses or []

        db["users"].append({
            "username": username,
            "password": password,
            "role": role,
            "assigned_courses": assigned_courses
        })
        self._save_db(db)
        return True, "User added"

    def remove_user(self, username):
        db = self._load_db()
        before = len(db["users"])
        db["users"] = [u for u in db["users"] if u["username"] != username]
        self._save_db(db)
        if len(db["users"]) < before:
            return True, f"{username} removed"
        return False, "Not found"

    # ---------------- Students ----------------
    def add_student(self, student):
        db = self._load_db()
        if any(s["id"] == student["id"] for s in db["students"]):
            return False, "Student ID already exists"
        db["students"].append(student)
        self._save_db(db)
        return True, "Student added"

    def get_all_students(self):
        return self._load_db()["students"]

    def remove_student(self, sid):
        db = self._load_db()
        before = len(db["students"])
        db["students"] = [s for s in db["students"] if s["id"] != sid]
        self._save_db(db)
        if len(db["students"]) < before:
            return True, "Student removed"
        return False, "Not found"

    def get_student_count(self):
        return len(self._load_db()["students"])

    # ---------------- Courses ----------------
    def get_all_courses(self):
        return self._load_db()["courses"]

    def add_course(self, cid, cname, schedule):
        db = self._load_db()
        if any(c["id"] == cid for c in db["courses"]):
            return False, "Course ID already exists"
        if any(c["name"] == cname for c in db["courses"]):
            return False, "Course name already exists"
        db["courses"].append({"id": cid, "name": cname, "schedule": schedule})
        self._save_db(db)
        return True, "Course added"

    def remove_course(self, cname):
        db = self._load_db()
        before = len(db["courses"])
        db["courses"] = [c for c in db["courses"] if c["name"] != cname]
        self._save_db(db)
        if len(db["courses"]) < before:
            return True, "Course removed"
        return False, "Not found"

    def set_course_schedule(self, cname, schedule):
        db = self._load_db()
        for c in db["courses"]:
            if c["name"] == cname:
                c["schedule"] = schedule
                self._save_db(db)
                return True, "Schedule set"
        return False, "Course not found"

    def get_course_schedule(self, cname):
        for c in self._load_db()["courses"]:
            if c["name"] == cname:
                return c.get("schedule", [])
        return None

    # ---------------- Attendance ----------------
    def record_attendance(self, sid, cname, status):
        db = self._load_db()
        record = {
            "id": str(uuid.uuid4()),
            "student_id": sid,
            "course": cname,
            "timestamp": datetime.datetime.now().isoformat(),
            "status": status
        }
        db["attendance_records"].append(record)
        self._save_db(db)

    def get_attendance_for_course(self, cname):
        return [r for r in self._load_db()["attendance_records"] if r["course"] == cname]

    def get_attendance_for_day_and_course(self, cname, date):
        return [
            r for r in self._load_db()["attendance_records"]
            if r["course"] == cname and r["timestamp"].startswith(date)
        ]

    def get_all_records(self):
        return self._load_db()["attendance_records"]
