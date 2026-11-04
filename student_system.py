"""Student Management System pages."""
import calendar
import sqlite3
from datetime import date

import pandas as pd
import streamlit as st

from crud_operations import clean_cell, flash
from database import db_session

GENDERS = ["Male", "Female", "Other"]
STATUSES = ["Active", "Inactive", "Graduated"]
ATT_STATUSES = ["Present", "Absent", "Leave"]
EXAM_TYPES = ["Quiz", "Assignment", "Midterm", "Final", "Other"]
GRADE_SCALE = [(80, "A+"), (70, "A"), (60, "B"), (50, "C"), (40, "D")]
LOW_ATTENDANCE = 75  # percent
STUDENT_COLS = ["roll_no", "name", "father_name", "gender", "dob", "phone", "email", "address", "admission_date", "status"]


# ------------------------------------------------------------------ helpers
def _db():
    return st.session_state.selected_db


def run_query(sql, params=()):
    with db_session(_db()) as conn:
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame([tuple(r) for r in rows], columns=cols)


def run_exec(sql, params=(), dup_msg="This record already exists."):
    """Returns (rowcount, error_message)."""
    try:
        with db_session(_db()) as conn:
            cur = conn.execute(sql, params)
            return cur.rowcount, None
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e):
            return 0, dup_msg
        return 0, f"Integrity error: {e}"
    except sqlite3.Error as e:
        return 0, str(e)


def run_many(sql, rows):
    """Returns error message or None."""
    try:
        with db_session(_db()) as conn:
            conn.executemany(sql, rows)
        return None
    except sqlite3.Error as e:
        return str(e)


def _nonce():
    return st.session_state.setdefault("_nonce", 0)


def _bump():
    st.session_state["_nonce"] = _nonce() + 1


def _txt(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    return str(v)


def _to_date(value, lo=date(1970, 1, 1), hi=None):
    hi = hi or date.today()
    try:
        d = date.fromisoformat(str(value)[:10])
    except Exception:
        d = date.today()
    return max(lo, min(d, hi))


def grade_for(pct):
    if pct is None or pd.isna(pct):
        return ""
    for limit, g in GRADE_SCALE:
        if pct >= limit:
            return g
    return "F"


def student_map(active_only=False):
    sql = "SELECT id, roll_no, name FROM students"
    if active_only:
        sql += " WHERE status='Active'"
    df = run_query(sql + " ORDER BY roll_no")
    return {int(r.id): f"{r.roll_no} — {r.name}" for r in df.itertuples()}


def course_map():
    df = run_query("SELECT id, code, title FROM courses ORDER BY code")
    return {int(r.id): f"{r.code} — {r.title}" for r in df.itertuples()}


def _csv_button(label, df, filename, key):
    if not df.empty:
        st.download_button(label, df.to_csv(index=False).encode("utf-8"), filename, "text/csv", key=key)


# ---------------------------------------------------------------- dashboard
def render_dashboard():
    st.subheader("📊 Overview")
    stu = run_query("SELECT COUNT(*) AS total, COALESCE(SUM(status='Active'), 0) AS active FROM students").iloc[0]
    n_courses = int(run_query("SELECT COUNT(*) FROM courses").iloc[0, 0])
    n_enr = int(run_query("SELECT COUNT(*) FROM enrollments").iloc[0, 0])
    att = run_query("SELECT AVG(status='Present') * 100 AS rate FROM attendance").iloc[0, 0]
    fees = run_query("SELECT COALESCE(SUM(amount), 0) AS due, COALESCE(SUM(paid), 0) AS paid FROM fees").iloc[0]

    c = st.columns(4)
    c[0].metric("Total Students", int(stu["total"]))
    c[1].metric("Active Students", int(stu["active"]))
    c[2].metric("Courses", n_courses)
    c[3].metric("Enrollments", n_enr)
    c = st.columns(3)
    c[0].metric("Overall Attendance", "—" if att is None or pd.isna(att) else f"{att:.1f}%")
    c[1].metric("Fees Collected", f"{float(fees['paid']):,.0f}")
    c[2].metric("Fees Pending", f"{float(fees['due'] - fees['paid']):,.0f}")

    left, right = st.columns(2)
    with left:
        st.markdown("**Students by gender**")
        df = run_query("SELECT gender, COUNT(*) AS students FROM students GROUP BY gender")
        if df.empty:
            st.caption("No students yet.")
        else:
            st.bar_chart(df.set_index("gender"))
    with right:
        st.markdown("**Enrollment per course**")
        df = run_query(
            "SELECT c.code, COUNT(e.id) AS enrolled FROM courses c "
            "LEFT JOIN enrollments e ON e.course_id = c.id GROUP BY c.id ORDER BY c.code"
        )
        if df.empty:
            st.caption("No courses yet.")
        else:
            st.bar_chart(df.set_index("code"))

    st.markdown(f"**⚠️ Low attendance (below {LOW_ATTENDANCE}%)**")
    low = run_query(
        """SELECT s.roll_no, s.name, c.code AS course,
                  ROUND(100.0 * SUM(a.status = 'Present') / COUNT(*), 1) AS attendance_pct
           FROM attendance a JOIN students s ON s.id = a.student_id JOIN courses c ON c.id = a.course_id
           GROUP BY a.student_id, a.course_id HAVING attendance_pct < ? ORDER BY attendance_pct""",
        (LOW_ATTENDANCE,),
    )
    if low.empty:
        st.caption("No students below the threshold.")
    else:
        st.dataframe(low, hide_index=True)

    st.markdown("**Recently added students**")
    recent = run_query("SELECT roll_no, name, status, admission_date FROM students ORDER BY id DESC LIMIT 5")
    if recent.empty:
        st.caption("No students yet. Add some from the Students tab.")
    else:
        st.dataframe(recent, hide_index=True)


# ----------------------------------------------------------------- students
def _student_form_fields(prefix, row=None):
    """Draws the shared student fields; returns a dict of the entered values."""
    g = lambda k: _txt(row[k]) if row is not None else ""
    c1, c2 = st.columns(2)
    roll_no = c1.text_input("Roll No *", value=g("roll_no"), key=f"{prefix}_roll")
    name = c2.text_input("Full Name *", value=g("name"), key=f"{prefix}_name")
    father = c1.text_input("Father's Name", value=g("father_name"), key=f"{prefix}_father")
    gender_val = g("gender")
    gender = c2.selectbox("Gender", GENDERS, index=GENDERS.index(gender_val) if gender_val in GENDERS else 0, key=f"{prefix}_gender")
    dob = c1.date_input("Date of Birth", value=_to_date(g("dob") or "2005-01-01"), min_value=date(1970, 1, 1), max_value=date.today(), key=f"{prefix}_dob")
    phone = c2.text_input("Phone", value=g("phone"), key=f"{prefix}_phone")
    email = c1.text_input("Email", value=g("email"), key=f"{prefix}_email")
    admission = c2.date_input("Admission Date", value=_to_date(g("admission_date"), hi=date(2100, 1, 1)), min_value=date(1970, 1, 1), max_value=date(2100, 1, 1), key=f"{prefix}_adm")
    status_val = g("status")
    status = c1.selectbox("Status", STATUSES, index=STATUSES.index(status_val) if status_val in STATUSES else 0, key=f"{prefix}_status")
    address = st.text_area("Address", value=g("address"), key=f"{prefix}_addr")
    return {
        "roll_no": roll_no.strip(), "name": name.strip(), "father_name": father.strip(), "gender": gender,
        "dob": dob.isoformat(), "phone": phone.strip(), "email": email.strip(),
        "address": address.strip(), "admission_date": admission.isoformat(), "status": status,
    }


def _validate_student(v):
    if not v["roll_no"] or not v["name"]:
        return "Roll No and Full Name are required."
    if v["email"] and "@" not in v["email"]:
        return "Please enter a valid email address."
    return None


def render_students():
    t_list, t_add, t_edit, t_import, t_prof = st.tabs(
        ["📋 All Students", "➕ Add Student", "✏️ Edit / Delete", "📥 Import CSV", "👤 Student Profile"]
    )

    with t_list:
        c1, c2, c3 = st.columns([2, 1, 1])
        q = c1.text_input("Search (name, roll no, phone)", key="stu_search")
        status_f = c2.selectbox("Status", ["All"] + STATUSES, key="stu_status_f")
        gender_f = c3.selectbox("Gender", ["All"] + GENDERS, key="stu_gender_f")
        sql = "SELECT roll_no, name, father_name, gender, dob, phone, email, admission_date, status FROM students WHERE 1=1"
        params = []
        if q:
            sql += " AND (name LIKE ? OR roll_no LIKE ? OR phone LIKE ?)"
            params += [f"%{q}%"] * 3
        if status_f != "All":
            sql += " AND status = ?"
            params.append(status_f)
        if gender_f != "All":
            sql += " AND gender = ?"
            params.append(gender_f)
        df = run_query(sql + " ORDER BY roll_no", params)
        st.caption(f"{len(df)} student(s) found")
        st.dataframe(df, hide_index=True)
        _csv_button("⬇️ Download CSV", df, "students.csv", "dl_students")

    with t_add:
        with st.form("add_student_form", clear_on_submit=True):
            vals = _student_form_fields(f"add{_nonce()}")
            submitted = st.form_submit_button("Save Student")
        if submitted:
            err = _validate_student(vals)
            if err:
                st.error(err)
            else:
                _, err = run_exec(
                    f"INSERT INTO students ({', '.join(STUDENT_COLS)}) VALUES ({', '.join('?' * len(STUDENT_COLS))})",
                    [vals[c] for c in STUDENT_COLS],
                    dup_msg=f"Roll No '{vals['roll_no']}' already exists.",
                )
                if err:
                    st.error(err)
                else:
                    flash(f"Student '{vals['name']}' added.")
                    st.rerun()

    with t_edit:
        smap = student_map()
        if not smap:
            st.info("No students yet.")
        else:
            sid = st.selectbox("Select student", list(smap), format_func=smap.get, key="stu_edit_sel")
            row = run_query("SELECT * FROM students WHERE id = ?", (sid,)).iloc[0]
            with st.form(f"edit_student_form_{sid}"):
                vals = _student_form_fields(f"edit{sid}", row)
                saved = st.form_submit_button("Update Student")
            if saved:
                err = _validate_student(vals)
                if err:
                    st.error(err)
                else:
                    set_sql = ", ".join(f"{c} = ?" for c in STUDENT_COLS)
                    _, err = run_exec(
                        f"UPDATE students SET {set_sql} WHERE id = ?",
                        [vals[c] for c in STUDENT_COLS] + [sid],
                        dup_msg=f"Roll No '{vals['roll_no']}' already belongs to another student.",
                    )
                    if err:
                        st.error(err)
                    else:
                        flash("Student updated.")
                        st.rerun()

            st.markdown("---")
            st.caption("Deleting a student also removes their enrollments, attendance, results and fee records.")
            ok = st.checkbox(f"Yes, permanently delete {smap[sid]}", key=f"stu_del_ok_{sid}")
            if st.button("🗑️ Delete Student", disabled=not ok, key="stu_del_btn"):
                _, err = run_exec("DELETE FROM students WHERE id = ?", (sid,))
                if err:
                    st.error(err)
                else:
                    flash("Student deleted.")
                    st.rerun()

    with t_import:
        st.write("Upload a CSV with these columns (only **roll_no** and **name** are required):")
        template = pd.DataFrame([{
            "roll_no": "CS-001", "name": "Ali Khan", "father_name": "Ahmed Khan", "gender": "Male",
            "dob": "2005-03-15", "phone": "03001234567", "email": "ali@example.com",
            "address": "Rawalpindi", "admission_date": "2026-09-01", "status": "Active",
        }])
        _csv_button("⬇️ Download CSV template", template, "students_template.csv", "dl_template")
        up = st.file_uploader("Students CSV", type=["csv"], key="stu_import_file")
        if up:
            try:
                up.seek(0)
                df = pd.read_csv(up, dtype=str)
            except Exception as e:
                st.error(f"Could not read this CSV: {e}")
                df = None
            if df is not None:
                df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
                st.dataframe(df.head(5), hide_index=True)
                if "roll_no" not in df.columns or "name" not in df.columns:
                    st.error("CSV must contain 'roll_no' and 'name' columns.")
                elif st.button("Import Students", key="stu_import_btn"):
                    added = skipped = 0
                    sql = f"INSERT OR IGNORE INTO students ({', '.join(STUDENT_COLS)}) VALUES ({', '.join('?' * len(STUDENT_COLS))})"
                    with db_session(_db()) as conn:
                        for rec in df.to_dict("records"):
                            v = {c: _txt(clean_cell(rec.get(c))).strip() for c in STUDENT_COLS}
                            if not v["roll_no"] or not v["name"]:
                                skipped += 1
                                continue
                            v["gender"] = v["gender"].capitalize() if v["gender"].capitalize() in GENDERS else "Male"
                            v["status"] = v["status"].capitalize() if v["status"].capitalize() in STATUSES else "Active"
                            v["dob"], v["admission_date"] = v["dob"][:10], v["admission_date"][:10]
                            cur = conn.execute(sql, [v[c] for c in STUDENT_COLS])
                            added += cur.rowcount
                            skipped += 1 - cur.rowcount
                    st.success(f"Imported {added} student(s). Skipped {skipped} (duplicate roll no or missing data).")

    with t_prof:
        smap = student_map()
        if not smap:
            st.info("No students yet.")
            return
        sid = st.selectbox("Select student", list(smap), format_func=smap.get, key="stu_prof_sel")
        s = run_query("SELECT * FROM students WHERE id = ?", (sid,)).iloc[0]
        st.markdown(f"### {s['name']}  ·  `{s['roll_no']}`")
        a, b, c = st.columns(3)
        a.write(f"**Father:** {_txt(s['father_name']) or '—'}")
        a.write(f"**Gender:** {_txt(s['gender']) or '—'}")
        b.write(f"**DOB:** {_txt(s['dob']) or '—'}")
        b.write(f"**Phone:** {_txt(s['phone']) or '—'}")
        c.write(f"**Email:** {_txt(s['email']) or '—'}")
        c.write(f"**Status:** {s['status']}")
        st.write(f"**Address:** {_txt(s['address']) or '—'}")

        st.markdown("#### Courses & attendance")
        att = run_query(
            """SELECT c.code, c.title, COUNT(a.id) AS classes,
                      COALESCE(SUM(a.status = 'Present'), 0) AS present,
                      ROUND(100.0 * SUM(a.status = 'Present') / NULLIF(COUNT(a.id), 0), 1) AS attendance_pct
               FROM enrollments e JOIN courses c ON c.id = e.course_id
               LEFT JOIN attendance a ON a.course_id = e.course_id AND a.student_id = e.student_id
               WHERE e.student_id = ? GROUP BY c.id ORDER BY c.code""",
            (sid,),
        )
        st.dataframe(att, hide_index=True) if not att.empty else st.caption("Not enrolled in any course.")

        st.markdown("#### Results")
        res = run_query(
            """SELECT c.code AS course, r.exam_type, r.obtained_marks AS obtained, r.total_marks AS total
               FROM results r JOIN courses c ON c.id = r.course_id WHERE r.student_id = ? ORDER BY c.code, r.exam_type""",
            (sid,),
        )
        if res.empty:
            st.caption("No results recorded.")
        else:
            res["percentage"] = (res["obtained"] / res["total"] * 100).round(1)
            res["grade"] = res["percentage"].map(grade_for)
            st.dataframe(res, hide_index=True)
            overall = res["obtained"].sum() / res["total"].sum() * 100
            st.metric("Overall percentage", f"{overall:.1f}%  ({grade_for(overall)})")

        st.markdown("#### Fees")
        fee = run_query(
            """SELECT fee_month AS month, amount, paid, amount - paid AS balance,
                      CASE WHEN paid >= amount THEN 'Paid' WHEN paid > 0 THEN 'Partial' ELSE 'Unpaid' END AS status
               FROM fees WHERE student_id = ? ORDER BY fee_month""",
            (sid,),
        )
        st.dataframe(fee, hide_index=True) if not fee.empty else st.caption("No fee records.")


# ------------------------------------------------------------------ courses
def render_courses():
    t_list, t_add, t_edit = st.tabs(["📋 All Courses", "➕ Add Course", "✏️ Edit / Delete"])

    with t_list:
        df = run_query(
            """SELECT c.code, c.title, c.credit_hours, c.teacher, COUNT(e.id) AS enrolled
               FROM courses c LEFT JOIN enrollments e ON e.course_id = c.id GROUP BY c.id ORDER BY c.code"""
        )
        st.dataframe(df, hide_index=True) if not df.empty else st.info("No courses yet.")
        _csv_button("⬇️ Download CSV", df, "courses.csv", "dl_courses")

    with t_add:
        with st.form("add_course_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            code = c1.text_input("Course Code * (e.g. CS-101)")
            title = c2.text_input("Course Title *")
            hours = c1.number_input("Credit Hours", min_value=1, max_value=10, value=3)
            teacher = c2.text_input("Teacher")
            submitted = st.form_submit_button("Save Course")
        if submitted:
            if not code.strip() or not title.strip():
                st.error("Course code and title are required.")
            else:
                _, err = run_exec(
                    "INSERT INTO courses (code, title, credit_hours, teacher) VALUES (?,?,?,?)",
                    (code.strip(), title.strip(), int(hours), teacher.strip()),
                    dup_msg=f"Course code '{code.strip()}' already exists.",
                )
                if err:
                    st.error(err)
                else:
                    flash("Course added.")
                    st.rerun()

    with t_edit:
        cmap = course_map()
        if not cmap:
            st.info("No courses yet.")
            return
        cid = st.selectbox("Select course", list(cmap), format_func=cmap.get, key="crs_edit_sel")
        row = run_query("SELECT * FROM courses WHERE id = ?", (cid,)).iloc[0]
        with st.form(f"edit_course_form_{cid}"):
            c1, c2 = st.columns(2)
            code = c1.text_input("Course Code *", value=_txt(row["code"]))
            title = c2.text_input("Course Title *", value=_txt(row["title"]))
            hours = c1.number_input("Credit Hours", min_value=1, max_value=10, value=int(row["credit_hours"] or 3))
            teacher = c2.text_input("Teacher", value=_txt(row["teacher"]))
            saved = st.form_submit_button("Update Course")
        if saved:
            if not code.strip() or not title.strip():
                st.error("Course code and title are required.")
            else:
                _, err = run_exec(
                    "UPDATE courses SET code=?, title=?, credit_hours=?, teacher=? WHERE id=?",
                    (code.strip(), title.strip(), int(hours), teacher.strip(), cid),
                    dup_msg=f"Course code '{code.strip()}' already exists.",
                )
                if err:
                    st.error(err)
                else:
                    flash("Course updated.")
                    st.rerun()
        st.markdown("---")
        st.caption("Deleting a course also removes its enrollments, attendance and results.")
        ok = st.checkbox(f"Yes, permanently delete {cmap[cid]}", key=f"crs_del_ok_{cid}")
        if st.button("🗑️ Delete Course", disabled=not ok, key="crs_del_btn"):
            _, err = run_exec("DELETE FROM courses WHERE id = ?", (cid,))
            if err:
                st.error(err)
            else:
                flash("Course deleted.")
                st.rerun()


# --------------------------------------------------------------- enrollment
def render_enrollment():
    cmap = course_map()
    if not cmap:
        st.info("Add at least one course first (Courses tab).")
        return
    if not student_map(active_only=True):
        st.info("Add at least one active student first (Students tab).")
        return

    cid = st.selectbox("Course", list(cmap), format_func=cmap.get, key="enr_course")
    n = _nonce()

    st.markdown("#### Enroll students")
    avail = run_query(
        """SELECT id, roll_no, name FROM students
           WHERE status = 'Active' AND id NOT IN (SELECT student_id FROM enrollments WHERE course_id = ?)
           ORDER BY roll_no""",
        (cid,),
    )
    amap = {int(r.id): f"{r.roll_no} — {r.name}" for r in avail.itertuples()}
    if not amap:
        st.caption("All active students are already enrolled in this course.")
    else:
        chosen = st.multiselect("Students to enroll", list(amap), format_func=amap.get, key=f"enr_pick_{cid}_{n}")
        if st.button("Enroll selected students", disabled=not chosen, key="enr_btn"):
            err = run_many("INSERT OR IGNORE INTO enrollments (student_id, course_id) VALUES (?, ?)", [(s, cid) for s in chosen])
            if err:
                st.error(err)
            else:
                _bump()
                flash(f"Enrolled {len(chosen)} student(s).")
                st.rerun()

    st.markdown("#### Currently enrolled")
    cur = run_query(
        """SELECT e.id AS enrollment_id, s.roll_no, s.name, s.status
           FROM enrollments e JOIN students s ON s.id = e.student_id WHERE e.course_id = ? ORDER BY s.roll_no""",
        (cid,),
    )
    if cur.empty:
        st.caption("Nobody is enrolled yet.")
        return
    st.dataframe(cur.drop(columns="enrollment_id"), hide_index=True)
    emap = {int(r.enrollment_id): f"{r.roll_no} — {r.name}" for r in cur.itertuples()}
    remove = st.multiselect("Remove students from this course", list(emap), format_func=emap.get, key=f"enr_rm_{cid}_{n}")
    if st.button("Remove selected", disabled=not remove, key="enr_rm_btn"):
        err = run_many("DELETE FROM enrollments WHERE id = ?", [(i,) for i in remove])
        if err:
            st.error(err)
        else:
            _bump()
            flash(f"Removed {len(remove)} student(s) from the course.")
            st.rerun()


# --------------------------------------------------------------- attendance
def render_attendance():
    cmap = course_map()
    if not cmap:
        st.info("Add courses and enroll students first.")
        return
    t_mark, t_report = st.tabs(["✅ Mark Attendance", "📈 Attendance Report"])

    with t_mark:
        c1, c2 = st.columns(2)
        cid = c1.selectbox("Course", list(cmap), format_func=cmap.get, key="att_course")
        day = c2.date_input("Date", value=date.today(), max_value=date.today(), key="att_date_pick")
        df = run_query(
            """SELECT s.id, s.roll_no, s.name, COALESCE(a.status, 'Present') AS status
               FROM enrollments e JOIN students s ON s.id = e.student_id
               LEFT JOIN attendance a ON a.student_id = s.id AND a.course_id = e.course_id AND a.att_date = ?
               WHERE e.course_id = ? AND s.status = 'Active' ORDER BY s.roll_no""",
            (day.isoformat(), cid),
        )
        if df.empty:
            st.info("No active students are enrolled in this course.")
        else:
            edited = st.data_editor(
                df, hide_index=True, key=f"att_editor_{cid}_{day.isoformat()}",
                disabled=["roll_no", "name"],
                column_config={
                    "id": None,
                    "status": st.column_config.SelectboxColumn("Status", options=ATT_STATUSES, required=True),
                },
            )
            if st.button("💾 Save Attendance", key="att_save"):
                rows = [(int(r.id), cid, day.isoformat(), r.status) for r in edited.itertuples()]
                err = run_many(
                    """INSERT INTO attendance (student_id, course_id, att_date, status) VALUES (?,?,?,?)
                       ON CONFLICT (student_id, course_id, att_date) DO UPDATE SET status = excluded.status""",
                    rows,
                )
                if err:
                    st.error(err)
                else:
                    st.success(f"Attendance saved for {len(rows)} student(s) on {day.isoformat()}.")

    with t_report:
        cid = st.selectbox("Course", list(cmap), format_func=cmap.get, key="att_rep_course")
        rep = run_query(
            """SELECT s.roll_no, s.name, COUNT(*) AS classes,
                      SUM(a.status = 'Present') AS present, SUM(a.status = 'Absent') AS absent,
                      SUM(a.status = 'Leave') AS on_leave,
                      ROUND(100.0 * SUM(a.status = 'Present') / COUNT(*), 1) AS attendance_pct
               FROM attendance a JOIN students s ON s.id = a.student_id
               WHERE a.course_id = ? GROUP BY s.id ORDER BY s.roll_no""",
            (cid,),
        )
        if rep.empty:
            st.info("No attendance recorded for this course yet.")
        else:
            rep["alert"] = rep["attendance_pct"].map(lambda p: "⚠️ Low" if p < LOW_ATTENDANCE else "")
            st.dataframe(rep, hide_index=True)
            _csv_button("⬇️ Download CSV", rep, "attendance_report.csv", "dl_att")


# ------------------------------------------------------------------ results
def render_results():
    cmap = course_map()
    if not cmap:
        st.info("Add courses and enroll students first.")
        return
    t_enter, t_view = st.tabs(["✍️ Enter Marks", "🏆 View Results"])

    with t_enter:
        c1, c2, c3 = st.columns(3)
        cid = c1.selectbox("Course", list(cmap), format_func=cmap.get, key="res_course")
        exam = c2.selectbox("Exam Type", EXAM_TYPES, key="res_exam")
        total = c3.number_input("Total Marks", min_value=1.0, value=100.0, step=1.0, key="res_total")
        df = run_query(
            """SELECT s.id, s.roll_no, s.name, r.obtained_marks AS obtained
               FROM enrollments e JOIN students s ON s.id = e.student_id
               LEFT JOIN results r ON r.student_id = s.id AND r.course_id = e.course_id AND r.exam_type = ?
               WHERE e.course_id = ? AND s.status = 'Active' ORDER BY s.roll_no""",
            (exam, cid),
        )
        if df.empty:
            st.info("No active students are enrolled in this course.")
        else:
            df["obtained"] = df["obtained"].astype(float)
            edited = st.data_editor(
                df, hide_index=True, key=f"res_editor_{cid}_{exam}",
                disabled=["roll_no", "name"],
                column_config={
                    "id": None,
                    "obtained": st.column_config.NumberColumn("Obtained Marks", min_value=0.0, max_value=float(total), step=0.5),
                },
            )
            if st.button("💾 Save Marks", key="res_save"):
                filled = edited[edited["obtained"].notna()]
                if (filled["obtained"] > total).any() or (filled["obtained"] < 0).any():
                    st.error(f"Obtained marks must be between 0 and {total:g}.")
                elif filled.empty:
                    st.warning("Enter marks for at least one student.")
                else:
                    rows = [(int(r.id), cid, exam, float(total), float(r.obtained)) for r in filled.itertuples()]
                    err = run_many(
                        """INSERT INTO results (student_id, course_id, exam_type, total_marks, obtained_marks)
                           VALUES (?,?,?,?,?)
                           ON CONFLICT (student_id, course_id, exam_type)
                           DO UPDATE SET total_marks = excluded.total_marks, obtained_marks = excluded.obtained_marks""",
                        rows,
                    )
                    if err:
                        st.error(err)
                    else:
                        st.success(f"Saved marks for {len(rows)} student(s).")

    with t_view:
        c1, c2 = st.columns(2)
        course_f = c1.selectbox("Course", [0] + list(cmap), format_func=lambda i: "All courses" if i == 0 else cmap[i], key="res_view_course")
        exam_f = c2.selectbox("Exam Type", ["All"] + EXAM_TYPES, key="res_view_exam")
        sql = """SELECT s.roll_no, s.name, c.code AS course, r.exam_type,
                        r.obtained_marks AS obtained, r.total_marks AS total
                 FROM results r JOIN students s ON s.id = r.student_id JOIN courses c ON c.id = r.course_id WHERE 1=1"""
        params = []
        if course_f:
            sql += " AND r.course_id = ?"
            params.append(course_f)
        if exam_f != "All":
            sql += " AND r.exam_type = ?"
            params.append(exam_f)
        res = run_query(sql + " ORDER BY c.code, r.exam_type, s.roll_no", params)
        if res.empty:
            st.info("No results found.")
        else:
            res["percentage"] = (res["obtained"] / res["total"] * 100).round(1)
            res["grade"] = res["percentage"].map(grade_for)
            m = st.columns(3)
            m[0].metric("Records", len(res))
            m[1].metric("Average %", f"{res['percentage'].mean():.1f}%")
            m[2].metric("Pass rate (≥40%)", f"{(res['percentage'] >= 40).mean() * 100:.0f}%")
            st.dataframe(res, hide_index=True)
            _csv_button("⬇️ Download CSV", res, "results.csv", "dl_results")
        st.caption("Grading: A+ ≥80 · A ≥70 · B ≥60 · C ≥50 · D ≥40 · F below 40")


# --------------------------------------------------------------------- fees
def render_fees():
    t_gen, t_collect, t_report = st.tabs(["🧾 Generate Fees", "💵 Collect Payment", "📑 Fee Report"])

    with t_gen:
        st.write("Create a fee record for **every active student** for one month (existing records are skipped).")
        c1, c2, c3 = st.columns(3)
        month = c1.selectbox("Month", list(range(1, 13)), index=date.today().month - 1,
                             format_func=lambda m: calendar.month_name[m], key="fee_month")
        year = c2.number_input("Year", min_value=2000, max_value=2100, value=date.today().year, key="fee_year")
        amount = c3.number_input("Fee Amount", min_value=1.0, value=5000.0, step=100.0, key="fee_amount")
        if st.button("Generate Fee Records", key="fee_gen_btn"):
            fee_month = f"{int(year)}-{month:02d}"
            created, err = run_exec(
                "INSERT OR IGNORE INTO fees (student_id, fee_month, amount) SELECT id, ?, ? FROM students WHERE status = 'Active'",
                (fee_month, float(amount)),
            )
            if err:
                st.error(err)
            else:
                st.success(f"Created {created} fee record(s) for {fee_month}.")

    with t_collect:
        smap = student_map()
        if not smap:
            st.info("No students yet.")
        else:
            sid = st.selectbox("Student", list(smap), format_func=smap.get, key="fee_stu")
            due = run_query(
                "SELECT id, fee_month, amount, paid, amount - paid AS balance FROM fees WHERE student_id = ? AND paid < amount ORDER BY fee_month",
                (sid,),
            )
            if due.empty:
                st.success("No pending fees for this student. 🎉")
            else:
                fmap = {int(r.id): f"{r.fee_month} — balance {r.balance:,.0f}" for r in due.itertuples()}
                fid = st.selectbox("Fee month", list(fmap), format_func=fmap.get, key=f"fee_pick_{sid}")
                balance = float(due.loc[due["id"] == fid, "balance"].iloc[0])
                pay = st.number_input("Amount received", min_value=min(0.01, balance), max_value=balance,
                                      value=balance, step=100.0, key=f"fee_pay_{fid}")
                paid_on = st.date_input("Payment date", value=date.today(), key=f"fee_paid_on_{fid}")
                if st.button("Record Payment", key="fee_pay_btn"):
                    _, err = run_exec(
                        "UPDATE fees SET paid = MIN(amount, paid + ?), paid_date = ? WHERE id = ?",
                        (float(pay), paid_on.isoformat(), fid),
                    )
                    if err:
                        st.error(err)
                    else:
                        flash(f"Payment of {pay:,.0f} recorded.")
                        st.rerun()

    with t_report:
        months = run_query("SELECT DISTINCT fee_month FROM fees ORDER BY fee_month DESC")["fee_month"].tolist()
        if not months:
            st.info("No fee records yet. Generate them in the first tab.")
            return
        c1, c2 = st.columns(2)
        month_f = c1.selectbox("Month", ["All"] + months, key="fee_rep_month")
        status_f = c2.selectbox("Status", ["All", "Paid", "Partial", "Unpaid"], key="fee_rep_status")
        sql = """SELECT s.roll_no, s.name, f.fee_month AS month, f.amount, f.paid, f.amount - f.paid AS balance,
                        CASE WHEN f.paid >= f.amount THEN 'Paid' WHEN f.paid > 0 THEN 'Partial' ELSE 'Unpaid' END AS status,
                        f.paid_date
                 FROM fees f JOIN students s ON s.id = f.student_id WHERE 1=1"""
        params = []
        if month_f != "All":
            sql += " AND f.fee_month = ?"
            params.append(month_f)
        df = run_query(sql + " ORDER BY f.fee_month DESC, s.roll_no", params)
        if status_f != "All":
            df = df[df["status"] == status_f]
        m = st.columns(3)
        m[0].metric("Total Billed", f"{df['amount'].sum():,.0f}")
        m[1].metric("Collected", f"{df['paid'].sum():,.0f}")
        m[2].metric("Pending", f"{df['balance'].sum():,.0f}")
        st.dataframe(df, hide_index=True)
        _csv_button("⬇️ Download CSV", df, "fee_report.csv", "dl_fees")
