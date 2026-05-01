import psutil
import platform
import time
import multiprocessing
import threading
import math
import sys
import select
import termios
import tty
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich.prompt import Prompt

# --- Shared State for UI Updates ---
app_state = {
    "mode": "Idle",
    "status_text": "Waiting to start...",
    "bench_results": None
}

console = Console()

# --- Hardware Data Functions ---
def get_cpu_model():
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line:
                    return line.split(":")[1].strip()
    except FileNotFoundError:
        pass
    return platform.processor() or "Unknown"

def get_cpu_temp():
    try:
        temps = psutil.sensors_temperatures()
        if not temps: return "N/A"
        for name in ['k10temp', 'coretemp', 'cpu_thermal', 'acpitz']:
            if name in temps and temps[name]:
                return f"{temps[name][0].current}°C"
        return f"{list(temps.values())[0][0].current}°C"
    except Exception:
        return "N/A"

# --- Benchmarking & Stress Testing ---
def benchmark_worker(duration, return_dict, worker_id):
    """Runs as fast as possible for a set duration and reports the iteration count."""
    start_time = time.time()
    iterations = 0
    while time.time() - start_time < duration:
        for i in range(1, 1000):
            _ = math.sqrt(i) * math.sin(i)
        iterations += 1000
    return_dict[worker_id] = iterations

def stress_worker():
    """An infinite loop to pin a CPU core to 100%."""
    try:
        while True:
            _ = 3.14159 ** 2.71828
    except KeyboardInterrupt:
        pass

def run_benchmark_thread(duration):
    """Runs the benchmark, tracks IPS (speed), and updates a live countdown."""
    logical_cores = multiprocessing.cpu_count()
    manager = multiprocessing.Manager()
    
    # 1. Single-Thread Test
    return_dict = manager.dict()
    p = multiprocessing.Process(target=benchmark_worker, args=(duration, return_dict, 0))
    p.start()
    
    # Live Countdown Loop for Single-Thread
    start_time = time.time()
    while p.is_alive():
        remaining = max(0.0, duration - (time.time() - start_time))
        app_state["status_text"] = f"[cyan]Running Single-Thread Benchmark... ({remaining:.1f}s remaining)[/cyan]"
        time.sleep(0.2)
        
    p.join()
    single_iterations = return_dict.get(0, 0)
    single_score = int((single_iterations / duration) / 1000) 

    # 2. Multi-Thread Test
    return_dict = manager.dict()
    processes = []
    for i in range(logical_cores):
        p = multiprocessing.Process(target=benchmark_worker, args=(duration, return_dict, i))
        processes.append(p)
        p.start()

    # Live Countdown Loop for Multi-Thread
    start_time = time.time()
    while any(p.is_alive() for p in processes):
        remaining = max(0.0, duration - (time.time() - start_time))
        app_state["status_text"] = f"[cyan]Running Multi-Thread Benchmark on {logical_cores} Threads... ({remaining:.1f}s remaining)[/cyan]"
        time.sleep(0.2)

    for p in processes:
        p.join()
        
    total_iterations = sum(return_dict.values())
    multi_score = int((total_iterations / duration) / 1000)
    multiplier = multi_score / single_score if single_score > 0 else 0

    # Save final results to state
    app_state["bench_results"] = {
        "single": single_score,
        "multi": multi_score,
        "multi_x": f"{multiplier:.2f}x"
    }
    app_state["status_text"] = "[bold green]Benchmark Complete! Press 'b' to return to menu.[/bold green]"

# --- UI Generation ---
def generate_hardware_panel():
    cores_physical = psutil.cpu_count(logical=False)
    cores_logical = psutil.cpu_count(logical=True)
    
    freq = psutil.cpu_freq()
    cpu_freq = f"{freq.current:.2f} MHz" if freq else "Unknown"
    cpu_usage = psutil.cpu_percent(interval=None)
    cpu_temp = get_cpu_temp()

    ram = psutil.virtual_memory()
    total_ram_gb = ram.total / (1024 ** 3)
    used_ram_gb = ram.used / (1024 ** 3)

    table = Table(show_header=False, expand=True, box=None)
    table.add_column("Component", style="cyan", width=20)
    table.add_column("Details", style="green")

    table.add_row("OS Release", f"{platform.system()} {platform.release()}")
    table.add_row("CPU Model", get_cpu_model())
    table.add_row("Cores / Threads", f"{cores_physical} Cores / {cores_logical} Threads")
    table.add_row("Current Speed", f"{cpu_freq} (Usage: {cpu_usage}%)")
    table.add_row("Temperature", cpu_temp)
    table.add_row("Total RAM", f"{total_ram_gb:.2f} GB")
    table.add_row("Used RAM", f"{used_ram_gb:.2f} GB ({ram.percent}%)")

    return Panel(table, title="[bold magenta]Py-CPU-Z : Hardware Monitor[/bold magenta]", border_style="blue")

def generate_status_panel():
    if app_state["bench_results"]:
        res = app_state["bench_results"]
        table = Table(show_header=True, expand=True, header_style="bold yellow")
        table.add_column("Test", style="cyan")
        table.add_column("Score", justify="right", style="green")
        table.add_row("Single-Thread", str(res["single"]))
        table.add_row("Multi-Thread", str(res["multi"]))
        table.add_row("Thread Multiplier", res["multi_x"])
        return Panel(table, title="[bold yellow]Benchmark Results (Press 'b' to go back)[/bold yellow]", border_style="yellow")
    
    return Panel(f"\n  {app_state['status_text']}\n", title=f"[bold yellow]{app_state['mode']} Status[/bold yellow]", border_style="yellow")

def generate_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="upper"),
        Layout(name="lower", size=10)
    )
    layout["upper"].update(generate_hardware_panel())
    layout["lower"].update(generate_status_panel())
    return layout

# --- Non-Blocking Terminal Input Handler ---
def run_live_view(stress_processes=None):
    """Runs the live dashboard and listens for 'b' or 'q' to go back to the menu."""
    old_settings = termios.tcgetattr(sys.stdin)
    
    try:
        tty.setcbreak(sys.stdin.fileno())
        
        with Live(generate_layout(), refresh_per_second=4, screen=True) as live:
            while True:
                live.update(generate_layout())
                
                # Check for keyboard input without blocking the UI updates
                if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                    char = sys.stdin.read(1).lower()
                    if char == 'b' or char == 'q':
                        break 
                
                time.sleep(0.25)
                
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        
        if stress_processes:
            console.print("\n[yellow]Stopping stress workers...[/yellow]")
            for p in stress_processes:
                p.terminate()
                p.join()

# --- Main Application ---
def main():
    psutil.cpu_percent(interval=0.1)

    while True:
        console.clear()
        app_state["bench_results"] = None
        app_state["status_text"] = "Waiting to start..."
        app_state["mode"] = "Idle"
        
        console.print(Panel("[bold magenta]Welcome to Py-CPU-Z[/bold magenta]\nChoose an execution mode:", border_style="blue"))
        console.print("1. [cyan]Monitor Only[/cyan] (Hardware tracking)")
        console.print("2. [cyan]Benchmark[/cyan]    (Test single/multi core performance)")
        console.print("3. [cyan]Stress Test[/cyan]  (Pin all cores to 100% to test thermals)")
        console.print("4. [red]Exit[/red]")
        
        try:
            choice = Prompt.ask("\nEnter your choice", choices=["1", "2", "3", "4"], default="1")
        except KeyboardInterrupt:
            console.print("\n[bold green]Exiting Py-CPU-Z. Goodbye![/bold green]")
            sys.exit(0)
            
        if choice == "4":
            console.print("[bold green]Exiting Py-CPU-Z. Goodbye![/bold green]")
            sys.exit(0)
        
        stress_processes = []
        
        if choice == "2":
            duration_str = Prompt.ask("Enter test duration in seconds per phase", default="5")
            try:
                duration = int(duration_str)
            except ValueError:
                duration = 5
                
            app_state["mode"] = f"Benchmark"
            threading.Thread(target=run_benchmark_thread, args=(duration,), daemon=True).start()
            
        elif choice == "3":
            app_state["mode"] = "Stress Test"
            app_state["status_text"] = f"[bold red]Running maximum heat payload on {multiprocessing.cpu_count()} threads.\n  Press 'b' to stop and return to menu.[/bold red]"
            for _ in range(multiprocessing.cpu_count()):
                p = multiprocessing.Process(target=stress_worker)
                stress_processes.append(p)
                p.start()
        else:
            app_state["mode"] = "Monitor"
            app_state["status_text"] = "Monitoring hardware. Press [bold]'b'[/bold] to return to menu."

        # Launch the live dashboard
        run_live_view(stress_processes)

if __name__ == "__main__":
    main()