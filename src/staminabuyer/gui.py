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


class LogCapture:
    """Captures log messages and sends them to GUI."""
    
    def __init__(self, queue: Queue):
        self.queue = queue
    
    def write(self, message: str):
        if message.strip():
            self.queue.put(("log", message.strip()))
    
    def flush(self):
        pass


class StaminaBuyerGUI(ctk.CTk):
    """Main GUI window for Stamina Buyer."""
    
    def __init__(self):
        super().__init__()
        
        # Configure window
        self.title("Stamina Buyer - Evony Automation")
        self.geometry("900x700")
        
        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # State
        self.targets: list[dict[str, Any]] = []
        self.is_running = False
        self.log_queue: Queue = Queue()
        
        # Build UI
        self._create_widgets()
        self._layout_widgets()
        
        # Start log monitor
        self.after(100, self._check_log_queue)
    
    def _create_widgets(self):
        """Create all UI widgets."""
        
        # Header
        self.header_label = ctk.CTkLabel(
            self,
            text="🎮 Stamina Buyer",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        
        self.subtitle_label = ctk.CTkLabel(
            self,
            text="Automate Black Market stamina purchases (no ADB required)",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        
        # Window Detection Frame
        self.window_frame = ctk.CTkFrame(self)
        self.window_frame_label = ctk.CTkLabel(
            self.window_frame,
            text="1️⃣  Find Emulator Windows",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        
        self.detect_button = ctk.CTkButton(
            self.window_frame,
            text="🔍 Detect Windows",
            command=self._detect_windows,
            width=150
        )
        
        self.window_dropdown = ctk.CTkComboBox(
            self.window_frame,
            values=["Click 'Detect Windows' first..."],
            width=400,
            state="readonly"
        )
        
        # Target Configuration Frame
        self.target_frame = ctk.CTkFrame(self)
        self.target_frame_label = ctk.CTkLabel(
            self.target_frame,
            text="2️⃣  Configure Targets",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        
        self.stamina_label = ctk.CTkLabel(
            self.target_frame,
            text="Stamina Amount:"
        )
        
        self.stamina_entry = ctk.CTkEntry(
            self.target_frame,
            placeholder_text="e.g., 100",
            width=150
        )
        self.stamina_entry.insert(0, "100")
        
        self.add_target_button = ctk.CTkButton(
            self.target_frame,
            text="➕ Add Target",
            command=self._add_target,
            width=150
        )
        
        # Targets List
        self.targets_textbox = ctk.CTkTextbox(
            self.target_frame,
            height=120,
            width=600,
            state="disabled"
        )
        
        self.clear_targets_button = ctk.CTkButton(
            self.target_frame,
            text="🗑️ Clear All",
            command=self._clear_targets,
            width=120,
            fg_color="red",
            hover_color="darkred"
        )
        
        # Control Frame
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame_label = ctk.CTkLabel(
            self.control_frame,
            text="3️⃣  Run",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        
        self.dry_run_button = ctk.CTkButton(
            self.control_frame,
            text="🧪 Test (Dry Run)",
            command=self._run_dry_run,
            width=200,
            height=40,
            font=ctk.CTkFont(size=14)
        )
        
        self.run_button = ctk.CTkButton(
            self.control_frame,
            text="🚀 Buy Stamina",
            command=self._run_purchase,
            width=200,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="green",
            hover_color="darkgreen"
        )
        
        self.progress_bar = ctk.CTkProgressBar(
            self.control_frame,
            width=400
        )
        self.progress_bar.set(0)
        
        # Log Frame
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame_label = ctk.CTkLabel(
            self.log_frame,
            text="📋 Activity Log",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        
        self.log_textbox = ctk.CTkTextbox(
            self.log_frame,
            height=200,
            width=850,
            state="disabled"
        )
        
        self.clear_log_button = ctk.CTkButton(
            self.log_frame,
            text="Clear Log",
            command=self._clear_log,
            width=100
        )
    
    def _layout_widgets(self):
        """Layout all widgets."""
        
        # Header
        self.header_label.pack(pady=(20, 5))
        self.subtitle_label.pack(pady=(0, 20))
        
        # Window Detection
        self.window_frame.pack(fill="x", padx=20, pady=10)
        self.window_frame_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        detect_frame = ctk.CTkFrame(self.window_frame, fg_color="transparent")
        detect_frame.pack(fill="x", padx=10, pady=10)
        self.detect_button.pack(side="left", padx=(0, 10))
        self.window_dropdown.pack(side="left")
        
        # Target Configuration
        self.target_frame.pack(fill="x", padx=20, pady=10)
        self.target_frame_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        config_frame = ctk.CTkFrame(self.target_frame, fg_color="transparent")
        config_frame.pack(fill="x", padx=10, pady=5)
        self.stamina_label.pack(side="left", padx=(0, 10))
        self.stamina_entry.pack(side="left", padx=(0, 10))
        self.add_target_button.pack(side="left")
        
        self.targets_textbox.pack(padx=10, pady=5)
        self.clear_targets_button.pack(anchor="e", padx=10, pady=(0, 10))
        
        # Control
        self.control_frame.pack(fill="x", padx=20, pady=10)
        self.control_frame_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        buttons_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        buttons_frame.pack(padx=10, pady=10)
        self.dry_run_button.pack(side="left", padx=10)
        self.run_button.pack(side="left", padx=10)
        
        self.progress_bar.pack(padx=10, pady=(0, 10))
        
        # Log
        self.log_frame.pack(fill="both", expand=True, padx=20, pady=10)
        self.log_frame_label.pack(anchor="w", padx=10, pady=(10, 5))
        self.log_textbox.pack(fill="both", expand=True, padx=10, pady=5)
        self.clear_log_button.pack(anchor="e", padx=10, pady=(0, 10))
    
    def _detect_windows(self):
        """Detect emulator windows."""
        self._log("🔍 Detecting emulator windows...")
        
        try:
            from .emulator.screen_capture import find_emulator_windows, list_windows, list_windows_debug
            
            # First, try to list all windows for debugging with stats
            try:
                all_windows, stats = list_windows_debug()
                self._log(f"📋 Window enumeration stats:")
                self._log(f"   Total windows checked: {stats['total_checked']}")
                self._log(f"   Visible windows: {stats['visible']}")
                self._log(f"   Windows with titles: {stats['with_title']}")
                if stats['errors'] > 0:
                    self._log(f"   Errors: {stats['errors']}")
                self._log(f"   Found {len(all_windows)} total windows")
            except Exception as e:
                self._log(f"⚠️ Could not list windows: {e}")
                all_windows = []
            
            # Now find emulator windows
            emulator_windows = find_emulator_windows()
            
            # Always show all windows for debugging
            if all_windows:
                self._log("")
                self._log("   📋 All detected windows (first 20):")
                for window in all_windows[:20]:
                    # Mark emulator windows with a star
                    marker = "⭐" if window in emulator_windows else "  "
                    self._log(f"      {marker} {window}")
                if len(all_windows) > 20:
                    self._log(f"      ... and {len(all_windows) - 20} more")
                self._log("")
            
            # Populate dropdown with ALL windows, but put emulator windows first
            if all_windows:
                # Sort: emulator windows first, then all others
                sorted_windows = []
                if emulator_windows:
                    sorted_windows.extend(emulator_windows)
                    sorted_windows.append("---")  # Separator
                
                # Add non-emulator windows
                for window in all_windows:
                    if window not in emulator_windows:
                        sorted_windows.append(window)
                
                self.window_dropdown.configure(values=sorted_windows)
                self.window_dropdown.set(sorted_windows[0])
                
                if emulator_windows:
                    self._log(f"✅ Found {len(emulator_windows)} emulator window(s) (matching keywords)")
                    for window in emulator_windows:
                        self._log(f"   ⭐ {window}")
                    self._log(f"   ℹ️  All {len(all_windows)} windows available in dropdown")
                else:
                    self._log("⚠️ No emulator keywords matched")
                    self._log(f"   ℹ️  Showing all {len(all_windows)} windows - select any window manually")
            else:
                self.window_dropdown.configure(values=["No windows found"])
                self.window_dropdown.set("No windows found")
                self._log("❌ No windows detected at all")
        
        except Exception as e:
            import traceback
            self._log(f"❌ Error detecting windows: {e}")
            self._log(f"   Details: {traceback.format_exc()}")
    
    def _add_target(self):
        """Add a target to the list."""
        window_title = self.window_dropdown.get()
        stamina_str = self.stamina_entry.get().strip()
        
        if not window_title or window_title == "Click 'Detect Windows' first..." or window_title == "No emulators found":
            self._log("⚠️ Please detect windows first")
            return
        
        try:
            stamina = int(stamina_str)
            if stamina <= 0:
                raise ValueError("Stamina must be positive")
        except ValueError:
            self._log("⚠️ Please enter a valid stamina amount (positive integer)")
            return
        
        self.targets.append({"name": window_title, "stamina": stamina})
        self._update_targets_display()
        self._log(f"➕ Added target: {window_title} → {stamina} stamina")
    
    def _clear_targets(self):
        """Clear all targets."""
        self.targets.clear()
        self._update_targets_display()
        self._log("🗑️ Cleared all targets")
    
    def _update_targets_display(self):
        """Update the targets textbox."""
        self.targets_textbox.configure(state="normal")
        self.targets_textbox.delete("1.0", "end")
        
        if not self.targets:
            self.targets_textbox.insert("1.0", "No targets configured yet. Add targets above.")
        else:
            for i, target in enumerate(self.targets, 1):
                self.targets_textbox.insert("end", f"{i}. {target['name']} → {target['stamina']} stamina\n")
        
        self.targets_textbox.configure(state="disabled")
    
    def _run_dry_run(self):
        """Run in dry-run mode."""
        self._run_pipeline(dry_run=True)
    
    def _run_purchase(self):
        """Run actual purchase."""
        if not self.targets:
            self._log("⚠️ No targets configured. Add at least one target first.")
            return
        
        # Confirmation dialog
        response = ctk.CTkInputDialog(
            text="Are you sure you want to start purchasing?\nType 'yes' to confirm:",
            title="Confirm Purchase"
        ).get_input()
        
        if response and response.lower() == "yes":
            self._run_pipeline(dry_run=False)
        else:
            self._log("❌ Purchase cancelled")
    
    def _run_pipeline(self, dry_run: bool):
        """Run the purchase pipeline."""
        if self.is_running:
            self._log("⚠️ Already running!")
            return
        
        if not self.targets:
            self._log("⚠️ No targets configured")
            return
        
        self.is_running = True
        self._disable_controls()
        self.progress_bar.set(0)
        
        mode = "DRY RUN" if dry_run else "PURCHASE"
        self._log(f"\n{'='*50}")
        self._log(f"🚀 Starting {mode} mode...")
        self._log(f"{'='*50}\n")
        
        # Run in background thread
        thread = threading.Thread(
            target=self._execute_pipeline,
            args=(dry_run,),
            daemon=True
        )
        thread.start()
    
    def _execute_pipeline(self, dry_run: bool):
        """Execute the pipeline (runs in background thread)."""
        try:
            # Convert targets
            emulator_targets = [
                EmulatorTarget(name=t["name"], stamina=t["stamina"])
                for t in self.targets
            ]
            
            # Create options
            options = PipelineOptions(
                dry_run=dry_run,
                max_retries=3,
                post_purchase_delay_seconds=3.0,  # Wait for emulator UI to update
                post_click_delay_seconds=0.5,  # Wait for confirm dialog to appear
                max_refreshes=100,  # Try refreshing Black Market up to 100 times (can take many tries)
                save_debug_screenshots=True,  # Enable debug screenshots for troubleshooting
            )
            
            # Redirect logs to GUI
            console = Console(file=LogCapture(self.log_queue), force_terminal=False)
            
            # Run pipeline
            runner = PipelineRunner(options=options, console=console)
            results = runner.run(emulator_targets)
            
            # Report results
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
                elif msg_type == "complete":
                    self._on_complete(msg)
                elif msg_type == "error":
                    self._on_error(msg)
        
        except Exception:
            pass
        
        # Check again soon
        self.after(100, self._check_log_queue)
    
    def _on_complete(self, results):
        """Handle pipeline completion."""
        self._log(f"\n{'='*50}")
        self._log("✅ Pipeline completed!")
        self._log(f"{'='*50}\n")
        
        for result in results:
            status = "✅" if result.successful else "❌"
            self._log(f"{status} {result.name}: {result.purchased}/{result.requested} stamina")
            if result.errors:
                for error in result.errors:
                    self._log(f"   ⚠️ {error}")
        
        self.progress_bar.set(1.0)
        self.is_running = False
        self._enable_controls()
    
    def _on_error(self, error_msg):
        """Handle pipeline error."""
        self._log(f"\n❌ ERROR: {error_msg}\n")
        self.is_running = False
        self._enable_controls()
        self.progress_bar.set(0)
    
    def _log(self, message: str):
        """Add message to log."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", message + "\n")
        self.log_textbox.see("end")  # Auto-scroll
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
        self.dry_run_button.configure(state="disabled")
        self.run_button.configure(state="disabled")
    
    def _enable_controls(self):
        """Enable controls after operation."""
        self.detect_button.configure(state="normal")
        self.add_target_button.configure(state="normal")
        self.clear_targets_button.configure(state="normal")
        self.dry_run_button.configure(state="normal")
        self.run_button.configure(state="normal")


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

