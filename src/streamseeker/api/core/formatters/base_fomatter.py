from __future__ import annotations

import re
import logging

from typing import ClassVar

from cleo.exceptions import CleoValueError
from cleo.formatters.style import Style
from cleo.formatters.style_stack import StyleStack

from streamseeker.api.core.helpers import Singleton

LOADING = 24
SUCCESS = 25

COLORS = {
    "black": "\033[0;30m",
    "red": "\033[0;31m",
    "green": "\033[0;32m",
    "yellow": "\033[0;33m",
    "blue": "\033[0;34m",
    "purple": "\033[0;35m",
    "cyan": "\033[0;36m",
    "white": "\033[0;37m",
    "default": "\033[0;39m",
    "dark_grey": "\033[1;30m",
    "bold_red": "\033[1;31m",
    "bold_green": "\033[1;32m",
    "bold_yellow": "\033[1;33m",
    "bold_blue": "\033[1;34m",
    "bold_purple": "\033[1;35m",
    "bold_cyan": "\033[1;36m",
    "bold_white": "\033[1;37m",
    "reset": "\033[0m",
}

class BaseFormatter(logging.Formatter):

    TAG_REGEX = re.compile(r"(?ix)<(([a-z](?:[^<>]*)) | /([a-z](?:[^<>]*))?)>")
    FORMATS = {
        logging.DEBUG: f"[{COLORS.get('green')}%(asctime)s{COLORS.get('reset')}] %(filename)-18s: %(message)s",
        logging.INFO: f"%(message)s",
        LOADING: f"[{COLORS.get('green')}%(asctime)s{COLORS.get('reset')}] Loading: %(message)s",
        SUCCESS: f"[{COLORS.get('green')}%(asctime)s{COLORS.get('reset')}] Success: %(message)s",
        logging.WARNING: f"%(message)s",
        logging.ERROR: f"[{COLORS.get('green')}%(asctime)s{COLORS.get('reset')}] {COLORS.get('red')}%(levelname)-8s{COLORS.get('reset')}: %(message)s ",
        logging.CRITICAL: f"[{COLORS.get('green')}%(asctime)s{COLORS.get('reset')}] {COLORS.get('red')}%(levelname)-8s{COLORS.get('reset')}: %(message)s ",
    }

    _inline_styles_cache: ClassVar[dict[str, Style]] = {}

    def setup(
        self, 
        decorated: bool = True,
        styles: dict[str, Style] | None = None
    ) -> None:
        self._decorated = decorated
        self._styles: dict[str, Style] = {}

        self.set_style("error", Style("red", options=["bold"]))
        self.set_style("info", Style("blue"))
        self.set_style("success", Style("green"))
        self.set_style("loading", Style("cyan"))
        self.set_style("warning", Style("yellow"))
        self.set_style("c1", Style("cyan"))
        self.set_style("c2", Style("default", options=["bold"]))
        self.set_style("b", Style("default", options=["bold"]))

        for name, style in (styles or {}).items():
            self.set_style(name, style)

        self._style_stack = StyleStack()

        return self

    @classmethod
    def escape(cls, text: str) -> str:
        """
        Escapes "<" special char in given text.
        """
        text = re.sub(r"([^\\]?)<", "\\1\\<", text)

        return cls.escape_trailing_backslash(text)

    @staticmethod
    def escape_trailing_backslash(text: str) -> str:
        """
        Escapes trailing "\\" in given text.
        """
        if text.endswith("\\"):
            length = len(text)
            text = text.rstrip("\\").replace("\0", "").ljust(length, "\0")

        return text

    def decorated(self, decorated: bool = True) -> None:
        self._decorated = decorated

    def is_decorated(self) -> bool:
        return self._decorated

    def set_style(self, name: str, style: Style) -> None:
        self._styles[name] = style

    def has_style(self, name: str) -> bool:
        return name in self._styles

    def style(self, name: str) -> Style:
        if not self.has_style(name):
            raise CleoValueError(f'Undefined style: "{name}"')

        return self._styles[name]

    def format(self, record: logging.LogRecord) -> str:
        _record = logging.LogRecord(
            record.name, record.levelno, record.pathname, record.lineno, self.format_and_wrap(record.getMessage(), 0), record.args, record.exc_info, record.funcName
        )

        log_fmt = self.FORMATS.get(record.levelno)
        # formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%dT%T%Z")
        return formatter.format(_record)

    def format_and_wrap(self, message: str, width: int) -> str:
        offset = 0
        output = ""
        current_line_length = 0
        for match in self.TAG_REGEX.finditer(message):
            pos = match.start()
            text = match.group(0)

            if pos != 0 and message[pos - 1] == "\\":
                continue

            # add the text up to the next tag
            formatted, current_line_length = self._apply_current_style(
                message[offset:pos], output, width, current_line_length
            )
            output += formatted
            offset = pos + len(text)

            # Opening tag
            seen_open = text[1] != "/"
            tag = match.group(1) if seen_open else match.group(2)

            style = None
            if tag:
                style = self._create_style_from_string(tag)

            if not (seen_open or tag):
                # </>
                self._style_stack.pop()
            elif style is None:
                formatted, current_line_length = self._apply_current_style(
                    text, output, width, current_line_length
                )
                output += formatted
            elif seen_open:
                self._style_stack.push(style)
            else:
                self._style_stack.pop(style)

        formatted, current_line_length = self._apply_current_style(
            message[offset:], output, width, current_line_length
        )
        output += formatted
        return output.replace("\0", "\\").replace("\\<", "<")

    def remove_format(self, text: str) -> str:
        decorated = self._decorated

        self._decorated = False
        text = re.sub(r"\033\[[^m]*m", "", self.format(text))

        self._decorated = decorated

        return text

    def _create_style_from_string(self, string: str) -> Style | None:
        if string in self._styles:
            return self._styles[string]

        if string in self._inline_styles_cache:
            return self._inline_styles_cache[string]

        matches = re.findall(r"([^=]+)=([^;]+)(;|$)", string.lower())
        if not matches:
            return None

        style = Style()

        for where, style_options, _ in matches:
            if where == "fg":
                style.foreground(style_options)
            elif where == "bg":
                style.background(style_options)
            else:
                try:
                    for option in map(str.strip, style_options.split(",")):
                        style.set_option(option)
                except ValueError:
                    return None

        self._inline_styles_cache[string] = style

        return style

    def _apply_current_style(
        self, text: str, current: str, width: int, current_line_length: int
    ) -> tuple[str, int]:
        if not text:
            return "", current_line_length

        if not width:
            if self.is_decorated():
                return self._style_stack.current.apply(text), current_line_length

            return text, current_line_length

        if not current_line_length and current:
            text = text.lstrip()

        if current_line_length:
            i = width - current_line_length
            prefix = text[:i] + "\n"
            text = text[i:]
        else:
            prefix = ""

        m = re.match(r"(\n)$", text)
        text = prefix + re.sub(rf"([^\n]{{{width}}})\ *", "\\1\n", text)
        text = text.rstrip("\n") + (m.group(1) if m else "")

        if not current_line_length and current and not current.endswith("\n"):
            text = "\n" + text

        lines = text.split("\n")
        for line in lines:
            current_line_length += len(line)
            if current_line_length >= width:
                current_line_length = 0

        if self.is_decorated():
            apply = self._style_stack.current.apply
            text = "\n".join(map(apply, lines))

        return text, current_line_length
