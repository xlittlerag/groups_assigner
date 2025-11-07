import json
import csv
import random
import io
import hashlib
import time
from datetime import datetime
from collections import defaultdict, Counter
from flask import Flask, request, jsonify, render_template, send_file

# Create the app with explicit template and static folders
app = Flask(__name__, template_folder="templates", static_folder="static")

# In-memory storage for the API
competitors_data = {}
groups_data = {}
fixed_positions_data = {}
assignment_results = {}


class Competitor:
    def __init__(self, id, name, country, seed_id=None):
        self.id = id
        self.name = name
        self.country = country
        self.seed_id = seed_id


class Group:
    def __init__(self, id, capacity, label=None):
        self.id = str(id)  # Ensure ID is always a string
        self.capacity = capacity
        self.label = label
        self.positions = ["a", "b", "c", "d"][:capacity]
        self.assigned_positions = {}  # position -> competitor_id


class Assignment:
    def __init__(self):
        self.assignments = {}  # (group_id, position) -> competitor_id
        self.collision_count = 0
        self.per_country_collisions = defaultdict(int)
        self.random_seed = None


def validate_inputs(competitors, groups, fixed_positions):
    # Validate that total competitors match total group capacity
    total_capacity = sum(g.capacity for g in groups.values())
    if len(competitors) != total_capacity:
        return (
            False,
            f"Total competitors ({len(competitors)}) does not match total group capacity ({total_capacity}).",
        )

    # Validate fixed positions
    for comp_name, (group_id, position) in fixed_positions.items():
        if comp_name not in competitors:
            return False, f"Fixed position: competitor '{comp_name}' does not exist."

        # Convert group_id to string for comparison
        group_id_str = str(group_id)

        if group_id_str not in groups:
            return (
                False,
                f"Fixed position: competitor '{comp_name}' refers to non-existent group {group_id}.",
            )
        if position not in groups[group_id_str].positions:
            return (
                False,
                f"Invalid position letter '{position}' for group {group_id} with capacity {groups[group_id_str].capacity}.",
            )

    # Check for duplicate fixed positions
    position_assignments = defaultdict(list)
    for comp_name, (group_id, position) in fixed_positions.items():
        # Convert group_id to string for consistency
        position_assignments[(str(group_id), position)].append(comp_name)

    for (group_id, position), comp_list in position_assignments.items():
        if len(comp_list) > 1:
            return (
                False,
                f"Duplicate fixed position: group {group_id} position {position} assigned to multiple competitors: {', '.join(comp_list)}.",
            )

    return True, ""


def calculate_collisions(assignment, competitors, groups):
    collision_count = 0
    per_country_collisions = defaultdict(int)

    # Group assignments by group
    group_assignments = defaultdict(list)
    for (group_id, position), comp_id in assignment.items():
        group_assignments[group_id].append(comp_id)

    # Count collisions within each group
    for group_id, comp_ids in group_assignments.items():
        # Count countries in this group
        country_counts = Counter(competitors[comp_id].country for comp_id in comp_ids)

        # For each country with more than 1 competitor, add to collision count
        for country, count in country_counts.items():
            if count > 1:
                # Number of pairs is n choose 2
                pairs = count * (count - 1) // 2
                collision_count += pairs
                per_country_collisions[country] += pairs

    return collision_count, per_country_collisions


def systematic_country_assignment(
    competitors, groups, fixed_positions, random_seed=None
):
    """
    Systematic algorithm that distributes countries to minimize collisions:
    1. Process countries in descending order of size
    2. For each country, distribute its competitors to groups with the fewest competitors from that country
    3. Shuffle positions within each group to ensure fairness
    """
    if random_seed is not None:
        random.seed(random_seed)

    assignment = Assignment()
    assignment.random_seed = random_seed

    # First, place fixed positions
    for comp_name, (group_id, position) in fixed_positions.items():
        # Convert group_id to string for consistency
        group_id_str = str(group_id)
        assignment.assignments[(group_id_str, position)] = comp_name
        groups[group_id_str].assigned_positions[position] = comp_name

    # Get remaining competitors
    remaining_competitors = [
        comp_name for comp_name in competitors if comp_name not in fixed_positions
    ]

    # Group competitors by country
    country_groups = defaultdict(list)
    for comp_name in remaining_competitors:
        country_groups[competitors[comp_name].country].append(comp_name)

    # Sort countries by number of competitors (descending)
    sorted_countries = sorted(
        country_groups.items(), key=lambda x: len(x[1]), reverse=True
    )

    # Track how many competitors from each country are in each group
    country_group_counts = defaultdict(lambda: defaultdict(int))

    # Initialize with fixed positions
    for comp_name, (group_id, position) in fixed_positions.items():
        country = competitors[comp_name].country
        # Convert group_id to string for consistency
        group_id_str = str(group_id)
        country_group_counts[country][group_id_str] += 1

    # For each country, distribute its competitors
    for country, comp_names in sorted_countries:
        # Shuffle the competitors within this country for randomness
        random.shuffle(comp_names)

        # For each competitor, find the best group
        for comp_name in comp_names:
            # Find groups with the fewest competitors from this country
            min_count = float("inf")
            best_groups = []

            for group_id, group in groups.items():
                # Count how many positions are still available in this group
                available_positions = sum(
                    1 for pos in group.positions if pos not in group.assigned_positions
                )

                if available_positions > 0:
                    count = country_group_counts[country][group_id]
                    if count < min_count:
                        min_count = count
                        best_groups = [group_id]
                    elif count == min_count:
                        best_groups.append(group_id)

            # Randomly select from the best groups
            if best_groups:
                selected_group_id = random.choice(best_groups)

                # Find an available position in this group
                available_positions = [
                    pos
                    for pos in groups[selected_group_id].positions
                    if pos not in groups[selected_group_id].assigned_positions
                ]

                if available_positions:
                    selected_position = random.choice(available_positions)

                    # Assign the competitor
                    assignment.assignments[(selected_group_id, selected_position)] = (
                        comp_name
                    )
                    groups[selected_group_id].assigned_positions[
                        selected_position
                    ] = comp_name
                    country_group_counts[country][selected_group_id] += 1

    # Now shuffle positions within each group (except fixed positions)
    # Create a set of fixed position tuples for easy lookup
    fixed_position_set = set((str(gid), pos) for gid, pos in fixed_positions.values())

    for group_id, group in groups.items():
        # Get all positions in this group
        group_positions = [(group_id, pos) for pos in group.positions]

        # Separate fixed and non-fixed positions
        fixed_positions_in_group = []
        non_fixed_positions = []

        for pos in group_positions:
            if pos in fixed_position_set:
                fixed_positions_in_group.append(pos)
            else:
                non_fixed_positions.append(pos)

        # If there are non-fixed positions, shuffle the competitors among them
        if non_fixed_positions:
            # Get the competitors at these positions
            competitors_at_positions = []
            for pos in non_fixed_positions:
                if pos in assignment.assignments:
                    competitors_at_positions.append(assignment.assignments[pos])

            # Only shuffle if we have the right number of competitors
            if len(competitors_at_positions) == len(non_fixed_positions):
                # Shuffle the competitors
                random.shuffle(competitors_at_positions)

                # Reassign them
                for i, pos in enumerate(non_fixed_positions):
                    assignment.assignments[pos] = competitors_at_positions[i]

    # Calculate final collisions
    assignment.collision_count, assignment.per_country_collisions = (
        calculate_collisions(assignment.assignments, competitors, groups)
    )

    return assignment


def optimized_systematic_assignment(
    competitors, groups, fixed_positions, random_seed=None, max_time_seconds=10
):
    """
    Optimized algorithm that tries multiple systematic assignments with different random seeds.
    """
    if random_seed is not None:
        random.seed(random_seed)

    best_assignment = None
    best_collision_count = float("inf")

    # Start time for timeout
    start_time = time.time()

    # Try multiple random permutations
    max_attempts = (
        100  # Fewer attempts needed since the systematic approach is more effective
    )
    for attempt in range(max_attempts):
        # Check if we've exceeded the time limit
        if time.time() - start_time > max_time_seconds:
            break

        # Create fresh copies of groups for each attempt
        fresh_groups = {}
        for group_id, group in groups.items():
            fresh_groups[group_id] = Group(group.id, group.capacity, group.label)

        # Generate a new assignment with a different seed
        current_seed = random_seed + attempt if random_seed is not None else None
        current_assignment = systematic_country_assignment(
            competitors, fresh_groups, fixed_positions, current_seed
        )

        # Update best assignment if this is better
        if current_assignment.collision_count < best_collision_count:
            best_assignment = current_assignment
            best_collision_count = current_assignment.collision_count

            # If we found a perfect assignment (no collisions), we can stop
            if current_assignment.collision_count == 0:
                break

    return best_assignment


def improved_assign_competitors(
    competitors,
    groups,
    fixed_positions,
    random_seed=None,
    minimization=True,
    max_time_seconds=10,
):
    """
    Improved algorithm that uses systematic country distribution with optimization.
    """
    if random_seed is not None:
        random.seed(random_seed)

    # If minimization is off, just use a single systematic assignment
    if not minimization:
        return systematic_country_assignment(
            competitors, groups, fixed_positions, random_seed
        )

    # Otherwise, try multiple assignments to find the best one
    return optimized_systematic_assignment(
        competitors, groups, fixed_positions, random_seed, max_time_seconds
    )


def format_assignment_output(assignment, competitors, groups):
    output = []
    for (group_id, position), comp_name in sorted(assignment.assignments.items()):
        output.append(
            {
                "group_id": group_id,
                "position": position,
                # "competitor_id": comp_name,
                "name": competitors[comp_name].name,
                "country": competitors[comp_name].country,
            }
        )
    return output


def format_summary_output(assignment):
    return {
        "total_collisions": assignment.collision_count,
        "per_country_collisions": dict(assignment.per_country_collisions),
        "random_seed": assignment.random_seed,
    }


# API endpoints
@app.route("/api/competitors", methods=["POST"])
def upload_competitors():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        competitors = {}
        for comp in data:
            name = comp.get("name")
            if not name:
                return jsonify({"error": "Competitor missing name"}), 400

            # Use name as the key
            competitors[name] = Competitor(
                name, name, comp.get("country", ""), comp.get("seed_id")
            )

        data_hash = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()
        competitors_data[data_hash] = competitors
        return jsonify(
            {"status": "success", "count": len(competitors), "hash": data_hash}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups", methods=["POST"])
def upload_groups():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        groups = {}
        for grp in data:
            grp_id = grp.get("id")
            if not grp_id:
                return jsonify({"error": "Group missing ID"}), 400

            capacity = grp.get("capacity")
            if capacity not in [3, 4]:
                return (
                    jsonify(
                        {
                            "error": f"Group {grp_id} has invalid capacity {capacity}. Must be 3 or 4."
                        }
                    ),
                    400,
                )

            # Convert group_id to string for consistency
            groups[str(grp_id)] = Group(grp_id, capacity, grp.get("label"))

        data_hash = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()
        groups_data[data_hash] = groups
        return jsonify({"status": "success", "count": len(groups), "hash": data_hash})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fixed", methods=["POST"])
def upload_fixed_positions():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        fixed_positions = {}
        for pos in data:
            comp_name = pos.get("competitor_name")
            group_id = pos.get("group_id")
            position = pos.get("position")

            if not all([comp_name, group_id, position]):
                return jsonify({"error": "Fixed position missing required fields"}), 400

            # Convert group_id to string to ensure consistency
            fixed_positions[comp_name] = (str(group_id), position)

        data_hash = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()
        fixed_positions_data[data_hash] = fixed_positions
        return jsonify(
            {"status": "success", "count": len(fixed_positions), "hash": data_hash}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/draw", methods=["POST"])
def run_draw():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        competitors_hash = data.get("competitors_hash")
        groups_hash = data.get("groups_hash")
        fixed_positions_hash = data.get("fixed_positions_hash")
        random_seed = data.get("random_seed")
        minimization = data.get("minimization", True)
        max_time = data.get("max_time_seconds", 10)

        if not competitors_hash or not groups_hash:
            return jsonify({"error": "Missing competitors or groups hash"}), 400

        if competitors_hash not in competitors_data or groups_hash not in groups_data:
            return jsonify({"error": "Invalid competitors or groups hash"}), 400

        competitors = competitors_data[competitors_hash]
        groups = groups_data[groups_hash]
        fixed_positions = fixed_positions_data.get(fixed_positions_hash, {})

        # Validate inputs
        is_valid, error_msg = validate_inputs(competitors, groups, fixed_positions)
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        # Run assignment with improved algorithm
        assignment = improved_assign_competitors(
            competitors, groups, fixed_positions, random_seed, minimization, max_time
        )

        # Format output
        assignment_output = format_assignment_output(assignment, competitors, groups)
        summary_output = format_summary_output(assignment)

        result_hash = hashlib.md5(
            json.dumps(
                {
                    "competitors_hash": competitors_hash,
                    "groups_hash": groups_hash,
                    "fixed_positions_hash": fixed_positions_hash,
                    "random_seed": random_seed,
                    "minimization": minimization,
                    "max_time_seconds": max_time,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

        assignment_results[result_hash] = {
            "assignment": assignment_output,
            "summary": summary_output,
            "timestamp": datetime.now().isoformat(),
        }

        return jsonify(
            {
                "status": "success",
                "result_hash": result_hash,
                "assignment": assignment_output,
                "summary": summary_output,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/results/<result_hash>", methods=["GET"])
def get_results(result_hash):
    if result_hash not in assignment_results:
        return jsonify({"error": "Result not found"}), 404

    return jsonify(assignment_results[result_hash])


@app.route("/api/results/<result_hash>/export", methods=["GET"])
def export_results(result_hash):
    if result_hash not in assignment_results:
        return jsonify({"error": "Result not found"}), 404

    format_type = request.args.get("format", "json")
    result = assignment_results[result_hash]

    if format_type == "csv":
        # Create CSV for assignment
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Group ID", "Position", "Competitor Name", "Country"])
        for item in result["assignment"]:
            writer.writerow(
                [item["group_id"], item["position"], item["name"], item["country"]]
            )

        # Create a response with the CSV file
        output.seek(0)
        return send_file(
            path_or_file=io.BytesIO(output.getvalue().encode("utf-8")),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"kendo_assignment_{result_hash}.csv",
        )
    else:
        # Return JSON
        return jsonify(result)


@app.route("/api/validate", methods=["POST"])
def validate_inputs_endpoint():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        competitors_hash = data.get("competitors_hash")
        groups_hash = data.get("groups_hash")
        fixed_positions_hash = data.get("fixed_positions_hash")

        if not competitors_hash or not groups_hash:
            return jsonify({"error": "Missing competitors or groups hash"}), 400

        if competitors_hash not in competitors_data or groups_hash not in groups_data:
            return jsonify({"error": "Invalid competitors or groups hash"}), 400

        competitors = competitors_data[competitors_hash]
        groups = groups_data[groups_hash]
        fixed_positions = fixed_positions_data.get(fixed_positions_hash, {})

        # Validate inputs
        is_valid, error_msg = validate_inputs(competitors, groups, fixed_positions)

        return jsonify(
            {
                "status": "success",
                "valid": is_valid,
                "message": error_msg if not is_valid else "Inputs are valid",
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Web UI routes
@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
