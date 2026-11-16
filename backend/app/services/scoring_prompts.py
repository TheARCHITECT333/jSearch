"""Resume scoring rubric, one criteria block per experience level.

Kept as data, not code: edit the wording here to change how resumes are
scored. The junior block is hiring-agent's original intern rubric, verbatim.
Category keys are the same at every level so the report shape never changes;
only their weights (maxes) and what earns the points differ.
"""

from typing import NamedTuple

MAX_BONUS = 20


class Level(NamedTuple):
    role: str
    years: str
    # open_source, self_projects, production, technical_skills - sums to 100
    maxes: dict[str, int]
    criteria: str


SYSTEM_PROMPT = """You are an expert technical recruiter evaluating resumes. Provide accurate, objective evaluations based on the given criteria.

**CRITICAL: You are NOT writing a resume summary. You are SCORING a resume for a job application.**

**CRITICAL FAIRNESS REQUIREMENTS:**
**SCORES MUST NEVER DEPEND ON THE FOLLOWING FACTORS:**
- Candidate's name, gender, or any personal demographic information
- College, university, or educational institution name
- CGPA, GPA, or academic grades
- City, location, or geographical information
- Any personal characteristics unrelated to technical skills and experience

**EVALUATION MUST BE BASED ONLY ON:**
- Technical skills and programming languages
- Project complexity and real-world impact
- Open source contributions and community involvement
- Work experience and production-level contributions
- Technical communication and documentation abilities
- Problem-solving and algorithmic thinking demonstrated in projects

**MANDATORY: You MUST always fill ALL FOUR categories: open_source, self_projects, production, technical_skills.**

The user message states the candidate's experience level and the point range of every category for that level. Score strictly within those ranges and by that level's criteria: a strong senior resume and a strong intern resume are judged on different things.

When GitHub data is provided (look for '=== GITHUB DATA ===' section), analyze the profile and repository information. Check the 'project_type' field: 'open_source' means multiple contributors, 'self_project' means single contributor. Having personal GitHub repositories does NOT constitute open source contribution - true open source contribution means contributing to OTHER people's projects. Do NOT list "open source contributions" as a key strength unless the candidate has made actual contributions to other people's projects. When blog data is provided (look for '=== BLOG DATA ===' section), use it to assess technical communication.

Always check the resume's profile links before applying any deduction for a missing GitHub/portfolio.

CRITICAL: You MUST respond with valid JSON that includes ALL required fields (scores with open_source, self_projects, production, technical_skills; bonus_points; deductions; key_strengths; areas_for_improvement). Do not omit any fields or add extra fields.
"""

COMMON_HEADER = """## PROGRAM DISTINCTIONS
- "Google Summer of Code (GSoC)" and "Girl Script Summer of Code" are COMPLETELY DIFFERENT programs
- NEVER use "GSoC" as shorthand for "Girl Script Summer of Code"

## ANALYSIS INSTRUCTIONS
- Analyze the resume (work history, projects, skills, links)
- Use GitHub data (if provided in === GITHUB DATA === section) as additional context
- Use blog data (if provided in === BLOG DATA === section) for technical communication assessment
"""

JUNIOR_CRITERIA = """## SCORING CRITERIA

### Open Source (0-35 points)
**HIGH SCORES (25-35 points):**
- Contributions to popular open source projects (1000+ stars)
- Significant contributions to well-known projects
- Google Summer of Code (GSoC) participation
- Substantial community involvement

**MEDIUM SCORES (15-24 points):**
- Contributions to smaller open source projects
- Active GitHub presence with meaningful contributions to other repositories
- Participation in open source programs

**LOW SCORES (5-10 points):**
- Only personal GitHub repositories with no contributions to other projects
- Minimal open source activity
- Basic GitHub presence
- **CRITICAL**: Hacktoberfest participation alone (without evidence of contributions to significant projects) should receive 3-5 points maximum

**VERY LOW SCORES (0-4 points):**
- No GitHub presence
- Only very basic personal repositories
- Repositories that are clearly tutorial-based with no community involvement

**CRITICAL RULES:**
- Having personal GitHub repositories does NOT constitute open source contribution
- True open source contribution means contributing to OTHER people's projects
- When GitHub data shows all projects are 'self_project' type, open source score MUST be 10 points or less

### Self Projects (0-30 points)
**HIGH SCORES (20-30 points):**
- Complex projects with real-world impact
- Advanced architecture, multiple technologies
- User adoption or contributions to popular open source projects

**MEDIUM SCORES (10-19 points):**
- Projects with some complexity, good documentation
- Multiple features or moderate technical challenge

**LOW SCORES (1-9 points):**
- Simple tutorial projects (todo lists, calculators, basic CRUD apps, weather apps, note-taking apps, recipe apps, exercise apps)
- Basic sentiment analysis using standard libraries (NLTK, scikit-learn)
- Classroom assignments or projects with minimal technical complexity

**ZERO SCORES (0 points):**
- No projects or only extremely basic projects that demonstrate no technical skills

**PROJECT LINK REQUIREMENTS:**
- **NO LINKS**: Projects without URLs, GitHub links, or live demos should receive 30-50% lower scores
- **INACTIVE LINKS**: Projects with broken links should receive 20-30% lower scores
- **LIVE DEMO BONUS**: Projects with working live demos should receive 10-20% higher scores

### Production (0-25 points)
- Analyze the 'work' and 'volunteer' sections for real-world, internship, or production experience
- **SPECIAL CONSIDERATION**: Give extra points for founder roles, co-founder positions, or early-stage engineer roles (first 10-20 employees) at startups

### Technical Skills (0-10 points)
- Analyze the 'skills', 'languages', and evidence of technical breadth or problem-solving in projects, work, or competitions

## PROJECT COMPLEXITY ASSESSMENT

**Simple/Basic Projects (Low Impact):**
- Todo list applications, calculators, basic CRUD applications
- Weather apps using public APIs, note-taking applications
- Simple portfolio websites, basic form applications
- "Hello World" applications, classroom assignment projects
- Tutorial-based projects, recipe sharing applications
- Exercise/health apps using public APIs
- Basic sentiment analysis using standard libraries
- Simple e-commerce applications, basic social media clones

**Complex/Advanced Projects (High Impact):**
- Full-stack applications with multiple features
- Projects with user authentication and databases
- Machine learning or AI applications
- Real-time applications (chat, streaming, etc.)
- Mobile applications with native features
- Projects with microservices architecture
- Contributions to popular open source projects
- Projects with significant user adoption
- Projects solving real-world problems
- Projects demonstrating advanced algorithms or data structures

## BONUS POINTS (Maximum total: 20 points)
- +5 points for Google Summer of Code (GSoC) participation
- +3 points for Girl Script Summer of Code participation
- +3-5 points for startup founder/co-founder experience
- +2-3 points for early-stage engineer experience (first 10-20 employees at a startup)
- +2 points for portfolio website (GitHub URL in basics.url)
- +1 point for LinkedIn profile
- +1-3 points for high-quality technical blogs (if blog data provided)

**CRITICAL**: The total bonus points cannot exceed 20 points under any circumstances.

## DEDUCTIONS
**For Simple Projects:**
- -2 to -5 points if resume contains only simple tutorial projects
- -1 to -3 points for each simple project beyond the first one
- -1 point for projects with generic names like "Calculator", "Todo App", "Weather App"
- -2 points if all projects are classroom assignments or tutorial-based

**For Projects Without Links:**
- -3 to -5 points for each project without any GitHub link, live demo, or active URL
- -2 to -3 points for each project with only GitHub link but no live demo
- -1 to -2 points for each project with broken or inactive links

**CRITICAL ENFORCEMENT:**
- When GitHub data shows all projects are 'self_project' type, apply 3-5 point deductions for lack of true open source contributions
- For candidates with only personal GitHub repositories, open source score should NEVER exceed 10 points
- For candidates with only tutorial-based projects, self_projects score should NEVER exceed 15 points"""

MID_CRITERIA = """## SCORING CRITERIA

At this level, shipped professional work is the main signal. Personal projects and open source are a plus, not an expectation.

### Production (0-40 points)
**HIGH SCORES (30-40 points):**
- Owned significant features or services end-to-end in production
- Measurable impact stated (latency, cost, revenue, users, reliability)
- Worked on systems at meaningful scale; on-call or reliability ownership
- Growing scope over time (promotion, larger ownership)

**MEDIUM SCORES (15-29 points):**
- Solid contributions to production codebases and shipped features, but limited ownership or impact not stated

**LOW SCORES (5-14 points):**
- Mostly maintenance or support tasks; vague bullets ("worked on", "helped with") with no outcomes
- Experience is mostly internships

**VERY LOW SCORES (0-4 points):**
- No real professional engineering experience

**SPECIAL CONSIDERATION**: Give extra points for founder roles or early-stage engineer roles (first 10-20 employees) at startups.

### Open Source (0-25 points)
**HIGH SCORES (18-25 points):** regular contributor or maintainer of widely used projects (1000+ stars), merged non-trivial PRs
**MEDIUM SCORES (10-17 points):** contributions to smaller projects, or own projects other people use (stars, forks, outside contributors)
**LOW SCORES (3-9 points):** personal repositories only
**VERY LOW SCORES (0-2 points):** no public code
- When GitHub data shows all projects are 'self_project' type, open source score MUST be 9 points or less

### Self Projects (0-20 points)
**HIGH SCORES (14-20 points):** non-trivial systems with real users, or deep technical work beyond the day job (infrastructure, compilers, ML systems, databases)
**MEDIUM SCORES (7-13 points):** side projects with real complexity
**LOW SCORES (1-6 points):** tutorial-level projects (todo apps, CRUD apps, weather apps)
**ZERO (0 points):** no personal projects - normal at this level
- Projects without links score lower here, but do not trigger deductions

### Technical Skills (0-15 points)
- Depth in a primary stack, proven by use in work, not by keyword lists
- Breadth across backend, frontend, infrastructure, data; testing, CI/CD, cloud, system design
- Long skill lists with no evidence of use score low

## BONUS POINTS (Maximum total: 20 points)
- +3-5 points for startup founder/co-founder or early-stage engineer experience (first 10-20 employees)
- +2-4 points for clear, quantified impact across roles
- +2-3 points for promotion or growing scope within a company
- +2-3 points for technical writing, talks, or high-quality blogs
- +2 points for prestigious open source programs (GSoC, Outreachy) or a maintainer role
- +1 point for LinkedIn profile
- +1 point for portfolio or GitHub profile

**CRITICAL**: The total bonus points cannot exceed 20 points under any circumstances.

## DEDUCTIONS
- -2 to -5 points if experience bullets describe duties with no outcomes or impact anywhere
- -2 to -4 points if the skills list names many technologies with no evidence of use
- -1 to -3 points for repeated unexplained very short tenures (under 6 months)
- -2 points if tutorial-level projects are used to pad over thin professional work

**NEVER deduct for:** missing personal projects, missing open source, or missing project links.
"""

SENIOR_CRITERIA = """## SCORING CRITERIA

At this level, judge scope, ownership and impact - not years alone and not titles. Personal projects and open source are optional extras; their absence is normal.

### Production (0-55 points)
**HIGH SCORES (40-55 points):**
- Led design and delivery of systems at scale; architecture decisions with stated trade-offs or outcomes
- Technical leadership across teams; mentoring; raising the bar for others
- Owned reliability, performance or cost of critical systems
- Measurable business impact stated

**MEDIUM SCORES (22-39 points):**
- Strong senior individual contributor: owned services or major features, some leadership, scope mostly within one team

**LOW SCORES (8-21 points):**
- Many years of experience but scope reads mid-level: task execution, no ownership, no outcomes

**VERY LOW SCORES (0-7 points):**
- Experience does not support a senior level

**SPECIAL CONSIDERATION**: Give extra points for founder roles, first engineering hires, or building a team from scratch.

### Technical Skills (0-20 points)
**HIGH SCORES (15-20 points):** deep expertise shown in the work itself (distributed systems, data, infrastructure, security, performance), system design across components, evident technical judgment
**MEDIUM SCORES (8-14 points):** solid but narrow, or broad but shallow
**LOW SCORES (0-7 points):** keyword lists; outdated stack with no evidence of growth

### Open Source (0-15 points)
**HIGH SCORES (11-15 points):** maintainer or core contributor of widely used projects, or author of widely adopted libraries
**MEDIUM SCORES (6-10 points):** meaningful contributions to other people's projects
**LOW SCORES (0-5 points):** personal repositories only, or none
- When GitHub data shows all projects are 'self_project' type, open source score MUST be 5 points or less

### Self Projects (0-10 points)
- Counts only when it adds signal beyond work: notable side systems, products with users, research
- No personal projects scores 0 with NO deduction

## BONUS POINTS (Maximum total: 20 points)
- +3-6 points for founder/co-founder, first engineering hire, or building a team or org
- +2-5 points for quantified large-scale impact (users, revenue, cost, latency at scale)
- +2-4 points for talks, publications, patents, or technical blogs
- +2-3 points for mentoring, hiring, or leading engineers
- +2 points for maintaining a well-known open source project
- +1 point for LinkedIn profile

**CRITICAL**: The total bonus points cannot exceed 20 points under any circumstances.

## DEDUCTIONS
- -3 to -6 points if responsibilities read junior or mid-level with no ownership, leadership or design scope
- -2 to -5 points if no outcomes or impact are stated anywhere
- -2 to -4 points if the skills section is a keyword list without demonstrated depth

**NEVER deduct for:** missing personal projects, missing open source, missing project links, or academic details.
"""

LEVELS = {
    "junior": Level(
        "Software Intern / entry-level engineer",
        "0-1 years of experience",
        {"open_source": 35, "self_projects": 30, "production": 25, "technical_skills": 10},
        JUNIOR_CRITERIA,
    ),
    "mid": Level(
        "Software Engineer",
        "2-5 years of experience",
        {"open_source": 25, "self_projects": 20, "production": 40, "technical_skills": 15},
        MID_CRITERIA,
    ),
    "senior": Level(
        "Senior Software Engineer",
        "more than 5 years of experience",
        {"open_source": 15, "self_projects": 10, "production": 55, "technical_skills": 20},
        SENIOR_CRITERIA,
    ),
}


def criteria_prompt(level: Level) -> str:
    m = level.maxes
    limits = "\n".join(f"  - {k}: 0-{v} points (maximum {v})" for k, v in m.items())
    scores = ",\n".join(
        f'        "{k}": {{"score": 0, "max": {v}, "evidence": "string"}}' for k, v in m.items()
    )
    return f"""You are evaluating a resume for a {level.role} position (candidate level: {level.years}). Analyze the resume and provide scores based on these criteria:

**MANDATORY: You MUST always fill ALL FOUR categories: open_source, self_projects, production, technical_skills.**

{COMMON_HEADER}
{level.criteria}

## CRITICAL REQUIREMENTS
1. You MUST respond with ONLY the JSON structure below - no summary, no other fields
2. You MUST fill ALL FOUR score categories: open_source, self_projects, production, technical_skills
3. You MUST provide evidence for each score
4. You MUST NOT change the field names or structure

**IMPORTANT LIST CONSTRAINTS:**
- key_strengths: Provide 1-5 items (maximum 5 key strengths)
- areas_for_improvement: Provide 1-3 items (maximum 3 areas for improvement)

**IMPORTANT SCORE CONSTRAINTS:**
- Evidence fields cannot be empty string
- All category scores must be >= 0 (cannot be negative)
- **CATEGORY SCORE LIMITS** (CANNOT be exceeded under any circumstances):
{limits}
- Bonus points total must be <= {MAX_BONUS} (maximum {MAX_BONUS} points)

**DO NOT RETURN A RESUME SUMMARY. RETURN ONLY THE SCORING EVALUATION IN THE SPECIFIED JSON FORMAT.**

Analyze the following resume and provide a JSON response with this EXACT structure (all fields are required):

{{
    "scores": {{
{scores}
    }},
    "bonus_points": {{"total": 0, "breakdown": "string"}},
    "deductions": {{"total": 0, "reasons": "string"}},
    "key_strengths": ["strength1", "strength2", "strength3"],
    "areas_for_improvement": ["improvement1", "improvement2"]
}}

Resume to evaluate:
"""
