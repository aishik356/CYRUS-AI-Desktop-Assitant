import os

import ollama
import requests

from config.settings import load_api_settings
from config.user_state import load_user_state
from memory.memory_manager import format_memory_for_prompt


OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


class CyrusBrain:
    def __init__(self, model_name: str = "llama3.2:3b"):
        self.model_name = model_name
        self.base_prompt = (
            "You are CYRUS, a hyper-intelligent, sharp AI desktop operating core. "
            "Keep verbal responses concise, direct, and authoritative. "
            "Use your long-term memory context to answer personal and ongoing project questions naturally. "
            "Never output raw code, JSON schemas, or technical metadata."
        )
        self.backend = "ollama"
        self.openrouter_api_key = ""
        self.openrouter_model = "openrouter/free"
        self._load_settings()
        self.messages = []
        self._refresh_system_prompt()

    def _load_settings(self):
        settings = load_api_settings()
        self.backend = os.getenv(
            "CYRUS_AI_BACKEND", settings.get("ai_backend", "ollama")
        ).strip().lower()
        offline = os.getenv("CYRUS_OFFLINE_MODE", "").strip().lower() in {
            "1", "true", "yes"
        } or bool(load_user_state().get("offline_mode", False))
        if offline and self.backend == "openrouter":
            self.backend = "ollama"
        self.openrouter_api_key = (
            os.getenv("OPENROUTER_API_KEY", "").strip()
            or settings.get("openrouter_api_key", "").strip()
        )
        self.openrouter_model = (
            os.getenv("OPENROUTER_CHAT_MODEL", "").strip()
            or settings.get("openrouter_chat_model", self.openrouter_model).strip()
        )

        if self.backend not in {"ollama", "openrouter"}:
            raise ValueError("ai_backend must be either 'ollama' or 'openrouter'.")
        if self.backend == "openrouter" and not self.openrouter_api_key:
            raise ValueError(
                "OpenRouter is selected, but OPENROUTER_API_KEY is missing from "
                ".env and config/api_keys.json."
            )

    def _refresh_system_prompt(self):
        memory_context = format_memory_for_prompt()
        full_sys_prompt = f"{self.base_prompt}\n{memory_context}"
        if not self.messages:
            self.messages = [{"role": "system", "content": full_sys_prompt}]
        else:
            self.messages[0] = {"role": "system", "content": full_sys_prompt}

    def _think_with_openrouter(self) -> str:
        response = requests.post(
            OPENROUTER_CHAT_URL,
            headers={
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/cyrus-system",
                "X-Title": "CYRUS System",
            },
            json={
                "model": self.openrouter_model,
                "messages": self.messages,
                "max_tokens": 350,
                "temperature": 0.7,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    def think(self, user_query: str) -> str:
        self._refresh_system_prompt()
        self.messages.append({"role": "user", "content": user_query})

        if len(self.messages) > 7:
            self.messages = [self.messages[0]] + self.messages[-6:]

        try:
            if self.backend == "openrouter":
                reply = self._think_with_openrouter()
            else:
                response = ollama.chat(
                    model=self.model_name,
                    messages=self.messages,
                )
                reply = response["message"]["content"].strip()

            if reply.startswith("{") and reply.endswith("}"):
                reply = "Understood."
        except ollama.RequestError as e:
            print(f"[Brain Error]: Ollama is unavailable: {e}")
            reply = "I couldn't reach Ollama. Start Ollama and try again."
        except ollama.ResponseError as e:
            print(f"[Brain Error]: Ollama rejected the request: {e}")
            reply = "Ollama couldn't process that request. Check that the model is installed."
        except (requests.RequestException, KeyError, IndexError, TypeError) as e:
            print(f"[Brain Error]: {self.backend} request failed: {e}")
            if self.backend == "openrouter":
                reply = "I couldn't reach OpenRouter. Check your connection and API key."
            else:
                reply = "I couldn't reach Ollama. Start Ollama and try again."
        except Exception as e:
            print(f"[Brain Error]: {self.backend} request failed: {e}")
            if self.backend == "openrouter":
                reply = "OpenRouter returned an invalid response. Please try again."
            else:
                reply = "Ollama returned an invalid response. Please try again."

        self.messages.append({"role": "assistant", "content": reply})
        return reply
