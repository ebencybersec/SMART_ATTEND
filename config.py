# config.py
# This file contains configuration constants for both the client and server.

SERVER_URL = "http://127.0.0.1:5000"  # Local development on HTTP

DB_FILE = 'attendance_db.json'

# Face matching: lower = stricter. 0.6 is common; we use stricter for classroom.
FACE_RECOGNITION_TOLERANCE = 0.38

# Extra guard: best match must beat 2nd-best by at least this margin.
SECOND_BEST_MARGIN = 0.05

# Require multiple sightings within a short window to mark PRESENT
CONFIRM_WINDOW_SEC = 2.0
CONFIRM_MIN_HITS = 2

# User roles
ROLE_ADMIN = "admin"
ROLE_LECTURER = "lecturer"
ROLE_COURSE_REP = "course_rep"

# UI helpers
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TIME_PERIODS = ["AM", "PM"]
