import json
import subprocess
from pathlib import Path


OUTPUT_FILE = Path("reports/hw01/verification.json")


def check_file(path):
    """
    Check whether a required file exists.
    """
    return Path(path).exists()


def run_command(command):
    """
    Run a command and return whether it succeeded.
    """
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    return {
        "success": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def main():
    checks = {}

    # Check important assignment files
    checks["index_html_exists"] = check_file("index.html")
    checks["script_js_exists"] = check_file("script.js")
    checks["dockerfile_exists"] = check_file("Dockerfile")
    checks["agents_demo_exists"] = check_file("agents_demo.py")
    checks["hw1_client_exists"] = check_file("hw1_client.py")
    checks["agent_md_exists"] = check_file("AGENT.md")
    checks["model_client_exists"] = check_file("src/model_client.py")
    checks["domain_schema_exists"] = check_file(
        "reports/hw01/DOMAIN_SCHEMA.md"
    )
    checks["metrics_exists"] = check_file(
        "reports/hw01/METRICS.md"
    )
    checks["ai_use_exists"] = check_file(
        "reports/hw01/AI_USE.md"
    )
    checks["nondeterminism_input_exists"] = check_file(
        "reports/hw01/cases/nondeterminism_input.json"
    )

    # Check the number of raw experiment files
    temp_07_files = list(
        Path("reports/hw01/raw/t0.7").glob("run_*.json")
    )

    temp_00_files = list(
        Path("reports/hw01/raw/t0.0").glob("run_*.json")
    )

    checks["temperature_0_7_run_count"] = len(temp_07_files)
    checks["temperature_0_0_run_count"] = len(temp_00_files)

    checks["temperature_0_7_has_20_runs"] = (
        len(temp_07_files) == 20
    )

    checks["temperature_0_0_has_20_runs"] = (
        len(temp_00_files) == 20
    )

    # Verify Python imports used by the project
    import_check = run_command([
        "python",
        "-c",
        (
            "import langchain_ollama; "
            "import langchain_core; "
            "print('Imports OK')"
        ),
    ])

    checks["python_import_check"] = import_check

    # Check whether agents_demo.py can load successfully
    agent_help_check = run_command([
        "python",
        "agents_demo.py",
        "--help",
    ])

    checks["agents_demo_help_check"] = {
        "success": agent_help_check["success"]
    }

    # Final overall result
    boolean_checks = [
        value
        for value in checks.values()
        if isinstance(value, bool)
    ]

    checks["overall_pass"] = all(boolean_checks)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            checks,
            file,
            indent=2
        )

    print(
        json.dumps(
            checks,
            indent=2
        )
    )

    print(
        f"\nVerification saved to: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()