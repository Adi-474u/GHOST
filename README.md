# 👻 GHOST — Stealth AI Desktop Assistant

GHOST is a real-time AI desktop assistant that can **see your screen, understand context, and respond intelligently** — all running locally using LLMs.

It combines **vision, voice, and system-level interaction** into a minimal, distraction-free overlay.

---

## 🚀 Features

- 🧠 **Local LLM Integration**
  - Uses Ollama for text + vision models
- 👁️ **Screen Understanding**
  - Full screenshot analysis
  - Region-based selection
- 🎤 **Voice Input**
  - Speech-to-text support
- 🔊 **Text-to-Speech**
  - Optional voice responses
- ⚡ **Intent Detection**
  - Automatically detects:
    - Math
    - Coding
    - Aptitude
    - General queries
- 🖥️ **Overlay UI**
  - Lightweight, always-on-top assistant

---

## 🕵️ Stealth Capabilities

- Hidden from screen capture tools (OBS, etc.)
- Not visible in taskbar / Alt+Tab
- Auto-hide during fullscreen apps
- Adjustable opacity (near invisible)

---

## 🧠 How It Works

GHOST dynamically selects models based on input:

- 📝 **Text Queries** → Code, math, reasoning handled by text model  
- 🖼️ **Screenshots** → Vision model analyzes and solves directly  

It combines:
- LLM reasoning
- Computer vision
- System-level window control

---

## 🛠️ Tech Stack

- **Python**
- **Tkinter** (UI)
- **Ollama** (LLM runtime)
- **LLaVA** (vision model)
- **SpeechRecognition**
- **PyTTSx3**
- **Pillow**

---

## ⚙️ Setup

### 1. Install dependencies

```bash
pip install pillow SpeechRecognition pyaudio keyboard pyttsx3 requests
