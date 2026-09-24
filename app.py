import streamlit as st
import pandas as pd
import os
import json
import db
from typing import Optional
from matcher import analyse_student, MatchResult
# ──────────────────────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────────────────────
DATA_DIR         = os.path.join(os.path.dirname(__file__), "data")
STUDENTS_CSV     = os.path.join(DATA_DIR, "students.csv")
JOBS_CSV         = os.path.join(DATA_DIR, "industry_jobs.csv")
CREDENTIALS_CSV  = os.path.join(DATA_DIR, "credentials.csv")
APPROVALS_CSV    = os.path.join(DATA_DIR, "course_approvals.csv")

# Score band thresholds
HIGH_THRESHOLD = 75   # >= 75% -> Job-Ready  (green)
MID_THRESHOLD  = 40   # >= 40% -> Partially Ready (orange)
                      # <  40% -> Needs Training  (red)

# Auto-shortlist threshold for Industry Portal
SHORTLIST_THRESHOLD = 60  # >= 60% -> candidate shown to HR

# Teacher scoring scale (1–5) with exact display labels
TEACHER_SCORE_LABELS = {
    1: "Least Recommended (Can be skipped)",
    2: "Moderately Recommended",
    3: "Recommended",
    4: "Highly Recommended",
    5: "Most Important (Should not skip)",
}

# Mock course metadata for the demo (keyed by Job_Role, case-insensitive)
# Used when industry_jobs.csv lacks Course_Summary / Course_Details columns.
MOCK_COURSE_INFO = {
    "data scientist": {
        "summary": (
            "A comprehensive Data Science specialization covering Python, statistics, "
            "machine learning, and data visualization from Johns Hopkins University."
        ),
        "details": (
            "This 10-course specialization by Johns Hopkins University on Coursera "
            "takes you from the basics of R and Python programming through exploratory "
            "data analysis, statistical inference, regression models, machine learning, "
            "and a capstone project. You will work with real-world datasets, learn to "
            "clean and wrangle messy data, build predictive models using scikit-learn "
            "and TensorFlow, and communicate results through compelling visualizations. "
            "Ideal for students with foundational programming skills who want a "
            "structured path into industry data science roles."
        ),
    },
    "machine learning engineer": {
        "summary": (
            "Stanford-led ML specialization covering supervised/unsupervised learning, "
            "neural networks, and best practices for deploying ML systems."
        ),
        "details": (
            "Andrew Ng's Machine Learning Specialization on Coursera provides a "
            "rigorous yet accessible introduction to modern machine learning. The "
            "curriculum spans linear regression, logistic regression, neural networks, "
            "decision trees, clustering, recommender systems, and reinforcement "
            "learning. Labs use TensorFlow and NumPy so you build real implementations. "
            "The final course focuses on ML system design — data pipelines, model "
            "evaluation, deployment strategies, and monitoring — preparing you for "
            "production ML engineering roles."
        ),
    },
    "web developer": {
        "summary": (
            "freeCodeCamp's full-stack curriculum covering HTML, CSS, JavaScript, "
            "React, Node.js, and relational databases with hands-on projects."
        ),
        "details": (
            "freeCodeCamp offers a free, self-paced full-stack web development "
            "curriculum totaling over 3,000 hours of coursework. You progress through "
            "responsive web design (HTML5/CSS3), JavaScript algorithms, front-end "
            "frameworks (React), back-end development (Node.js, Express), databases "
            "(MongoDB, PostgreSQL), and quality assurance. Each section culminates in "
            "certification projects you build from scratch, giving you a portfolio of "
            "deployed applications that demonstrate job-ready skills to employers."
        ),
    },
    "data analyst": {
        "summary": (
            "Kaggle Learn's micro-courses on Python, SQL, data cleaning, "
            "visualization, and introductory ML for aspiring analysts."
        ),
        "details": (
            "Kaggle Learn provides bite-sized, interactive courses that cover the "
            "core toolkit of a data analyst. Starting with Python fundamentals and "
            "Pandas data manipulation, you advance through SQL for data extraction, "
            "data cleaning best practices, Matplotlib/Seaborn visualization, feature "
            "engineering, and introductory machine learning with scikit-learn. Each "
            "lesson pairs a concise tutorial with a hands-on Kaggle notebook exercise, "
            "letting you practice on real competition datasets and build a public "
            "notebook portfolio."
        ),
    },
    "embedded systems engineer": {
        "summary": (
            "Udemy bare-metal embedded programming course covering C, "
            "microcontrollers, RTOS concepts, and hardware interfacing."
        ),
        "details": (
            "This Udemy course teaches embedded systems programming from the ground "
            "up. You start with C programming refreshers, then move into ARM Cortex-M "
            "microcontroller architecture, GPIO, timers, interrupts, UART/SPI/I2C "
            "communication protocols, and real-time operating system (RTOS) concepts "
            "using FreeRTOS. Hands-on labs guide you through writing bare-metal "
            "firmware, debugging with JTAG/SWD, and integrating sensors and actuators. "
            "By the end you will have built several embedded projects suitable for "
            "your engineering portfolio."
        ),
    },
}


# ──────────────────────────────────────────────────────────────
#  CREDENTIALS SETUP
# ──────────────────────────────────────────────────────────────

def setup_credentials() -> None:
    """
    Auto-generate data/credentials.csv if it doesn't exist.

    Creates one row per student (using Student_ID from students.csv)
    plus two extra accounts: HR01 (Industry) and Admin01 (Academician).
    All passwords default to 'pass123'.
    """
    if os.path.exists(CREDENTIALS_CSV):
        return  # already set up

    if not os.path.exists(STUDENTS_CSV):
        return  # can't generate without student data

    students = pd.read_csv(STUDENTS_CSV)
    rows = []

    # One credential row per student
    for sid in students["Student_ID"]:
        rows.append({"User_ID": str(sid), "Password": "pass123", "Role": "Student"})

    # Fixed industry and academician accounts
    rows.append({"User_ID": "HR01",    "Password": "pass123", "Role": "Industry"})
    rows.append({"User_ID": "Admin01", "Password": "pass123", "Role": "Academician"})

    cred_df = pd.DataFrame(rows)
    cred_df.to_csv(CREDENTIALS_CSV, index=False)


def load_credentials() -> pd.DataFrame:
    """Load the credentials CSV."""
    return pd.read_csv(CREDENTIALS_CSV, dtype=str)


# ──────────────────────────────────────────────────────────────
#  COURSE APPROVALS HELPER
# ──────────────────────────────────────────────────────────────

def load_approvals() -> pd.DataFrame:
    """
    Auto-generate and load data/course_approvals.csv.

    Columns:
        Student_ID       – student identifier
        Target_Role      – the job role the course is for
        Course_Link      – AI-recommended training URL
        Approval_Status  – Pending | Scored
        Teacher_Score    – 0 (unscored) or 1-5
    """
    required_cols = [
        "Student_ID", "Target_Role", "Course_Link",
        "Approval_Status", "Teacher_Score",
    ]
    if not os.path.exists(APPROVALS_CSV):
        df = pd.DataFrame(columns=required_cols)
        df.to_csv(APPROVALS_CSV, index=False)
        return df

    df = pd.read_csv(APPROVALS_CSV, dtype=str)

    # Backward-compat: add Teacher_Score if missing from an older CSV
    if "Teacher_Score" not in df.columns:
        df["Teacher_Score"] = "0"
        df.to_csv(APPROVALS_CSV, index=False)

    return df


def save_approvals(df: pd.DataFrame) -> None:
    """Persist the approvals DataFrame back to CSV."""
    df.to_csv(APPROVALS_CSV, index=False)


def _get_course_info(target_role: str) -> dict:
    """
    Return mock Course_Summary and Course_Details for a given job role.
    Falls back to a generic blurb if the role is not in MOCK_COURSE_INFO.
    """
    key = target_role.strip().lower()
    if key in MOCK_COURSE_INFO:
        return MOCK_COURSE_INFO[key]
    return {
        "summary": (
            f"AI-recommended training course to bridge skill gaps for the "
            f"{target_role} role."
        ),
        "details": (
            f"This course covers the core competencies required for a {target_role} "
            "position, including both technical and soft skill development. "
            "The curriculum is designed to take you from your current skill level "
            "to industry readiness through structured modules, hands-on projects, "
            "and assessments. Please consult your faculty mentor for personalized "
            "guidance on how to best utilize this resource."
        ),
    }


# ──────────────────────────────────────────────────────────────
#  DATA LOADERS
# ──────────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Loading student database...")
def load_students() -> pd.DataFrame:
    """Load and validate students.csv. Parses skill columns into Python lists."""
    if not os.path.exists(STUDENTS_CSV):
        raise FileNotFoundError(
            f"students.csv not found at {STUDENTS_CSV}. "
            "Place it in the data/ folder and restart."
        )
    df = pd.read_csv(STUDENTS_CSV)
    required = {
        "Student_ID", "Name", "Degree", "Target_Job_Role",
        "Technical_Skills", "Soft_Skills"
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"students.csv missing columns: {missing}")
    df["Technical_Skills_List"] = df["Technical_Skills"].apply(_parse_skills)
    df["Soft_Skills_List"]      = df["Soft_Skills"].apply(_parse_skills)
    return df


@st.cache_data(show_spinner="Loading industry jobs database...")
def load_jobs() -> pd.DataFrame:
    """Load and validate industry_jobs.csv. Parses skill columns into Python lists."""
    if not os.path.exists(JOBS_CSV):
        raise FileNotFoundError(
            f"industry_jobs.csv not found at {JOBS_CSV}. "
            "Place it in the data/ folder and restart."
        )
    df = pd.read_csv(JOBS_CSV)
    required = {
        "Job_Role", "Required_Technical_Skills",
        "Required_Soft_Skills", "Recommended_Training_Link"
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"industry_jobs.csv missing columns: {missing}")
    df["Required_Technical_Skills_List"] = df["Required_Technical_Skills"].apply(_parse_skills)
    df["Required_Soft_Skills_List"]      = df["Required_Soft_Skills"].apply(_parse_skills)
    return df


# ──────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────

def _parse_skills(raw: str) -> list:
    """Convert a comma-separated string into a clean list. NaN-safe."""
    if pd.isna(raw) or not str(raw).strip():
        return []
    return [s.strip() for s in str(raw).split(',') if s.strip()]


def _safe_load(loader_fn, label: str):
    """Run a loader; surface errors as Streamlit messages instead of crashes."""
    try:
        return loader_fn()
    except FileNotFoundError as e:
        st.error(f"📂 **File Not Found — {label}**\n\n{e}")
        return None
    except ValueError as e:
        st.error(f"⚠️ **Schema Error — {label}**\n\n{e}")
        return None
    except Exception as e:
        st.error(f"❌ **Unexpected Error — {label}**\n\n{e}")
        return None


def _score_band(score: float) -> tuple:
    """
    Return (emoji, label, bar_color_hex) based on the readiness score.

    Bands:
        >= 75  ->  Job-Ready       (green)
        >= 40  ->  Partially Ready (orange)
        <  40  ->  Needs Training  (red)
    """
    if score >= HIGH_THRESHOLD:
        return ("🟢", "Job-Ready", "#2ecc71")
    elif score >= MID_THRESHOLD:
        return ("🟡", "Partially Ready", "#f39c12")
    else:
        return ("🔴", "Needs Training", "#e74c3c")


def _pill(text: str, bg: str, fg: str = "white") -> str:
    """Return an HTML pill/badge span for a single skill."""
    style = (
        f"background:{bg}; color:{fg}; "
        "border-radius:20px; padding:4px 12px; "
        "margin:3px 4px; display:inline-block; "
        "font-size:0.85rem; font-weight:600; "
        "letter-spacing:0.02em;"
    )
    return f"<span style='{style}'>{text}</span>"


def _skill_pills(skills: list, color: str) -> str:
    """Render a list of skills as inline HTML pill badges."""
    if not skills:
        return "<span style='color:#aaa; font-style:italic;'>None</span>"
    return "".join(_pill(s, color) for s in skills)


# ──────────────────────────────────────────────────────────────
#  SIDEBAR — Student Portal
# ──────────────────────────────────────────────────────────────

def render_student_sidebar(students_df: pd.DataFrame,
                           user_id: Optional[str] = None) -> pd.Series:
    """
    Render the Student Portal sidebar controls and return the selected student row.

    If *user_id* is provided (logged-in student), the dropdown is skipped and
    the student is automatically resolved from students_df via Student_ID.
    """
    with st.sidebar:
        st.divider()

        if user_id is not None:
            # Logged-in student — auto-resolve, no dropdown
            match = students_df[students_df["Student_ID"] == user_id]
            if match.empty:
                st.error(f"No student found with ID '{user_id}'.")
                st.stop()
            row = match.iloc[0]
        else:
            # Fallback: manual selector (shouldn't happen with RBAC)
            st.markdown("**Select a Student**")
            selected_name = st.selectbox(
                label="Student",
                options=students_df["Name"].tolist(),
                label_visibility="collapsed",
                help="Choose a student to view their SkillSync readiness report.",
            )
            row = students_df[students_df["Name"] == selected_name].iloc[0]

        st.divider()

        # Mini student card
        st.markdown("**Student ID**")
        st.code(row["Student_ID"], language=None)
        st.markdown("**Degree**")
        st.info(row["Degree"])
        st.markdown("**Target Role**")
        st.info(row["Target_Job_Role"])

        st.divider()
        st.caption("🚀 SkillSync")
        st.caption("Bridging Skills. Building Futures.")

    return row


# ──────────────────────────────────────────────────────────────
#  STUDENT PORTAL — DASHBOARD SECTIONS
# ──────────────────────────────────────────────────────────────

def render_student_header(row: pd.Series) -> None:
    """Display the student's basic info in a three-column card row."""
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            "<div style='background:#1e293b; border-radius:12px; padding:20px;'>"
            "<p style='color:#94a3b8; margin:0; font-size:0.8rem; text-transform:uppercase; letter-spacing:0.08em;'>Student</p>"
            f"<p style='color:#f1f5f9; margin:4px 0 0; font-size:1.3rem; font-weight:700;'>{row['Name']}</p>"
            "</div>",
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            "<div style='background:#1e293b; border-radius:12px; padding:20px;'>"
            "<p style='color:#94a3b8; margin:0; font-size:0.8rem; text-transform:uppercase; letter-spacing:0.08em;'>Degree</p>"
            f"<p style='color:#f1f5f9; margin:4px 0 0; font-size:1.3rem; font-weight:700;'>{row['Degree']}</p>"
            "</div>",
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            "<div style='background:#1e293b; border-radius:12px; padding:20px;'>"
            "<p style='color:#94a3b8; margin:0; font-size:0.8rem; text-transform:uppercase; letter-spacing:0.08em;'>Target Role</p>"
            f"<p style='color:#f1f5f9; margin:4px 0 0; font-size:1.3rem; font-weight:700;'>{row['Target_Job_Role']}</p>"
            "</div>",
            unsafe_allow_html=True,
        )


def render_readiness_score(result: MatchResult) -> None:
    """Display the large visual Job Readiness Score section."""
    emoji, label, color = _score_band(result.readiness_score)
    score_pct = int(result.readiness_score)

    st.markdown("### 📊 Job Readiness Score")

    # Score number + band label side by side
    left, right = st.columns([1, 3])
    with left:
        st.markdown(
            f"<div style='text-align:center; background:#1e293b; "
            "border-radius:12px; padding:24px 16px;'>"
            f"<p style='font-size:3.5rem; font-weight:900; color:{color}; margin:0;'>"
            f"{score_pct}%</p>"
            f"<p style='font-size:1rem; color:#cbd5e1; margin:6px 0 0;'>"
            f"{emoji} {label}</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    with right:
        # Styled progress bar
        st.markdown(
            f"<p style='color:#94a3b8; font-size:0.85rem; margin-bottom:6px;'>"
            f"Overall readiness for <strong style='color:#f1f5f9;'>"
            f"{result.target_job}</strong></p>",
            unsafe_allow_html=True,
        )
        # Native Streamlit progress bar
        st.progress(score_pct / 100)

        # Breakdown mini-metrics below the bar
        m1, m2, m3 = st.columns(3)
        m1.metric(
            label="Technical",
            value=f"{len(result.matched_technical)}/{result.total_required_technical}",
            help="Matched / Required Technical Skills",
        )
        m2.metric(
            label="Soft Skills",
            value=f"{len(result.matched_soft)}/{result.total_required_soft}",
            help="Matched / Required Soft Skills",
        )
        m3.metric(
            label="Overall",
            value=f"{score_pct}%",
            help="Combined readiness percentage",
        )


def render_skill_analysis(result: MatchResult) -> None:
    """Display Matched Skills (green) and Skill Gaps (red) in message boxes."""
    st.markdown("### 🧠 Skill Analysis")
    col_match, col_gap = st.columns(2, gap="large")

    with col_match:
        # ── Matched Technical ──────────────────────────────────
        if result.matched_technical:
            pills_html = _skill_pills(result.matched_technical, "#166534")
            st.success(
                f"✅ **Matched Technical Skills ({len(result.matched_technical)}/{result.total_required_technical})**\n\n"
                "You already have these skills that the role requires!",
            )
            st.markdown(pills_html, unsafe_allow_html=True)
        else:
            st.success("✅ **Matched Technical Skills (0)**\n\n"
                       "No technical skills matched yet.")

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Matched Soft ───────────────────────────────────────
        if result.matched_soft:
            pills_html = _skill_pills(result.matched_soft, "#14532d")
            st.success(
                f"✅ **Matched Soft Skills ({len(result.matched_soft)}/{result.total_required_soft})**\n\n"
                "Great interpersonal strengths for this role!",
            )
            st.markdown(pills_html, unsafe_allow_html=True)
        else:
            st.success("✅ **Matched Soft Skills (0)**\n\nNo soft skills matched yet.")

    with col_gap:
        # ── Gap Technical ──────────────────────────────────────
        if result.gap_technical:
            pills_html = _skill_pills(result.gap_technical, "#991b1b")
            st.error(
                f"❌ **Technical Skill Gaps ({len(result.gap_technical)} missing)**\n\n"
                "Acquire these to become fully job-ready.",
            )
            st.markdown(pills_html, unsafe_allow_html=True)
        else:
            st.error("❌ **Technical Skill Gaps (0)**\n\n"
                     "No technical gaps. Excellent!")

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Gap Soft ──────────────────────────────────────────
        if result.gap_soft:
            pills_html = _skill_pills(result.gap_soft, "#7f1d1d")
            st.error(
                f"❌ **Soft Skill Gaps ({len(result.gap_soft)} missing)**\n\n"
                "Work on these interpersonal skills to strengthen your profile.",
            )
            st.markdown(pills_html, unsafe_allow_html=True)
        else:
            st.error("❌ **Soft Skill Gaps (0)**\n\nNo soft skill gaps. Well done!")


def render_training_cta(result: MatchResult,
                       student_id: Optional[str] = None) -> None:
    """
    Display the call-to-action training recommendation at the bottom.

    When *student_id* is provided the function checks the
    course_approvals.csv for the faculty Teacher_Score and renders:
        Unscored (0)  → "⏳ Pending Teacher Review" warning + link
        Scored (1-5)  → Color-coded box with score label + link
    """
    st.markdown("### 🚀 Recommended Training")

    has_gaps = bool(result.gap_technical or result.gap_soft)

    if has_gaps:
        gap_count = len(result.gap_technical) + len(result.gap_soft)
        st.markdown(
            f"<div style='background:#1e3a5f; border-left:4px solid #3b82f6; "
            "border-radius:8px; padding:16px 20px; margin-bottom:16px;'>"
            f"<p style='color:#bfdbfe; margin:0; font-size:0.9rem;'>"
            f"You have <strong style='color:#93c5fd;'>{gap_count} skill gap(s)</strong> "
            f"to close before you are fully ready for "
            f"<strong style='color:#93c5fd;'>{result.target_job}</strong>. "
            "The course below is tailored to bridge exactly these gaps.</p>"
            "</div>",
            unsafe_allow_html=True,
        )

        # ── Determine teacher score ────────────────────────
        teacher_score = 0
        if student_id is not None:
            approvals_df = load_approvals()
            match = approvals_df[
                (approvals_df["Student_ID"] == str(student_id))
                & (approvals_df["Target_Role"].str.strip().str.lower()
                   == result.target_job.strip().lower())
            ]
            if not match.empty:
                try:
                    teacher_score = int(match.iloc[0]["Teacher_Score"])
                except (ValueError, TypeError):
                    teacher_score = 0

        # ── Render based on teacher score ──────────────────
        if teacher_score == 0:
            # Not yet reviewed
            st.warning(
                "⏳ **Pending Teacher Review** — This course recommendation "
                "is awaiting scoring from your faculty mentor."
            )
            st.link_button(
                label=f"📚 Start Training for {result.target_job} (Pending Review) →",
                url=result.training_link,
                type="secondary",
                use_container_width=True,
            )
        else:
            # Teacher has scored — pick color theme by score
            score_label = TEACHER_SCORE_LABELS.get(teacher_score, "Scored")
            score_themes = {
                1: {"bg": "#374151", "border": "#6b7280", "text": "#d1d5db", "emoji": "⬜"},
                2: {"bg": "#312e81", "border": "#6366f1", "text": "#c7d2fe", "emoji": "🟪"},
                3: {"bg": "#1e3a5f", "border": "#3b82f6", "text": "#bfdbfe", "emoji": "🔵"},
                4: {"bg": "#14532d", "border": "#22c55e", "text": "#bbf7d0", "emoji": "🟢"},
                5: {"bg": "#7f1d1d", "border": "#ef4444", "text": "#fca5a5", "emoji": "🔴"},
            }
            theme = score_themes.get(teacher_score, score_themes[3])

            st.markdown(
                f"<div style='background:{theme['bg']}; border:2px solid {theme['border']}; "
                "border-radius:10px; padding:14px 20px; margin-bottom:12px; "
                "text-align:center;'>"
                f"<span style='font-size:1.3rem; font-weight:800; color:{theme['text']};'>"
                f"{theme['emoji']} Faculty Score: {teacher_score} — {score_label}</span>"
                "</div>",
                unsafe_allow_html=True,
            )

            # High-priority callout for scores 4-5
            if teacher_score >= 4:
                st.success(
                    f"🎯 Your faculty mentor considers this course **{score_label}**. "
                    "It is strongly encouraged to complete it."
                )
            elif teacher_score == 3:
                st.info(
                    f"📘 Your faculty mentor rates this course as **{score_label}**. "
                    "Consider adding it to your learning plan."
                )
            elif teacher_score == 2:
                st.info(
                    f"📝 Your faculty mentor rates this course as **{score_label}**. "
                    "It may be helpful but is not critical."
                )
            else:  # score == 1
                st.warning(
                    f"💡 Your faculty mentor rates this course as **{score_label}**. "
                    "You may skip it and consult your teacher for alternatives."
                )

            st.link_button(
                label=f"📚 Start Training for {result.target_job} →",
                url=result.training_link,
                type="primary",
                use_container_width=True,
            )
    else:
        st.balloons()
        st.success(
            f"🏆 **Congratulations, {result.student_name}!** "
            f"You meet all the skill requirements for **{result.target_job}**. "
            "You are fully job-ready!"
        )


# ──────────────────────────────────────────────────────────────
#  INDUSTRY PORTAL — SECTIONS
# ──────────────────────────────────────────────────────────────

def render_industry_header() -> None:
    """Display the Industry Portal main header."""
    st.markdown(
        "<h1 style='font-size:2.4rem; font-weight:800; margin-bottom:0;'>"
        "🏢 Industry Partner Dashboard</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color:#94a3b8; font-size:1rem; margin-top:4px; margin-bottom:0;'>"
        "Post opportunities, publish courses, and auto-shortlist candidates</p>",
        unsafe_allow_html=True,
    )
    st.divider()


def render_post_opportunity() -> None:
    """
    'Post a New Opportunity' section.
    A Streamlit form that appends a new job row to industry_jobs.csv.
    """
    st.markdown("### 📝 Post a New Opportunity")
    st.markdown(
        "<p style='color:#94a3b8; font-size:0.9rem;'>"
        "Fill in the details below to add a new job role to the database.</p>",
        unsafe_allow_html=True,
    )

    with st.form("post_opportunity_form", clear_on_submit=True):
        job_title = st.text_input(
            "Job Title",
            placeholder="e.g. Backend Developer",
        )
        required_tech = st.text_input(
            "Required Technical Skills (comma-separated)",
            placeholder="e.g. Python, Django, PostgreSQL, Docker",
        )
        required_soft = st.text_input(
            "Required Soft Skills (comma-separated)",
            placeholder="e.g. Communication, Teamwork, Problem Solving",
        )

        submitted = st.form_submit_button(
            "🚀 Submit Opportunity",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        # Validate required fields
        if not job_title.strip():
            st.error("❌ **Job Title** is required.")
            return
        if not required_tech.strip():
            st.error("❌ **Required Technical Skills** is required.")
            return

        # Build the new row matching the CSV schema
        new_row = pd.DataFrame([{
            "Job_Role":                   job_title.strip(),
            "Required_Technical_Skills":  required_tech.strip(),
            "Required_Soft_Skills":       required_soft.strip(),
            "Recommended_Training_Link":  "",
        }])

        # Append to CSV (create header if file doesn't exist yet)
        file_exists = os.path.exists(JOBS_CSV)
        new_row.to_csv(
            JOBS_CSV,
            mode="a",
            header=not file_exists,
            index=False,
        )

        # Clear cached data so the new job appears everywhere
        load_jobs.clear()

        st.success("✅ **Job Opportunity Posted successfully!**")
        st.balloons()


def render_publish_upskilling() -> None:
    """
    'Publish Upskilling Program' section.
    A Streamlit form that lets industry partners share a training course.
    """
    st.markdown("### 📚 Publish Upskilling Program")
    st.markdown(
        "<p style='color:#94a3b8; font-size:0.9rem;'>"
        "Share a training program to help students bridge their skill gaps.</p>",
        unsafe_allow_html=True,
    )

    with st.form("publish_upskilling_form", clear_on_submit=True):
        program_title = st.text_input(
            "Program Title",
            placeholder="e.g. Full-Stack Web Development Bootcamp",
        )
        target_skill = st.text_input(
            "Target Skill",
            placeholder="e.g. SQL, React, Machine Learning",
        )
        course_link = st.text_input(
            "Link to Course",
            placeholder="e.g. https://www.coursera.org/...",
        )

        submitted = st.form_submit_button(
            "📢 Publish Course",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not program_title.strip():
            st.error("❌ **Program Title** is required.")
            return
        if not target_skill.strip():
            st.error("❌ **Target Skill** is required.")
            return
        if not course_link.strip():
            st.error("❌ **Link to Course** is required.")
            return

        st.success(
            f"✅ **Upskilling Program Published!**\n\n"
            f"**{program_title.strip()}** targeting "
            f"**{target_skill.strip()}** is now live."
        )
        st.balloons()


def render_candidate_shortlist(students_df: pd.DataFrame,
                               jobs_df: pd.DataFrame) -> None:
    """
    'Candidate Auto-Shortlist' section.
    Select a job, then show all students with readiness score >= 60%.
    """
    st.markdown("### 🎯 Candidate Auto-Shortlist")
    st.markdown(
        "<p style='color:#94a3b8; font-size:0.9rem;'>"
        "Select a job role to instantly find qualified candidates "
        f"(readiness ≥ {SHORTLIST_THRESHOLD}%).</p>",
        unsafe_allow_html=True,
    )

    # Reload jobs fresh (in case one was just posted)
    fresh_jobs_df = load_jobs()
    job_roles = fresh_jobs_df["Job_Role"].tolist()

    if not job_roles:
        st.info("No job roles in the database yet. Post one above first!")
        return

    selected_role = st.selectbox(
        "Select a Job Role",
        options=job_roles,
        help="Choose a role to find matching candidates.",
    )

    if not selected_role:
        return

    # Find the job row for the selected role
    job_matches = fresh_jobs_df[
        fresh_jobs_df["Job_Role"].str.strip().str.lower()
        == selected_role.strip().lower()
    ]
    if job_matches.empty:
        st.warning("Selected role not found in database.")
        return

    job_row = job_matches.iloc[0]

    # Calculate readiness score for every student against the selected job
    req_tech = job_row["Required_Technical_Skills_List"]
    req_soft = job_row["Required_Soft_Skills_List"]

    shortlist_rows = []
    for _, student_row in students_df.iterrows():
        # Build skill maps for case-insensitive comparison
        stu_tech = {s.lower().strip() for s in student_row["Technical_Skills_List"]}
        stu_soft = {s.lower().strip() for s in student_row["Soft_Skills_List"]}

        matched_tech = [s for s in req_tech if s.lower().strip() in stu_tech]
        matched_soft = [s for s in req_soft if s.lower().strip() in stu_soft]

        total_required = len(req_tech) + len(req_soft)
        total_matched  = len(matched_tech) + len(matched_soft)
        score = round((total_matched / total_required) * 100, 1) if total_required else 0.0

        if score >= SHORTLIST_THRESHOLD:
            shortlist_rows.append({
                "Student ID":          student_row["Student_ID"],
                "Name":                student_row["Name"],
                "Degree":              student_row["Degree"],
                "Technical Skills":    student_row["Technical_Skills"],
                "Soft Skills":         student_row["Soft_Skills"],
                "Job Readiness Score": f"{score:.1f}%",
            })

    if shortlist_rows:
        st.markdown(
            f"<div style='background:#14532d; border-left:4px solid #22c55e; "
            "border-radius:8px; padding:12px 16px; margin-bottom:12px;'>"
            f"<p style='color:#bbf7d0; margin:0; font-size:0.9rem;'>"
            f"🎉 Found <strong>{len(shortlist_rows)}</strong> candidate(s) "
            f"with readiness ≥ {SHORTLIST_THRESHOLD}% for "
            f"<strong>{selected_role}</strong></p>"
            "</div>",
            unsafe_allow_html=True,
        )
        shortlist_df = pd.DataFrame(shortlist_rows)
        st.dataframe(
            shortlist_df,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning(
            f"⚠️ No candidates found with readiness ≥ {SHORTLIST_THRESHOLD}% "
            f"for **{selected_role}**."
        )


# ──────────────────────────────────────────────────────────────
#  STUDENT PORTAL — FULL VIEW
# ──────────────────────────────────────────────────────────────

def run_student_portal(students_df: pd.DataFrame,
                       jobs_df: pd.DataFrame,
                       user_id: Optional[str] = None) -> None:
    """Render the complete Student Portal (original app behaviour)."""
    # Sidebar controls — pass user_id so logged-in students skip the dropdown
    student_row = render_student_sidebar(students_df, user_id=user_id)

    # Main page header
    st.markdown(
        "<h1 style='font-size:2.4rem; font-weight:800; margin-bottom:0;'>"
        "🚀 SkillSync Dashboard</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color:#94a3b8; font-size:1rem; margin-top:4px; margin-bottom:0;'>"
        "Bridging Skills. Building Futures.</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    # Section 1: Student info cards
    render_student_header(student_row)
    st.markdown("<br>", unsafe_allow_html=True)

    # Run matching engine
    result = analyse_student(student_row, jobs_df)

    if result is None:
        st.warning(
            f"⚠️ No job profile found for '{student_row['Target_Job_Role']}' "
            "in industry_jobs.csv. Please add the role to the database."
        )
        st.stop()

    # ── Upsert a Pending approval row if gaps exist ────────
    has_gaps = bool(result.gap_technical or result.gap_soft)
    if has_gaps and user_id is not None:
        approvals_df = load_approvals()
        existing = approvals_df[
            (approvals_df["Student_ID"] == str(user_id))
            & (approvals_df["Target_Role"].str.strip().str.lower()
               == result.target_job.strip().lower())
        ]
        if existing.empty:
            new_row = pd.DataFrame([{
                "Student_ID":      str(user_id),
                "Target_Role":     result.target_job,
                "Course_Link":     result.training_link,
                "Approval_Status": "Pending",
                "Teacher_Score":   "0",
            }])
            approvals_df = pd.concat([approvals_df, new_row], ignore_index=True)
            save_approvals(approvals_df)

    # Section 2: Readiness score + progress bar
    render_readiness_score(result)
    st.markdown("<br>", unsafe_allow_html=True)

    # Section 3: Skill analysis (matched + gaps)
    render_skill_analysis(result)
    st.markdown("<br>", unsafe_allow_html=True)

    # Section 4: Training CTA (with approval-aware rendering)
    render_training_cta(result, student_id=user_id)


# ──────────────────────────────────────────────────────────────
#  INDUSTRY PORTAL — FULL VIEW
# ──────────────────────────────────────────────────────────────

def run_industry_portal(students_df: pd.DataFrame,
                        jobs_df: pd.DataFrame) -> None:
    """Render the complete Industry Partner Portal."""
    # Sidebar branding
    with st.sidebar:
        st.divider()
        st.markdown(
            "<p style='color:#94a3b8; font-size:0.85rem; text-align:center;'>"
            "Manage job postings, publish training programs, "
            "and discover qualified candidates.</p>",
            unsafe_allow_html=True,
        )
        st.divider()
        st.caption("🚀 SkillSync")
        st.caption("Bridging Skills. Building Futures.")

    # Main content
    render_industry_header()

    # ── Section 1: Post a New Opportunity ──────────────────
    render_post_opportunity()
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Section 2: Publish Upskilling Program ──────────────
    render_publish_upskilling()
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Section 3: Candidate Auto-Shortlist ────────────────
    render_candidate_shortlist(students_df, jobs_df)


# ──────────────────────────────────────────────────────────────
#  ACADEMICIAN PORTAL — FULL VIEW
# ──────────────────────────────────────────────────────────────

def run_academician_portal(students_df: pd.DataFrame,
                           jobs_df: pd.DataFrame) -> None:
    """Render the complete Academician / Institution Portal."""
    # Sidebar branding
    with st.sidebar:
        st.divider()
        st.markdown(
            "<p style='color:#94a3b8; font-size:0.85rem; text-align:center;'>"
            "Explore student analytics and faculty development "
            "opportunities for your institution.</p>",
            unsafe_allow_html=True,
        )
        st.divider()
        st.caption("🚀 SkillSync")
        st.caption("Bridging Skills. Building Futures.")

    # ── Page header ────────────────────────────────────────
    st.markdown(
        "<h1 style='font-size:2.4rem; font-weight:800; margin-bottom:0;'>"
        "🏫 Institution &amp; Faculty Dashboard</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color:#94a3b8; font-size:1rem; margin-top:4px; margin-bottom:0;'>"
        "Student analytics and faculty development at a glance</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Tabs ───────────────────────────────────────────────
    tab_analytics, tab_fdp, tab_approvals, tab_hitl = st.tabs(
        ["📊 Student Analytics", "🎓 Faculty Development (FDP)", "✅ Course Approvals", "⏳ Pending Skill Approvals"]
    )

    # ────────────────────────────────────────────────────────
    #  TAB 1: Student Analytics
    # ────────────────────────────────────────────────────────
    with tab_analytics:
        st.markdown("### 📈 Student Overview")

        # ── Top-level metrics ──────────────────────────────
        total_students = len(students_df)

        # Most popular target role
        role_counts = students_df["Target_Job_Role"].value_counts()
        most_popular_role = role_counts.idxmax() if not role_counts.empty else "N/A"

        # Average Skill Gap (mocked)
        avg_skill_gap = "34%"

        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(
                "<div style='background:#1e293b; border-radius:12px; padding:20px; text-align:center;'>"
                "<p style='color:#94a3b8; margin:0; font-size:0.8rem; text-transform:uppercase; "
                "letter-spacing:0.08em;'>Total Students Registered</p>"
                f"<p style='color:#60a5fa; margin:8px 0 0; font-size:2.4rem; font-weight:900;'>{total_students}</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        with m2:
            st.markdown(
                "<div style='background:#1e293b; border-radius:12px; padding:20px; text-align:center;'>"
                "<p style='color:#94a3b8; margin:0; font-size:0.8rem; text-transform:uppercase; "
                "letter-spacing:0.08em;'>Most Popular Target Job</p>"
                f"<p style='color:#34d399; margin:8px 0 0; font-size:1.6rem; font-weight:900;'>{most_popular_role}</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        with m3:
            st.markdown(
                "<div style='background:#1e293b; border-radius:12px; padding:20px; text-align:center;'>"
                "<p style='color:#94a3b8; margin:0; font-size:0.8rem; text-transform:uppercase; "
                "letter-spacing:0.08em;'>Average Skill Gap</p>"
                f"<p style='color:#fbbf24; margin:8px 0 0; font-size:2.4rem; font-weight:900;'>{avg_skill_gap}</p>"
                "</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Bar chart: students per target role ────────────
        st.markdown("### 🎯 Students per Target Job Role")
        st.markdown(
            "<p style='color:#94a3b8; font-size:0.9rem;'>"
            "Distribution of career aspirations across enrolled students.</p>",
            unsafe_allow_html=True,
        )

        chart_data = role_counts.rename_axis("Target Job Role").reset_index(name="Student Count")
        chart_data = chart_data.set_index("Target Job Role")
        st.bar_chart(chart_data, color="#60a5fa")
# ── Detailed Student Monitor ───────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 🔍 Detailed Student Progress Monitor")
        st.markdown(
            "<p style='color:#94a3b8; font-size:0.9rem;'>"
            "Search, filter, and monitor individual student skill profiles and target roles.</p>",
            unsafe_allow_html=True,
        )

        # Display as a highly interactive, searchable table
        st.dataframe(
            students_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Student_ID": st.column_config.TextColumn("ID", width="small"),
                "Name": st.column_config.TextColumn("Student Name"),
                "Degree": st.column_config.TextColumn("Program/Degree"),
                "Target_Job_Role": st.column_config.TextColumn("Career Goal"),
                "Technical_Skills": st.column_config.TextColumn("Current Tech Skills"),
                "Soft_Skills": st.column_config.TextColumn("Soft Skills"),
                "Technical_Skills_List": None,  # Hide the background AI lists
                "Soft_Skills_List": None
            }
        )
        # ── Individual Student Deep Dive ───────────────────
        st.markdown("---")
        st.markdown("### 🔬 Individual Student Deep Dive")
        st.markdown(
            "<p style='color:#94a3b8; font-size:0.9rem;'>"
            "Select a student ID to view their complete SkillSync readiness report.</p>",
            unsafe_allow_html=True,
        )

        # Dropdown to select a specific student
        student_list = ["-- Select a Student --"] + students_df["Student_ID"].tolist()
        selected_sid = st.selectbox("Search Student by ID", options=student_list, label_visibility="collapsed")

        if selected_sid != "-- Select a Student --":
            # Grab the specific student's data
            target_student = students_df[students_df["Student_ID"] == selected_sid].iloc[0]
            
            st.info(f"Viewing report for: **{target_student['Name']}** ({target_student['Degree']} ➡️ {target_student['Target_Job_Role']})")
            
            # Run the matching engine just like in the student portal
            result = analyse_student(target_student, jobs_df)
            
            if result is None:
                st.warning(f"⚠️ No job profile found for '{target_student['Target_Job_Role']}' in the database yet.")
            else:
                # Reuse the exact UI components from the Student Portal!
                render_readiness_score(result)
                st.markdown("<br>", unsafe_allow_html=True)
                render_skill_analysis(result)  
        

      
    # ────────────────────────────────────────────────────────
    #  TAB 2: Faculty Development (FDP)
    # ────────────────────────────────────────────────────────
    with tab_fdp:
        st.markdown("### 🧑‍🏫 Industry Opportunities for Academicians")
        st.markdown(
            "<p style='color:#94a3b8; font-size:0.9rem;'>"
            "Explore curated Faculty Development Programs (FDPs) from leading "
            "industry partners to upskill and stay current.</p>",
            unsafe_allow_html=True,
        )

        # Hardcoded FDP catalog
        fdp_programs = {
            "Google Cloud for Educators": {
                "provider":    "Google",
                "duration":    "6 weeks (self-paced)",
                "description": "Hands-on labs covering Cloud Computing, BigQuery, "
                               "and Vertex AI — designed specifically for university "
                               "faculty who want to integrate GCP into their curriculum.",
                "link":        "https://cloud.google.com/edu",
            },
            "TCS Corporate Faculty Internship": {
                "provider":    "Tata Consultancy Services",
                "duration":    "4 weeks (on-site / hybrid)",
                "description": "An immersive industry internship for faculty members "
                               "covering Agile methodologies, DevOps pipelines, and "
                               "enterprise software engineering practices.",
                "link":        "https://www.tcs.com/faculty-internship",
            },
            "AI in Modern Curriculum Workshop": {
                "provider":    "NASSCOM & Microsoft",
                "duration":    "3-day intensive workshop",
                "description": "Learn to design AI/ML course modules using Azure AI "
                               "services, responsible AI principles, and real-world "
                               "case studies suitable for undergraduate curricula.",
                "link":        "https://nasscom.in/ai-curriculum",
            },
        }

        for title, details in fdp_programs.items():
            with st.container():
                st.markdown(
                    f"<div style='background:#1e293b; border-left:4px solid #818cf8; "
                    "border-radius:8px; padding:16px 20px; margin-bottom:6px;'>"
                    f"<p style='color:#f1f5f9; font-size:1.15rem; font-weight:700; margin:0;'>"
                    f"📘 {title}</p>"
                    f"<p style='color:#94a3b8; margin:6px 0 2px; font-size:0.85rem;'>"
                    f"<strong>Provider:</strong> {details['provider']}  &nbsp;|&nbsp;  "
                    f"<strong>Duration:</strong> {details['duration']}</p>"
                    f"<p style='color:#cbd5e1; margin:4px 0 0; font-size:0.9rem;'>"
                    f"{details['description']}</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.link_button(
                    label=f"🚀 Apply Now — {title}",
                    url=details["link"],
                    type="primary",
                    use_container_width=True,
                )
                st.markdown("<br>", unsafe_allow_html=True)

    # ────────────────────────────────────────────────────────
    #  TAB 3: Course Approvals — Faculty Mentorship & Scoring
    # ────────────────────────────────────────────────────────
    with tab_approvals:
        st.markdown("### ✅ Faculty Mentorship & Course Scoring")
        st.markdown(
            "<p style='color:#94a3b8; font-size:0.9rem;'>"
            "Review AI-recommended courses for your students. Read the course "
            "summary, expand for full details, then score each recommendation "
            "from 1 (Least Recommended) to 5 (Most Important).</p>",
            unsafe_allow_html=True,
        )

        approvals_df = load_approvals()

        if approvals_df.empty:
            st.info("📭 No course recommendations to review yet. "
                    "They will appear here once students log in and receive suggestions.")
        else:
            # ── Summary metrics ────────────────────────────
            scored_mask = approvals_df["Teacher_Score"].apply(
                lambda x: int(x) > 0 if str(x).isdigit() else False
            )
            pending_count = (~scored_mask).sum()
            scored_count  = scored_mask.sum()

            mc1, mc2 = st.columns(2)
            mc1.metric("⏳ Pending Review", int(pending_count))
            mc2.metric("✅ Scored",         int(scored_count))
            st.markdown("---")

            # ── Iterate over all recommendations ───────────
            for idx, row in approvals_df.iterrows():
                target_role  = str(row["Target_Role"])
                student_id   = str(row["Student_ID"])
                course_link  = str(row["Course_Link"])
                current_score_str = str(row.get("Teacher_Score", "0"))
                current_score = int(current_score_str) if current_score_str.isdigit() else 0

                # Fetch mock course info
                course_info = _get_course_info(target_role)

                # Status indicator
                if current_score > 0:
                    status_pill = (
                        f"<span style='background:#14532d; color:#bbf7d0; "
                        "border-radius:12px; padding:3px 10px; font-size:0.75rem; "
                        f"font-weight:700;'>Score: {current_score}/5</span>"
                    )
                else:
                    status_pill = (
                        "<span style='background:#92400e; color:#fde68a; "
                        "border-radius:12px; padding:3px 10px; font-size:0.75rem; "
                        "font-weight:700;'>⏳ Pending</span>"
                    )

                # Card header
                st.markdown(
                    f"<div style='background:#1e293b; border-left:4px solid #818cf8; "
                    "border-radius:8px; padding:16px 20px; margin-bottom:4px;'>"
                    f"<p style='color:#f1f5f9; font-weight:700; margin:0; font-size:1.1rem;'>"
                    f"🎓 {student_id} → {target_role} &nbsp;{status_pill}</p>"
                    f"<p style='color:#94a3b8; margin:8px 0 4px; font-size:0.85rem;'>"
                    f"Course: <a href='{course_link}' target='_blank' "
                    f"style='color:#60a5fa;'>{course_link}</a></p>"
                    f"<p style='color:#cbd5e1; margin:6px 0 0; font-size:0.9rem;'>"
                    f"<strong>Summary:</strong> {course_info['summary']}</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )

                # Expander with full details
                with st.expander("📖 View In-Depth Details", expanded=False):
                    st.markdown(
                        f"<p style='color:#e2e8f0; font-size:0.9rem; line-height:1.7;'>"
                        f"{course_info['details']}</p>",
                        unsafe_allow_html=True,
                    )

                # Scoring controls
                score_options = [
                    f"{k} — {v}" for k, v in TEACHER_SCORE_LABELS.items()
                ]
                # Determine default index
                default_idx = (current_score - 1) if current_score >= 1 else 0

                col_score, col_save = st.columns([3, 1])
                with col_score:
                    selected = st.selectbox(
                        "Score this course",
                        options=score_options,
                        index=default_idx,
                        key=f"score_select_{idx}",
                        label_visibility="collapsed",
                    )
                with col_save:
                    if st.button(
                        "💾 Save Score",
                        key=f"save_score_{idx}",
                        type="primary",
                        use_container_width=True,
                    ):
                        # Parse the selected score (first char)
                        new_score = int(selected.split(" — ")[0])
                        approvals_df.at[idx, "Teacher_Score"] = str(new_score)
                        approvals_df.at[idx, "Approval_Status"] = "Scored"
                        save_approvals(approvals_df)
                        st.success(
                            f"Saved score **{new_score}** for "
                            f"**{student_id}** ({target_role})."
                        )
                        st.rerun()

                st.markdown("<br>", unsafe_allow_html=True)

            # ── Full history table ─────────────────────────
            st.markdown("---")
            st.markdown("### 📋 All Scoring Records")

            # Add a human-readable label column for display
            display_df = approvals_df.copy()
            display_df["Score_Label"] = display_df["Teacher_Score"].apply(
                lambda x: TEACHER_SCORE_LABELS.get(int(x), "Pending")
                if str(x).isdigit() and int(x) > 0 else "Pending Review"
            )
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Student_ID":      st.column_config.TextColumn("Student ID", width="small"),
                    "Target_Role":     st.column_config.TextColumn("Target Role"),
                    "Course_Link":     st.column_config.LinkColumn("Course Link", display_text="Open"),
                    "Approval_Status": st.column_config.TextColumn("Status"),
                    "Teacher_Score":   st.column_config.TextColumn("Score", width="small"),
                    "Score_Label":     st.column_config.TextColumn("Score Label"),
                },
            )
    # ────────────────────────────────────────────────────────
    #  TAB 4: Pending Skill Approvals (HITL)
    # ────────────────────────────────────────────────────────
    with tab_hitl:
        st.markdown("### ⏳ Pending Skill Approvals")
        st.markdown(
            "<p style='color:#94a3b8; font-size:0.9rem;'>"
            "Review recently registered students. Check their proof of skills and approve them.</p>",
            unsafe_allow_html=True,
        )
        
        pending_students = db.get_pending_students()
        
        if not pending_students:
            st.info("No pending students to approve.")
        else:
            for p_student in pending_students:
                with st.container():
                    st.markdown(
                        f"<div style='background:#1e293b; border-left:4px solid #f59e0b; "
                        "border-radius:8px; padding:16px 20px; margin-bottom:4px;'>"
                        f"<p style='color:#f1f5f9; font-weight:700; margin:0; font-size:1.1rem;'>"
                        f"🧑‍🎓 {p_student['name']} ({p_student['email']})</p>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    
                    metadata = json.loads(p_student['metadata_json'])
                    st.write(f"**Branch:** {metadata.get('branch', 'N/A')}")
                    st.write(f"**Year of Study:** {metadata.get('year', 'N/A')}")
                    st.write(f"**Target Role:** {metadata.get('target_role', 'N/A')}")
                    st.write(f"**Claimed Skills:** {', '.join(metadata.get('skills', []))}")
                    
                    if p_student['proof_path'] and os.path.exists(p_student['proof_path']):
                        with open(p_student['proof_path'], "rb") as file:
                            st.download_button(
                                label="📄 Download Proof",
                                data=file,
                                file_name=os.path.basename(p_student['proof_path']),
                                mime="application/octet-stream",
                                key=f"dl_proof_{p_student['id']}"
                            )
                    else:
                        st.warning("No proof file available or file missing.")
                        
                    if st.button("✅ Approve Credential", key=f"approve_{p_student['id']}", type="primary"):
                        db.approve_student(p_student['id'])
                        st.success(f"Approved {p_student['name']} successfully!")
                        st.rerun()
                    st.markdown("---")


# ──────────────────────────────────────────────────────────────
#  ROLE-TO-SKILL MATRIX ENGINE
# ──────────────────────────────────────────────────────────────

def get_role_skill_matrix(role_name: str) -> dict:
    """
    Map common target roles to their expected technical and soft skills.
    Includes a keyword-matching fallback for free-text inputs.
    """
    role_lower = role_name.lower().strip()
    
    # Predefined strict mappings
    matrix = {
        "data scientist": {
            "technical_skills": ["Python", "SQL", "Machine Learning", "Pandas", "Scikit-Learn", "TensorFlow / PyTorch", "Data Visualization", "Statistics"],
            "soft_skills": ["Problem Solving", "Analytical Thinking", "Data Storytelling", "Communication", "Business Acumen"]
        },
        "full stack developer": {
            "technical_skills": ["HTML/CSS", "JavaScript/TypeScript", "React / Angular", "Node.js / Django", "SQL / NoSQL", "Git", "REST APIs", "Docker"],
            "soft_skills": ["Agile & Scrum Collaboration", "Technical Problem Solving & Debugging Mindset", "Clear Communication & Code Documentation", "Time Management & Delivery"]
        },
        "cybersecurity analyst": {
            "technical_skills": ["Networking (TCP/IP)", "Linux", "Ethical Hacking", "SIEM Tools", "Cryptography", "Firewall Configuration", "Vulnerability Assessment"],
            "soft_skills": ["Critical Thinking", "Attention to Detail", "Risk Assessment", "Ethics and Integrity", "Incident Response Communication"]
        },
        "cloud / devops engineer": {
            "technical_skills": ["AWS / GCP / Azure", "Docker", "Kubernetes", "CI/CD (Jenkins/Actions)", "Linux/Bash", "Terraform", "Python / Go", "Networking"],
            "soft_skills": ["System Troubleshooting", "Cross-team Collaboration", "Process Automation Mindset", "Adaptability", "Clear Communication"]
        },
        "ai / ml engineer": {
            "technical_skills": ["Python", "TensorFlow / PyTorch", "Deep Learning", "NLP / Computer Vision", "Data Engineering (Spark)", "MLOps", "C++", "SQL"],
            "soft_skills": ["Complex Problem Solving", "Research Mindset", "Analytical Thinking", "Technical Communication", "Continuous Learning"]
        },
        "web developer": {
            "technical_skills": ["HTML/CSS", "JavaScript", "React / Vue", "Node.js", "SQL", "Git", "Responsive Design"],
            "soft_skills": ["User-Centric Thinking", "Collaboration", "Debugging Mindset", "Attention to Detail"]
        }
    }
    
    # Strict match check
    for key, value in matrix.items():
        if key == role_lower:
            return value
            
    # Substring matching fallback
    if "data" in role_lower or "analyst" in role_lower:
        return matrix["data scientist"]
    if "web" in role_lower or "front" in role_lower or "back" in role_lower or "stack" in role_lower:
        return matrix["full stack developer"]
    if "security" in role_lower or "cyber" in role_lower or "hack" in role_lower:
        return matrix["cybersecurity analyst"]
    if "cloud" in role_lower or "devops" in role_lower or "sysadmin" in role_lower:
        return matrix["cloud / devops engineer"]
    if "ai" in role_lower or "ml" in role_lower or "machine" in role_lower or "artificial" in role_lower:
        return matrix["ai / ml engineer"]
        
    # Broad default fallback
    return {
        "technical_skills": ["Python", "Java", "C++", "SQL", "Git", "Linux", "Cloud Basics (AWS/GCP)"],
        "soft_skills": ["Communication", "Teamwork", "Problem Solving", "Time Management", "Adaptability"]
    }

# ──────────────────────────────────────────────────────────────
#  AUTHENTICATION PAGE (Login & Register)
# ──────────────────────────────────────────────────────────────

def render_auth_page() -> None:
    """
    Display the Auth page with Login and Register tabs.
    """
    st.image("assests/skillsync_banner.jpg", use_container_width=True)

    _col_left, col_mid, _col_right = st.columns([1, 2, 1])

    with col_mid:
        tab_login, tab_register = st.tabs(["🔑 Login", "📝 Register"])

        with tab_login:
            st.markdown(
                "<p style='text-align:center; color:#94a3b8; font-size:1rem; "
                "margin-top:12px; margin-bottom:28px;'>"
                "Sign in to access your personalised dashboard</p>",
                unsafe_allow_html=True,
            )
            with st.form("login_form"):
                email = st.text_input("Email", placeholder="e.g. S001@example.com, HR01@company.com")
                password = st.text_input("Password", type="password", placeholder="Enter your password")
                submitted = st.form_submit_button("🔐 Login", type="primary", use_container_width=True)

            if submitted:
                if not email.strip() or not password.strip():
                    st.error("❌ Please enter both Email and Password.")
                else:
                    # Fallback for mock credentials from CSV (for backward compatibility)
                    creds = load_credentials()
                    match = creds[
                        (creds["User_ID"].str.strip() == email.strip())
                        & (creds["Password"].str.strip() == password.strip())
                    ]
                    
                    user_data = None
                    role = None
                    user_id = None
                    
                    if not match.empty:
                        role = match.iloc[0]["Role"]
                        user_id = match.iloc[0]["User_ID"]
                        user_data = {"status": "APPROVED", "name": user_id, "email": email}
                    else:
                        # Check SQLite Database
                        user = db.authenticate_user(email.strip(), password)
                        if user:
                            role = user['role']
                            user_id = user['id']
                            user_data = user
                    
                    if user_data:
                        st.session_state.logged_in = True
                        st.session_state.user_id = str(user_id)
                        st.session_state.role = role
                        st.session_state.user_data = user_data
                        st.rerun()
                    else:
                        st.error("❌ Invalid Email or Password. Please try again.")

        with tab_register:
            role = st.radio("Select Role", ["Student", "Teacher", "HR"], horizontal=True)
            
            if role == "Student":
                if "reg_step" not in st.session_state:
                    st.session_state.reg_step = 1
                if "reg_data" not in st.session_state:
                    st.session_state.reg_data = {}
                    
                step = st.session_state.reg_step
                
                if step == 1:
                    st.markdown("### Step 1: Basic Information & Target Role")
                    with st.form("reg_step_1"):
                        name = st.text_input("Full Name", value=st.session_state.reg_data.get("name", ""))
                        email = st.text_input("Email", value=st.session_state.reg_data.get("email", ""))
                        password = st.text_input("Password", type="password", value=st.session_state.reg_data.get("password", ""))
                        confirm_password = st.text_input("Confirm Password", type="password", value=st.session_state.reg_data.get("confirm_password", ""))
                        branch = st.text_input("Branch", value=st.session_state.reg_data.get("branch", ""))
                        
                        year_opts = ["1st Year", "2nd Year", "3rd Year", "4th Year"]
                        current_year = st.session_state.reg_data.get("year", "1st Year")
                        year_idx = year_opts.index(current_year) if current_year in year_opts else 0
                        year = st.selectbox("Year of Study", year_opts, index=year_idx)
                        
                        target_role = st.text_input("Target Job Role (e.g. Data Scientist, Web Developer)", value=st.session_state.reg_data.get("target_role", ""))
                        
                        submitted = st.form_submit_button("🔍 Analyze Career Path & Select Skills", type="primary")
                        
                        if submitted:
                            if not name or not email or not password or not confirm_password or not target_role:
                                st.error("❌ Please fill in all fields.")
                            elif password != confirm_password:
                                st.error("❌ Passwords do not match.")
                            else:
                                st.session_state.reg_data.update({
                                    "name": name,
                                    "email": email,
                                    "password": password,
                                    "confirm_password": confirm_password,
                                    "branch": branch,
                                    "year": year,
                                    "target_role": target_role
                                })
                                st.session_state.reg_step = 2
                                st.rerun()
                                
                elif step == 2:
                    st.markdown("### Step 2: Technical Skills Checklist")
                    target_role = st.session_state.reg_data.get("target_role", "")
                    st.info(f"Based on your target role **{target_role}**, we've identified key technical skills.")
                    
                    matrix = get_role_skill_matrix(target_role)
                    tech_skills = matrix["technical_skills"]
                    
                    is_none = st.checkbox("⚪ I am a beginner / I do not have any of these skills yet (None)", 
                                          value=st.session_state.reg_data.get("tech_none", False))
                    
                    selected_tech = []
                    if is_none:
                        st.session_state.reg_data["tech_none"] = True
                        for skill in tech_skills:
                            st.checkbox(skill, value=False, disabled=True)
                    else:
                        st.session_state.reg_data["tech_none"] = False
                        prev_tech = st.session_state.reg_data.get("tech_skills", [])
                        for skill in tech_skills:
                            val = st.checkbox(skill, value=skill in prev_tech)
                            if val:
                                selected_tech.append(skill)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("⬅️ Back"):
                            st.session_state.reg_step = 1
                            st.rerun()
                    with col2:
                        if st.button("Proceed to Soft Skills ➔", type="primary"):
                            st.session_state.reg_data["tech_skills"] = [] if is_none else selected_tech
                            st.session_state.reg_step = 3
                            st.rerun()
                            
                elif step == 3:
                    st.markdown("### Step 3: Soft Skills Checklist")
                    target_role = st.session_state.reg_data.get("target_role", "")
                    matrix = get_role_skill_matrix(target_role)
                    soft_skills_list = matrix["soft_skills"]
                    
                    selected_soft = []
                    prev_soft = st.session_state.reg_data.get("soft_skills", [])
                    for skill in soft_skills_list:
                        val = st.checkbox(skill, value=skill in prev_soft)
                        if val:
                            selected_soft.append(skill)
                            
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("⬅️ Back"):
                            st.session_state.reg_step = 2
                            st.rerun()
                    with col2:
                        if st.button("Proceed to Document Upload ➔", type="primary"):
                            st.session_state.reg_data["soft_skills"] = selected_soft
                            st.session_state.reg_step = 4
                            st.rerun()
                            
                elif step == 4:
                    st.markdown("### Step 4: Verification Document Upload")
                    is_none = st.session_state.reg_data.get("tech_none", False)
                    
                    if is_none:
                        st.info("Since you marked yourself as a beginner, uploading a certificate is OPTIONAL.")
                        proof_file = st.file_uploader("Skill Verification (Certificates/Drive Link) [PDF/Image]", type=['pdf', 'png', 'jpg', 'jpeg'])
                    else:
                        st.warning("You've claimed technical skills. Uploading proof is REQUIRED.")
                        proof_file = st.file_uploader("Skill Verification (Certificates/Drive Link) [PDF/Image]", type=['pdf', 'png', 'jpg', 'jpeg'])
                        
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("⬅️ Back"):
                            st.session_state.reg_step = 3
                            st.rerun()
                    with col2:
                        if st.button("🚀 Complete Registration", type="primary"):
                            if not is_none and not proof_file:
                                st.error("❌ Please upload a proof file to verify your skills.")
                            else:
                                proof_path = None
                                if proof_file:
                                    uploads_dir = os.path.join(DATA_DIR, "uploads")
                                    os.makedirs(uploads_dir, exist_ok=True)
                                    proof_path = os.path.join(uploads_dir, proof_file.name)
                                    with open(proof_path, "wb") as f:
                                        f.write(proof_file.getbuffer())
                                
                                reg_data = st.session_state.reg_data
                                metadata = {
                                    "branch": reg_data["branch"],
                                    "year": reg_data["year"],
                                    "target_role": reg_data["target_role"],
                                    "skills": reg_data.get("tech_skills", []) + reg_data.get("soft_skills", [])
                                }
                                success = db.register_user(reg_data["name"], reg_data["email"], reg_data["password"], "Student", metadata, proof_path)
                                if success:
                                    st.success("✅ Profile submitted! Your credentials and claimed skills are currently pending Human-in-the-Loop verification by the Faculty Mentorship board.")
                                    # Reset state
                                    del st.session_state.reg_step
                                    del st.session_state.reg_data
                                else:
                                    st.error("❌ Email already exists.")
                                    
            else:
                # Teacher or HR
                with st.form("register_form", clear_on_submit=True):
                    name = st.text_input("Full Name")
                    email = st.text_input("Email")
                    password = st.text_input("Password", type="password")
                    confirm_password = st.text_input("Confirm Password", type="password")
                    
                    metadata = {}
                    
                    if role == "Teacher":
                        department = st.text_input("Department")
                        faculty_id = st.text_input("Faculty ID")
                        specialization = st.text_input("Specialization")
                    elif role == "HR":
                        company = st.text_input("Company Name")
                        designation = st.text_input("Designation")
                        hiring_stack = st.text_input("Hiring Tech Stack (comma separated)")
                    
                    submitted = st.form_submit_button("📝 Register", type="primary", use_container_width=True)
                
                if submitted:
                    if not name or not email or not password or not confirm_password:
                        st.error("❌ Please fill in all standard fields.")
                    elif password != confirm_password:
                        st.error("❌ Passwords do not match.")
                    else:
                        if role == "Teacher":
                            metadata = {
                                "department": department,
                                "faculty_id": faculty_id,
                                "specialization": specialization
                            }
                            role_str = "Academician"
                        elif role == "HR":
                            metadata = {
                                "company": company,
                                "designation": designation,
                                "hiring_stack": hiring_stack
                            }
                            role_str = "Industry"
                            
                        success = db.register_user(name, email, password, role_str, metadata)
                        if success:
                            st.success("✅ Registration successful! You can now log in.")
                        else:
                            st.error("❌ Email already exists.")

# ──────────────────────────────────────────────────────────────
#  MAIN APP
# ──────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="SkillSync",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    db.init_db()
    setup_credentials()

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.markdown(
            "<style>[data-testid='stSidebar']{display:none;}</style>",
            unsafe_allow_html=True,
        )
        render_auth_page()
        return
        
    user_data = st.session_state.get("user_data", {})
    if user_data.get("status") == "PENDING":
        st.markdown("<style>[data-testid='stSidebar']{display:none;}</style>", unsafe_allow_html=True)
        st.warning("⏳ Application Submitted: Awaiting Faculty Mentorship Verification...")
        st.info("Your credentials and proof documents have been routed to the Faculty Verification Queue.")
        
        # Check current status in DB to auto-sync
        current_db_user = db.get_user_by_id(user_data["id"])
        if current_db_user and current_db_user["status"] == "APPROVED":
            st.session_state.user_data["status"] = "APPROVED"
            st.toast("🎉 Profile Approved by Faculty!", icon="✅")
            st.rerun()
            
        if st.button("🔄 Check Verification Status", use_container_width=True):
            st.rerun()
            
        if st.button("🚪 Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
            
        import time
        time.sleep(3)
        st.rerun()
        return

    role    = st.session_state.role
    user_id = st.session_state.user_id

    students_df = _safe_load(load_students, "Student Data")
    jobs_df     = _safe_load(load_jobs,     "Industry Jobs")
    if students_df is None or jobs_df is None:
        st.stop()
        
    # Inject newly registered approved student into students_df
    if role == "Student" and user_id.isdigit():
        metadata = json.loads(user_data.get("metadata_json", "{}"))
        tech_skills = metadata.get("skills", [])
        new_row = {
            "Student_ID": str(user_id),
            "Name": user_data.get("name", "Student"),
            "Degree": f"{metadata.get('branch', 'N/A')} - {metadata.get('year', 'N/A')}",
            "Target_Job_Role": metadata.get("target_role", "Software Engineer"), 
            "Technical_Skills": ", ".join(tech_skills),
            "Soft_Skills": "Communication, Teamwork",
            "Technical_Skills_List": tech_skills,
            "Soft_Skills_List": ["Communication", "Teamwork"]
        }
        students_df = pd.concat([students_df, pd.DataFrame([new_row])], ignore_index=True)

    with st.sidebar:
        st.markdown(
            "<h1 style='text-align:center; font-size:1.6rem;'>"
            "🚀 SkillSync</h1>",
            unsafe_allow_html=True,
        )
        name_display = user_data.get("name", user_id)
        st.markdown(
            f"<p style='text-align:center; color:#94a3b8; font-size:0.85rem;'>"
            f"Logged in as <strong style='color:#f1f5f9;'>{name_display}</strong>"
            f" &nbsp;|&nbsp; Role: <strong style='color:#f1f5f9;'>{role}</strong></p>",
            unsafe_allow_html=True,
        )

    if role == "Student":
        run_student_portal(students_df, jobs_df, user_id=str(user_id))
    elif role == "Industry":
        run_industry_portal(students_df, jobs_df)
    elif role == "Academician":
        run_academician_portal(students_df, jobs_df)
    else:
        st.error(f"Unknown role: **{role}**")

    with st.sidebar:
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

if __name__ == "__main__":
    main()
