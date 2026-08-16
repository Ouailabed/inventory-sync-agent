"""Starts the three warehouse services for the test session."""

import os
import socket
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
WAREHOUSES_DIR = os.path.join(HERE, "warehouses")

SERVICES = [
    ("warehouse_a", 8001),
    ("warehouse_b", 8002),
    ("warehouse_c", 8003),
]


def port_is_open(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def wait_for_port(port, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_is_open(port):
            return True
        time.sleep(0.1)
    return False


def start_service(module_name, port):
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", f"{module_name}:app", "--port", str(port)],
        cwd=WAREHOUSES_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not wait_for_port(port):
        process.terminate()
        raise RuntimeError(f"{module_name} never came up on port {port}")
    return process


@pytest.fixture(scope="session", autouse=True)
def warehouse_services():
    processes = []
    for module_name, port in SERVICES:
        if port_is_open(port):
            # already running, leave it alone
            continue
        processes.append(start_service(module_name, port))

    yield

    for process in processes:
        process.terminate()
    for process in processes:
        process.wait()
