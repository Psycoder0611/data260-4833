import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from main import app


HW = 4
SID4 = 4833
SEED = 4833
VERIFY_SEED = 264833

OUTPUT_FILE = Path("reports/hw04/verification.json")


def get_commit_hash():
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        text=True
    ).strip()


def run_checks():
    client = TestClient(app)

    checks = []

    login_response = client.post(
        "/api/login",
        json={
            "email": "admin@example.com",
            "password": "password123"
        }
    )

    checks.append(
        {
            "name": "login_endpoint",
            "passed": login_response.status_code == 200
        }
    )

    naive_response = client.get(
        "/api/hw4/trials/naive",
        params={"page_size": 10}
    )

    checks.append(
        {
            "name": "naive_endpoint_returns_data",
            "passed": (
                naive_response.status_code == 200
                and len(naive_response.json()) == 10
            )
        }
    )

    fixed_response = client.get(
        "/api/hw4/trials/fixed",
        params={"page_size": 10}
    )

    checks.append(
        {
            "name": "fixed_endpoint_returns_data",
            "passed": (
                fixed_response.status_code == 200
                and len(fixed_response.json()) == 10
            )
        }
    )

    checks.append(
        {
            "name": "naive_and_fixed_same_length",
            "passed": (
                naive_response.status_code == 200
                and fixed_response.status_code == 200
                and len(naive_response.json())
                == len(fixed_response.json())
            )
        }
    )

    checks.append(
        {
            "name": "rag_raw_outputs_exist",
            "passed": (
                Path(
                    "reports/hw04/raw/"
                    "rag_retrievals.txt"
                ).exists()
                and Path(
                    "reports/hw04/raw/"
                    "rag_comparison.txt"
                ).exists()
                and Path(
                    "reports/hw04/raw/"
                    "rag_k_sweep.txt"
                ).exists()
            )
        }
    )

    checks.append(
        {
            "name": "nplus1_raw_output_exists",
            "passed": Path(
                "reports/hw04/raw/"
                "nplus1_raw.csv"
            ).exists()
        }
    )

    result = {
        "homework": HW,
        "SID4": SID4,
        "commit_hash": get_commit_hash(),
        "model_configuration": {
            "llm": "qwen3:8b",
            "embedding_model": "nomic-embed-text",
            "vector_store": "FAISS",
            "top_k": 3
        },
        "SEED": SEED,
        "VERIFY_SEED": VERIFY_SEED,
        "checks": checks,
        "all_passed": all(
            check["passed"]
            for check in checks
        )
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            result,
            indent=2
        ),
        encoding="utf-8"
    )

    print(json.dumps(result, indent=2))
    print()
    print(
        f"Saved verification output to "
        f"{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    run_checks()