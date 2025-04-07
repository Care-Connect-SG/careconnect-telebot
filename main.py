import subprocess
import sys
import time
import signal

processes = []

def run_bot(module_path):
    """Run a bot module as a separate process"""
    print(f"Starting {module_path}...")

    python_executable = sys.executable

    process = subprocess.Popen(
        [python_executable, "-m", module_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    processes.append(process)
    return process

def signal_handler(sig, frame):
    """Handle Ctrl+C and other termination signals"""
    print("\nStopping all bots...")
    for process in processes:
        if process.poll() is None:
            process.terminate()

    time.sleep(1)

    for process in processes:
        if process.poll() is None:
            process.kill()

    print("All bots stopped")
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    assistant_process = run_bot("assistant_bot.main")
    reminders_process = run_bot("reminders_bot.main")

    print("Both bots are now running!")

    while True:
        if assistant_process.poll() is not None:
            print("Assistant bot has stopped unexpectedly!")
            break

        if reminders_process.poll() is not None:
            print("Reminders bot has stopped unexpectedly!")
            break

        try:
            assistant_output = assistant_process.stdout.readline()
            if assistant_output:
                print(f"[ASSISTANT] {assistant_output.rstrip()}")
        except:
            pass

        try:
            reminders_output = reminders_process.stdout.readline()
            if reminders_output:
                print(f"[REMINDERS] {reminders_output.rstrip()}")
        except:
            pass

        time.sleep(0.1)

if __name__ == "__main__":
    main()
