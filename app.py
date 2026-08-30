import streamlit as st
import sqlite3
from datetime import datetime, date, timedelta
import pandas as pd

# Import our scheduling engine
from scheduler import (
    get_tasks,
    get_trains,
    get_resources,
    generate_schedule,
    update_train_delay,
    minutes_to_time,
    generate_full_plan,
    generate_what_if_plan,
    get_plan_summary
)


# ============================================================
# CONFIGURATION
# ============================================================

DB_PATH = "database/railway_planner.db"


st.set_page_config(
    page_title="Railway Automatic Block Planner",
    page_icon="🚂",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_connection():

    connection = sqlite3.connect(DB_PATH)

    connection.row_factory = sqlite3.Row

    return connection


def initialize_app_tables():

    connection = get_connection()

    cursor = connection.cursor()

    # Table used by our prototype to store defect reports.
    # This does NOT modify the existing railway tables.

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS defect_reports (

            report_id INTEGER PRIMARY KEY AUTOINCREMENT,

            reported_by TEXT NOT NULL,

            reporter_role TEXT NOT NULL,

            department_id INTEGER,

            department_name TEXT,

            subdivision_id INTEGER,

            subdivision_name TEXT,

            defect_type TEXT NOT NULL,

            location_start_km REAL,

            location_end_km REAL,

            severity TEXT NOT NULL,

            description TEXT,

            reported_at TEXT NOT NULL,

            status TEXT DEFAULT 'PENDING'
        )
    """)

    connection.commit()

    connection.close()


def get_departments():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            department_id,
            department_name
        FROM departments
        ORDER BY department_id
    """)

    departments = cursor.fetchall()

    connection.close()

    return departments


def get_subdivisions():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            subdivision_id,
            subdivision_name
        FROM sub_sub_divisions
        ORDER BY subdivision_id
    """)

    subdivisions = cursor.fetchall()

    connection.close()

    return subdivisions


def get_department_id_by_name(name):

    departments = get_departments()

    for department in departments:

        if name.lower() in department["department_name"].lower():

            return department["department_id"]

    return None


def get_department_name(department_id):

    departments = get_departments()

    for department in departments:

        if department["department_id"] == department_id:

            return department["department_name"]

    return "Unknown"


def get_subdivision_name(subdivision_id):

    subdivisions = get_subdivisions()

    for subdivision in subdivisions:

        if subdivision["subdivision_id"] == subdivision_id:

            return subdivision["subdivision_name"]

    return "Unknown"


# ============================================================
# DEFECT REPORTING
# ============================================================

def save_defect_report(
    reported_by,
    reporter_role,
    department_id,
    department_name,
    subdivision_id,
    subdivision_name,
    defect_type,
    location_start_km,
    location_end_km,
    severity,
    description
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO defect_reports (

            reported_by,
            reporter_role,
            department_id,
            department_name,
            subdivision_id,
            subdivision_name,
            defect_type,
            location_start_km,
            location_end_km,
            severity,
            description,
            reported_at,
            status

        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (

        reported_by,
        reporter_role,
        department_id,
        department_name,
        subdivision_id,
        subdivision_name,
        defect_type,
        location_start_km,
        location_end_km,
        severity,
        description,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "PENDING"

    ))

    connection.commit()

    connection.close()


def get_defect_reports():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM defect_reports
        ORDER BY report_id DESC
    """)

    reports = cursor.fetchall()

    connection.close()

    return reports


# ============================================================
# TASK CREATION FROM DEFECT
# ============================================================

def create_task_from_defect(
    defect_type,
    description,
    department_id,
    subdivision_id,
    location_start_km,
    location_end_km,
    severity
):

    severity_priority = {

        "Critical": 100,
        "High": 90,
        "Medium": 70,
        "Low": 50

    }

    priority = severity_priority.get(
        severity,
        50
    )

    title = f"{defect_type} - Newly Reported"

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute("""
            INSERT INTO tasks (

                title,
                description,
                department_id,
                subdivision_id,
                location_start_km,
                location_end_km,
                priority,
                duration_minutes,
                requires_block,
                required_resource_id,
                due_date,
                status,
                source

            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (

            title,
            description,
            department_id,
            subdivision_id,
            location_start_km,
            location_end_km,
            priority,
            60,
            1,
            None,
            None,
            "PENDING",
            "DEFECT_REPORT"

        ))

        connection.commit()

        success = True

    except sqlite3.Error:

        success = False

    connection.close()

    return success


# ============================================================
# LOGIN SYSTEM
# ============================================================

def get_demo_users():

    departments = get_departments()

    subdivisions = get_subdivisions()

    engineering_id = None
    snt_id = None
    trd_id = None

    for department in departments:

        name = department["department_name"].lower()

        if "engineering" in name:
            engineering_id = department["department_id"]

        elif "s&t" in name or "signal" in name:
            snt_id = department["department_id"]

        elif "trd" in name or "traction" in name:
            trd_id = department["department_id"]


    # Fallback in case our dummy database uses different names.

    if engineering_id is None and len(departments) >= 1:
        engineering_id = departments[0]["department_id"]

    if snt_id is None and len(departments) >= 2:
        snt_id = departments[1]["department_id"]

    if trd_id is None and len(departments) >= 3:
        trd_id = departments[2]["department_id"]


    subdivision_id = None

    if subdivisions:

        subdivision_id = subdivisions[0]["subdivision_id"]


    users = {

        "eng001": {
            "password": "eng123",
            "role": "Gang / Beat",
            "department_id": engineering_id,
            "subdivision_id": subdivision_id,
            "display_name": "Engineering Beat 01"
        },

        "snt001": {
            "password": "snt123",
            "role": "Gang / Beat",
            "department_id": snt_id,
            "subdivision_id": subdivision_id,
            "display_name": "S&T Beat 01"
        },

        "trd001": {
            "password": "trd123",
            "role": "Gang / Beat",
            "department_id": trd_id,
            "subdivision_id": subdivision_id,
            "display_name": "TRD Beat 01"
        },

        "inspect001": {
            "password": "inspect123",
            "role": "Inspection Team",
            "department_id": None,
            "subdivision_id": None,
            "display_name": "Inspection Team"
        },

        "control001": {
            "password": "control123",
            "role": "Control Office",
            "department_id": None,
            "subdivision_id": None,
            "display_name": "Control Office"
        },

        "admin": {
            "password": "admin123",
            "role": "Planner / Administrator",
            "department_id": None,
            "subdivision_id": None,
            "display_name": "Railway Planner"
        }

    }

    return users


def login_screen():

    st.markdown(
        """
        <div style="text-align:center">

        <h1>🚂 Railway Automatic Block Planner</h1>

        <p>
        AI-Assisted Maintenance Coordination &
        Block Optimization
        </p>

        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    left, center, right = st.columns(
        [1, 2, 1]
    )

    with center:

        st.subheader("🔐 Railway Personnel Login")

        username = st.text_input(
            "Username"
        )

        password = st.text_input(
            "Password",
            type="password"
        )

        login = st.button(
            "LOGIN",
            use_container_width=True
        )

        if login:

            users = get_demo_users()

            if (
                username in users
                and users[username]["password"] == password
            ):

                st.session_state.logged_in = True

                st.session_state.username = username

                st.session_state.user = users[username]

                st.success(
                    "Login successful!"
                )

                st.rerun()

            else:

                st.error(
                    "Invalid username or password."
                )


        with st.expander(
            "Demo credentials"
        ):

            st.write(
                "Engineering Gang: `eng001 / eng123`"
            )

            st.write(
                "S&T Gang: `snt001 / snt123`"
            )

            st.write(
                "TRD Gang: `trd001 / trd123`"
            )

            st.write(
                "Inspection: `inspect001 / inspect123`"
            )

            st.write(
                "Control Office: `control001 / control123`"
            )

            st.write(
                "Planner: `admin / admin123`"
            )


# ============================================================
# SIDEBAR
# ============================================================

def show_sidebar():

    user = st.session_state.user

    st.sidebar.title("🚂 Railway Planner")

    st.sidebar.write(
        f"**User:** {user['display_name']}"
    )

    st.sidebar.write(
        f"**Role:** {user['role']}"
    )

    st.sidebar.divider()

    if st.sidebar.button(
        "🚪 Logout",
        use_container_width=True
    ):

        st.session_state.logged_in = False

        st.session_state.pop(
            "user",
            None
        )

        st.session_state.pop(
            "username",
            None
        )

        st.rerun()


# ============================================================
# TASK CARD
# ============================================================

def display_task_card(task):

    priority = task["priority"]

    if priority >= 90:

        priority_icon = "🔴"
        priority_text = "CRITICAL / HIGH"

    elif priority >= 70:

        priority_icon = "🟠"
        priority_text = "MEDIUM"

    else:

        priority_icon = "🟢"
        priority_text = "LOW"


    with st.container(border=True):

        col1, col2 = st.columns(
            [3, 1]
        )

        with col1:

            st.markdown(
                f"### {priority_icon} "
                f"{task['title']}"
            )

            st.write(
                f"**Department:** "
                f"{task['department_name']}"
            )

            st.write(
                f"**Location:** "
                f"KM {task['location_start_km']} "
                f"– "
                f"{task['location_end_km']}"
            )

            st.write(
                f"**Duration:** "
                f"{task['duration_minutes']} minutes"
            )

        with col2:

            st.metric(
                "Priority",
                priority
            )

            st.caption(
                priority_text
            )


# ============================================================
# DEFECT REPORT FORM
# ============================================================

def defect_report_form(
    reporter_name,
    reporter_role,
    department_id,
    subdivision_id,
    inspection_mode=False
):

    st.subheader(
        "📝 Report a Defect"
    )

    defect_type = st.selectbox(

        "Defect Type",

        [
            "Rail Defect",
            "Track Alignment",
            "Sleeper Damage",
            "Ballast Issue",
            "Drainage Problem",
            "Signal Failure",
            "Telecommunication Failure",
            "OHE / Traction Defect",
            "Equipment Failure",
            "Other"
        ]

    )

    col1, col2 = st.columns(2)

    with col1:

        start_km = st.number_input(
            "Location Start (KM)",
            min_value=0.0,
            step=0.1
        )

    with col2:

        end_km = st.number_input(
            "Location End (KM)",
            min_value=0.0,
            step=0.1
        )


    severity = st.select_slider(

        "Severity",

        options=[
            "Low",
            "Medium",
            "High",
            "Critical"
        ],

        value="Medium"

    )


    description = st.text_area(
        "Description",
        placeholder="Describe the defect..."
    )


    # Inspection team must choose department.

    if inspection_mode:

        departments = get_departments()

        department_options = {

            d["department_name"]:
            d["department_id"]

            for d in departments

        }

        selected_department = st.selectbox(

            "Responsible Department",

            list(
                department_options.keys()
            )

        )

        selected_department_id = \
            department_options[selected_department]

    else:

        selected_department_id = department_id

        selected_department = \
            get_department_name(
                department_id
            )


    if st.button(
        "🚨 SUBMIT DEFECT REPORT",
        use_container_width=True
    ):

        if end_km < start_km:

            st.error(
                "End KM cannot be smaller than Start KM."
            )

            return


        if not description.strip():

            st.error(
                "Please provide a description."
            )

            return


        subdivision_name = \
            get_subdivision_name(
                subdivision_id
            )


        save_defect_report(

            reporter_name,
            reporter_role,

            selected_department_id,
            selected_department,

            subdivision_id,
            subdivision_name,

            defect_type,

            start_km,
            end_km,

            severity,
            description

        )


        task_created = create_task_from_defect(

            defect_type,
            description,

            selected_department_id,
            subdivision_id,

            start_km,
            end_km,

            severity

        )


        if task_created:

            st.success(
                "🚨 Defect reported successfully "
                "and added to the maintenance task queue!"
            )

            st.info(
                "The scheduling engine will consider "
                "this task during the next schedule generation."
            )

        else:

            st.warning(
                "Defect report saved, but the task "
                "could not be added to the existing task table."
            )


        st.rerun()


# ============================================================
# GANG / BEAT DASHBOARD
# ============================================================

def gang_dashboard():

    user = st.session_state.user

    st.title(
        f"👷 {user['display_name']}"
    )

    st.caption(
        "Maintenance & Defect Reporting Dashboard"
    )

    department_id = user["department_id"]

    subdivision_id = user["subdivision_id"]


    if department_id is None:

        st.error(
            "Department could not be identified."
        )

        return


    # --------------------------------------------------------
    # Header metrics
    # --------------------------------------------------------

    tasks = get_tasks()

    own_tasks = [

        task

        for task in tasks

        if task["department_id"] == department_id

        and task["subdivision_id"] == subdivision_id

    ]


    critical_tasks = [

        task

        for task in own_tasks

        if task["priority"] >= 90

    ]


    col1, col2, col3 = st.columns(3)


    with col1:

        st.metric(
            "Pending Tasks",
            len(own_tasks)
        )


    with col2:

        st.metric(
            "High Priority",
            len(critical_tasks)
        )


    with col3:

        st.metric(
            "Subdivision",
            get_subdivision_name(
                subdivision_id
            )
        )


    st.divider()


    tab1, tab2, tab3 = st.tabs(

        [
            "📋 My Maintenance Tasks",
            "📝 Report Defect",
            "🚂 Today's Block Plan"
        ]

    )


    # --------------------------------------------------------
    # TASK TAB
    # --------------------------------------------------------

    with tab1:

        st.subheader(
            "Your Maintenance Tasks"
        )

        if not own_tasks:

            st.success(
                "No pending maintenance tasks."
            )

        else:

            sorted_tasks = sorted(

                own_tasks,

                key=lambda x: x["priority"],

                reverse=True

            )

            for task in sorted_tasks:

                display_task_card(task)


    # --------------------------------------------------------
    # REPORT TAB
    # --------------------------------------------------------

    with tab2:

        defect_report_form(

            reporter_name=user["display_name"],

            reporter_role=user["role"],

            department_id=department_id,

            subdivision_id=subdivision_id,

            inspection_mode=False

        )


    # --------------------------------------------------------
    # BLOCK PLAN TAB
    # --------------------------------------------------------

    with tab3:

        show_schedule()


# ============================================================
# INSPECTION TEAM DASHBOARD
# ============================================================

def inspection_dashboard():

    st.title(
        "🔍 Inspection Team"
    )

    st.caption(
        "Cross-Department Maintenance Inspection"
    )


    subdivisions = get_subdivisions()


    if not subdivisions:

        st.warning(
            "No subdivisions found."
        )

        return


    subdivision_options = {

        subdivision["subdivision_name"]:
        subdivision["subdivision_id"]

        for subdivision in subdivisions

    }


    selected_name = st.selectbox(

        "Select Sub-Subdivision",

        list(
            subdivision_options.keys()
        )

    )


    selected_id = \
        subdivision_options[selected_name]


    tasks = get_tasks()


    subdivision_tasks = [

        task

        for task in tasks

        if task["subdivision_id"] == selected_id

    ]


    st.divider()


    # --------------------------------------------------------
    # Department summary
    # --------------------------------------------------------

    departments = {}

    for task in subdivision_tasks:

        department = task["department_name"]

        departments[department] = \
            departments.get(department, 0) + 1


    st.subheader(
        f"Maintenance Overview — {selected_name}"
    )


    cols = st.columns(
        max(1, len(departments))
    )


    for index, (
        department,
        count
    ) in enumerate(
        departments.items()
    ):

        with cols[index]:

            st.metric(
                department,
                count
            )


    st.divider()


    # --------------------------------------------------------
    # All department tasks
    # --------------------------------------------------------

    if not subdivision_tasks:

        st.success(
            "No pending maintenance work."
        )

    else:

        sorted_tasks = sorted(

            subdivision_tasks,

            key=lambda x: x["priority"],

            reverse=True

        )


        for task in sorted_tasks:

            display_task_card(task)


    st.divider()


    # --------------------------------------------------------
    # Inspection reporting
    # --------------------------------------------------------

    with st.expander(
        "📝 Report New Inspection Finding",
        expanded=True
    ):

        defect_report_form(

            reporter_name="Inspection Team",

            reporter_role="Inspection Team",

            department_id=None,

            subdivision_id=selected_id,

            inspection_mode=True

        )


# ============================================================
# CONTROL OFFICE DASHBOARD
# ============================================================

def control_office_dashboard():

    st.title(
        "🚦 Control Office"
    )

    st.caption(
        "Train Movement & Delay Management"
    )


    trains = get_trains()


    if not trains:

        st.warning(
            "No train data found."
        )

        return


    # --------------------------------------------------------
    # Current train status
    # --------------------------------------------------------

    unique_trains = {}

    for train in trains:

        unique_trains[
            train["train_number"]
        ] = train


    train_numbers = list(
        unique_trains.keys()
    )


    selected_train_number = st.selectbox(

        "Select Delayed Train",

        train_numbers

    )


    selected_train = unique_trains[
        selected_train_number
    ]


    st.subheader(
        f"🚆 Train {selected_train_number}"
    )


    col1, col2, col3 = st.columns(3)


    with col1:

        st.write(
            "**Train Name**"
        )

        st.write(
            selected_train["train_name"]
        )


    with col2:

        st.write(
            "**Train Type**"
        )

        st.write(
            selected_train["train_type"]
        )


    with col3:

        current_delay = \
            selected_train["delay_minutes"] or 0

        st.metric(
            "Current Delay",
            f"{current_delay} min"
        )


    # --------------------------------------------------------
    # Route
    # --------------------------------------------------------

    st.subheader(
        "📍 Train Route"
    )


    train_route = [

        train

        for train in trains

        if train["train_number"]
        == selected_train_number

    ]


    for route in train_route:

        st.write(

            f"KM {route['location_start_km']} "
            f"→ "
            f"KM {route['location_end_km']} | "
            f"{route['scheduled_arrival']} "
            f"→ "
            f"{route['scheduled_departure']}"

        )


    st.divider()


    # --------------------------------------------------------
    # Delay update
    # --------------------------------------------------------

    st.subheader(
        "⏱️ Update Train Delay"
    )


    delay = st.number_input(

        "Delay in minutes",

        min_value=0,

        max_value=720,

        value=int(
            selected_train["delay_minutes"] or 0
        ),

        step=5

    )


    if st.button(

        "🔄 UPDATE & RESCHEDULE",

        use_container_width=True

    ):

        update_train_delay(

            selected_train_number,

            delay

        )


        st.success(

            f"Train {selected_train_number} "
            f"updated with {delay} minute delay."

        )


        # Generate new schedule

        new_schedule = generate_schedule()


        st.session_state[
            "latest_schedule"
        ] = new_schedule


        st.session_state[
            "schedule_updated"
        ] = True


        st.rerun()


    # --------------------------------------------------------
    # Updated schedule
    # --------------------------------------------------------

    if st.session_state.get(
        "schedule_updated",
        False
    ):

        st.divider()

        st.success(
            "🚨 Maintenance schedule has been recalculated."
        )

        show_schedule()


# ============================================================
# SCHEDULE DASHBOARD
# ============================================================

def show_schedule():

    st.subheader(
        "🤖 Automatic Block Plan"
    )


    try:

        schedule = generate_schedule()

    except Exception as error:

        st.error(
            f"Scheduling engine error: {error}"
        )

        return


    if not schedule:

        st.warning(
            "No feasible maintenance blocks found."
        )

        return


    # --------------------------------------------------------
    # Metrics
    # --------------------------------------------------------

    total_blocks = len(schedule)

    total_tasks = sum(

        len(block["tasks"])

        for block in schedule

    )


    total_block_minutes = sum(

        block["end_time"]
        - block["start_time"]

        for block in schedule

    )


    average_score = sum(

        block["score"]

        for block in schedule

    ) / total_blocks


    col1, col2, col3, col4 = st.columns(4)


    with col1:

        st.metric(
            "Maintenance Blocks",
            total_blocks
        )


    with col2:

        st.metric(
            "Scheduled Tasks",
            total_tasks
        )


    with col3:

        st.metric(
            "Total Block Time",
            f"{total_block_minutes} min"
        )


    with col4:

        st.metric(
            "Avg. Optimization Score",
            f"{average_score:.1f}"
        )


    st.divider()


    # --------------------------------------------------------
    # Blocks
    # --------------------------------------------------------

    for index, block in enumerate(
        schedule,
        start=1
    ):

        start_time = minutes_to_time(
            block["start_time"]
        )

        end_time = minutes_to_time(
            block["end_time"]
        )


        with st.container(
            border=True
        ):

            st.markdown(
                f"## 🚧 BLOCK #{index}"
            )


            col1, col2, col3 = st.columns(3)


            with col1:

                st.write(
                    "**Corridor**"
                )

                st.write(

                    f"KM {block['start_km']} "
                    f"→ "
                    f"KM {block['end_km']}"

                )


            with col2:

                st.write(
                    "**Time Window**"
                )

                st.write(

                    f"{start_time} "
                    f"→ "
                    f"{end_time}"

                )


            with col3:

                st.write(
                    "**Optimization Score**"
                )

                st.write(
                    f"{block['score']:.2f}"
                )


            st.markdown(
                "### Maintenance Activities"
            )


            for task in block["tasks"]:

                st.write(

                    f"🔧 **{task['department_name']}** — "
                    f"{task['title']} | "
                    f"Priority: "
                    f"{task['priority']} | "
                    f"Duration: "
                    f"{task['duration_minutes']} min"

                )
# ============================================================
# FULL PLAN DISPLAY
# Weekly / Monthly Plan A
# ============================================================

def display_full_plan(plan, plan_title="Optimized Plan"):

    st.subheader(f"📅 {plan_title}")

    if not plan:

        st.warning(
            "No maintenance blocks could be scheduled."
        )

        return

    summary = get_plan_summary(plan)

    # --------------------------------------------------------
    # Plan Metrics
    # --------------------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        st.metric(
            "Total Blocks",
            summary["total_blocks"]
        )

    with col2:

        st.metric(
            "Total Tasks",
            summary["total_tasks"]
        )

    with col3:

        st.metric(
            "Total Block Time",
            f"{summary['total_block_minutes']} min"
        )

    with col4:

        st.metric(
            "Avg. Optimization Score",
            f"{summary['average_score']:.1f}"
        )

    st.divider()

    # --------------------------------------------------------
    # Display Each Block
    # --------------------------------------------------------

    for block in plan:

        start_time = minutes_to_time(
            block["start_time"]
        )

        end_time = minutes_to_time(
            block["end_time"]
        )

        status = block.get(
            "status",
            "SCHEDULED"
        )

        plan_date = block.get(
            "plan_date",
            "Not Assigned"
        )

        with st.container(border=True):

            st.markdown(
                f"### 🚧 {block['block_id']}"
            )

            col1, col2, col3, col4 = st.columns(4)

            with col1:

                st.write(
                    "**Date**"
                )

                st.write(
                    plan_date
                )

            with col2:

                st.write(
                    "**Corridor**"
                )

                st.write(
                    f"KM {block['start_km']} "
                    f"→ {block['end_km']}"
                )

            with col3:

                st.write(
                    "**Time**"
                )

                st.write(
                    f"{start_time} "
                    f"→ {end_time}"
                )

            with col4:

                st.write(
                    "**Status**"
                )

                st.write(
                    status
                )

            st.write(
                f"**Departments:** "
                f"{', '.join(block['departments'])}"
            )

            st.write(
                f"**Tasks:** "
                f"{block['task_count']}"
            )

            st.write(
                f"**Total Priority:** "
                f"{block['total_priority']}"
            )

            st.write(
                f"**Optimization Score:** "
                f"{block['score']:.2f}"
            )

            st.markdown(
                "#### 🔧 Maintenance Activities"
            )

            for task in block["tasks"]:

                st.write(

                    f"• **{task['department_name']}** — "
                    f"{task['title']} | "
                    f"Priority: {task['priority']} | "
                    f"Duration: "
                    f"{task['duration_minutes']} min"

                )


# ============================================================
# PLAN DOWNLOAD
# ============================================================

def convert_plan_to_csv(plan):

    import csv
    import io

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Block ID",
        "Plan Date",
        "Start Time",
        "End Time",
        "Start KM",
        "End KM",
        "Departments",
        "Task Count",
        "Total Priority",
        "Duration Minutes",
        "Optimization Score",
        "Status"
    ])

    for block in plan:

        writer.writerow([

            block.get(
                "block_id",
                ""
            ),

            block.get(
                "plan_date",
                ""
            ),

            minutes_to_time(
                block["start_time"]
            ),

            minutes_to_time(
                block["end_time"]
            ),

            block["start_km"],

            block["end_km"],

            ", ".join(
                block.get(
                    "departments",
                    []
                )
            ),

            block.get(
                "task_count",
                len(block["tasks"])
            ),

            block.get(
                "total_priority",
                0
            ),

            block.get(
                "duration_minutes",
                block["end_time"]
                - block["start_time"]
            ),

            round(
                block["score"],
                2
            ),

            block.get(
                "status",
                "SCHEDULED"
            )

        ])

    return output.getvalue()


# ============================================================
# PLANNER / ADMIN DASHBOARD
# ============================================================

def planner_dashboard():

    st.title(
        "📊 Railway Maintenance Planning Center"
    )

    st.caption(
        "Centralized view of maintenance, trains and optimized blocks"
    )

    tasks = get_tasks()
    trains = get_trains()
    resources = get_resources()
    reports = get_defect_reports()

    # System metrics
    ...

    st.divider()

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "🤖 Daily Schedule",
            "📅 Weekly Plan",
            "🗓️ Monthly Plan",
            "🧪 What-If / Plan B",
            "🚨 Defects & Trains"
        ]
    )

    # DAILY SCHEDULE
    with tab1:
        show_schedule()

    # WEEKLY PLAN
    with tab2:
        st.subheader("📅 Weekly Maintenance Plan")

        st.write(
            "Generate a 7-day optimized maintenance plan."
        )

        if st.button(
            "🚀 GENERATE WEEKLY PLAN",
            use_container_width=True
        ):
            weekly_plan = generate_full_plan("weekly")

            st.session_state["weekly_plan"] = weekly_plan

        if "weekly_plan" in st.session_state:

            weekly_plan = st.session_state["weekly_plan"]

            display_full_plan(
                weekly_plan,
                "Weekly Optimized Plan"
            )

            csv_data = convert_plan_to_csv(weekly_plan)

            st.download_button(
                label="⬇️ Download Weekly Plan CSV",
                data=csv_data,
                file_name="weekly_maintenance_plan.csv",
                mime="text/csv",
                use_container_width=True
            )


    # MONTHLY PLAN
    with tab3:
        st.subheader("🗓️ Monthly Maintenance Plan")

        st.write(
            "Generate a 30-day optimized maintenance plan."
        )

        if st.button(
            "🚀 GENERATE MONTHLY PLAN",
            use_container_width=True
        ):
            monthly_plan = generate_full_plan("monthly")

            st.session_state["monthly_plan"] = monthly_plan

        if "monthly_plan" in st.session_state:

            monthly_plan = st.session_state["monthly_plan"]

            display_full_plan(
                monthly_plan,
                "Monthly Optimized Plan"
            )

            csv_data = convert_plan_to_csv(monthly_plan)

            st.download_button(
                label="⬇️ Download Monthly Plan CSV",
                data=csv_data,
                file_name="monthly_maintenance_plan.csv",
                mime="text/csv",
                use_container_width=True
            )


    # WHAT-IF / PLAN B
    with tab4:

        st.subheader(
            "🧪 What-If Simulation / Plan B"
        )

        st.info(
            "Simulate train delays and weather conditions "
            "without changing the original Plan A."
        )


    # DEFECTS & TRAINS
    with tab5:

        st.subheader("🚨 Defect Reports")

        if not reports:

            st.success("No defect reports.")

        else:

            for report in reports:

                with st.container(border=True):

                    st.markdown(
                        f"### 🚨 Report #{report['report_id']}"
                    )

                    st.write(
                        f"**Type:** {report['defect_type']}"
                    )

                    st.write(
                        f"**Department:** "
                        f"{report['department_name']}"
                    )

                    st.write(
                        f"**Location:** "
                        f"KM {report['location_start_km']} "
                        f"→ {report['location_end_km']}"
                    )

                    st.write(
                        f"**Severity:** {report['severity']}"
                    )

                    st.write(
                        f"**Reported by:** "
                        f"{report['reported_by']}"
                    )

                    st.write(report["description"])

        st.divider()

        st.subheader("🚆 Train Status")

        if not trains:

            st.warning("No train data.")

        else:

            for train in trains:

                delay = train["delay_minutes"] or 0

                if delay > 0:
                    status = "🔴 DELAYED"
                else:
                    status = "🟢 ON TIME"

                st.write(
                    f"**{train['train_number']}** "
                    f"{train['train_name']} — "
                    f"{status} ({delay} min)"
                )

# ============================================================
# MAIN APPLICATION
# ============================================================

def main():

    initialize_app_tables()


    # Session initialization

    if "logged_in" not in st.session_state:

        st.session_state.logged_in = False


    # --------------------------------------------------------
    # Login
    # --------------------------------------------------------

    if not st.session_state.logged_in:

        login_screen()

        return


    # --------------------------------------------------------
    # Logged-in application
    # --------------------------------------------------------

    show_sidebar()


    user = st.session_state.user

    role = user["role"]


    # --------------------------------------------------------
    # Role-based routing
    # --------------------------------------------------------

    if role == "Gang / Beat":

        gang_dashboard()


    elif role == "Inspection Team":

        inspection_dashboard()


    elif role == "Control Office":

        control_office_dashboard()


    elif role == "Planner / Administrator":

        planner_dashboard()


    else:

        st.error(
            "Unknown user role."
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
