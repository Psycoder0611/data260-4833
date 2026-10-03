import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError


# ---------------------------------------------------------
# RETRY POLICY
# ---------------------------------------------------------

def run_with_retry(
    operation,
    max_attempts=3,
    timeout_seconds=2.0,
    base_delay=0.1
):
    """
    Run an operation with:
    - per-attempt timeout
    - bounded retries
    - exponential backoff

    Backoff:
        attempt 1 -> 0.1 sec
        attempt 2 -> 0.2 sec
    """

    last_error = None

    for attempt in range(1, max_attempts + 1):

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(operation)

                result = future.result(
                    timeout=timeout_seconds
                )

            return {
                "ok": True,
                "data": result,
                "error": None,
                "attempts": attempt,
            }

        except TimeoutError:
            last_error = (
                f"operation timed out after "
                f"{timeout_seconds} seconds"
            )

        except Exception as exc:
            last_error = str(exc)

        # Retry only if attempts remain.
        if attempt < max_attempts:
            delay = base_delay * (2 ** (attempt - 1))

            time.sleep(delay)

    return {
        "ok": False,
        "data": None,
        "error": last_error,
        "attempts": max_attempts,
    }