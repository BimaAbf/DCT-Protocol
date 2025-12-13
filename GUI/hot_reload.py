import sys, time, subprocess, os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class RH(FileSystemEventHandler):
    def __init__(self, p, cwd, env): self.p, self.cwd, self.env, self.pr = p, cwd, env, None; self.sp()
    def sp(self):
        if self.pr: self.pr.terminate(); self.pr.wait()
        print(f"Starting {self.p}..."); self.pr = subprocess.Popen([sys.executable, self.p], cwd=self.cwd, env=self.env)
    def on_modified(self, e):
        if e.is_directory: return
        f = e.src_path
        if f.endswith(".py"):
            if os.path.abspath(f) == os.path.abspath(__file__): return
            print(f"Change in {f}. Restarting..."); self.sp()
        elif f.endswith((".svg", ".png", ".jpg", ".jpeg", ".ico")): print(f"Asset change {f}. Restarting..."); self.sp()

def main():
    cd = os.path.dirname(os.path.abspath(__file__))
    s = os.path.join(cd, "main.py")
    if not os.path.exists(s): print(f"Error: No {s}"); return
    h = RH(s, cd, None); o = Observer(); o.schedule(h, cd, recursive=True); o.start(); print(f"Watching {cd}...")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt: o.stop(); h.pr.terminate() if h.pr else None
    o.join()

if __name__ == "__main__": main()
