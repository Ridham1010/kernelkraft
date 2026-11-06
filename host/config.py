"""Load the host-side project configuration."""

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config(path=CONFIG_PATH):
    """Return the JSON configuration as a dictionary."""
    with Path(path).open(encoding="utf-8") as config_file:
        return json.load(config_file)


def deadline_for_alpha(alpha, w_ticks):
    """Return round(alpha * W) as an int, rounding halves up.

    Python's round() rounds halves to even, so 1.25 * 24.4 = 30.5 would give
    30. Decimal on the printed values avoids that and binary float error, so
    30.5 becomes 31 as in ordinary arithmetic.
    """
    product = Decimal(str(alpha)) * Decimal(str(w_ticks))
    return int(product.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def alpha_label(alpha):
    """Canonical text for an alpha value in CSV cells, log names and keys."""
    return str(float(alpha))


def require_w_ticks(config, who):
    """Return W_ticks as a float, or stop with a clear message if it is unset.

    W_ticks is null until the team recalibrates the PLAN workload; nothing
    that derives a deadline from it may run before then.
    """
    w_ticks = config.get("W_ticks")
    if w_ticks is None:
        raise SystemExit(
            "W_ticks is null in host/config.json; recalibrate (PLAN Stage 6) "
            "and set it before running {}.".format(who))
    return float(w_ticks)
