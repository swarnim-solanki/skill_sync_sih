"""
matcher.py - Core Skill Matching Engine
=========================================
Compares a student's skills against a target job's requirements and
produces a structured MatchResult containing:
  matched_technical  : skills the student HAS that the job REQUIRES
  gap_technical      : skills the job REQUIRES that the student LACKS
  matched_soft       : same logic for soft skills
  gap_soft           : same logic for soft skills
  readiness_score    : percentage of total required skills that are matched
  training_link      : recommended training URL from industry_jobs.csv

All skill comparisons are CASE-INSENSITIVE but the original casing is
preserved in the output for clean display in the UI.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd


# ─────────────────────────────────────────────────────────
#  RESULT DATACLASS
# ─────────────────────────────────────────────────────────

@dataclass
class MatchResult:
    """Holds every output produced by the matching engine for one student."""

    student_name:      str
    target_job:        str

    # Technical skill breakdown
    matched_technical: list = field(default_factory=list)
    gap_technical:     list = field(default_factory=list)

    # Soft skill breakdown
    matched_soft:      list = field(default_factory=list)
    gap_soft:          list = field(default_factory=list)

    # Scoring
    readiness_score:   float = 0.0     # 0.0 to 100.0
    training_link:     str   = ""

    @property
    def total_required_technical(self) -> int:
        return len(self.matched_technical) + len(self.gap_technical)

    @property
    def total_required_soft(self) -> int:
        return len(self.matched_soft) + len(self.gap_soft)

    @property
    def score_label(self) -> str:
        """Human-readable readiness band for UI display."""
        s = self.readiness_score
        if s >= 80:
            return "Job-Ready"
        elif s >= 50:
            return "Partially Ready"
        else:
            return "Needs Training"

    @property
    def score_color(self) -> str:
        """Streamlit metric delta_color or badge color."""
        s = self.readiness_score
        if s >= 80:
            return "green"
        elif s >= 50:
            return "orange"
        else:
            return "red"


# ─────────────────────────────────────────────────────────
#  PRIVATE HELPERS
# ─────────────────────────────────────────────────────────

def _to_map(skill_list: list) -> dict:
    """
    Build {lowercase_key: original_casing} mapping from a skill list.
    Enables case-insensitive comparison while preserving display casing.

    Example:
        ["Python", "SQL", "NumPy"]
        returns {"python": "Python", "sql": "SQL", "numpy": "NumPy"}
    """
    return {s.lower().strip(): s.strip() for s in skill_list if s}


def _compare(student_skills: list, required_skills: list) -> tuple:
    """
    Compare two skill lists (case-insensitive).

    Returns:
        matched : skills student HAS that are in the required list
        gaps    : skills required that the student LACKS

    Casing in returned lists comes from the required list so output
    always reads consistently (job-spec language, not student free-text).
    """
    student_map  = _to_map(student_skills)
    required_map = _to_map(required_skills)

    matched = [required_map[key] for key in required_map if key in student_map]
    gaps    = [required_map[key] for key in required_map if key not in student_map]

    return matched, gaps


def _readiness_score(matched_tech: list, gap_tech: list,
                     matched_soft: list, gap_soft: list) -> float:
    """
    Calculate overall Job Readiness Score as a percentage.

    Formula:
        score = (matched_technical + matched_soft)
                ___________________________________ x 100
                (total_technical   + total_soft)

    Technical and soft skills are weighted equally.
    Returns 0.0 if no required skills exist (guards against ZeroDivisionError).
    """
    total_matched  = len(matched_tech) + len(matched_soft)
    total_required = (len(matched_tech) + len(gap_tech) +
                      len(matched_soft) + len(gap_soft))

    if total_required == 0:
        return 0.0

    return round((total_matched / total_required) * 100, 1)


# ─────────────────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────────────────

def analyse_student(student_row: pd.Series, jobs_df: pd.DataFrame):
    """
    Run the full skill-gap analysis for a single student.

    Steps:
        1. Look up the student's Target_Job_Role in jobs_df.
        2. Extract and compare Technical Skills (student vs job).
        3. Extract and compare Soft Skills (student vs job).
        4. Compute the Job Readiness Score.
        5. Pack everything into a MatchResult dataclass.

    Args:
        student_row : A single row from the students DataFrame (pd.Series).
        jobs_df     : The full industry jobs DataFrame.

    Returns:
        MatchResult if the job role is found, otherwise None.
    """
    target_role = str(student_row["Target_Job_Role"]).strip()

    # Step 1: look up the job row (case-insensitive match on Job_Role)
    job_matches = jobs_df[
        jobs_df["Job_Role"].str.strip().str.lower() == target_role.lower()
    ]

    if job_matches.empty:
        return None   # caller handles the role-not-found case

    job_row = job_matches.iloc[0]

    # Steps 2 & 3: compare technical and soft skills
    matched_tech, gap_tech = _compare(
        student_row["Technical_Skills_List"],
        job_row["Required_Technical_Skills_List"],
    )
    matched_soft, gap_soft = _compare(
        student_row["Soft_Skills_List"],
        job_row["Required_Soft_Skills_List"],
    )

    # Step 4: compute readiness score
    score = _readiness_score(matched_tech, gap_tech, matched_soft, gap_soft)

    # Step 5: assemble MatchResult
    return MatchResult(
        student_name      = str(student_row["Name"]),
        target_job        = target_role,
        matched_technical = matched_tech,
        gap_technical     = gap_tech,
        matched_soft      = matched_soft,
        gap_soft          = gap_soft,
        readiness_score   = score,
        training_link     = str(job_row["Recommended_Training_Link"]),
    )


def get_all_results(students_df: pd.DataFrame, jobs_df: pd.DataFrame) -> list:
    """
    Run analyse_student for every student in students_df.
    Skips students whose Target_Job_Role is not found in jobs_df.

    Returns:
        List of MatchResult objects (one per matched student).
    """
    results = []
    for _, row in students_df.iterrows():
        result = analyse_student(row, jobs_df)
        if result is not None:
            results.append(result)
    return results
