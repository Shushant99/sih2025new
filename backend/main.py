import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
import numpy as np
import cv2
import torch
from datetime import datetime
from PIL import Image
from facenet_pytorch import MTCNN, InceptionResnetV1
from openpyxl import Workbook

# ==============================
# CONFIGURATION
# ==============================
DATASET_DIR = os.path.join(BASE_DIR, "database", "photo") # Student images
CLASSROOM_IMG_DIR = os.path.join(BASE_DIR, "database", "class_img") # Classroom images
OUTPUT_DIR = os.path.join(BASE_DIR, "roster_embeddings") # Where to save embeddings
REPORTS_DIR = os.path.join(BASE_DIR, "reports") # Where to save reports

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"[INFO] Using device: {device}")

# Initialize models
mtcnn = MTCNN(keep_all=True, device=device)  # Detect all faces
model = InceptionResnetV1(pretrained='vggface2').eval().to(device)

# ==========================================
# Helper function for class report directory
# ==========================================
def get_class_report_dir(class_name):
    """Create and return class-specific report directory"""
    if not class_name:
        return REPORTS_DIR
    path = os.path.join(REPORTS_DIR, class_name)
    os.makedirs(path, exist_ok=True)
    return path

# ==========================================
# Generate face embedding for one image
# ==========================================
def generate_embedding(image_path):
    img = cv2.imread(image_path)
    if img is None:
        print(f"[WARNING] Unable to read image: {image_path}")
        return None

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)

    boxes, _ = mtcnn.detect(pil_img)
    if boxes is None:
        print(f"[WARNING] No face detected in: {image_path}")
        return None

    x1, y1, x2, y2 = [int(v) for v in boxes[0]]
    face_crop = pil_img.crop((x1, y1, x2, y2)).resize((160, 160))

    face_tensor = torch.tensor(np.array(face_crop)).permute(2, 0, 1).unsqueeze(0).float().to(device)
    face_tensor = (face_tensor - 127.5) / 128.0

    with torch.no_grad():
        embedding = model(face_tensor).cpu().numpy()[0]

    return embedding

# ==========================================
# Step 1: Build embeddings for specific class or all classes
# ==========================================
def build_class_embeddings(class_name=None):
    """
    Build embeddings for a specific class or all classes
    :param class_name: Specific class to process, or None for all classes
    """
    if class_name:
        # Process only the specified class
        class_folders = [class_name]
    else:
        # Process all classes
        class_folders = [f for f in os.listdir(DATASET_DIR) if os.path.isdir(os.path.join(DATASET_DIR, f))]

    for class_folder in class_folders:
        class_path = os.path.join(DATASET_DIR, class_folder)
        if not os.path.isdir(class_path):
            print(f"[WARNING] Class directory not found: {class_folder}")
            continue

        print(f"\n[INFO] Processing class: {class_folder}")
        embeddings = []
        names = []

        for student_name in os.listdir(class_path):
            student_folder = os.path.join(class_path, student_name)
            if not os.path.isdir(student_folder):
                continue

            print(f"  → Generating average embedding for: {student_name}")
            student_embeddings = []

            for img_file in os.listdir(student_folder):
                if img_file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    image_path = os.path.join(student_folder, img_file)
                    embedding = generate_embedding(image_path)
                    if embedding is not None:
                        student_embeddings.append(embedding)

            if len(student_embeddings) == 0:
                print(f"[WARNING] No valid faces for {student_name}, skipping...")
                continue

            avg_embedding = np.mean(student_embeddings, axis=0)
            embeddings.append(avg_embedding)
            names.append(student_name)

            print(f"     ✓ {len(student_embeddings)} images used for {student_name}")

        if len(embeddings) > 0:
            np.save(os.path.join(OUTPUT_DIR, f"{class_folder}_embeddings.npy"), np.array(embeddings))
            np.save(os.path.join(OUTPUT_DIR, f"{class_folder}_names.npy"), np.array(names))
            print(f"[SUCCESS] Saved embeddings for {class_folder} in '{OUTPUT_DIR}'")
        else:
            print(f"[WARNING] No embeddings generated for class: {class_folder}")

# ==========================================
# Load embeddings for specific class
# ==========================================
def load_class_embeddings(class_name):
    """
    Load embeddings for a specific class
    :param class_name: The class to load embeddings for
    :return: embeddings array and names array
    """
    emb_path = os.path.join(OUTPUT_DIR, f"{class_name}_embeddings.npy")
    names_path = os.path.join(OUTPUT_DIR, f"{class_name}_names.npy")
    
    if not os.path.exists(emb_path) or not os.path.exists(names_path):
        raise RuntimeError(f"No embeddings found for class {class_name}. Run build_class_embeddings('{class_name}') first.")
    
    embeddings = np.load(emb_path)
    names = np.load(names_path)
    
    return embeddings, names

# ==========================================
# Load all saved embeddings (fallback for backward compatibility)
# ==========================================
def load_all_embeddings():
    all_embeddings = []
    all_names = []
    for file in os.listdir(OUTPUT_DIR):
        if file.endswith("_embeddings.npy"):
            class_name = file.replace("_embeddings.npy", "")
            emb_path = os.path.join(OUTPUT_DIR, file)
            names_path = os.path.join(OUTPUT_DIR, f"{class_name}_names.npy")

            if not os.path.exists(names_path):
                print(f"[WARNING] Missing names file for {class_name}")
                continue

            embeddings = np.load(emb_path)
            names = np.load(names_path)
            all_embeddings.append(embeddings)
            all_names.extend(names)

    if len(all_embeddings) == 0:
        raise RuntimeError("No embeddings found. Run build_class_embeddings() first.")

    return np.vstack(all_embeddings), all_names

# ==========================================
# Generate embedding for detected face
# ==========================================
def get_face_embedding(face_img):
    face_tensor = torch.tensor(np.array(face_img)).permute(2, 0, 1).unsqueeze(0).float().to(device)
    face_tensor = (face_tensor - 127.5) / 128.0
    with torch.no_grad():
        return model(face_tensor).cpu().numpy()[0]

# ==========================================
# Match a face with known roster
# ==========================================
def match_face(face_embedding, roster_embeddings, roster_names, threshold=0.9):
    distances = np.linalg.norm(roster_embeddings - face_embedding, axis=1)
    min_idx = np.argmin(distances)
    min_dist = distances[min_idx]
    if min_dist < threshold:
        return roster_names[min_idx], min_dist
    return "Unknown", min_dist

# ==========================================
# Step 2: Process single classroom image (original function)
# ==========================================
def process_classroom_images(class_name=None):
    """
    Process classroom images for attendance (single image mode)
    :param class_name: Specific class to process, or None for all classes
    :return: Set of recognized students
    """
    if class_name:
        # Load embeddings for specific class only
        roster_embeddings, roster_names = load_class_embeddings(class_name)
        print(f"[INFO] Loaded embeddings for class: {class_name}")
    else:
        # Load all embeddings (fallback)
        roster_embeddings, roster_names = load_all_embeddings()
        print("[INFO] Loaded embeddings for all classes")
    
    recognized_students = set()

    for img_file in os.listdir(CLASSROOM_IMG_DIR):
        if not img_file.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue

        img_path = os.path.join(CLASSROOM_IMG_DIR, img_file)
        print(f"\n[INFO] Processing classroom image: {img_path}")

        img = cv2.imread(img_path)
        if img is None:
            print(f"[ERROR] Could not read image: {img_path}")
            continue

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)

        boxes, _ = mtcnn.detect(pil_img)
        if boxes is None:
            print("[WARNING] No faces detected in this image.")
            continue

        for box in boxes:
            x1, y1, x2, y2 = [int(b) for b in box]
            face_crop = pil_img.crop((x1, y1, x2, y2)).resize((160, 160))

            face_embedding = get_face_embedding(face_crop)
            name, dist = match_face(face_embedding, roster_embeddings, roster_names)

            if name != "Unknown":
                recognized_students.add(name)

            # Draw bounding box
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(img, f"{name} ({dist:.2f})", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        output_img_path = os.path.join(CLASSROOM_IMG_DIR, f"result_{img_file}")
        cv2.imwrite(output_img_path, img)
        print(f"[INFO] Saved processed image: {output_img_path}")

    return recognized_students

# ==========================================
# Step 2: Process multiple classroom images (enhanced accuracy)
# ==========================================
def process_multiple_classroom_images(class_name=None):
    """
    Process multiple classroom images for enhanced attendance accuracy
    :param class_name: Specific class to process, or None for all classes
    :return: Set of recognized students with confidence scores
    """
    if class_name:
        # Load embeddings for specific class only
        roster_embeddings, roster_names = load_class_embeddings(class_name)
        print(f"[INFO] Loaded embeddings for class: {class_name}")
    else:
        # Load all embeddings (fallback)
        roster_embeddings, roster_names = load_all_embeddings()
        print("[INFO] Loaded embeddings for all classes")
    
    # Dictionary to track student recognition across multiple images
    student_detections = {}
    for name in roster_names:
        student_detections[name] = []
    
    total_images = 0
    
    # Process each classroom image
    for img_file in os.listdir(CLASSROOM_IMG_DIR):
        if not img_file.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue

        img_path = os.path.join(CLASSROOM_IMG_DIR, img_file)
        print(f"\n[INFO] Processing classroom image: {img_path}")
        total_images += 1

        img = cv2.imread(img_path)
        if img is None:
            print(f"[ERROR] Could not read image: {img_path}")
            continue

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)

        boxes, _ = mtcnn.detect(pil_img)
        if boxes is None:
            print("[WARNING] No faces detected in this image.")
            continue

        faces_in_image = 0
        for box in boxes:
            x1, y1, x2, y2 = [int(b) for b in box]
            face_crop = pil_img.crop((x1, y1, x2, y2)).resize((160, 160))

            face_embedding = get_face_embedding(face_crop)
            name, dist = match_face(face_embedding, roster_embeddings, roster_names)

            if name != "Unknown":
                student_detections[name].append({
                    'distance': dist,
                    'image': img_file,
                    'confidence': max(0, 1 - dist)  # Convert distance to confidence
                })
                faces_in_image += 1

            # Draw bounding box on image
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(img, f"{name} ({dist:.2f})", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        print(f"[INFO] Detected {faces_in_image} faces in {img_file}")

        # Save processed image
        output_img_path = os.path.join(CLASSROOM_IMG_DIR, f"result_{img_file}")
        cv2.imwrite(output_img_path, img)

    # Determine final attendance based on multiple detections
    print(f"\n[INFO] Analyzing attendance across {total_images} images...")
    recognized_students = set()
    
    for student_name, detections in student_detections.items():
        if len(detections) > 0:
            # Calculate average confidence and detection frequency
            avg_confidence = sum(d['confidence'] for d in detections) / len(detections)
            detection_frequency = len(detections) / total_images
            
            # Student is considered present if:
            # 1. Average confidence > 0.6, OR
            # 2. Detected in at least 30% of images with confidence > 0.5
            if avg_confidence > 0.6 or (detection_frequency >= 0.3 and avg_confidence > 0.5):
                recognized_students.add(student_name)
                print(f"[PRESENT] {student_name} - Avg confidence: {avg_confidence:.3f}, "
                      f"Frequency: {detection_frequency:.2f} ({len(detections)}/{total_images})")
            else:
                print(f"[UNCERTAIN] {student_name} - Low confidence/frequency: "
                      f"{avg_confidence:.3f}, {detection_frequency:.2f}")

    print(f"\n[SUMMARY] {len(recognized_students)} students marked present from {total_images} images")
    return recognized_students

# ==========================================
# Step 3: Generate Excel Report for specific class
# ==========================================
def generate_excel_report(students_present, class_name=None):
    """
    Generate Excel attendance report with Present and Absent status.
    :param students_present: Set of names of students detected as present.
    :param class_name: Specific class name for report generation
    :return: Dictionary of results and filename
    """
    # --- Load student names for specific class or all classes ---
    if class_name:
        # Load names for specific class only
        names_path = os.path.join(OUTPUT_DIR, f"{class_name}_names.npy")
        if os.path.exists(names_path):
            all_students = list(np.load(names_path))
        else:
            print(f"[ERROR] No student names found for class: {class_name}")
            all_students = []
    else:
        # Load all student names (fallback)
        all_students = []
        for file in os.listdir(OUTPUT_DIR):
            if file.endswith("_names.npy"):
                names_path = os.path.join(OUTPUT_DIR, file)
                class_students = np.load(names_path)
                all_students.extend(class_students)

    # --- Prepare results dictionary ---
    results = {}
    for student in sorted(all_students):
        status = "Present" if student in students_present else "Absent"
        results[student] = status

    # --- Generate Excel file ---
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Attendance Report"
    
    # Add headers
    sheet.append(["Student Name", "Status"])
    
    # Fill attendance data
    for student, status in results.items():
        sheet.append([student, status])

    # --- Save report with class-specific naming and location ---
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    if class_name:
        filename = f"attendance_{class_name}_{timestamp}.xlsx"
        report_dir = get_class_report_dir(class_name)
    else:
        filename = f"attendance_{timestamp}.xlsx"
        report_dir = REPORTS_DIR
    
    report_path = os.path.join(report_dir, filename)
    workbook.save(report_path)
    print(f"[SUCCESS] Attendance report saved at: {report_path}")

    return results, filename

# ==========================================
# Clear old results
# ==========================================
def clear_old_results():
    for file in os.listdir(CLASSROOM_IMG_DIR):
        if file.startswith("result_"):
            os.remove(os.path.join(CLASSROOM_IMG_DIR, file))
            print(f"[INFO] Removed old result file: {file}")

# ==========================================
# MAIN (for testing purposes)
# ==========================================
if __name__ == "__main__":
    print("[STEP 1] Building class embeddings...")
    build_class_embeddings()

    clear_old_results()
    
    print("\n[STEP 2] Processing classroom images...")
    students_present = process_classroom_images()

    print("\n[STEP 3] Generating Excel report...")
    results, filename = generate_excel_report(students_present)

    print("\n[FINISHED] Workflow completed successfully!")
