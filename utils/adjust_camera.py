# Edit config.yaml and preview the camera.
#
# One-time setup (run from the repository root):
#   python3 -m venv utils/.venv
#   source utils/.venv/bin/activate
#   python -m pip install opencv-python PyYAML PyQt5
#
# On Windows PowerShell, create and activate the environment with:
#   py -m venv utils/.venv
#   .\utils\.venv\Scripts\Activate.ps1
# Then run the same pip install command above.
#
# Each time you use the script, activate the environment, then run:
#   python utils/adjust_camera.py
# When finished, leave the environment with: deactivate

from pathlib import Path
import math
import os
import stat
import sys

import cv2
import yaml
from PyQt5.QtCore import QLibraryInfo, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QLabel, QMessageBox, QPushButton, QPlainTextEdit,
    QVBoxLayout, QWidget,
)


CONFIG_PATH = Path(__file__).with_name("config.yaml")


def prepare_qt_plugins():
    # Qt skips plugins marked hidden by macOS. Make them visible before startup.
    if sys.platform == "darwin":
        plugins = Path(QLibraryInfo.location(QLibraryInfo.PluginsPath)) / "platforms"
        for plugin in plugins.glob("*.dylib"):
            flags = plugin.stat().st_flags
            if flags & stat.UF_HIDDEN:
                os.chflags(plugin, flags & ~stat.UF_HIDDEN)


class CameraSettingsApp(QWidget):
    def __init__(self):
        super().__init__()
        self.camera = None
        self.camera_index = None
        self.config = None

        self.setWindowTitle("Camera settings")
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Camera feed (left) / threshold mask (right)"))
        self.preview = QLabel("Camera preview")
        layout.addWidget(self.preview)

        layout.addWidget(QLabel("Edit config.yaml, then click Update:"))
        self.settings_text = QPlainTextEdit()
        self.settings_text.setPlainText(CONFIG_PATH.read_text())
        self.settings_text.setMinimumSize(650, 220)
        layout.addWidget(self.settings_text)

        update_button = QPushButton("Update")
        update_button.clicked.connect(lambda: self.update_settings())
        layout.addWidget(update_button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.update_settings(save=False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_preview)
        self.timer.start(30)

    def update_settings(self, save=True):
        text = self.settings_text.toPlainText()
        try:
            config = yaml.safe_load(text)
            if not isinstance(config, dict):
                raise ValueError("The config must contain named settings and values.")

            enemy_color = config.get("enemy_color")
            if not isinstance(enemy_color, str) or enemy_color.lower() not in ("red", "blue"):
                raise ValueError("enemy_color must be red or blue.")
            lower = config.get("lower_threshold")
            upper = config.get("upper_threshold")
            if type(lower) is not int or type(upper) is not int or not 0 <= lower <= upper <= 255:
                raise ValueError("Thresholds must be integers: 0 <= lower <= upper <= 255.")

            camera_index = config.get("camera_index", 0)
            if type(camera_index) is not int or camera_index < 0:
                raise ValueError("camera_index must be a non-negative integer.")

            settings = config.get("opencv", {})
            if not isinstance(settings, dict):
                raise ValueError("opencv must contain property names and numeric values.")

            # Validate everything before changing the camera or saving the file.
            for name, value in settings.items():
                if (not isinstance(name, str) or not name.startswith("CAP_PROP_")
                        or not hasattr(cv2, name)):
                    raise ValueError(f"Unknown OpenCV property: {name}")
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError(f"{name} must have a finite numeric value.")

            if self.camera is None or camera_index != self.camera_index:
                new_camera = cv2.VideoCapture(camera_index)
                if not new_camera.isOpened():
                    new_camera.release()
                    raise ValueError(f"Could not open camera {camera_index}.")
                if self.camera is not None:
                    self.camera.release()
                self.camera = new_camera
                self.camera_index = camera_index

            rejected = []
            for name, value in settings.items():
                if not self.camera.set(getattr(cv2, name), float(value)):
                    rejected.append(name)

            # Save the original text so YAML comments and formatting are kept.
            if save:
                CONFIG_PATH.write_text(text)
            self.config = config

            status = "Config saved and camera updated." if save else "Camera opened."
            if rejected:
                status += " Camera rejected: " + ", ".join(rejected)
            self.status.setText(status)
        except (ValueError, OverflowError, OSError, yaml.YAMLError, cv2.error) as error:
            QMessageBox.warning(self, "Camera settings", str(error))

    def update_preview(self):
        if self.camera is not None and self.config is not None:
            success, frame = self.camera.read()
            if success:
                # OpenCV frames are BGR. Subtract the other color to isolate the enemy.
                if self.config["enemy_color"].lower() == "red":
                    difference = cv2.subtract(frame[:, :, 2], frame[:, :, 0])
                else:
                    difference = cv2.subtract(frame[:, :, 0], frame[:, :, 2])
                mask = cv2.inRange(
                    difference,
                    self.config["lower_threshold"],
                    self.config["upper_threshold"],
                )
                frame = cv2.hconcat([frame, cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)])

                # Keep the preview small without changing the capture resolution.
                height, width = frame.shape[:2]
                scale = min(1000 / width, 450 / height, 1)
                if scale < 1:
                    frame = cv2.resize(frame, (int(width * scale), int(height * scale)))

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width = frame.shape[:2]
                image = QImage(
                    frame.data, width, height, frame.strides[0], QImage.Format_RGB888
                ).copy()
                self.preview.setPixmap(QPixmap.fromImage(image))
            else:
                self.preview.clear()
                self.preview.setText("Could not read a camera frame.")

    def closeEvent(self, event):
        self.timer.stop()
        if self.camera is not None:
            self.camera.release()
        event.accept()


if __name__ == "__main__":
    prepare_qt_plugins()
    app = QApplication(sys.argv)
    window = CameraSettingsApp()
    window.show()
    sys.exit(app.exec_())
