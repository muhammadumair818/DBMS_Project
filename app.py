import streamlit as st

from crud_operations import (
    flash,
    render_crud_operations,
    render_csv_uploader,
    render_table_manager,
    show_flash,
)
from database import create_department, delete_department, init_schema, list_departments
from student_system import (
    render_attendance,
    render_courses,
    render_dashboard,
    render_enrollment,
    render_fees,
    render_results,
    render_students,
)

st.set_page_config(page_title="Student Management System", layout="wide", page_icon="🎓")
st.title("🎓 Student Management System")

NO_SELECTION = "-- Select --"
st.session_state.setdefault("selected_db", None)

show_flash()

# ------------------------------------------------------------------ sidebar
st.sidebar.header("🏫 Department / Campus")

with st.sidebar.form("create_department_form", clear_on_submit=True):
    new_dept = st.text_input("New Department Name:")
    create_clicked = st.form_submit_button("Create Department")

if create_clicked:
    name, error = create_department(new_dept)
    if error:
        st.sidebar.error(error)
    else:
        st.session_state["dept_select"] = name  # auto-select the new department
        st.sidebar.success(f"Department '{name}' created!")

options = [NO_SELECTION] + list_departments()
if st.session_state.get("dept_select") not in options:
    st.session_state["dept_select"] = NO_SELECTION

choice = st.sidebar.selectbox("Select Active Department:", options, key="dept_select")
st.session_state.selected_db = None if choice == NO_SELECTION else choice

if st.session_state.selected_db:
    active = st.session_state.selected_db
    init_schema(active)  # makes sure all student-system tables exist (also for old .db files)

    st.sidebar.markdown("---")
    st.sidebar.warning(f"Danger Zone: {active}")
    confirm = st.sidebar.checkbox(f"Yes, delete '{active}' and all its data", key=f"confirm_{active}")
    if st.sidebar.button("🚨 Delete Department File", disabled=not confirm):
        try:
            delete_department(active)
        except Exception as e:
            st.sidebar.error(f"Error deleting file: {e}")
        else:
            st.session_state.selected_db = None
            flash("Department file deleted!")
            st.rerun()

# -------------------------------------------------------------- main window
if not st.session_state.selected_db:
    st.info("👈 Create or select a Department from the sidebar to get started.")
else:
    st.header(f"📍 {st.session_state.selected_db}")

    tabs = st.tabs([
        "📊 Dashboard", "🎓 Students", "📚 Courses", "📝 Enrollment",
        "🗓️ Attendance", "🏆 Results", "💰 Fees", "⚙️ Advanced Tools",
    ])
    with tabs[0]:
        render_dashboard()
    with tabs[1]:
        render_students()
    with tabs[2]:
        render_courses()
    with tabs[3]:
        render_enrollment()
    with tabs[4]:
        render_attendance()
    with tabs[5]:
        render_results()
    with tabs[6]:
        render_fees()
    with tabs[7]:
        st.caption("Build your own extra tables here. The core student tables are managed from the other tabs.")
        adv1, adv2, adv3 = st.tabs(["🏗️ Table Architect", "📥 CSV Smart Loader", "📝 Data Workspace (CRUD)"])
        with adv1:
            render_table_manager()
        with adv2:
            render_csv_uploader()
        with adv3:
            render_crud_operations()
