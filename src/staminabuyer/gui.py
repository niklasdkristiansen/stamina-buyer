"""
Modern GUI for Stamina Buyer using CustomTkinter.

Provides a user-friendly interface for:
- Discovering emulator windows
- Configuring targets
- Running stamina purchases
- Viewing real-time logs
"""

from __future__ import annotations

import sys
import threading
from queue import Queue
from typing import Any

try:
    import customtkinter as ctk
    from PIL import Image
    
    HAS_GUI_DEPS = True
except ImportError:
    HAS_GUI_DEPS = False


from rich.console import Console

from .config import EmulatorTarget
from .pipeline import PipelineOptions, PipelineRunner


# Default reference width for template matching (matches template extraction resolution)
# Templates were extracted from ~341-344px wide screenshots
DEFAULT_REFERENCE_WIDTH = 343


class LogCapture:
    """Captures log messages and sends them to GUI."""
    
    def __init__(self, queue: Queue):
        self.queue = queue
    
    def write(self, message: str):
        if message.strip():
            self.queue.put(("log", message.strip()))
    
    def flush(self):
        pass


class TargetProgressFrame(ctk.CTkFrame):
    """Frame showing progress for a single target."""
    
    def __init__(self, master, target_name: str, stamina_goal: int, **kwargs):
        super().__init__(master, **kwargs)
        
        self.target_name = target_name
        self.stamina_goal = stamina_goal
        self.stamina_purchased = 0
        
        # Layout
        self.grid_columnconfigure(1, weight=1)
        
        # Target name
        self.name_label = ctk.CTkLabel(
            self,
            text=f"📱 {target_name[:30]}..." if len(target_name) > 30 else f"📱 {target_name}",
            font=ctk.CTkFont(size=12),
            anchor="w",
            width=200
        )
        self.name_label.grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self, width=300)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Progress text
        self.progress_label = ctk.CTkLabel(
            self,
            text=f"0/{stamina_goal}",
            font=ctk.CTkFont(size=12),
            width=80
        )
        self.progress_label.grid(row=0, column=2, padx=(5, 10), pady=5)
        
        # Status indicator
        self.status_label = ctk.CTkLabel(
            self,
            text="⏳",
            font=ctk.CTkFont(size=14),
            width=30
        )
        self.status_label.grid(row=0, column=3, padx=(0, 10), pady=5)
    
    def update_progress(self, purchased: int):
        """Update the progress display."""
        self.stamina_purchased = purchased
        progress = min(1.0, purchased / self.stamina_goal) if self.stamina_goal > 0 else 0
        self.progress_bar.set(progress)
        self.progress_label.configure(text=f"{purchased}/{self.stamina_goal}")
        
        if purchased >= self.stamina_goal:
            self.status_label.configure(text="✅")
            self.progress_bar.configure(progress_color="green")
    
    def set_active(self):
        """Mark this target as currently being processed."""
        self.status_label.configure(text="🔄")
        self.configure(border_width=2, border_color="blue")
    
    def set_complete(self, success: bool):
        """Mark this target as complete."""
        if success:
            self.status_label.configure(text="✅")
            self.progress_bar.configure(progress_color="green")
        else:
            self.status_label.configure(text="❌")
            self.progress_bar.configure(progress_color="red")
        self.configure(border_width=0)
    
    def set_cancelled(self):
        """Mark this target as cancelled."""
        self.status_label.configure(text="⏹️")
        self.configure(border_width=0)


class StaminaBuyerGUI(ctk.CTk):
    """Main GUI window for Stamina Buyer."""
    
    def __init__(self):
        super().__init__()
        
        # Configure window
        self.title("Stamina Buyer - Evony Automation")
        self.geometry("800x600")
        self.minsize(600, 400)
        
        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # State
        self.targets: list[dict[str, Any]] = []
        self.is_running = False
        self.cancel_requested = False
        self.log_queue: Queue = Queue()
        self.target_frames: list[TargetProgressFrame] = []
        
        # Build UI
        self._create_widgets()
        self._layout_widgets()
        
        # Start log monitor
        self.after(100, self._check_log_queue)
    
    def _create_widgets(self):
        """Create all UI widgets."""
        
        # Header Frame
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        
        self.header_label = ctk.CTkLabel(
            self.header_frame,
            text="🎮 Stamina Buyer",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        
        self.subtitle_label = ctk.CTkLabel(
            self.header_frame,
            text="Automate Black Market stamina purchases",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        
        # === Combined Target Configuration Frame ===
        self.config_frame = ctk.CTkFrame(self)
        self.config_frame_label = ctk.CTkLabel(
            self.config_frame,
            text="1️⃣  Configure Targets",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        
        # Window detection row
        self.detect_button = ctk.CTkButton(
            self.config_frame,
            text="🔍 Detect Windows",
            command=self._detect_windows,
            width=140
        )
        
        self.window_dropdown = ctk.CTkComboBox(
            self.config_frame,
            values=["Click 'Detect Windows' first..."],
            width=350,
            state="readonly"
        )
        
        # Stamina input
        self.stamina_label = ctk.CTkLabel(
            self.config_frame,
            text="Stamina:"
        )
        
        self.stamina_entry = ctk.CTkEntry(
            self.config_frame,
            placeholder_text="100",
            width=80
        )
        self.stamina_entry.insert(0, "100")
        
        self.add_target_button = ctk.CTkButton(
            self.config_frame,
            text="➕ Add",
            command=self._add_target,
            width=80
        )
        
        # Targets List
        self.targets_textbox = ctk.CTkTextbox(
            self.config_frame,
            height=60,
            state="disabled"
        )
        
        self.clear_targets_button = ctk.CTkButton(
            self.config_frame,
            text="🗑️ Clear All",
            command=self._clear_targets,
            width=100,
            fg_color="#8B0000",
            hover_color="#5C0000"
        )
        
        # === Run Frame ===
        self.run_frame = ctk.CTkFrame(self)
        self.run_frame_label = ctk.CTkLabel(
            self.run_frame,
            text="2️⃣  Run",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        
        self.run_button = ctk.CTkButton(
            self.run_frame,
            text="🚀 Start Buying Stamina",
            command=self._run_purchase,
            width=250,
            height=45,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#228B22",
            hover_color="#006400"
        )
        
        self.cancel_button = ctk.CTkButton(
            self.run_frame,
            text="⏹️ Cancel",
            command=self._cancel_run,
            width=120,
            height=45,
            font=ctk.CTkFont(size=14),
            fg_color="#8B0000",
            hover_color="#5C0000",
            state="disabled"
        )
        
        # === Progress Frame ===
        self.progress_frame = ctk.CTkFrame(self)
        self.progress_frame_label = ctk.CTkLabel(
            self.progress_frame,
            text="📊 Progress",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        
        # Scrollable frame for target progress bars
        self.progress_scroll = ctk.CTkScrollableFrame(
            self.progress_frame,
            height=80
        )
        
        # === Log Frame ===
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame_label = ctk.CTkLabel(
            self.log_frame,
            text="📋 Activity Log",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        
        self.log_textbox = ctk.CTkTextbox(
            self.log_frame,
            height=100,
            state="disabled"
        )
        
        self.clear_log_button = ctk.CTkButton(
            self.log_frame,
            text="Clear",
            command=self._clear_log,
            width=80
        )
    
    def _layout_widgets(self):
        """Layout all widgets using grid for better resizing."""
        
        # Configure grid weights for resizing
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)  # Log frame expands
        
        # Header (row 0)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(10, 5))
        self.header_label.pack()
        self.subtitle_label.pack()
        
        # === Config Frame (row 1) ===
        self.config_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=5)
        self.config_frame_label.pack(anchor="w", padx=10, pady=(8, 5))
        
        # Row 1: Window detection + stamina + add button
        row1 = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=3)
        
        self.detect_button.pack(side="left", padx=(0, 8))
        self.window_dropdown.pack(side="left", padx=(0, 15))
        self.stamina_label.pack(side="left", padx=(0, 5))
        self.stamina_entry.pack(side="left", padx=(0, 8))
        self.add_target_button.pack(side="left")
        
        # Row 2: Targets list
        self.targets_textbox.pack(fill="x", padx=10, pady=3)
        self.clear_targets_button.pack(anchor="e", padx=10, pady=(0, 8))
        
        # === Run Frame (row 2) ===
        self.run_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=5)
        self.run_frame_label.pack(anchor="w", padx=10, pady=(8, 5))
        
        buttons_row = ctk.CTkFrame(self.run_frame, fg_color="transparent")
        buttons_row.pack(padx=10, pady=(3, 10))
        self.run_button.pack(side="left", padx=(0, 15))
        self.cancel_button.pack(side="left")
        
        # === Progress Frame (row 3) ===
        self.progress_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=5)
        self.progress_frame_label.pack(anchor="w", padx=10, pady=(8, 3))
        self.progress_scroll.pack(fill="x", padx=10, pady=(0, 8))
        
        # === Log Frame (row 4 - expandable) ===
        self.log_frame.grid(row=4, column=0, sticky="nsew", padx=15, pady=(5, 10))
        
        log_header = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=10, pady=(8, 3))
        self.log_frame_label.pack(side="left")
        self.clear_log_button.pack(side="right")
        
        self.log_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 8))
    
    def _detect_windows(self):
        """Detect emulator windows."""
        self._log("🔍 Detecting windows...")
        
        try:
            from .emulator.screen_capture import find_emulator_windows, list_windows_debug
            
            try:
                all_windows, stats = list_windows_debug()
                self._log(f"   Found {len(all_windows)} windows")
            except Exception as e:
                self._log(f"⚠️ Error: {e}")
                all_windows = []
            
            emulator_windows = find_emulator_windows()
            
            if all_windows:
                # Sort: emulator windows first, then all others
                sorted_windows = []
                if emulator_windows:
                    sorted_windows.extend(emulator_windows)
                    if len(all_windows) > len(emulator_windows):
                        sorted_windows.append("── Other Windows ──")
                
                for window in all_windows:
                    if window not in emulator_windows:
                        sorted_windows.append(window)
                
                self.window_dropdown.configure(values=sorted_windows)
                self.window_dropdown.set(sorted_windows[0])
                
                if emulator_windows:
                    self._log(f"✅ Found {len(emulator_windows)} emulator(s)")
                else:
                    self._log("ℹ️ No emulators auto-detected, select manually")
            else:
                self.window_dropdown.configure(values=["No windows found"])
                self.window_dropdown.set("No windows found")
                self._log("❌ No windows found")
        
        except Exception as e:
            self._log(f"❌ Error: {e}")
    
    def _add_target(self):
        """Add a target to the list."""
        window_title = self.window_dropdown.get()
        stamina_str = self.stamina_entry.get().strip()
        
        if not window_title or window_title.startswith("Click") or window_title.startswith("No windows") or window_title.startswith("──"):
            self._log("⚠️ Please select a window first")
            return
        
        try:
            stamina = int(stamina_str)
            if stamina <= 0:
                raise ValueError("Stamina must be positive")
        except ValueError:
            self._log("⚠️ Enter a valid stamina amount")
            return
        
        # Check for duplicate
        for t in self.targets:
            if t["name"] == window_title:
                self._log(f"⚠️ {window_title} already added")
                return
        
        self.targets.append({"name": window_title, "stamina": stamina})
        self._update_targets_display()
        self._log(f"➕ Added: {window_title} → {stamina} stamina")
    
    def _clear_targets(self):
        """Clear all targets."""
        self.targets.clear()
        self._update_targets_display()
        self._log("🗑️ Cleared targets")
    
    def _update_targets_display(self):
        """Update the targets textbox."""
        self.targets_textbox.configure(state="normal")
        self.targets_textbox.delete("1.0", "end")
        
        if not self.targets:
            self.targets_textbox.insert("1.0", "No targets added yet. Select a window and click Add.")
        else:
            lines = [f"{i}. {t['name']} → {t['stamina']} stamina" for i, t in enumerate(self.targets, 1)]
            self.targets_textbox.insert("1.0", "\n".join(lines))
        
        self.targets_textbox.configure(state="disabled")
    
    def _run_purchase(self):
        """Run the purchase pipeline."""
        if not self.targets:
            self._log("⚠️ Add at least one target first")
            return
        
        if self.is_running:
            self._log("⚠️ Already running!")
            return
        
        self.is_running = True
        self.cancel_requested = False
        self._disable_controls()
        self._setup_progress_display()
        
        self._log(f"\n{'='*50}")
        self._log("🚀 Starting stamina purchases...")
        self._log(f"{'='*50}\n")
        
        # Run in background thread
        thread = threading.Thread(
            target=self._execute_pipeline,
            daemon=True
        )
        thread.start()
    
    def _cancel_run(self):
        """Request cancellation of the current run."""
        if self.is_running and not self.cancel_requested:
            self.cancel_requested = True
            self._log("\n⏹️ Cancel requested... waiting for current operation to finish")
            self.cancel_button.configure(state="disabled", text="Cancelling...")
            self.log_queue.put(("cancel", None))
    
    def _setup_progress_display(self):
        """Create progress bars for each target."""
        # Clear existing progress frames
        for frame in self.target_frames:
            frame.destroy()
        self.target_frames.clear()
        
        # Create new progress frames
        for target in self.targets:
            frame = TargetProgressFrame(
                self.progress_scroll,
                target["name"],
                target["stamina"]
            )
            frame.pack(fill="x", pady=2)
            self.target_frames.append(frame)
    
    def _execute_pipeline(self):
        """Execute the pipeline (runs in background thread)."""
        try:
            from .pipeline import PipelineResult
            
            # Redirect logs to GUI
            console = Console(file=LogCapture(self.log_queue), force_terminal=False)
            
            results: list[PipelineResult] = []
            
            for i, target in enumerate(self.targets):
                if self.cancel_requested:
                    self._log(f"⏹️ Skipping remaining targets")
                    # Mark remaining as cancelled
                    for j in range(i, len(self.targets)):
                        self.log_queue.put(("target_cancelled", j))
                    break
                
                # Mark target as active
                self.log_queue.put(("target_active", i))
                
                emulator_target = EmulatorTarget(name=target["name"], stamina=target["stamina"])
                
                # Create options
                options = PipelineOptions(
                    dry_run=False,
                    max_retries=3,
                    post_purchase_delay_seconds=3.0,
                    post_click_delay_seconds=2.0,
                    max_refreshes=100,
                    save_debug_screenshots=True,
                    reference_width=DEFAULT_REFERENCE_WIDTH,
                )
                
                runner = PipelineRunner(options=options, console=console)
                
                try:
                    result = runner.run([emulator_target])[0]
                    results.append(result)
                    
                    # Update progress
                    self.log_queue.put(("target_progress", (i, result.purchased)))
                    self.log_queue.put(("target_complete", (i, result.successful)))
                    
                except Exception as e:
                    self._log(f"❌ Error on {target['name']}: {e}")
                    self.log_queue.put(("target_complete", (i, False)))
            
            self.log_queue.put(("complete", results))
        
        except Exception as e:
            self.log_queue.put(("error", str(e)))
    
    def _check_log_queue(self):
        """Check for log messages from background thread."""
        try:
            while not self.log_queue.empty():
                msg_type, msg = self.log_queue.get_nowait()
                
                if msg_type == "log":
                    self._log(msg)
                elif msg_type == "target_active":
                    if msg < len(self.target_frames):
                        self.target_frames[msg].set_active()
                elif msg_type == "target_progress":
                    idx, purchased = msg
                    if idx < len(self.target_frames):
                        self.target_frames[idx].update_progress(purchased)
                elif msg_type == "target_complete":
                    idx, success = msg
                    if idx < len(self.target_frames):
                        self.target_frames[idx].set_complete(success)
                elif msg_type == "target_cancelled":
                    if msg < len(self.target_frames):
                        self.target_frames[msg].set_cancelled()
                elif msg_type == "cancel":
                    pass  # Already handled
                elif msg_type == "complete":
                    self._on_complete(msg)
                elif msg_type == "error":
                    self._on_error(msg)
        
        except Exception:
            pass
        
        self.after(100, self._check_log_queue)
    
    def _on_complete(self, results):
        """Handle pipeline completion."""
        self._log(f"\n{'='*50}")
        
        if self.cancel_requested:
            self._log("⏹️ Run cancelled")
        else:
            self._log("✅ Completed!")
        
        self._log(f"{'='*50}\n")
        
        for result in results:
            status = "✅" if result.successful else "❌"
            self._log(f"{status} {result.name}: {result.purchased}/{result.requested} stamina")
            if result.errors:
                for error in result.errors:
                    self._log(f"   ⚠️ {error}")
        
        self.is_running = False
        self.cancel_requested = False
        self._enable_controls()
    
    def _on_error(self, error_msg):
        """Handle pipeline error."""
        self._log(f"\n❌ ERROR: {error_msg}\n")
        self.is_running = False
        self.cancel_requested = False
        self._enable_controls()
    
    def _log(self, message: str):
        """Add message to log."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", message + "\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")
    
    def _clear_log(self):
        """Clear the log."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")
    
    def _disable_controls(self):
        """Disable controls during operation."""
        self.detect_button.configure(state="disabled")
        self.add_target_button.configure(state="disabled")
        self.clear_targets_button.configure(state="disabled")
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="normal", text="⏹️ Cancel")
    
    def _enable_controls(self):
        """Enable controls after operation."""
        self.detect_button.configure(state="normal")
        self.add_target_button.configure(state="normal")
        self.clear_targets_button.configure(state="normal")
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled", text="⏹️ Cancel")


def launch_gui():
    """Launch the GUI application."""
    if not HAS_GUI_DEPS:
        print("GUI dependencies not installed.")
        print("Install with: pip install customtkinter pillow")
        sys.exit(1)
    
    app = StaminaBuyerGUI()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
