"""HW6 Part 4: check that a function follows the coding rules written in AGENT.md.

Default target: count_active_lines() in hw6/file_memory.py.
Example:  python check_agentmd_compliance.py --function count_active_lines
"""
import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
SNAKE_CASE = re.compile(r"^[a-z_][a-z0-9_]*$")
SECRET_NAME = re.compile(r"(password|passwd|secret|api_?key|token)", re.IGNORECASE)
CATEGORIES = ["Project description", "Technology stack", "Coding conventions", "Testing approach", "Prohibited actions"]


def find_function(tree: ast.AST, name: str) -> Optional[ast.FunctionDef]:
    """Return the function definition called name, or None."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def check_function(node: ast.FunctionDef, source: str, test_text: str) -> List[Tuple[str, bool, str]]:
    """Run each AGENT.md coding rule against one function and return (rule, passed, detail)."""
    results: List[Tuple[str, bool, str]] = []
    results.append(("Function name is snake_case", bool(SNAKE_CASE.match(node.name)), node.name))

    results.append(("Function has a docstring", ast.get_docstring(node) is not None, "docstring found" if ast.get_docstring(node) else "missing"))

    args = [arg for arg in node.args.args + node.args.kwonlyargs if arg.arg not in ("self", "cls")]
    missing = [arg.arg for arg in args if arg.annotation is None]
    results.append(("All parameters have type hints", not missing, "all annotated" if not missing else f"missing: {missing}"))
    results.append(("Return value has a type hint", node.returns is not None, ast.unparse(node.returns) if node.returns else "missing"))

    prints = [
        call for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "print"
    ]
    results.append(("No print() inside the function", not prints, "no print calls" if not prints else f"{len(prints)} print call(s)"))

    secrets = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assign) and isinstance(child.value, ast.Constant) and isinstance(child.value.value, str):
            for target in child.targets:
                if isinstance(target, ast.Name) and SECRET_NAME.search(target.id) and child.value.value:
                    secrets.append(target.id)
    results.append(("No hard-coded secrets", not secrets, "none found" if not secrets else f"found: {secrets}"))

    has_test = re.search(rf"def test_\w+\(.*\):[\s\S]*?{re.escape(node.name)}", test_text) is not None
    results.append(("A pytest test uses the function", has_test, "test found in test_hw6_offline.py" if has_test else "no test"))
    return results


def check_agent_file(agent_text: str) -> Dict[str, int]:
    """Count instruction bullets under each AGENT.md category heading."""
    counts: Dict[str, int] = {}
    heading = None
    for line in agent_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip()
        elif stripped.startswith("- ") and heading in CATEGORIES:
            counts[heading] = counts.get(heading, 0) + 1
    return counts


def main() -> int:
    """Print a pass/fail report and return 0 when everything passes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default="hw6/file_memory.py")
    parser.add_argument("--function", default="count_active_lines")
    args = parser.parse_args()

    counts = check_agent_file((ROOT / "AGENT.md").read_text(encoding="utf-8"))
    total = sum(counts.values())
    agent_ok = total >= 5 and len(counts) >= 3
    print("AGENT.md check")
    print(f"  instructions: {total} (need 5+) | categories: {len(counts)} (need 3+)")
    for name, count in counts.items():
        print(f"    - {name}: {count}")
    print(f"  RESULT: {'PASS' if agent_ok else 'FAIL'}\n")

    source = (ROOT / args.file).read_text(encoding="utf-8")
    node = find_function(ast.parse(source), args.function)
    if node is None:
        print(f"Function {args.function} not found in {args.file}")
        return 1
    test_text = (ROOT / "test_hw6_offline.py").read_text(encoding="utf-8")
    print(f"Function check: {args.function}() in {args.file}")
    results = check_function(node, source, test_text)
    for rule, passed, detail in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {rule} - {detail}")
    function_ok = all(passed for _, passed, _ in results)
    print(f"  RESULT: {'PASS' if function_ok else 'FAIL'}")
    return 0 if (agent_ok and function_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
