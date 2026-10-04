"""Display-only English/Japanese localization.

English source strings are the translation keys. Japanese text lives in
:mod:`app.i18n_ja`; a missing entry falls back to English. Translation is a
presentation concern only: stored database values, exported CSV/JSON headers,
enum values and protocol identifiers always stay English/canonical.

The application always starts in English (no persisted preference).
"""

from __future__ import annotations

import re
from enum import StrEnum

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTableWidget,
    QTabWidget,
    QTextEdit,
    QWidget,
)

from app.i18n_ja import JA

# Reverse lookup: Japanese text -> English source (first wins on duplicates).
_REVERSE: dict[str, str] = {}
for _en, _ja in JA.items():
    _REVERSE.setdefault(_ja, _en)


class Language(StrEnum):
    EN = "en"
    JA = "ja"


class Translator(QObject):
    """Holds the current UI language and announces changes."""

    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._language = Language.EN

    @property
    def language(self) -> Language:
        return self._language

    def set_language(self, language: Language | str) -> None:
        language = Language(language)
        if language == self._language:
            return
        self._language = language
        self.language_changed.emit(str(language))

    def toggle(self) -> Language:
        self.set_language(Language.JA if self._language == Language.EN else Language.EN)
        return self._language


translator = Translator()


def current_language() -> Language:
    return translator.language


def is_japanese() -> bool:
    return translator.language == Language.JA


def tr(text: str, **values: object) -> str:
    """Translate an English source string, then apply ``str.format`` values."""
    result = JA.get(text, text) if translator.language == Language.JA else text
    if values:
        try:
            return result.format(**values)
        except (KeyError, IndexError, ValueError):
            return text.format(**values)
    return result


def to_english(text: str) -> str:
    """Map a displayed (possibly Japanese) exact string back to its English source."""
    return _REVERSE.get(text, text)


def translate_exact(text: str) -> str | None:
    """Return ``text`` in the current language if it is a known exact string, else None."""
    if not text:
        return None
    source = _REVERSE.get(text, text)
    if source not in JA:
        return None
    return JA[source] if translator.language == Language.JA else source


_FIELD_NAMES = {
    "color": "Color",
    "size": "Size",
    "thickness": "Thickness",
    "gap": "Gap",
    "outline_thickness": "Outline thickness",
    "opacity": "Opacity",
    "outline_enabled": "Outline",
}

# Dynamic validation/status messages: (pattern, Japanese template using groups).
_MESSAGE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(\w+) must be between (\S+) and (\S+) \(got (.+)\)\.$"),
     "{0}は{1}〜{2}の範囲で指定してください（入力値: {3}）。"),
    (re.compile(r"^(\w+) must be a number \(got (.+)\)\.$"),
     "{0}は数値で指定してください（入力値: {1}）。"),
    (re.compile(r"^(\w+) must be finite \(got (.+)\)\.$"),
     "{0}は有限の数値で指定してください（入力値: {1}）。"),
    (re.compile(r"^(.+) must be greater than 0 \(got (.+)\)\.$"),
     "{0}は0より大きい値で指定してください（入力値: {1}）。"),
    (re.compile(r"^color must be a hex colour like #RRGGBB(?: \(got (.*)\))?\.$"),
     "色は #RRGGBB 形式の16進数で指定してください。"),
    (re.compile(r"^outline_enabled must be true or false \(got (.+)\)\.$"),
     "アウトラインはオン/オフで指定してください（入力値: {0}）。"),
    # Stored session note (the leading empty group keeps the identifier untranslated).
    (re.compile(r"^()Placeholder task parameters \((\w+_task\.confirmed = false)\)\.$"),
     "仮の課題パラメータです（{1}）。"),
]


def tr_message(text: str) -> str:
    """Translate an exact or known dynamic (validation) message; else return it as is."""
    if translator.language != Language.JA:
        return text
    if text in JA:
        return JA[text]
    for pattern, template in _MESSAGE_PATTERNS:
        match = pattern.match(text)
        if match:
            groups = [g if g is not None else "" for g in match.groups()]
            if groups:
                groups[0] = tr(_FIELD_NAMES.get(groups[0], groups[0]))
            return template.format(*groups)
    return text


def display(value: object) -> str:
    """Display text for a canonical stored value (enum/status code).

    English display shows the canonical value unchanged; Japanese display uses
    the translation of the code. The stored value itself is never modified.
    """
    text = "" if value is None else str(value)
    return tr(text)


# --------------------------------------------------------------------- widgets
# Several English strings can share one Japanese translation ("Trial"/"Trials"),
# so every translated text slot remembers its English source. Reverse lookup is
# only a fallback for text that was set while Japanese was already active.
_SOURCE_PROPERTY = "i18n_source"
_VALUES_PROPERTY = "i18n_values"
_STATIC_PROPERTY = "i18n_static"
_ITEM_SOURCE_ROLE = Qt.ItemDataRole.UserRole + 64


def _resolve_source(current: str, stored: str | None) -> str | None:
    """English source of ``current``: the remembered one if the text is unchanged."""
    if not current:
        return None
    if stored and current in (stored, JA.get(stored)):
        return stored
    if current in JA:
        return current
    return _REVERSE.get(current)


def _retranslate_slot(current: str, stored: str | None, set_text, set_source) -> None:
    source = _resolve_source(current, stored)
    if source is None or source not in JA:
        if stored:
            set_source(None)
        return
    if source != stored:
        set_source(source)
    target = JA[source] if translator.language == Language.JA else source
    if target != current:
        set_text(target)


def _property_slot(widget: QWidget, name: str, current: str, set_text) -> None:
    _retranslate_slot(current, widget.property(name) or None, set_text,
                      lambda value: widget.setProperty(name, value))


def _item_slot(item, current: str, set_text) -> None:
    _retranslate_slot(current, item.data(_ITEM_SOURCE_ROLE) or None, set_text,
                      lambda value: item.setData(_ITEM_SOURCE_ROLE, value))


def mark_source(widget: QWidget, source: str) -> None:
    """Remember the English source of a label/button text created with ``tr``."""
    if source in JA:
        widget.setProperty(_STATIC_PROPERTY, source)


def set_tr_text(widget: QWidget, source: str | None, **values: object) -> None:
    """Set a label/button text from an English template and remember it.

    Widgets set this way are re-formatted in the new language on every
    language change, so formatted texts (with numbers, IDs, ...) also switch.
    Passing ``None`` clears the binding and the text.
    """
    if source is None:
        clear_tr_binding(widget)
        widget.setText("")  # type: ignore[attr-defined]
        return
    safe = {
        key: value if isinstance(value, (int, float, str)) else str(value)
        for key, value in values.items()
    }
    widget.setProperty(_SOURCE_PROPERTY, source)
    widget.setProperty(_VALUES_PROPERTY, safe or None)
    widget.setText(tr(source, **safe) if safe else tr_message(source))  # type: ignore[attr-defined]


def clear_tr_binding(widget: QWidget) -> None:
    widget.setProperty(_SOURCE_PROPERTY, None)
    widget.setProperty(_VALUES_PROPERTY, None)


def retranslate_widget(widget: QWidget) -> None:
    """Translate the static texts of a single widget in place."""
    source = widget.property(_SOURCE_PROPERTY)
    if source and isinstance(widget, (QLabel, QAbstractButton)):
        values = widget.property(_VALUES_PROPERTY) or {}
        widget.setText(tr(source, **values) if values else tr_message(source))
    elif isinstance(widget, (QLabel, QAbstractButton)):
        _property_slot(widget, _STATIC_PROPERTY, widget.text(), widget.setText)
    elif isinstance(widget, QGroupBox):
        _property_slot(widget, _STATIC_PROPERTY, widget.title(), widget.setTitle)
    elif isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
        _property_slot(widget, "i18n_placeholder", widget.placeholderText(), widget.setPlaceholderText)
    elif isinstance(widget, QComboBox) and not widget.isEditable():
        for index in range(widget.count()):
            stored = widget.itemData(index, _ITEM_SOURCE_ROLE) or None
            _retranslate_slot(
                widget.itemText(index), stored,
                lambda text, i=index: widget.setItemText(i, text),
                lambda value, i=index: widget.setItemData(i, value, _ITEM_SOURCE_ROLE),
            )
    elif isinstance(widget, QTabWidget):
        sources = dict(widget.property("i18n_tabs") or {})
        for index in range(widget.count()):
            def remember(value, i=index):
                sources[str(i)] = value
            _retranslate_slot(widget.tabText(index), sources.get(str(index)),
                              lambda text, i=index: widget.setTabText(i, text), remember)
        widget.setProperty("i18n_tabs", sources)
    elif isinstance(widget, QTableWidget):
        for column in range(widget.columnCount()):
            item = widget.horizontalHeaderItem(column)
            if item is not None:
                _item_slot(item, item.text(), item.setText)
        for row in range(widget.rowCount()):
            for column in range(widget.columnCount()):
                item = widget.item(row, column)
                if item is not None:
                    _item_slot(item, item.text(), item.setText)
    tooltip = widget.toolTip()
    if tooltip:
        _property_slot(widget, "i18n_tooltip", tooltip, widget.setToolTip)
    if widget.isWindow():
        _property_slot(widget, "i18n_title", widget.windowTitle(), widget.setWindowTitle)


def retranslate_tree(root: QWidget) -> None:
    """Translate ``root`` and all of its descendant widgets."""
    retranslate_widget(root)
    for child in root.findChildren(QWidget):
        retranslate_widget(child)


class WindowTranslationFilter(QObject):
    """Application event filter: translates top-level windows when they are shown.

    Covers message boxes, dialogs and experiment windows created while Japanese
    is active.
    """

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if (
            event.type() == QEvent.Type.Show
            and isinstance(obj, QWidget)
            and obj.isWindow()
            and translator.language == Language.JA
        ):
            retranslate_tree(obj)
        return False
