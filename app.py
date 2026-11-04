import html

import streamlit as st

from database import create_department, delete_department, init_schema, list_departments
from student_system import (
    inject_css,
    notify,
    render_backup,
    render_dashboard,
    render_students,
    show_notifications,
)

st.set_page_config(page_title="Student Management System", layout="wide", page_icon="🎓")
inject_css()

NO_SELECTION = "Select a department"
st.session_state.setdefault("selected_db", None)
show_notifications()


def _on_create_department():
    name, error = create_department(st.session_state.get("new_dept_name", ""))
    if error:
        st.session_state["_dept_error"] = error
    else:
        st.session_state["dept_select"] = name
        st.session_state.pop("_dept_error", None)
        notify(f"Department '{name}' created.")


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown('<div class="brand">Student Records</div>'
                '<div class="brand-sub">Department workspace</div>', unsafe_allow_html=True)

    options = [NO_SELECTION] + list_departments()
    if st.session_state.get("dept_select") not in options:
        st.session_state["dept_select"] = NO_SELECTION
    choice = st.selectbox("Department", options, key="dept_select")
    st.session_state.selected_db = None if choice == NO_SELECTION else choice

    with st.expander("New department"):
        with st.form("create_department_form", clear_on_submit=True):
            st.text_input("Name", key="new_dept_name", placeholder="e.g. Artificial_Intelligence")
            st.form_submit_button("Create", on_click=_on_create_department)
        if st.session_state.get("_dept_error"):
            st.error(st.session_state["_dept_error"])

    if st.session_state.selected_db:
        with st.expander("Department settings"):
            active = st.session_state.selected_db
            confirm = st.checkbox(f"Confirm deletion of '{active}'", key=f"confirm_{active}")
            if st.button("Delete department", disabled=not confirm):
                try:
                    delete_department(active)
                except Exception as e:
                    st.error(f"Could not delete: {e}")
                else:
                    notify("Department deleted.", "🗑️")
                    st.rerun()

# -------------------------------------------------------------- main window
active = st.session_state.selected_db
subtitle = (f'Department <span class="hero-chip">{html.escape(active)}</span>'
            if active else "Select or create a department from the sidebar to begin")
st.markdown(
    f'<div class="hero"><div class="hero-title">Student Management System</div>'
    f'<div class="hero-sub">{subtitle}</div></div>',
    unsafe_allow_html=True,
)

if active:
    init_schema(active)  # creates / upgrades the table, never deletes data
    tab_dash, tab_students, tab_backup = st.tabs(["Dashboard", "Students", "Backup"])
    with tab_dash:
        render_dashboard()
    with tab_students:
        render_students()
    with tab_backup:
        render_backup()

st.markdown('<div class="app-footer">Student Management System · Streamlit &amp; SQLite</div>',
            unsafe_allow_html=True)
