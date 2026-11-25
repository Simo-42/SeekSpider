"""Shared filters for job search results."""
import re

SCORE_VERSION = "cv-rules-v2"

ROLE_PATTERNS = {
    "IA complémentaire": re.compile(r"\b(?:junior\s+)?ai\s+(?:engineer|infrastructure|platform)\b|\b(?:mlops|llmops|genai|generative\s+ai|machine\s+learning\s+ops)\b", re.I),
    "Cloud & DevOps": re.compile(r"\b(?:aws\s+)?cloud\b|\bdevops\b|\bsite\s+reliability\b|\bsre\b|\bplatform\b|\bci\s*/?\s*cd\b|\bobservability\b|\brelease\s+engineer\b", re.I),
    "Infrastructure": re.compile(r"\binfrastructure\b|\bsystems?\s+(?:engineer|administrator)\b|\blinux\s+system\s+administrator\b|\bict\s+systems?\s+administrator\b|\bit\s+operations\b|\bproduction\s+support\b|\bapplication\s+support\b", re.I),
    "Support IT": re.compile(r"\b(?:technical|it|level\s*[23]|ict|noc|desktop|service\s+desk|data\s+center|field\s+services?)\s+(?:support|engineer|analyst|officer|technician)\b|\b(?:noc|msp)\s+(?:engineer|analyst|systems?\s+engineer)\b", re.I),
}
PRIORITY_ROLE = re.compile(r"\b(?:cloud\s+support\s+engineer|cloud\s+operations\s+engineer|junior\s+devops\s+engineer|infrastructure\s+engineer)\b", re.I)


def role_category(job):
    title = job if isinstance(job, str) else (job.get("job_title") or "")
    for category, pattern in ROLE_PATTERNS.items():
        if pattern.search(title):
            return category
    return "Hors cible"


def role_tier(job):
    title = job if isinstance(job, str) else (job.get("job_title") or "")
    if PRIORITY_ROLE.search(title):
        return 0
    return {"Cloud & DevOps": 1, "Infrastructure": 2, "Support IT": 3,
            "IA complémentaire": 4}.get(role_category(job), 5)


def is_target_role(job):
    return role_category(job) != "Hors cible"


def is_senior(job):
    title = job.get("job_title") or ""
    return bool(re.search(
        r"\b(?:senior|sr|snr|principal|staff|director|managers?|mgr|leads?)\b|"
        r"\bhead\s+of\b",
        title, re.IGNORECASE))


def experience_mentions(text, min_years=0, required_only=False):
    """Yield experience minimums with their literal excerpts."""
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
        if required_only and re.search(r"(?:up\s+to|less\s+than|fewer\s+than|under|maximum\s+of|at\s+most)\s*$", before, re.I):
            continue
        before_clause = re.split(r"[;,\n]", before)[-1]
        after_clause = re.split(r"[;,\n]", after)[0]
        nearby = before_clause[-35:] + after_clause[:65]
        if required_only and re.search(r"\bnot\s+(?:required|mandatory|essential|necessary)\b", nearby, re.I):
            continue
        optional_cue = r"\b(?:optional|preferred|desirable|nice\s+to\s+have|bonus|advantage(?:ous)?|ideal(?:ly)?|beneficial|plus|highly\s+regarded|or\s+equivalent)\b"
        line_start = text.rfind("\n", 0, match.start()) + 1
        previous_line_end = max(0, line_start - 1)
        previous_line_start = text.rfind("\n", 0, previous_line_end) + 1
        previous_line = text[previous_line_start:previous_line_end].strip()
        optional_heading = bool(re.fullmatch(r"(?:preferred|desirable|optional|bonus|nice\s+to\s+have)\s*:?", previous_line, re.I))
        optional_context = before[-100:] + after[:100]
        if (required_only and (re.search(optional_cue, optional_context, re.I) or optional_heading)
                and not re.search(r"\b(?:required|mandatory|must)\b", nearby, re.I)):
            continue
        # Do not treat company age, contracts, or support periods as job experience.
        experience_words = re.search(r"\b(?:experience|expérience|background|working\s+in|hands[- ]on)\b", before[-55:] + after[:65], re.I)
        activity = re.match(r"\s*(?:(?:of\s+)?(?:designing|developing|building|deploying|maintaining|administering|engineering|operating|implementing)\b|(?:in|as)\s+(?:a\s+)?(?:similar|related|cloud|devops|platform|infrastructure|systems?|sre|site\s+reliability|it|technology|software|network)\b)", after, re.I)
        if not experience_words and not activity:
            continue
        yield number, (before + text[match.start():match.end()] + after).strip()


def experience_evidence(text):
    return next((quote for _, quote in experience_mentions(text)), None)


def experience_exclusion(text):
    """Return a literal excerpt only for a clear minimum of five years or more."""
    return next((quote for _, quote in experience_mentions(text, min_years=5, required_only=True)), None)
