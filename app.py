from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, session, jsonify
import os
import base64
import sqlite3
from datetime import datetime
from io import BytesIO
from PIL import Image
from functools import wraps
import json

from werkzeug.security import generate_password_hash, check_password_hash
from backend.main import build_class_embeddings, process_classroom_images, process_multiple_classroom_images, generate_excel_report

# =============================
# CONFIG
# ==============================
UPLOAD_FOLDER_STUDENTS = "database/photo"         # Student samples
UPLOAD_FOLDER_CLASSROOM = "database/class_img"   # Captured classroom images
REPORTS_DIR = "reports"
USERS_DIR = "database/users"
USERS_FILE = os.path.join(USERS_DIR, "users.json")

os.makedirs(UPLOAD_FOLDER_STUDENTS, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_CLASSROOM, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(USERS_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = "sih2025_secret"


# Load or initialize user database
def get_all_reports():
    all_reports = []
    for root, dirs, files in os.walk(REPORTS_DIR):
        for file in files:
            if file.endswith('.xlsx'):
                rel_dir = os.path.relpath(root, REPORTS_DIR)
                rel_file = os.path.join(rel_dir, file) if rel_dir != '.' else file
                all_reports.append(rel_file)
    return sorted(all_reports, reverse=True)


def load_users():
    if not os.path.exists(USERS_FILE):
        default_users = {
            "admin1": {
                "password": generate_password_hash("adminpass"),
                "role": "admin",
                "last_login": "",
                "login_count": 0
            },
            "teacher1": {
                "password": generate_password_hash("teachpass"),
                "role": "teacher",
                "class": "class101",
                "last_login": "",
                "login_count": 0
            }
        }
        with open(USERS_FILE, "w") as f:
            json.dump(default_users, f, indent=2)
        return default_users
    else:
        try:
            with open(USERS_FILE, "r") as f:
                data = f.read().strip()
                if not data:
                    raise ValueError("Empty file")
                return json.loads(data)
        except Exception:
            default_users = {
                "admin1": {
                    "password": generate_password_hash("adminpass"),
                    "role": "admin",
                    "last_login": "",
                    "login_count": 0
                },
                "teacher1": {
                    "password": generate_password_hash("teachpass"),
                    "role": "teacher",
                    "class": "class101",
                    "last_login": "",
                    "login_count": 0
                }
            }
            with open(USERS_FILE, "w") as f:
                json.dump(default_users, f, indent=2)
            return default_users

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

users = load_users()

def get_class_report_dir(class_name):
    """Create and return class-specific report directory"""
    if not class_name:
        return REPORTS_DIR
    path = os.path.join(REPORTS_DIR, class_name)
    os.makedirs(path, exist_ok=True)
    return path

# Role-based access decorator
def role_required(role):
    def wrapper(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'role' not in session or session['role'] != role:
                flash("Access denied. Please login with appropriate credentials.")
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapped
    return wrapper

# ==============================
# Login and Logout
# ==============================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        userid = request.form.get('userid')
        password = request.form.get('password')
        user = users.get(userid)
        if user and check_password_hash(user['password'], password):
            # Record last login time
            current_login = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            user['last_login'] = current_login
            
            # Update login count (optional)
            user['login_count'] = user.get('login_count', 0) + 1
            
            # Save updated user data
            users[userid] = user
            save_users(users)
            
            session['userid'] = userid
            session['role'] = user['role']
            session['class'] = user.get('class')
            flash(f"Welcome, {userid}!")
            
            if user['role'] == 'teacher':
                return redirect(url_for('index'))
            else:
                return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid user ID or password.")
            return redirect(url_for('login'))
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for('login'))

# ==============================
# Teacher Routes
# ==============================

@app.route("/", methods=["GET"])
@role_required('teacher')
def index():
    return render_template("index.html")

@app.route("/capture", methods=["POST"])
@role_required('teacher')
def capture_image():
    try:
        teacher_class = session.get('class')
        if not teacher_class:
            flash("No class assigned to your account. Contact admin.")
            return redirect(url_for('index'))
            
        data_url = request.form["image"]
        image_data = base64.b64decode(data_url.split(",")[1])

        image_path = os.path.join(UPLOAD_FOLDER_CLASSROOM, "captured_classroom.jpg")
        with open(image_path, "wb") as f:
            f.write(image_data)

        # Pass teacher's class to backend functions
        build_class_embeddings(teacher_class)
        students_present = process_classroom_images(teacher_class)
        results, report_filename = generate_excel_report(students_present, teacher_class)

        # Debug: Print where the file should be
        print(f"[DEBUG] Report should be saved as: {report_filename}")
        if teacher_class:
            expected_path = os.path.join(get_class_report_dir(teacher_class), report_filename)
            print(f"[DEBUG] Expected path: {expected_path}")
            print(f"[DEBUG] File exists: {os.path.exists(expected_path)}")
        
        flash("Attendance processed successfully!")
        return render_template("results.html", present=results, report_file=report_filename)
        
    except Exception as e:
        flash(f"Error while processing image: {str(e)}")
        return redirect(url_for("index"))

@app.route("/view_attendance")
@role_required('teacher')
def view_attendance():
    teacher_class = session.get('class')
    if not teacher_class:
        flash("No class assigned to your account. Contact admin.")
        return redirect(url_for('index'))
        
    class_report_dir = get_class_report_dir(teacher_class)
    try:
        files = sorted(os.listdir(class_report_dir), reverse=True)
    except Exception:
        files = []  
    return render_template("reports.html", files=files)

@app.route("/upload_classroom_images", methods=["GET", "POST"])
@role_required('teacher')
def upload_classroom_images():
    """Allow teachers to upload multiple classroom images for attendance"""
    if request.method == "POST":
        teacher_class = session.get('class')
        if not teacher_class:
            flash("No class assigned to your account. Contact admin.")
            return redirect(url_for('index'))

        # Get uploaded files
        uploaded_files = request.files.getlist("classroom_images")
        
        if not uploaded_files or all(f.filename == '' for f in uploaded_files):
            flash("Please select at least one classroom image.")
            return redirect(request.url)

        try:
            # Clear old classroom images
            clear_old_classroom_images()
            
            # Save uploaded images
            saved_count = 0
            for i, file in enumerate(uploaded_files):
                if file and file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    filename = f"classroom_{i+1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    file_path = os.path.join(UPLOAD_FOLDER_CLASSROOM, filename)
                    file.save(file_path)
                    saved_count += 1

            if saved_count == 0:
                flash("No valid image files were uploaded.")
                return redirect(request.url)

            flash(f"Successfully uploaded {saved_count} classroom images.")

            # Process attendance from multiple images
            build_class_embeddings(teacher_class)
            students_present = process_multiple_classroom_images(teacher_class)
            results, report_filename = generate_excel_report(students_present, teacher_class)

            flash("Attendance processed successfully from uploaded images!")
            return render_template(
                "results.html",
                present=results,
                report_file=report_filename,
                image_count=saved_count
            )

        except Exception as e:
            flash(f"Error processing classroom images: {str(e)}")
            return redirect(request.url)

    return render_template("upload_classroom_images.html")

def clear_old_classroom_images():
    """Clear old classroom images before processing new ones"""
    for file in os.listdir(UPLOAD_FOLDER_CLASSROOM):
        if file.startswith("classroom_") or file.startswith("captured_"):
            file_path = os.path.join(UPLOAD_FOLDER_CLASSROOM, file)
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"[WARNING] Could not remove {file}: {e}")

# ==============================
# Admin Routes
# ==============================

@app.route("/admin_dashboard")
@role_required('admin')
def admin_dashboard():
    # Get reports
    try:
        reports = sorted(os.listdir(REPORTS_DIR), reverse=True)
    except Exception:
        reports = []
    
    # Prepare user statistics
    total_users = len(users)
    total_teachers = sum(1 for user in users.values() if user.get('role') == 'teacher')
    total_admins = sum(1 for user in users.values() if user.get('role') == 'admin')
    
    # Get classes count
    try:
        total_classes = len([d for d in os.listdir(os.path.join('database', 'photo')) 
                           if os.path.isdir(os.path.join('database', 'photo', d))])
        class_list = [d for d in os.listdir(os.path.join('database', 'photo')) 
                     if os.path.isdir(os.path.join('database', 'photo', d))]
    except:
        total_classes = 0
        class_list = []
    
    # Prepare detailed user list with login info
    user_list = []
    for userid, data in users.items():
        last_login = data.get('last_login', 'Never')
        if last_login != 'Never':
            try:
                # Parse and format the datetime for better display
                login_dt = datetime.strptime(last_login, '%Y-%m-%d %H:%M:%S')
                time_ago = datetime.now() - login_dt
                
                if time_ago.days > 0:
                    last_login_display = f"{last_login} ({time_ago.days} days ago)"
                elif time_ago.seconds > 3600:
                    hours = time_ago.seconds // 3600
                    last_login_display = f"{last_login} ({hours}h ago)"
                elif time_ago.seconds > 60:
                    minutes = time_ago.seconds // 60
                    last_login_display = f"{last_login} ({minutes}m ago)"
                else:
                    last_login_display = f"{last_login} (Just now)"
            except:
                last_login_display = last_login
        else:
            last_login_display = "Never"
        
        user_list.append({
            "userid": userid,
            "role": data.get("role", "Unknown"),
            "class": data.get("class", "N/A"),
            "last_login": last_login,
            "last_login_display": last_login_display,
            "login_count": data.get("login_count", 0),
            "status": "Active" if last_login != 'Never' else "Inactive"
        })
    
    # Sort by last login (most recent first)
    user_list.sort(key=lambda x: x['last_login'] if x['last_login'] != 'Never' else '1900-01-01', reverse=True)
    
    return render_template("admin_dashboard_combined.html", 
                         reports=reports, 
                         user_list=user_list,
                         total_users=total_users,
                         total_teachers=total_teachers,
                         total_admins=total_admins,
                         total_classes=total_classes,
                         class_list=class_list)

# New route to add teacher (admin only)
@app.route("/add_teacher", methods=["GET", "POST"])
@role_required('admin')
def add_teacher():
    if request.method == "POST":
        new_userid = request.form.get("userid")
        new_password = request.form.get("password")
        role = request.form.get("role")
        class_name = request.form.get("class")  # Get class from form
        
        # Restrict admin creation - only allow teachers
        if role != "teacher":
            flash("You can only create teacher accounts.")
            return redirect(url_for("add_teacher"))
        
        if not new_userid or not new_password or not role:
            flash("All required fields must be filled.")
            return redirect(url_for("add_teacher"))

        if new_userid in users:
            flash("User ID already exists.")
            return redirect(url_for("add_teacher"))

        new_user = {
            "password": generate_password_hash(new_password),
            "role": role,
            "last_login": "",  # Initialize as empty
            "login_count": 0   # Initialize login count
        }
        
        # Add class for teachers only
        if role == "teacher" and class_name:
            new_user["class"] = class_name
            
        users[new_userid] = new_user
        save_users(users)
        flash(f"User '{new_userid}' added successfully.")
        return redirect(url_for("admin_dashboard"))

    return render_template("add_teacher.html")

@app.route("/upload_samples", methods=["GET", "POST"])
@role_required('admin')
def upload_samples():
    if request.method == "POST":
        class_name = request.form.get("class_name")
        student_name = request.form.get("student_name")

        if not class_name or not student_name:
            flash("Class name and student name are required!")
            return redirect(request.url)

        # Create folders dynamically
        student_folder = os.path.join(UPLOAD_FOLDER_STUDENTS, class_name, student_name)
        os.makedirs(student_folder, exist_ok=True)

        total_saved = 0

        # Handle file uploads
        files = request.files.getlist("sample_images")
        for file in files:
            if file and file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                file.save(os.path.join(student_folder, file.filename))
                total_saved += 1

        # Handle multiple captured images from webcam
        captured_images = request.form.getlist("captured_images")
        for i, captured_image_data in enumerate(captured_images):
            if captured_image_data:
                try:
                    # Strip base64 header
                    img_data = captured_image_data.split(",")[1]
                    img_bytes = base64.b64decode(img_data)
                    img = Image.open(BytesIO(img_bytes))

                    # Save with unique filename
                    filename = f"captured_{student_name}_{i+1}_{len(os.listdir(student_folder)) + 1}.jpg"
                    img.save(os.path.join(student_folder, filename))
                    total_saved += 1
                except Exception as e:
                    flash(f"Error saving captured image {i+1}: {str(e)}")

        if total_saved > 0:
            flash(f"Successfully saved {total_saved} images for {student_name} in {class_name}.")
        else:
            flash("No valid images were saved. Please check your uploads.")
        
        return redirect(url_for("upload_samples"))

    return render_template("upload_samples.html")

# ==============================
# Admin API Routes
# ==============================

@app.route('/admin/reports')
def admin_reports():
    """Admin reports dashboard"""
    return render_template('admin_reports.html')

@app.route('/api/admin/students-overview')
def admin_students_overview():
    """Get overview of all students with sample images and attendance"""
    class_filter = request.args.get('class', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search_query = request.args.get('search', '')

    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row

    # Base query to get students from sample_images table
    base_query = """
        SELECT DISTINCT 
            s.student_id,
            s.student_name,
            s.class_name,
            COUNT(CASE WHEN s.status = 'approved' THEN 1 END) as approved_samples,
            COUNT(CASE WHEN s.status = 'pending' THEN 1 END) as pending_samples,
            COUNT(CASE WHEN s.status = 'rejected' THEN 1 END) as rejected_samples,
            COUNT(*) as total_samples,
            MAX(s.upload_date) as last_upload
        FROM sample_images s
        WHERE 1=1
    """
    params = []

    if class_filter != 'all':
        base_query += " AND s.class_name = ?"
        params.append(class_filter)

    if search_query:
        base_query += " AND (s.student_name LIKE ? OR s.student_id LIKE ?)"
        params.extend([f'%{search_query}%', f'%{search_query}%'])

    base_query += " GROUP BY s.student_id, s.student_name, s.class_name"

    # Get total count for pagination
    count_query = f"SELECT COUNT(*) FROM ({base_query}) as subquery"
    total_count = conn.execute(count_query, params).fetchone()[0]

    # Add pagination
    base_query += " ORDER BY s.student_name LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    cursor = conn.execute(base_query, params)
    students = []

    for row in cursor.fetchall():
        student_data = dict(row)

        # Get attendance statistics for this student
        attendance_query = """
            SELECT 
                COUNT(*) as total_classes,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as present_count
            FROM attendance_records 
            WHERE student_name = ? AND class_name = ?
        """

        attendance_result = conn.execute(attendance_query, 
                                       (student_data['student_name'], student_data['class_name'])).fetchone()

        if attendance_result and attendance_result[0] > 0:
            student_data['total_classes'] = attendance_result[0]
            student_data['present_count'] = attendance_result[1]
            student_data['attendance_percentage'] = round((attendance_result[1] / attendance_result[0]) * 100, 1)
        else:
            student_data['total_classes'] = 0
            student_data['present_count'] = 0
            student_data['attendance_percentage'] = 0.0

        students.append(student_data)

    conn.close()

    return jsonify({
        'students': students,
        'total': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page
    })

@app.route('/api/admin/attendance-records')
def admin_attendance_records():
    """Get detailed attendance records"""
    class_filter = request.args.get('class', 'all')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row

    base_query = """
        SELECT 
            student_name,
            class_name,
            date,
            time,
            status,
            confidence
        FROM attendance_records
        WHERE 1=1
    """
    params = []

    if class_filter != 'all':
        base_query += " AND class_name = ?"
        params.append(class_filter)

    if date_from:
        base_query += " AND date >= ?"
        params.append(date_from)

    if date_to:
        base_query += " AND date <= ?"
        params.append(date_to)

    # Get total count
    count_query = base_query.replace('SELECT student_name, class_name, date, time, status, confidence', 'SELECT COUNT(*)')
    total_count = conn.execute(count_query, params).fetchone()[0]

    # Add pagination
    base_query += " ORDER BY date DESC, time DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    cursor = conn.execute(base_query, params)
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        'records': records,
        'total': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page
    })

@app.route('/api/admin/student-detail/<student_id>')
def admin_student_detail(student_id):
    """Get detailed information about a specific student"""
    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row

    # Get student's sample images
    sample_images = conn.execute("""
        SELECT id, image_filename, upload_date, status, quality_score, rejection_reason
        FROM sample_images 
        WHERE student_id = ?
        ORDER BY upload_date DESC
    """, (student_id,)).fetchall()

    # Get student's attendance records
    attendance_records = conn.execute("""
        SELECT date, time, status, confidence, class_name
        FROM attendance_records 
        WHERE student_id = ? OR student_name IN (
            SELECT DISTINCT student_name FROM sample_images WHERE student_id = ?
        )
        ORDER BY date DESC, time DESC
        LIMIT 50
    """, (student_id, student_id)).fetchall()

    conn.close()

    return jsonify({
        'sample_images': [dict(img) for img in sample_images],
        'attendance_records': [dict(rec) for rec in attendance_records]
    })

@app.route('/api/admin/class-statistics')
def admin_class_statistics():
    """Get statistics by class"""
    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row

    # Get sample image stats by class
    sample_stats = conn.execute("""
        SELECT 
            class_name,
            COUNT(DISTINCT student_id) as total_students,
            COUNT(*) as total_samples,
            COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_samples,
            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_samples,
            COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_samples
        FROM sample_images
        WHERE class_name IS NOT NULL
        GROUP BY class_name
        ORDER BY class_name
    """).fetchall()

    # Get attendance stats by class
    attendance_stats = conn.execute("""
        SELECT 
            class_name,
            COUNT(*) as total_records,
            COUNT(CASE WHEN status = 'Present' THEN 1 END) as present_records,
            COUNT(DISTINCT student_name) as unique_students,
            COUNT(DISTINCT date) as unique_dates
        FROM attendance_records
        WHERE class_name IS NOT NULL
        GROUP BY class_name
        ORDER BY class_name
    """).fetchall()

    conn.close()

    return jsonify({
        'sample_stats': [dict(row) for row in sample_stats],
        'attendance_stats': [dict(row) for row in attendance_stats]
    })

@app.route('/download_report/<path:filename>')
def download_report(filename):
    user_role = session.get('role')
    try:
        # Construct full absolute file path
        full_path = os.path.join(REPORTS_DIR, filename)
        
        if not os.path.exists(full_path):
            flash("Report file not found.")
            # Redirect based on user role
            if user_role == 'teacher':
                return redirect(url_for('view_attendance'))
            else:
                return redirect(url_for('admin_dashboard'))
        
        # Determine directory and file name for send_from_directory
        directory = os.path.dirname(full_path)
        file = os.path.basename(full_path)
        
        # Serve the file as attachment to trigger download
        return send_from_directory(directory=directory, filename=file, as_attachment=True)
    
    except Exception as e:
        flash(f"Error downloading file: {str(e)}")
        if user_role == 'teacher':
            return redirect(url_for('view_attendance'))
        else:
            return redirect(url_for('admin_dashboard'))

# Sample Images Management Routes
@app.route('/admin/sample-images')
def admin_sample_images():
    """Admin page to view all sample images"""
    return render_template('admin_sample_images.html')

@app.route('/api/sample-images')
def get_sample_images():
    """API to fetch sample images with filters"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status_filter = request.args.get('status', 'all')
    class_filter = request.args.get('class', 'all')
    search_query = request.args.get('search', '')

    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row

    # Build query with filters
    base_query = """
        SELECT id, student_id, student_name, image_filename, image_path, 
               upload_date, status, quality_score, class_name, file_size,
               rejection_reason, approved_by, approval_date
        FROM sample_images 
        WHERE 1=1
    """
    params = []

    if status_filter != 'all':
        base_query += " AND status = ?"
        params.append(status_filter)

    if class_filter != 'all':
        base_query += " AND class_name = ?"
        params.append(class_filter)

    if search_query:
        base_query += " AND (student_name LIKE ? OR student_id LIKE ?)"
        params.extend([f'%{search_query}%', f'%{search_query}%'])

    # Get total count
    count_query = base_query.replace('SELECT id, student_id, student_name, image_filename, image_path, upload_date, status, quality_score, class_name, file_size, rejection_reason, approved_by, approval_date', 'SELECT COUNT(*)')
    total_count = conn.execute(count_query, params).fetchone()[0]

    # Add pagination
    base_query += " ORDER BY upload_date DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    cursor = conn.execute(base_query, params)
    images = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        'images': images,
        'total': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page
    })

@app.route('/api/sample-image/<int:image_id>')
def get_sample_image_details(image_id):
    """Get detailed information about a specific sample image"""
    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("SELECT * FROM sample_images WHERE id = ?", (image_id,))
    image = cursor.fetchone()
    conn.close()

    if image:
        return jsonify(dict(image))
    else:
        return jsonify({'error': 'Image not found'}), 404

@app.route('/api/sample-image/<int:image_id>/approve', methods=['POST'])
def approve_sample_image(image_id):
    """Approve a sample image"""
    admin_id = request.json.get('admin_id', 'admin')

    conn = sqlite3.connect('attendance.db')
    conn.execute("""
        UPDATE sample_images 
        SET status = 'approved', 
            approved_by = ?, 
            approval_date = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (admin_id, image_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Image approved successfully'})

@app.route('/api/sample-image/<int:image_id>/reject', methods=['POST'])
def reject_sample_image(image_id):
    """Reject a sample image"""
    admin_id = request.json.get('admin_id', 'admin')
    reason = request.json.get('reason', 'Quality not acceptable')

    conn = sqlite3.connect('attendance.db')
    conn.execute("""
        UPDATE sample_images 
        SET status = 'rejected', 
            rejection_reason = ?,
            approved_by = ?, 
            approval_date = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (reason, admin_id, image_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Image rejected successfully'})

@app.route('/api/sample-images/bulk-action', methods=['POST'])
def bulk_sample_action():
    """Handle bulk actions on sample images"""
    action = request.json.get('action')
    image_ids = request.json.get('image_ids', [])
    admin_id = request.json.get('admin_id', 'admin')
    reason = request.json.get('reason', 'Bulk action')

    if not image_ids:
        return jsonify({'error': 'No images selected'}), 400

    conn = sqlite3.connect('attendance.db')

    if action == 'approve':
        placeholders = ','.join(['?' for _ in image_ids])
        conn.execute(f"""
            UPDATE sample_images 
            SET status = 'approved', 
                approved_by = ?, 
                approval_date = CURRENT_TIMESTAMP 
            WHERE id IN ({placeholders})
        """, [admin_id] + image_ids)
        message = f'{len(image_ids)} images approved successfully'

    elif action == 'reject':
        placeholders = ','.join(['?' for _ in image_ids])
        conn.execute(f"""
            UPDATE sample_images 
            SET status = 'rejected', 
                rejection_reason = ?,
                approved_by = ?, 
                approval_date = CURRENT_TIMESTAMP 
            WHERE id IN ({placeholders})
        """, [reason, admin_id] + image_ids)
        message = f'{len(image_ids)} images rejected successfully'

    else:
        conn.close()
        return jsonify({'error': 'Invalid action'}), 400

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': message})

@app.route('/uploads/samples/<filename>')
def serve_sample_image(filename):
    """Serve sample images"""
    return send_from_directory('database/photo', filename)

@app.route('/api/classes')
def get_classes():
    """Get list of all classes for filtering"""
    try:
        # Get from database if available
        conn = sqlite3.connect('attendance.db')
        cursor = conn.execute("SELECT DISTINCT class_name FROM sample_images WHERE class_name IS NOT NULL")
        db_classes = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        # Get from filesystem
        try:
            fs_classes = [d for d in os.listdir(os.path.join('database', 'photo')) 
                         if os.path.isdir(os.path.join('database', 'photo', d))]
        except:
            fs_classes = []
        
        # Combine and deduplicate
        all_classes = list(set(db_classes + fs_classes))
        return jsonify(all_classes)
        
    except Exception as e:
        print(f"Error getting classes: {e}")
        return jsonify([])

from init_db import initialize_database

if __name__ == "__main__":
    app.run(debug=True)
