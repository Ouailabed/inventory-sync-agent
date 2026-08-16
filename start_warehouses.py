"""Start all three warehouse services at once.

Purely a convenience — each service is an ordinary uvicorn app and can be run
by hand in its own terminal if you'd rather watch them separately:

    cd warehouses
    python -m uvicorn warehouse_a:app --port 8001
    python -m uvicorn warehouse_b:app --port 8002
    python -m uvicorn warehouse_c:app --port 8003

Ctrl-C here stops all three.
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
