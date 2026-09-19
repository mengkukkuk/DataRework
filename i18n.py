"""JSON message catalogs with named placeholders and persistent EN/TH selection."""
import json
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal


_ROOT = Path(__file__).resolve().parent / "locales"
CATALOGS = {code: json.loads((_ROOT / f"{code}.json").read_text(encoding="utf-8"))
            for code in ("en", "th")}


class Language(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        saved = QSettings("DataRework", "ProductionRework").value("language", "en")
        self.code = saved if saved in CATALOGS else "en"

    def set(self, code):
        if code not in CATALOGS or code == self.code:
            return
        self.code = code
        QSettings("DataRework", "ProductionRework").setValue("language", code)
        self.changed.emit()


language = Language()


class Message(str):
    """A string retaining its key/parameters so visible widgets can retranslate."""
    def __new__(cls, key, **params):
        value = CATALOGS[language.code].get(key, CATALOGS["en"].get(key, key))
        rendered = {k: v.render() if isinstance(v, Message) else v for k, v in params.items()}
        obj = super().__new__(cls, value.format(**rendered) if params else value)
        obj.key, obj.params = key, params
        return obj

    def render(self):
        return str(Message(self.key, **self.params))

    def __add__(self, other):
        return Message("{left}{right}", left=self, right=other)

    def __radd__(self, other):
        return Message("{left}{right}", left=other, right=self)

    def join(self, values):
        result = Message("")
        for index, value in enumerate(values):
            if index:
                result = result + self
            result = result + value
        return result


def tr(key, **params):
    return Message(key, **params)


def column_label(name):
    # Unknown deployment-specific columns remain visible with their original name.
    return tr(name)
