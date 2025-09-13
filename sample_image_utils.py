# utils.py - Image processing utilities

import cv2
import numpy as np
import sqlite3
import os
from datetime import datetime

def calculate_image_quality(image_path):
    """Calculate image quality score based on various factors"""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return 0.0

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Calculate blur (Laplacian variance)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        blur_normalized = min(blur_score / 1000, 1.0)

        # Calculate brightness
        brightness = np.mean(gray)
        brightness_score = 1.0 - abs(brightness - 128) / 128

        # Calculate contrast
        contrast = gray.std()
        contrast_score = min(contrast / 64, 1.0)

        # Face detection
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        face_score = 1.0 if len(faces) == 1 else 0.5

        # Composite score
        quality_score = (blur_normalized * 0.4 + 
                        brightness_score * 0.2 + 
                        contrast_score * 0.2 + 
                        face_score * 0.2)

        return min(quality_score, 1.0)

    except Exception as e:
        print(f"Error calculating quality for {image_path}: {e}")
        return 0.0

def process_uploaded_image(file_path, student_id, student_name, class_name):
    """Process uploaded image and add to database"""
    try:
        quality_score = calculate_image_quality(file_path)
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)

        conn = sqlite3.connect('attendance.db')
        conn.execute("""
            INSERT INTO sample_images 
            (student_id, student_name, image_filename, image_path, 
             quality_score, file_size, class_name, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (student_id, student_name, filename, file_path, 
              quality_score, file_size, class_name))
        conn.commit()
        conn.close()

        return True

    except Exception as e:
        print(f"Error processing image: {e}")
        return False

def get_sample_statistics():
    """Get statistics about sample images"""
    conn = sqlite3.connect('attendance.db')

    # Get counts by status
    cursor = conn.execute("""
        SELECT status, COUNT(*) as count 
        FROM sample_images 
        GROUP BY status
    """)
    status_counts = dict(cursor.fetchall())

    # Get total count
    total = conn.execute("SELECT COUNT(*) FROM sample_images").fetchone()[0]

    # Get average quality
    avg_quality = conn.execute("SELECT AVG(quality_score) FROM sample_images").fetchone()[0]

    conn.close()

    return {
        'total': total,
        'pending': status_counts.get('pending', 0),
        'approved': status_counts.get('approved', 0),
        'rejected': status_counts.get('rejected', 0),
        'average_quality': avg_quality or 0
    }

def cleanup_rejected_images():
    """Remove rejected images from filesystem"""
    conn = sqlite3.connect('attendance.db')
    cursor = conn.execute("""
        SELECT image_path FROM sample_images 
        WHERE status = 'rejected' AND upload_date < date('now', '-30 days')
    """)

    for (image_path,) in cursor.fetchall():
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
                print(f"Removed old rejected image: {image_path}")
        except Exception as e:
            print(f"Error removing {image_path}: {e}")

    # Delete database records
    conn.execute("""
        DELETE FROM sample_images 
        WHERE status = 'rejected' AND upload_date < date('now', '-30 days')
    """)
    conn.commit()
    conn.close()