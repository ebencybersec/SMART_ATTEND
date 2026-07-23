from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from db_manager import DatabaseManager
from config import (
    ROLE_ADMIN, ROLE_LECTURER, ROLE_COURSE_REP,
    FACE_RECOGNITION_TOLERANCE, SECOND_BEST_MARGIN,
    CONFIRM_WINDOW_SEC, CONFIRM_MIN_HITS
)
import cv2, numpy as np, face_recognition, base64, re, functools, os, time
from datetime import datetime, timedelta
import datetime as dt

app = Flask(__name__)
# Proper env var usage; change in your shell for prod
app.secret_key = os.environ.get("APP_SECRET_KEY", "a27b190eb929f27d556d84e4e86e241999c02b737b1ae297b03cffbbc1112793")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,  # HTTP => must be False
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=45)
)

db = DatabaseManager()

# ---- Multi-sighting confirmation cache (in-memory)
RECENT_SEEN = {}  # key: (student_id, course) -> list[timestamps]

def _prune_seen(now_s, key):
    hits = [t for t in RECENT_SEEN.get(key, []) if now_s - t <= CONFIRM_WINDOW_SEC]
    if hits:
        RECENT_SEEN[key] = hits
    else:
        RECENT_SEEN.pop(key, None)
    return RECENT_SEEN.get(key, [])

# ---------------- Helpers ----------------
def decode_image(data_url: str):
    img_str = re.sub("^data:image/.+;base64,", "", data_url or "")
    img_bytes = base64.b64decode(img_str)
    nparr = np.frombuffer(img_bytes, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

def requires_role(role):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            user = session.get("user")
            if not user or user["role"] != role:
                return redirect(url_for("login_page"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def requires_any_role(roles):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            user = session.get("user")
            if not user or user["role"] not in roles:
                return redirect(url_for("login_page"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def require_admin_json():
    u = session.get("user")
    return bool(u and u["role"] == ROLE_ADMIN)

def _parse_time_12h(s):
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None

def is_within_schedule(course_name: str):
    course = next((c for c in db.get_all_courses() if c["name"] == course_name), None)
    if not course:
        return False, [], f"Course '{course_name}' not found."
    sched = course.get("schedule") or []
    if not sched:
        return False, [], "No schedule set for this course."

    now = dt.datetime.now()
    today_name = now.strftime("%A")
    t = now.time()

    for s in sched:
        if s["day"] == today_name:
            start = _parse_time_12h(s["start_time"])
            end = _parse_time_12h(s["end_time"])
            if start and end and start <= t <= end:
                return True, sched, "OK"
    return False, sched, "Not within scheduled time."

def build_schedule_item(day, sh, sm, sp, eh, em, ep):
    def norm(h, m, p):
        h = int(h); m = int(m); p = p.strip().upper()
        return f"{h:02}:{m:02} {p}"
    return [{
        "day": (day or "").strip().title(),
        "start_time": norm(sh, sm, sp),
        "end_time": norm(eh, em, ep)
    }]

def can_access_course(user, course_name: str) -> bool:
    if not user:
        return False
    if user["role"] == ROLE_ADMIN:
        return False
    if user["role"] == ROLE_COURSE_REP:
        return True
    if user["role"] == ROLE_LECTURER:
        return course_name in (user.get("assigned_courses") or [])
    return False

# ---------------- Global Auth Guard ----------------
@app.before_request
def global_login_guard():
    endpoint = (getattr(request, "endpoint", None) or "")
    if endpoint in {"login_page", "logout", "check_login"} or endpoint.startswith("static"):
        return
    if "user" in session:
        return
    if request.path.startswith("/api/"):
        return jsonify({"error": "Unauthorized"}), 401
    return redirect(url_for("login_page"))

@app.get("/api/check_login")
def check_login():
    return jsonify({
        "logged_in": "user" in session,
        "user": session.get("user", {}).get("username") if session.get("user") else None,
        "role": session.get("user", {}).get("role") if session.get("user") else None
    })

# ---------------- Auth & Pages ----------------
@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login_page"))

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = db.get_user(username, password)
        if user:
            session.clear()
            session.permanent = True
            session["user"] = user
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

@app.route("/dashboard")
def dashboard():
    user = session["user"]
    stats = {
        "students": db.get_student_count(),
        "users": len(db.get_all_users()) if user["role"] == ROLE_ADMIN else None
    }
    return render_template("dashboard.html", user=user, stats=stats)

@app.route("/capture")
@requires_any_role([ROLE_LECTURER, ROLE_COURSE_REP])
def capture_page():
    return render_template("capture.html", user=session["user"])

@app.route("/take_attendance")
@requires_any_role([ROLE_LECTURER, ROLE_COURSE_REP])
def take_attendance_page():
    user = session["user"]
    courses = [c["name"] for c in db.get_all_courses()] if user["role"] == ROLE_COURSE_REP else (user.get("assigned_courses") or [])
    return render_template("take_attendance.html", user=user, courses=courses)

@app.route("/view_attendance")
@requires_any_role([ROLE_LECTURER, ROLE_COURSE_REP])
def view_attendance_page():
    user = session["user"]
    courses = [c["name"] for c in db.get_all_courses()] if user["role"] == ROLE_COURSE_REP else (user.get("assigned_courses") or [])
    return render_template("view_attendance.html", user=user, courses=courses)

@app.route("/admin/courses")
@requires_role(ROLE_ADMIN)
def admin_courses():
    return render_template("admin_courses.html", user=session["user"])

@app.route("/admin/users")
@requires_role(ROLE_ADMIN)
def admin_users():
    return render_template("admin_users.html", user=session["user"])

@app.route("/admin/students")
@requires_role(ROLE_ADMIN)
def admin_students():
    return render_template("admin_students.html", user=session["user"])

@app.route("/admin/records")
@requires_role(ROLE_ADMIN)
def admin_records():
    return render_template("admin_records.html", user=session["user"])

# ---------------- Admin JSON APIs ----------------
@app.route("/api/courses", methods=["GET"])
def api_courses_list():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    out = []
    for c in db.get_all_courses():
        sched = c.get("schedule") or []
        sched_str = ", ".join([f"{x['day']} ({x['start_time']} - {x['end_time']})" for x in sched]) if sched else ""
        out.append({"id": c["id"], "name": c["name"], "schedule": sched_str})
    return jsonify(out)

@app.route("/api/courses", methods=["POST"])
def api_courses_add():
    if not require_admin_json():
        return jsonify({"error": "Unauthorized"}), 403
    d = request.get_json(force=True) or {}
    cid = d.get("id") or d.get("course_id")
    cname = d.get("name") or d.get("course_name")
    day = d.get("day"); sh=d.get("start_hour"); sm=d.get("start_min"); sp=d.get("start_period")
    eh=d.get("end_hour"); em=d.get("end_min"); ep=d.get("end_period")
    if not cid or not cname:
        return jsonify({"error": "Course id and name required"}), 400
    schedule = build_schedule_item(day, sh, sm, sp, eh, em, ep) if all([day, sh, sm, sp, eh, em, ep]) else []
    ok, msg = db.add_course(cid, cname, schedule)
    return (jsonify({"message": msg}), 201) if ok else (jsonify({"error": msg}), 409)

@app.route("/api/courses", methods=["DELETE"])
def api_courses_delete():
    if not require_admin_json():
        return jsonify({"error": "Unauthorized"}), 403
    d = request.get_json(force=True) or {}
    cname = d.get("name") or d.get("course_name")
    if not cname:
        return jsonify({"error": "Course name required"}), 400
    ok, msg = db.remove_course(cname)
    return (jsonify({"message": msg}), 200) if ok else (jsonify({"error": msg}), 404)

@app.route("/api/courses/schedule", methods=["POST"])
def api_courses_set_schedule():
    if not require_admin_json():
        return jsonify({"error": "Unauthorized"}), 403
    d = request.get_json(force=True) or {}
    cname = d.get("name") or d.get("course_name")
    day = d.get("day"); sh=d.get("start_hour"); sm=d.get("start_min"); sp=d.get("start_period")
    eh=d.get("end_hour"); em=d.get("end_min"); ep=d.get("end_period")
    if not (cname and day and sh and sm and sp and eh and em and ep):
        return jsonify({"error": "name, day, start/end fields required"}), 400
    schedule = build_schedule_item(day, sh, sm, sp, eh, em, ep)
    ok, msg = db.set_course_schedule(cname, schedule)
    return (jsonify({"message": msg}), 200) if ok else (jsonify({"error": msg}), 404)

@app.route("/api/users", methods=["GET"])
def api_users_list():
    if not require_admin_json():
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify(db.get_all_users())

@app.route("/api/users", methods=["POST"])
def api_users_add():
    if not require_admin_json():
        return jsonify({"error": "Unauthorized"}), 403
    d = request.get_json(force=True) or {}
    username = d.get("username")
    password = d.get("password")
    role = d.get("role")
    assigned_courses = d.get("assigned_courses") or []
    if role != ROLE_LECTURER:
        assigned_courses = []
    if not all([username, password, role]):
        return jsonify({"error": "username, password, role required"}), 400
    ok, msg = db.add_user(username, password, role, assigned_courses)
    return (jsonify({"message": msg}), 201) if ok else (jsonify({"error": msg}), 409)

@app.route("/api/users", methods=["DELETE"])
def api_users_delete():
    if not require_admin_json():
        return jsonify({"error": "Unauthorized"}), 403
    d = request.get_json(force=True) or {}
    username = d.get("username")
    if not username:
        return jsonify({"error": "username required"}), 400
    ok, msg = db.remove_user(username)
    return (jsonify({"message": msg}), 200) if ok else (jsonify({"error": msg}), 404)

@app.route("/api/students", methods=["GET"])
def api_students_list():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(db.get_all_students())

@app.route("/api/students", methods=["DELETE"])
def api_students_delete():
    if not require_admin_json():
        return jsonify({"error": "Unauthorized"}), 403
    d = request.get_json(force=True) or {}
    sid = d.get("id") or d.get("student_id")
    if not sid:
        return jsonify({"error": "student id required"}), 400
    ok, msg = db.remove_student(sid)
    return (jsonify({"message": msg}), 200) if ok else (jsonify({"error": msg}), 404)

@app.route("/api/records", methods=["GET"])
def api_records_list():
    if not require_admin_json():
        return jsonify({"error": "Unauthorized"}), 403
    date = request.args.get("date")
    course = request.args.get("course")
    records = db.get_all_records()
    if course:
        records = [r for r in records if r["course"] == course]
    if date:
        records = [r for r in records if r["timestamp"].startswith(date)]
    students = {s["id"]: s["name"] for s in db.get_all_students()}
    for r in records:
        r["student_name"] = students.get(r["student_id"], "N/A")
    return jsonify(records)

@app.route("/api/stats", methods=["GET"])
def api_stats():
    user = session.get("user")
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    payload = {"students": db.get_student_count()}
    if user["role"] == ROLE_ADMIN:
        payload["users"] = len(db.get_all_users())
    return jsonify(payload)

# ---------- Registration face detection preview ----------
@app.route("/api/detect_faces", methods=["POST"])
@requires_any_role([ROLE_LECTURER, ROLE_COURSE_REP])
def api_detect_faces():
    d = request.get_json(force=True) or {}
    img_data = d.get("image")
    if not img_data:
        return jsonify({"error": "image required"}), 400
    frame = decode_image(img_data)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    locs = face_recognition.face_locations(rgb)
    faces = [{"top": int(t), "right": int(r), "bottom": int(b), "left": int(l)} for (t, r, b, l) in locs]
    return jsonify({"faces": faces})

# ---------- Register student ----------
@app.route("/api/encode_face", methods=["POST"])
@requires_any_role([ROLE_LECTURER, ROLE_COURSE_REP])
def api_encode_face():
    d = request.get_json(force=True) or {}
    name, sid, img_data = d.get("name"), d.get("id"), d.get("image")
    if not all([name, sid, img_data]):
        return jsonify({"error": "name, id, image required"}), 400
    frame = decode_image(img_data)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    locs = face_recognition.face_locations(rgb)
    encs = face_recognition.face_encodings(rgb, locs)
    if not encs:
        return jsonify({"error": "No face detected"}), 400
    student = {"id": sid, "name": name, "face_encoding": encs[0].tolist()}
    ok, msg = db.add_student(student)
    return (jsonify({"message": msg}), 201) if ok else (jsonify({"error": msg}), 409)

# ---------- Take attendance: best-match + margin + 2-hit confirm ----------
@app.route("/api/recognize_face", methods=["POST"])
@requires_any_role([ROLE_LECTURER, ROLE_COURSE_REP])
def api_recognize_face():
    d = request.get_json(force=True) or {}
    course = d.get("course")
    img_data = d.get("image")
    if not course or not img_data:
        return jsonify({"error": "course and image required"}), 400
    user = session["user"]
    if not can_access_course(user, course):
        return jsonify({"error": "Unauthorized"}), 403

    ok_time, schedule, _ = is_within_schedule(course)
    if not ok_time:
        return jsonify({"error": "Not the scheduled time for this course.", "schedule": schedule}), 409

    frame = decode_image(img_data)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    locs = face_recognition.face_locations(rgb)
    encs = face_recognition.face_encodings(rgb, locs)

    students = db.get_all_students()
    known_encs = np.array([np.array(s["face_encoding"], dtype=np.float32) for s in students]) if students else np.empty((0,128))
    today = datetime.now().strftime("%Y-%m-%d")
    todays = db.get_attendance_for_day_and_course(course, today)
    already_present = {(r["student_id"], r["course"]) for r in todays if r["status"] == "present"}

    faces_out, recognized_new = [], []
    now_s = time.time()

    for (t, r, b, l), e in zip(locs, encs):
        label = "Unknown"
        known = False

        if len(known_encs) > 0:
            dists = face_recognition.face_distance(known_encs, e)
            best_idx = int(np.argmin(dists))
            best = float(dists[best_idx])
            second = float(np.partition(dists, 1)[1]) if len(dists) > 1 else 1.0

            if best < FACE_RECOGNITION_TOLERANCE and (second - best) >= SECOND_BEST_MARGIN:
                s = students[best_idx]
                label = f"{s['name']} ({s['id']})"
                known = True

                key = (s["id"], course)
                hits = _prune_seen(now_s, key)
                hits.append(now_s)
                RECENT_SEEN[key] = hits

                if key not in already_present and len(hits) >= CONFIRM_MIN_HITS:
                    db.record_attendance(s["id"], course, "present")
                    already_present.add(key)
                    recognized_new.append({
                        "student_id": s["id"],
                        "student_name": s["name"],
                        "course": course,
                        "timestamp": datetime.now().isoformat()
                    })

        faces_out.append({
            "top": int(t), "right": int(r), "bottom": int(b), "left": int(l),
            "label": label, "known": known
        })

    return jsonify({"faces": faces_out, "recent": recognized_new, "schedule": schedule})

# ---------- View course attendance ----------
@app.route("/attendance/<course_name>", methods=["GET"])
@requires_any_role([ROLE_LECTURER, ROLE_COURSE_REP])
def get_attendance_for_course(course_name):
    if not can_access_course(session["user"], course_name):
        return jsonify({"error": "Unauthorized"}), 403
    date = request.args.get("date")
    records = db.get_attendance_for_day_and_course(course_name, date) if date \
        else db.get_attendance_for_course(course_name)
    students = {s["id"]: s["name"] for s in db.get_all_students()}
    for r in records:
        r["student_name"] = students.get(r["student_id"], "N/A")
    return jsonify(records)

if __name__ == "__main__":
    app.config["SESSION_COOKIE_SECURE"] = False
    app.run(host="0.0.0.0", port=5000, debug=True)
