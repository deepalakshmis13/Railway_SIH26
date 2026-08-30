import sqlite3

DB_PATH = "database/railway_planner.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


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

    tasks = cursor.fetchall()

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

    trains = cursor.fetchall()

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

    resources = cursor.fetchall()

    connection.close()

    return resources

def locations_overlap(task1, task2):

    start1 = task1["location_start_km"]
    end1 = task1["location_end_km"]

    start2 = task2["location_start_km"]
    end2 = task2["location_end_km"]

    return max(start1, start2) <= min(end1, end2)

def can_share_block(task1, task2):

    # Must be in the same subdivision
    if task1["subdivision_id"] != task2["subdivision_id"]:
        return False

    # Both must require a block
    if not task1["requires_block"] or not task2["requires_block"]:
        return False

    # Their physical work areas must overlap
    if not locations_overlap(task1, task2):
        return False

    # Same department tasks are allowed too,
    # but resource conflicts will be checked later.

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

def build_task_groups(tasks):

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

                for existing in group:

                    if can_share_block(existing, candidate):

                        group.append(candidate)
                        visited.add(candidate["task_id"])

                        changed = True
                        break

        groups.append(group)

    return groups

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

    return max(
        task["duration_minutes"]
        for task in task_group
    )

def time_to_minutes(time_string):

    hours, minutes = map(int, time_string.split(":"))

    return hours * 60 + minutes

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

def ranges_overlap(start1, end1, start2, end2):

    return max(start1, start2) <= min(end1, end2)

def block_conflicts_with_train(
    block_start_km,
    block_end_km,
    block_start_time,
    block_end_time,
    train
):

    # Different subdivision = no conflict
    if train["subdivision_id"] is None:
        return False

    # Check geographic overlap
    spatial_conflict = ranges_overlap(
        block_start_km,
        block_end_km,
        train["location_start_km"],
        train["location_end_km"]
    )

    if not spatial_conflict:
        return False

    train_arrival, train_departure = get_actual_train_times(train)

    # Check time overlap
    temporal_conflict = ranges_overlap(
        block_start_time,
        block_end_time,
        train_arrival,
        train_departure
    )

    return temporal_conflict

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
    trains
):

    block_start_km, block_end_km = \
        calculate_block_location(task_group)

    duration = calculate_block_duration(task_group)

    candidates = generate_time_windows()

    feasible = []

    for start_time in candidates:

        end_time = start_time + duration

        # Don't go beyond 18:00
        if end_time > 18 * 60:
            continue

        conflict = False

        for train in trains:

            if block_conflicts_with_train(
                block_start_km,
                block_end_km,
                start_time,
                end_time,
                train
            ):

                conflict = True
                break

        if not conflict:

            feasible.append(
                (start_time, end_time)
            )

    return feasible

def calculate_priority_score(task_group):

    return sum(
        task["priority"]
        for task in task_group
    )

def score_schedule(
    task_group,
    start_time,
    end_time
):

    priority_score = calculate_priority_score(
        task_group
    )

    duration = end_time - start_time

    # Earlier schedules get a small advantage.
    time_penalty = start_time / 100

    # Longer blocks are penalized.
    duration_penalty = duration / 10

    score = (
        priority_score
        - time_penalty
        - duration_penalty
    )

    return score

def generate_schedule():

    tasks = get_tasks()
    trains = get_trains()

    groups = build_task_groups(tasks)

    schedule = []

    for group in groups:

        # Skip groups with resource conflicts
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

        start_km, end_km = \
            calculate_block_location(group)

        schedule.append({
            "tasks": group,
            "start_km": start_km,
            "end_km": end_km,
            "start_time": start_time,
            "end_time": end_time,
            "score": best_score
        })

    return schedule

def minutes_to_time(minutes):

    hours = minutes // 60
    mins = minutes % 60

    return f"{hours:02d}:{mins:02d}"


def display_schedule(schedule):

    print("\n")
    print("=" * 60)
    print("          AUTOMATIC BLOCK PLAN")
    print("=" * 60)

    for index, block in enumerate(schedule, start=1):

        print(f"\nBLOCK #{index}")

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

def update_train_delay(train_number, delay_minutes):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE trains

        SET
            delay_minutes = ?,
            status = 'DELAYED'

        WHERE train_number = ?
    """, (delay_minutes, train_number))

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
# Weekly / Monthly Planning Layer
# ============================================================

from datetime import date, timedelta
import copy


def get_horizon_days(horizon):

    horizon = horizon.lower()

    if horizon == "weekly":
        return 7

    elif horizon == "monthly":
        return 30

    else:
        raise ValueError(
            "Horizon must be either 'weekly' or 'monthly'."
        )


def blocks_overlap(block1, block2):

    # Check whether the two blocks overlap geographically.
    location_overlap = ranges_overlap(

        block1["start_km"],
        block1["end_km"],

        block2["start_km"],
        block2["end_km"]
    )

    # Check whether the two blocks overlap in time.
    time_overlap = ranges_overlap(

        block1["start_time"],
        block1["end_time"],

        block2["start_time"],
        block2["end_time"]
    )

    return location_overlap and time_overlap


def assign_blocks_to_days(schedule, horizon_days):

    """
    Distributes generated maintenance blocks across
    the selected planning horizon.

    High-priority blocks are scheduled earlier.
    """

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

    start_date = date.today()

    daily_blocks = {}

    for day_offset in range(horizon_days):

        plan_date = start_date + timedelta(days=day_offset)

        daily_blocks[plan_date.isoformat()] = []

    final_plan = []

    for block in sorted_schedule:

        assigned = False

        # Try every day in the planning horizon.
        for day_offset in range(horizon_days):

            plan_date = (
                start_date +
                timedelta(days=day_offset)
            ).isoformat()

            existing_blocks = daily_blocks[plan_date]

            conflict_found = False

            for existing_block in existing_blocks:

                if blocks_overlap(
                    block,
                    existing_block
                ):

                    conflict_found = True
                    break

            # If no conflicting maintenance block exists,
            # assign the block to this date.
            if not conflict_found:

                new_block = copy.deepcopy(block)

                new_block["plan_date"] = plan_date

                new_block["block_id"] = (
                    f"BLK-{len(final_plan) + 1:03d}"
                )

                daily_blocks[plan_date].append(
                    new_block
                )

                final_plan.append(
                    new_block
                )

                assigned = True

                break

        # If the horizon is full, keep the block as unscheduled.
        if not assigned:

            new_block = copy.deepcopy(block)

            new_block["plan_date"] = "UNSCHEDULED"

            new_block["block_id"] = (
                f"BLK-{len(final_plan) + 1:03d}"
            )

            new_block["status"] = "UNSCHEDULED"

            final_plan.append(
                new_block
            )

    return final_plan


def generate_full_plan(horizon="weekly"):

    """
    Generates the optimized maintenance Plan A.

    horizon:
        'weekly'  -> 7 days
        'monthly' -> 30 days
    """

    horizon_days = get_horizon_days(
        horizon
    )

    # Reuse our existing scheduling engine.
    base_schedule = generate_schedule()

    if not base_schedule:

        return []

    full_plan = assign_blocks_to_days(

        base_schedule,

        horizon_days
    )

    # Add metadata to every block.
    for block in full_plan:

        departments = sorted({

            task["department_name"]

            for task in block["tasks"]
        })

        block["departments"] = departments

        block["task_count"] = len(
            block["tasks"]
        )

        block["total_priority"] = sum(

            task["priority"]

            for task in block["tasks"]
        )

        block["duration_minutes"] = (

            block["end_time"] -
            block["start_time"]
        )

        if "status" not in block:

            block["status"] = "SCHEDULED"

    return full_plan


# ============================================================
# WHAT-IF / PLAN B SIMULATOR
# ============================================================

def apply_weather_impact(
    schedule,
    weather_condition
):

    """
    Simulates the effect of bad weather on
    maintenance block duration.

    This does NOT change the database.
    """

    weather_condition = (
        weather_condition or "Normal"
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

            new_block["end_time"] -

            new_block["start_time"]
        )

        new_duration = int(
            original_duration * multiplier
        )

        new_block["end_time"] = (

            new_block["start_time"] +

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
    Creates a simulated Plan B by shifting
    maintenance blocks when a hypothetical
    train delay affects operations.

    No database values are changed.
    """

    modified_schedule = []

    for block in schedule:

        new_block = copy.deepcopy(block)

        # Simple prototype simulation:
        # delayed operations reduce the available
        # maintenance window, so affected blocks
        # are shifted later.

        if delay_minutes > 0:

            new_block["start_time"] += delay_minutes

            new_block["end_time"] += delay_minutes

        new_block["simulated_delay"] = (
            delay_minutes
        )

        modified_schedule.append(
            new_block
        )

    return modified_schedule


def generate_what_if_plan(

    horizon="weekly",

    delay_minutes=0,

    weather_condition="Normal"

):

    """
    Generates Plan B without modifying
    the database or the original Plan A.
    """

    # Generate the original optimized plan.
    plan_b = generate_full_plan(
        horizon
    )

    if not plan_b:

        return []

    # Apply hypothetical weather impact.
    plan_b = apply_weather_impact(

        plan_b,

        weather_condition
    )

    # Apply hypothetical delay impact.
    plan_b = apply_delay_impact(

        plan_b,

        delay_minutes
    )

    # Recalculate metadata after simulation.
    for block in plan_b:

        block["duration_minutes"] = (

            block["end_time"] -

            block["start_time"]
        )

        block["plan_type"] = "PLAN B"

    return plan_b


# ============================================================
# PLAN SUMMARY
# ============================================================

def get_plan_summary(plan):

    """
    Returns useful metrics for Plan A / Plan B.
    """

    if not plan:

        return {

            "total_blocks": 0,

            "total_tasks": 0,

            "total_block_minutes": 0,

            "average_score": 0

        }

    total_blocks = len(plan)

    total_tasks = sum(

        len(block["tasks"])

        for block in plan
    )

    total_block_minutes = sum(

        block["end_time"] -

        block["start_time"]

        for block in plan
    )

    average_score = sum(

        block["score"]

        for block in plan

    ) / total_blocks

    return {

        "total_blocks": total_blocks,

        "total_tasks": total_tasks,

        "total_block_minutes": total_block_minutes,

        "average_score": average_score

    }

if __name__ == "__main__":

    schedule = generate_schedule()

    display_schedule(schedule)
