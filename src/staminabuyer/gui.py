"""
Modern GUI for Stamina Buyer using CustomTkinter.

Provides a user-friendly interface for:
- Discovering emulator windows
- Configuring targets
- Running stamina purchases
- Viewing real-time logs
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from queue import Queue
from typing import Any

try:
    import customtkinter as ctk
    
    HAS_GUI_DEPS = True
except ImportError:
    HAS_GUI_DEPS = False

from rich.console import Console

from .config import EmulatorTarget
from .pipeline import PipelineOptions, PipelineRunner

# Anchor-based scale calibration supersedes the legacy reference-width
# rescale, so the GUI leaves it disabled. Kept as a sentinel here in case a
# future preference screen wants to expose it for fixed-size deployments.
DEFAULT_REFERENCE_WIDTH: int | None = None


def _get_config_dir() -> Path:
    """Get the config directory for saving presets."""
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".config"
    
    config_dir = base / "StaminaBuyer"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _save_targets(targets: list[dict]) -> bool:
    """Save targets to config file."""
    try:
        config_file = _get_config_dir() / "last_targets.json"
        with open(config_file, "w") as f:
            json.dump(targets, f, indent=2)
        return True
    except Exception:
        return False


def _load_targets() -> list[dict]:
    """Load targets from config file."""
    try:
        config_file = _get_config_dir() / "last_targets.json"
        if config_file.exists():
            with open(config_file) as f:
                return json.load(f)
    except Exception:
        pass
    return []


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
    
    def __init__(self, master, target_name: str, stamina_goal: int, on_remove=None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.target_name = target_name
        self.stamina_goal = stamina_goal
        self.stamina_purchased = 0
        self._on_remove = on_remove
        self._is_running = False
        
        # Layout
        self.grid_columnconfigure(1, weight=1)
        
        # Target name (truncate longer names)
        display_name = target_name[:25] + "..." if len(target_name) > 25 else target_name
        self.name_label = ctk.CTkLabel(
            self,
            text=display_name,
            font=ctk.CTkFont(size=11),
            anchor="w",
            width=160
        )
        self.name_label.grid(row=0, column=0, padx=(6, 3), pady=3, sticky="w")
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self, width=200, height=12)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, padx=3, pady=3, sticky="ew")
        
        # Progress text
        self.progress_label = ctk.CTkLabel(
            self,
            text=f"0/{stamina_goal}",
            font=ctk.CTkFont(size=11),
            width=70
        )
        self.progress_label.grid(row=0, column=2, padx=(3, 6), pady=3)
        
        # Remove button (only visible when not running)
        self.remove_btn = ctk.CTkButton(
            self,
            text="✕",
            width=24,
            height=24,
            font=ctk.CTkFont(size=12),
            fg_color="transparent",
            hover_color="darkred",
            command=self._handle_remove
        )
        self.remove_btn.grid(row=0, column=3, padx=(0, 4), pady=3)
    
    def _handle_remove(self):
        """Handle remove button click."""
        if self._on_remove and not self._is_running:
            self._on_remove(self)
    
    def update_progress(self, purchased: int):
        """Update the progress display."""
        self.stamina_purchased = purchased
        progress = min(1.0, purchased / self.stamina_goal) if self.stamina_goal > 0 else 0
        self.progress_bar.set(progress)
        self.progress_label.configure(text=f"{purchased}/{self.stamina_goal}")
        
        if purchased >= self.stamina_goal:
            self.progress_bar.configure(progress_color="green")
            self.remove_btn.configure(state="disabled", text="✓", fg_color="green", hover_color="green")
    
    def set_active(self):
        """Mark this target as currently being processed."""
        self._is_running = True
        self.remove_btn.configure(state="disabled", text="...", fg_color="transparent")
        self.configure(border_width=2, border_color="blue")
    
    def set_complete(self, success: bool):
        """Mark this target as complete."""
        self._is_running = False
        if success:
            self.progress_bar.configure(progress_color="green")
            self.remove_btn.configure(state="disabled", text="✓", fg_color="green", hover_color="green")
        else:
            self.progress_bar.configure(progress_color="red")
            self.remove_btn.configure(state="disabled", text="✕", fg_color="red", hover_color="red")
        self.configure(border_width=0)
    
    def set_cancelled(self):
        """Mark this target as cancelled."""
        self._is_running = False
        self.remove_btn.configure(state="disabled", text="—", fg_color="gray", hover_color="gray")
        self.configure(border_width=0)


class TargetListItem(ctk.CTkFrame):
    """Interactive item for displaying/editing a target in the config list."""
    
    def __init__(self, master, target_name: str, stamina: int, 
                 on_update=None, on_remove=None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.target_name = target_name
        self._on_update = on_update
        self._on_remove = on_remove
        
        self.grid_columnconfigure(0, weight=1)
        
        # Target name
        display_name = target_name[:30] + "..." if len(target_name) > 30 else target_name
        self.name_label = ctk.CTkLabel(
            self,
            text=display_name,
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        self.name_label.grid(row=0, column=0, padx=(8, 4), pady=4, sticky="w")
        
        # Stamina entry
        self.stamina_entry = ctk.CTkEntry(
            self,
            width=70,
            height=24,
            font=ctk.CTkFont(size=11),
            justify="right"
        )
        self.stamina_entry.insert(0, str(stamina))
        self.stamina_entry.grid(row=0, column=1, padx=2, pady=4)
        self.stamina_entry.bind("<Return>", lambda e: self._save_stamina())
        self.stamina_entry.bind("<FocusOut>", lambda e: self._save_stamina())
        
        # Label
        self.unit_label = ctk.CTkLabel(
            self,
            text="stam",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.unit_label.grid(row=0, column=2, padx=(0, 4), pady=4)
        
        # Remove button
        self.remove_btn = ctk.CTkButton(
            self,
            text="✕",
            width=24,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            hover_color="darkred",
            command=self._handle_remove
        )
        self.remove_btn.grid(row=0, column=3, padx=(0, 4), pady=4)
    
    def _save_stamina(self):
        """Save the updated stamina value."""
        try:
            new_stamina = int(self.stamina_entry.get().strip())
            if new_stamina > 0 and self._on_update:
                self._on_update(self.target_name, new_stamina)
        except ValueError:
            pass  # Invalid input, ignore
    
    def _handle_remove(self):
        """Handle remove button click."""
        if self._on_remove:
            self._on_remove(self.target_name)
    
    def get_stamina(self) -> int:
        """Get current stamina value."""
        try:
            return int(self.stamina_entry.get().strip())
        except ValueError:
            return 0


class StaminaBuyerGUI(ctk.CTk):
    """Main GUI window for Stamina Buyer."""
    
    def __init__(self):
        super().__init__()
        
        # Configure window
        self.title("Stamina Buyer")
        self.geometry("650x480")
        self.minsize(500, 350)
        
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
        
        # Main scrollable container
        self.main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        
        # Header Frame
        self.header_frame = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        
        self.header_label = ctk.CTkLabel(
            self.header_frame,
            text="🎮 Stamina Buyer",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        
        self.subtitle_label = ctk.CTkLabel(
            self.header_frame,
            text="Automate Black Market stamina purchases",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        
        # === Combined Target Configuration Frame ===
        self.config_frame = ctk.CTkFrame(self.main_scroll)
        self.config_frame_label = ctk.CTkLabel(
            self.config_frame,
            text="1️⃣  Configure Targets",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        
        # Row frame for window detection controls
        self.config_row = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        
        # Window detection row - all children of config_row
        self.detect_button = ctk.CTkButton(
            self.config_row,
            text="🔍 Detect",
            command=self._detect_windows,
            width=90,
            height=28
        )
        
        self.window_dropdown = ctk.CTkComboBox(
            self.config_row,
            values=["Click 'Detect' first..."],
            width=180,
            height=28,
            state="readonly"
        )
        
        # Stamina input
        self.stamina_label = ctk.CTkLabel(
            self.config_row,
            text="Stamina:",
            font=ctk.CTkFont(size=12)
        )
        
        self.stamina_entry = ctk.CTkEntry(
            self.config_row,
            placeholder_text="100",
            width=60,
            height=28
        )
        self.stamina_entry.insert(0, "100")
        
        self.add_target_button = ctk.CTkButton(
            self.config_row,
            text="➕ Add",
            command=self._add_target,
            width=60,
            height=28
        )
        
        self.load_last_button = ctk.CTkButton(
            self.config_row,
            text="📂 Last",
            command=self._load_last_targets,
            width=60,
            height=28,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90")
        )
        
        # Targets List (scrollable frame for interactive items)
        self.targets_scroll = ctk.CTkScrollableFrame(
            self.config_frame,
            height=60,
            label_text=""
        )
        self.target_list_items: list[TargetListItem] = []
        
        # Empty state label
        self.targets_empty_label = ctk.CTkLabel(
            self.targets_scroll,
            text="No targets added. Select a window above and click Add.",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        
        # === Run Frame ===
        self.run_frame = ctk.CTkFrame(self.main_scroll)
        self.run_frame_label = ctk.CTkLabel(
            self.run_frame,
            text="2️⃣  Run",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        
        self.run_button = ctk.CTkButton(
            self.run_frame,
            text="🚀 Start",
            command=self._run_purchase,
            width=100,
            height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#228B22",
            hover_color="#006400"
        )
        
        self.cancel_button = ctk.CTkButton(
            self.run_frame,
            text="⏹️ Cancel",
            command=self._cancel_run,
            width=80,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#8B0000",
            hover_color="#5C0000",
            state="disabled"
        )
        
        # === Progress Frame ===
        self.progress_frame = ctk.CTkFrame(self.main_scroll)
        self.progress_frame_label = ctk.CTkLabel(
            self.progress_frame,
            text="📊 Progress",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        
        # Scrollable frame for target progress bars
        self.progress_scroll = ctk.CTkScrollableFrame(
            self.progress_frame,
            height=60
        )
        
        # === Log Frame ===
        self.log_frame = ctk.CTkFrame(self.main_scroll)
        self.log_frame_label = ctk.CTkLabel(
            self.log_frame,
            text="📋 Log",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        
        self.log_textbox = ctk.CTkTextbox(
            self.log_frame,
            height=120,
            font=ctk.CTkFont(size=11),
            state="disabled"
        )
        
        self.clear_log_button = ctk.CTkButton(
            self.log_frame,
            text="Clear",
            command=self._clear_log,
            width=60,
            height=24,
            font=ctk.CTkFont(size=11)
        )
    
    def _layout_widgets(self):
        """Layout all widgets in a scrollable container."""
        
        # Main scrollable frame fills the window
        self.main_scroll.pack(fill="both", expand=True, padx=3, pady=3)
        
        # Header
        self.header_frame.pack(fill="x", padx=10, pady=(3, 3))
        self.header_label.pack()
        self.subtitle_label.pack()
        
        # === Config Frame (compact) ===
        self.config_frame.pack(fill="x", padx=8, pady=2)
        self.config_frame_label.pack(anchor="w", padx=8, pady=(4, 2))
        
        # Row 1: Window detection + stamina + add button
        self.config_row.pack(fill="x", padx=8, pady=2)
        self.detect_button.pack(side="left", padx=(0, 4))
        self.window_dropdown.pack(side="left", padx=(0, 6))
        self.stamina_label.pack(side="left", padx=(0, 2))
        self.stamina_entry.pack(side="left", padx=(0, 4))
        self.add_target_button.pack(side="left", padx=(0, 4))
        self.load_last_button.pack(side="left")
        
        # Row 2: Targets list
        self.targets_scroll.pack(fill="x", padx=8, pady=(0, 4))
        
        # === Run Frame (compact - label and buttons on same row) ===
        self.run_frame.pack(fill="x", padx=8, pady=2)
        self.run_frame.grid_columnconfigure(0, weight=1)
        
        self.run_frame_label.grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self.run_button.grid(row=0, column=1, padx=2, pady=6)
        self.cancel_button.grid(row=0, column=2, padx=(2, 8), pady=6)
        
        # === Progress Frame (compact) ===
        self.progress_frame.pack(fill="x", padx=8, pady=2)
        self.progress_frame_label.pack(anchor="w", padx=8, pady=(4, 2))
        self.progress_scroll.pack(fill="x", padx=8, pady=(0, 4))
        
        # === Log Frame (compact) ===
        self.log_frame.pack(fill="x", padx=8, pady=2)
        
        log_header = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=8, pady=(4, 2))
        self.log_frame_label.pack(side="left")
        self.clear_log_button.pack(side="right")
        
        self.log_textbox.pack(fill="x", padx=8, pady=(0, 4))
    
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
        
        if not window_title or window_title.startswith("Click") or window_title.startswith("No ") or window_title.startswith("──"):
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
    
    def _load_last_targets(self):
        """Load the last saved targets."""
        saved = _load_targets()
        if saved:
            self.targets = saved
            self._update_targets_display()
            self._log(f"📂 Loaded {len(saved)} targets from last session")
        else:
            self._log("⚠️ No saved targets found")
    
    def _update_target_stamina(self, target_name: str, new_stamina: int):
        """Update stamina for a target."""
        for t in self.targets:
            if t["name"] == target_name:
                t["stamina"] = new_stamina
                break
    
    def _remove_target(self, target_name: str):
        """Remove a target from the list."""
        self.targets = [t for t in self.targets if t["name"] != target_name]
        self._update_targets_display()
    
    def _update_targets_display(self):
        """Update the targets list with interactive items."""
        # Clear existing items
        for item in self.target_list_items:
            item.destroy()
        self.target_list_items.clear()
        
        if not self.targets:
            self.targets_empty_label.pack(pady=8)
        else:
            self.targets_empty_label.pack_forget()
            for target in self.targets:
                item = TargetListItem(
                    self.targets_scroll,
                    target["name"],
                    target["stamina"],
                    on_update=self._update_target_stamina,
                    on_remove=self._remove_target
                )
                item.pack(fill="x", pady=1)
                self.target_list_items.append(item)
    
    def _sync_target_values(self):
        """Sync stamina values from the UI entries to the targets list."""
        for i, item in enumerate(self.target_list_items):
            if i < len(self.targets):
                stamina = item.get_stamina()
                if stamina > 0:
                    self.targets[i]["stamina"] = stamina
    
    def _run_purchase(self):
        """Run the purchase pipeline."""
        if not self.targets:
            self._log("⚠️ Add at least one target first")
            return
        
        if self.is_running:
            self._log("⚠️ Already running!")
            return
        
        # Sync any pending edits from the UI
        self._sync_target_values()
        
        # Save targets for "Load Last" feature
        _save_targets(self.targets)
        
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
        for i, target in enumerate(self.targets):
            frame = TargetProgressFrame(
                self.progress_scroll,
                target["name"],
                target["stamina"],
                on_remove=lambda f, idx=i: self._remove_target_by_frame(f, idx)
            )
            frame.pack(fill="x", pady=2)
            self.target_frames.append(frame)
    
    def _remove_target_by_frame(self, frame: TargetProgressFrame, index: int):
        """Remove a target from the queue."""
        if self.is_running:
            return  # Can't remove while running
        
        # Find and remove the frame
        if frame in self.target_frames:
            frame_idx = self.target_frames.index(frame)
            self.target_frames.remove(frame)
            frame.destroy()
            
            # Remove corresponding target
            if frame_idx < len(self.targets):
                self.targets.pop(frame_idx)
            
            # Rebuild the display to fix indices
            self._setup_progress_display()
    
    def _execute_pipeline(self):
        """Execute the pipeline (runs in background thread)."""
        try:
            from .pipeline import CancelledError, PipelineResult
            
            # Redirect logs to GUI
            console = Console(file=LogCapture(self.log_queue), force_terminal=False)
            
            results: list[PipelineResult] = []
            
            for i, target in enumerate(self.targets):
                if self.cancel_requested:
                    self._log("⏹️ Skipping remaining targets")
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
                    post_purchase_delay_seconds=1.0,
                    post_click_delay_seconds=1.0,
                    max_refreshes=100,
                    reference_width=DEFAULT_REFERENCE_WIDTH,
                )
                
                # Progress callback to update UI in real-time
                # Use default argument to capture current value of i (not reference)
                def on_progress(target_name: str, purchased: int, idx=i):
                    self.log_queue.put(("target_progress", (idx, purchased)))
                
                # Cancel check callback
                def should_cancel():
                    return self.cancel_requested
                
                runner = PipelineRunner(
                    options=options,
                    console=console,
                    progress_callback=on_progress,
                    cancel_callback=should_cancel,
                )
                
                try:
                    result = runner.run([emulator_target])[0]
                    results.append(result)
                    
                    # Final update
                    self.log_queue.put(("target_progress", (i, result.purchased)))
                    self.log_queue.put(("target_complete", (i, result.successful)))
                
                except CancelledError:
                    self.log_queue.put(("target_cancelled", i))
                    # Mark remaining as cancelled too
                    for j in range(i + 1, len(self.targets)):
                        self.log_queue.put(("target_cancelled", j))
                    break
                    
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
        self.load_last_button.configure(state="disabled")
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="normal", text="⏹️ Cancel")
    
    def _enable_controls(self):
        """Enable controls after operation."""
        self.detect_button.configure(state="normal")
        self.add_target_button.configure(state="normal")
        self.load_last_button.configure(state="normal")
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
