"""Helpers for driving experiment windows without real input devices."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from app.ui.experiment_window import State


def press_key(window, key: Qt.Key) -> None:
    window.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def mouse(window, kind, device_point: QPointF) -> None:
    dpr = window.devicePixelRatioF()
    pos = QPointF(device_point.x() / dpr, device_point.y() / dpr)
    button = Qt.MouseButton.LeftButton if kind != QMouseEvent.Type.MouseMove else Qt.MouseButton.NoButton
    event = QMouseEvent(kind, pos, window.mapToGlobal(pos.toPoint()), button, button,
                        Qt.KeyboardModifier.NoModifier)
    if kind == QMouseEvent.Type.MouseMove:
        window.mouseMoveEvent(event)
    else:
        window.mousePressEvent(event)


def move(window, point: QPointF) -> None:
    mouse(window, QMouseEvent.Type.MouseMove, point)


def click(window, point: QPointF) -> None:
    mouse(window, QMouseEvent.Type.MouseButtonPress, point)


def show_target(window, qapp, fallback: bool = False) -> None:
    """Skip the foreperiod and make the stimulus visible (t = 0).

    Headless platforms may not deliver a paint, so a paint is simulated
    unless ``fallback`` asks for the onset fallback path.
    """
    window.foreperiod_timer.stop()
    if fallback:
        window.repaint = lambda: None  # the target paint never arrives before the fallback fires
        window._show_target()
        del window.repaint
        window._onset_fallback()
    else:
        window._show_target()
    qapp.processEvents()
    if window.state == State.TARGET_PENDING:
        window._on_target_painted()
    assert window.state == State.TARGET


def stabilize(window) -> None:
    """Complete the stabilisation period immediately (cursor already held still)."""
    assert window.state == State.STABILIZING
    window.stabilize_timer.stop()
    window._on_stable()
    assert window.state == State.FOREPERIOD


def begin_foreperiod(window) -> None:
    center = window._center_px()
    move(window, center)
    click(window, center)
    stabilize(window)


def start_trial(window, qapp, fallback: bool = False) -> None:
    begin_foreperiod(window)
    show_target(window, qapp, fallback)
