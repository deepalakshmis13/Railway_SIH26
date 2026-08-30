import sqlite3
from datetime import datetime, date, timedelta
import copy


# ============================================================
# CONFIGURATION
# ============================================================

DB_PATH = "database/railway_planner.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    connection = sqlite3.connect(DB_PATH)

    return connection


# ============================================================
# DATA RETRIEVAL
# ============================================================

def get_tasks():

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            t.task_id,
            t.title,
            t.description,
            t.department_id,
            d.department_name,
            t.subdivision_id,
            s.subdivision_name,
            t.location_start_km,
            t.location_end_km,
            t.priority,
            t.duration_minutes,
            t.requires_block,
            t.required_resource_id,
            t.due_date,
            t.status,
            t.source
        FROM tasks t

        JOIN departments d
            ON t.department_id = d.department_id

        JOIN sub_sub_divisions s
            ON t.subdivision_id = s.subdivision_id

        WHERE t.status = 'PENDING'

        ORDER BY t.priority DESC
    """)

    # Convert sqlite3.Row objects to normal dictionaries
    tasks = [
        dict(row)
        for row in cursor.fetchall()
    ]

    connection.close()

    return tasks


def get_trains():

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            tr.route_id,
            tr.train_id,
            t.train_number,
            t.train_name,
            t.train_type,
            tr.subdivision_id,
            tr.location_start_km,
            tr.location_end_km,
            tr.scheduled_arrival,
            tr.scheduled_departure,
            t.delay_minutes
        FROM train_routes tr

        JOIN trains t
            ON tr.train_id = t.train_id

        ORDER BY tr.scheduled_arrival
    """)

    # Convert sqlite3.Row objects to normal dictionaries
    trains = [
        dict(row)
        for row in cursor.fetchall()
    ]

    connection.close()

    return trains

def get_resources():

    connection = get_connection()

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            resource_id,
            resource_name,
            resource_type,
            department_id,
            subdivision_id,
            available_from,
            available_until,
            status
        FROM resources
        WHERE status = 'AVAILABLE'
    """)

    # Convert sqlite3.Row objects to normal dictionaries
    resources = [
        dict(row)
        for row in cursor.fetchall()
    ]

    connection.close()

    return resources

# ============================================================
# LOCATION AND COMPATIBILITY
# ============================================================

def locations_overlap(task1, task2):

    start1 = task1["location_start_km"]
    end1 = task1["location_end_km"]

    start2 = task2["location_start_km"]
    end2 = task2["location_end_km"]

    return max(start1, start2) <= min(end1, end2)


def can_share_block(task1, task2):

    # Must belong to the same subdivision.

    if task1["subdivision_id"] != task2["subdivision_id"]:

        return False


    # Both activities must require a railway block.

    if not task1["requires_block"]:

        return False

    if not task2["requires_block"]:

        return False


    # Work locations must overlap.

    if not locations_overlap(task1, task2):

        return False


    return True


def find_compatible_tasks(tasks):

    compatible_pairs = []

    for i in range(len(tasks)):

        for j in range(i + 1, len(tasks)):

            task1 = tasks[i]
            task2 = tasks[j]

            if can_share_block(task1, task2):

                compatible_pairs.append(
                    (task1, task2)
                )

    return compatible_pairs


# ============================================================
# TASK GROUPING
# ============================================================

def task_can_join_group(candidate, group):

    if not group:
        return True

    first_task = group[0]

    # Task must be in the same subdivision.
    if (
        candidate["subdivision_id"]
        != first_task["subdivision_id"]
    ):
        return False

    # Both tasks must require a railway block.
    if not candidate["requires_block"]:
        return False

    # Check whether the candidate overlaps with
    # the current combined block location.
    block_start, block_end = calculate_block_location(
        group
    )

    if not ranges_overlap(
        block_start,
        block_end,
        candidate["location_start_km"],
        candidate["location_end_km"]
    ):
        return False

    # Avoid grouping tasks that are too far apart
    # in terms of due date.
    group_due_date = get_group_due_date(group)

    if group_due_date and candidate["due_date"]:

        group_date = datetime.strptime(
            group_due_date,
            "%Y-%m-%d"
        ).date()

        candidate_date = datetime.strptime(
            candidate["due_date"],
            "%Y-%m-%d"
        ).date()

        date_difference = abs(
            (candidate_date - group_date).days
        )

        # Tasks within 2 days can share a block.
        if date_difference > 2:
            return False

    return True
def build_task_groups(tasks):

    """
    Groups compatible maintenance tasks into shared blocks.
    """

    groups = []

    visited = set()


    for task in tasks:

        if task["task_id"] in visited:

            continue


        group = [task]

        visited.add(task["task_id"])


        changed = True


        while changed:

            changed = False


            for candidate in tasks:

                if candidate["task_id"] in visited:

                    continue


                if task_can_join_group(candidate, group):

                    group.append(candidate)

                    visited.add(candidate["task_id"])

                    changed = True


        groups.append(group)


    return groups


# ============================================================
# BLOCK CALCULATIONS
# ============================================================

def calculate_block_location(task_group):

    start_km = min(

        task["location_start_km"]

        for task in task_group
    )


    end_km = max(

        task["location_end_km"]

        for task in task_group
    )


    return start_km, end_km


def calculate_block_duration(task_group):

    """
    Tasks in the same block are assumed to be performed
    in parallel where possible.

    Therefore the longest task determines the block duration.
    """

    return max(

        task["duration_minutes"]

        for task in task_group
    )


def calculate_priority_score(task_group):

    return sum(

        task["priority"]

        for task in task_group
    )

def get_group_due_date(task_group):

    due_dates = [

        task["due_date"]

        for task in task_group

        if task["due_date"]
    ]

    if not due_dates:

        return None

    return min(due_dates)


# ============================================================
# TIME UTILITIES
# ============================================================

def time_to_minutes(time_string):

    if time_string is None:

        return 0


    time_string = str(time_string).strip()


    if not time_string:

        return 0


    hours, minutes = map(

        int,
        time_string.split(":")
    )


    return hours * 60 + minutes


def minutes_to_time(minutes):

    minutes = int(minutes)

    hours = minutes // 60

    mins = minutes % 60

    return f"{hours:02d}:{mins:02d}"


def ranges_overlap(

    start1,
    end1,

    start2,
    end2
):

    return max(

        start1,
        start2

    ) <= min(

        end1,
        end2
    )


# ============================================================
# TRAIN CONFLICT LOGIC
# ============================================================

def get_actual_train_times(train):

    arrival = time_to_minutes(

        train["scheduled_arrival"]
    )


    departure = time_to_minutes(

        train["scheduled_departure"]
    )


    delay = train["delay_minutes"] or 0


    arrival += delay

    departure += delay


    return arrival, departure


def block_conflicts_with_train(

    block_start_km,
    block_end_km,

    block_start_time,
    block_end_time,

    train,

    subdivision_id=None
):

    # If subdivision information is available,
    # trains on another subdivision cannot conflict.

    if subdivision_id is not None:

        if train["subdivision_id"] != subdivision_id:

            return False


    # Geographic overlap.

    spatial_conflict = ranges_overlap(

        block_start_km,
        block_end_km,

        train["location_start_km"],
        train["location_end_km"]
    )


    if not spatial_conflict:

        return False


    train_arrival, train_departure = (

        get_actual_train_times(train)
    )


    # Temporal overlap.

    temporal_conflict = ranges_overlap(

        block_start_time,
        block_end_time,

        train_arrival,
        train_departure
    )


    return temporal_conflict


# ============================================================
# RESOURCE CONFLICT CHECK
# ============================================================

def resource_conflict(task_group):

    resources_used = set()


    for task in task_group:

        resource_id = task["required_resource_id"]


        if resource_id is None:

            continue


        if resource_id in resources_used:

            return True


        resources_used.add(resource_id)


    return False


# ============================================================
# TIME WINDOW GENERATION
# ============================================================

def generate_time_windows(

    start_hour=8,
    end_hour=18,
    step_minutes=30
):

    windows = []

    start = start_hour * 60

    end = end_hour * 60


    current = start


    while current < end:

        windows.append(current)

        current += step_minutes


    return windows


def find_feasible_windows(

    task_group,
    trains,

    start_hour=8,
    end_hour=18
):

    block_start_km, block_end_km = (

        calculate_block_location(task_group)
    )


    duration = calculate_block_duration(

        task_group
    )


    subdivision_id = task_group[0]["subdivision_id"]


    candidates = generate_time_windows(

        start_hour=start_hour,
        end_hour=end_hour
    )


    feasible = []


    for start_time in candidates:

        end_time = start_time + duration


        # Do not exceed operating window.

        if end_time > end_hour * 60:

            continue


        conflict = False


        for train in trains:

            if block_conflicts_with_train(

                block_start_km,
                block_end_km,

                start_time,
                end_time,

                train,

                subdivision_id
            ):

                conflict = True

                break


        if not conflict:

            feasible.append(

                (
                    start_time,
                    end_time
                )
            )


    return feasible


# ============================================================
# SCHEDULE SCORING
# ============================================================

def score_schedule(

    task_group,

    start_time,
    end_time
):

    priority_score = calculate_priority_score(

        task_group
    )


    duration = end_time - start_time


    # Earlier blocks get a small advantage.

    time_penalty = start_time / 100


    # Longer blocks receive a small penalty.

    duration_penalty = duration / 10


    score = (

        priority_score

        - time_penalty

        - duration_penalty
    )


    return score


# ============================================================
# DAILY SCHEDULE GENERATION
# ============================================================

def generate_schedule():

    tasks = get_tasks()

    trains = get_trains()


    if not tasks:

        return []


    groups = build_task_groups(tasks)


    schedule = []


    for group in groups:


        # Skip groups with duplicate exclusive resources.

        if resource_conflict(group):

            continue


        windows = find_feasible_windows(

            group,
            trains
        )


        if not windows:

            print(

                "No feasible window found for group."
            )

            continue


        best_window = None

        best_score = float("-inf")


        for start_time, end_time in windows:

            score = score_schedule(

                group,

                start_time,
                end_time
            )


            if score > best_score:

                best_score = score

                best_window = (

                    start_time,
                    end_time
                )


        start_time, end_time = best_window


        start_km, end_km = (

            calculate_block_location(group)
        )


        schedule.append({

            "tasks": group,

            "subdivision_id":
                group[0]["subdivision_id"],

            "start_km":
                start_km,

            "end_km":
                end_km,

            "start_time":
                start_time,

            "end_time":
                end_time,

            "score":
                best_score

        })


    return schedule


# ============================================================
# CONSOLE DISPLAY
# ============================================================

def display_schedule(schedule):

    print("\n")

    print("=" * 60)

    print("          AUTOMATIC BLOCK PLAN")

    print("=" * 60)


    for index, block in enumerate(

        schedule,
        start=1
    ):

        print(

            f"\nBLOCK #{index}"
        )


        print(

            f"Location: "
            f"KM {block['start_km']} - "
            f"KM {block['end_km']}"
        )


        print(

            f"Time: "
            f"{minutes_to_time(block['start_time'])} - "
            f"{minutes_to_time(block['end_time'])}"
        )


        print(

            f"Optimization Score: "
            f"{block['score']:.2f}"
        )


        print("\nTasks:")


        for task in block["tasks"]:

            print(

                f"  [{task['department_name']}] "
                f"{task['title']} "
                f"(Priority {task['priority']})"
            )


    print("\n" + "=" * 60)


# ============================================================
# TRAIN DELAY MANAGEMENT
# ============================================================

def update_train_delay(

    train_number,
    delay_minutes
):

    connection = get_connection()

    cursor = connection.cursor()


    cursor.execute("""

        UPDATE trains

        SET
            delay_minutes = ?,
            status = 'DELAYED'

        WHERE train_number = ?

    """, (

        delay_minutes,
        train_number
    ))


    connection.commit()

    connection.close()


def reschedule_after_delay(

    train_number,
    delay_minutes
):

    update_train_delay(

        train_number,
        delay_minutes
    )


    new_schedule = generate_schedule()


    return new_schedule


# ============================================================
# FULL PLAN GENERATION
# WEEKLY / MONTHLY PLANNING
# ============================================================

def get_horizon_days(horizon):

    horizon = horizon.lower()


    if horizon == "weekly":

        return 7


    elif horizon == "monthly":

        return 30


    else:

        raise ValueError(

            "Horizon must be either "
            "'weekly' or 'monthly'."
        )


def blocks_overlap(

    block1,
    block2
):

    # Geographic overlap.

    location_overlap = ranges_overlap(

        block1["start_km"],
        block1["end_km"],

        block2["start_km"],
        block2["end_km"]
    )


    # Time overlap.

    time_overlap = ranges_overlap(

        block1["start_time"],
        block1["end_time"],

        block2["start_time"],
        block2["end_time"]
    )


    # Different subdivisions can operate independently.

    subdivision1 = block1.get(
        "subdivision_id"
    )

    subdivision2 = block2.get(
        "subdivision_id"
    )


    if (

        subdivision1 is not None

        and subdivision2 is not None

        and subdivision1 != subdivision2
    ):

        return False


    return location_overlap and time_overlap


def assign_blocks_to_days(
    schedule,
    horizon_days
):

    """
    Assigns maintenance blocks across the planning horizon.

    Blocks are scheduled according to their task due dates
    instead of placing everything on today's date.
    """

    start_date = date.today()

    end_date = (
        start_date
        + timedelta(days=horizon_days - 1)
    )

    # Create calendar.

    daily_blocks = {}

    for day_offset in range(horizon_days):

        plan_date = (
            start_date
            + timedelta(days=day_offset)
        ).isoformat()

        daily_blocks[plan_date] = []

    # Sort by priority.

    sorted_schedule = sorted(

        schedule,

        key=lambda block: (

            max(
                task["priority"]
                for task in block["tasks"]
            ),

            block["score"]

        ),

        reverse=True
    )

    final_plan = []


    for block in sorted_schedule:

        assigned = False

        # Get the preferred date from task due dates.

        due_date_string = get_group_due_date(
            block["tasks"]
        )

        if due_date_string:

            preferred_date = datetime.strptime(

                due_date_string,
                "%Y-%m-%d"

            ).date()

        else:

            preferred_date = start_date


        # Emergency or overdue work should start today.

        if preferred_date < start_date:

            preferred_date = start_date


        # If task is outside planning horizon,
        # mark it unscheduled.

        if preferred_date > end_date:

            new_block = copy.deepcopy(block)

            new_block["plan_date"] = (
                "OUTSIDE HORIZON"
            )

            new_block["block_id"] = (

                f"BLK-{len(final_plan) + 1:03d}"
            )

            new_block["status"] = (
                "UNSCHEDULED"
            )

            final_plan.append(new_block)

            continue


        # First try the preferred due date,
        # then following dates.

        candidate_dates = []

        for offset in range(horizon_days):

            candidate_date = (
                preferred_date
                + timedelta(days=offset)
            )

            if candidate_date <= end_date:

                candidate_dates.append(
                    candidate_date
                )


        # If still not possible,
        # try earlier dates.

        for offset in range(1, horizon_days):

            candidate_date = (
                preferred_date
                - timedelta(days=offset)
            )

            if candidate_date >= start_date:

                candidate_dates.append(
                    candidate_date
                )


        # Find first date without a block conflict.

        for candidate_date in candidate_dates:

            plan_date = candidate_date.isoformat()

            existing_blocks = (
                daily_blocks[plan_date]
            )

            conflict_found = False


            for existing_block in existing_blocks:

                if blocks_overlap(

                    block,
                    existing_block

                ):

                    conflict_found = True

                    break


            if not conflict_found:

                new_block = copy.deepcopy(block)

                new_block["plan_date"] = (
                    plan_date
                )

                new_block["block_id"] = (

                    f"BLK-{len(final_plan) + 1:03d}"
                )

                new_block["status"] = (
                    "SCHEDULED"
                )

                daily_blocks[plan_date].append(
                    new_block
                )

                final_plan.append(
                    new_block
                )

                assigned = True

                break


        # No possible date.

        if not assigned:

            new_block = copy.deepcopy(block)

            new_block["plan_date"] = (
                "UNSCHEDULED"
            )

            new_block["block_id"] = (

                f"BLK-{len(final_plan) + 1:03d}"
            )

            new_block["status"] = (
                "UNSCHEDULED"
            )

            final_plan.append(
                new_block
            )


    return final_plan
def add_plan_metadata(plan):

    """
    Adds display and reporting information
    to every maintenance block.
    """

    for block in plan:

        departments = sorted({

            task["department_name"]

            for task in block["tasks"]
        })


        block["departments"] = (
            departments
        )


        block["task_count"] = len(

            block["tasks"]
        )


        block["total_priority"] = sum(

            task["priority"]

            for task in block["tasks"]
        )


        block["duration_minutes"] = (

            block["end_time"]

            -

            block["start_time"]
        )


        if "status" not in block:

            block["status"] = (
                "SCHEDULED"
            )


    return plan


def generate_full_plan(

    horizon="weekly"
):

    """
    Generates the optimized Plan A.

    horizon:
        weekly  -> 7 days
        monthly -> 30 days
    """


    horizon_days = get_horizon_days(

        horizon
    )


    base_schedule = generate_schedule()


    if not base_schedule:

        return []


    full_plan = assign_blocks_to_days(

        base_schedule,

        horizon_days
    )


    full_plan = add_plan_metadata(

        full_plan
    )


    for block in full_plan:

        block["plan_type"] = (
            "PLAN A"
        )


    return full_plan


# ============================================================
# WHAT-IF / PLAN B SIMULATION
# ============================================================

def apply_weather_impact(

    schedule,
    weather_condition
):

    """
    Simulates weather effects.

    This does NOT modify the database
    or the original Plan A.
    """


    weather_condition = (

        weather_condition

        or

        "Normal"
    )


    weather_impact = {

        "Normal": 1.00,

        "Light Rain": 1.10,

        "Heavy Rain": 1.30,

        "Extreme Weather": 1.60
    }


    multiplier = weather_impact.get(

        weather_condition,

        1.00
    )


    modified_schedule = []


    for block in schedule:

        new_block = copy.deepcopy(block)


        original_duration = (

            new_block["end_time"]

            -

            new_block["start_time"]
        )


        new_duration = max(

            1,

            int(
                original_duration *
                multiplier
            )
        )


        new_block["end_time"] = (

            new_block["start_time"]

            +

            new_duration
        )


        new_block["weather_condition"] = (

            weather_condition
        )


        new_block["weather_multiplier"] = (

            multiplier
        )


        modified_schedule.append(

            new_block
        )


    return modified_schedule


def apply_delay_impact(

    schedule,
    delay_minutes
):

    """
    Creates a hypothetical Plan B.

    No database values are modified.
    """


    modified_schedule = []


    for block in schedule:

        new_block = copy.deepcopy(block)


        if delay_minutes > 0:

            new_block["start_time"] += (

                delay_minutes
            )


            new_block["end_time"] += (

                delay_minutes
            )


        new_block["simulated_delay"] = (

            delay_minutes
        )


        modified_schedule.append(

            new_block
        )


    return modified_schedule


def normalize_plan_times(plan):

    """
    Ensures simulated blocks remain inside a
    24-hour time range.

    If a block extends beyond midnight,
    it is marked as affected.
    """

    for block in plan:

        if block["end_time"] > 24 * 60:

            block["status"] = (
                "REQUIRES REVIEW"
            )


        if block["start_time"] < 0:

            block["status"] = (
                "REQUIRES REVIEW"
            )


    return plan


def generate_what_if_plan(

    horizon="weekly",

    delay_minutes=0,

    weather_condition="Normal"
):

    """
    Generates Plan B without changing
    the database or Plan A.
    """


    plan_b = generate_full_plan(

        horizon
    )


    if not plan_b:

        return []


    plan_b = apply_weather_impact(

        plan_b,

        weather_condition
    )


    plan_b = apply_delay_impact(

        plan_b,

        delay_minutes
    )


    plan_b = normalize_plan_times(

        plan_b
    )


    plan_b = add_plan_metadata(

        plan_b
    )


    for block in plan_b:

        block["plan_type"] = (
            "PLAN B"
        )


    return plan_b


# ============================================================
# PLAN SUMMARY
# ============================================================

def get_plan_summary(plan):

    """
    Returns summary metrics for Plan A or Plan B.
    """


    if not plan:

        return {

            "total_blocks": 0,

            "total_tasks": 0,

            "total_block_minutes": 0,

            "average_score": 0,

            "scheduled_blocks": 0,

            "unscheduled_blocks": 0
        }


    total_blocks = len(plan)


    total_tasks = sum(

        len(block["tasks"])

        for block in plan
    )


    total_block_minutes = sum(

        block["end_time"]

        -

        block["start_time"]

        for block in plan
    )


    average_score = sum(

        block["score"]

        for block in plan

    ) / total_blocks


    scheduled_blocks = sum(

        1

        for block in plan

        if block.get("status")
        == "SCHEDULED"
    )


    unscheduled_blocks = sum(

        1

        for block in plan

        if block.get("status")
        == "UNSCHEDULED"
    )


    return {

        "total_blocks":
            total_blocks,

        "total_tasks":
            total_tasks,

        "total_block_minutes":
            total_block_minutes,

        "average_score":
            average_score,

        "scheduled_blocks":
            scheduled_blocks,

        "unscheduled_blocks":
            unscheduled_blocks
    }


# ============================================================
# DASHBOARD HELPER
# ============================================================

def get_schedule_summary():

    """
    Quick summary for the daily dashboard.
    """

    schedule = generate_schedule()


    return get_plan_summary(

        schedule
    )


# ============================================================
# RUN DIRECTLY
# ============================================================

if __name__ == "__main__":

    schedule = generate_schedule()


    display_schedule(schedule)
