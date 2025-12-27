from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, Response
)
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
import csv
import io
import base64
import secrets
import os
import json

# ---------------------------
# App config
# ---------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "change_this_to_a_secure_key"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(BASE_DIR, "instance")
if not os.path.exists(instance_dir):
    os.makedirs(instance_dir)

db_path = os.path.join(instance_dir, "qr_attendance.db")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ---------------------------
# Models
# ---------------------------

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    batch = db.Column(db.String(50), nullable=False)
    course = db.Column(db.String(50), nullable=False)
    year = db.Column(db.String(20), nullable=False)
    device_id = db.Column(db.String(200), nullable=True)


class ClassSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course = db.Column(db.String(50), nullable=False)
    batch = db.Column(db.String(50), nullable=False)
    room = db.Column(db.String(50), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    teacher = db.relationship("Teacher", backref="sessions")


class QRSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_session_id = db.Column(db.Integer, db.ForeignKey("class_session.id"), nullable=False)
    token = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    active = db.Column(db.Boolean, default=True)

    class_session = db.relationship("ClassSession", backref="qr_codes")


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    class_session_id = db.Column(db.Integer, db.ForeignKey("class_session.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), default="Present", nullable=False)

    student = db.relationship("Student", backref="attendance")
    class_session = db.relationship("ClassSession", backref="attendance")


# ---------------------------
# Helpers
# ---------------------------

def create_default_admin():
    if Admin.query.first() is None:
        admin = Admin(username="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        print("Default admin created: admin/admin123")


def generate_qr(data: str) -> str:
    qr = qrcode.QRCode(box_size=8, border=3)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def login_required(role: str) -> bool:
    return session.get("role") == role


# ---------------------------
# Auth
# ---------------------------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_type = request.form.get("login_type")
        username = request.form.get("username")
        password = request.form.get("password")

        user = Admin.query.filter_by(username=username).first() if login_type == "admin" else Teacher.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session["role"] = login_type
            session["user_id"] = user.id
            return redirect(f"/{login_type}/dashboard")

        flash("Invalid credentials", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------
# Admin Panel
# ---------------------------

@app.route("/admin/dashboard")
def admin_dashboard():
    if not login_required("admin"):
        return redirect(url_for("login"))

    totals = {
        "students": Student.query.count(),
        "teachers": Teacher.query.count(),
        "sessions": ClassSession.query.count(),
        "attendance": Attendance.query.count()
    }
    return render_template("admin_dashboard.html", **totals)


@app.route("/admin/add_student", methods=["GET", "POST"])
def admin_add_student():
    if not login_required("admin"):
        return redirect(url_for("login"))

    if request.method == "POST":
        roll = request.form.get("roll")
        name = request.form.get("name")
        batch = request.form.get("batch")
        course = request.form.get("course")
        year = request.form.get("year")
        device_id = request.form.get("device_id")

        if Student.query.filter_by(roll_number=roll).first():
            flash("This roll number already exists!", "danger")
            return redirect(request.url)

        db.session.add(Student(
            roll_number=roll,
            name=name,
            batch=batch,
            course=course,
            year=year,
            device_id=device_id
        ))
        db.session.commit()
        flash("Student added!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_add_student.html")


@app.route("/admin/students")
def admin_students():
    if not login_required("admin"):
        return redirect(url_for("login"))
    return render_template("students_list.html", students=Student.query.all())


@app.route("/admin/create_session", methods=["GET", "POST"])
def admin_create_session():
    if not login_required("admin"):
        return redirect(url_for("login"))

    teachers = Teacher.query.all()

    if request.method == "POST":
        sess = ClassSession(
            course=request.form.get("course"),
            batch=request.form.get("batch"),
            room=request.form.get("room"),
            teacher_id=int(request.form.get("teacher")),
            date=datetime.strptime(request.form.get("date"), "%Y-%m-%d").date(),
            start_time=datetime.strptime(request.form.get("start"), "%H:%M").time(),
            end_time=datetime.strptime(request.form.get("end"), "%H:%M").time(),
        )
        db.session.add(sess)
        db.session.commit()
        flash("Session Created!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_create_session.html", teachers=teachers)


@app.route("/admin/view_sessions")
def admin_view_sessions():
    if not login_required("admin"):
        return redirect(url_for("login"))
    return render_template("view_sessions.html", sessions=ClassSession.query.all())


# ---------------------------
# NEW UPDATED QR GENERATE (students list included)
# ---------------------------

@app.route("/admin/generate_qr/<int:cid>")
def admin_generate_qr(cid):
    if not login_required("admin"):
        return redirect(url_for("login"))

    session_obj = ClassSession.query.get_or_404(cid)

    QRSession.query.filter_by(class_session_id=cid, active=True).update({"active": False})

    token = secrets.token_urlsafe(16)
    now = datetime.utcnow()
    expiry = now + timedelta(seconds=30)

    qs = QRSession(
        class_session_id=cid,
        token=token,
        created_at=now,
        expires_at=expiry,
        active=True
    )
    db.session.add(qs)
    db.session.commit()

    # Fetch students of this class
    students = Student.query.filter_by(
        batch=session_obj.batch,
        course=session_obj.course
    ).all()

    # QR Payload
    qr_payload = {
        "scan_url": f"{request.host_url.rstrip('/')}/scan?sid={qs.id}&token={token}",
        "class": session_obj.course,
        "batch": session_obj.batch,
        "students": [
            {"name": s.name, "roll": s.roll_number}
            for s in students
        ]
    }

    qr_img = generate_qr(json.dumps(qr_payload))

    return render_template("admin_qr.html", qr=qr_img, expires=expiry, class_session=session_obj)


# ---------------------------
# Student Scan (UPDATED MESSAGE)
# ---------------------------

@app.route("/scan", methods=["GET", "POST"])
def student_scan():
    sid = request.args.get("sid")
    token = request.args.get("token")

    if not sid or not token:
        return "Invalid QR parameters", 400

    qs = QRSession.query.get(sid)
    if not qs or qs.token != token or not qs.active:
        return "Invalid or inactive QR session", 400

    if datetime.utcnow() > qs.expires_at:
        return "QR expired", 400

    class_sess = qs.class_session

    if request.method == "POST":
        roll = request.form.get("roll")

        student = Student.query.filter_by(
            roll_number=roll,
            batch=class_sess.batch,
            course=class_sess.course
        ).first()

        if not student:
            flash("Invalid Student", "danger")
            return redirect(request.url)

        if Attendance.query.filter_by(student_id=student.id, class_session_id=class_sess.id).first():
            return "Attendance already marked"

        db.session.add(Attendance(student_id=student.id, class_session_id=class_sess.id))
        db.session.commit()

        return render_template("student_success.html", student=student, class_session=class_sess)

    return render_template("student_scan.html", class_session=class_sess)


# ---------------------------
# Teacher Panel
# ---------------------------

@app.route("/teacher/dashboard")
def teacher_dashboard():
    if not login_required("teacher"):
        return redirect(url_for("login"))
    teacher_id = session.get("user_id")
    today = datetime.utcnow().date()
    sessions = ClassSession.query.filter_by(teacher_id=teacher_id, date=today).all()
    return render_template("teacher_dashboard.html", sessions=sessions)


@app.route("/teacher/session/<int:cid>")
def teacher_session(cid):
    if not login_required("teacher"):
        return redirect(url_for("login"))
    records = Attendance.query.filter_by(class_session_id=cid).all()
    return render_template("teacher_attendance.html", records=records)


# ---------------------------
# Init
# ---------------------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        create_default_admin()

    app.run(host="0.0.0.0", port=5000, debug=True)
