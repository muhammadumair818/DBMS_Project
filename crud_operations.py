"""Table architect, CSV smart loader and CRUD workspace."""
import sqlite3

import pandas as pd
import streamlit as st

from database import SQLITE_TYPES, SYSTEM_TABLES, db_session, quote_ident, sanitize_name


# ---------------------------------------------------------------- helpers
def flash(message, kind="success"):
    """Store a message that survives st.rerun()."""
    st.session_state["_flash"] = (kind, message)


def show_flash():
    item = st.session_state.pop("_flash", None)
    if item:
        kind, message = item
        getattr(st, kind)(message)


def get_tables_list():
    db = st.session_state.get("selected_db")
    if not db:
        return []
    with db_session(db) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [r["name"] for r in rows if r["name"].lower() not in SYSTEM_TABLES]


def get_columns(table):
    with db_session(st.session_state.selected_db) as conn:
        rows = conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    return [{"name": r["name"], "type": (r["type"] or "TEXT").upper()} for r in rows]


def parse_value(text, col_type):
    """Convert form text to a DB value. Blank -> NULL. Returns (value, error)."""
    text = (text or "").strip()
    if text == "":
        return None, None
    try:
        if col_type == "INTEGER":
            return int(text), None
        if col_type == "REAL":
            return float(text), None
    except ValueError:
        return None, f"'{text}' is not a valid {col_type.lower()} value."
    return text, None


def clean_cell(value):
    """Turn pandas/numpy values into plain Python values sqlite3 can bind."""
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy.int64 / numpy.float64 / numpy.bool_
        return value.item()
    return value


# ---------------------------------------------------------- table manager
def render_table_manager():
    st.subheader("Manage Tables")
    col1, col2 = st.columns(2)
    tables = get_tables_list()
    existing = {t.lower() for t in tables}

    with col1:
        st.write("### Create New Table Structure")
        new_table_name = st.text_input("Table Name:", key="new_table_name")
        num_cols = st.number_input(
            "Number of schema parameters:", min_value=1, max_value=10, value=2, key="num_cols"
        )

        fields = []
        for i in range(int(num_cols)):
            c_name = st.text_input(f"Field {i + 1} Name:", key=f"cname_{i}")
            c_type = st.selectbox(f"Field {i + 1} Type:", SQLITE_TYPES, key=f"ctype_{i}")
            fields.append((c_name, c_type))

        if st.button("Generate Dynamic Table"):
            t_name = sanitize_name(new_table_name)
            errors, columns_def, seen = [], [], {"id"}

            if not t_name:
                errors.append("Enter a valid table name.")
            elif t_name.lower().startswith("sqlite_"):
                errors.append("Table names cannot start with 'sqlite_'.")
            elif t_name.lower() in existing:
                errors.append(f"Table '{t_name}' already exists.")

            for raw_name, c_type in fields:
                if not raw_name.strip():
                    continue  # unused field slot
                c_name = sanitize_name(raw_name)
                if not c_name:
                    errors.append(f"'{raw_name}' is not a valid field name.")
                elif c_name.lower() in seen:
                    errors.append(f"Field '{c_name}' is duplicated or reserved ('id' is automatic).")
                else:
                    seen.add(c_name.lower())
                    columns_def.append(f"{quote_ident(c_name)} {c_type}")

            if not columns_def and not errors:
                errors.append("Add at least one field.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                query = (
                    f"CREATE TABLE {quote_ident(t_name)} "
                    f"(id INTEGER PRIMARY KEY AUTOINCREMENT, {', '.join(columns_def)})"
                )
                try:
                    with db_session(st.session_state.selected_db) as conn:
                        conn.execute(query)
                except sqlite3.Error as e:
                    st.error(f"Execution Error: {e}")
                else:
                    flash(f"Table '{t_name}' created successfully!")
                    st.rerun()

    with col2:
        st.write("### Rename or Drop Table Elements")
        if not tables:
            st.info("No active tables found in this department.")
            return

        table = st.selectbox("Select Target Table:", tables, key="tbl_manage")
        new_tbl_name = st.text_input("Rename Table To:", key="rename_to")

        if st.button("Confirm Rename"):
            new_name = sanitize_name(new_tbl_name)
            if not new_name:
                st.error("Enter a valid new table name.")
            elif new_name.lower() in existing and new_name.lower() != table.lower():
                st.error(f"Table '{new_name}' already exists.")
            else:
                try:
                    with db_session(st.session_state.selected_db) as conn:
                        conn.execute(
                            f"ALTER TABLE {quote_ident(table)} RENAME TO {quote_ident(new_name)}"
                        )
                except sqlite3.Error as e:
                    st.error(f"Rename failed: {e}")
                else:
                    flash("Table renamed!")
                    st.rerun()

        st.markdown("---")
        confirm = st.checkbox(f"Yes, permanently drop '{table}'", key=f"confirm_drop_{table}")
        if st.button("🗑️ Drop Table Entity", disabled=not confirm):
            try:
                with db_session(st.session_state.selected_db) as conn:
                    conn.execute(f"DROP TABLE {quote_ident(table)}")
            except sqlite3.Error as e:
                st.error(f"Drop failed: {e}")
            else:
                flash(f"Table '{table}' deleted!")
                st.rerun()


# ------------------------------------------------------------ CSV loader
def render_csv_uploader():
    st.subheader("Direct CSV Bulk Data Sync")
    tables = get_tables_list()
    if not tables:
        st.info("Create a target table architecture layout first.")
        return

    target = st.selectbox("Destination Table Target:", tables, key="csv_target")
    uploaded = st.file_uploader("Upload CSV sheet:", type=["csv"])
    if not uploaded:
        return

    try:
        uploaded.seek(0)
        df = pd.read_csv(uploaded)
    except Exception as e:
        st.error(f"Could not read this CSV: {e}")
        return

    st.dataframe(df.head(5))

    db_cols = [c["name"] for c in get_columns(target) if c["name"] != "id"]
    # CSV headers are normalised the same way field names are when tables are created
    lookup = {sanitize_name(str(c)).lower(): c for c in df.columns}
    mapping = {col: lookup.get(col.lower()) for col in db_cols}
    unmatched = [col for col, src in mapping.items() if src is None]

    if len(unmatched) == len(db_cols):
        st.error("No CSV column matches this table's fields. Check the header names.")
        return
    if unmatched:
        st.warning(f"These table fields were not found in the CSV and will be NULL: {', '.join(unmatched)}")

    if st.button("Migrate Data Rows to Database"):
        col_sql = ", ".join(quote_ident(c) for c in db_cols)
        placeholders = ", ".join("?" * len(db_cols))
        sql = f"INSERT INTO {quote_ident(target)} ({col_sql}) VALUES ({placeholders})"

        inserted, failed, first_error = 0, 0, None
        with db_session(st.session_state.selected_db) as conn:
            for rec in df.astype(object).to_dict("records"):
                values = [
                    clean_cell(rec[mapping[c]]) if mapping[c] is not None else None
                    for c in db_cols
                ]
                try:
                    conn.execute(sql, values)
                    inserted += 1
                except sqlite3.Error as e:
                    failed += 1
                    first_error = first_error or str(e)

        st.success(f"Batch Synced: successfully added {inserted} entries.")
        if failed:
            st.warning(f"{failed} row(s) failed. First error: {first_error}")


# -------------------------------------------------------------------- CRUD
def render_crud_operations():
    st.subheader("Data Engine Workspace Matrix")
    tables = get_tables_list()
    if not tables:
        st.info("Create a table first.")
        return

    db = st.session_state.selected_db
    table = st.selectbox("Select Display Target Table:", tables, key="crud_table")
    cols_info = get_columns(table)
    col_types = {c["name"]: c["type"] for c in cols_info}
    editable = [c["name"] for c in cols_info if c["name"] != "id"]

    with db_session(db) as conn:
        rows = conn.execute(f"SELECT * FROM {quote_ident(table)}").fetchall()
    # dtype=object keeps integers as integers (pandas would turn them into 20.0 when NULLs exist)
    df = pd.DataFrame([tuple(r) for r in rows], columns=[c["name"] for c in cols_info], dtype=object)
    st.dataframe(df)

    if "id" not in col_types:
        st.warning("This table has no 'id' column, so it is view-only here.")
        return
    if not editable:
        st.info("This table only has an 'id' column.")
        return

    operation = st.radio(
        "Execute Row Manipulation Task:",
        ["Add Entry Record", "Modify Existing Entry", "Purge Data Record"],
        key="crud_op",
    )

    # ---- ADD
    if operation == "Add Entry Record":
        with st.form(f"add_form_{table}", clear_on_submit=True):
            raw = {
                col: st.text_input(f"Value for {col} ({col_types[col]}):", key=f"add_{table}_{col}")
                for col in editable
            }
            submitted = st.form_submit_button("Commit Insert Run")
        if submitted:
            values, errors = [], []
            for col in editable:
                val, err = parse_value(raw[col], col_types[col])
                values.append(val)
                if err:
                    errors.append(f"{col}: {err}")
            if errors:
                for e in errors:
                    st.error(e)
            elif all(v is None for v in values):
                st.warning("Enter at least one value.")
            else:
                col_sql = ", ".join(quote_ident(c) for c in editable)
                marks = ", ".join("?" * len(editable))
                with db_session(db) as conn:
                    conn.execute(
                        f"INSERT INTO {quote_ident(table)} ({col_sql}) VALUES ({marks})", values
                    )
                flash("Database entry synced successfully!")
                st.rerun()

    # ---- UPDATE
    elif operation == "Modify Existing Entry":
        if df.empty:
            st.info("No records to modify.")
            return
        # ID picker is OUTSIDE the form so the fields below reload for the chosen record
        rec_id = int(st.selectbox("Target Record (ID):", df["id"].tolist(), key=f"upd_id_{table}"))
        current = df[df["id"] == rec_id].iloc[0]
        with st.form(f"update_form_{table}_{rec_id}"):
            raw = {}
            for col in editable:
                cur = current[col]
                cur_text = "" if pd.isna(cur) else str(cur)
                raw[col] = st.text_input(
                    f"Update Field Value for ({col}, {col_types[col]}):",
                    value=cur_text,
                    key=f"upd_{table}_{rec_id}_{col}",
                )
            submitted = st.form_submit_button("Push Update Execution")
        st.caption("Fields are pre-filled with the current values. Clearing a field sets it to empty (NULL).")
        if submitted:
            values, errors = [], []
            for col in editable:
                val, err = parse_value(raw[col], col_types[col])
                values.append(val)
                if err:
                    errors.append(f"{col}: {err}")
            if errors:
                for e in errors:
                    st.error(e)
            else:
                set_clause = ", ".join(f"{quote_ident(c)} = ?" for c in editable)
                with db_session(db) as conn:
                    conn.execute(
                        f"UPDATE {quote_ident(table)} SET {set_clause} WHERE id = ?",
                        values + [rec_id],
                    )
                flash("Target record updated.")
                st.rerun()

    # ---- DELETE
    else:
        if df.empty:
            st.info("No records to delete.")
            return
        rec_id = int(st.selectbox("Select Target Entry ID to Delete:", df["id"].tolist(), key=f"del_id_{table}"))
        confirm = st.checkbox(f"Yes, delete record {rec_id}", key=f"confirm_del_{table}_{rec_id}")
        if st.button("Execute Record Delete", disabled=not confirm):
            with db_session(db) as conn:
                conn.execute(f"DELETE FROM {quote_ident(table)} WHERE id = ?", (rec_id,))
            flash("Record permanently removed.")
            st.rerun()
