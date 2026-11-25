"""Shared filters for job search results."""
import re


def is_senior(job):
    return bool(re.search(r"\b(?:senior|sr|snr)\b", job.get("job_title") or "", re.IGNORECASE))


def experience_exclusion(text):
    """Return a literal excerpt only for a clear minimum of five years or more."""
    numbers = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
               "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    number_pattern = r"\d{1,2}(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten"
    pattern = re.compile(r"(?<![\d.])\b(?P<min>" + number_pattern + r")\s*(?:(?:[-–—]|to)\s*(?P<max>" + number_pattern + r")\s*)?(?:\+\s*|or\s+more\s+)?(?:years?|yrs?)\b", re.I)
    for match in pattern.finditer(text or ""):
        minimum = match.group("min").lower()
        number = float(minimum) if minimum[0].isdigit() else numbers[minimum]
        if number < 5 or number > 20:
            continue
        left = max(0, match.start() - 80)
        right = min(len(text), match.end() + 100)
        before = text[left:match.start()]
        after = text[match.end():right]
        if re.search(r"\b(?:company|business|consultancy|organisation|organization|firm|agency|provider)\b.{0,40}\b(?:with|has|over|for|more\s+than)\b[^.]*$", before, re.I):
            continue
        if re.search(r"(?:up\s+to|less\s+than|fewer\s+than|under|maximum\s+of|at\s+most)\s*$", before, re.I):
            continue
        before_clause = re.split(r"[;\n]", before)[-1]
        after_clause = re.split(r"[;\n]", after)[0]
        nearby = before_clause[-35:] + after_clause[:65]
        if re.search(r"\bnot\s+required\b", nearby, re.I):
            continue
        if (re.search(r"\b(?:preferred|desirable|nice\s+to\s+have)\b", nearby, re.I)
                and not re.search(r"\b(?:required|mandatory)\b", after_clause[:40], re.I)
                and not re.search(r"\b(?:minimum|at\s+least|must)\s*(?:of\s*)?$", before_clause, re.I)):
            continue
        # Do not treat company age, contracts, or support periods as job experience.
        if not re.search(r"\b(?:experience|expérience|background|working\s+in|hands[- ]on)\b", before[-55:] + after[:65], re.I):
            continue
        begin = text.rfind(". ", left, match.start())
        end = text.find(". ", match.end(), right)
        return text[(begin + 2 if begin >= 0 else left):(end + 1 if end >= 0 else right)].strip()
    return None
