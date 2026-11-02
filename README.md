[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

<div align="center">

<img src="assets/cyrus.png" alt="CYRUS app icon" width="160">

# CYRUS

### Your desktop. Your commands. Your AI assistant.

A Windows desktop assistant with a cyber-style dashboard, local or online AI,
typed chat, optional voice, system tools, timers, web search, and news.

> [!IMPORTANT]
> CYRUS is currently available for **Windows only**. Android, iOS, and macOS
> versions are planned for future updates; they are not available yet.

[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/UI-PyQt6-41CD52?logo=qt&logoColor=white)](https://www.riverbankcomputing.com/software/pyqt/)
[![Ollama](https://img.shields.io/badge/AI-Ollama-black?logo=ollama&logoColor=white)](https://ollama.com/)
[![DuckDuckGo](https://img.shields.io/badge/Search-DuckDuckGo-DE5833?logo=duckduckgo&logoColor=white)](https://duckduckgo.com/)
[![Releases](https://img.shields.io/badge/Downloads-GitHub%20Releases-181717?logo=github&logoColor=white)](https://github.com/aishik356/CYRUS-AI-Desktop-Assitant/releases)

**[Explore the code](https://github.com/aishik356/CYRUS-AI-Desktop-Assitant)**
· **[Download releases](https://github.com/aishik356/CYRUS-AI-Desktop-Assitant/releases)**
· **[Report a problem](https://github.com/aishik356/CYRUS-AI-Desktop-Assitant/issues)**

</div>

> [!NOTE]
> CYRUS runs as a Windows desktop app. GitHub hosts its source and downloadable
> releases; it does not host the running assistant or provide a built-in
> database of everything in the world.

## CYRUS v1.1

This release improves microphone transcription and safe mic toggling, adds
common command typo correction, makes timer/reminder countdowns and alarms
more reliable, and includes the custom reminder sound. It also improves
personalized local-time greetings and YouTube search/play commands.

**Only the Windows installer is provided.** The portable download is omitted
because users reported inconsistent startup and microphone behavior with that
package. The installer remains the supported distribution while those
portable reliability issues are avoided.

## ✨ What it can do

- **Chat your way:** use the dashboard chat box, with an optional manually
  enabled microphone. The microphone starts muted; there is no always-listening
  wake word. CYRUS uses context to interpret ordinary typing mistakes and
  corrects common misspellings in supported command words.
- **Choose an AI backend:** installed/source builds offer Ollama or OpenRouter
  during first-run setup.
- **Speak and listen:** use the bundled local Piper Alan voice for speech
  output and Google's online speech recognition for microphone input.
- **Find information:** search the web and current news with DuckDuckGo. CYRUS
  returns a limited set of snippets and links, not exhaustive or guaranteed
  complete coverage.
- **Control your PC:** view hardware and live resource reports, launch
  applications, adjust Windows and player volume, and use optional VLC music
  controls.
- **Stay on schedule:** create timers and reminders with dashboard countdowns.
  Reminders can use a duration or a calendar date/time; a date without a time
  defaults to 9:00 AM local time.
- **Personalize greetings:** set the name CYRUS uses for you; greetings use the
  computer's current local time and public holidays for the automatically
  detected system region.
- **Customize the dashboard:** arrange its panels and adjust its appearance.

## 🚀 Download and install

Open **[GitHub Releases](https://github.com/aishik356/CYRUS-AI-Desktop-Assitant/releases)**
and download `CYRUS-Setup.exe`. Version 1.1 provides the installer only; no
portable application package is published. Run the installer to choose an
install folder and optional features. No Python commands or
`requirements.txt` installation are needed for the packaged app; the installer
bundles CYRUS and its Python dependencies.

> [!IMPORTANT]
> Ollama and VLC are separate apps and are not bundled. CYRUS can offer to
> download the Ollama model during setup, but Ollama itself must already be
> installed. Windows may show an unknown-publisher warning because the
> installer is not code-signed.

The setup lets you choose these optional features:

| Feature | Notes |
| --- | --- |
| Alan voice output | Bundled local voice model; no separate download is needed; review its upstream terms |
| Microphone input | Internet is required for Google's speech-recognition service; starts muted |
| Web search and news | Internet required; uses DuckDuckGo |
| VLC music controls | VLC must be installed separately |
| Screen analysis | Requires an OpenRouter API key; screenshots are sent when analysis is requested |

The local Ollama model `llama3.2:3b` is several gigabytes and is an optional,
separate download. OpenRouter keys are verified during setup and stored in
local configuration; free keys are restricted to free models.

## 🛠️ Run from source

### Requirements

- Windows 10/11, 64-bit
- Python 3.11
- Ollama running locally or an OpenRouter API key
- VLC installed separately if you want music playback

### Install Python dependencies

Open PowerShell in the project folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks environment activation, allow it for the current terminal
and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Configure the AI backend

On first launch, choose Ollama or OpenRouter. For local AI, [install
Ollama](https://ollama.com/download) and pull CYRUS's model:

```powershell
ollama pull llama3.2:3b
```

Keep Ollama running while using the local backend. For OpenRouter, CYRUS
prompts for a key, verifies its tier, and stores the provider settings locally.
Paid keys use a premium default model; free keys are locked to free models.

After provider setup, first launch asks what name CYRUS should use for the
current Windows user. Time-of-day greetings use the system's current local
timezone; public holiday names come from the installed `holidays` package and
the automatically detected Windows country/region.

Date-based reminders accept ISO dates or written dates, for example:

```text
remind me on 2026-10-15 at 3:00 PM that my interview is scheduled
remind me on 15th of October 2026 that I have an interview
```

If no time is included, the reminder is scheduled for 9:00 AM local time.
A time-only reminder such as `set a reminder for 5:15 PM to call home` uses the
next occurrence in the computer's local timezone. Timers and reminders remain
separate types. A named reminder such as `set a reminder for 10 seconds named stretch`
keeps its name when the alarm fires.

When a timer or reminder is due, CYRUS displays an alert and rings without
speaking the reminder aloud. The Windows build bundles the provided alarm
sound. To override it for one Windows user, place a WAV file at
`%LOCALAPPDATA%\CYRUS\reminder_alarm.wav`; if neither file is available, CYRUS
generates a default alarm tone.

### Configure optional Alan speech

The Windows builds and installer bundle the Alan voice files; setup does not
offer a separate Alan download. For source runs where the assets are missing,
download both files from the
[upstream Alan voice folder on Hugging Face](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB/alan/medium):

- [Download the Alan ONNX model](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx?download=true)
- [Download its voice configuration](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json?download=true)

Save both files, with their original names, in the project's `voices` folder:

```text
CYRUS/
└── voices/
    ├── en_GB-alan-medium.onnx
    └── en_GB-alan-medium.onnx.json
```

The user-level directory `%LOCALAPPDATA%\CYRUS\voices\` can also hold a
downloaded copy. The model card points to a source marked **All Rights
Reserved**; review the
[upstream model card and terms](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB/alan/medium)
before downloading or using the voice.

### Start CYRUS

```powershell
python main.py
```

CYRUS performs startup checks and warns about unavailable features without
preventing the dashboard from opening. The microphone remains muted until you
enable it using the dashboard control or F3/Ctrl+M.

## 🔨 Build the Windows installer

Set up the Python build environment with the project requirements and
`requirements-build.txt`, and install [Inno Setup 6](https://jrsoftware.org/isinfo.php):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build_windows.ps1
```

The build script creates a temporary runtime folder for packaging, then removes
it after compiling the setup package. The distributable output is:

- Installer: `dist\installer\CYRUS-Setup.exe`

The installer requests administrator approval through UAC and offers a custom
install location, optional features, and a desktop shortcut. It can optionally
download the Ollama model after installation; that download is not required
to build the installer.

## 🌦️ Search, weather, and media

- Ask for current conditions by city, or a seven-day forecast. Named-location
  weather uses Open-Meteo. If no city is specified, CYRUS estimates your
  location using your public IP.
- Ask for news or current events to get live DuckDuckGo news results; use
  `search for ...` for general web results. Search is not a guarantee of
  complete or exhaustive answers.
- Open supported applications and websites with chat or voice commands.
- Ask CYRUS to search YouTube or open and play the first matching video in the
  default browser. Music search and queue controls use VLC, which must be
  installed for the local player integration.
- Explicit Google and Spotify searches open results in the default browser;
  Spotify play requests open matching results for the user to select.
- Set timers and reminders using natural-language requests.

## 🔊 Audio controls

- **VOICE** changes CYRUS's Piper speech loudness.
- **SYSTEM** changes the Windows master volume and tracks external Windows
  volume changes.
- **PLAYER** changes VLC music playback independently.

The slider values are saved for the current user. Existing typed and voice
volume commands remain available.

## 🔐 Privacy and network use

- Typed conversations use the selected provider. With OpenRouter, prompts and
  the memory context included with them are sent online.
- When enabled, microphone speech is sent to Google's online
  speech-recognition service. The microphone starts muted.
- A screen-analysis request sends a screenshot to OpenRouter.
- Web/news queries go to DuckDuckGo. Weather uses Open-Meteo and IP-based
  geolocation when no location is given.
- Alan speech synthesis is local; packaged builds include the model files.
- Personal API keys, local `config.json`, `.env`, memory, build outputs, and
  downloaded voice models are excluded from Git. **Never commit credentials or
  personal data.**

Use voice and screen-analysis features with sensitive information only if
you're comfortable with these data flows. Offline mode disables online AI,
search, weather, websites, YouTube playback, screen analysis, and cloud speech
input while retaining local system tools, reminders, and local Ollama chat.

## 🧩 Technology

<p>
  <a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white"></a>
  <a href="https://www.riverbankcomputing.com/software/pyqt/"><img alt="PyQt6" src="https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt&logoColor=white"></a>
  <a href="https://ollama.com/"><img alt="Ollama" src="https://img.shields.io/badge/Local_AI-Ollama-black?logo=ollama&logoColor=white"></a>
  <a href="https://github.com/rhasspy/piper"><img alt="Piper" src="https://img.shields.io/badge/Voice-Piper-7B68EE"></a>
  <a href="https://duckduckgo.com/"><img alt="DuckDuckGo" src="https://img.shields.io/badge/Web-DuckDuckGo-DE5833?logo=duckduckgo&logoColor=white"></a>
  <a href="https://pyinstaller.org/"><img alt="PyInstaller" src="https://img.shields.io/badge/Packaging-PyInstaller-FFD43B"></a>
</p>

## 🤝 Contributing

Bug reports and suggestions are welcome through
[GitHub Issues](https://github.com/aishik356/CYRUS-AI-Desktop-Assitant/issues).
Please don't include API keys, personal memory, or sensitive screenshots in
issues.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
