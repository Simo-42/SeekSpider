"""Shared filters for job search results."""
import re


def is_senior(job):
    return bool(re.search(r"\b(?:senior|sr|snr)\b", job.get("job_title") or "", re.IGNORECASE))
