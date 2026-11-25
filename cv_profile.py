"""Extract a CV summary and calculate job fit from the text available locally."""
import hashlib
import re

from job_filters import SCORE_VERSION, experience_mentions, role_category, role_tier


SKILL_PATTERNS = {
    "AWS": r"\baws\b|amazon web services",
    "Terraform": r"\bterraform\b",
    "Kubernetes": r"\bkubernetes\b|\bk8s\b|\bk3s\b|\bk3d\b",
    "Docker": r"\bdocker\b",
    "Linux": r"\blinux\b",
    "Ansible": r"\bansible\b",
    "Python": r"\bpython\b",
    "Bash": r"\bbash\b",
    "GitLab CI/CD": r"\bgitlab\s+ci/?cd\b",
    "GitHub Actions": r"\bgithub\s+actions\b",
    "Argo CD": r"\bargo\s*cd\b|\bargocd\b",
    "Helm": r"\bhelm\b",
    "Grafana": r"\bgrafana\b",
    "Observability": r"\bobservability\b|\bobservabilit[ée]\b",
    "SRE": r"\bsre\b|site reliability engineering",
    "Incident management": r"incident management|incident response|incident workflow",
    "SLI/SLO": r"\bsli(?:s)?\b|\bslo(?:s)?\b",
    "CloudWatch": r"\bcloudwatch\b",
    "AWS Lambda": r"\b(?:aws\s+)?lambda\b",
    "API Gateway": r"\bapi gateway\b",
    "CI/CD": r"\bci\s*/?\s*cd\b|continuous integration|continuous delivery",
    "FastAPI": r"\bfastapi\b",
    "MCP": r"\bmcp servers?\b|model context protocol",
    "IA générative / agentique": r"\bagentic ai\b|\bgenai\b|generative ai|\bllm(?:ops|s?)\b",
    "Azure": r"\bazure\b|\baz-104\b",
    "Google Cloud": r"\bgcp\b|\bgoogle cloud\b",
    "Jenkins": r"\bjenkins\b",
    "Prometheus": r"\bprometheus\b",
    "Datadog": r"\bdatadog\b",
    "OpenTelemetry": r"\bopentelemetry\b|\botel\b",
    "PowerShell": r"\bpowershell\b",
    "Windows Server": r"\bwindows server\b",
    "Microsoft 365": r"\bmicrosoft 365\b|\boffice 365\b|\bm365\b|\bo365\b",
    "Intune": r"\bintune\b",
    "Active Directory": r"\bactive directory\b|\bentra id\b",
    "ServiceNow": r"\bservicenow\b",
    "Jira": r"\bjira\b",
    "Networking": r"\bnetwork(?:ing| protocols?)\b|\btcp/ip\b",
    "PostgreSQL": r"\bpostgres(?:ql)?\b",
    "TypeScript": r"\btypescript\b",
    "Node.js": r"\bnode\.?js\b",
    "Vue.js": r"\bvue\.?js\b",
    "NGINX": r"\bnginx\b",
    "C++": r"(?<![\w+])c\+\+(?![\w+])",
    "Git": r"\bgit\b",
}


def profile_fingerprint(profile):
    return hashlib.sha256(profile.encode("utf-8")).hexdigest()


def profile_summary(profile):
    """Expose selected professional fields without serving the CV or contact details."""
    if not profile.strip():
        return None
    sections = {}
    heading = ""
    for line in profile.splitlines():
        line = line.strip()
        if re.fullmatch(r"[A-Z][A-Z &/]{2,}", line):
            heading = line
        elif line and not re.search(r"@|https?://|(?:\+?\d[ .()-]*){8,}", line, re.I):
            sections.setdefault(heading, []).append(line)
    return {
        "education": [line for line in sections.get("EDUCATION", [])
                      if re.search(r"\bbac\s*\+|\bbachelor\b|\bmaster\b|\bdegree\b|\bdiploma\b", line, re.I)],
        "certifications": [line for line in sections.get("CERTIFICATIONS", [])
                           if re.match(r"^(?:AWS|HashiCorp|Microsoft|Google|Cisco|CompTIA|CNCF)\b", line, re.I)],
        "experience": list(dict.fromkeys(
            line.split(" | ", 1)[0] for line in sections.get("EXPERIENCE", []) if " | " in line
        )),
        "skills": skill_mentions(profile),
        "languages": [item.strip() for line in sections.get("SKILLS", []) if line.startswith("Languages:")
                      for item in line.split(":", 1)[1].split(",") if item.strip()],
    }


def skill_mentions(text):
    present = []
    for skill, pattern in SKILL_PATTERNS.items():
        for match in re.finditer(pattern, text, re.I):
            left = re.split(r"[.;:\n!?]", text[max(0, match.start() - 70):match.start()])[-1]
            right = re.split(r"[.;:\n!?]", text[match.end():match.end() + 70])[0]
            if re.search(r"\b(?:no|without)\s+(?:(?:prior|previous)\s+)?(?:experience\s+(?:with|of|in)\s+)?$", left, re.I):
                continue
            if re.match(r"\s+(?:experience\s+|knowledge\s+)?(?:is\s+)?(?:not\s+(?:required|needed)|isn't\s+required)", right, re.I):
                continue
            # A vendor-specific CI/CD entry should not also earn generic CI/CD points.
            if skill == "CI/CD" and re.search(r"\bgitlab\s+$", left, re.I):
                continue
            present.append(skill)
            break
    return present


def calculate_fit_score(job, description, profile):
    """Use the technologies mentioned by the job as the comparison set."""
    category = role_category(job)
    tier = role_tier(job)
    role_points = 20 if tier == 0 and category != "IA complémentaire" else {
        "Cloud & DevOps": 18, "Infrastructure": 15, "Support IT": 13,
        "IA complémentaire": 9,
    }.get(category, 0)
    requested = skill_mentions(description)
    skills = set(skill_mentions(profile))
    matched = [skill for skill in requested if skill in skills]
    missing = [skill for skill in requested if skill not in skills]
    # Score both coverage and depth so one shared keyword cannot max out the score.
    skill_points = round(65 * (0.6 * len(matched) / len(requested) + 0.4 * min(len(matched) / 5, 1))) if requested else 0
    years = max((years for years, _ in experience_mentions(description, required_only=True)), default=None)
    if years is None:
        experience_points, experience_reason = 4, "Minimum d’expérience non précisé clairement"
    elif years <= 3:
        experience_points, experience_reason = 10, f"Minimum repéré : {years:g} an(s), dans la cible de 0 à 3 ans"
    else:
        experience_points, experience_reason = 3, f"Minimum repéré : {years:g} ans, au-dessus de la cible"
    area = (job.get("area") or "").lower()
    region = (job.get("region") or "").lower()
    location_points = 5 if "sydney" in area or "melbourne" in area else (3 if "australia" in region else 0)
    if matched:
        summary = f"L’annonce mentionne {len(matched)} compétence(s) présente(s) dans le CV."
    elif requested:
        summary = "Aucun recoupement entre les compétences reconnues dans l’annonce et celles du CV."
    else:
        summary = "Aucune compétence reconnue par le barème dans le texte de l’annonce."
    return {
        "resume": summary,
        "score": role_points + skill_points + experience_points + location_points,
        "score_method": SCORE_VERSION,
        "profile_fingerprint": profile_fingerprint(profile),
        "role_category": category,
        "score_role": role_points,
        "score_skills": skill_points,
        "score_experience": experience_points,
        "experience_score_reason": experience_reason,
        "score_location": location_points,
        "competences_reperees": matched,
        "competences_manquantes": missing,
        "competences_comparees": len(requested),
    }
