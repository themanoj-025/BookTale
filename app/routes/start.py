"""
start.py -- Library Management System Launcher
Start the web server, CLI, or both with one click.
"""

import os
import socket
import subprocess  # nosec B404 (launcher uses list-form Popen with constant args)
import sys
import time
import webbrowser
import contextlib
import logging

logger = logging.getLogger(__name__)


# Ensure we're in the project directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(BASE_DIR)

# -- Import config -- respects .env settings ----------------------
sys.path.insert(0, BASE_DIR)
try:
    from app.config.settings import Config

    FLASK_HOST = Config.FLASK_HOST
    FLASK_PORT = Config.FLASK_PORT
except ImportError:
    # Fallback defaults if config.py has issues
    FLASK_HOST = "0.0.0.0"  # nosec B104 (dev launcher fallback; prod binds via gunicorn)
    FLASK_PORT = 5000

FLASK_URL = f"http://localhost:{FLASK_PORT}"


def safe_print(text) -> None:
    """Print text, gracefully handling UnicodeEncodeError on Windows cp1252."""
    try:
        logger.info("%s", text)
    except UnicodeEncodeError:
        # Fallback: strip non-ASCII characters
        logger.error("%s", text.encode("ascii", errors="replace").decode("ascii"))


def print_banner() -> dict:
    """Display a clean launch banner."""
    logger.info("""
  +=============================================+
  |     Library Management System v3.0          |
  |     Python + Flask + Bootstrap 5            |
  +=============================================+
""")


def launch_web() -> None:
    """Launch the Flask web server in a subprocess.

    NOTE: stdout/stderr are NOT piped to avoid pipe-buffer deadlocks
    that occur when Flask/SocketIO writes verbose debug output.
    Output goes directly to the terminal.
    """
    logger.info(f"  [NET] Starting web server at http://0.0.0.0:{FLASK_PORT}...")
    logger.info("  [LOCK] Admin login: ADMIN001 (password printed once on first boot)")
    logger.info("  [HINT] Press Ctrl+K to search books anywhere")
    print()

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(  # nosec B603 (constant argv list, no shell)
        [sys.executable, "web_app.py"],
        cwd=BASE_DIR,
        env=env,
        # No PIPE -- output goes directly to terminal to prevent deadlocks
    )
    return process


def launch_cli() -> None:
    """Launch the CLI application in a subprocess."""
    logger.info("  [CLI] Starting CLI interface...")
    print()

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(  # nosec B603 (constant argv list, no shell)
        [sys.executable, "main.py"],
        cwd=BASE_DIR,
        env=env,
    )
    return process


def show_menu() -> None:
    """Display the launcher menu."""
    print_banner()
    logger.info("  Select launch mode:\n")
    logger.info("  1. [WEB] Web Dashboard only  (http://localhost:5000)")
    logger.info("  2. [CLI] CLI only             (Terminal interface)")
    logger.info("  3. [WEB+CLI] Both            (Web + CLI side-by-side)")
    logger.info("  4. [X] Quit")
    print()

    while True:
        choice = input("  Enter choice [1]: ").strip() or "1"
        if choice in ("1", "2", "3", "4"):
            return choice
        logger.info("  [X] Invalid choice. Try 1-4.")


def main() -> None:
    """Main entry point -- show menu and launch."""
    if len(sys.argv) > 1:
        # CLI args: --web, --cli, --both
        mode = sys.argv[1].lstrip("-").lower()
        if mode in ("web", "w"):
            choice = "1"
        elif mode in ("cli", "c"):
            choice = "2"
        elif mode in ("both", "b", "all", "a"):
            choice = "3"
        else:
            logger.info(f"  [X] Unknown option: {sys.argv[1]}")
            logger.info("  Usage: python start.py [--web|--cli|--both]")
            sys.exit(1)
    else:
        choice = show_menu()

    if choice == "4":
        logger.info("  [OK] Goodbye!")
        return

    print_banner()
    processes = []

    if choice in ("1", "3"):
        web_proc = launch_web()
        processes.append(("Web", web_proc))
        # Health check: wait for port to be ready before opening browser
        logger.info(f"  [WAIT] Waiting for server on port {FLASK_PORT}...")
        port_ready = False
        for _attempt in range(30):  # Up to 60 seconds
            time.sleep(2)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            try:
                sock.connect(("127.0.0.1", FLASK_PORT))
                sock.close()
                port_ready = True
                break
            except (OSError, ConnectionRefusedError, TimeoutError):
                sock.close()
            # Check if process crashed
            if web_proc.poll() is not None:
                print()
                logger.info(f"  [X] Server process exited early (code {web_proc.returncode}).")
                logger.error("     Run 'python web_app.py' directly to see error details.")
                print()
                return  # Exit without suggesting browser
            logger.info(".")

        if port_ready:
            logger.info(" READY!")
            logger.info(f"  [WEB] Opening browser at {FLASK_URL}")
            with contextlib.suppress(Exception):
                webbrowser.open(FLASK_URL)
        else:
            print()
            if web_proc.poll() is None:
                logger.info(f"  [!] Server is running but port {FLASK_PORT} is not responding yet.")
            logger.info(f"  [WEB] Open {FLASK_URL} manually in your browser.")
            logger.info("  [AUTH] Admin login: ADMIN001 (password printed once on first boot)")

    if choice in ("2", "3"):
        cli_proc = launch_cli()
        processes.append(("CLI", cli_proc))

    if not processes:
        return

    print()
    logger.info("  --------------------------------------------")
    logger.info("  [OK] Library Management System is running!")
    for name, proc in processes:
        status = "running" if proc.poll() is None else f"exited ({proc.returncode})"
        logger.info(f"     {name}: {status}")
    print()
    logger.info("  [WEB] http://localhost:5000")
    logger.info("  [AUTH] Admin login: ADMIN001 (password printed once on first boot)")
    logger.info("  [HINT] Shortcut: Ctrl+K to search books")
    print()
    logger.info("  Press any key to stop the server, or Ctrl+C to quit.")
    logger.info("  --------------------------------------------")

    # Wait for keypress to shut down
    def shutdown_all() -> None:
        """Terminate all running processes cleanly."""
        print()
        logger.info("  [STOP] Shutting down...")
        for n, proc in processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                logger.info(f"     {n}: stopped")
        logger.info("  [OK] All services stopped. Goodbye! [OK]")

    try:
        if sys.platform == "win32":
            import msvcrt

            # Use msvcrt for non-blocking key detection on Windows
            while True:
                if msvcrt.kbhit():
                    msvcrt.getch()  # consume the key
                    shutdown_all()
                    return
                # Check if any process exited on its own
                all_dead = True
                for _n, proc in processes:
                    if proc.poll() is None:
                        all_dead = False
                        break
                if all_dead:
                    logger.info("\n  [i]  All processes have exited.")
                    return
                time.sleep(0.2)
        else:
            # Non-Windows: fall back to stdin read with timeout
            import select

            while True:
                if select.select([sys.stdin], [], [], 0.2)[0]:
                    sys.stdin.read(1)
                    shutdown_all()
                    return
                all_dead = True
                for _n, proc in processes:
                    if proc.poll() is None:
                        all_dead = False
                        break
                if all_dead:
                    logger.info("\n  [i]  All processes have exited.")
                    return
    except KeyboardInterrupt:
        shutdown_all()
    except ImportError:
        # Fallback if msvcrt/select not available
        try:
            for _name, proc in processes:
                proc.wait()
        except KeyboardInterrupt:
            shutdown_all()


if __name__ == "__main__":
    main()
