import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import io
import pytest
from unittest.mock import patch, MagicMock
from app import app
from bson import ObjectId

# Fix import path



# -------------------------
# FIXTURE
# -------------------------
@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['MAIL_SUPPRESS_SEND'] = True
    app.secret_key = 'test_secret'

    with patch('app.MongoClient'):
        with app.test_client() as client:
            yield client


# -------------------------
# 1. BASIC ROUTES
# -------------------------
def test_home_page(client):
    response = client.get('/')
    assert response.status_code == 200


def test_login_page(client):
    response = client.get('/login')
    assert response.status_code == 200


def test_dashboard_without_login(client):
    response = client.get('/dashboard', follow_redirects=True)
    assert response.status_code in [200, 302]


# -------------------------
# 2. LOGIN LOGIC
# -------------------------
def test_login_success(client):
    with patch('app.db') as mock_db:
        with patch('app.check_password_hash', return_value=True):
            mock_db.users.find_one.return_value = {
                "username": "admin",
                "password": "hashed",
                "role": "admin"
            }

            response = client.post('/login', data={
                "username": "admin",
                "password": "admin",
                "role": "admin"
            }, follow_redirects=True)

            assert response.status_code == 200


def test_login_wrong_password(client):
    with patch('app.db') as mock_db:
        with patch('app.check_password_hash', return_value=False):
            mock_db.users.find_one.return_value = {
                "username": "admin",
                "password": "hashed",
                "role": "admin"
            }

            response = client.post('/login', data={
                "username": "admin",
                "password": "wrong",
                "role": "admin"
            })

            assert b"Invalid Credentials" in response.data


def test_login_no_role(client):
    with patch('app.db') as mock_db:
        mock_db.users.find_one.return_value = None

        response = client.post('/login', data={
            "username": "admin",
            "password": "admin"
            # role missing
        })

        assert response.status_code == 200


def test_login_user_not_found(client):
    with patch('app.db') as mock_db:
        mock_db.users.find_one.return_value = None

        response = client.post('/login', data={
            "username": "wrong",
            "password": "wrong",
            "role": "student"
        })

        assert b"Invalid Credentials" in response.data


# -------------------------
# 3. ADMISSION LOGIC
# -------------------------
def test_admission_post(client):
    with patch('app.db') as mock_db:
        with patch('os.makedirs'), patch('werkzeug.datastructures.FileStorage.save'):
            data = {
                'full_name': 'Test Student',
                'parent_name': 'Parent',
                'email': 'test@student.com',
                'phone': '1234567890',
                'dob': '2010-01-01',
                'course': 'Science',
                'address': 'Addr',
                'student_photo': (io.BytesIO(b"img"), 'test.jpg')
            }

            response = client.post('/admission', data=data,
                                   content_type='multipart/form-data',
                                   follow_redirects=True)

            assert mock_db.admissions.insert_one.called


def test_admission_get(client):
    response = client.get('/admission')
    assert response.status_code == 200


# -------------------------
# 4. STUDENT PROFILE
# -------------------------
def test_student_profile_logic(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.students.find_one.return_value = {
            "name": "S1", "username": "u1", "class": "10"
        }

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = []
        mock_db.marks.find.return_value = mock_cursor

        mock_db.attendance.count_documents.return_value = 10

        response = client.get(f'/student_profile/{ObjectId()}')
        assert response.status_code == 200


def test_student_not_found(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.students.find_one.return_value = None

        response = client.get(f'/student_profile/{ObjectId()}')
        assert response.status_code == 404


def test_student_access_denied(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'student'
        sess['username'] = 'wrong_user'

    with patch('app.db') as mock_db:
        mock_db.students.find_one.return_value = {"username": "real_user"}

        response = client.get(f'/student_profile/{ObjectId()}')
        assert response.status_code == 403


# -------------------------
# 5. ATTENDANCE
# -------------------------
def test_attendance_submission(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'
        sess['username'] = 't1'

    with patch('app.db') as mock_db:
        mock_db.students.find_one.return_value = {
            "_id": ObjectId(), "name": "S1"
        }

        data = {
            'class_name': '10',
            'attendance_date': '2026-03-23',
            'student_ids': [str(ObjectId())],
            'attendance_status': []
        }

        response = client.post('/submit_attendance', data=data, follow_redirects=True)
        assert mock_db.attendance.insert_many.called


# -------------------------
# 6. MARKS
# -------------------------
def test_marks_submission(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        data = {
            'student_ids': [str(ObjectId())],
            'marks_list': ['90'],
            'status_list': ['PASS'],
            'subject': 'Math',
            'class': '1',
            'exam': 'Final'
        }

        response = client.post('/marks', data=data, follow_redirects=True)
        assert mock_db.marks.insert_many.called


# -------------------------
# 7. ADMIN
# -------------------------
def test_admin_manage_users(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'admin'

    with patch('app.db') as mock_db:
        mock_db.users.find.return_value = []
        mock_db.users.find_one.return_value = None

        response = client.post('/admin/manage_users', data={
            'username': 'n',
            'password': 'p',
            'role': 'student'
        }, follow_redirects=True)

        assert mock_db.users.insert_one.called


def test_admin_get_page(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'admin'

    response = client.get('/admin/manage_users')
    assert response.status_code == 200


# -------------------------
# 8. CHANGE PASSWORD
# -------------------------
def test_change_password(client):
    with client.session_transaction() as sess:
        sess['username'] = 't1'
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.users.find_one.return_value = {
            "username": "t1",
            "password": "old"
        }

        response = client.post('/change_password', data={
            'current_password': 'old',
            'new_password': 'new',
            'confirm_password': 'new'
        }, follow_redirects=True)

        assert mock_db.users.update_one.called


def test_change_password_mismatch(client):
    with client.session_transaction() as sess:
        sess['username'] = 't1'
        sess['user_role'] = 'teacher'

    response = client.post('/change_password', data={
        'current_password': 'old',
        'new_password': 'new',
        'confirm_password': 'wrong'
    })

    assert response.status_code == 200


# -------------------------
# 9. LOGOUT
# -------------------------
def test_logout(client):
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200


# -------------------------
# 10. EXCEPTION TEST
# -------------------------
def test_db_exception(client):
    with patch('app.db') as mock_db:
        mock_db.users.find_one.side_effect = Exception("DB error")

        response = client.post('/login', data={
            "username": "admin",
            "password": "admin",
            "role": "admin"
        })

        assert response.status_code == 500

# -------------------------
# 11. DASHBOARD COVERAGE
# -------------------------
def test_dashboard_admin(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'admin'

    response = client.get('/dashboard')
    assert response.status_code == 200


def test_dashboard_teacher(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    response = client.get('/dashboard')
    assert response.status_code == 200


def test_dashboard_student(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'student'

    response = client.get('/dashboard')
    assert response.status_code == 200


# -------------------------
# 12. INVALID ACCESS
# -------------------------
def test_dashboard_no_session(client):
    response = client.get('/dashboard', follow_redirects=True)
    assert response.status_code in [200, 302]


# -------------------------
# 13. MARKS EDGE CASES
# -------------------------
def test_marks_empty_data(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    response = client.post('/marks', data={}, follow_redirects=True)
    assert response.status_code == 200


# -------------------------
# 14. ATTENDANCE EDGE CASE
# -------------------------
def test_attendance_empty(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    response = client.post('/submit_attendance', data={}, follow_redirects=True)
    assert response.status_code == 200


# -------------------------
# 15. ADMIN DUPLICATE USER
# -------------------------
def test_admin_existing_user(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'admin'

    with patch('app.db') as mock_db:
        mock_db.users.find_one.return_value = {"username": "exists"}

        response = client.post('/admin/manage_users', data={
            'username': 'exists',
            'password': 'p',
            'role': 'student'
        }, follow_redirects=True)

        assert response.status_code == 200


# -------------------------
# 16. PASSWORD WRONG CURRENT
# -------------------------
def test_change_password_wrong_current(client):
    with client.session_transaction() as sess:
        sess['username'] = 't1'
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.users.find_one.return_value = {
            "username": "t1",
            "password": "correct"
        }

        response = client.post('/change_password', data={
            'current_password': 'wrong',
            'new_password': 'new',
            'confirm_password': 'new'
        })

        assert response.status_code == 200


# -------------------------
# 17. FILE UPLOAD FAILURE
# -------------------------
def test_admission_no_file(client):
    with patch('app.db') as mock_db:
        data = {
            'full_name': 'Test',
            'parent_name': 'Parent'
        }

        response = client.post('/admission', data=data, follow_redirects=True)
        assert response.status_code == 200


# -------------------------
# 18. RANDOM ROUTE (404)
# -------------------------
def test_invalid_route(client):
    response = client.get('/random_route')
    assert response.status_code == 404


# -------------------------
# 10. CALENDAR
# -------------------------
def test_calendar_view(client):
    with patch('app.db') as mock_db:
        mock_db.calendar_events.find.return_value.sort.return_value = []
        response = client.get('/calendar')
        assert response.status_code == 200


def test_add_calendar_event(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        response = client.post('/add_calendar_event', data={
            "date": "2026-03-25",
            "description": "Test Event",
            "category": "Holiday"
        })
        assert mock_db.calendar_events.insert_one.called


# -------------------------
# 11. CONTACT FORM
# -------------------------
def test_contact_post(client):
    with patch('app.db') as mock_db:
        response = client.post('/contact', data={
            "full_name": "Test",
            "email": "test@mail.com",
            "message": "Hello"
        })
        assert mock_db.support_messages.insert_one.called


# -------------------------
# 12. DASHBOARD
# -------------------------
def test_dashboard_teacher(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.admissions.find.return_value = []
        mock_db.support_messages.count_documents.return_value = 0

        response = client.get('/dashboard')
        assert response.status_code == 200


# -------------------------
# 13. DELETE STUDENT
# -------------------------
def test_delete_student(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        response = client.get(f'/delete_student/{ObjectId()}')
        assert mock_db.students.delete_one.called


# -------------------------
# 14. BULK PROMOTE
# -------------------------
def test_bulk_promote(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.students.update_many.return_value.modified_count = 5

        response = client.post('/bulk_promote', data={
            "source_class": "10",
            "new_batch": "2026"
        })

        assert response.status_code == 302


# -------------------------
# 15. TIMETABLE
# -------------------------
def test_timetable_get(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.timetable.find.return_value = []
        response = client.get('/timetable')
        assert response.status_code == 200


def test_timetable_post(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        response = client.post('/timetable', data={
            "class": "10",
            "time": "10AM",
            "monday": "Math",
            "tuesday": "Sci",
            "wednesday": "Eng",
            "thursday": "Bio",
            "friday": "Chem"
        })
        assert mock_db.timetable.insert_one.called


# -------------------------
# 16. SUPPORT PAGE
# -------------------------
def test_teacher_support(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.support_messages.find.return_value.sort.return_value = []
        response = client.get('/teacher/support')
        assert response.status_code == 200


# -------------------------
# 17. LIBRARY & CAREERS
# -------------------------
def test_library(client):
    with patch('app.db') as mock_db:
        mock_db.resources.find.return_value = []
        response = client.get('/library')
        assert response.status_code == 200


def test_careers(client):
    response = client.get('/careers')
    assert response.status_code == 200


def test_apply(client):
    with patch('app.db') as mock_db:
        response = client.post('/apply', data={
            "name": "Test",
            "position": "Teacher"
        })
        assert mock_db.applications.insert_one.called

def test_dashboard_no_session(client):
    response = client.get('/dashboard')
    assert response.status_code == 302


def test_delete_student_unauthorized(client):
    response = client.get(f'/delete_student/{ObjectId()}')
    assert response.status_code == 403


def test_marks_unauthorized_post(client):
    response = client.post('/marks', data={})
    assert response.status_code == 302

def test_students_with_filters(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.students.find.return_value = [
            {"name": "A", "batch": "2025"},
            {"name": "B"}
        ]
        mock_db.students.distinct.return_value = ["2025"]

        response = client.get('/students?class=10&search=A')
        assert response.status_code == 200

def test_get_student_performance(client):
    with patch('app.db') as mock_db:
        mock_db.students.find.return_value = [{"_id": ObjectId()}]
        mock_db.marks.find.return_value = [{
            "subject": "Math",
            "marks": 90,
            "status": "PASS",
            "exam": "Final"
        }]

        response = client.get('/get_student_performance/A')
        assert response.status_code == 200

def test_delete_attendance(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.attendance.find_one.return_value = {"class": "10"}

        response = client.get(f'/delete_attendance/{ObjectId()}')
        assert response.status_code == 302

def test_update_student_full(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        response = client.post('/update_student_full', data={
            "id": str(ObjectId()),
            "name": "New",
            "username": "u",
            "parent_username": "p",
            "parent_name": "Parent",
            "roll": "1",
            "class": "10",
            "batch": "2025",
            "dob": "2000-01-01",
            "email": "e@mail.com",
            "phone": "123",
            "address": "addr"
        })
        assert mock_db.students.update_one.called

def test_marks_get(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.marks.find.return_value = []
        mock_db.students.find.return_value = []

        response = client.get('/marks')
        assert response.status_code == 200

def test_fix_database(client):
    with patch('app.db') as mock_db:
        mock_db.students.update_many.return_value.modified_count = 5
        response = client.get('/fix_database')
        assert response.status_code == 200


def test_assign_batches(client):
    with patch('app.db') as mock_db:
        response = client.get('/assign_batches')
        assert response.status_code == 200

def test_get_students_api(client):
    with patch('app.db') as mock_db:
        mock_db.students.find.return_value = [
            {"_id": ObjectId(), "name": "A"}
        ]

        response = client.get('/get_students/10')
        assert response.status_code == 200

# -------------------------
# 10. UNAUTHORIZED ACCESS
# -------------------------
def test_dashboard_no_login(client):
    response = client.get('/dashboard')
    assert response.status_code == 302


def test_marks_unauthorized(client):
    response = client.post('/marks', data={})
    assert response.status_code == 302


def test_delete_student_unauthorized(client):
    response = client.get(f'/delete_student/{ObjectId()}')
    assert response.status_code == 403


def test_delete_mark_unauthorized(client):
    response = client.get(f'/delete_mark/{ObjectId()}')
    assert response.status_code == 403


# -------------------------
# 11. CALENDAR ROUTES
# -------------------------
def test_calendar_get(client):
    with patch('app.db') as mock_db:
        mock_db.calendar_events.find.return_value.sort.return_value = []
        response = client.get('/calendar')
        assert response.status_code == 200


def test_add_calendar_event(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        response = client.post('/add_calendar_event', data={
            "date": "2026-03-25",
            "description": "Event",
            "category": "Exam"
        })
        assert mock_db.calendar_events.insert_one.called


# -------------------------
# 12. CONTACT FORM
# -------------------------
def test_contact_post(client):
    with patch('app.db') as mock_db:
        response = client.post('/contact', data={
            "full_name": "Test",
            "email": "t@test.com",
            "message": "Hello"
        })
        assert mock_db.support_messages.insert_one.called


# -------------------------
# 13. DELETE ATTENDANCE
# -------------------------
def test_delete_attendance_unauthorized(client):
    response = client.get(f'/delete_attendance/{ObjectId()}')
    assert response.status_code == 403


def test_delete_attendance_success(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.attendance.find_one.return_value = {"class": "10"}
        response = client.get(f'/delete_attendance/{ObjectId()}')
        assert mock_db.attendance.delete_one.called


# -------------------------
# 14. STUDENTS FILTER
# -------------------------
def test_students_filter(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.students.find.return_value = []
        mock_db.students.distinct.return_value = []
        mock_db.students.find_one.return_value = None

        response = client.get('/students?class=10')
        assert response.status_code == 200


# -------------------------
# 15. PERFORMANCE API
# -------------------------
def test_get_student_performance_empty(client):
    with patch('app.db') as mock_db:
        mock_db.students.find.return_value = []
        response = client.get('/get_student_performance/test')
        assert response.json == []


def test_get_student_performance_exception(client):
    with patch('app.db') as mock_db:
        mock_db.students.find.side_effect = Exception("Error")
        response = client.get('/get_student_performance/test')
        assert response.status_code == 500


# -------------------------
# 16. SUPPORT ROUTES
# -------------------------
def test_teacher_support_unauthorized(client):
    response = client.get('/teacher/support')
    assert response.status_code == 403


def test_delete_support(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        response = client.get(f'/delete_support/{ObjectId()}')
        assert mock_db.support_messages.delete_one.called


# -------------------------
# 17. ADMIN DELETE USER
# -------------------------
def test_delete_user(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'admin'

    with patch('app.db') as mock_db:
        response = client.get(f'/delete_user/{ObjectId()}')
        assert mock_db.users.delete_one.called


# -------------------------
# 18. LIBRARY & CAREERS
# -------------------------
def test_library_page(client):
    with patch('app.db') as mock_db:
        mock_db.resources.find.return_value = []
        response = client.get('/library')
        assert response.status_code == 200


def test_careers_page(client):
    response = client.get('/careers')
    assert response.status_code == 200


def test_apply_job(client):
    with patch('app.db') as mock_db:
        response = client.post('/apply', data={
            "name": "Test",
            "position": "Teacher"
        })
        assert mock_db.applications.insert_one.called


# -------------------------
# 19. FIX DATABASE ROUTES
# -------------------------
def test_fix_database(client):
    with patch('app.db') as mock_db:
        mock_db.students.update_many.return_value.modified_count = 5
        response = client.get('/fix_database')
        assert b"Updated" in response.data


def test_assign_batches(client):
    with patch('app.db') as mock_db:
        response = client.get('/assign_batches')
        assert response.status_code == 200


def test_debug_batch(client):
    with patch('app.db') as mock_db:
        response = client.get('/debug_batch')
        assert response.status_code == 200

# -------------------------
# 20. LOGIN EDGE CASES
# -------------------------
def test_login_no_role(client):
    with patch('app.db') as mock_db:
        mock_db.users.find_one.return_value = None

        response = client.post('/login', data={
            "username": "u",
            "password": "p"
        })
        assert b"Invalid Credentials" in response.data


# -------------------------
# 21. CHANGE PASSWORD EDGE
# -------------------------
def test_change_password_wrong_current(client):
    with client.session_transaction() as sess:
        sess['username'] = 'u1'
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.users.find_one.return_value = {
            "username": "u1",
            "password": "correct"
        }

        response = client.post('/change_password', data={
            "current_password": "wrong",
            "new_password": "new",
            "confirm_password": "new"
        })

        assert b"incorrect" in response.data


def test_change_password_mismatch(client):
    with client.session_transaction() as sess:
        sess['username'] = 'u1'
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.users.find_one.return_value = {
            "username": "u1",
            "password": "old"
        }

        response = client.post('/change_password', data={
            "current_password": "old",
            "new_password": "new",
            "confirm_password": "wrong"
        })

        assert b"do not match" in response.data


# -------------------------
# 22. DASHBOARD TEACHER DATA
# -------------------------
def test_dashboard_teacher_data(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.admissions.find.return_value = []
        mock_db.support_messages.count_documents.return_value = 0

        response = client.get('/dashboard')
        assert response.status_code == 200


# -------------------------
# 23. CLEAR NOTIFICATIONS
# -------------------------
def test_clear_notifications(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        response = client.get('/clear_notifications')
        assert mock_db.admissions.update_many.called


# -------------------------
# 24. APPROVE ADMISSION
# -------------------------
def test_approve_admission(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.admissions.find_one.return_value = {
            "full_name": "S",
            "email": "e",
            "course": "10"
        }

        response = client.post(f'/approve_admission/{ObjectId()}')
        assert mock_db.students.insert_one.called


# -------------------------
# 25. DELETE CALENDAR EVENT
# -------------------------
def test_delete_calendar_event(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        response = client.get(f'/delete_calendar_event/{ObjectId()}')
        assert mock_db.calendar_events.delete_one.called


# -------------------------
# 26. UPDATE STUDENT
# -------------------------
def test_update_student(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        response = client.post('/update_student', data={
            "id": str(ObjectId()),
            "name": "S",
            "class": "10",
            "batch": "2025"
        })
        assert mock_db.students.update_one.called


# -------------------------
# 27. BULK PROMOTE
# -------------------------
def test_bulk_promote_success(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.students.update_many.return_value.modified_count = 2

        response = client.post('/bulk_promote', data={
            "source_class": "10",
            "new_batch": "2026"
        })

        assert response.status_code == 302


def test_bulk_promote_invalid(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    response = client.post('/bulk_promote', data={})
    assert response.status_code == 302


# -------------------------
# 28. DELETE TIMETABLE
# -------------------------
def test_delete_timetable(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.timetable.find_one.return_value = {"class": "10"}
        response = client.get(f'/delete_timetable/{ObjectId()}')
        assert mock_db.timetable.delete_one.called


# -------------------------
# 29. UPDATE TIMETABLE
# -------------------------
def test_update_timetable(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        response = client.post('/update_timetable', data={
            "id": str(ObjectId()),
            "class": "10"
        })
        assert mock_db.timetable.update_one.called


# -------------------------
# 30. GET STUDENTS API
# -------------------------
def test_get_students_api(client):
    with patch('app.db') as mock_db:
        mock_db.students.find.return_value = []
        response = client.get('/get_students/10')
        assert response.status_code == 200


# -------------------------
# 31. MARKS GET FILTER
# -------------------------
def test_marks_get_filter(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.marks.find.return_value = []
        mock_db.students.find.return_value = []

        response = client.get('/marks?class_no=10')
        assert response.status_code == 200

def test_db_connection_exception():
    with patch('app.MongoClient', side_effect=Exception("DB fail")):
        import importlib
        import app
        importlib.reload(app)

def test_respond_support_exception(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.mail.send', side_effect=Exception("mail error")), \
         patch('app.db') as mock_db:

        response = client.post('/respond_support', data={
            "message_id": str(ObjectId()),
            "user_email": "a@test.com",
            "user_name": "A",
            "original_msg": "Hi",
            "response": "Reply"
        })

        assert b"Detailed Error Info" in response.data

def test_respond_support_unauthorized(client):
    response = client.post('/respond_support')
    assert response.status_code == 302

def test_respond_support_unauthorized(client):
    response = client.post('/respond_support')
    assert response.status_code == 302

def test_calendar_empty(client):
    with patch('app.db') as mock_db:
        mock_db.calendar_events.find.return_value.sort.return_value = []
        response = client.get('/calendar')
        assert response.status_code == 200

def test_delete_attendance_no_record(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.attendance.find_one.return_value = None
        response = client.get(f'/delete_attendance/{ObjectId()}')
        assert response.status_code == 302

def test_bulk_promote_unauthorized(client):
    response = client.post('/bulk_promote', data={
        "source_class": "10",
        "new_batch": "2026"
    })
    assert response.status_code == 403

def test_bulk_promote_unauthorized(client):
    response = client.post('/bulk_promote', data={
        "source_class": "10",
        "new_batch": "2026"
    })
    assert response.status_code == 403


def test_timetable_post_unauthorized(client):
    response = client.post('/timetable', data={})
    assert response.status_code == 302

def test_timetable_post_unauthorized(client):
    response = client.post('/timetable', data={})
    assert response.status_code == 302


def test_delete_user_unauthorized(client):
    response = client.get(f'/delete_user/{ObjectId()}')
    assert response.status_code == 302

def test_contact_get(client):
    response = client.get('/contact')
    assert response.status_code == 200

def test_add_calendar_event_unauthorized(client):
    response = client.post('/add_calendar_event', data={
        "date": "2026-01-01"
    })
    assert response.status_code == 302

def test_delete_calendar_event_unauthorized(client):
    response = client.get(f'/delete_calendar_event/{ObjectId()}')
    assert response.status_code == 302

def test_delete_calendar_event_unauthorized(client):
    response = client.get(f'/delete_calendar_event/{ObjectId()}')
    assert response.status_code == 302

def test_dashboard_student_role(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'student'

    response = client.get('/dashboard')
    assert response.status_code == 200

def test_admission_get(client):
    response = client.get('/admission')
    assert response.status_code == 200

def test_attendance_with_class(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.attendance.find.return_value.sort.return_value = []

        response = client.get('/attendance?class_no=10')
        assert response.status_code == 200

def test_students_no_filters(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.students.distinct.return_value = []
        mock_db.students.find_one.return_value = None

        response = client.get('/students')
        assert response.status_code == 200

def test_students_no_filters(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.students.distinct.return_value = []
        mock_db.students.find_one.return_value = None

        response = client.get('/students')
        assert response.status_code == 200

def test_update_student_full_unauthorized(client):
    response = client.post('/update_student_full', data={})
    assert response.status_code == 302

def test_delete_timetable_unauthorized(client):
    response = client.get(f'/delete_timetable/{ObjectId()}')
    assert response.status_code == 403

def test_delete_timetable_unauthorized(client):
    response = client.get(f'/delete_timetable/{ObjectId()}')
    assert response.status_code == 403

def test_teacher_support_success(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.support_messages.find.return_value.sort.return_value = []

        response = client.get('/teacher/support')
        assert response.status_code == 200

def test_teacher_support_success(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'teacher'

    with patch('app.db') as mock_db:
        mock_db.support_messages.find.return_value.sort.return_value = []

        response = client.get('/teacher/support')
        assert response.status_code == 200

def test_apply_empty(client):
    with patch('app.db') as mock_db:
        response = client.post('/apply', data={})
        assert mock_db.applications.insert_one.called

def test_manage_users_get(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'admin'

    with patch('app.db') as mock_db:
        mock_db.users.find.return_value = []

        response = client.get('/admin/manage_users')
        assert response.status_code == 200

def test_manage_users_get(client):
    with client.session_transaction() as sess:
        sess['user_role'] = 'admin'

    with patch('app.db') as mock_db:
        mock_db.users.find.return_value = []

        response = client.get('/admin/manage_users')
        assert response.status_code == 200

def test_manage_users_unauthorized(client):
    response = client.get('/admin/manage_users')
    assert response.status_code == 403

def test_manage_users_unauthorized(client):
    response = client.get('/admin/manage_users')
    assert response.status_code == 403

def test_manage_users_unauthorized(client):
    response = client.get('/admin/manage_users')
    assert response.status_code == 403