import os
from datetime import datetime

import ollama
import requests

from config.settings import PORTABLE_MODE, load_api_settings
from config.user_state import load_user_state
from memory.memory_manager import format_memory_for_prompt


OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-3.5-sonnet"
DEFAULT_OPENROUTER_FREE_MODEL = "openrouter/free"


class CyrusBrain:
    def __init__(self, model_name: str = "llama3.2:3b"):
        self.model_name = model_name
        self.base_prompt = (
            "You are CYRUS, a hyper-intelligent, sharp AI desktop operating core. "
            "Keep verbal responses concise, direct, and authoritative. "
            "Interpret ordinary spelling and typing mistakes from the user "
            "using the surrounding context; ask a brief clarifying question "
            "when the intended meaning is genuinely ambiguous. "
            "Use your long-term memory context to answer personal and ongoing project questions naturally. "
            "Never output raw code, JSON schemas, or technical metadata."
        )
        self.backend = "ollama"
        self.openrouter_api_key = ""
        self.openrouter_model = DEFAULT_OPENROUTER_MODEL
        self.openrouter_key_tier = "free"
        self.ollama_host = "http://localhost:11434"
        self.offline_mode = False
        self.on_network_error = None
        self._load_settings()
        self.ollama_client = ollama.Client(host=self.ollama_host)
        self.messages = []
        self._refresh_system_prompt()

    def _load_settings(self):
        settings = load_api_settings()
        configured_backend = os.getenv(
            "CYRUS_AI_BACKEND", settings.get("ai_backend", "ollama")
        )
        self.backend = (
            "openrouter"
            if PORTABLE_MODE
            else str(configured_backend).strip().lower()
        )
        offline = os.getenv("CYRUS_OFFLINE_MODE", "").strip().lower() in {
            "1", "true", "yes"
        } or bool(load_user_state().get("offline_mode", False))
        self.offline_mode = offline
        if not PORTABLE_MODE and offline and self.backend == "openrouter":
            self.backend = "ollama"
        self.openrouter_api_key = (
            os.getenv("OPENROUTER_API_KEY", "").strip()
            or str(settings.get("openrouter_api_key", "") or "").strip()
        )
        self.openrouter_model = (
            os.getenv("OPENROUTER_CHAT_MODEL", "").strip()
            or str(
                settings.get("openrouter_chat_model")
                or DEFAULT_OPENROUTER_MODEL
            ).strip()
        )
        self.openrouter_key_tier = str(
            settings.get("openrouter_key_tier") or "free"
        ).strip().lower()
        if self.openrouter_key_tier != "paid":
            self.openrouter_key_tier = "free"
            if self.openrouter_model != DEFAULT_OPENROUTER_FREE_MODEL and not (
                self.openrouter_model.endswith(":free")
            ):
                self.openrouter_model = DEFAULT_OPENROUTER_FREE_MODEL
        self.ollama_host = str(
            settings.get(
                "ollama_host",
                os.getenv("OLLAMA_HOST", self.ollama_host),
            )
            or self.ollama_host
        ).strip()

        if self.backend not in {"ollama", "openrouter"}:
            raise ValueError("ai_backend must be either 'ollama' or 'openrouter'.")
        if (
            self.backend == "openrouter"
            and not self.openrouter_api_key
            and not self.offline_mode
        ):
            raise ValueError(
                "OpenRouter is selected, but OPENROUTER_API_KEY is missing from "
                "local environment or application settings."
            )

    def _refresh_system_prompt(self):
        memory_context = format_memory_for_prompt()
        user_state = load_user_state()
        preferred_name = str(user_state.get("preferred_name", "")).strip()
        identity_instruction = (
            f"Address the user only as {preferred_name!r}; do not use titles, "
            "alternate names, or honorifics."
            if preferred_name
            else "Do not address the user with a title or honorific."
        )
        local_time = datetime.now().astimezone()
        local_context = (
            "\n[LOCAL USER CONTEXT]\n"
            f"Current local date and time: {local_time.isoformat()}\n"
            f"{identity_instruction}\n"
            "[END LOCAL USER CONTEXT]"
        )
        full_sys_prompt = f"{self.base_prompt}\n{memory_context}\n{local_context}"
        if not self.messages:
            self.messages = [{"role": "system", "content": full_sys_prompt}]
        else:
            self.messages[0] = {"role": "system", "content": full_sys_prompt}

    def _notify_network_error(self, error):
        self.offline_mode = True
        callback = self.on_network_error
        if callback is not None:
            callback(error)

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
        if PORTABLE_MODE and self.offline_mode:
            return "OpenRouter is unavailable while offline mode is enabled."
        self.messages.append({"role": "user", "content": user_query})

        if len(self.messages) > 7:
            self.messages = [self.messages[0]] + self.messages[-6:]

        try:
            if self.backend == "openrouter":
                reply = self._think_with_openrouter()
            else:
                response = self.ollama_client.chat(
                    model=self.model_name,
                    messages=self.messages,
                )
                reply = response["message"]["content"].strip()

            if reply.startswith("{") and reply.endswith("}"):
                reply = "Understood."
        except ollama.RequestError as e:
            print(f"[Brain Error]: Ollama is unavailable: {e}")
            self._notify_network_error(e)
            reply = "I couldn't reach Ollama. Start Ollama and try again."
        except ollama.ResponseError as e:
            print(f"[Brain Error]: Ollama rejected the request: {e}")
            reply = "Ollama couldn't process that request. Check that the model is installed."
        except (requests.RequestException, KeyError, IndexError, TypeError) as e:
            print(f"[Brain Error]: {self.backend} request failed: {e}")
            if isinstance(e, requests.RequestException):
                status_code = getattr(e.response, "status_code", None)
                if (
                    not isinstance(e, requests.HTTPError)
                    or status_code is None
                    or status_code >= 500
                ):
                    self._notify_network_error(e)
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
