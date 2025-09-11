from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, session
import os
import base64
from datetime import datetime
from io import BytesIO
from PIL import Image
from functools import wraps
import json
from werkzeug.security import generate_password_hash, check_password_hash
from backend.main import build_class_embeddings, process_classroom_images, generate_excel_report

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

# Simple user store for demo (replace with DB in prod)
users = {
    'teacher1': {'password': 'teachpass', 'role': 'teacher'},
    'admin1': {'password': 'adminpass', 'role': 'admin'}
}

# Load or initialize user database
def load_users():
    if not os.path.exists(USERS_FILE):
        # Create default users
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
            # Reset to default if file empty/corrupt
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
# New route to add teacher (admin only)
@app.route("/add_teacher", methods=["GET", "POST"])
@role_required('admin')
def add_teacher():
    if request.method == "POST":
        new_userid = request.form.get("userid")
        new_password = request.form.get("password")
        role = request.form.get("role")
        class_name = request.form.get("class")  # Get class from form
        
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
# ==============================
# Admin Routes
# ==============================

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
    except:
        total_classes = 0
    
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
    
    return render_template("admin_dashboard.html", 
                         reports=reports, 
                         user_list=user_list,
                         total_users=total_users,
                         total_teachers=total_teachers,
                         total_admins=total_admins,
                         total_classes=total_classes)
# ==============================
# Shared Routes
# ==============================
def get_class_report_dir(class_name):
    """Create and return class-specific report directory"""
    if not class_name:
        return REPORTS_DIR
    path = os.path.join(REPORTS_DIR, class_name)
    os.makedirs(path, exist_ok=True)
    return path


@app.route("/download_report/<filename>")
def download_report(filename):
    """Download attendance report files"""
    try:
        # For teachers, look in their class-specific folder first
        if session.get('role') == 'teacher':
            teacher_class = session.get('class')
            if teacher_class:
                class_report_dir = get_class_report_dir(teacher_class)
                class_report_path = os.path.join(class_report_dir, filename)
                
                # Check if file exists in class folder
                if os.path.exists(class_report_path):
                    return send_from_directory(class_report_dir, filename, as_attachment=True)
        
        # Fallback: Look in main reports directory
        main_report_path = os.path.join(REPORTS_DIR, filename)
        if os.path.exists(main_report_path):
            return send_from_directory(REPORTS_DIR, filename, as_attachment=True)
        
        # If file not found in either location
        flash("Report file not found.")
        return redirect(url_for('view_attendance'))
        
    except Exception as e:
        flash(f"Error downloading report: {str(e)}")
        return redirect(url_for('view_attendance'))

# Create class subdirectories as needed


if __name__ == "__main__":
    app.run(debug=True)
