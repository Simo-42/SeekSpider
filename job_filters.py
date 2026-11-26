"""Shared filters for job search results."""
import re

SCORE_VERSION = "cv-rules-v5"
DEFAULT_MODEL = "qwen3:14b"

ROLE_PATTERNS = {
    "IA complémentaire": re.compile(
        r"\b(?:junior\s+)?ai\s+(?:&\s+)?(?:automation|azure|engineer|infrastructure|platform|associate)\b|"
        r"\b(?:ml(?:\s*/\s*llm)?|machine\s+learning)\s+engineer\b|"
        r"\b(?:mlops|llmops|genai|generative\s+ai|machine\s+learning\s+ops)\b",
        re.I,
    ),
    "Cloud & DevOps": re.compile(
        r"\b(?:aws\s+)?cloud\b|\bdevops\b|\bsite\s+reliability\b|\bsre\b|"
        r"\b(?:cloud|devops|ai|engineering|tech(?:nology)?)\s+platforms?\b|\bplatforms?\s+engineer\b|"
        r"\bopenshift\b|\bci\s*/?\s*cd\b|\bobservability\b|\brelease\s+engineer\b",
        re.I,
    ),
    "Infrastructure": re.compile(
        r"\binfrastructure\b|\bsystems?\s+(?:engineer|administrator)\b|"
        r"\blinux\s+(?:systems?\s+)?(?:engineer|administrator)\b|"
        r"\bict\s+systems?\s+administrator\b|"
        r"\bit\s+systems?\s+(?:and\s+applications?\s+)?(?:administrator|support\s+engineer)\b|"
        r"\bit\s+operations\b|\b(?:(?:technical|identity)\s+)?operations\s+engineer\b|"
        r"\bproduction\s+support\b|\bapplication\s+support\b",
        re.I,
    ),
    "Support IT": re.compile(
        r"\b(?:technical|it|ict|noc|desktop|help\s*desk|service\s+desk|data\s+cent(?:er|re)|field\s+services?)"
        r"\s+(?:support|engineers?|analysts?|officers?|technicians?|engineering\s+operations)\b|"
        r"\b(?:field|enterprise)\s+support\s+engineers?\b|"
        r"\b(?:service\s+desk|help\s*desk|technical\s+support)\b|"
        r"\b(?:noc|msp)\s+(?:support|engineers?|analysts?|officers?|technicians?|systems?\s+engineers?)\b|"
        r"\blevel\s*[23](?:\s*(?:&|/|and)\s*[23])?(?:\s+(?:it|ict|technical|systems?|desktop|service\s+desk|help\s*desk))?"
        r"(?:\s*[-–—]\s*|\s+)(?:support|engineers?|analysts?|officers?|technicians?|team)\b|"
        r"\b(?:support|engineers?|analysts?|officers?|technicians?|team)(?:\s+(?:engineers?|analysts?|officers?|technicians?))?"
        r"(?:\s*[-–—(/]\s*|\s+)level\s*[23](?:\s*(?:&|/|and)\s*[23])?\b",
        re.I,
    ),
}
PRIORITY_ROLE = re.compile(
    r"\b(?:(?:aws\s+)?cloud\s+engineer|junior\s+devops\s+engineer|site\s+reliability\s+engineer|sre|cloud\s+support\s+(?:engineer|associate)|cloud\s+operations\s+engineer)\b",
    re.I,
)
OFF_TARGET_DOMAIN = re.compile(
    r"\b(?:electrical|instrumentation|control\s+systems?|cctv|mainframe|z/os|cics/mq|"
    r"mechatronic|mechanical|civil|mining|building\s+services|"
    r"adobe\s+experience|salesforce|power\s+platform|uav|avionics|naval\s+combat|"
    r"ev\s+charging|digital\s+signage|crm\s+systems?|graduate\b.*\b2027|2027\s+start|autodesk)\b",
    re.I,
)
PUBLIC_SECTOR_EMPLOYER = re.compile(
    r"\b(?:department\s+of|bureau\s+of\s+meteorology|government|council|defence|defense|"
    r"services\s+australia|csiro|australian\s+nuclear|police|ato|"
    r"australian\s+secret\s+intelligence|asis|ahpra|health\s+practitioner\s+regulation|"
    r"environment\s+protection\s+authority|bayside\s+health|icare|satac|saab|"
    r"bae\s+systems|boeing|raytheon)\b",
    re.I,
)
IT_AGENCY_EMPLOYER = re.compile(
    r"\b(?:talenza|talentweb|green\s+light|paxus|finite|hays|launch\s+recruitment|"
    r"davidson|robert\s+half|talent\s+international|finxl|pm-partners|thedrivegroup|"
    r"randstad|michael\s+page|hudson|peoplebank|click\s+recruiting|pra|opus\s+recruitment|"
    r"greythorn|modis|akkodis|tek\s*systems|"
    r"talent|clicks\s+it|recruitment\s+hive|emanate|genesis\s+it|face2face|robert\s+walters|"
    r"the\s+recruitment\s+company|fourquarters|oui\s+recruitment|jpex|cleared\s+recruitment|lumiq\s+talent)\b",
    re.I,
)
AWS_MSP_EMPLOYER = re.compile(
    r"\b(?:versent|mantel|cevo|ac3|datacom|brennan|interactive|dius|cmd\s+solutions|"
    r"kinetic\s+it|data#3|macquarie\s+cloud|rackspace|nec|insight|slalom|kasna|"
    r"innablr|servian|deloitte|accenture|capgemini|infosys|wipro|cognizant|"
    r"amazon\s+web\s+services|dws\s+limited|atturra|ever\s+nimble|compnow|leidos)\b",
    re.I,
)
WHV_RESTRICTIVE_VISA = re.compile(
    r"\b(?:(?:australian|us|u\.s\.)\s+)?citizen(?:s|ship)?\b|"
    r"\bpermanent\s+residen(?:ts?|cy)\b|"
    r"\bpr\s+only\b|"
    r"\bfull(?:,\s*permanent|\s+valid)?\s+(?:australian\s+)?work(?:ing)?\s+rights?\b|"
    r"\b(?:unrestricted|unlimited)\s+(?:right\s+to\s+work|(?:australian\s+)?work(?:ing)?\s+rights?)\b|"
    r"\bno\s+(?:whv|working\s+holiday)\b",
    re.I,
)
WHV_NO_SPONSORSHIP = re.compile(
    r"\b(?:no\s+(?:visa\s+)?sponsor(?:ship|ing)?|"
    r"sponsorship\s+is\s+(?:not\s+|un)available|"
    r"unable\s+to\s+(?:provide\s+|offer\s+)?(?:visa\s+)?sponsor(?:ship)?|"
    r"not\s+(?:able|eligible)\s+to\s+sponsor|"
    r"cannot\s+(?:provide\s+|offer\s+)?(?:visa\s+)?sponsor(?:ship)?|"
    r"do(?:es)?\s+not\s+(?:provide\s+|offer\s+)?(?:visa\s+)?sponsor(?:ship)?|"
    r"don['’]t\s+sponsor)\b",
    re.I,
)
WHV_EXEMPT_CONTEXT = re.compile(
    r"\bor\s+(?:hold\s+)?(?:a\s+)?valid\s+work\s+(?:permit|visa)\b|"
    r"\bvalid\s+working\s+visa\b|"
    r"\b(?:never\s+based\s+on|regardless\s+of|without\s+regard\s+to)\b|"
    r"\bmay\s+obtain\s+nationality\s+or\s+citizenship\s+information\b",
    re.I,
)


def role_category(job):
    title = job if isinstance(job, str) else (job.get("job_title") or "")
    if OFF_TARGET_DOMAIN.search(title):
        return "Hors cible"
    for category, pattern in ROLE_PATTERNS.items():
        if pattern.search(title):
            return category
    return "Hors cible"


def employer_tag(job):
    """Classify employer into public_sector, agency, aws_msp, or empty string."""
    name = job if isinstance(job, str) else (job.get("business_name") or "")
    if not name.strip():
        return ""
    if PUBLIC_SECTOR_EMPLOYER.search(name):
        return "public_sector"
    if IT_AGENCY_EMPLOYER.search(name):
        return "agency"
    if AWS_MSP_EMPLOYER.search(name):
        return "aws_msp"
    return ""


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
    if re.search(
        r"\b(?:senior|sr|snr|principal|staff|director|managers?|mgr|leads?|el[12])\b|"
        r"\b(?:head\s+of|executive\s+level\s+[12])\b",
        title, re.IGNORECASE,
    ):
        return True
    return bool(
        re.search(r"\barchitects?\b", title, re.IGNORECASE)
        and not re.search(r"\bjunior\b.{0,25}\barchitects?\b", title, re.IGNORECASE)
    )


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
        if re.search(r"^\s*(?:with\s+)?over\s+$", before, re.I) and re.search(r"^[^,\n]{0,40},\s*[A-Z]", after):
            continue
        if required_only and re.search(r"(?:up\s+to|less\s+than|fewer\s+than|under|maximum\s+of|at\s+most)\s*$", before, re.I):
            continue
        before_clause = re.split(r"[;,\n]", before)[-1]
        after_clause = re.split(r"[;,\n]", after)[0]
        clause = before_clause + after_clause
        nearby = before_clause[-35:] + after_clause[:65]
        if required_only and re.search(r"\bnot\s+(?:required|mandatory|essential|necessary)\b", nearby, re.I):
            continue
        optional_cue = r"\b(?:optional|preferred|desirable|nice\s+to\s+have|bonus|advantage(?:ous)?|ideal(?:ly)?|beneficial|plus|highly\s+regarded)\b"
        line_start = text.rfind("\n", 0, match.start()) + 1
        previous_line_end = max(0, line_start - 1)
        previous_line_start = text.rfind("\n", 0, previous_line_end) + 1
        previous_line = text[previous_line_start:previous_line_end].strip()
        optional_heading = bool(re.fullmatch(r"(?:preferred|desirable|optional|bonus|nice\s+to\s+have)\s*:?", previous_line, re.I))
        optional_context = before[-100:] + after[:100]
        explicit_required = bool(
            re.search(r"\b(?:required|mandatory|must)\b", nearby, re.I)
            or (
                not optional_heading
                and re.search(r"\b(?:minimum|at\s+least)\b", clause, re.I)
                and not re.search(
                    r"\b(?:would\s+be|is)\s+(?:a\s+|an\s+)?(?:bonus|beneficial|advantage(?:ous)?|optional|preferred|desirable|nice\s+to\s+have|ideal)\b",
                    clause, re.I,
                )
            )
        )
        if required_only and (re.search(optional_cue, optional_context, re.I) or optional_heading) and not explicit_required:
            continue
        # Do not treat company age, contracts, or support periods as job experience.
        experience_words = re.search(r"\b(?:experience|expérience|background|working\s+in|hands[- ]on)\b", before[-55:] + after[:65], re.I)
        activity = re.match(r"\s*(?:(?:of\s+)?(?:designing|developing|building|deploying|maintaining|administering|engineering|operating|implementing)\b|(?:in|as)\s+(?:a\s+)?(?:similar|related|cloud|devops|platform|infrastructure|systems?|sre|site\s+reliability|it|technology|technical|software|network|data\s+science|cyber\s*security)\b)", after, re.I)
        if not experience_words and not activity:
            continue
        yield number, (before + text[match.start():match.end()] + after).strip()


def experience_evidence(text):
    return next((quote for _, quote in experience_mentions(text)), None)


def experience_exclusion(text):
    """Return a literal excerpt only for a clear minimum of five years or more."""
    return next((quote for _, quote in experience_mentions(text, min_years=5, required_only=True)), None)


def _has_excerpt(value):
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    lowered = text.lower()
    return lowered != "non précisé" and not lowered.startswith("aucun extrait")


def whv_flags(analysis):
    """Return deterministic WHV and clearance risk flags from extracted excerpts."""
    analysis = analysis or {}
    visa = analysis.get("preuve_visa")
    clearance = analysis.get("preuve_habilitation")
    has_visa = _has_excerpt(visa)
    return {
        "clearance": _has_excerpt(clearance),
        "citizen_pr_risk": bool(
            has_visa and WHV_RESTRICTIVE_VISA.search(visa) and not WHV_EXEMPT_CONTEXT.search(visa)
        ),
        "no_sponsorship": bool(has_visa and WHV_NO_SPONSORSHIP.search(visa)),
        "visa_mention": has_visa,
    }


_COMPANY_SUFFIX = re.compile(
    r"(?:[,\s\-–—]+(?:\((?:australia|anz|nsw|vic|qld|wa|sa|act)\)|"
    r"pty\.?\s+limited|pty\.?\s+ltd\.?|defence\s+australia|"
    r"limited|ltd\.?|inc\.?|australia|group|pty\.?|services|solutions))+$",
    re.I,
)
_TITLE_QUALIFIER = (
    r"(?:hybrid|remote|on-?site|wfh|"
    r"sydney(?:\s+cbd)?|melbourne(?:\s+cbd)?|brisbane(?:\s+cbd)?|perth|adelaide|canberra|australia|"
    r"nsw|vic|qld|wa|sa|act|"
    r"contract(?:/temp)?|permanent|full[- ]?time|part[- ]?time|fixed[- ]?term|"
    r"(?:initial\s+)?\d+\s+months?(?:\s+contract)?)"
)
_TITLE_PAREN_SUFFIX = re.compile(
    r"(?:\s*[\(\[]\s*" + _TITLE_QUALIFIER + r"(?:\s*[/,&|]\s*" + _TITLE_QUALIFIER + r")*\s*[\)\]])+$",
    re.I,
)
_TITLE_DASH_SUFFIX = re.compile(
    r"(?:\s*[-–—|/]\s*" + _TITLE_QUALIFIER + r"(?:\s*[/,&|]\s*" + _TITLE_QUALIFIER + r")*)+$",
    re.I,
)


def normalized_dedup_key(title, company):
    """Normalize (title, company) for cross-source deduplication."""
    norm_title = re.sub(r"\s+", " ", (title or "").strip().lower()).strip(" -–—|/,")
    norm_company = re.sub(r"\s+", " ", (company or "").strip().lower()).strip(" .,-")
    if not norm_title or not norm_company:
        return None
    while True:
        stripped = _COMPANY_SUFFIX.sub("", norm_company).strip(" .,-")
        if not stripped or stripped == norm_company:
            break
        norm_company = stripped
    while True:
        stripped = _TITLE_DASH_SUFFIX.sub("", _TITLE_PAREN_SUFFIX.sub("", norm_title)).strip(" -–—|/,")
        if not stripped or stripped == norm_title:
            break
        norm_title = stripped
    return (norm_title, norm_company)


_CONTRACT_DURATION = re.compile(
    r"(?<![\d.])(?P<min>\d{1,2})\s*(?:(?:[-–—]|to)\s*(?P<max>\d{1,2})\s*)?[- ]?(?P<unit>months?|mths?|weeks?|wks?|years?|yrs?)\b",
    re.I,
)
_CONTRACT_CONTEXT = re.compile(
    r"\b(?:contract(?:or)?|fixed[- ]?term|max(?:imum)?[- ]?term|initial|engagement|"
    r"assignment|temp(?:orary)?|secondment|day\s+rate|daily\s+rate|exten(?:sion|d))\b",
    re.I,
)
_NON_CONTRACT_DURATION = re.compile(
    r"\b(?:parental|maternity|paternity|annual|sick|paid|unpaid|long\s+service)?\s*leave\b|"
    r"\b(?:parental|maternity|paternity|paid)\b|"
    r"\b(?:experience|expérience|warranty|probation(?:ary)?|notice|prior|last|past|every|history)\b",
    re.I,
)


def contract_duration(text):
    """Extract explicit contract length and WHV 6-month employer-limit fit."""
    body = text or ""
    for match in _CONTRACT_DURATION.finditer(body):
        start, end = match.start(), match.end()
        left_bound = max(body.rfind(". ", max(0, start - 90), start), body.rfind("\n", max(0, start - 90), start))
        before = body[left_bound + 1 if left_bound >= 0 else max(0, start - 90):start]
        right_end = min(len(body), end + 90)
        stops = [pos for pos in (body.find(". ", end, right_end), body.find("\n", end, right_end)) if pos >= 0]
        after = body[end:min(stops) if stops else right_end]
        immediate = before[-30:] + " " + after[:45]
        if _NON_CONTRACT_DURATION.search(immediate):
            continue
        if not _CONTRACT_CONTEXT.search(before + " " + after):
            continue
        unit = match.group("unit").lower()
        lo = int(match.group("min"))
        hi = int(match.group("max")) if match.group("max") else lo
        if hi < lo:
            lo, hi = hi, lo
        if unit.startswith(("w",)):
            if not (1 <= lo <= 104 and hi <= 104):
                continue
            m_min, m_max = max(1, round(lo / 4)), max(1, round(hi / 4))
        elif unit.startswith("y"):
            if not (1 <= lo <= 5 and hi <= 5):
                continue
            m_min, m_max = lo * 12, hi * 12
        else:
            if not (1 <= lo <= 60 and hi <= 60):
                continue
            m_min, m_max = lo, hi
        label = f"{m_min} mois" if m_min == m_max else f"{m_min}-{m_max} mois"
        whv_fit = "ideal" if m_max <= 6 else ("long" if m_min >= 10 else "unknown")
        return {"months_min": m_min, "months_max": m_max, "label": label, "whv_fit": whv_fit}
    if re.search(r"\bfixed[- ]?term\b", body, re.I):
        return {"months_min": None, "months_max": None, "label": "Durée déterminée", "whv_fit": "unknown"}
    return {"months_min": None, "months_max": None, "label": "", "whv_fit": "unknown"}


_STRICT_REMOTE = re.compile(
    r"\b(?:100%\s+remote|fully\s+remote|remote[- ]only|work\s+from\s+anywhere)\b",
    re.I,
)
_HYBRID_MODE = re.compile(
    r"\b(?:[1-4]\s*(?:[-–—]|to)\s*[2-4]|[1-4])\s*days?\s+(?:(?:a|per)\s+week\s+)?(?:in\s+(?:the\s+)?office|on[- ]?site|wfh|from\s+home)\b|"
    r"\bwork\s+from\s+home\b.{0,35}\b(?:office|on[- ]?site)\b|"
    r"\b(?:office|on[- ]?site)\b.{0,35}\bwork\s+from\s+home\b|"
    r"(?<!cloud\s)(?<!azure\s)(?<!aws\s)\bhybrid\b(?!\s+(?:cloud|infrastructure|architecture|identity|azure|aws|active\s+directory|ad\b|it\b|network|storage|platform|deployment|exchange|microsoft|m365|o365|data\s+cent(?:er|re)|compute))",
    re.I,
)
_REMOTE_MODE = re.compile(
    r"\b(?:remote\s+(?:work(?:ing)?|role|position|opportunity|friendly|first|within\s+australia|across\s+australia)|"
    r"work(?:ing)?\s+remotely|remote[- ]first|"
    r"(?:work(?:ing)?\s+)?(?:100%\s+|fully\s+)?from\s+home|"
    r"(?:location|work\s+mode|arrangement)\s*:\s*remote)\b",
    re.I,
)
_ONSITE_MODE = re.compile(
    r"\b(?:(?:100%\s+|fully\s+|full[- ]?time\s+|strictly\s+|mandatory\s+)?on[- ]?site\s+(?:role|position|only|work(?:ing)?|5\s+days|in\s+(?:our\s+)?(?:sydney|melbourne|brisbane|perth|adelaide|canberra|office))|"
    r"5\s+days\s+(?:(?:a|per)\s+week\s+)?(?:in\s+(?:the\s+)?office|on[- ]?site)|"
    r"in[- ]office\s+(?:role|position|only|5\s+days)|"
    r"(?:based|required|must\s+(?:work|be))\s+on[- ]?site|"
    r"(?:location|work\s+mode|arrangement)\s*:\s*on[- ]?site)\b",
    re.I,
)


def work_mode(text):
    """Detect work mode ('remote', 'hybrid', 'onsite', or '') from description text."""
    body = text or ""
    if not body.strip():
        return ""
    if _STRICT_REMOTE.search(body):
        return "remote"
    if _HYBRID_MODE.search(body):
        return "hybrid"
    if _REMOTE_MODE.search(body):
        return "remote"
    if _ONSITE_MODE.search(body):
        return "onsite"
    return ""


_EMAIL_PATTERN = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
_IGNORED_EMAIL = re.compile(
    r"^(?:no[-_.]?reply|do[-_.]?not[-_.]?reply|privacy|abuse)@|"
    r"^(?:careers|support)@seek\b|"
    r"@example\.(?:com|org|net)$",
    re.I,
)
_AU_PHONE = re.compile(
    r"(?<!\d)(?:"
    r"\+61[\s.-]*(?:\(0\)\s*)?(?:4\d{2}[\s.-]*\d{3}[\s.-]*\d{3}|[2378][\s.-]*\d{4}[\s.-]*\d{4})|"
    r"04\d{2}[\s.-]*\d{3}[\s.-]*\d{3}|"
    r"\(0[2378]\)[\s.-]*\d{4}[\s.-]*\d{4}|"
    r"0[2378][\s.-]+\d{4}[\s.-]+\d{4}"
    r")(?!\d)"
)


def recruiter_contacts(text):
    """Extract up to 2 unique recruiter emails and Australian phone numbers."""
    body = text or ""
    emails = []
    seen_emails = set()
    for match in _EMAIL_PATTERN.finditer(body):
        addr = match.group(0).lower()
        if addr in seen_emails or _IGNORED_EMAIL.search(addr):
            continue
        seen_emails.add(addr)
        emails.append(addr)
        if len(emails) == 2:
            break
    phones = []
    seen_phones = set()
    for match in _AU_PHONE.finditer(body):
        raw = re.sub(r"\s+", " ", match.group(0).strip())
        digits = re.sub(r"\D", "", raw)
        if digits.startswith("610"):
            digits = "0" + digits[3:]
        elif digits.startswith("61"):
            digits = "0" + digits[2:]
        if digits in seen_phones:
            continue
        seen_phones.add(digits)
        phones.append(raw)
        if len(phones) == 2:
            break
    return {"emails": emails, "phones": phones}
