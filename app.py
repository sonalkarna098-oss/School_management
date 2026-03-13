import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime

app = Flask(__name__)
app.secret_key = "super_secret_school_key"

# ================= DATABASE =================
atlas_uri = os.getenv("MONGO_URLI")

try:
    client = MongoClient(atlas_uri)
    db = client["management"]
    # Verify connection
    client.admin.command('ping')
    print("Successfully connected to MongoDB Atlas (Database: management)")
except Exception as e:
    print(f"Error connecting to MongoDB Atlas: {e}")
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
        return "<h3>Thank you! We will contact you shortly.</h3><a href='/'>Return Home</a>"
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
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")

        if db.users.find_one({"username": username}):
            return "User already exists! <a href='/signup'>Try again</a>"

        db.users.insert_one({
            "username": username,
            "password": password, 
            "role": role
        })
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role")
        username = request.form.get("username")
        password = request.form.get("password")

        user = db.users.find_one({
            "username": username,
            "password": password,
            "role": role
        })

        if user:
            session["user_role"] = user["role"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        else:
            return f"Invalid Credentials for {role.capitalize()}! <a href='/login'>Try again</a>"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

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
        admission_data = {
            "full_name": request.form.get("full_name"),
            "email": request.form.get("email"),
            "course": request.form.get("course"),
            "status": "Pending",
            "viewed": False 
        }
        db.admissions.insert_one(admission_data)
        return render_template("thanks.html")
    return render_template("admission.html")

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
            # Check against student master or user collection based on your logic
            # Here we check the students collection to get the name
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
@app.route("/students", methods=["GET","POST"])
def students():
    if "user_role" not in session: return redirect(url_for("login"))
    
    if request.method == "POST":
        if session.get("user_role") != "teacher": return "Unauthorized Action", 403
            
        db.students.insert_one({
            "name": request.form["name"],
            "roll_no": request.form["roll"],
            "class": request.form["class"],
            "section": request.form["section"]
        })
        return redirect(url_for("students"))

    selected_class = request.args.get("class")
    students_list = list(db.students.find({"class": selected_class})) if selected_class else list(db.students.find())
    return render_template("students.html", students=students_list)

@app.route("/delete_student/<id>")
def delete_student(id):
    if session.get("user_role") != "teacher": return "Unauthorized", 403
    db.students.delete_one({"_id": ObjectId(id)})
    return redirect(url_for("students"))

@app.route("/update_student", methods=["POST"])
def update_student():
    if session.get("user_role") != "teacher": return "Unauthorized", 403
    student_id = request.form.get("id")
    db.students.update_one(
        {"_id": ObjectId(student_id)},
        {"$set": {
            "name": request.form["name"],
            "roll_no": request.form["roll"],
            "class": request.form["class"],
            "section": request.form["section"]
        }}
    )
    return redirect(url_for("students"))

# ================= MARKS =================
@app.route("/marks", methods=["GET", "POST"])
def marks():
    if "user_role" not in session: 
        return redirect(url_for("login"))
    
    if request.method == "POST":
        if session.get("user_role") != "teacher": 
            return "Unauthorized", 403
        
        # FIX: Get lists from the form instead of a single ID
        student_ids = request.form.getlist('student_ids')
        marks_values = request.form.getlist('marks_list')
        subject = request.form.get("subject")
        class_name = request.form.get("class")
        exam = request.form.get("exam")

        records = []
        # Loop through the lists and match ID with Mark
        for i in range(len(student_ids)):
            # Only add if a mark was actually entered
            if marks_values[i]:
                records.append({
                    "student_id": student_ids[i],
                    "class": class_name,
                    "subject": subject,
                    "marks": marks_values[i],
                    "exam": exam
                })
        
        if records:
            db.marks.insert_many(records)
            
        return redirect(url_for("marks", class_no=class_name, subject=subject))

    selected_class = request.args.get("class_no")
    selected_subject = request.args.get("subject")
    query = {}
    if selected_class: query["class"] = selected_class
    if selected_subject: query["subject"] = selected_subject

    marks_list = list(db.marks.find(query)) if query else []
    students_map = {str(s["_id"]): s["name"] for s in db.students.find()}
    for m in marks_list:
        m["student_name"] = students_map.get(m["student_id"], "Unknown")

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
    db.marks.update_one(
        {"_id": ObjectId(mark_id)},
        {"$set": {
            "subject": request.form["subject"],
            "marks": request.form["marks"],
            "exam": request.form["exam"]
        }}
    )
    return redirect(url_for("marks", class_no=request.form["class"]))

# ================= TIMETABLE =================
@app.route("/timetable", methods=["GET","POST"])
def timetable():
    if "user_role" not in session: return redirect(url_for("login"))
    
    if request.method == "POST":
        if session.get("user_role") != "teacher": return "Unauthorized", 403
        db.timetable.insert_one({
            "class": request.form["class"],
            "time": request.form["time"],
            "monday": request.form["monday"],
            "tuesday": request.form["tuesday"],
            "wednesday": request.form["wednesday"],
            "thursday": request.form["thursday"],
            "friday": request.form["friday"]
        })
        return redirect(url_for("timetable", class_name=request.form["class"]))

    selected_class = request.args.get("class_name")
    classes = [str(i) for i in range(1,11)]
    timetable_data = list(db.timetable.find({"class": selected_class})) if selected_class else []
    return render_template("timetable.html", 
                           classes=classes, 
                           selected_class=selected_class, 
                           timetable=timetable_data)

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
    db.timetable.update_one(
        {"_id": ObjectId(timetable_id)},
        {"$set": {
            "class": class_val,
            "time": request.form.get("time"),
            "monday": request.form.get("monday"),
            "tuesday": request.form.get("tuesday"),
            "wednesday": request.form.get("wednesday"),
            "thursday": request.form.get("thursday"),
            "friday": request.form.get("friday")
        }}
    )
    return redirect(url_for("timetable", class_name=class_val))

# ================= SUPPORT =================
@app.route("/teacher/support")
def teacher_support():
    if session.get("user_role") != "teacher":
        return "403 Forbidden - Teachers only", 403

    messages = list(db.support_messages.find().sort("_id", -1))
    return render_template("teacher_support.html", messages=messages)

@app.route("/respond_support/<id>", methods=["POST"])
def respond_support(id):
    if session.get('user_role') == 'teacher':
        response_text = request.form.get("response")
        db.support_messages.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"response": response_text, "status": "replied"}}
        )
    return redirect(url_for('teacher_support'))

@app.route("/delete_support/<id>")
def delete_support(id):
    if session.get('user_role') == 'teacher':
        db.support_messages.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('teacher_support'))

# ================= API & EXTRAS =================
@app.route("/get_students/<class_no>")
def get_students(class_no):
    # This specifically targets the students collection for attendance/marks
    students_cursor = db.students.find({"class": class_no})
    return jsonify([{"id": str(s["_id"]), "name": s["name"]} for s in students_cursor])

@app.route('/library')
def library():
    resources = db.resources.find() 
    return render_template('library.html', resources=resources)

@app.route('/careers')
def careers():
    return render_template('careers.html')

@app.route('/apply', methods=['POST'])
def apply():
    application_data = {
        "name": request.form.get("name"),
        "position": request.form.get("position"),
        "timestamp": datetime.now()
    }
    db.applications.insert_one(application_data)
    return redirect(url_for('careers'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)