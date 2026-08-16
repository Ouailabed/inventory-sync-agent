"""Start all three warehouse services. Ctrl-C stops them all.

Each one can also be run on its own:

    cd warehouses
    python -m uvicorn warehouse_a:app --port 8001
"""

import os
import subprocess
import sys

WAREHOUSES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "warehouses")

SERVICES = [
    ("warehouse_a", 8001),
    ("warehouse_b", 8002),
    ("warehouse_c", 8003),
]


def main():
    processes = []
    for module_name, port in SERVICES:
        print(f"starting {module_name} on port {port}")
        processes.append(
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", f"{module_name}:app", "--port", str(port)],
                cwd=WAREHOUSES_DIR,
            )
        )

    print("\nall three warehouses running. ctrl-c to stop.\n")
    try:
        for process in processes:
            process.wait()
    except KeyboardInterrupt:
        print("\nstopping warehouses...")
        for process in processes:
            process.terminate()
        for process in processes:
            process.wait()


if __name__ == "__main__":
    main()
