VALID_CHECK_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN"})


def calculate_overall_status(check_statuses) -> str:
    statuses = tuple(check_statuses)

    if not statuses:
        raise ValueError("At least one check status is required.")

    invalid_statuses = set(statuses) - VALID_CHECK_STATUSES
    if invalid_statuses:
        invalid = ", ".join(sorted(invalid_statuses))
        raise ValueError(f"Invalid check status: {invalid}")

    if "FAIL" in statuses:
        return "INSECURE"

    if "UNKNOWN" in statuses:
        return "INCOMPLETE"

    return "SECURE"
