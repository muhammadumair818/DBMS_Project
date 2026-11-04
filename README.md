# Student Management System

A clean, department-based student records app built with Streamlit and SQLite.

## Features
- **Dashboard** – total students, average GPA, fee status, GPA distribution, top students, pending fees
- **Students** – directory with search/filter/sort, add, edit, photo, bulk fee update, CSV import/export,
  printable PDF profile, Recycle Bin (restore deleted students)
- **Backup** – download a database backup and restore it later (a safety copy is saved automatically)
- Each department keeps its own data in its own `.db` file

## Student fields
Roll No, Name, Father Name, Email, Phone Number, Address, Fee Submitted (Yes/No), GPA (0.00 – 4.00), Photo

## Run
```
pip install -r requirements.txt
streamlit run app.py
```
Keep the `.streamlit` folder next to `app.py` (it contains the theme).
