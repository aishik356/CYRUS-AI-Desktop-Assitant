import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from main import FileInspectionWorker, ProviderSetupWorker, StartupConfigurationWorker


class BackendWorkerTests(unittest.TestCase):
    def test_file_inspection_reads_preview_in_worker(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "notes.txt"
            file_path.write_text("A short file preview.", encoding="utf-8")
            worker = FileInspectionWorker(str(file_path))
            results = []
            worker.completed.connect(lambda *result: results.append(result))

            worker.run()

        self.assertEqual(len(results), 1)
        self.assertIn("A short file preview.", results[0][0])
        self.assertIn("notes.txt loaded", results[0][1])

    def test_file_inspection_reports_files_removed_before_read(self):
        worker = FileInspectionWorker("missing-file.txt")
        errors = []
        worker.failed.connect(lambda *error: errors.append(error))

        worker.run()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], "missing-file.txt")
        self.assertIn("no longer exists", errors[0][1])

    @patch("main.has_saved_api_settings", return_value=True)
    @patch("main.load_api_settings", return_value={"ai_backend": "ollama"})
    def test_startup_configuration_reads_settings_in_worker(
        self, _load_settings, _has_saved_settings
    ):
        worker = StartupConfigurationWorker()
        results = []
        worker.completed.connect(lambda *result: results.append(result))

        worker.run()

        self.assertEqual(results, [({"ai_backend": "ollama"}, True)])

    @patch("main.configure_ollama", side_effect=requests.ConnectionError("offline"))
    def test_provider_worker_marks_connection_errors_for_offline_fallback(
        self, _configure_ollama
    ):
        worker = ProviderSetupWorker("ollama")
        failures = []
        worker.failed.connect(lambda *failure: failures.append(failure))

        worker.run()

        self.assertEqual(failures[0][0], "ollama")
        self.assertIn("offline", failures[0][1])
        self.assertTrue(failures[0][2])

    @patch(
        "main.configure_ollama",
        return_value={"ollama_host": "http://localhost:11434"},
    )
    def test_provider_worker_reports_verified_provider(self, _configure_ollama):
        worker = ProviderSetupWorker("ollama")
        providers = []
        worker.completed.connect(providers.append)

        with patch.dict("os.environ"):
            worker.run()

        self.assertEqual(providers, ["ollama"])

    def test_provider_worker_does_not_treat_invalid_key_as_offline(
        self,
    ):
        response = requests.Response()
        response.status_code = 401
        worker = ProviderSetupWorker("openrouter", "invalid")
        failures = []
        worker.failed.connect(lambda *failure: failures.append(failure))

        with patch(
            "main.configure_openrouter",
            side_effect=requests.HTTPError("invalid API key", response=response),
        ):
            worker.run()

        self.assertFalse(failures[0][2])


if __name__ == "__main__":
    unittest.main()
