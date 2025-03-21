#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont  # Correct import for font module
import pty
import os
import threading
import signal
import re
import time
import queue
import json
import pynput
import socket
import sys
import http.client
import urllib.parse
from urllib.request import Request, urlopen
import fnmatch
MODEL = "large-v3-turbo-q8_0"
SERVER_PORT = 7654
SINGLETON_PORT = 45678  # Choose an unused port

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WHISPER_SERVER_PATH = f"{PROJECT_ROOT}/whisper.cpp/build/bin/whisper-server"
WHISPER_MODEL_PATH = f"{PROJECT_ROOT}/whisper.cpp/models/ggml-{MODEL}.bin"

# Sox threshold for recording
THRESH_START = 4.0
THRESH_END = 4.0

FONT_SIZE = 12

class VoiceTypingGUI:
    def __init__(self, root):
        self.MODEL = MODEL
        self.SERVER_PORT = SERVER_PORT
        self.SERVER_URL = f"http://127.0.0.1:{self.SERVER_PORT}/inference"
        self.WHISPER_SERVER_PATH = WHISPER_SERVER_PATH
        self.WHISPER_MODEL_PATH = WHISPER_MODEL_PATH

        self.root = root
        self.root.title("Voice Typing")
        self.root.geometry("600x450")

        self.RECORDING = False
        self.AUDIO_queue = queue.Queue()
        self.keyboard = pynput.keyboard.Controller()

        # Set up bindings first
        self.root.bind("<space>", lambda event: self.toggle_recording())
        self.root.bind("<Escape>", lambda event: self.on_closing())
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Then set up UI and start operations
        self.setup_ui()
        self.start_whisper_server()
        self.processing_thread = threading.Thread(
            target=self.process_audio_queue, daemon=True
        )
        self.processing_thread.start()

        self.root.focus_force()
        self.start_recording()

    def setup_ui(self):
        # Configure default font size for the entire application
        default_font = tkfont.nametofont("TkDefaultFont")
        text_font = tkfont.nametofont("TkTextFont")
        
        # Try to use a nicer font with fallback to system default
        preferred_fonts = ['helvetica']
        
        # Find the first available font from our preferred list
        chosen_font = None
        print("Available fonts:", tkfont.families())
        for font_name in preferred_fonts:
            if font_name.lower() in [f.lower() for f in tkfont.families()]:
                chosen_font = font_name
                break
        
        # Configure fonts with the chosen font or keep default if none available
        if chosen_font:
            print("Using font:", chosen_font)
            default_font.configure(family=chosen_font, size=FONT_SIZE)
            text_font.configure(family=chosen_font, size=FONT_SIZE)
        else:
            print("No preferred fonts available, using system default")
            # Just set the size if no preferred fonts are available
            default_font.configure(size=FONT_SIZE)
            text_font.configure(size=FONT_SIZE)
        
        # Apply the font configuration to all widgets
        self.root.option_add("*Font", default_font)

        config_frame = ttk.LabelFrame(self.root, text="Configuration")
        config_frame.pack(padx=10, pady=5, fill="x")
        
        # Display current configuration with integrated threshold controls
        info_frame = ttk.Frame(config_frame)
        info_frame.pack(pady=2, fill="x")
        
        # Model and port info
        self.config_label = ttk.Label(
            info_frame, 
            text=f"Model: {self.MODEL} | Port: {self.SERVER_PORT} | Thresholds: {THRESH_START}%",
        )
        self.config_label.pack(pady=2, side=tk.LEFT)
        

        control_frame = ttk.Frame(self.root)
        control_frame.pack(padx=10, pady=5, fill="x")
        
        # Create two equal columns for the button and status frame
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(side=tk.LEFT, fill="both", expand=True)
        
        threshold_frame = ttk.Frame(control_frame)
        threshold_frame.pack(side=tk.LEFT, fill="both", expand=True)
        
        status_container = ttk.Frame(control_frame)
        status_container.pack(side=tk.RIGHT, fill="both", expand=True)
        
        threshold_container = ttk.Frame(control_frame)
        threshold_container.pack(side=tk.RIGHT, fill="both", expand=True)
        
        # Label for threshold
        threshold_label = ttk.Label(threshold_container, text="Thresh:")
        threshold_label.pack(side=tk.LEFT, padx=1)

        # Add increment/decrement buttons that update immediately
        dec_button = ttk.Button(threshold_container, text="-", width=2, command=lambda: self.adjust_threshold(-1))
        dec_button.pack(side=tk.LEFT, padx=1)
        
        inc_button = ttk.Button(threshold_container, text="+", width=2, command=lambda: self.adjust_threshold(1))
        inc_button.pack(side=tk.LEFT, padx=1)
        
        # Start threshold controls (inline)
        self.thresh_var = tk.StringVar(value=str(THRESH_START))
        self.thresh_entry = ttk.Entry(threshold_container, width=3, textvariable=self.thresh_var)
        self.thresh_entry.pack(side=tk.LEFT, padx=1)
        
        # Update button (inline)
        update_button = ttk.Button(threshold_container, text="Set", command=self.update_thresholds)
        update_button.pack(side=tk.LEFT, padx=1)
        
        # Add button to left column
        self.record_button = ttk.Button(
            button_frame, text="Start Recording", command=self.toggle_recording
        )
        self.record_button.pack()
        self.status_label = ttk.Label(status_container, text="Stopped")
        self.status_label.pack()

        status_frame = ttk.LabelFrame(self.root, text="System Status")
        status_frame.pack(padx=10, pady=5, fill="both", expand=True)
        status_frame2 = ttk.LabelFrame(self.root, text="Recording Status")
        status_frame2.pack(padx=10, pady=5, fill="both", expand=True)

        self.status_display = tk.Text(status_frame, height=5, wrap="word")
        status_scrollbar = ttk.Scrollbar(
            status_frame, orient="vertical", command=self.status_display.yview
        )
        self.status_display.configure(yscrollcommand=status_scrollbar.set)
        self.status_display.pack(side=tk.LEFT, padx=5, pady=5, fill="both", expand=True)
        status_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.status_display2 = tk.Text(status_frame2, height=1, wrap="word")
        status_scrollbar2 = ttk.Scrollbar(
            status_frame2, orient="vertical", command=self.status_display2.yview
        )
        self.status_display2.configure(yscrollcommand=status_scrollbar2.set)
        self.status_display2.pack(
            side=tk.LEFT, padx=5, pady=5, fill="both", expand=True
        )
        status_scrollbar2.pack(side=tk.RIGHT, fill="y")

        transcribe_frame = ttk.LabelFrame(self.root, text="Transcribed Text")
        transcribe_frame.pack(padx=10, pady=5, fill="both", expand=True)
        self.transcribe_display = tk.Text(transcribe_frame, height=5, wrap="word")
        transcribe_scrollbar = ttk.Scrollbar(
            transcribe_frame, orient="vertical", command=self.transcribe_display.yview
        )
        self.transcribe_display.configure(yscrollcommand=transcribe_scrollbar.set)
        self.transcribe_display.pack(
            side=tk.LEFT, padx=5, pady=5, fill="both", expand=True
        )
        transcribe_scrollbar.pack(side=tk.RIGHT, fill="y")

        ttk.Label(self.root, text="Space: Toggle recording | Esc: Quit").pack(pady=5)

    def start_whisper_server(self):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", self.SERVER_PORT)
            conn.request("GET", "/inference")
            conn.getresponse()
            self.update_STATUS_display("[INFO] Whisper server is already running\n")
        except (http.client.HTTPException, ConnectionRefusedError, socket.error):
            cmd = f"{self.WHISPER_SERVER_PATH} -m {self.WHISPER_MODEL_PATH} --port {self.SERVER_PORT}"
            print(f"Executing: {cmd}")
            self.status_label.config(text="Starting Whisper server...")
            self.update_STATUS_display("[INFO] Starting Whisper server...\n")
            self.cleanup_temp_files()

            # Fork a process to run the Whisper server
            pid = os.fork()
            if pid == 0:  # Child process
                # Redirect stdout and stderr to /dev/null
                with open(os.devnull, "w") as devnull:
                    os.dup2(devnull.fileno(), 1)
                    os.dup2(devnull.fileno(), 2)
                # Execute the Whisper server command with correct path
                os.execv(
                    self.WHISPER_SERVER_PATH,
                    [
                        self.WHISPER_SERVER_PATH,
                        "-m",
                        self.WHISPER_MODEL_PATH,
                        "--port",
                        str(self.SERVER_PORT),
                    ],
                )
            else:  # Parent process
                # Wait for server to start (max 30 seconds)
                start_time = time.time()
                while time.time() - start_time < 30:
                    try:
                        time.sleep(2)  # Give the server some time to start
                        conn = http.client.HTTPConnection("127.0.0.1", self.SERVER_PORT)
                        conn.request("GET", "/inference")
                        conn.getresponse()
                        self.status_label.config(text="Server running")
                        self.update_STATUS_display("[INFO] Whisper server started successfully\n")
                        return
                    except (
                        http.client.HTTPException,
                        ConnectionRefusedError,
                        socket.error,
                    ):
                        self.update_STATUS_display("[INFO] Waiting for server to start...\n")
                        time.sleep(1)
                    except Exception as e:
                        self.update_STATUS_display(f"[ERROR] checking server: {str(e)}\n")

                # If we get here, server failed to start
                self.status_label.config(text="Server start failed")
                self.update_STATUS_display("[ERROR] Failed to start Whisper server\n")
                self.root.update()
                time.sleep(3)
                self.on_closing()

    def toggle_recording(self):
        if self.RECORDING:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        self.RECORDING = True
        self.record_button.config(text="Stop Recording")
        self.status_label.config(text="Recording...")
        self.recording_thread = threading.Thread(target=self.record_AUDIO, daemon=True)
        self.recording_thread.start()

    def stop_recording(self):
        self.RECORDING = False
        self.record_button.config(text="Start Recording")
        self.status_label.config(text="Stopped")
        cmd = "pkill -f 'rec -V -c 1'"
        print(f"Executing: {cmd}")
        try:
            os.system(cmd)
            # Process any remaining audio in the queue
            if os.path.exists(self.current_audio_file):
                self.AUDIO_queue.put(self.current_audio_file)
        except Exception as e:
            self.update_STATUS_display(f"Error stopping recording: {str(e)}\n")

    def record_AUDIO(self):
        self.current_audio_file = ""
        while self.RECORDING:
            tmp_FILE = f"/tmp/voice_{int(time.time())}.mp3"
            self.current_audio_file = tmp_FILE
            cmd = f"rec -V -c 1 -r 22050 -b 16 -e signed-integer -t mp3 {tmp_FILE} silence 1 0.2 3% 1 0.8 4%"
            print(f"Executing: {cmd}")
            self.update_STATUS_display(f"Recording to: {tmp_FILE}\n")

            master, slave = pty.openpty()
            pid = os.fork()
            if pid == 0:
                # Child process
                os.dup2(slave, 0)
                os.dup2(slave, 1)
                os.dup2(slave, 2)
                os.close(slave)
                os.execvp(
                    "rec",
                    [
                        "rec","-V","-c","1","-r","22050","-b","16","-e","signed-integer","-t","mp3","-e","signed-integer",
                        "-t","mp3",tmp_FILE,"silence",
                        "1","0.2",f"{THRESH_START}%",
                        "1","0.8",f"{THRESH_END}%",
                    ],
                )
            else:
                # Parent process
                os.close(slave)

                def read_output():
                    while True:
                        try:
                            data = os.read(master, 1024).decode(
                                "utf-8", errors="ignore"
                            )
                            if not data:
                                break
                            for line in data.splitlines():
                                self.root.after(
                                    0, self.update_recording_display, line + "\n"
                                )
                        except OSError:
                            # Handle Input/output error gracefully
                            break

                thread = threading.Thread(target=read_output, daemon=True)
                thread.start()

                while self.RECORDING and thread.is_alive():
                    time.sleep(0.1)

                if self.RECORDING:
                    # User stopped recording, send SIGINT to rec
                    os.kill(pid, signal.SIGINT)

                thread.join()
                os.waitpid(pid, 0)

                if os.path.exists(tmp_FILE):
                    self.AUDIO_queue.put(tmp_FILE)

    def parse_volume(self, line):
        pattern = r"\[ (.*?)\|.*?\].*"
        match = re.search(pattern, line)
        if match:
            left_bar = match.group(1).strip()
            if "-" in left_bar:
                parts = left_bar.split("-", maxsplit=1)
                if len(parts) == 2:
                    equals_count = parts[1].count("=")
                    if equals_count > 4:
                        equals_count = 4
                    volume_percent = (equals_count / 4) * 100
                    return volume_percent
        return 0
    
    def cleanup_temp_files(self):
        """Clean up any voice temp files that might have been left behind"""
        try:
            temp_dir = "/tmp"
            pattern = "voice_*.mp3"
            count = 0
            
            for filename in os.listdir(temp_dir):
                if fnmatch.fnmatch(filename, pattern):
                    file_path = os.path.join(temp_dir, filename)
                    try:
                        os.remove(file_path)
                        count += 1
                    except Exception as e:
                        self.update_STATUS_display(f"[ERROR] Failed to remove {file_path}: {str(e)}\n")
            
            if count > 0:
                self.update_STATUS_display(f"[INFO] Cleaned up {count} temporary voice files\n")
        except Exception as e:
            self.update_STATUS_display(f"[ERROR] During cleanup: {str(e)}\n") 

    def update_volume_display(self, volume_percent, db):
        self.volume_bar["value"] = volume_percent
        self.volume_value.config(text=f"{db:.1f} dB")

        if volume_percent > 80:
            self.volume_bar.configure(style="Red.Horizontal.TProgressbar")
        elif volume_percent > 40:
            self.volume_bar.configure(style="Green.Horizontal.TProgressbar")
        else:
            self.volume_bar.configure(style="Blue.Horizontal.TProgressbar")

        if volume_percent > 90:
            self.update_STATUS_display("[WARN] Volume is very high!\n")

    def update_STATUS_display(self, text):
        if not text.strip():
            return
        # Print to console
        print(text, end="")
        self.status_display.insert(tk.END, text)
        self.status_display.see(tk.END)
    
    def update_recording_display(self, text):
        if not text.strip():
            return
        # Print to console
        print(text, end="")
        if "In:" in text:
            # Clear previous content first
            self.status_display2.delete(1.0, tk.END)
            # Insert only the current line
            self.status_display2.insert(tk.END, text.strip())
            self.status_display2.see(tk.END)

    def update_transcribe_display(self, text):
        # Print transcribed text to console
        print(f"Transcribed: {text}", end="")
        self.transcribe_display.insert(tk.END, text)
        self.transcribe_display.see(tk.END)

    def process_audio_queue(self):
        while True:
            audio_file = self.AUDIO_queue.get()
            try:
                with open(audio_file, "rb") as f:
                    file_data = f.read()

                # Create a boundary for multipart form data
                boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"

                # Prepare the multipart form data
                body = b""
                # Add the form field
                body += f"--{boundary}\r\n".encode()
                body += f'Content-Disposition: form-data; name="temperature"\r\n\r\n'.encode()
                body += f"0.0\r\n".encode()
                body += f"--{boundary}\r\n".encode()
                body += f'Content-Disposition: form-data; name="response-format"\r\n\r\n'.encode()
                body += f"json\r\n".encode()
                # Add the file
                body += f"--{boundary}\r\n".encode()
                body += f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(audio_file)}"\r\n'.encode()
                body += f"Content-Type: audio/mpeg\r\n\r\n".encode()
                body += file_data
                body += f"\r\n--{boundary}--\r\n".encode()

                # Set up the connection
                conn = http.client.HTTPConnection("127.0.0.1", self.SERVER_PORT)
                headers = {
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": str(len(body)),
                }

                # Send the request
                conn.request("POST", "/inference", body=body, headers=headers)
                response = conn.getresponse()
                response_data = response.read().decode("utf-8")
                response_data = json.loads(response_data)
                
                if "text" not in response_data:
                    self.root.after(0, self.update_STATUS_display, "[WARN] empty response\n")
                    continue

                text = response_data["text"].strip().replace("\n", " ")
                # Remove text enclosed in double asterisks (sound dictation)
                text = re.sub(r"\*.*?\*", "", text)
                if len(text) > 15 or "hank you" not in text:
                    self.root.after(0, self.update_transcribe_display, f"{text}\n")
                    for char in text:
                        self.keyboard.tap(char)
                        time.sleep(0.01)
            except Exception as e:
                self.root.after(0, self.update_STATUS_display, f"[ERROR] Error: {str(e)}\n")
            finally:
                # Always attempt to remove the file, even if processing failed
                if os.path.exists(audio_file):
                    try:
                        os.remove(audio_file)
                        self.root.after(0, self.update_STATUS_display, f"[INFO] Removed temp file: {audio_file}\n")
                    except Exception as e:
                        self.root.after(0, self.update_STATUS_display, f"[ERROR] Failed to remove temp file {audio_file}: {str(e)}\n")
                self.AUDIO_queue.task_done()

            # Restart recording if it was stopped due to silence detection
            if self.RECORDING and not self.recording_thread.is_alive():
                self.recording_thread = threading.Thread(
                    target=self.record_AUDIO, daemon=True
                )
                self.recording_thread.start()

    def on_closing(self):
        self.RECORDING = False
        self.cleanup_temp_files()
        self.root.destroy()

    def update_thresholds(self):
        """Update the threshold values based on user input"""
        try:
            # Get values from entry fields and convert to float
            new_start = float(self.thresh_var.get())
            new_end = float(self.thresh_var.get())
            
            # Update global variables
            global THRESH_START, THRESH_END
            THRESH_START = new_start
            THRESH_END = new_end
            
            # Update the configuration label
            self.config_label.config(
                text=f"Model: {self.MODEL} | Port: {self.SERVER_PORT} | Thresholds: {THRESH_START}%"
            )
            
            # Update the display
            self.update_STATUS_display(f"[INFO] Thresholds updated: Start={THRESH_START}, End={THRESH_END}\n")
            
            # If recording is active, restart it to apply new thresholds
            if self.RECORDING:
                self.stop_recording()
                self.start_recording()
        except ValueError:
            self.update_STATUS_display("[ERROR] Please enter valid numbers for thresholds\n")

    def adjust_threshold(self, amount):
        """Increment or decrement the threshold value and apply immediately"""
        try:
            current = float(self.thresh_var.get())
            new_value = current + amount
            # Ensure threshold doesn't go below 0
            new_value = max(0.0, new_value)
            self.thresh_var.set(f"{new_value:.1f}")
            
            # Apply the change immediately
            self.update_thresholds()
        except ValueError:
            self.update_STATUS_display("[ERROR] Invalid threshold value\n")


def is_already_running():
    """Check if another instance is running using socket binding"""
    try:
        # Try to create and bind a socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", SINGLETON_PORT))
        sock.listen(1)

        # Store socket as attribute to prevent garbage collection
        global singleton_socket
        singleton_socket = sock
        return False
    except socket.error:
        # Port is in use, meaning another instance is running
        return True
    
def activate_existing_window():
    """Try to bring the existing window to the foreground"""
    try:
        # This approach works on most Linux systems
        os.system("wmctrl -a 'Voice Typing'")
        return True
    except Exception:
        return False


if __name__ == "__main__":
    if is_already_running():
        print("Another instance is already running!")
        activate_existing_window()
        sys.exit(1)

    root = tk.Tk()
    app = VoiceTypingGUI(root)
    root.mainloop()
