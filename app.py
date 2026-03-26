import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_mail import Mail, Message
from werkzeug.security import check_password_hash, generate_password_hash
from pymongo import MongoClient
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from bson import ObjectId
from datetime import datetime

# 1. LOAD environment variables FIRST
load_dotenv()

app = Flask(__name__)

# 2. SET CONFIGURATIONS
app.secret_key = os.getenv('SECRET_KEY', 'super_secret_school_key')

# --- PRODUCTION EMAIL CONFIG (Port 465 for Render) ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

# --- UPLOAD CONFIGURATION ---
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
# Create folder after UPLOAD_FOLDER is defined
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 3. INITIALIZE SERVICES
mail = Mail(app)

# 4. DATABASE CONNECTION
# 4. DATABASE CONNECTION
atlas_uri = os.getenv("MONGO_URI")
client = None
db = None # Initialize to None so the attribute always exists for Mocks

try:
    if not atlas_uri:
        raise ValueError("MONGO_URI environment variable is not set!")
        
    client = MongoClient(atlas_uri)
    db = client["school"]
    
    # Optional: Ping the database to verify connection
    client.admin.command('ping')
    print("Successfully connected to MongoDB Atlas")
    
except Exception as e:
    print(f"CRITICAL DATABASE ERROR: {e}")
    # In a real app, you might want to use a dummy/local DB here 
    # if you want the app to still "start" without a cloud connection.

# ================= ROUTES =================
# ... your respond_support and other routes go here ...

@app.route("/respond_support", methods=["POST"])
def respond_support():
    # 1. Security Check
    if str(session.get("user_role")).lower() != "teacher":
        return redirect(url_for('login', error="Please log in as a teacher"))

    # 2. Extract Data
    message_id = request.form.get("message_id") or request.args.get("id")
    user_email = request.form.get("user_email")
    user_name = request.form.get("user_name")
    original_msg = request.form.get("original_msg")
    teacher_response = request.form.get("response")

    try:
        # 3. Create and Send Email
        msg = Message(
            subject=f"Support Reply: {user_name}",
            recipients=[user_email],
            body=f"Hello {user_name},\n\nRegarding: '{original_msg}'\n\nResponse: {teacher_response}"
        )
        mail.send(msg)

        # 4. Update Database
        db.support_messages.update_one(
            {"_id": ObjectId(message_id)},
            {"$set": {"status": "replied", "response": teacher_response}}
        )

        return redirect(url_for('teacher_support', message="Response sent successfully!"))

    except Exception as e:
        # THIS IS THE KEY: It will show the REAL error on your screen instead of 'Internal Server Error'
        return f"<h1>Detailed Error Info:</h1><p>{str(e)}</p><a href='/teacher/support'>Go Back</a>"    
    
# ================= INSTITUTIONAL PAGES =================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/courses")
def courses():
    return render_template("courses.html")

# ================= CONTACT & HELPERS =================
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        contact_data = {
            "full_name": request.form.get("full_name"),
            "email": request.form.get("email"),
            "message": request.form.get("message"),
            "timestamp": datetime.now().strftime("%d %b %Y, %H:%M"),
            "status": "unread"
        }
        db.support_messages.insert_one(contact_data)
        return render_template("thanks1.html")
    return render_template("contact.html")

# ================= CALENDAR MANAGEMENT =================
@app.route("/calendar", methods=["GET", "POST"])
def calendar():
    events = list(db.calendar_events.find().sort("date", 1))
    return render_template("calendar.html", events=events)

@app.route("/add_calendar_event", methods=["POST"])
def add_calendar_event():
    if session.get('user_role') == 'teacher':
        new_event = {
            "date": request.form.get("date"),
            "description": request.form.get("description"),
            "category": request.form.get("category"),
            "viewed": False
        }
        db.calendar_events.insert_one(new_event)
    return redirect(url_for('calendar'))

@app.route("/delete_calendar_event/<id>")
def delete_calendar_event(id):
    if session.get('user_role') == 'teacher':
        db.calendar_events.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('calendar'))

# ================= AUTHENTICATION =================
@app.route("/login", methods=["GET", "POST"])
def login():
    message = request.args.get('message')

    if request.method == "POST":
        role = request.form.get("role")
        username = request.form.get("username")
        password = request.form.get("password")

        try:
            user = db.users.find_one({
                "username": username,
                "role": role
            })
        except Exception:
            return "Database Error! Please try again later.", 500

        if user:
            is_valid = False

            if user.get("role") == "admin":
                is_valid = check_password_hash(user["password"], password)
            else:
                is_valid = (user["password"] == password)

            if is_valid:
                session["user_role"] = user["role"]
                session["username"] = user["username"]
                return redirect(url_for("dashboard"))
            else:
                safe_role = role.capitalize() if role else "User"
                return f"Invalid Credentials for {safe_role}! <a href='/login'>Try again</a>"
        else:
            safe_role = role.capitalize() if role else "User"
            return f"Invalid Credentials for {safe_role}! <a href='/login'>Try again</a>"

    return render_template("login.html", message=message)
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

#=================change_password -----------------
@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        current_pass = request.form.get("current_password")
        new_pass = request.form.get("new_password")
        confirm_pass = request.form.get("confirm_password")
        role = session.get('user_role')

        # FIXED: Fetch user by username only to verify the current password logic
        user = db.users.find_one({"username": session['username']})

        if user:
            # Check if current password is valid (Hash for admin, plain for others)
            is_valid = False
            if role == "admin":
                is_valid = check_password_hash(user["password"], current_pass)
            else:
                is_valid = (user["password"] == current_pass)

            if not is_valid:
                return render_template("change_password.html", error="Current password is incorrect.")

            if new_pass != confirm_pass:
                return render_template("change_password.html", error="New passwords do not match.")

            # Update the password
            db.users.update_one(
                {"username": session['username']},
                {"$set": {"password": new_pass}}
            )

            # LOGOUT LOGIC: Clear session and redirect to login
            session.clear()
            return redirect(url_for('login', message="Password updated! Please log in again."))

    return render_template("change_password.html")

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "user_role" not in session:
        return redirect(url_for("login"))
    
    new_applicants = []
    notif_count = 0
    support_count = 0

    if session.get('user_role') == 'teacher':
        new_applicants = list(db.admissions.find({"viewed": False}))
        notif_count = len(new_applicants)
        support_count = db.support_messages.count_documents({"status": "unread"})
    
    return render_template(
        "dashboard.html",
        user_role=session["user_role"],
        notif_count=notif_count,
        new_applicants=new_applicants,
        support_count=support_count
    )

@app.route("/clear_notifications")
def clear_notifications():
    if session.get('user_role') == 'teacher':
        db.admissions.update_many({"viewed": False}, {"$set": {"viewed": True}})
    return redirect(url_for("dashboard"))

# ================= ADMISSIONS =================
@app.route("/admission", methods=["GET", "POST"])
def admission():
    if request.method == "POST":
        photo_path = None
        file = request.files.get('student_photo')
        
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            photo_path = f"/static/uploads/{unique_name}"

        admission_data = {
            "full_name": request.form.get("full_name"),
            "parent_name": request.form.get("parent_name"),
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
            "dob": request.form.get("dob"),
            "course": request.form.get("course"),
            "address": request.form.get("address"),
            "photo_path": photo_path,
            "status": "Pending",
            "viewed": False 
        }
        
        db.admissions.insert_one(admission_data)
        return render_template("thanks.html")
    
    return render_template("admission.html")

@app.route("/approve_admission/<id>", methods=["POST"])
def approve_admission(id):
    if session.get('user_role') == 'teacher':
        applicant = db.admissions.find_one({"_id": ObjectId(id)})
        
        if applicant:
            db.students.insert_one({
                "name": applicant.get('full_name'),
                "username": applicant.get('email'),
                "roll_no": "REG-" + str(datetime.now().microsecond)[:5],
                "class": applicant.get('course'),
                "section": "A",
                "email": applicant.get('email'),
                "phone": applicant.get('phone'),
                "dob": applicant.get('dob'),
                "address": applicant.get('address'),
                "parent_name": applicant.get('parent_name'),
                "photo_path": applicant.get('photo_path'),
                "admission_date": datetime.now().strftime("%Y-%m-%d")
            })
            db.admissions.delete_one({"_id": ObjectId(id)})
            
    return redirect(url_for('dashboard'))

# ================= ATTENDANCE =================
@app.route("/attendance")
def attendance():
    if "user_role" not in session:
        return redirect(url_for("login"))
    
    today_str = datetime.now().strftime("%d %B %Y")
    today_date = datetime.now().strftime("%Y-%m-%d")
    classes = [str(i) for i in range(1,11)]
    
    selected_class = request.args.get('class_no')
    
    if selected_class:
        attendance_list = list(db.attendance.find({"class": selected_class}).sort("date", -1))
    else:
        attendance_list = list(db.attendance.find().sort("date", -1).limit(20))
    
    return render_template("attendance.html", 
                           attendance_list=attendance_list, 
                           today=today_str, 
                           today_date=today_date,
                           selected_class=selected_class,
                           classes=classes)

@app.route("/delete_attendance/<id>")
def delete_attendance(id):
    if session.get("user_role") != "teacher":
        return "Unauthorized Action", 403
        
    record = db.attendance.find_one({"_id": ObjectId(id)})
    target_class = record.get('class') if record else None
    db.attendance.delete_one({"_id": ObjectId(id)})
    
    if target_class:
        return redirect(url_for("attendance", class_no=target_class))
    return redirect(url_for("attendance"))

@app.route("/submit_attendance", methods=["POST"])
def submit_attendance():
    if session.get('user_role') == 'teacher':
        class_name = request.form.get('class_name')
        attendance_date = request.form.get('attendance_date')
        student_ids = request.form.getlist('student_ids')
        present_ids = request.form.getlist('attendance_status')

        attendance_records = []
        for s_id in student_ids:
            student = db.students.find_one({"_id": ObjectId(s_id)})
            if student:
                status = "Present" if s_id in present_ids else "Absent"
                attendance_records.append({
                    "student_name": student['name'],
                    "class": class_name,
                    "status": status,
                    "date": attendance_date,
                    "marked_by": session.get('username')
                })

        if attendance_records:
            db.attendance.insert_many(attendance_records)
            
    return redirect(url_for('attendance'))

# ================= STUDENT MANAGEMENT =================
@app.route("/students", methods=["GET", "POST"])
def students():
    if "user_role" not in session:
        return redirect(url_for("login"))
    
    selected_class = request.args.get("class")
    selected_batch = request.args.get("batch")
    search_query = request.args.get("search")

    query = {}
    if selected_class: query["class"] = selected_class
    if selected_batch:
        if selected_batch == "Unassigned": query["batch"] = {"$exists": False}
        else: query["batch"] = selected_batch
    if search_query: query["name"] = {"$regex": search_query, "$options": "i"}

    grouped_students = {}

    if selected_class or selected_batch or search_query:
        raw_students = list(db.students.find(query))

        def get_sort_key(s):
            b = s.get('batch')
            if not b or str(b).lower() in ['none', '', 'unassigned']:
                return (0, 0)
            try: return (1, 3000 - int(b))
            except: return (2, str(b))

        raw_students.sort(key=get_sort_key)

        for s in raw_students:
            batch_name = s.get('batch')
            if not batch_name or str(batch_name).lower() in ['none', '', 'unassigned']:
                batch_name = "Unassigned"
            
            if batch_name not in grouped_students:
                grouped_students[batch_name] = []
            grouped_students[batch_name].append(s)

    db_batches = db.students.distinct("batch")
    years = sorted([int(x) for x in db_batches if str(x).isdigit()], reverse=True)
    available_batches = [str(y) for y in years]
    if db.students.find_one({"batch": {"$exists": False}}) or "Unassigned" in db_batches:
        if "Unassigned" not in available_batches: available_batches.insert(0, "Unassigned")
    
    return render_template("students.html", 
                           grouped_students=grouped_students, 
                           batches=available_batches)

@app.route("/delete_student/<id>")
def delete_student(id):
    if session.get("user_role") != "teacher": return "Unauthorized", 403
    db.students.delete_one({"_id": ObjectId(id)})
    return redirect(url_for("students"))

@app.route("/update_student", methods=["POST"])
def update_student():
    if session.get("user_role") != "teacher": 
        return "Unauthorized", 403
    
    student_id = request.form.get("id")
    name = request.form.get("name")
    cls = request.form.get("class")
    batch = request.form.get("batch")

    db.students.update_one(
        {"_id": ObjectId(student_id)},
        {"$set": {
            "name": name,
            "roll_no": request.form.get("roll"),
            "class": cls,
            "section": request.form.get("section"),
            "batch": str(batch) if batch else "Unassigned"
        }}
    )
    return redirect(url_for('students', search=name))

@app.route("/get_student_performance/<name>")
def get_student_performance(name):
    try:
        clean_search = name.strip()
        selected_class = request.args.get('class') 

        student_query = {"name": {"$regex": clean_search, "$options": "i"}}
        if selected_class and selected_class != "":
            student_query["class"] = selected_class

        students = list(db.students.find(student_query))
        student_ids = [str(s['_id']) for s in students]

        if not student_ids:
            return jsonify([])

        marks_query = {"student_id": {"$in": student_ids}}
        if selected_class and selected_class != "":
            marks_query["class"] = selected_class

        marks = list(db.marks.find(marks_query))

        results = []
        for m in marks:
            results.append({
                "subject": m.get("subject", "N/A"),
                "exam": m.get("exam", "N/A"),
                "marks": m.get("marks", 0),
                "status": m.get("status", "N/A")
            })
        
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/fix_na_statuses")
def fix_na_statuses():
    db.marks.update_many({"status": {"$exists": False}, "marks": {"$gte": "33"}}, {"$set": {"status": "PASS"}})
    db.marks.update_many({"status": {"$exists": False}, "marks": {"$lt": "33"}}, {"$set": {"status": "FAIL"}})
    return "All N/A records have been updated based on marks!"

@app.route("/fix_old_statuses")
def fix_old_statuses():
    db.marks.update_many({"status": {"$exists": False}, "marks": {"$gte": 35}}, {"$set": {"status": "PASS"}})
    db.marks.update_many({"status": {"$exists": False}, "marks": {"$lt": 35}}, {"$set": {"status": "FAIL"}})
    return "Old records updated!"

@app.route("/student_profile/<id>")
def student_profile(id):
    if "user_role" not in session:
        return redirect(url_for("login"))

    student = db.students.find_one({"_id": ObjectId(id)})
    if not student:
        return "Student not found", 404

    user_role = session.get('user_role')
    username = session.get('username')

    if user_role == 'student':
        if username != student.get('username'):
            return "Access Denied: You can only view your own profile.", 403
            
    elif user_role == 'parent':
        if username != student.get('parent_username'):
            return "Access Denied: You can only view your child's profile.", 403

    marks = list(db.marks.find({"student_id": id}).sort([("exam",1)]))
    total_days = db.attendance.count_documents({"student_name": student['name']})
    present_days = db.attendance.count_documents({"student_name": student['name'], "status": "Present"})
    
    attendance_pct = 0
    if total_days > 0:
        attendance_pct = round((present_days / total_days) * 100, 2)

    return render_template("student_details.html", student=student, marks=marks, attendance_pct=attendance_pct, total_days=total_days)

@app.route("/update_student_full", methods=["POST"])
def update_student_full():
    if session.get('user_role') == 'teacher':
        student_id = request.form.get("id")
        updated_data = {
            "name": request.form.get("name"),
            "username": request.form.get("username"),
            "parent_username": request.form.get("parent_username"),
            "parent_name": request.form.get("parent_name"),
            "roll_no": request.form.get("roll"),
            "class": request.form.get("class"),
            "batch": request.form.get("batch"),
            "dob": request.form.get("dob"),
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
            "address": request.form.get("address")
        }
        
        file = request.files.get('profile_photo')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            unique_filename = f"{student_id}_{filename}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(save_path)
            updated_data["photo_path"] = f"/static/uploads/{unique_filename}"
        
        db.students.update_one({"_id": ObjectId(student_id)}, {"$set": updated_data})
        return redirect(url_for('student_profile', id=student_id))
    return redirect(url_for('login'))

@app.route("/bulk_promote", methods=["POST"])
def bulk_promote():
    if session.get("user_role") != "teacher":
        return "Unauthorized", 403
    source_class = request.form.get("source_class")
    new_batch = request.form.get("new_batch")
    if source_class and new_batch:
        result = db.students.update_many({"class": source_class}, {"$set": {"batch": new_batch}})
        message = f"Successfully moved {result.modified_count} students to Batch {new_batch}!"
        return redirect(url_for('students', message=message))
    return redirect(url_for('students', error="Invalid selection"))

# ================= MARKS =================
@app.route("/marks", methods=["GET", "POST"])
def marks():
    if "user_role" not in session: return redirect(url_for("login"))
    if request.method == "POST":
        if session.get("user_role") != "teacher": return "Unauthorized", 403
        student_ids = request.form.getlist('student_ids')
        marks_values = request.form.getlist('marks_list')
        status_values = request.form.getlist('status_list')
        subject = request.form.get("subject")
        class_name = request.form.get("class")
        exam = request.form.get("exam")
        records = [{"student_id": student_ids[i], "class": class_name, "subject": subject, "marks": marks_values[i], "status": status_values[i], "exam": exam} for i in range(len(student_ids)) if i < len(marks_values) and marks_values[i]]
        if records: db.marks.insert_many(records)
        return redirect(url_for("marks", class_no=class_name, subject=subject))

    selected_class = request.args.get("class_no")
    selected_subject = request.args.get("subject")
    query = {}
    if selected_class: query["class"] = selected_class
    if selected_subject: query["subject"] = selected_subject
    marks_list = list(db.marks.find(query)) if query else []
    students_map = {str(s["_id"]): s["name"] for s in db.students.find()}
    for m in marks_list: m["student_name"] = students_map.get(m["student_id"], "Unknown")
    return render_template("marks.html", marks_list=marks_list, selected_class=selected_class, selected_subject=selected_subject)

@app.route("/delete_mark/<id>")
def delete_mark(id):
    if session.get("user_role") != "teacher": return "Unauthorized Action", 403
    db.marks.delete_one({"_id": ObjectId(id)})
    return redirect(url_for("marks"))

@app.route("/update_marks", methods=["POST"])
def update_marks():
    if session.get("user_role") != "teacher": return "Unauthorized", 403
    mark_id = request.form.get("id")
    class_val = request.form.get("class") 
    db.marks.update_one({"_id": ObjectId(mark_id)}, {"$set": {"subject": request.form.get("subject"), "marks": request.form.get("marks"), "exam": request.form.get("exam"), "status": request.form.get("status")}})
    return redirect(url_for("marks", class_no=class_val))

# ================= TIMETABLE =================
@app.route("/timetable", methods=["GET","POST"])
def timetable():
    if "user_role" not in session: return redirect(url_for("login"))
    if request.method == "POST":
        if session.get("user_role") != "teacher": return "Unauthorized", 403
        db.timetable.insert_one({"class": request.form["class"], "time": request.form["time"], "monday": request.form["monday"], "tuesday": request.form["tuesday"], "wednesday": request.form["wednesday"], "thursday": request.form["thursday"], "friday": request.form["friday"]})
        return redirect(url_for("timetable", class_name=request.form["class"]))

    selected_class = request.args.get("class_name")
    timetable_data = list(db.timetable.find({"class": selected_class})) if selected_class else []
    return render_template("timetable.html", classes=[str(i) for i in range(1,11)], selected_class=selected_class, timetable=timetable_data)

@app.route("/delete_timetable/<id>")
def delete_timetable(id):
    if session.get("user_role") != "teacher": return "Unauthorized", 403
    record = db.timetable.find_one({"_id": ObjectId(id)})
    class_to_return = record.get('class') if record else None
    db.timetable.delete_one({"_id": ObjectId(id)})
    return redirect(url_for("timetable", class_name=class_to_return) if class_to_return else url_for("timetable"))

@app.route("/update_timetable", methods=["POST"])
def update_timetable():
    if session.get("user_role") != "teacher": return "Unauthorized", 403
    timetable_id = request.form.get("id")
    class_val = request.form.get("class")
    db.timetable.update_one({"_id": ObjectId(timetable_id)}, {"$set": {"class": class_val, "time": request.form.get("time"), "monday": request.form.get("monday"), "tuesday": request.form.get("tuesday"), "wednesday": request.form.get("wednesday"), "thursday": request.form.get("thursday"), "friday": request.form.get("friday")}})
    return redirect(url_for("timetable", class_name=class_val))

# ================= SUPPORT =================
@app.route("/teacher/support")
def teacher_support():
    if session.get("user_role") != "teacher": return "403 Forbidden", 403
    messages = list(db.support_messages.find().sort("_id", -1))
    return render_template("teacher_support.html", messages=messages)

# @app.route("/respond_support/<id>", methods=["POST"])
# def respond_support(id):
#     if session.get('user_role') == 'teacher':
#         response_text = request.form.get("response")
#         db.support_messages.update_one({"_id": ObjectId(id)}, {"$set": {"response": response_text, "status": "replied"}})
#     return redirect(url_for('teacher_support'))

@app.route("/delete_support/<id>")
def delete_support(id):
    if session.get('user_role') == 'teacher':
        db.support_messages.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('teacher_support'))

# ================= API & EXTRAS =================
@app.route("/get_students/<class_no>")
def get_students(class_no):
    batch = request.args.get('batch')
    query = {"class": class_no}
    if batch and batch != "": query["batch"] = batch
    students_cursor = db.students.find(query)
    return jsonify([{"id": str(s["_id"]), "name": s["name"]} for s in students_cursor])

@app.route('/library')
def library():
    return render_template('library.html', resources=db.resources.find())

@app.route('/careers')
def careers():
    return render_template('careers.html')

@app.route('/apply', methods=['POST'])
def apply():
    db.applications.insert_one({"name": request.form.get("name"), "position": request.form.get("position"), "timestamp": datetime.now()})
    return redirect(url_for('careers'))

# ================= ADMIN MANAGEMENT =================
@app.route("/admin/manage_users", methods=["GET", "POST"])
def manage_users():
    if session.get('user_role') != 'admin': return "Unauthorized Access", 403
    if request.method == "POST":
        new_username = request.form.get("username")
        new_password = request.form.get("password")
        assigned_role = request.form.get("role")
        if not db.users.find_one({"username": new_username}):
            db.users.insert_one({"username": new_username, "password": new_password, "role": assigned_role, "created_at": datetime.now()})
        return redirect(url_for('manage_users'))
    return render_template("admin_manage.html", users=list(db.users.find()))

@app.route("/delete_user/<id>")
def delete_user(id):
    if session.get('user_role') == 'admin': db.users.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('manage_users'))

#========= FIx database ===========================
@app.route("/fix_database")
def fix_database():
    result = db.students.update_many({"batch": {"$exists": False}}, {"$set": {"batch": "2026"}})
    return f"Updated {result.modified_count} students to Batch 2026!"

@app.route("/assign_batches")
def assign_batches():
    db.students.update_many({"batch": {"$exists": False}}, {"$set": {"batch": "2025"}})
    return "Existing students moved to Batch 2025!"

@app.route("/debug_batch")
def debug_batch():
    db.students.update_many({}, {"$set": {"batch": "2025"}})
    return "All students are now Batch 2025. The filter should now work!"

if __name__=="__main__":
    app.run(debug=True)