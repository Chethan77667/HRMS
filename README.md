# Human Resource Management System (HRMS) - College Edition

This is a premium, web-based Live College Office Management System built with Python (Flask), MongoDB, and Tailwind CSS.

## 🚀 Setup & Run Procedure

### 1. Prerequisites
- Python 3.8+ installed.
- MongoDB Server installed and running locally (default: `mongodb://localhost:27017/`).
- (For Timetable PDF auto-detection) Tesseract OCR installed on Windows.

### 2. Installation
Open your terminal in the project directory (`d:\HRMS`) and run:
```bash
pip install -r requirements.txt
```

### 2.1 (Windows) Install Tesseract OCR (required for scanned PDFs)
If your timetable PDF pages are scanned images (not selectable text), OCR is required.

- Install **Tesseract OCR for Windows**.
- Ensure the install folder is added to your **PATH**, or set an env var `TESSERACT_CMD` to the full exe path.

Example (PowerShell, current session):

```powershell
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
python app.py
```

### 3. Environment Configuration
The system uses a `.env` file for configuration. A default one has been created for you.
- Ensure MongoDB is running.
- (Optional) Modify `MONGO_URI` in `.env` if your database is hosted elsewhere.

### 4. Running the Application
Run the following command:
```bash
python app.py
```

### 5. Accessing the System
Open your web browser and go to:
[http://127.0.0.1:5000](http://127.0.0.1:5000)

### 🔑 Demo Credentials
- **Admin Access:**
  - Username: `admin`
  - Password: `admin123`
- **Lecturer Access:**
  - Username: `lecturer`
  - Password: `lect123`

## 🛠️ Project Modules
1. **Admin Module:** Complete control over staff, leave approvals, and payroll.
2. **Lecturer Module:** Personal profile, leave applications, and schedule viewing.
3. **AI Integration (Experimental):** Predictive analytics for leave and attendance patterns (integrated via FastAI hooks).

## 📂 Project Structure
- `/templates`: HTML views styled with Tailwind CSS.
- `/utils`: Database and helper logic.
- `app.py`: Main Flask application server.
- `.env`: System configurations.
