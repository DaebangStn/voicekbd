#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
import pty
import os
import threading
import signal
import re
import numpy as np
import time
import queue
import requests
import json
import pynput

SHOW_VOLUME = False
MODEL = "large-v3-turbo-q8_0"
SERVER_PORT = 7654
WHISPER_SERVER_PATH = "/home/geon/voicekbd/whisper.cpp/build/bin/whisper-server"
WHISPER_MODEL_PATH = f"/home/geon/voicekbd/whisper.cpp/models/ggml-{MODEL}.bin"

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
        self.processing_thread = threading.Thread(target=self.process_audio_queue, daemon=True)
        self.processing_thread.start()
        
        self.root.focus_force()
        self.start_recording()

    def setup_ui(self):
        style = ttk.Style()
        style.configure("Red.Horizontal.TProgressbar", foreground="red", background="red")
        style.configure("Green.Horizontal.TProgressbar", foreground="green", background="green")
        style.configure("Blue.Horizontal.TProgressbar", foreground="blue", background="blue")
        
        config_frame = ttk.LabelFrame(self.root, text="Configuration")
        config_frame.pack(padx=10, pady=5, fill="x")
        ttk.Label(config_frame, text=f"Model: {self.MODEL} | Port: {self.SERVER_PORT}").pack(pady=2, side=tk.LEFT)
        
        control_frame = ttk.Frame(self.root)
        control_frame.pack(padx=10, pady=5, fill="x")
        self.record_button = ttk.Button(control_frame, text="Start Recording", command=self.toggle_recording)
        self.record_button.pack(fill="x")
        
        if SHOW_VOLUME:
            volume_frame = ttk.LabelFrame(self.root, text="Microphone Volume")
            volume_frame.pack(padx=10, pady=5, fill="x")
            self.volume_bar = ttk.Progressbar(volume_frame, length=300, maximum=100, style="Blue.Horizontal.TProgressbar")
            self.volume_bar.pack(pady=5)
            self.volume_value = ttk.Label(volume_frame, text="0.0 dB")
            self.volume_value.pack(pady=5)
        
        status_frame = ttk.LabelFrame(self.root, text="Mic Status and Errors")
        status_frame.pack(padx=10, pady=5, fill="both", expand=True)
        status_frame2 = ttk.LabelFrame(self.root, text="Recording Status")
        status_frame2.pack(padx=10, pady=5, fill="both", expand=True)
        self.status_label = ttk.Label(status_frame, text="Stopped")
        self.status_label.pack(pady=5)
        self.status_display = tk.Text(status_frame, height=5, wrap="word")
        status_scrollbar = ttk.Scrollbar(status_frame, orient="vertical", command=self.status_display.yview)
        self.status_display.configure(yscrollcommand=status_scrollbar.set)
        self.status_display.pack(side=tk.LEFT, padx=5, pady=5, fill="both", expand=True)
        status_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.status_display2 = tk.Text(status_frame2, height=1, wrap="word")
        status_scrollbar2 = ttk.Scrollbar(status_frame2, orient="vertical", command=self.status_display2.yview)
        self.status_display2.configure(yscrollcommand=status_scrollbar2.set)
        self.status_display2.pack(side=tk.LEFT, padx=5, pady=5, fill="both", expand=True)
        status_scrollbar2.pack(side=tk.RIGHT, fill="y")
        
        transcribe_frame = ttk.LabelFrame(self.root, text="Transcribed Text")
        transcribe_frame.pack(padx=10, pady=5, fill="both", expand=True)
        self.transcribe_display = tk.Text(transcribe_frame, height=5, wrap="word")
        transcribe_scrollbar = ttk.Scrollbar(transcribe_frame, orient="vertical", command=self.transcribe_display.yview)
        self.transcribe_display.configure(yscrollcommand=transcribe_scrollbar.set)
        self.transcribe_display.pack(side=tk.LEFT, padx=5, pady=5, fill="both", expand=True)
        transcribe_scrollbar.pack(side=tk.RIGHT, fill="y")
        
        ttk.Label(self.root, text="Space: Toggle recording | Esc: Quit").pack(pady=5)

    def start_whisper_server(self):
        try:
            requests.get(self.SERVER_URL, timeout=1)
            self.update_STATUS_display("Whisper server is already running\n")
        except requests.ConnectionError:
            cmd = f"{self.WHISPER_SERVER_PATH} -m {self.WHISPER_MODEL_PATH} --port {self.SERVER_PORT}"
            print(f"Executing: {cmd}")
            self.status_label.config(text="Starting Whisper server...")
            self.update_STATUS_display("Starting Whisper server...\n")
            
            # Fork a process to run the Whisper server
            pid = os.fork()
            if pid == 0:  # Child process
                # Redirect stdout and stderr to /dev/null
                with open(os.devnull, 'w') as devnull:
                    os.dup2(devnull.fileno(), 1)
                    os.dup2(devnull.fileno(), 2)
                # Execute the Whisper server command with correct path
                os.execv(self.WHISPER_SERVER_PATH, 
                        [self.WHISPER_SERVER_PATH, '-m', self.WHISPER_MODEL_PATH, 
                         '--port', str(self.SERVER_PORT)])
            else:  # Parent process
                # Wait for server to start (max 30 seconds)
                start_time = time.time()
                while time.time() - start_time < 30:
                    try:
                        time.sleep(2)  # Give the server some time to start
                        requests.get(self.SERVER_URL)
                        self.status_label.config(text="Server running")
                        self.update_STATUS_display("Whisper server started successfully\n")
                        return
                    except requests.ConnectionError:
                        self.update_STATUS_display("Waiting for server to start...\n")
                        time.sleep(1)
                    except Exception as e:
                        self.update_STATUS_display(f"Error checking server: {str(e)}\n")
                
                # If we get here, server failed to start
                self.status_label.config(text="Server start failed")
                self.update_STATUS_display("Failed to start Whisper server\n")
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
                os.execvp('rec', ['rec', '-V', '-c', '1', '-r', '22050', '-b', '16', '-e', 'signed-integer', '-t', 
                                  'mp3', tmp_FILE, 'silence', '1', '0.2', '3%', '1', '0.8', '4%'])
            else:
                # Parent process
                os.close(slave)
                
                def read_output():
                    while True:
                        try:
                            data = os.read(master, 1024).decode('utf-8', errors='ignore')
                            if not data:
                                break
                            for line in data.splitlines():
                                self.root.after(0, self.update_STATUS_display, line + "\n")
                                if SHOW_VOLUME:
                                    volume_percent = self.parse_volume(line)
                                    db = -80 + (volume_percent / 100) * 80
                                    self.update_volume_display(volume_percent, db)
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
        pattern = r'\[ (.*?)\|.*?\].*'
        match = re.search(pattern, line)
        if match:
            left_bar = match.group(1).strip()
            if '-' in left_bar:
                parts = left_bar.split('-', maxsplit=1)
                if len(parts) == 2:
                    equals_count = parts[1].count('=')
                    if equals_count > 4:
                        equals_count = 4
                    volume_percent = (equals_count / 4) * 100
                    return volume_percent
        return 0

    def update_volume_display(self, volume_percent, db):
        self.volume_bar['value'] = volume_percent
        self.volume_value.config(text=f"{db:.1f} dB")
        
        if volume_percent > 80:
            self.volume_bar.configure(style="Red.Horizontal.TProgressbar")
        elif volume_percent > 40:
            self.volume_bar.configure(style="Green.Horizontal.TProgressbar")
        else:
            self.volume_bar.configure(style="Blue.Horizontal.TProgressbar")
        
        if volume_percent > 90:
            self.update_STATUS_display("Warning: Volume is very high!\n")

    def update_STATUS_display(self, text):
        if not text.strip():
            return
        # Print to console
        print(text, end='')
        if "In:" in text:
            self.status_display2.insert(tk.END, text)
            self.status_display2.see(tk.END)
        else:
            self.status_display.insert(tk.END, text)
            self.status_display.see(tk.END)

    def update_transcribe_display(self, text):
        # Print transcribed text to console
        print(f"Transcribed: {text}", end='')
        self.transcribe_display.insert(tk.END, text)
        self.transcribe_display.see(tk.END)

    def process_audio_queue(self):
        while True:
            audio_file = self.AUDIO_queue.get()
            try:
                with open(audio_file, 'rb') as f:
                    response = requests.post(
                        self.SERVER_URL,
                        files={"file": f},
                        data={"temperature": "0.0", "response-format": "json"}
                    )
                text = json.loads(response.text)["text"].strip().replace('\n', ' ')
                if len(text) > 15 or "hank you" not in text:
                    self.root.after(0, self.update_transcribe_display, f"{text}\n")
                    for char in text:
                        self.keyboard.tap(char)
                        time.sleep(0.01)
            except Exception as e:
                self.root.after(0, self.update_STATUS_display, f"Error: {str(e)}\n")
            if os.path.exists(audio_file):
                os.remove(audio_file)
            self.AUDIO_queue.task_done()
            
            # Restart recording if it was stopped due to silence detection
            if self.RECORDING and not self.recording_thread.is_alive():
                self.recording_thread = threading.Thread(target=self.record_AUDIO, daemon=True)
                self.recording_thread.start()

    def on_closing(self):
        self.RECORDING = False
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = VoiceTypingGUI(root)
    root.mainloop()
    