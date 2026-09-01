import time
import threading
import subprocess

def start_watchdog(process, server_command, server_env, server_log, backup_fn, interval: int = 180):
    def loop():
        while True:
            try:
                time.sleep(interval)
                if process.poll() is not None:
                    print("[WATCHDOG] Reiniciando OpenCode...")
                    new_log = open(server_log, "a", encoding="utf-8")
                    new_proc = subprocess.Popen(server_command, stdout=new_log, stderr=new_log, env=server_env, start_new_session=True)
                    # actualizar referencia global si es necesario
                    print(f"[WATCHDOG] Nuevo PID: {new_proc.pid}")
                print(f"[BACKUP] {time.strftime('%Y-%m-%d %H:%M:%S')}")
                backup_fn()
            except Exception as e:
                print(f"[WATCHDOG ERROR] {e!r}")
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t
