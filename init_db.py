import sqlite3
import os

DB_PATH = 'attendance.db'
PHOTO_ROOT = os.path.join('database', 'photo')

def initialize_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sample_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id VARCHAR(50),
        student_name VARCHAR(100) NOT NULL,
        image_filename VARCHAR(255) NOT NULL,
        image_path TEXT,
        upload_date DATE DEFAULT CURRENT_DATE,
        status VARCHAR(20) DEFAULT 'pending',
        quality_score FLOAT DEFAULT 0.0,
        class_name VARCHAR(50) NOT NULL,
        file_size INTEGER DEFAULT 0,
        rejection_reason TEXT,
        approved_by VARCHAR(50),
        approval_date DATETIME
    );
    """)
    conn.commit()
    conn.close()
    print("sample_images table created!")

def populate_sample_images():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for class_name in os.listdir(PHOTO_ROOT):
        class_dir = os.path.join(PHOTO_ROOT, class_name)
        if not os.path.isdir(class_dir):
            continue

        for student_name in os.listdir(class_dir):
            student_dir = os.path.join(class_dir, student_name)
            if not os.path.isdir(student_dir):
                continue

            for imgfile in os.listdir(student_dir):
                if imgfile.lower().endswith(('.jpg', '.jpeg', '.png')):
                    abs_path = os.path.abspath(os.path.join(student_dir, imgfile))

                    # Check if entry already exists
                    cursor.execute(
                        "SELECT COUNT(*) FROM sample_images WHERE image_filename=? AND student_name=? AND class_name=?", 
                        (imgfile, student_name, class_name)
                    )
                    if cursor.fetchone()[0] == 0:
                        cursor.execute("""
                            INSERT INTO sample_images (student_id, student_name, image_filename, image_path, class_name, status)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (None, student_name, imgfile, abs_path, class_name, "approved"))
                        print(f"Added to DB: {student_name} ({class_name}) -> {imgfile}")

    conn.commit()
    conn.close()
    print("Sample images populated into database.")

if __name__ == "__main__":
    initialize_database()
    populate_sample_images()
