from __future__ import annotations

from streamseeker.console.logging.formatters.builder_formatter import BuilderLogFormatter


FORMATTERS = {
    "streamseeker.core.masonry.builders.builder": BuilderLogFormatter(),
    "streamseeker.core.masonry.builders.sdist": BuilderLogFormatter(),
    "streamseeker.core.masonry.builders.wheel": BuilderLogFormatter(),
}