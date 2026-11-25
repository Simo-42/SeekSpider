"""Shared filters for job search results."""
import re


def is_senior(job):
    return bool(re.search(r"\b(?:senior|sr|snr)\b", job.get("job_title") or "", re.IGNORECASE))


def experience_evidence(text, min_years=0):
    """Return a literal excerpt only for a job-related experience duration."""
    numbers = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
               "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    number_pattern = r"\d{1,2}(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten"
    pattern = re.compile(r"(?<![\d.])\b(?P<min>" + number_pattern + r")\s*(?:(?:[-–—]|to)\s*(?P<max>" + number_pattern + r")\s*)?(?:\+\s*|or\s+more\s+)?(?:years?|yrs?)\b", re.I)
    for match in pattern.finditer(text or ""):
        minimum = match.group("min").lower()
        number = float(minimum) if minimum[0].isdigit() else numbers[minimum]
        if number < min_years or number > 20:
            continue
        left = max(0, match.start() - 80)
        right = min(len(text), match.end() + 100)
        before = text[left:match.start()]
        after = text[match.end():right]
        # Only use the same sentence or bullet as the duration.
        begin = max(text.rfind('. ', left, match.start()), text.rfind('\n', left, match.start()))
        if begin >= 0:
            before = text[begin + (2 if text[begin:begin + 2] == '. ' else 1):match.start()]
        end = text.find('. ', match.end(), right)
        line_end = text.find('\n', match.end(), right)
        boundaries = [position for position in (end, line_end) if position >= 0]
        if boundaries:
            right = min(boundaries) + (1 if text[min(boundaries)] == '.' else 0)
            after = text[match.end():right]
        if re.search(r"\b(?:we(?:'ve|\s+have)|our\s+(?:team|company|business)|the\s+company)\b.{0,50}(?:over|more\s+than|for|with)\s*$", before, re.I):
            continue
        if re.search(r"\b(?:company|business|consultancy|organisation|organization|firm|agency|provider)\b.{0,40}\b(?:with|has|over|for|more\s+than)\b[^.]*$", before, re.I):
            continue
        if min_years and re.search(r"(?:up\s+to|less\s+than|fewer\s+than|under|maximum\s+of|at\s+most)\s*$", before, re.I):
            continue
        before_clause = re.split(r"[;\n]", before)[-1]
        after_clause = re.split(r"[;\n]", after)[0]
        nearby = before_clause[-35:] + after_clause[:65]
        if min_years and re.search(r"\bnot\s+required\b", nearby, re.I):
            continue
        if (min_years and re.search(r"\b(?:preferred|desirable|nice\s+to\s+have)\b", nearby, re.I)
                and not re.search(r"\b(?:required|mandatory)\b", after_clause[:40], re.I)
                and not re.search(r"\b(?:minimum|at\s+least|must)\s*(?:of\s*)?$", before_clause, re.I)):
            continue
        # Do not treat company age, contracts, or support periods as job experience.
        experience_words = re.search(r"\b(?:experience|expérience|background|working\s+in|hands[- ]on)\b", before[-55:] + after[:65], re.I)
        activity = re.match(r"\s*(?:(?:of\s+)?(?:designing|developing|building|deploying|maintaining|administering|engineering|operating|implementing)\b|(?:in|as)\s+(?:a\s+)?(?:similar|related)\b)", after, re.I)
        if not experience_words and not activity:
            continue
        return (before + text[match.start():match.end()] + after).strip()
    return None


def experience_exclusion(text):
    """Return a literal excerpt only for a clear minimum of five years or more."""
    return experience_evidence(text, min_years=5)
