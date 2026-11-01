import os
import sys
import math
import time
import getpass
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path
from array import array
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QPoint, QRectF
from PyQt6.QtWidgets import (
    QApplication, QWidget, QFileDialog, QDialog, QCheckBox, QComboBox,
    QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QSlider, QVBoxLayout, QFrame, QTextEdit, QLineEdit, QProgressBar, QInputDialog,
    QGraphicsDropShadowEffect, QSizePolicy,
)
from PyQt6.QtGui import (
    QPainter, QColor, QCloseEvent, QFont, QPen, QBrush,
    QConicalGradient, QRadialGradient, QLinearGradient
)

from config.user_state import load_user_state, save_user_state
from config.features import load_installed_features
from config.settings import PROJECT_ROOT, get_user_data_dir

try:
    import winsound
except ImportError:
    winsound = None


# Optional psutil for live system metrics (with graceful fallback)
try:
    import psutil
except ImportError:
    psutil = None


# --- High-Tech Cyber Frame with Glowing Corner Brackets ---
class CyberPanel(QFrame):
    """
    A stylized futuristic panel featuring HUD chamfered corner brackets
    and a subtle semi-translucent cyber matrix background.
    """
    def __init__(self, parent=None, corner_len=14, corner_color=QColor(0, 240, 255, 230), border_color=QColor(0, 240, 255, 55)):
        super().__init__(parent)
        self.corner_len = corner_len
        self.corner_color = corner_color
        self.border_color = border_color
        self.setStyleSheet("""
            CyberPanel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(10, 16, 29, 235), 
                    stop:1 rgba(6, 10, 18, 245));
                border: 1px solid rgba(0, 240, 255, 45);
                border-radius: 10px;
            }
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cl = self.corner_len

        # Glowing Corner Brackets (HUD Reticle Style)
        pen = QPen(self.corner_color, 2)
        painter.setPen(pen)

        # Top-Left
        painter.drawLine(1, 1, 1 + cl, 1)
        painter.drawLine(1, 1, 1, 1 + cl)

        # Top-Right
        painter.drawLine(w - 2, 1, w - 2 - cl, 1)
        painter.drawLine(w - 2, 1, w - 2, 1 + cl)

        # Bottom-Left
        painter.drawLine(1, h - 2, 1 + cl, h - 2)
        painter.drawLine(1, h - 2, 1, h - 2 - cl)

        # Bottom-Right
        painter.drawLine(w - 2, h - 2, w - 2 - cl, h - 2)
        painter.drawLine(w - 2, h - 2, w - 2, h - 2 - cl)


# --- Glowing Arc Reactor Core Widget ---
class ArcReactorWidget(QWidget):
    """
    High-tech multi-layered Quantum Arc Reactor Core with rotating segmented rings,
    calibrated dial reticles, counter-rotating energy teeth, and pulsating center fusion core.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle_outer = 0
        self.angle_inner = 0
        self.angle_core = 0
        self.pulse_phase = 0.0

        self.setMinimumSize(280, 280)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.timer.start(25)

    @property
    def angle(self):
        """Backwards compatibility for external references."""
        return self.angle_outer

    @angle.setter
    def angle(self, val):
        self.angle_outer = val

    def rotate(self):
        self.angle_outer = (self.angle_outer + 1.5) % 360
        self.angle_inner = (self.angle_inner - 2.2) % 360
        self.angle_core = (self.angle_core + 3.0) % 360
        self.pulse_phase = (self.pulse_phase + 0.07) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        center_x = width / 2.0
        center_y = height / 2.0
        radius = max(min(width, height) / 2.0 - 22, 50)
        pulse = 0.90 + 0.10 * math.sin(self.pulse_phase)

        # 1. Subtle Background Reticle & Guide Rings
        faint_pen = QPen(QColor(0, 240, 255, 30), 1)
        painter.setPen(faint_pen)
        painter.drawEllipse(QPoint(int(center_x), int(center_y)), int(radius * 0.96), int(radius * 0.96))
        painter.drawEllipse(QPoint(int(center_x), int(center_y)), int(radius * 0.76), int(radius * 0.76))
        painter.drawEllipse(QPoint(int(center_x), int(center_y)), int(radius * 0.52), int(radius * 0.52))
        painter.drawEllipse(QPoint(int(center_x), int(center_y)), int(radius * 0.30), int(radius * 0.30))

        # Crosshair axis lines
        reticle_pen = QPen(QColor(0, 240, 255, 45), 1, Qt.PenStyle.DashLine)
        painter.setPen(reticle_pen)
        painter.drawLine(int(center_x - radius), int(center_y), int(center_x + radius), int(center_y))
        painter.drawLine(int(center_x), int(center_y - radius), int(center_x), int(center_y + radius))

        # 2. Calibrated Outer Dial Ring with Notches
        outer_ring_pen = QPen(QColor(0, 240, 255, 90), 1.5)
        painter.setPen(outer_ring_pen)
        painter.drawEllipse(QPoint(int(center_x), int(center_y)), int(radius), int(radius))

        for i in range(36):
            deg = i * 10
            rad = math.radians(deg)
            is_cardinal = (deg % 90 == 0)
            is_major = (deg % 30 == 0)
            tick_len = 9 if is_cardinal else (6 if is_major else 3)
            alpha = 240 if is_cardinal else (180 if is_major else 90)

            tick_pen = QPen(QColor(0, 240, 255, alpha), 2 if is_cardinal else 1)
            painter.setPen(tick_pen)

            r_out = radius
            r_in = radius - tick_len
            x1 = center_x + r_out * math.cos(rad)
            y1 = center_y + r_out * math.sin(rad)
            x2 = center_x + r_in * math.cos(rad)
            y2 = center_y + r_in * math.sin(rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # 3. Rotating Outer Segmented Arcs
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self.angle_outer)

        arc_pen = QPen(QColor(0, 240, 255, 230), 4)
        painter.setPen(arc_pen)
        outer_rect = QRectF(-radius + 12, -radius + 12, (radius - 12) * 2, (radius - 12) * 2)
        painter.drawArc(outer_rect, 0 * 16, 75 * 16)
        painter.drawArc(outer_rect, 120 * 16, 75 * 16)
        painter.drawArc(outer_rect, 240 * 16, 75 * 16)

        node_brush = QBrush(QColor(85, 245, 255, 240))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(node_brush)
        for base_deg in [0, 75, 120, 195, 240, 315]:
            rad = math.radians(base_deg)
            nx = (radius - 12) * math.cos(rad)
            ny = (radius - 12) * math.sin(rad)
            painter.drawEllipse(QPoint(int(nx), int(ny)), 3, 3)

        painter.restore()

        # 4. Counter-Rotating Intermediate Ring
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self.angle_inner)

        inner_pen = QPen(QColor(85, 225, 255, 225), 3)
        painter.setPen(inner_pen)
        mid_radius = radius - 26
        mid_rect = QRectF(-mid_radius, -mid_radius, mid_radius * 2, mid_radius * 2)
        painter.drawArc(mid_rect, 15 * 16, 60 * 16)
        painter.drawArc(mid_rect, 105 * 16, 60 * 16)
        painter.drawArc(mid_rect, 195 * 16, 60 * 16)
        painter.drawArc(mid_rect, 285 * 16, 60 * 16)

        teeth_pen = QPen(QColor(0, 240, 255, 170), 2)
        painter.setPen(teeth_pen)
        for i in range(8):
            rad = math.radians(i * 45)
            x1 = (mid_radius - 6) * math.cos(rad)
            y1 = (mid_radius - 6) * math.sin(rad)
            x2 = (mid_radius + 4) * math.cos(rad)
            y2 = (mid_radius + 4) * math.sin(rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        painter.restore()

        # 5. Radiant Energy Spokes
        spoke_pen = QPen(QColor(0, 240, 255, 60), 1)
        painter.setPen(spoke_pen)
        for i in range(12):
            rad = math.radians(i * 30 + self.angle_outer * 0.5)
            x1 = center_x + (radius * 0.28) * math.cos(rad)
            y1 = center_y + (radius * 0.28) * math.sin(rad)
            x2 = center_x + (radius * 0.72) * math.cos(rad)
            y2 = center_y + (radius * 0.72) * math.sin(rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # 6. Rotating Conical Magnetic Core
        core_field_radius = radius * 0.44
        conical = QConicalGradient(center_x, center_y, self.angle_core)
        conical.setColorAt(0.00, QColor(0, 240, 255, 210))
        conical.setColorAt(0.25, QColor(0, 120, 255, 90))
        conical.setColorAt(0.50, QColor(85, 245, 255, 220))
        conical.setColorAt(0.75, QColor(0, 80, 200, 70))
        conical.setColorAt(1.00, QColor(0, 240, 255, 210))
        painter.setBrush(QBrush(conical))
        painter.setPen(QPen(QColor(0, 240, 255, 140), 1))
        painter.drawEllipse(
            QPoint(int(center_x), int(center_y)), 
            int(core_field_radius), 
            int(core_field_radius)
        )

        # 7. Pulsating Quantum Fusion Core
        fusion_radius = (radius * 0.28) * pulse
        radial = QRadialGradient(center_x, center_y, fusion_radius)
        radial.setColorAt(0.0, QColor(255, 255, 255, 255))
        radial.setColorAt(0.35, QColor(85, 245, 255, 230))
        radial.setColorAt(0.75, QColor(0, 200, 255, 160))
        radial.setColorAt(1.0, QColor(0, 50, 120, 0))

        painter.setBrush(QBrush(radial))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QPoint(int(center_x), int(center_y)), 
            int(fusion_radius), 
            int(fusion_radius)
        )

        target_pen = QPen(QColor(190, 250, 255, 230), 1.5)
        painter.setPen(target_pen)
        cross_sz = 6
        painter.drawLine(int(center_x - cross_sz), int(center_y), int(center_x + cross_sz), int(center_y))
        painter.drawLine(int(center_x), int(center_y - cross_sz), int(center_x), int(center_y + cross_sz))


# --- Holographic Drag and Drop File Receptor Box ---
class DragDropReceptor(QFrame):
    """
    High-tech cyber file intake chamber with visual drop feedback,
    inspection metadata display, and pyqtSignal dispatch.
    """
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.is_drag_active = False
        self.last_filename = ""
        self.last_filesize = ""

        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.badge_label = QLabel("⮋ QUANTUM DATA RECEPTOR ⮊", self)
        self.badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_label.setStyleSheet("color: #00f0ff; font-size: 9px; font-weight: bold; letter-spacing: 2px;")

        self.label = QLabel("📄 Drag & Drop File Inspector", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #55f5ff; font-size: 11px; font-weight: bold;")

        self.sub_label = QLabel("RELEASE TO SCAN & INGEST LOCAL ARTIFACT", self)
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_label.setStyleSheet("color: #628298; font-size: 8px; font-family: 'Consolas', monospace;")

        layout.addWidget(self.badge_label)
        layout.addWidget(self.label)
        layout.addWidget(self.sub_label)

    def apply_theme(self):
        if self.is_drag_active:
            self.setStyleSheet("""
                QFrame {
                    border: 2px solid #00ffff;
                    border-radius: 8px;
                    background-color: rgba(0, 240, 255, 38);
                }
            """)
            self.label.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold;")
            self.sub_label.setStyleSheet("color: #00ffff; font-size: 8px; font-weight: bold;")
        else:
            self.setStyleSheet("""
                QFrame {
                    border: 1.5px dashed rgba(0, 240, 255, 140);
                    border-radius: 8px;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                        stop:0 rgba(0, 240, 255, 15), 
                        stop:1 rgba(6, 12, 24, 180));
                }
                QFrame:hover {
                    border: 1.5px dashed #00f0ff;
                    background-color: rgba(0, 240, 255, 28);
                }
            """)
            self.label.setStyleSheet("color: #55f5ff; font-size: 11px; font-weight: bold;")
            self.sub_label.setStyleSheet("color: #628298; font-size: 8px; font-family: 'Consolas', monospace;")

    def set_inspected_file(self, file_path: str):
        self.last_filename = os.path.basename(file_path)
        try:
            sz_bytes = os.path.getsize(file_path)
            if sz_bytes >= 1024 * 1024:
                self.last_filesize = f"{sz_bytes / (1024 * 1024):.2f} MB"
            elif sz_bytes >= 1024:
                self.last_filesize = f"{sz_bytes / 1024:.1f} KB"
            else:
                self.last_filesize = f"{sz_bytes} Bytes"
        except Exception:
            self.last_filesize = "READY"

        ext = os.path.splitext(self.last_filename)[1].upper() or "FILE"
        self.label.setText(f"✓ {self.last_filename}")
        self.sub_label.setText(f"PAYLOAD: {ext} | SIZE: {self.last_filesize} | STATUS: INSPECTED")
        self.sub_label.setStyleSheet("color: #00ffcc; font-size: 8px; font-family: 'Consolas', monospace;")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.is_drag_active = True
            self.apply_theme()
            self.sub_label.setText("READY TO CAPTURE PAYLOAD...")
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.is_drag_active = False
        self.apply_theme()
        if self.last_filename:
            self.sub_label.setText(f"STATUS: LOADED // {self.last_filesize}")
        else:
            self.sub_label.setText("RELEASE TO SCAN & INGEST LOCAL ARTIFACT")
        event.accept()

    def dropEvent(self, event):
        self.is_drag_active = False
        self.apply_theme()
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.exists(file_path):
                self.set_inspected_file(file_path)
                self.file_dropped.emit(file_path)
                event.acceptProposedAction()
                break


if __name__ == "__main__":
    app = QApplication(sys.argv)
    hud = DynamicIslandHUD()
    hud.show()
    sys.exit(app.exec())

# --- Main Integrated Tactical GUI Window ---
class DynamicIslandHUD(QWidget):
    """
    CYRUS High-Tech Tactical Operations Dashboard & Dynamic Island HUD.
    Features:
    - Full Tactical JARVIS Operations Dashboard (Cyber Cyan Aesthetic)
    - Full Windows standard window controls (Minimize to taskbar, Maximize/Restore, Close)
    - Dynamic Island Pill Mode toggle
    - Integrated Cyber Text Chat Input with instant voice reply
    - Physical Hardware Microphone Toggle Button (Dashboard & Pill modes)
    - Animated Arc Reactor Core visual with rotating rings & pulsing gradient
    - Live Telemetry gauges (CPU, RAM, Core Temp/Disk) with automated refresh
    - Monospace Cyber Terminal with styled scrollbars & deduplicated status stream
    - Holographic Drag & Drop File Inspector
    """
    file_inspected_signal = pyqtSignal(str)
    mic_toggled_signal = pyqtSignal(bool)
    mic_toggle_requested_signal = pyqtSignal()
    text_command_signal = pyqtSignal(str)
    stop_speech_signal = pyqtSignal()
    voice_output_status_signal = pyqtSignal(bool, bool)
    shutdown_signal = pyqtSignal()
    voice_volume_changed_signal = pyqtSignal(int)
    system_volume_changed_signal = pyqtSignal(int)
    player_volume_changed_signal = pyqtSignal(int)
    volume_levels_signal = pyqtSignal(int, int)
    music_control_signal = pyqtSignal(str)
    music_state_signal = pyqtSignal(str, str, bool, bool)
    log_message_signal = pyqtSignal(str)
    _state_signal = pyqtSignal(str, str)
    _offline_mode_requested_signal = pyqtSignal(bool)
    reminder_alert_signal = pyqtSignal(str)
    reminders_changed_signal = pyqtSignal(object)
    action_confirmation_signal = pyqtSignal(str)
    confirmed_action_signal = pyqtSignal(str)
    offline_mode_signal = pyqtSignal(bool)
    microphone_input_status_signal = pyqtSignal(bool)
    voice_output_initializing_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.is_pill_mode = False
        self.is_mic_muted = True
        self.microphone_input_enabled = load_installed_features()[
            "microphone_input"
        ]
        self.user_preferences = load_user_state()
        self.offline_mode = bool(
            self.user_preferences.get("offline_mode", False)
            or os.getenv("CYRUS_OFFLINE_MODE", "").strip().lower() in {"1", "true", "yes"}
        )
        self.dashboard_scale = int(self.user_preferences.get("dashboard_scale", 100))
        self.dashboard_brightness = int(self.user_preferences.get("brightness", 100))
        self.voice_volume = max(
            0, min(100, int(self.user_preferences.get("voice_volume", 70)))
        )
        self.system_volume = max(
            0, min(100, int(self.user_preferences.get("system_volume", 50)))
        )
        self.player_volume = max(
            0, min(100, int(self.user_preferences.get("player_volume", 100)))
        )
        self._reminder_alerts = []
        self._alarm_audio_path = None
        self._alarm_playing = False
        self._shutdown_confirmed = False
        self.current_state = ""
        self.current_subtext = ""
        self.drag_position = QPoint()
        self.setAcceptDrops(True)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Connect thread-safe state updating slot
        self._state_signal.connect(self._apply_state)
        self.mic_toggle_requested_signal.connect(
            self.toggle_mic, Qt.ConnectionType.QueuedConnection
        )
        self._offline_mode_requested_signal.connect(self._apply_offline_mode)
        self.voice_output_status_signal.connect(self.set_voice_output_status)
        self.voice_output_initializing_signal.connect(
            self.set_voice_output_initializing
        )
        self.microphone_input_status_signal.connect(
            self.set_microphone_input_enabled
        )

        self.init_ui()
        self.voice_volume_save_timer = QTimer(self)
        self.voice_volume_save_timer.setSingleShot(True)
        self.voice_volume_save_timer.timeout.connect(self._save_voice_volume_preference)
        self.system_volume_apply_timer = QTimer(self)
        self.system_volume_apply_timer.setSingleShot(True)
        self.system_volume_apply_timer.timeout.connect(self._apply_system_volume)
        self.player_volume_apply_timer = QTimer(self)
        self.player_volume_apply_timer.setSingleShot(True)
        self.player_volume_apply_timer.timeout.connect(self._apply_player_volume)
        self.log_message_signal.connect(self.log_terminal.append)
        self.music_state_signal.connect(self._apply_music_state)
        self.volume_levels_signal.connect(self.set_volume_levels)
        self.reminder_alert_signal.connect(self.show_reminder_alert)
        self.reminders_changed_signal.connect(self.set_active_reminders)
        self.action_confirmation_signal.connect(self.confirm_sensitive_action)
        self.init_telemetry_timer()
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self.refresh_reminder_countdowns)
        self.countdown_timer.start(1000)
        self.alarm_timer = QTimer(self)
        self.alarm_timer.timeout.connect(self._play_alarm_sound)
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.cleanup_alarm_audio)
        self.update_mic_ui()
        voice_output_selected = load_installed_features()["alan_voice"]
        self.set_voice_output_status(voice_output_selected, False)
        self.set_voice_output_initializing(voice_output_selected)
        self.set_microphone_input_enabled(self.microphone_input_enabled)
        self.update_offline_indicator()
        self.apply_dashboard_customization()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # -------------------------------------------------------------
        # 1. TACTICAL DASHBOARD CONTAINER (HIGH-TECH CYBER HUD)
        # -------------------------------------------------------------
        self.dashboard_container = QFrame(self)
        self.dashboard_container.setObjectName("dashboard_container")
        self.dashboard_container.setStyleSheet("""
            QFrame#dashboard_container {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #08121f, 
                    stop:0.5 #050c17, 
                    stop:1 #03070d);
                border: 1px solid rgba(76, 211, 255, 170);
                border-radius: 18px;
            }
        """)

        dash_shadow = QGraphicsDropShadowEffect(self)
        dash_shadow.setBlurRadius(32)
        dash_shadow.setColor(QColor(0, 240, 255, 95))
        dash_shadow.setOffset(0, 0)
        self.dashboard_container.setGraphicsEffect(dash_shadow)

        dash_outer_layout = QVBoxLayout(self.dashboard_container)
        dash_outer_layout.setContentsMargins(16, 12, 16, 12)
        dash_outer_layout.setSpacing(10)

        # --- Dashboard Window Control & Branding Header ---
        dash_header = QHBoxLayout()
        dash_header.setSpacing(8)

        # Logo / Badge Icon
        self.badge_lbl = QLabel("◈ CYRUS // HUD", self)
        self.badge_lbl.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.badge_lbl.setStyleSheet("""
            color: #060a14;
            background-color: #00f0ff;
            border-radius: 4px;
            padding: 3px 8px;
            font-weight: bold;
        """)
        dash_header.addWidget(self.badge_lbl)

        # Main Title
        self.dash_title = QLabel("CYRUS // SYSTEM CONSOLE", self)
        self.dash_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.dash_title.setStyleSheet("color: #e0f7fa; letter-spacing: 2px; border: none; background: transparent;")
        dash_header.addWidget(self.dash_title)

        dash_header.addStretch()

        # Physical Microphone Control Button (Dashboard Mode)
        self.btn_mic = QPushButton("🎤 MIC ON", self)
        self.btn_mic.setFixedSize(100, 26)
        self.btn_mic.setToolTip("Click to Mute / Turn OFF Microphone (F3 / Ctrl+M)")
        self.btn_mic.clicked.connect(self.toggle_mic)
        dash_header.addWidget(self.btn_mic)

        self.offline_badge = QLabel(self)
        self.offline_badge.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        dash_header.addWidget(self.offline_badge)

        self.btn_settings = QPushButton("⚙", self)
        self.btn_settings.setFixedSize(30, 26)
        self.btn_settings.setToolTip("Dashboard, offline, and privacy settings")
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        dash_header.addWidget(self.btn_settings)

        # Dynamic Header State Badge
        self.header_state_badge = QLabel("STATUS: ONLINE // ARMED", self)
        self.header_state_badge.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.header_state_badge.setStyleSheet("""
            color: #00f0ff;
            border: 1px solid rgba(0, 240, 255, 120);
            background: rgba(0, 240, 255, 20);
            border-radius: 8px;
            padding: 3px 10px;
        """)
        dash_header.addWidget(self.header_state_badge)

        # Collapse into Dynamic Island Pill Mode Button
        self.btn_pill = QPushButton("⮑ PILL", self)
        self.btn_pill.setFixedSize(72, 26)
        self.btn_pill.setToolTip("Collapse into compact floating Dynamic Island pill")
        self.btn_pill.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 240, 255, 20);
                color: #00f0ff;
                border: 1px solid #00f0ff;
                border-radius: 5px;
                font-family: 'Consolas', 'Segoe UI';
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #00f0ff;
                color: #060a14;
            }
        """)
        self.btn_pill.clicked.connect(self.switchToPillMode)
        dash_header.addWidget(self.btn_pill)

        # --- Standard Windows Window Control Buttons (—, 🗖, ✕) ---
        win_controls = QHBoxLayout()
        win_controls.setSpacing(4)

        # Minimize to Windows Taskbar
        self.btn_win_min = QPushButton("—", self)
        self.btn_win_min.setFixedSize(28, 26)
        self.btn_win_min.setToolTip("Minimize to Taskbar")
        self.btn_win_min.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 10);
                color: #8ca3b8;
                border: 1px solid rgba(0, 240, 255, 40);
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 35);
                color: #00f0ff;
                border: 1px solid #00f0ff;
            }
        """)
        self.btn_win_min.clicked.connect(self.showMinimized)
        win_controls.addWidget(self.btn_win_min)

        # Maximize / Restore / Fullscreen Toggle
        self.btn_win_max = QPushButton("🗖", self)
        self.btn_win_max.setFixedSize(28, 26)
        self.btn_win_max.setToolTip("Maximize Window")
        self.btn_win_max.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 10);
                color: #8ca3b8;
                border: 1px solid rgba(0, 240, 255, 40);
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 35);
                color: #00f0ff;
                border: 1px solid #00f0ff;
            }
        """)
        self.btn_win_max.clicked.connect(self.toggle_maximize)
        win_controls.addWidget(self.btn_win_max)

        # Close Application Button
        self.btn_win_close = QPushButton("✕", self)
        self.btn_win_close.setFixedSize(28, 26)
        self.btn_win_close.setToolTip("Close CYRUS System")
        self.btn_win_close.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 10);
                color: #8ca3b8;
                border: 1px solid rgba(255, 68, 85, 40);
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e81123;
                color: #ffffff;
                border: 1px solid #ff4455;
            }
        """)
        self.btn_win_close.clicked.connect(self.close_application)
        win_controls.addWidget(self.btn_win_close)

        dash_header.addLayout(win_controls)
        dash_outer_layout.addLayout(dash_header)

        # Subtle Header Separator Line
        header_divider = QFrame()
        header_divider.setFrameShape(QFrame.Shape.HLine)
        header_divider.setStyleSheet("background-color: rgba(0, 240, 255, 55); max-height: 1px; border: none;")
        dash_outer_layout.addWidget(header_divider)

        # -------------------------------------------------------------
        # TACTICAL THREE-PANEL CORE LAYOUT
        # -------------------------------------------------------------
        panels_layout = QHBoxLayout()
        panels_layout.setSpacing(12)

        # =============================================================
        # LEFT PANEL: High-Tech Telemetry & System Diagnostics
        # =============================================================
        left_panel = CyberPanel(self, corner_color=QColor(92, 194, 220, 210))
        left_panel.setMinimumWidth(0)
        left_panel.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        # Panel Section Header
        left_header_box = QHBoxLayout()
        self.telemetry_title = QLabel("// 01. TELEMETRY MONITOR")
        self.telemetry_title.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.telemetry_title.setStyleSheet("color: #00f0ff; letter-spacing: 1px; border: none; background: transparent;")
        live_badge = QLabel("LIVE")
        live_badge.setStyleSheet("color: #00ffcc; font-size: 9px; font-weight: bold; border: 1px solid #00ffcc; border-radius: 4px; padding: 1px 4px;")
        left_header_box.addWidget(self.telemetry_title)
        left_header_box.addStretch()
        left_header_box.addWidget(live_badge)
        left_layout.addLayout(left_header_box)

        # CPU Metric Block
        cpu_box = QVBoxLayout()
        cpu_box.setSpacing(2)
        self.cpu_label = QLabel("CPU LOAD: --")
        self.cpu_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.cpu_label.setStyleSheet("color: #e0f7fa; border: none; background: transparent;")
        self.cpu_bar = self._create_cyber_progress_bar()
        self.cpu_bar.setValue(0)
        cpu_sub = QLabel("LIVE PROCESSOR UTILIZATION")
        cpu_sub.setStyleSheet("color: #557588; font-size: 8px; font-family: 'Consolas'; border: none;")
        cpu_box.addWidget(self.cpu_label)
        cpu_box.addWidget(self.cpu_bar)
        cpu_box.addWidget(cpu_sub)
        left_layout.addLayout(cpu_box)

        # RAM Metric Block
        mem_box = QVBoxLayout()
        mem_box.setSpacing(2)
        self.mem_label = QLabel("RAM USAGE: -- / -- GB")
        self.mem_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.mem_label.setStyleSheet("color: #e0f7fa; border: none; background: transparent;")
        self.mem_bar = self._create_cyber_progress_bar()
        self.mem_bar.setValue(0)
        mem_sub = QLabel("PHYSICAL MEMORY UTILIZATION")
        mem_sub.setStyleSheet("color: #557588; font-size: 8px; font-family: 'Consolas'; border: none;")
        mem_box.addWidget(self.mem_label)
        mem_box.addWidget(self.mem_bar)
        mem_box.addWidget(mem_sub)
        left_layout.addLayout(mem_box)

        # Thermal / Storage Metric Block
        disk_box = QVBoxLayout()
        disk_box.setSpacing(2)
        self.disk_label = QLabel("SYSTEM DISK: --")
        self.disk_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.disk_label.setStyleSheet("color: #e0f7fa; border: none; background: transparent;")
        self.disk_bar = self._create_cyber_progress_bar()
        self.disk_bar.setValue(0)
        disk_sub = QLabel("SYSTEM DRIVE CAPACITY")
        disk_sub.setStyleSheet("color: #557588; font-size: 8px; font-family: 'Consolas'; border: none;")
        disk_box.addWidget(self.disk_label)
        disk_box.addWidget(self.disk_bar)
        disk_box.addWidget(disk_sub)
        left_layout.addLayout(disk_box)

        system_volume_layout, self.system_volume_slider, self.system_volume_value = self._create_volume_control(
            left_panel, "SYSTEM", self.system_volume, self._on_system_volume_changed
        )
        left_layout.addLayout(system_volume_layout)
        player_volume_layout, self.player_volume_slider, self.player_volume_value = self._create_volume_control(
            left_panel, "PLAYER", self.player_volume, self._on_player_volume_changed
        )
        left_layout.addLayout(player_volume_layout)

        left_layout.addStretch()
        left_panel.setObjectName("telemetry_panel")
        panels_layout.addWidget(left_panel, 2)

        # =============================================================
        # CENTER PANEL: Quantum Arc Reactor Core Visual
        # =============================================================
        center_panel = CyberPanel(
            self,
            corner_len=20,
            corner_color=QColor(95, 232, 255, 245),
            border_color=QColor(80, 215, 255, 105),
        )
        center_panel.setMinimumWidth(0)
        center_panel.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        center_panel.setObjectName("core_panel")
        center_panel.setStyleSheet("""
            CyberPanel#core_panel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(8, 25, 39, 248),
                    stop:0.55 rgba(4, 15, 27, 250),
                    stop:1 rgba(3, 10, 20, 252));
                border: 1px solid rgba(70, 207, 245, 100);
                border-radius: 16px;
            }
        """)
        center_layout = QVBoxLayout(center_panel)
        self.center_layout = center_layout
        center_layout.setContentsMargins(12, 12, 12, 12)
        center_layout.setSpacing(6)

        center_header_box = QHBoxLayout()
        reactor_header_lbl = QLabel("// CYRUS SYSTEM CORE")
        reactor_header_lbl.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        reactor_header_lbl.setStyleSheet("color: #00f0ff; letter-spacing: 1px; border: none; background: transparent;")
        center_header_box.addWidget(reactor_header_lbl)
        center_header_box.addStretch()
        sync_lbl = QLabel("LOCAL // ACTIVE")
        sync_lbl.setStyleSheet("color: #75dff5; font-size: 9px; font-weight: bold; font-family: 'Consolas';")
        center_header_box.addWidget(sync_lbl)
        center_layout.addLayout(center_header_box)

        self.status_label = QLabel("CORE ONLINE")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.status_label.setMinimumWidth(0)
        self.status_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.status_label.setStyleSheet("""
            color: #a9f4ff;
            letter-spacing: 4px;
            border: 1px solid rgba(79, 202, 238, 95);
            background: rgba(16, 77, 103, 35);
            border-radius: 10px;
            padding: 7px;
        """)
        center_layout.addWidget(self.status_label)

        self.substatus_label = QLabel("STANDBY // AWAITING DIRECTIVE")
        self.substatus_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.substatus_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.substatus_label.setMinimumWidth(0)
        self.substatus_label.setStyleSheet("color: #628298; font-size: 9px; font-family: 'Consolas'; letter-spacing: 1px;")
        center_layout.addWidget(self.substatus_label)

        self.countdown_panel = QFrame(center_panel)
        self.countdown_panel.setObjectName("countdown_panel")
        self.countdown_panel.setStyleSheet("""
            QFrame#countdown_panel {
                background-color: rgba(0, 240, 255, 14);
                border: 1px solid rgba(0, 240, 255, 80);
                border-radius: 7px;
            }
        """)
        countdown_layout = QVBoxLayout(self.countdown_panel)
        countdown_layout.setContentsMargins(8, 4, 8, 4)
        countdown_layout.setSpacing(2)
        self.countdown_label = QLabel()
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setWordWrap(True)
        self.countdown_label.setStyleSheet(
            "color: #55f5ff; font-family: 'Consolas'; font-size: 10px; "
            "font-weight: bold; border: none; background: transparent;"
        )
        countdown_layout.addWidget(self.countdown_label)
        self.countdown_panel.hide()
        center_layout.addWidget(self.countdown_panel)

        voice_volume_panel = QFrame(center_panel)
        self.voice_volume_panel = voice_volume_panel
        voice_volume_panel.setObjectName("voice_volume_panel")
        voice_volume_panel.setStyleSheet("""
            QFrame#voice_volume_panel {
                background-color: rgba(0, 240, 255, 12);
                border: 1px solid rgba(0, 240, 255, 55);
                border-radius: 7px;
            }
        """)
        voice_volume_layout = QVBoxLayout(voice_volume_panel)
        voice_volume_layout.setContentsMargins(8, 3, 8, 5)
        voice_volume_layout.setSpacing(3)
        voice_volume_controls = QHBoxLayout()
        voice_volume_controls.setContentsMargins(0, 0, 0, 0)
        voice_volume_controls.setSpacing(8)
        voice_volume_label = QLabel("VOICE")
        voice_volume_label.setStyleSheet(
            "color: #75dff5; font-family: 'Consolas'; font-size: 9px; "
            "font-weight: bold; border: none; background: transparent;"
        )
        voice_volume_controls.addWidget(voice_volume_label)
        self.voice_volume_slider = QSlider(Qt.Orientation.Horizontal, voice_volume_panel)
        self.voice_volume_slider.setRange(0, 100)
        self.voice_volume_slider.setValue(self.voice_volume)
        self.voice_volume_slider.setToolTip(
            "Adjust CYRUS speech volume without changing system or music volume"
        )
        self.voice_volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 5px;
                background: rgba(89, 134, 153, 100);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #00d9f5;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 12px;
                margin: -4px 0;
                background: #b6f7ff;
                border: 1px solid #00d9f5;
                border-radius: 6px;
            }
        """)
        self.voice_volume_slider.valueChanged.connect(self._on_voice_volume_changed)
        voice_volume_controls.addWidget(self.voice_volume_slider, 1)
        self.voice_volume_value = QLabel(f"{self.voice_volume}%")
        self.voice_volume_value.setMinimumWidth(36)
        self.voice_volume_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.voice_volume_value.setStyleSheet(
            "color: #55f5ff; font-family: 'Consolas'; font-size: 9px; "
            "font-weight: bold; border: none; background: transparent;"
        )
        voice_volume_controls.addWidget(self.voice_volume_value)
        voice_volume_layout.addLayout(voice_volume_controls)
        self.voice_download_help = QLabel(voice_volume_panel)
        self.voice_download_help.setObjectName("voice_download_help")
        self.voice_download_help.setWordWrap(True)
        self.voice_download_help.setOpenExternalLinks(True)
        self.voice_download_help.setTextFormat(Qt.TextFormat.RichText)
        self.voice_download_help.setText(
            'Alan voice is not installed. Download both files from '
            '<a href="https://huggingface.co/rhasspy/piper-voices/resolve/main/'
            'en/en_GB/alan/medium/en_GB-alan-medium.onnx?download=true">the '
            'official model download</a> and its '
            '<a href="https://huggingface.co/rhasspy/piper-voices/resolve/main/'
            'en/en_GB/alan/medium/en_GB-alan-medium.onnx.json?download=true">'
            'voice configuration</a>. Save both in '
            '<code>%LOCALAPPDATA%\\CYRUS\\voices\\</code>, then restart CYRUS. '
            'Review the model card and voice source terms before downloading.'
        )
        self.voice_download_help.setStyleSheet(
            "color: #c3dce4; font-family: 'Segoe UI'; font-size: 8px; "
            "border: none; background: transparent;"
        )
        self.voice_download_help.hide()
        voice_volume_layout.addWidget(self.voice_download_help)
        center_layout.addWidget(voice_volume_panel)

        self.reactor = ArcReactorWidget(center_panel)
        self.reactor.setMinimumSize(320, 320)
        center_layout.addWidget(self.reactor, 1)

        reactor_telemetry = QHBoxLayout()
        reactor_telemetry.setSpacing(6)
        metrics = [
            ("AUDIO", "PIPER"),
            ("CHAT", "READY"),
            ("CONTROL", "ACTIVE"),
            ("CORE", "ONLINE")
        ]
        for key, val in metrics:
            m_box = QFrame()
            m_box.setStyleSheet("background: rgba(37, 129, 158, 18); border: 1px solid rgba(96, 205, 232, 42); border-radius: 6px; padding: 2px;")
            m_lay = QVBoxLayout(m_box)
            m_lay.setContentsMargins(4, 2, 4, 2)
            m_lay.setSpacing(0)
            k_lbl = QLabel(key)
            k_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            k_lbl.setStyleSheet("color: #789baa; font-size: 8px; font-family: 'Consolas'; font-weight: bold;")
            v_lbl = QLabel(val)
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v_lbl.setStyleSheet("color: #9defff; font-size: 9px; font-family: 'Consolas'; font-weight: bold;")
            m_lay.addWidget(k_lbl)
            m_lay.addWidget(v_lbl)
            reactor_telemetry.addWidget(m_box)
        center_layout.addLayout(reactor_telemetry)

        panels_layout.addWidget(center_panel, 5)

        # =============================================================
        # RIGHT PANEL: Terminal & Integrated Cyber Text Chat Input
        # =============================================================
        right_panel = CyberPanel(self, corner_color=QColor(92, 194, 220, 210))
        right_panel.setMinimumWidth(0)
        right_panel.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        # Panel Section Header
        right_header_box = QHBoxLayout()
        self.term_title = QLabel("// 03. TACTICAL TERMINAL & CHAT")
        self.term_title.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.term_title.setStyleSheet("color: #00f0ff; letter-spacing: 1px; border: none; background: transparent;")
        self.stream_badge = QLabel("● STREAM ACTIVE")
        self.stream_badge.setStyleSheet("color: #00ffcc; font-size: 9px; font-family: 'Consolas'; font-weight: bold;")
        right_header_box.addWidget(self.term_title)
        right_header_box.addStretch()
        right_header_box.addWidget(self.stream_badge)
        right_layout.addLayout(right_header_box)

        # Monospace Terminal Window
        self.log_terminal = QTextEdit()
        self.log_terminal.setReadOnly(True)
        self.log_terminal.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.log_terminal.setSizeAdjustPolicy(
            QTextEdit.SizeAdjustPolicy.AdjustIgnored
        )
        self.log_terminal.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Expanding,
        )
        self.log_terminal.setMinimumHeight(0)
        self.log_terminal.setStyleSheet("""
            QTextEdit {
                background-color: #050811;
                color: #00f0ff;
                font-family: 'Consolas', 'Courier New', monospace;
                border: 1px solid rgba(0, 240, 255, 60);
                border-radius: 8px;
                font-size: 10px;
                padding: 6px;
                selection-background-color: #007a8a;
                selection-color: #ffffff;
            }
            QScrollBar:vertical {
                border: none;
                background: #080d18;
                width: 6px;
                border-radius: 3px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #00f0ff;
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #55f5ff;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        self.log_terminal.append("[00:00:01] [SYS_INIT]: Cyrus Core v4.2 kernel initialized.")
        self.log_terminal.append(
            "[00:00:01] [AUDIO_ENGINE]: Piper Alan initialization runs in background."
        )
        self.log_terminal.append("[00:00:02] [HUD_SYNC]: Full window controls and chat bus online.")
        right_layout.addWidget(self.log_terminal, 2)

        self.music_player_bar = QFrame(right_panel)
        self.music_player_bar.setObjectName("music_player_bar")
        self.music_player_bar.setStyleSheet("""
            QFrame#music_player_bar {
                background-color: rgba(0, 240, 255, 12);
                border: 1px solid rgba(0, 240, 255, 90);
                border-radius: 6px;
            }
        """)
        music_layout = QHBoxLayout(self.music_player_bar)
        music_layout.setContentsMargins(8, 4, 8, 4)
        music_layout.setSpacing(6)
        self.music_title_label = QLabel("Music player")
        self.music_title_label.setStyleSheet(
            "color: #e0f7fa; font-family: 'Consolas'; font-size: 9px; "
            "border: none; background: transparent;"
        )
        self.music_title_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        music_layout.addWidget(self.music_title_label, 1)

        self.music_previous_button = QPushButton("⏮")
        self.music_play_pause_button = QPushButton("▶")
        self.music_next_button = QPushButton("⏭")
        self.music_stop_button = QPushButton("■")
        for button, tooltip, action in (
            (self.music_previous_button, "Previous track", "previous"),
            (self.music_play_pause_button, "Play or pause", "toggle"),
            (self.music_next_button, "Next track", "next"),
            (self.music_stop_button, "Stop playback", "stop"),
        ):
            button.setFixedSize(32, 28)
            button.setToolTip(tooltip)
            button.setStyleSheet("""
                QPushButton {
                    color: #00f0ff;
                    background-color: rgba(0, 240, 255, 18);
                    border: 1px solid rgba(0, 240, 255, 100);
                    border-radius: 4px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    color: #060a14;
                    background-color: #00f0ff;
                }
            """)
            button.clicked.connect(
                lambda checked=False, control=action:
                    self.music_control_signal.emit(control)
            )
            music_layout.addWidget(button)
        self.music_player_bar.hide()
        right_layout.addWidget(self.music_player_bar)

        # --- Cyber Chat Input Bar (Type queries when mic is off or on) ---
        chat_box = QHBoxLayout()
        chat_box.setSpacing(6)

        self.chat_input = QLineEdit(self)
        self.chat_input.setPlaceholderText("⌨ Type a command or ask CYRUS... (Press Enter)")
        self.chat_input.returnPressed.connect(self.submit_chat_command)
        self.chat_input.setStyleSheet("""
            QLineEdit {
                background-color: #060a14;
                color: #e0f7fa;
                border: 1px solid rgba(0, 240, 255, 90);
                border-radius: 6px;
                font-family: 'Consolas', 'Segoe UI';
                font-size: 10px;
                padding: 5px 8px;
            }
            QLineEdit:focus {
                border: 1.5px solid #00f0ff;
                background-color: rgba(0, 240, 255, 12);
            }
        """)
        chat_box.addWidget(self.chat_input)

        self.btn_send = QPushButton("SEND ➢", self)
        self.btn_send.setFixedSize(68, 26)
        self.btn_send.setToolTip("Send text directive to CYRUS")
        self.btn_send.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 rgba(0, 240, 255, 30), 
                    stop:1 rgba(0, 160, 220, 50));
                color: #00f0ff;
                border: 1px solid #00f0ff;
                border-radius: 5px;
                font-family: 'Consolas', 'Segoe UI';
                font-weight: bold;
                font-size: 9px;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background-color: #00f0ff;
                color: #060a14;
            }
        """)
        self.btn_send.clicked.connect(self.submit_chat_command)
        chat_box.addWidget(self.btn_send)

        right_layout.addLayout(chat_box)

        # Universal File Browse Inspector Button
        self.file_browse_btn = QPushButton("📁 BROWSE FILE TO INSPECT", self)
        self.file_browse_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 240, 255, 10);
                border: 2px dashed #00f0ff;
                border-radius: 8px;
                color: #00f0ff;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: bold;
                padding: 10px;
                margin-top: 5px;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 30);
                border: 2px solid #55f5ff;
                color: #ffffff;
            }
        """)
        self.file_browse_btn.clicked.connect(self.open_file_dialog)
        right_layout.addWidget(self.file_browse_btn)

        right_panel.setObjectName("terminal_panel")
        panels_layout.addWidget(right_panel, 3)
        self.dashboard_panels = {
            "telemetry": left_panel,
            "reactor": center_panel,
            "terminal": right_panel,
        }
        self.panels_layout = panels_layout
        dash_outer_layout.addLayout(panels_layout)

        # -------------------------------------------------------------
        # DASHBOARD FOOTER: Tactical HUD Quick Metrics Strip
        # -------------------------------------------------------------
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(6, 2, 6, 0)
        footer_tags = [
            ("SYS_ID", "CYRUS-JARVIS"),
            ("VOICE_CORE", "PIPER LOCAL"),
            ("CHAT_BUS", "SYNCHRONIZED"),
            ("CLEARANCE", "OMNI-5"),
            ("HUD_STATUS", "OPTIMAL")
        ]
        for tag, val in footer_tags:
            lbl = QLabel(f"[{tag}: {val}]")
            lbl.setStyleSheet("color: #436172; font-size: 8px; font-family: 'Consolas'; font-weight: bold;")
            footer_layout.addWidget(lbl)
            if tag != footer_tags[-1][0]:
                dot = QLabel("•")
                dot.setStyleSheet("color: #243b49; font-size: 8px;")
                footer_layout.addWidget(dot)

        footer_layout.addStretch()
        dash_outer_layout.addLayout(footer_layout)

        # -------------------------------------------------------------
        # 2. DYNAMIC ISLAND PILL CONTAINER
        # -------------------------------------------------------------
        self.pill_container = QFrame(self)
        self.pill_container.setObjectName("pill_container")
        self.pill_container.setStyleSheet("""
            QFrame#pill_container {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(10, 16, 28, 245), 
                    stop:1 rgba(4, 7, 14, 252));
                border: 2px solid #00f0ff;
                border-radius: 26px;
            }
            QFrame#pill_container:hover {
                border: 2px solid #55f5ff;
            }
        """)

        pill_shadow = QGraphicsDropShadowEffect(self)
        pill_shadow.setBlurRadius(22)
        pill_shadow.setColor(QColor(0, 240, 255, 130))
        pill_shadow.setOffset(0, 0)
        self.pill_container.setGraphicsEffect(pill_shadow)

        pill_layout = QHBoxLayout(self.pill_container)
        pill_layout.setContentsMargins(14, 0, 12, 0)
        pill_layout.setSpacing(8)

        self.pill_beacon = QLabel("◈", self)
        self.pill_beacon.setStyleSheet("color: #00f0ff; font-size: 13px; border: none; background: transparent;")
        pill_layout.addWidget(self.pill_beacon)

        self.pill_status_label = QLabel("● CYRUS IDLE", self)
        self.pill_status_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.pill_status_label.setStyleSheet("color: #00f0ff; letter-spacing: 1px; border: none; background: transparent;")
        pill_layout.addWidget(self.pill_status_label)

        pill_layout.addStretch()

        # Pill Mic Button
        self.pill_btn_mic = QPushButton("🎤", self)
        self.pill_btn_mic.setFixedSize(28, 26)
        self.pill_btn_mic.setToolTip("Microphone Active - Click to Mute")
        self.pill_btn_mic.clicked.connect(self.toggle_mic)
        pill_layout.addWidget(self.pill_btn_mic)

        # Expand to Dashboard
        btn_maximize = QPushButton("⤢", self)
        btn_maximize.setFixedSize(28, 26)
        btn_maximize.setToolTip("Expand to Tactical Operations Dashboard")
        btn_maximize.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 240, 255, 20);
                color: #00f0ff;
                border: 1px solid #00f0ff;
                border-radius: 13px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00f0ff;
                color: #060a14;
            }
        """)
        btn_maximize.clicked.connect(self.switchToDashboardMode)
        pill_layout.addWidget(btn_maximize)

        # Pill Close Button
        pill_btn_close = QPushButton("✕", self)
        pill_btn_close.setFixedSize(26, 26)
        pill_btn_close.setToolTip("Close CYRUS System")
        pill_btn_close.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #8ca3b8;
                border: none;
                border-radius: 13px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e81123;
                color: #ffffff;
            }
        """)
        pill_btn_close.clicked.connect(self.close_application)
        pill_layout.addWidget(pill_btn_close)

        self.update_mic_ui()

        self.main_layout.addWidget(self.dashboard_container)
        self.main_layout.addWidget(self.pill_container)

        self.switchToDashboardMode()

    def submit_chat_command(self):
        """Dispatches typed text directive to CYRUS query engine."""
        query = self.chat_input.text().strip()
        if not query:
            return

        self.chat_input.clear()
        timestamp = time.strftime("%H:%M:%S")
        self.log_terminal.append(f"[{timestamp}] [USER]: {query}")
        
        scrollbar = self.log_terminal.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        speech_stop_commands = {
            "stop", "stop speaking", "be quiet", "shut up", "cancel speech",
        }
        if query.lower().strip(" .,!?:;") in speech_stop_commands:
            self.stop_speech_signal.emit()
            return

        # Emit to controller
        self.text_command_signal.emit(query)

    def toggle_maximize(self):
        """Standard Windows Maximize / Restore window toggle."""
        if self.isMaximized():
            self.showNormal()
            self.btn_win_max.setText("🗖")
            self.btn_win_max.setToolTip("Maximize Window")
        else:
            self.showMaximized()
            self.btn_win_max.setText("❐")
            self.btn_win_max.setToolTip("Restore Window")

    def close_application(self):
        self.close()

    def closeEvent(self, event: QCloseEvent):
        if self._shutdown_confirmed:
            event.accept()
            return

        result = QMessageBox.question(
            self,
            "Close CYRUS?",
            "Are you sure you want to close the assistant?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            event.ignore()
            return

        self._shutdown_confirmed = True
        event.accept()
        QApplication.quit()

    def update_mic_ui(self):
        """Updates mic buttons across dashboard and pill containers based on mute state."""
        if not self.is_mic_muted:
            self.btn_mic.setText("🎤 MIC ON")
            self.btn_mic.setToolTip(
                "Microphone listening is enabled. Speak now, or click to turn it off "
                "(F3 / Ctrl+M)."
            )
            self.btn_mic.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 rgba(0, 240, 255, 30), 
                        stop:1 rgba(0, 180, 220, 50));
                    color: #00f0ff;
                    border: 1.5px solid #00f0ff;
                    border-radius: 5px;
                    font-family: 'Consolas', 'Segoe UI';
                    font-weight: bold;
                    font-size: 10px;
                    letter-spacing: 1px;
                }
                QPushButton:hover {
                    background-color: #00f0ff;
                    color: #060a14;
                    border: 1.5px solid #55f5ff;
                }
            """)
            self.pill_btn_mic.setText("🎤")
            self.pill_btn_mic.setToolTip("Microphone listening is enabled - Click to mute")
            self.pill_btn_mic.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 240, 255, 25);
                    color: #00f0ff;
                    border: 1px solid #00f0ff;
                    border-radius: 13px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #00f0ff;
                    color: #060a14;
                }
            """)
        else:
            self.btn_mic.setText("🔇 MIC OFF")
            self.btn_mic.setToolTip(
                "Microphone is off for privacy. Click to enable live speech input "
                "(F3 / Ctrl+M). Typed chat works while muted."
            )
            self.btn_mic.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 rgba(255, 68, 85, 35), 
                        stop:1 rgba(220, 38, 38, 60));
                    color: #ff5566;
                    border: 1.5px solid #ff4455;
                    border-radius: 5px;
                    font-family: 'Consolas', 'Segoe UI';
                    font-weight: bold;
                    font-size: 10px;
                    letter-spacing: 1px;
                }
                QPushButton:hover {
                    background-color: #ff4455;
                    color: #ffffff;
                    border: 1.5px solid #ff6677;
                }
            """)
            self.pill_btn_mic.setText("🔇")
            self.pill_btn_mic.setToolTip("Microphone Muted - Click to Unmute")
            self.pill_btn_mic.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 68, 85, 40);
                    color: #ff5566;
                    border: 1px solid #ff4455;
                    border-radius: 13px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #ff4455;
                    color: #ffffff;
                }
            """)

    def update_offline_indicator(self):
        mode = "OFFLINE" if self.offline_mode else "ONLINE"
        color = "#ffcc66" if self.offline_mode else "#00ffcc"
        self.offline_badge.setText(f"● {mode}")
        self.offline_badge.setStyleSheet(
            f"color: {color}; border: 1px solid {color}; border-radius: 5px; "
            "padding: 3px 6px;"
        )

    def set_offline_mode(self, enabled: bool):
        """Thread-safe entrypoint for enabling offline mode after network errors."""
        self._offline_mode_requested_signal.emit(bool(enabled))

    def _apply_offline_mode(self, enabled: bool):
        self.offline_mode = bool(enabled)
        self.user_preferences["offline_mode"] = self.offline_mode
        save_user_state(self.user_preferences)
        self.update_offline_indicator()
        self.offline_mode_signal.emit(self.offline_mode)
        if self.offline_mode:
            self.set_mic_muted(True)

    def open_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("CYRUS Settings")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        preferred_name = QLineEdit(
            str(self.user_preferences.get("preferred_name", "")), dialog
        )
        form.addRow("Call me", preferred_name)

        panel_checks = {}
        panel_labels = {
            "telemetry": "Show system telemetry and history",
            "reactor": "Show central reactor",
            "terminal": "Show chat and terminal",
        }
        for panel_key, label in panel_labels.items():
            check = QCheckBox(label, dialog)
            check.setChecked(
                self.user_preferences.get("panels", {}).get(panel_key, True)
            )
            panel_checks[panel_key] = check
            form.addRow(check)

        order = QComboBox(dialog)
        order_options = (
            ("Telemetry - Reactor - Chat", ["telemetry", "reactor", "terminal"]),
            ("Telemetry - Chat - Reactor", ["telemetry", "terminal", "reactor"]),
            ("Reactor - Telemetry - Chat", ["reactor", "telemetry", "terminal"]),
            ("Reactor - Chat - Telemetry", ["reactor", "terminal", "telemetry"]),
            ("Chat - Telemetry - Reactor", ["terminal", "telemetry", "reactor"]),
            ("Chat - Reactor - Telemetry", ["terminal", "reactor", "telemetry"]),
        )
        current_order = self.user_preferences.get(
            "panel_order", ["telemetry", "reactor", "terminal"]
        )
        for label, panel_order in order_options:
            order.addItem(label, panel_order)
            if panel_order == current_order:
                order.setCurrentIndex(order.count() - 1)
        form.addRow("Panel order", order)

        scale = QComboBox(dialog)
        for value in (80, 90, 100, 110, 120):
            scale.addItem(f"{value}%", value)
        scale.setCurrentIndex(max(0, scale.findData(self.dashboard_scale)))
        form.addRow("Dashboard scale", scale)

        brightness = QSlider(Qt.Orientation.Horizontal, dialog)
        brightness.setRange(40, 100)
        brightness.setValue(self.dashboard_brightness)
        form.addRow("Brightness", brightness)

        offline = QCheckBox("Offline mode (blocks network features)", dialog)
        offline.setChecked(self.offline_mode)
        form.addRow(offline)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if not preferred_name.text().strip():
            QMessageBox.warning(self, "Settings", "Enter the name CYRUS should use for you.")
            return

        visible_panels = {key: check.isChecked() for key, check in panel_checks.items()}
        if not any(visible_panels.values()):
            QMessageBox.warning(
                dialog, "Settings", "At least one dashboard panel must remain visible."
            )
            return

        previous_offline = self.offline_mode
        self.user_preferences.update(
            {
                "panels": visible_panels,
                "panel_order": order.currentData(),
                "dashboard_scale": scale.currentData(),
                "brightness": brightness.value(),
                "offline_mode": offline.isChecked(),
                "preferred_name": preferred_name.text().strip(),
            }
        )
        if not save_user_state(self.user_preferences):
            QMessageBox.warning(
                self,
                "Settings",
                "The settings could not be saved. Check local storage permissions and try again.",
            )
            return
        self.offline_mode = offline.isChecked()
        self.dashboard_scale = scale.currentData()
        self.dashboard_brightness = brightness.value()
        self.apply_dashboard_customization()
        self.update_offline_indicator()
        if self.offline_mode != previous_offline:
            self.offline_mode_signal.emit(self.offline_mode)
            if self.offline_mode:
                self.set_mic_muted(True)
                QMessageBox.information(
                    self,
                    "Offline mode",
                    "Network features and cloud speech recognition are disabled. "
                    "Use typed chat for commands while offline.",
                )

    def prompt_user_profile_if_needed(self) -> bool:
        if self.user_preferences.get("profile_setup_complete"):
            return True

        while True:
            dialog = QDialog(self)
            dialog.setWindowTitle("Personalize CYRUS")
            dialog.setMinimumWidth(360)
            layout = QVBoxLayout(dialog)
            form = QFormLayout()
            name_input = QLineEdit(getpass.getuser(), dialog)
            form.addRow("What should CYRUS call you?", name_input)
            layout.addLayout(form)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Save
                | QDialogButtonBox.StandardButton.Cancel,
                parent=dialog,
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False

            preferred_name = name_input.text().strip()
            if preferred_name:
                break
            QMessageBox.warning(
                self,
                "Personalize CYRUS",
                "Enter the name CYRUS should use for you.",
            )

        self.user_preferences.update(
            {
                "preferred_name": preferred_name,

                "profile_setup_complete": True,
            }
        )
        if not save_user_state(self.user_preferences):
            QMessageBox.critical(
                self,
                "Personalize CYRUS",
                "Your profile could not be saved. Check local storage permissions.",
            )
            return False
        return True

    def prompt_microphone_permission(self) -> bool:
        if not self.microphone_input_enabled:
            return False
        if self.offline_mode:
            self.append_log(
                "[MICROPHONE]: Offline mode is active; online speech recognition "
                "is unavailable."
            )
            return False

        result = QMessageBox.question(
            self,
            "Allow microphone access?",
            "May CYRUS access your microphone for live voice commands? "
            "Your microphone stays off unless you choose Yes. "
            "Speech transcription uses the online recognition service.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.append_log(
                "[MICROPHONE]: Permission granted for this session. "
                "Opening the selected input device..."
            )
            self.set_mic_muted(False)
            return True

        self.append_log(
            "[MICROPHONE]: Permission not granted. Typed chat remains available."
        )
        self.set_mic_muted(True)
        return False

    def apply_dashboard_customization(self):
        panels = getattr(self, "dashboard_panels", {})
        if panels:
            visibility = self.user_preferences.get("panels", {})
            for key, panel in panels.items():
                panel.setVisible(visibility.get(key, True))
            order = self.user_preferences.get(
                "panel_order", ["telemetry", "reactor", "terminal"]
            )
            if set(order) == set(panels):
                stretch = {"telemetry": 2, "reactor": 5, "terminal": 3}
                for key in order:
                    self.panels_layout.removeWidget(panels[key])
                for key in order:
                    self.panels_layout.addWidget(panels[key], stretch[key])
        if not self.isMaximized():
            width, height = self._dashboard_size()
            self.setMinimumSize(min(600, width), min(400, height))
            self._update_responsive_layout(width)
            self.resize(width, height)
        self._update_responsive_layout()
        self.setWindowOpacity(max(0.4, min(1.0, self.dashboard_brightness / 100)))

    def _dashboard_size(self):
        scale = max(80, min(120, int(self.dashboard_scale))) / 100
        width, height = int(1150 * scale), int(720 * scale)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(width, max(1, available.width() - 24))
            height = min(height, max(1, available.height() - 24))
        return width, height

    def _update_responsive_layout(self, width=None):
        width = self.width() if width is None else width
        compact = width < 950
        self.dash_title.setVisible(not compact)
        self.badge_lbl.setVisible(width >= 800)
        self.telemetry_title.setText(
            "// 01. TELEMETRY" if compact else "// 01. TELEMETRY MONITOR"
        )
        self.term_title.setText(
            "// 03. CHAT" if compact else "// 03. TACTICAL TERMINAL & CHAT"
        )
        self.stream_badge.setText("● LIVE" if compact else "● STREAM ACTIVE")

    def show_reminder_alert(self, message: str):
        self.append_log(f"[REMINDER]: {message}")
        alert = QMessageBox(self)
        alert.setIcon(QMessageBox.Icon.Information)
        alert.setWindowTitle("CYRUS reminder")
        alert.setText(message)
        alert.setStandardButtons(QMessageBox.StandardButton.Ok)
        alert.setWindowModality(Qt.WindowModality.NonModal)
        alert.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._reminder_alerts.append(alert)
        alert.finished.connect(lambda _result, current=alert: self._forget_reminder_alert(current))
        self._play_alarm_sound()
        self.alarm_timer.start(1200)
        alert.show()

    def _ensure_alarm_audio_file(self) -> Path:
        if self._alarm_audio_path and self._alarm_audio_path.is_file():
            return self._alarm_audio_path

        custom_audio_path = get_user_data_dir() / "reminder_alarm.wav"
        if custom_audio_path.is_file():
            return custom_audio_path

        bundled_audio_path = PROJECT_ROOT / "assets" / "reminder_alarm.wav"
        if bundled_audio_path.is_file():
            return bundled_audio_path

        audio_path = Path(tempfile.gettempdir()) / (
            f"cyrus-reminder-alarm-{os.getpid()}.wav"
        )
        sample_rate = 22050
        sample_count = sample_rate
        samples = array("h")
        for index in range(sample_count):
            pulse = (index // (sample_rate // 5)) % 2 == 0
            frequency = 1046 if (index // (sample_rate // 2)) % 2 == 0 else 1318
            value = (
                int(32767 * 0.72 * math.sin(2 * math.pi * frequency * index / sample_rate))
                if pulse
                else 0
            )
            samples.append(value)
        with wave.open(str(audio_path), "wb") as audio_file:
            audio_file.setnchannels(1)
            audio_file.setsampwidth(2)
            audio_file.setframerate(sample_rate)
            audio_file.writeframes(samples.tobytes())
        self._alarm_audio_path = audio_path
        return audio_path

    def _play_alarm_sound(self):
        try:
            if winsound is not None:
                if self._alarm_playing:
                    return
                audio_path = self._ensure_alarm_audio_file()
                winsound.PlaySound(
                    str(audio_path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP,
                )
                self._alarm_playing = True
            else:
                QApplication.beep()
        except (OSError, RuntimeError) as error:
            print(f"[Reminder Alarm Warning]: Could not play alert sound: {error}")
            self.alarm_timer.stop()

    def cleanup_alarm_audio(self):
        if winsound is not None and self._alarm_playing:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except (RuntimeError, OSError) as error:
                print(f"[Reminder Alarm Warning]: Could not stop alarm audio: {error}")
        self._alarm_playing = False
        if self._alarm_audio_path is not None:
            try:
                self._alarm_audio_path.unlink(missing_ok=True)
            except OSError as error:
                print(f"[Reminder Alarm Warning]: Could not remove temporary alarm: {error}")
            self._alarm_audio_path = None

    def set_active_reminders(self, reminders):
        self._active_reminders = [
            dict(reminder)
            for reminder in reminders
            if isinstance(reminder, dict)
            and isinstance(reminder.get("due_at"), str)
            and isinstance(reminder.get("message"), str)
        ]
        self.refresh_reminder_countdowns()

    def refresh_reminder_countdowns(self):
        now = datetime.now(timezone.utc)
        countdowns = []
        nearest_countdown = None
        for reminder in getattr(self, "_active_reminders", []):
            try:
                due_at = datetime.fromisoformat(reminder["due_at"])
            except ValueError as error:
                print(f"[Reminder Display Warning]: Ignoring invalid due time: {error}")
                continue
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=timezone.utc)
            remaining = math.ceil((due_at - now).total_seconds())
            if remaining <= 0:
                continue
            days, remaining = divmod(remaining, 86400)
            hours, remaining = divmod(remaining, 3600)
            minutes, seconds = divmod(remaining, 60)
            if days:
                time_left = f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
            elif hours:
                time_left = f"{hours:02}:{minutes:02}:{seconds:02}"
            else:
                time_left = f"{minutes:02}:{seconds:02}"
            kind = reminder.get("kind")
            name = reminder["message"].strip()
            if kind not in {"timer", "reminder"}:
                kind = "reminder" if name.lower() not in {"timer", "timer finished"} else "timer"
            if name.lower() in {"timer finished", "timer", "reminder"}:
                name = "Timer" if kind == "timer" else "Reminder"
            label = name.upper() if kind == "reminder" else "TIMER"
            countdowns.append(f"{label}  •  {time_left}")
            if nearest_countdown is None or remaining < nearest_countdown[0]:
                nearest_countdown = (remaining, label)

        self.countdown_label.setText("\n".join(countdowns))
        self.countdown_panel.setVisible(bool(countdowns) and not self.is_pill_mode)
        if self.is_pill_mode:
            if nearest_countdown is not None:
                remaining, label = nearest_countdown
                minutes, seconds = divmod(remaining, 60)
                self.pill_status_label.setText(
                    f"● {label[:18]} {minutes:02}:{seconds:02}"
                )
            else:
                self.pill_status_label.setText(
                    f"● CYRUS {self.current_state or 'READY'}"
                )

    def _forget_reminder_alert(self, alert):
        if alert in self._reminder_alerts:
            self._reminder_alerts.remove(alert)
        if not self._reminder_alerts:
            self.alarm_timer.stop()
            if winsound is not None and self._alarm_playing:
                try:
                    winsound.PlaySound(None, winsound.SND_PURGE)
                except (RuntimeError, OSError) as error:
                    print(f"[Reminder Alarm Warning]: Could not stop alarm audio: {error}")
                self._alarm_playing = False

    def _on_voice_volume_changed(self, volume: int):
        self.voice_volume = volume
        self.voice_volume_value.setText(f"{volume}%")
        self.voice_volume_changed_signal.emit(volume)
        self.voice_volume_save_timer.start(400)

    def _save_voice_volume_preference(self):
        self.user_preferences["voice_volume"] = self.voice_volume
        self.user_preferences["system_volume"] = self.system_volume
        self.user_preferences["player_volume"] = self.player_volume
        if not save_user_state(self.user_preferences):
            message = "[Settings Error]: Could not save the volume preferences."
            print(message)
            self.append_log(message)

    def set_volume_levels(self, system_volume: int, player_volume: int):
        self.system_volume = max(0, min(100, system_volume))
        self.player_volume = max(0, min(100, player_volume))
        self.system_volume_slider.blockSignals(True)
        self.player_volume_slider.blockSignals(True)
        self.system_volume_slider.setValue(self.system_volume)
        self.player_volume_slider.setValue(self.player_volume)
        self.system_volume_slider.blockSignals(False)
        self.player_volume_slider.blockSignals(False)
        self.system_volume_value.setText(f"{self.system_volume}%")
        self.player_volume_value.setText(f"{self.player_volume}%")
        self.voice_volume_save_timer.start(400)

    def _on_system_volume_changed(self, volume: int):
        self.system_volume = volume
        self.system_volume_value.setText(f"{volume}%")
        self.system_volume_apply_timer.start(150)
        self.voice_volume_save_timer.start(400)

    def _on_player_volume_changed(self, volume: int):
        self.player_volume = volume
        self.player_volume_value.setText(f"{volume}%")
        self.player_volume_apply_timer.start(150)
        self.voice_volume_save_timer.start(400)

    def _apply_system_volume(self):
        self.system_volume_changed_signal.emit(self.system_volume)

    def _apply_player_volume(self):
        self.player_volume_changed_signal.emit(self.player_volume)

    def confirm_sensitive_action(self, action: str):
        prompts = {
            "shutdown_pc": (
                "Shut down this computer?",
                "CYRUS will request an operating-system shutdown after confirmation.",
            ),
            "lock_pc": ("Lock this computer?", "Your Windows session will be locked."),
            "shutdown_cyrus": ("Close CYRUS?", "The assistant will exit."),
        }
        title, message = prompts.get(action, ("Confirm action", action))
        result = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.confirmed_action_signal.emit(action)
        else:
            self.append_log(f"[ACTION]: Cancelled {action.replace('_', ' ')}.")

    @pyqtSlot()
    def toggle_mic(self):
        """Toggles microphone mute state."""
        if not self.microphone_input_enabled:
            return
        self.set_mic_muted(not self.is_mic_muted)

    def set_microphone_input_enabled(self, enabled: bool):
        self.microphone_input_enabled = bool(enabled)
        self.btn_mic.setEnabled(self.microphone_input_enabled)
        self.pill_btn_mic.setEnabled(self.microphone_input_enabled)
        if not self.microphone_input_enabled:
            self.btn_mic.setToolTip("Microphone input was not selected during setup.")
            self.pill_btn_mic.setToolTip(
                "Microphone input was not selected during setup."
            )
            self.set_mic_muted(True)

    def prompt_ai_provider(self, portable: bool) -> str | None:
        if portable:
            return "openrouter"

        dialog = QMessageBox(self)
        dialog.setWindowTitle("CYRUS AI Provider")
        dialog.setText("Choose the AI engine CYRUS should use.")
        dialog.setInformativeText(
            "Ollama runs locally. OpenRouter requires an API key and internet access."
        )
        ollama_button = dialog.addButton(
            "Option A: Ollama (Local Engine)",
            QMessageBox.ButtonRole.ActionRole,
        )
        openrouter_button = dialog.addButton(
            "Option B: OpenRouter (Cloud API)",
            QMessageBox.ButtonRole.ActionRole,
        )
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(openrouter_button)
        dialog.exec()
        if dialog.clickedButton() is ollama_button:
            return "ollama"
        if dialog.clickedButton() is openrouter_button:
            return "openrouter"
        return None

    def prompt_openrouter_api_key(self) -> str | None:
        api_key, accepted = QInputDialog.getText(
            self,
            "OpenRouter API Key",
            "Enter your OpenRouter API key:",
            QLineEdit.EchoMode.Password,
        )
        return api_key.strip() if accepted and api_key.strip() else None

    def set_voice_output_status(self, selected: bool, available: bool):
        self.voice_volume_panel.setVisible(bool(selected))
        self.voice_volume_slider.setEnabled(bool(selected and available))
        self.voice_volume_value.setEnabled(bool(selected and available))
        self.voice_download_help.setVisible(bool(selected and not available))

    def set_voice_output_initializing(self, selected: bool):
        if selected:
            self.voice_download_help.hide()

    def set_mic_muted(self, muted: bool):
        """Sets microphone mute state, emits signal, and refreshes UI feedback."""
        if self.is_mic_muted == muted:
            return

        self.is_mic_muted = muted
        self.update_mic_ui()
        self.mic_toggled_signal.emit(muted)

        timestamp = time.strftime("%H:%M:%S")
        if muted:
            self.log_terminal.append(f"[{timestamp}] [AUDIO_IO]: Microphone MUTED - Input halted. (Use Chat Box below)")
            self.set_state("MUTED", "MIC OFF // CHAT READY")
        else:
            self.log_terminal.append(
                f"[{timestamp}] [AUDIO_IO]: Microphone enabled - waiting for speech."
            )
            self.set_state("LISTENING", "MIC ON // SPEAK NOW")

    def _create_volume_control(self, parent, label: str, initial_value: int, callback):
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(6)

        title = QLabel(label)
        title.setMinimumWidth(48)
        title.setStyleSheet(
            "color: #75dff5; font-family: 'Consolas'; font-size: 8px; "
            "font-weight: bold; border: none; background: transparent;"
        )
        slider = QSlider(Qt.Orientation.Horizontal, parent)
        slider.setRange(0, 100)
        slider.setValue(initial_value)
        slider.setToolTip(f"Adjust {label.lower()} audio volume")
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 5px;
                background: rgba(89, 134, 153, 100);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #00d9f5;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 12px;
                margin: -4px 0;
                background: #b6f7ff;
                border: 1px solid #00d9f5;
                border-radius: 6px;
            }
        """)
        value = QLabel(f"{initial_value}%")
        value.setMinimumWidth(36)
        value.setAlignment(Qt.AlignmentFlag.AlignRight)
        value.setStyleSheet(
            "color: #55f5ff; font-family: 'Consolas'; font-size: 8px; "
            "font-weight: bold; border: none; background: transparent;"
        )

        layout.addWidget(title)
        layout.addWidget(slider, 1)
        layout.addWidget(value)
        slider.valueChanged.connect(callback)
        return layout, slider, value

    def _create_cyber_progress_bar(self) -> QProgressBar:
        """Helper to create unified high-tech cyber progress bars."""
        bar = QProgressBar(self)
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(0, 240, 255, 70);
                border-radius: 4px;
                background-color: rgba(5, 10, 20, 220);
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #006680, 
                    stop:0.5 #00d2ea, 
                    stop:1 #55f5ff);
                border-radius: 3px;
            }
        """)
        return bar

    def init_telemetry_timer(self):
        """Initializes non-blocking periodic system metrics polling."""
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self.update_telemetry)
        self.telemetry_timer.start(1800)
        self.update_telemetry()

    def update_telemetry(self):
        """Refreshes CPU, RAM, and Disk telemetry dynamically with graceful fallbacks."""
        if not psutil:
            return

        try:
            cpu_val = psutil.cpu_percent(interval=None)
            self.cpu_label.setText(f"CPU LOAD: {cpu_val:.1f}%")
            self.cpu_bar.setValue(int(cpu_val))

            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            self.mem_label.setText(f"RAM USAGE: {used_gb:.1f} / {total_gb:.1f} GB")
            self.mem_bar.setValue(int(mem.percent))

            try:
                disk = psutil.disk_usage(os.path.abspath(os.sep))
                self.disk_label.setText(f"SYSTEM DISK: {disk.percent:.0f}%")
                self.disk_bar.setValue(int(disk.percent))
            except OSError as error:
                print(f"[Telemetry Warning]: Could not read system disk usage: {error}")
                disk = None
        except (psutil.Error, OSError, AttributeError, TypeError, ValueError) as error:
            print(f"[Telemetry Warning]: Could not refresh system metrics: {error}")

    def switchToPillMode(self):
        """Collapses the interface into the compact Dynamic Island floating pill."""
        if self.isMaximized():
            self.showNormal()
        self.is_pill_mode = True
        self.dashboard_container.hide()
        self.pill_container.show()

        self.setMinimumSize(0, 0)
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        width = min(400, available.width()) if available is not None else 400
        self.resize(width, 56)
        if available is not None:
            self.move(
                available.x() + (available.width() - width) // 2,
                available.y() + 15,
            )
        self.show()

    def switchToDashboardMode(self):
        """Expands the interface to full Tactical JARVIS Operations Dashboard."""
        self.is_pill_mode = False
        self.pill_container.hide()
        self.dashboard_container.show()

        width, height = self._dashboard_size()
        self.setMinimumSize(min(600, width), min(400, height))
        self._update_responsive_layout(width)
        self.resize(width, height)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.move(
                available.x() + (available.width() - self.width()) // 2,
                available.y() + (available.height() - self.height()) // 2,
            )
        self._update_responsive_layout()
        self.refresh_reminder_countdowns()
        self.show()

    def handle_file_drop(self, file_path: str):
        filename = os.path.basename(file_path)
        timestamp = time.strftime("%H:%M:%S")
        self.log_terminal.append(f"[{timestamp}] [INSPECTOR]: Ingested -> {filename}")
        self.file_inspected_signal.emit(file_path)

        if self.is_pill_mode:
            trunc_name = filename if len(filename) <= 18 else filename[:15] + "..."
            self.pill_status_label.setText(f"● INGEST: {trunc_name}")

    def set_state(self, state: str, text: str = ""):
        """Thread-safe state change entrypoint."""
        self._state_signal.emit(state, text)

    def append_log(self, message: str):
        self.log_message_signal.emit(message)

    def set_music_state(self, title: str, status: str, visible: bool, playing: bool):
        self.music_state_signal.emit(title, status, visible, playing)

    def _apply_music_state(self, title: str, status: str, visible: bool, playing: bool):
        self.music_title_label.setText(f"{title} — {status}")
        self.music_player_bar.setVisible(visible)
        self.music_play_pause_button.setText("⏸" if playing else "▶")
        self.music_play_pause_button.setToolTip("Pause playback" if playing else "Resume playback")

    def _apply_state(self, state: str, text: str):
        """Applies state changes onto GUI components on the main Qt thread."""
        display_text = f"[{state}] {text}" if text else f"[{state}]"
        detail_text = text.upper() if text else f"CORE STATE: {state} // STANDBY"
        if len(detail_text) > 56:
            detail_text = f"{detail_text[:53].rstrip()}..."
        timestamp = time.strftime("%H:%M:%S")

        state_changed = (self.current_state != state or self.current_subtext != text)
        self.current_state = state
        self.current_subtext = text

        self.status_label.setText(f"[{state}]")
        self.pill_status_label.setText(f"● CYRUS {state}")
        self.header_state_badge.setText(f"STATUS: {state}")
        
        self.substatus_label.setText(detail_text)

        if state_changed:
            self.log_terminal.append(f"[{timestamp}] [STATE]: {display_text}")
            scrollbar = self.log_terminal.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        if self.is_pill_mode:
            self.refresh_reminder_countdowns()

    # Allow smooth dragging of the entire frameless window anywhere on screen
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.isMaximized():
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "term_title"):
            self._update_responsive_layout()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self.isMaximized():
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    # Double-clicking the Dynamic Island pill expands it into full Dashboard mode
    def mouseDoubleClickEvent(self, event):
        if self.is_pill_mode:
            self.switchToDashboardMode()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.exists(file_path):
                self.drop_zone.set_inspected_file(file_path)
                self.handle_file_drop(file_path)
                break
    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Any File for CYRUS Inspection", 
            "", 
            "All Files (*.*)"
        )
        if file_path:
            self.append_log(f"[INSPECTOR]: Selected -> {os.path.basename(file_path)}")
            self.file_inspected_signal.emit(file_path)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    hud = DynamicIslandHUD()
    hud.show()
    sys.exit(app.exec())
