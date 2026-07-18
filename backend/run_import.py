"""
Import runner: loads password from gcloud secret, starts proxy inline via
subprocess, waits for it to be ready, runs the import, then stops the proxy.
Never prints the password.
"""
import os
import subprocess
import sys
import time
import socket
from pathlib import Path


def _load_password_from_gcloud() -> str:
    import shutil
    gcloud_cmd = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not gcloud_cmd:
        # Try the known gcloud SDK location on Windows
        gcloud_cmd = r"C:\Users\sulta\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    result = subprocess.run(
        [
            gcloud_cmd,
            "secrets", "versions", "access", "latest",
            "--secret=catalog-db-password-staging",
            "--project=pc-recomendation-project",
        ],
        capture_output=True,
        text=True,
        check=True,
        shell=True,
    )
    return result.stdout.strip()


def _proxy_port_open(host="127.0.0.1", port=5433, timeout=1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def main():
    proxy_exe = str(Path(__file__).parent.parent / "cloud-sql-proxy.exe")

    # Start proxy
    print("Starting Cloud SQL Auth Proxy on 127.0.0.1:5433 ...")
    proxy = subprocess.Popen(
        [
            proxy_exe,
            "--port=5433",
            "--gcloud-auth",
            "pc-recomendation-project:me-central1:catalog-postgres-staging",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait up to 20s for proxy to be ready
    for i in range(20):
        time.sleep(1)
        if _proxy_port_open():
            print(f"Proxy ready after {i+1}s")
            break
    else:
        proxy.terminate()
        print("ERROR: Proxy did not become ready in 20 seconds.")
        return 1

    try:
        # Load password
        pw = _load_password_from_gcloud()

        os.environ["CATALOG_DB_PASSWORD"] = pw
        os.environ["CATALOG_DB_HOST"] = "127.0.0.1"
        os.environ["CATALOG_DB_PORT"] = "5433"
        os.environ["CATALOG_DB_NAME"] = "catalog"
        os.environ["CATALOG_DB_USER"] = "sultansotb"
        os.environ["CATALOG_BUILDCORES_IMPORT_ENABLED"] = "true"

        from app.catalog.buildcores_import_cli import main as cli_main
        return cli_main(sys.argv[1:])
    finally:
        print("Stopping proxy...")
        proxy.terminate()
        try:
            proxy.wait(timeout=5)
        except Exception:
            proxy.kill()


if __name__ == "__main__":
    sys.exit(main())
