from retry_utils import run_with_retry


# ---------------------------------------------------------
# CASE 1
# Success on first attempt
# ---------------------------------------------------------

def first_attempt_success():
    return "database operation completed"


# ---------------------------------------------------------
# CASE 2
# First attempt fails, retry succeeds
# ---------------------------------------------------------

retry_counter = {
    "count": 0
}


def retry_then_success():
    retry_counter["count"] += 1

    if retry_counter["count"] == 1:
        raise RuntimeError(
            "simulated temporary storage failure"
        )

    return "database operation completed after retry"


# ---------------------------------------------------------
# CASE 3
# All retry attempts fail
# ---------------------------------------------------------

def all_attempts_fail():
    raise RuntimeError(
        "simulated persistent storage failure"
    )


# ---------------------------------------------------------
# RUN DEMONSTRATIONS
# ---------------------------------------------------------

print("=" * 65)
print("CASE 1 - SUCCESS ON FIRST ATTEMPT")
print("=" * 65)

result_1 = run_with_retry(
    first_attempt_success
)

print(result_1)


print("\n" + "=" * 65)
print("CASE 2 - FIRST FAILURE, THEN RETRY SUCCESS")
print("=" * 65)

result_2 = run_with_retry(
    retry_then_success
)

print(result_2)


print("\n" + "=" * 65)
print("CASE 3 - ALL RETRIES FAIL CLEANLY")
print("=" * 65)

result_3 = run_with_retry(
    all_attempts_fail
)

print(result_3)