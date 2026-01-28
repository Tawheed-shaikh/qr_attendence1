from flask import Flask, render_template, request, redirect, session, flash, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode, io, base64, secrets, os

SERVER_IP = "192.168.0.101"

# -----------------------
# SERVER_IPS = [
#     "192.168.0.101",  
#     # "192.168.1.5",  
#     # "127.0.0.1"     
# ]                                     ONLY IF USING MULTIPLY IP
# SERVER_PORT = 5000
# -------------------------


# ---------------------------
# Auto detect local IP
# ---------------------------
# def get_local_ip():
#     s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     try:
#         s.connect(("8.8.8.8", 80))
#         ip = s.getsockname()[0]
#     except:
#         ip = "127.0.0.1"
#     finally:
#         s.close()
#     return ip                                 FOR AUTO DETECT LOCAL IP
                                    
# SERVER_IP = get_local_ip()


# ---------------------------
# App config
# ---------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "secure_key_change_later"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(BASE_DIR, "instance")
os.makedirs(instance_dir, exist_ok=True)

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


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    course = db.Column(db.String(100), nullable=False)
    year = db.Column(db.String(20), nullable=False)


class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class ClassSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course = db.Column(db.String(50), nullable=False)
    room = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False)
    teacher = db.relationship("Teacher")


class QRSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_session_id = db.Column(db.Integer, db.ForeignKey("class_session.id"))
    token = db.Column(db.String(200))
    expires_at = db.Column(db.DateTime)
    active = db.Column(db.Boolean, default=True)


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"))
    class_session_id = db.Column(db.Integer, db.ForeignKey("class_session.id"))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------------------
# Helpers
# ---------------------------

def admin_required():
    return session.get("admin") is True


def generate_qr(data):
    qr = qrcode.make(data)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

# ---------------------------
# Auth
# ---------------------------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        admin = Admin.query.filter_by(username=request.form["username"]).first()
        if admin and admin.check_password(request.form["password"]):
            session["admin"] = True
            return redirect("/admin/dashboard")
        flash("Invalid login")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------------------
# Admin Dashboard
# ---------------------------

@app.route("/admin/dashboard")
def admin_dashboard():
    if not admin_required():
        return redirect("/")
    return render_template(
        "admin_dashboard.html",
        total_students=Student.query.count(),
        total_teachers=Teacher.query.count(),
        total_sessions=ClassSession.query.count(),
        total_attendance=Attendance.query.count()
    )

# ---------------------------
# Students
# ---------------------------

@app.route("/admin/add_student", methods=["GET", "POST"])
def admin_add_student():
    if not admin_required():
        return redirect("/")

    if request.method == "POST":
        if Student.query.filter_by(roll_no=request.form["roll_no"]).first():
            flash("Roll number already exists")
            return redirect(request.url)

        s = Student(
            roll_no=request.form["roll_no"],
            name=request.form["name"],
            course=request.form["course"],
            year=request.form["year"]
        )
        db.session.add(s)
        db.session.commit()
        return redirect("/admin/students")

    return render_template("admin_add_student.html")


@app.route("/admin/students")
def view_students():
    if not admin_required():
        return redirect("/")
    return render_template("student_list.html", students=Student.query.all())


@app.route("/admin/delete_student/<int:id>")
def delete_student(id):
    if not admin_required():
        return redirect("/")
    Student.query.filter_by(id=id).delete()
    db.session.commit()
    return redirect("/admin/students")

# ---------------------------
# Teachers
# ---------------------------

@app.route("/admin/add_teacher", methods=["GET", "POST"])
def admin_add_teacher():
    if not admin_required():
        return redirect("/")

    if request.method == "POST":
        if Teacher.query.filter_by(username=request.form["username"]).first():
            flash("Username already exists")
            return redirect(request.url)

        t = Teacher(
            name=request.form["name"],
            username=request.form["username"]
        )
        t.set_password(request.form["password"])

        db.session.add(t)
        db.session.commit()
        return redirect("/admin/dashboard")

    return render_template("admin_add_teacher.html")

@app.route("/admin/teachers")
def view_teachers():
    if not admin_required():
        return redirect("/")
    teachers = Teacher.query.all()
    return render_template("view_teachers.html", teachers=teachers)


# ---------------------------
# Sessions
# ---------------------------

@app.route("/admin/create_session", methods=["GET", "POST"])
def admin_create_session():
    if not admin_required():
        return redirect("/")

    teachers = Teacher.query.all()

    if request.method == "POST":
        cs = ClassSession(
            course=request.form["course"],
            room=request.form["room"],
            date=datetime.strptime(request.form["date"], "%Y-%m-%d").date(),
            start_time=datetime.strptime(request.form["start"], "%H:%M").time(),
            end_time=datetime.strptime(request.form["end"], "%H:%M").time(),
            teacher_id=request.form["teacher"]
        )
        db.session.add(cs)
        db.session.commit()
        return redirect("/admin/view_sessions")

    return render_template("admin_create_session.html", teachers=teachers)


@app.route("/admin/view_sessions")
def view_sessions():
    if not admin_required():
        return redirect("/")
    return render_template("view_session.html", sessions=ClassSession.query.all())

# ---------------------------
# QR
# ---------------------------

@app.route("/admin/generate_qr/<int:id>")
def generate_qr_route(id):
    if not admin_required():
        return redirect("/")

    cs = ClassSession.query.get_or_404(id)

    token = secrets.token_urlsafe(16)
    qr = QRSession(
        class_session_id=id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(seconds=30),
        active=True
    )
    db.session.add(qr)
    db.session.commit()

    img = generate_qr(f"http://{SERVER_IP}:5000/scan/{qr.id}/{token}")

    return render_template("admin_qr.html", qr=img, expires=qr.expires_at, class_session=cs)

# ---------------------------
# Scan
# ---------------------------

@app.route("/scan/<int:id>/<token>", methods=["GET", "POST"])
def scan(id, token):
    qr = QRSession.query.get(id)
    if not qr or qr.token != token or datetime.utcnow() > qr.expires_at:
        return "QR Invalid or Expired"

    cs = ClassSession.query.get(qr.class_session_id)

    if request.method == "POST":
        student = Student.query.filter_by(roll_no=request.form["roll_no"]).first()
        if not student:
            return "Invalid Student"

        if Attendance.query.filter_by(student_id=student.id, class_session_id=cs.id).first():
            return "Already marked"

        db.session.add(Attendance(student_id=student.id, class_session_id=cs.id))
        db.session.commit()
        return render_template("student_success.html", student=student, class_session=cs)

    return render_template("student_scan.html", class_session=cs)

# ---------------------------
# Export
# ---------------------------

@app.route("/admin/export", methods=["GET", "POST"])
def export_attendance():
    if not admin_required():
        return redirect("/")

    if request.method == "POST":
        rows = Attendance.query.all()

        def generate():
            yield "Roll,Name,Course,Date\n"
            for a in rows:
                s = Student.query.get(a.student_id)
                cs = ClassSession.query.get(a.class_session_id)
                yield f"{s.roll_no},{s.name},{s.course},{cs.date}\n"

        return Response(
            generate(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=attendance.csv"}
        )

    return render_template("export_attendance.html")

# ---------------------------
# Init
# ---------------------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if not Admin.query.first():
            admin = Admin(username="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
    app.run(host="0.0.0.0", port=5000, debug=True)

