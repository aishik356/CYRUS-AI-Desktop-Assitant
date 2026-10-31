import os
import io
import json
import base64
import requests
from PIL import Image
import mss

from config.settings import CONFIG_PATH, load_api_settings

# Fallback pool across currently active free vision-capable endpoints
FREE_VISION_MODELS = [
    "openrouter/free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-3-27b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free"
]

def load_openrouter_key() -> str:
    try:
        settings = load_api_settings()
        return os.getenv("OPENROUTER_API_KEY", "").strip() or settings.get(
            "openrouter_api_key", ""
        ).strip()
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(f"[Vision Config Warning]: Could not read {CONFIG_PATH}: {e}")
        return ""

def capture_screen_base64() -> str:
    """Takes an instantaneous hardware snapshot of the primary screen in memory."""
    with mss.mss() as sct:
        # Monitor 1 captures the entire primary display
        monitor = sct.monitors[1]
        sct_img = sct.grab(monitor)
        
        # Convert raw BGRA buffer to standard RGB image
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
        # Downscale proportionally to 1280x720 max for sub-second cloud upload
        img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=78)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

def analyze_screen(prompt: str = "") -> str:
    """Sends the desktop snapshot to OpenRouter's vision pool."""
    api_key = load_openrouter_key()
    if not api_key:
        return "OpenRouter API key is missing. Add OPENROUTER_API_KEY to .env or config/api_keys.json."

    try:
        image_b64 = capture_screen_base64()
    except Exception as e:
        return f"Failed to capture screen display: {e}"

    if not prompt or len(prompt.strip()) < 3:
        prompt = (
            "Look at my screen and tell me what is currently open or displayed. "
            "Whether it is a browser, desktop, folder, or application, describe what you see."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/cyrus-system",
        "X-Title": "CYRUS System"
    }

    system_instruction = (
        "You are the visual sensory system of CYRUS, an AI desktop assistant. "
        "Analyze the provided screenshot of the user's computer monitor. "
        "Identify the active window, application, browser page, desktop icons, or folder contents. "
        "Provide a concise, direct, spoken response summarizing what is visible. "
        "Keep your answer under 3-4 sentences so it sounds natural when spoken aloud."
    )

    # Model fallback loop
    for model_name in FREE_VISION_MODELS:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 250,
            "temperature": 0.2
        }

        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if reply:
                    return reply
        except Exception:
            continue

    return "I was unable to analyze the screen at this moment. The visual server did not respond."