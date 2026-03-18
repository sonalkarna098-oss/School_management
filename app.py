import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime

app = Flask(__name__)
app.secret_key = "super_secret_school_key"

# ================= DATABASE =================
atlas_uri = os.getenv("MONGO_URI")

try:
    client = MongoClient(atlas_uri)
    db = client["school"]
    # Verify connection
    client.admin.command('ping')
    print("Successfully connected to MongoDB Atlas (Database: management)")
except Exception as e:
    print(f"Error connecting to MongoDB Atlas: {e}")

# Setup safe folders for pictures
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}

# Make sure the folder exists when the app starts
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
# ================= AUTHENTICATION =================
@app.route("/login", methods=["GET", "POST"])
def login():
    message = request.args.get('message')
    if request.method == "POST":
        role = request.form.get("role")
        username = request.form.get("username")
        password = request.form.get("password") # This is your variable

        # Fetch user by username and role
        user = db.users.find_one({
            "username": username,
            "role": role
        })

        if user:
            # Check password based on role
            is_valid = False
            if user.get("role") == "admin":
                # Use password variable here
                is_valid = check_password_hash(user["password"], password)
            else:
                # Use password variable here
                is_valid = (user["password"] == password)

            if is_valid:
                session["user_role"] = user["role"]
                session["username"] = user["username"]
                return redirect(url_for("dashboard"))
            else:
                return f"Invalid Credentials for {role.capitalize()}! <a href='/login'>Try again</a>"
        else:
            return f"Invalid Credentials for {role.capitalize()}! <a href='/login'>Try again</a>"

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

        # 1. Fetch user by username only
        user = db.users.find_one({"username": session['username']})

        if user:
            # 2. Verify current password based on role
            is_valid = False
            if role == "admin":
                is_valid = check_password_hash(user["password"], current_pass)
            else:
                is_valid = (user["password"] == current_pass)

            if not is_valid:
                return render_template("change_password.html", error="Current password is incorrect.")

            if new_pass != confirm_pass:
                return render_template("change_password.html", error="New passwords do not match.")

            # 3. Update the password
            # NOTE: If you want the new admin password to be hashed, 
            # you would use generate_password_hash(new_pass) here.
            db.users.update_one(
                {"username": session['username']},
                {"$set": {"password": new_pass}}
            )

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
        # --- ADD THE IMAGE LOGIC HERE (START) ---
        photo_path = None
        file = request.files.get('student_photo')
        
        if file and file.filename != '':
            # 1. Clean the filename
            filename = secure_filename(file.filename)
            # 2. Create a unique name to avoid overwriting files
            unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            # 3. Save the physical file to your static/uploads folder
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            # 4. Set the path that the browser will use to show the image
            photo_path = f"/static/uploads/{unique_name}"
        # --- ADD THE IMAGE LOGIC HERE (END) ---

        # Now include photo_path in your dictionary
        admission_data = {
            "full_name": request.form.get("full_name"),
            "parent_name": request.form.get("parent_name"),
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
            "dob": request.form.get("dob"),
            "course": request.form.get("course"),
            "address": request.form.get("address"),
            "photo_path": photo_path, # <--- This uses the variable from above
            "status": "Pending",
            "viewed": False 
        }
        
        db.admissions.insert_one(admission_data)
        return render_template("thanks.html")
    
    return render_template("admission.html")

@app.route("/approve_admission/<id>", methods=["POST"])
def approve_admission(id):
    if session.get('user_role') == 'teacher':
        # 1. Fetch the data from the 'admissions' collection
        applicant = db.admissions.find_one({"_id": ObjectId(id)})
        
        if applicant:
            current_year = datetime.now().year # Gets 2026
            # 2. Insert into the 'students' collection including the photo_path
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
                "photo_path": applicant.get('photo_path'), # <--- ADD THIS LINE
                "admission_date": datetime.now().strftime("%Y-%m-%d")
            })
            
            # 3. Delete the temporary admission record
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
    
    # ... (Keep your POST logic same) ...

    selected_class = request.args.get("class")
    selected_batch = request.args.get("batch")
    search_query = request.args.get("search")

    query = {}
    if selected_class: query["class"] = selected_class
    if selected_batch:
        if selected_batch == "Unassigned": query["batch"] = {"$exists": False}
        else: query["batch"] = selected_batch
    if search_query: query["name"] = {"$regex": search_query, "$options": "i"}

    # Final Grouped Dictionary
    grouped_students = {}

    if selected_class or selected_batch or search_query:
        raw_students = list(db.students.find(query))

        # 1. Sort them in Python FIRST
        def get_sort_key(s):
            b = s.get('batch')
            if not b or str(b).lower() in ['none', '', 'unassigned']:
                return (0, 0)
            try: return (1, 3000 - int(b))
            except: return (2, str(b))

        raw_students.sort(key=get_sort_key)

        # 2. Manual Grouping to preserve order for Jinja
        for s in raw_students:
            batch_name = s.get('batch')
            if not batch_name or str(batch_name).lower() in ['none', '', 'unassigned']:
                batch_name = "Unassigned"
            
            if batch_name not in grouped_students:
                grouped_students[batch_name] = []
            grouped_students[batch_name].append(s)

    # BATCH LIST FOR DROPDOWN
    db_batches = db.students.distinct("batch")
    years = sorted([int(x) for x in db_batches if str(x).isdigit()], reverse=True)
    available_batches = [str(y) for y in years]
    if db.students.find_one({"batch": {"$exists": False}}) or "Unassigned" in db_batches:
        if "Unassigned" not in available_batches: available_batches.insert(0, "Unassigned")
    
    return render_template("students.html", 
                           grouped_students=grouped_students, # Sending dictionary
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
            "batch": str(batch) if batch else "Unassigned" # Ensure string format
        }}
    )

    # Redirect using the 'name' in search to instantly see the updated student
    return redirect(url_for('students', search=name))

#=================student marks get ==========================
@app.route("/get_student_performance/<name>")
def get_student_performance(name):
    try:
        clean_search = name.strip()
        # Ensure 'request' is imported at the top of the file
        selected_class = request.args.get('class') 

        # 1. Find the student IDs
        student_query = {"name": {"$regex": clean_search, "$options": "i"}}
        if selected_class and selected_class != "":
            student_query["class"] = selected_class

        # Fetch IDs and convert to strings
        students = list(db.students.find(student_query))
        student_ids = [str(s['_id']) for s in students]

        if not student_ids:
            return jsonify([])

        # 2. Fetch marks filtered by student IDs and class
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
        print(f"Error in get_student_performance: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/fix_na_statuses")
def fix_na_statuses():
    # Update all records missing a status
    # If marks >= 33, set to PASS. If less, set to FAIL.
    db.marks.update_many({"status": {"$exists": False}, "marks": {"$gte": "33"}}, {"$set": {"status": "PASS"}})
    db.marks.update_many({"status": {"$exists": False}, "marks": {"$lt": "33"}}, {"$set": {"status": "FAIL"}})
    return "All N/A records have been updated based on marks!"


@app.route("/fix_old_statuses")
def fix_old_statuses():
    # Set anything 35+ to PASS and below to FAIL for old records
    db.marks.update_many({"status": {"$exists": False}, "marks": {"$gte": 35}}, {"$set": {"status": "PASS"}})
    db.marks.update_many({"status": {"$exists": False}, "marks": {"$lt": 35}}, {"$set": {"status": "FAIL"}})
    return "Old records updated!"

@app.route("/student_profile/<id>")
def student_profile(id):
    if "user_role" not in session:
        return redirect(url_for("login"))

    # 1. Fetch Student Basic Details
    student = db.students.find_one({"_id": ObjectId(id)})
    if not student:
        return "Student not found", 404
    # --- PRIVACY CHECK ---
    user_role = session.get('user_role')
    username = session.get('username')

    if user_role == 'student':
        if username != student.get('username'):
            return "Access Denied: You can only view your own profile.", 403
            
    elif user_role == 'parent':
        # Check if the logged-in parent's username matches the parent_username field
        if username != student.get('parent_username'):
            return "Access Denied: You can only view your child's profile.", 403
    # --- END PRIVACY CHECK ---

    # 3. Fetch Marks History
    marks = list(db.marks.find({"student_id": id}).sort("exam",1))

    # 4. Calculate Attendance Percentage
    total_days = db.attendance.count_documents({"student_name": student['name']})
    present_days = db.attendance.count_documents({"student_name": student['name'], "status": "Present"})
    
    attendance_pct = 0
    if total_days > 0:
        attendance_pct = round((present_days / total_days) * 100, 2)

    return render_template(
        "student_details.html", 
        student=student, 
        marks=marks, 
        attendance_pct=attendance_pct,
        total_days=total_days
    )

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
            "address": request.form.get("address"),
            "batch":request.form.get("batch")
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
        # update_many finds all matches and updates them at once
        result = db.students.update_many(
            {"class": source_class},
            {"$set": {"batch": new_batch}}
        )
        message = f"Successfully moved {result.modified_count} students to Batch {new_batch}!"
        return redirect(url_for('students', message=message))
    
    return redirect(url_for('students', error="Invalid selection"))

# ================= MARKS =================
@app.route("/marks", methods=["GET", "POST"])
def marks():
    if "user_role" not in session: 
        return redirect(url_for("login"))
    
    if request.method == "POST":
        if session.get("user_role") != "teacher": 
            return "Unauthorized", 403
        
        student_ids = request.form.getlist('student_ids')
        marks_values = request.form.getlist('marks_list')
        status_values = request.form.getlist('status_list')
        subject = request.form.get("subject")
        class_name = request.form.get("class")
        exam = request.form.get("exam")

        records = []
        for i in range(len(student_ids)):
            if i < len(marks_values) and marks_values[i]:
                records.append({
                    "student_id": student_ids[i],
                    "class": class_name,
                    "subject": subject,
                    "marks": marks_values[i],
                    "status":status_values[i],
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
    if session.get("user_role") != "teacher": 
        return "Unauthorized", 403
    
    mark_id = request.form.get("id")
    class_val = request.form.get("class") 
    
    db.marks.update_one(
        {"_id": ObjectId(mark_id)},
        {"$set": {
            "subject": request.form.get("subject"),
            "marks": request.form.get("marks"),
            "exam": request.form.get("exam"),
            "status": request.form.get("status")
        }}
    )
    return redirect(url_for("marks", class_no=class_val))

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
    # Get batch from query parameters, e.g., /get_students/3?batch=2026
    batch = request.args.get('batch')
    
    query = {"class": class_no}
    if batch and batch != "":
        query["batch"] = batch

    students_cursor = db.students.find(query)
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

# ================= ADMIN MANAGEMENT =================
@app.route("/admin/manage_users", methods=["GET", "POST"])
def manage_users():
    if session.get('user_role') != 'admin':
        return "Unauthorized Access", 403

    if request.method == "POST":
        new_username = request.form.get("username")
        new_password = request.form.get("password")
        assigned_role = request.form.get("role")

        if db.users.find_one({"username": new_username}):
            return f"User '{new_username}' already exists! <a href='/admin/manage_users'>Back</a>"

        db.users.insert_one({
            "username": new_username,
            "password": new_password,
            "role": assigned_role,
            "created_at": datetime.now()
        })
        return redirect(url_for('manage_users'))

    users_list = list(db.users.find())
    return render_template("admin_manage.html", users=users_list)

@app.route("/delete_user/<id>")
def delete_user(id):
    if session.get('user_role') == 'admin':
        db.users.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('manage_users'))

#========= FIx database ===========================
@app.route("/fix_database")
def fix_database():
    # This finds every student missing the 'batch' field and sets it to '2026'
    result = db.students.update_many(
        {"batch": {"$exists": False}}, 
        {"$set": {"batch": "2026"}}
    )
    return f"Updated {result.modified_count} students to Batch 2026!"

#-------------- batches ------------------------------------
@app.route("/assign_batches")
def assign_batches():
    # Example: Moves all unassigned students to Batch 2025
    db.students.update_many(
        {"batch": {"$exists": False}}, 
        {"$set": {"batch": "2025"}}
    )
    return "Existing students moved to Batch 2025!"

#============ debug-batch ===================================
@app.route("/debug_batch")
def debug_batch():
    # This sets all current students to Batch 2025
    db.students.update_many({}, {"$set": {"batch": "2025"}})
    return "All students are now Batch 2025. The filter should now work!"

# if __name__=="__main__":
#     app.run(debug=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)