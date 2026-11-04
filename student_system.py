"""Student Management System - interface and data layer."""
import html
import io
import re
import sqlite3
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

from database import db_session, export_backup, inspect_backup, restore_backup

PRIMARY, GREEN, AMBER, SLATE = "#2563EB", "#16A34A", "#F59E0B", "#64748B"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?\d{7,15}$")
SORT_OPTIONS = {
    "Roll No": "roll_no COLLATE NOCASE ASC",
    "Name (A-Z)": "name COLLATE NOCASE ASC",
    "GPA (high to low)": "gpa IS NULL, gpa DESC",
    "GPA (low to high)": "gpa IS NULL, gpa ASC",
}
INSERT_SQL = (
    "INSERT INTO students (roll_no, name, father_name, email, phone, address, fee_submitted, gpa, photo) "
    "VALUES (?,?,?,?,?,?,?,?,?)"
)
GPA_COLUMN = st.column_config.ProgressColumn("GPA", min_value=0.0, max_value=4.0, format="%.2f")

CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1180px;}
section[data-testid="stSidebar"] {border-right: 1px solid #E2E8F0;}

.hero {background: linear-gradient(120deg, #0F172A 0%, #1E3A8A 55%, #2563EB 100%);
       padding: 28px 34px; border-radius: 16px; margin-bottom: 22px;}
.hero-title {color: #FFFFFF; font-size: 1.85rem; font-weight: 700; letter-spacing: -0.4px; line-height: 1.2;}
.hero-sub {color: #CBD5E1; font-size: 0.95rem; margin-top: 6px;}
.hero-chip {display: inline-block; background: rgba(255,255,255,0.14); color: #FFFFFF; padding: 3px 12px;
            border-radius: 999px; font-size: 0.8rem; font-weight: 600; margin-left: 8px;}

[data-testid="stMetric"] {background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 14px;
                          padding: 16px 20px; box-shadow: 0 1px 2px rgba(15,23,42,0.04);}
[data-testid="stMetricLabel"] p {color: #64748B; font-weight: 600; font-size: 0.78rem;
                                 text-transform: uppercase; letter-spacing: 0.05em;}
[data-testid="stMetricValue"] {color: #0F172A; font-weight: 700;}

.stTabs [data-baseweb="tab-list"] {gap: 4px; border-bottom: 1px solid #E2E8F0;}
.stTabs [data-baseweb="tab"] {padding: 10px 18px; font-weight: 600; color: #475569;}
.stTabs [aria-selected="true"] {color: #2563EB;}

.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: 10px; font-weight: 600; padding: 0.45rem 1.1rem;}
div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, div[data-baseweb="textarea"] > div {
    background: #FFFFFF; border-color: #CBD5E1;}

.section-title {font-size: 1.05rem; font-weight: 700; color: #0F172A; margin: 6px 0 2px 0;}
.muted {color: #64748B; font-size: 0.9rem; margin-bottom: 10px;}
.brand {font-size: 1.15rem; font-weight: 700; color: #0F172A; margin-bottom: 2px;}
.brand-sub {color: #64748B; font-size: 0.82rem; margin-bottom: 14px;}
.empty {border: 1px dashed #CBD5E1; border-radius: 12px; padding: 30px; text-align: center;
        color: #64748B; background: #FFFFFF;}
.pill {display: inline-block; padding: 3px 12px; border-radius: 999px; font-size: 0.78rem; font-weight: 600;}
.pill-green {background: #DCFCE7; color: #166534;}
.pill-amber {background: #FEF3C7; color: #92400E;}
.pill-blue {background: #DBEAFE; color: #1E40AF;}
.profile-card {background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 14px; padding: 22px 26px;}
.profile-name {font-size: 1.4rem; font-weight: 700; color: #0F172A;}
.profile-grid {display: grid; grid-template-columns: 140px 1fr; row-gap: 8px; margin-top: 14px; font-size: 0.95rem;}
.profile-label {color: #64748B; font-weight: 600;}
.profile-value {color: #0F172A;}
.avatar {width: 130px; height: 130px; border-radius: 16px; display: flex; align-items: center; justify-content: center;
         background: linear-gradient(135deg, #2563EB, #1E3A8A); color: #FFFFFF; font-size: 2.4rem; font-weight: 700;}
.app-footer {text-align: center; color: #94A3B8; font-size: 0.8rem; margin-top: 36px;}
</style>
"""


# ------------------------------------------------------------------ helpers
def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def _db():
    return st.session_state.selected_db


def run_query(sql, params=()):
    with db_session(_db()) as conn:
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame([tuple(r) for r in rows], columns=cols)


def run_exec(sql, params=()):
    """Returns (rowcount, error_message)."""
    try:
        with db_session(_db()) as conn:
            return conn.execute(sql, params).rowcount, None
    except sqlite3.Error as e:
        return 0, str(e)


def notify(message, icon="✅"):
    """Queue a small toast that survives st.rerun()."""
    st.session_state.setdefault("_toasts", []).append((message, icon))


def show_notifications():
    for message, icon in st.session_state.pop("_toasts", []):
        st.toast(message, icon=icon)


def _nonce():
    return st.session_state.setdefault("_nonce", 0)


def _bump():
    st.session_state["_nonce"] = _nonce() + 1


def _txt(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    return str(v)


def empty_state(message):
    st.markdown(f'<div class="empty">{html.escape(message)}</div>', unsafe_allow_html=True)


def section(title, subtitle=""):
    st.markdown(f'<div class="section-title">{html.escape(title)}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="muted">{html.escape(subtitle)}</div>', unsafe_allow_html=True)


def card():
    try:
        return st.container(border=True)
    except TypeError:  # older Streamlit
        return st.container()


def show_chart(chart):
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def pill(text, kind):
    return f'<span class="pill pill-{kind}">{html.escape(text)}</span>'


def process_photo(uploaded):
    """Resize an uploaded image to a compact JPEG. Returns bytes or None."""
    if uploaded is None:
        return None
    try:
        img = Image.open(uploaded).convert("RGB")
        img.thumbnail((400, 400))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return None


def validate(roll_no, name, father_name, email, phone, address, fee_submitted, gpa_text):
    """Returns (values_dict, errors_list)."""
    errors = []
    roll_no, name = roll_no.strip(), name.strip()
    if not roll_no:
        errors.append("Roll No is required.")
    if not name:
        errors.append("Name is required.")
    email = email.strip()
    if email and not EMAIL_RE.match(email):
        errors.append("Email address is not valid.")
    phone = re.sub(r"[\s\-()]", "", phone or "")
    if phone and not PHONE_RE.match(phone):
        errors.append("Phone number should contain 7 to 15 digits (optionally starting with +).")
    gpa = None
    gpa_text = (gpa_text or "").strip()
    if gpa_text:
        try:
            gpa = round(float(gpa_text), 2)
            if not 0 <= gpa <= 4:
                errors.append("GPA must be between 0.00 and 4.00.")
        except ValueError:
            errors.append("GPA must be a number, for example 3.45.")
    values = {
        "roll_no": roll_no, "name": name, "father_name": father_name.strip(), "email": email,
        "phone": phone, "address": address.strip(), "fee_submitted": int(bool(fee_submitted)), "gpa": gpa,
    }
    return values, errors


def student_map():
    df = run_query("SELECT id, roll_no, name FROM students WHERE deleted_at IS NULL ORDER BY roll_no COLLATE NOCASE")
    return {int(r.id): f"{r.roll_no}  ·  {r.name}" for r in df.itertuples()}


def load_students(search="", fee="All", sort="Roll No"):
    sql = ("SELECT id, roll_no, name, father_name, email, phone, address, fee_submitted, gpa "
           "FROM students WHERE deleted_at IS NULL")
    params = []
    if search:
        sql += " AND (name LIKE ? OR roll_no LIKE ? OR phone LIKE ? OR email LIKE ?)"
        params += [f"%{search}%"] * 4
    if fee == "Submitted":
        sql += " AND fee_submitted = 1"
    elif fee == "Pending":
        sql += " AND fee_submitted = 0"
    return run_query(sql + " ORDER BY " + SORT_OPTIONS[sort], params)


def directory_frame(df):
    out = df.copy()
    out["Fee"] = out["fee_submitted"].map({1: "Submitted", 0: "Pending"})
    out = out[["roll_no", "name", "father_name", "email", "phone", "address", "Fee", "gpa"]]
    out.columns = ["Roll No", "Name", "Father Name", "Email", "Phone", "Address", "Fee", "GPA"]
    return out


def import_students(df):
    """Insert students from a DataFrame. Returns (added_count, skipped_rows)."""
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    added, skipped = 0, []
    with db_session(_db()) as conn:
        for line, rec in enumerate(df.to_dict("records"), start=2):
            g = lambda k: _txt(rec.get(k)).strip()
            fee = g("fee_submitted").lower() in ("yes", "y", "true", "1", "paid", "submitted")
            v, errors = validate(g("roll_no"), g("name"), g("father_name"), g("email"), g("phone"),
                                 g("address"), fee, g("gpa"))
            if errors:
                skipped.append({"Row": line, "Roll No": g("roll_no"), "Reason": errors[0]})
                continue
            try:
                conn.execute(INSERT_SQL, (v["roll_no"], v["name"], v["father_name"], v["email"], v["phone"],
                                          v["address"], v["fee_submitted"], v["gpa"], None))
                added += 1
            except sqlite3.IntegrityError:
                skipped.append({"Row": line, "Roll No": g("roll_no"), "Reason": "Roll No already exists"})
    return added, skipped


def build_profile_pdf(s, photo_bytes):
    """Printable one-page profile. Returns PDF bytes (requires fpdf2)."""
    from fpdf import FPDF

    def latin(x):
        return str(x).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(15, 23, 42)
    pdf.rect(0, 0, 210, 40, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_xy(15, 12)
    pdf.cell(0, 10, "Student Profile")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(15, 24)
    pdf.cell(0, 6, latin(f"Department: {_db()}"))

    if photo_bytes:
        try:
            pdf.image(io.BytesIO(photo_bytes), x=155, y=52, w=40)
        except Exception:
            pass

    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_xy(15, 52)
    pdf.cell(130, 10, latin(s["name"]))
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 116, 139)
    pdf.set_xy(15, 63)
    pdf.cell(130, 6, latin(f"Roll No: {s['roll_no']}"))

    gpa = "-" if pd.isna(s["gpa"]) else f"{s['gpa']:.2f}"
    rows = [
        ("Father Name", _txt(s["father_name"]) or "-"),
        ("Email", _txt(s["email"]) or "-"),
        ("Phone", _txt(s["phone"]) or "-"),
        ("Address", _txt(s["address"]) or "-"),
        ("Fee Submitted", "Yes" if int(s["fee_submitted"]) == 1 else "No"),
        ("GPA", gpa),
    ]
    y = 100
    for label, value in rows:
        pdf.set_xy(15, y)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(45, 9, label)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(15, 23, 42)
        pdf.multi_cell(130, 9, latin(value))
        pdf.set_draw_color(226, 232, 240)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        y = pdf.get_y() + 2

    pdf.set_xy(15, 280)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 5, f"Generated on {datetime.now():%d %b %Y, %H:%M}")
    return bytes(pdf.output())


# ---------------------------------------------------------------- dashboard
def render_dashboard():
    df = run_query("SELECT roll_no, name, phone, fee_submitted, gpa FROM students WHERE deleted_at IS NULL")
    if df.empty:
        empty_state("No students yet. Add your first student from the Students tab.")
        return

    total = len(df)
    paid = int(df["fee_submitted"].sum())
    pending = total - paid
    gpa_values = df["gpa"].dropna()

    c = st.columns(4)
    c[0].metric("Total Students", total)
    c[1].metric("Average GPA", f"{gpa_values.mean():.2f}" if len(gpa_values) else "—")
    c[2].metric("Fee Submitted", paid)
    c[3].metric("Fee Pending", pending)
    st.write("")

    left, right = st.columns(2)
    with left:
        with card():
            section("Fee status", "Share of students who have submitted their fee")
            fee_df = pd.DataFrame({"Status": ["Submitted", "Pending"], "Students": [paid, pending]})
            donut = alt.Chart(fee_df).mark_arc(innerRadius=62, outerRadius=105).encode(
                theta="Students:Q",
                color=alt.Color("Status:N", scale=alt.Scale(domain=["Submitted", "Pending"], range=[GREEN, AMBER]),
                                legend=alt.Legend(orient="bottom", title=None)),
                tooltip=["Status", "Students"],
            ).properties(height=270)
            show_chart(donut)
    with right:
        with card():
            section("GPA distribution", "Number of students in each GPA range")
            if gpa_values.empty:
                empty_state("No GPA recorded yet.")
            else:
                labels = ["Below 2.0", "2.0 - 2.49", "2.5 - 2.99", "3.0 - 3.49", "3.5 - 4.0"]
                bins = pd.cut(gpa_values, bins=[-0.01, 1.99, 2.49, 2.99, 3.49, 4.0], labels=labels)
                dist = bins.value_counts().reindex(labels, fill_value=0).reset_index()
                dist.columns = ["Range", "Students"]
                bars = alt.Chart(dist).mark_bar(color=PRIMARY, cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
                    x=alt.X("Range:N", sort=labels, title=None, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("Students:Q", title=None, axis=alt.Axis(tickMinStep=1)),
                    tooltip=["Range", "Students"],
                ).properties(height=270)
                show_chart(bars)

    left, right = st.columns(2)
    with left:
        with card():
            section("Top students", "Highest GPA")
            top = df.dropna(subset=["gpa"]).sort_values("gpa", ascending=False).head(5)
            if top.empty:
                empty_state("No GPA recorded yet.")
            else:
                view = top[["roll_no", "name", "gpa"]]
                view.columns = ["Roll No", "Name", "GPA"]
                st.dataframe(view, hide_index=True, column_config={"GPA": GPA_COLUMN})
    with right:
        with card():
            section("Fee pending", f"{pending} student(s) have not submitted the fee")
            due = df[df["fee_submitted"] == 0][["roll_no", "name", "phone"]].head(8)
            if due.empty:
                empty_state("All students have submitted their fee.")
            else:
                due.columns = ["Roll No", "Name", "Phone"]
                st.dataframe(due, hide_index=True)


# ----------------------------------------------------------------- students
def render_students():
    t_dir, t_add, t_edit, t_prof, t_imp, t_bin = st.tabs(
        ["Directory", "Add Student", "Edit Student", "Profile", "Import CSV", "Recycle Bin"]
    )

    # ---- Directory
    with t_dir:
        c1, c2, c3 = st.columns([2.2, 1, 1.2])
        search = c1.text_input("Search", placeholder="Name, roll no, phone or email", key="dir_search")
        fee_f = c2.selectbox("Fee", ["All", "Submitted", "Pending"], key="dir_fee")
        sort_f = c3.selectbox("Sort by", list(SORT_OPTIONS), key="dir_sort")
        df = load_students(search, fee_f, sort_f)
        st.caption(f"{len(df)} student(s)")
        if df.empty:
            empty_state("No students match your filters.")
        else:
            shown = directory_frame(df)
            st.dataframe(shown, hide_index=True, column_config={"GPA": GPA_COLUMN})
            st.download_button("Download CSV", shown.to_csv(index=False).encode("utf-8"),
                               "students.csv", "text/csv", key="dl_students")

        with st.expander("Bulk fee update"):
            smap = student_map()
            pick = st.multiselect("Select students", list(smap), format_func=smap.get, key=f"bulk_pick_{_nonce()}")
            b1, b2, _ = st.columns([1, 1, 2])
            for col, label, flag in ((b1, "Mark as Submitted", 1), (b2, "Mark as Pending", 0)):
                if col.button(label, disabled=not pick, key=f"bulk_{flag}"):
                    with db_session(_db()) as conn:
                        conn.executemany("UPDATE students SET fee_submitted = ? WHERE id = ?",
                                         [(flag, i) for i in pick])
                    notify(f"Fee status updated for {len(pick)} student(s).")
                    _bump()
                    st.rerun()

    # ---- Add
    with t_add:
        section("New student", "Roll No and Name are required.")
        with st.form("add_student", clear_on_submit=True):
            c1, c2 = st.columns(2)
            roll = c1.text_input("Roll No *", key="add_roll")
            name = c2.text_input("Name *", key="add_name")
            father = c1.text_input("Father Name", key="add_father")
            email = c2.text_input("Email", key="add_email")
            phone = c1.text_input("Phone Number", key="add_phone")
            gpa = c2.text_input("GPA (0.00 - 4.00)", placeholder="e.g. 3.45", key="add_gpa")
            address = st.text_area("Address", height=80, key="add_address")
            c3, c4 = st.columns(2)
            fee = c3.radio("Fee Submitted", ["No", "Yes"], horizontal=True, key="add_fee")
            photo = c4.file_uploader("Photo (optional)", type=["png", "jpg", "jpeg"], key="add_photo")
            submitted = st.form_submit_button("Save Student", type="primary")
        if submitted:
            v, errors = validate(roll, name, father, email, phone, address, fee == "Yes", gpa)
            if errors:
                st.error("\n".join(f"- {e}" for e in errors))
            else:
                _, err = run_exec(INSERT_SQL, (v["roll_no"], v["name"], v["father_name"], v["email"], v["phone"],
                                               v["address"], v["fee_submitted"], v["gpa"], process_photo(photo)))
                if err and "UNIQUE" in err:
                    st.error(f"Roll No '{v['roll_no']}' already exists (it may be in the Recycle Bin).")
                elif err:
                    st.error(err)
                else:
                    notify(f"{v['name']} added.")
                    st.rerun()

    # ---- Edit
    with t_edit:
        smap = student_map()
        if not smap:
            empty_state("No students to edit yet.")
        else:
            sid = st.selectbox("Student", list(smap), format_func=smap.get, key="edit_sel")
            s = run_query("SELECT id, roll_no, name, father_name, email, phone, address, fee_submitted, gpa "
                          "FROM students WHERE id = ?", (sid,)).iloc[0]
            current_photo = run_query("SELECT photo FROM students WHERE id = ?", (sid,)).iloc[0, 0]
            if current_photo:
                st.image(current_photo, width=110)
            with st.form(f"edit_student_{sid}"):
                c1, c2 = st.columns(2)
                roll = c1.text_input("Roll No *", value=_txt(s["roll_no"]), key=f"e_roll_{sid}")
                name = c2.text_input("Name *", value=_txt(s["name"]), key=f"e_name_{sid}")
                father = c1.text_input("Father Name", value=_txt(s["father_name"]), key=f"e_father_{sid}")
                email = c2.text_input("Email", value=_txt(s["email"]), key=f"e_email_{sid}")
                phone = c1.text_input("Phone Number", value=_txt(s["phone"]), key=f"e_phone_{sid}")
                gpa_val = "" if pd.isna(s["gpa"]) else f"{s['gpa']:.2f}"
                gpa = c2.text_input("GPA (0.00 - 4.00)", value=gpa_val, key=f"e_gpa_{sid}")
                address = st.text_area("Address", value=_txt(s["address"]), height=80, key=f"e_addr_{sid}")
                c3, c4 = st.columns(2)
                fee = c3.radio("Fee Submitted", ["No", "Yes"], index=int(s["fee_submitted"] == 1),
                               horizontal=True, key=f"e_fee_{sid}")
                photo = c4.file_uploader("Replace photo", type=["png", "jpg", "jpeg"], key=f"e_photo_{sid}")
                remove_photo = c4.checkbox("Remove current photo", key=f"e_rmphoto_{sid}") if current_photo else False
                saved = st.form_submit_button("Update Student", type="primary")
            if saved:
                v, errors = validate(roll, name, father, email, phone, address, fee == "Yes", gpa)
                if errors:
                    st.error("\n".join(f"- {e}" for e in errors))
                else:
                    sql = ("UPDATE students SET roll_no=?, name=?, father_name=?, email=?, phone=?, address=?, "
                           "fee_submitted=?, gpa=?")
                    params = [v["roll_no"], v["name"], v["father_name"], v["email"], v["phone"], v["address"],
                              v["fee_submitted"], v["gpa"]]
                    new_photo = process_photo(photo)
                    if new_photo:
                        sql += ", photo=?"
                        params.append(new_photo)
                    elif remove_photo:
                        sql += ", photo=NULL"
                    _, err = run_exec(sql + " WHERE id=?", params + [sid])
                    if err and "UNIQUE" in err:
                        st.error(f"Roll No '{v['roll_no']}' belongs to another student.")
                    elif err:
                        st.error(err)
                    else:
                        notify("Student updated.")
                        st.rerun()

            if st.button("Move to Recycle Bin", key="to_bin"):
                run_exec("UPDATE students SET deleted_at = ? WHERE id = ?",
                         (datetime.now().strftime("%Y-%m-%d %H:%M"), sid))
                notify("Moved to Recycle Bin. You can restore it anytime.", "🗑️")
                st.rerun()

    # ---- Profile
    with t_prof:
        smap = student_map()
        if not smap:
            empty_state("No students yet.")
        else:
            sid = st.selectbox("Student", list(smap), format_func=smap.get, key="prof_sel")
            s = run_query("SELECT * FROM students WHERE id = ?", (sid,)).iloc[0]
            photo_bytes = s["photo"] if isinstance(s["photo"], (bytes, bytearray)) else None
            left, right = st.columns([1, 3])
            with left:
                if photo_bytes:
                    st.image(bytes(photo_bytes), width=130)
                else:
                    initials = "".join(p[0] for p in str(s["name"]).split()[:2]).upper()
                    st.markdown(f'<div class="avatar">{html.escape(initials)}</div>', unsafe_allow_html=True)
            with right:
                fee_pill = pill("Fee submitted", "green") if int(s["fee_submitted"]) == 1 else pill("Fee pending", "amber")
                gpa_pill = pill("GPA not set", "blue") if pd.isna(s["gpa"]) else pill(f"GPA {s['gpa']:.2f}", "blue")
                rows = [("Roll No", s["roll_no"]), ("Father Name", s["father_name"]), ("Email", s["email"]),
                        ("Phone", s["phone"]), ("Address", s["address"])]
                grid = "".join(
                    f'<div class="profile-label">{lbl}</div><div class="profile-value">{html.escape(_txt(val)) or "—"}</div>'
                    for lbl, val in rows
                )
                st.markdown(
                    f'<div class="profile-card"><div class="profile-name">{html.escape(str(s["name"]))}</div>'
                    f'<div style="margin-top:8px">{fee_pill} &nbsp; {gpa_pill}</div>'
                    f'<div class="profile-grid">{grid}</div></div>',
                    unsafe_allow_html=True,
                )
            st.write("")
            try:
                pdf = build_profile_pdf(s, bytes(photo_bytes) if photo_bytes else None)
                st.download_button("Download profile (PDF)", pdf, f"{s['roll_no']}_profile.pdf",
                                   "application/pdf", key=f"dl_pdf_{sid}")
            except ImportError:
                st.caption("Install the PDF package to enable this: pip install fpdf2")

    # ---- Import
    with t_imp:
        section("Import students from CSV", "Required columns: roll_no, name. Optional: father_name, email, phone, "
                "address, fee_submitted (Yes/No), gpa.")
        template = pd.DataFrame([{
            "roll_no": "AI-001", "name": "Ali Khan", "father_name": "Ahmed Khan", "email": "ali@example.com",
            "phone": "03001234567", "address": "Rawalpindi", "fee_submitted": "Yes", "gpa": "3.45",
        }])
        st.download_button("Download CSV template", template.to_csv(index=False).encode("utf-8"),
                           "students_template.csv", "text/csv", key="dl_template")
        up = st.file_uploader("Choose a CSV file", type=["csv"], key=f"imp_file_{_nonce()}")
        if up:
            try:
                up.seek(0)
                data = pd.read_csv(up, dtype=str)
            except Exception as e:
                data = None
                st.error(f"Could not read this file: {e}")
            if data is not None:
                st.dataframe(data.head(5), hide_index=True)
                cols = {str(c).strip().lower().replace(" ", "_") for c in data.columns}
                if not {"roll_no", "name"} <= cols:
                    st.error("The file must contain 'roll_no' and 'name' columns.")
                elif st.button("Import students", type="primary", key="imp_btn"):
                    added, skipped = import_students(data)
                    notify(f"Imported {added} student(s)." + (f" {len(skipped)} skipped." if skipped else ""))
                    if skipped:
                        st.session_state["_import_skipped"] = skipped
                    _bump()
                    st.rerun()
        skipped = st.session_state.pop("_import_skipped", None)
        if skipped:
            section("Skipped rows")
            st.dataframe(pd.DataFrame(skipped), hide_index=True)

    # ---- Recycle bin
    with t_bin:
        section("Recycle Bin", "Deleted students can be restored.")
        bin_df = run_query("SELECT id, roll_no, name, deleted_at FROM students WHERE deleted_at IS NOT NULL "
                           "ORDER BY deleted_at DESC")
        if bin_df.empty:
            empty_state("The Recycle Bin is empty.")
        else:
            bmap = {int(r.id): f"{r.roll_no}  ·  {r.name}" for r in bin_df.itertuples()}
            view = bin_df[["roll_no", "name", "deleted_at"]]
            view.columns = ["Roll No", "Name", "Deleted on"]
            st.dataframe(view, hide_index=True)
            pick = st.multiselect("Select students", list(bmap), format_func=bmap.get, key=f"bin_pick_{_nonce()}")
            c1, c2, c3 = st.columns([1, 1.4, 2])
            if c1.button("Restore", type="primary", disabled=not pick, key="bin_restore"):
                with db_session(_db()) as conn:
                    conn.executemany("UPDATE students SET deleted_at = NULL WHERE id = ?", [(i,) for i in pick])
                notify(f"Restored {len(pick)} student(s).")
                _bump()
                st.rerun()
            confirm = c3.checkbox("Confirm permanent deletion", key=f"bin_confirm_{_nonce()}")
            if c2.button("Delete permanently", disabled=not (pick and confirm), key="bin_delete"):
                with db_session(_db()) as conn:
                    conn.executemany("DELETE FROM students WHERE id = ?", [(i,) for i in pick])
                notify(f"Permanently deleted {len(pick)} student(s).", "🗑️")
                _bump()
                st.rerun()


# ------------------------------------------------------------------- backup
def render_backup():
    dept = _db()
    left, right = st.columns(2)

    with left:
        with card():
            section("Download backup", "Save a copy of this department's data to your computer.")
            data = export_backup(dept)
            count = int(run_query("SELECT COUNT(*) FROM students WHERE deleted_at IS NULL").iloc[0, 0])
            stamp = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button("Download backup", data, f"{dept}_backup_{stamp}.db", "application/octet-stream",
                               type="primary", key="dl_backup")
            st.caption(f"{count} student(s)  ·  {len(data) / 1024:.0f} KB")

    with right:
        with card():
            section("Restore from backup", "A safety copy of the current data is saved automatically first.")
            up = st.file_uploader("Backup file (.db)", type=["db"], key=f"restore_file_{_nonce()}")
            if up:
                payload = up.getvalue()
                count, err = inspect_backup(payload)
                if err:
                    st.error(err)
                else:
                    st.caption(f"This backup contains {count} student(s).")
                    if st.button("Restore this backup", type="primary", key="restore_btn"):
                        try:
                            restore_backup(dept, payload)
                        except Exception as e:
                            st.error(f"Restore failed: {e}")
                        else:
                            notify("Backup restored successfully.")
                            _bump()
                            st.rerun()
