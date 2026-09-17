"""JSON event logs without source, model output, or credentials."""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("testgen.events")


def event(name: str, **fields):
    logger.info(
        json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "event": name, **fields})
    )
