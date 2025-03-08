# GUI Voice Keyboard for Minimalist Linux Users

A lightweight voice keyboard using `whisper.cpp` for minimalist Linux users. This project integrates with function key shortcuts—press a key, and a GUI appears for dictating text. It runs the Whisper server locally, ensuring privacy without external APIs.

Built for minimalism, it uses a basic Python installation with standard libraries. The GUI leverages Tkinter and relies solely on Python's built-in system libraries.

## Features
- Simple GUI triggered by keyboard shortcuts
- Local processing—no internet required
- Minimal resource usage
- Compatible with any app accepting keyboard input

## Installation

### Dependencies
1. **whisper.cpp**  
   - Clone and build:  
     ```bash
     git clone https://github.com/ggerganov/whisper.cpp.git && cd whisper.cpp && make
     ```
   - Ensure the `whisper` binary is in your PATH or note its location in the client.py file.
   - For CUDA support, follow the whisper.cpp repository's CUDA build instructions and use the appropriate commands.

2. **Python**  
   - Requires Python 3.6+ with standard libraries (Tkinter included in most distributions).
   - Verify Tkinter:
     ```bash
     python3 -c "import tkinter"
     ```
   - If missing, install (e.g., on Debian/Ubuntu):
     ```bash
     sudo apt install python3-tk
     ```

3. **Clone this Repository**  
   ```bash
   git clone https://github.com/daebangstn/voicekbd.git && cd voicekbd
   ```

### Usage
1. Configure a keyboard shortcut (e.g., F12) to launch the script:
   ```bash
   python3 voice_keyboard.py
   ```
   Use your desktop environment’s shortcut settings or a tool like xbindkeys.

2. Press the configured shortcut to launch the GUI.
3. Dictate your text.
4. whisper.cpp processes the audio locally.
5. Recognized text is typed at your cursor position.

## Inspiration
Inspired by voice_typing, a cutting-edge voice typing tool for Linux terminals.

## License
GPL-2.0 License

## Usage
Configure a keyboard shortcut (e.g., F12) to launch the script:

Use your desktop environment’s shortcut settings or a tool like xbindkeys.
Press the shortcut to open the GUI, speak, and insert text at your cursor.

## Inspiration
Inspired by voice_typing, a cutting-edge voice typing tool for Linux terminals.

## License
GPL-2.0 License