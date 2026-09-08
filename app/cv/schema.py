"""
Canonical CV JSON schema and sample data.

Every CV in JobPilot flows through this structure:
- The editor (tailor.html) reads/writes this shape
- The preview template (cv_preview.html) renders this shape
- The PDF export (WeasyPrint) renders the same template from this shape
"""

SAMPLE_CV = {
    "personal_info": {
        "full_name": "Alex Chen",
        "job_title": "Full-Stack Software Engineer",
        "email": "alex.chen@email.com",
        "phone": "+1 (555) 123-4567",
        "location": "San Francisco, CA",
        "website": {"text": "alexchen.dev", "url": "https://alexchen.dev"},
        "linkedin": {"text": "LinkedIn", "url": "https://linkedin.com/in/alexchen"},
        "github": {"text": "GitHub", "url": "https://github.com/alexchen"},
        "portfolio": {"text": "Portfolio", "url": ""},
        "other_links": [],
    },
    "summary": (
        "Software engineer with 5+ years of experience building scalable web applications. "
        "Proficient in Python, TypeScript, and cloud-native architectures. "
        "Passionate about developer experience and shipping reliable products."
    ),
    "skills": [
        "Python", "TypeScript", "JavaScript", "React", "Node.js",
        "Flask", "FastAPI", "PostgreSQL", "Redis", "Docker",
        "AWS", "CI/CD", "Git", "REST APIs", "GraphQL",
    ],
    "skill_groups": [
        {"category": "Languages", "items": ["Python", "TypeScript", "JavaScript", "SQL"]},
        {"category": "Frameworks", "items": ["React", "Flask", "FastAPI", "Node.js"]},
        {"category": "Infrastructure", "items": ["AWS", "Docker", "PostgreSQL", "Redis", "CI/CD"]},
    ],
    "experience": [
        {
            "title": "Senior Software Engineer",
            "company": "Acme Corp",
            "location": "San Francisco, CA",
            "start_date": "Jan 2022",
            "end_date": "Present",
            "bullets": [
                "Led migration of monolithic Flask app to microservices, reducing deploy time by 60%",
                "Designed and implemented real-time data pipeline processing 2M+ events/day",
                "Mentored 3 junior engineers and established code review best practices",
            ],
            "description": "",
        },
        {
            "title": "Software Engineer",
            "company": "StartupXYZ",
            "location": "Remote",
            "start_date": "Jun 2019",
            "end_date": "Dec 2021",
            "bullets": [
                "Built customer-facing React dashboard used by 10K+ active users",
                "Implemented RESTful APIs serving 500K+ requests/day with 99.9% uptime",
                "Reduced database query latency by 40% through indexing and query optimization",
            ],
            "description": "",
        },
    ],
    "education": [
        {
            "degree": "B.S. Computer Science",
            "institution": "University of California, Berkeley",
            "location": "Berkeley, CA",
            "start_date": "2015",
            "end_date": "2019",
            "gpa": "3.7",
            "details": "Dean's List. Teaching Assistant for CS 162 (Operating Systems).",
        },
    ],
    "projects": [
        {
            "name": "OpenTracer",
            "url": "https://github.com/alexchen/opentracer",
            "description": "Open-source distributed tracing library for Python microservices",
            "bullets": [
                "800+ GitHub stars, adopted by 3 companies in production",
                "Built with async Python, OpenTelemetry-compatible, published to PyPI",
            ],
        },
    ],
    "certifications": [
        {
            "name": "AWS Solutions Architect – Associate",
            "issuer": "Amazon Web Services",
            "date": "2023",
            "url": "",
        },
    ],
    "languages": [
        {"language": "English", "proficiency": "Native"},
        {"language": "Mandarin", "proficiency": "Professional"},
    ],
    "references": [
        {
            "name": "Jane Smith",
            "title": "Engineering Manager",
            "company": "Acme Corp",
            "email": "jane.smith@acme.com",
        },
    ],
    "custom_sections": [],
}
