import streamlit as st

from crud_operations import (
    flash,
    render_crud_operations,
    render_csv_uploader,
    render_table_manager,
    show_flash,
)
from database import create_department, delete_department, list_departments

st.set_page_config(page_title="Dynamic EduManager (SQLite)", layout="wide", page_icon="🏫")
st.title("🏫 Dynamic Department & Student Manager (SQLite Version)")

NO_SELECTION = "-- Select --"
st.session_state.setdefault("selected_db", None)

show_flash()

# ------------------------------------------------------------------ sidebar
st.sidebar.header("📁 Department Setup")

with st.sidebar.form("create_department_form", clear_on_submit=True):
    new_dept = st.text_input("New Department Name:")
    create_clicked = st.form_submit_button("Create Department")

if create_clicked:
    name, error = create_department(new_dept)
    if error:
        st.sidebar.error(error)
    else:
        st.session_state["dept_select"] = name  # auto-select the new department
        st.sidebar.success(f"Department '{name}' created as a local file!")

options = [NO_SELECTION] + list_departments()
# If the stored choice no longer exists (e.g. deleted), fall back to "-- Select --"
if st.session_state.get("dept_select") not in options:
    st.session_state["dept_select"] = NO_SELECTION

choice = st.sidebar.selectbox("Select Active Department:", options, key="dept_select")
st.session_state.selected_db = None if choice == NO_SELECTION else choice

# Danger zone for the active department
if st.session_state.selected_db:
    active = st.session_state.selected_db
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
    st.info("👈 Please select or create a Department from the sidebar to activate the SQLite local system.")
else:
    st.header(f"📍 Active Department Workspace: {st.session_state.selected_db}")

    tab1, tab2, tab3 = st.tabs(["🏗️ Table Architect", "📥 CSV Smart Loader", "📝 Data Workspace (CRUD)"])
    with tab1:
        render_table_manager()
    with tab2:
        render_csv_uploader()
    with tab3:
        render_crud_operations()
