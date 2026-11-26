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
    "EC2": r"\bec2\b",
    "S3": r"\b(?:aws\s+)?s3\b",
    "IAM": r"\biam\b",
    "RDS": r"\brds\b",
    "SSM": r"\b(?:aws\s+)?ssm\b|systems manager",
    "CloudFormation": r"\bcloudformation\b",
    "EKS / ECS": r"\beks\b|\becs\b",
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
    "ITIL": r"\bitil\b",
    "VMware": r"\bvmware\b|\bvsphere\b",
    "Networking": r"\bnetwork(?:ing| protocols?)\b|\btcp/ip\b|\bvpc\b|\bdns\b|\bsubnets?\b|\bfirewalls?\b|\bload balanc(?:er|ing)\b",
    "TLS / SSL": r"\btls\b|\bssl\b",
    "OAuth2": r"\boauth\s*2?(?:\.0)?\b|\boidc\b",
    "Docker Compose": r"\bdocker[- ]compose\b",
    "PostgreSQL": r"\bpostgres(?:ql)?\b",
    "MySQL / MariaDB": r"\bmariadb\b|\bmysql\b",
    "TypeScript": r"\btypescript\b",
    "Node.js": r"\bnode\.?js\b",
    "Vue.js": r"\bvue\.?js\b",
    "NGINX": r"\bnginx\b",
    "Agile / Scrum": r"\bagile\b|\bscrum\b",
    "C++": r"(?<![\w+])c\+\+(?![\w+])",
    "Git": r"\bgit\b",
    "Azure DevOps": r"\bazure\s+devops\b",
    "SQL / MSSQL": r"(?<!postgre)\b(?:ms)?sql\b|\bsql\s+server\b",
    "Cisco": r"\bcisco\b",
    "Hyper-V": r"\bhyper[- ]v\b",
    "Veeam": r"\bveeam\b",
    "SharePoint": r"\bsharepoint\b",
    "Exchange": r"\bexchange\s+(?:online|server)\b|\bmicrosoft\s+exchange\b",
    "Splunk": r"\bsplunk\b",
    "AWS CDK": r"\baws\s+cdk\b|cloud development kit",
    "FinOps": r"\bfinops\b",
    "SSO / SAML / Okta": r"\bsso\b|\bsaml\b|\bokta\b",
    "Salesforce": r"\bsalesforce\b",
    "Adobe Experience": r"\badobe\s+experience\b",
    "Snowflake": r"\bsnowflake\b",
    "ConnectWise / HaloPSA": r"\bconnectwise\b|\bhalopsa\b",
}

TARGET_LOCATIONS = re.compile(
    r"\b(?:sydney|melbourne|macquarie park|north sydney|parramatta|barangaroo|chatswood|"
    r"surry hills|pyrmont|mascot|camberwell|richmond|hawthorn|southbank|essendon|"
    r"docklands|cremorne|box hill|mulgrave|narre warren)\b",
    re.I,
)


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
        elif line and not re.search(
            r"@|https?://|\b(?:www\.|linkedin\.com|github\.com|gitlab\.com|t\.me|x\.com|twitter\.com)\S*|(?:\+?\d[ .()-]*){8,}",
            line, re.I,
        ):
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
            if skill == "Helm" and re.search(r"\b(?:tak(?:e|ing)|took|at)\s+the\s+$", left, re.I):
                continue
            if skill == "RDS" and re.search(r"\bremote\s+desktop(?:\s+services?)?\b", left + " " + right, re.I):
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
    # Score both coverage and depth; floor denominator at 3 to prevent 1/1 or 2/2 inflation.
    skill_points = round(65 * (0.6 * len(matched) / max(len(requested), 3) + 0.4 * min(len(matched) / 5, 1))) if requested else 0
    years = max((years for years, _ in experience_mentions(description, required_only=True)), default=None)
    if years is None:
        experience_points, experience_reason = 4, "Minimum d’expérience non précisé clairement"
    elif years <= 3:
        experience_points, experience_reason = 10, f"Minimum repéré : {years:g} an(s), dans la cible de 0 à 3 ans"
    else:
        experience_points, experience_reason = 3, f"Minimum repéré : {years:g} ans, au-dessus de la cible"
    area = job.get("area") or ""
    region = (job.get("region") or "").lower()
    location_points = 5 if TARGET_LOCATIONS.search(area) else (3 if "australia" in region else 0)
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
