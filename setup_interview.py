"""
DIY Copilot — interview setup script.

Reads a prep markdown file and populates ~/.diycopilot/settings.json with:

  job_description  ← the "## Job Description" section from the prep doc
                     (what the role requires — DeepSeek tailors answers to it)

  resume           ← your existing CV  +  the rest of the prep doc appended
                     (your stories, scripted answers, key context for the AI)

Your API key, audio device, and all other settings are left untouched.

USAGE
-----
1. Explicit path (any markdown file, anywhere):
       python setup_interview.py path/to/prep.md

2. Auto-pick from ai-cs-system/docs/interview_*.md:
       python setup_interview.py
   • If exactly one interview_*.md exists → loads it automatically.
   • If multiple exist → shows a numbered menu so you can pick one.

PREP DOC FORMAT
---------------
Structure your interview_<company>.md like this:

    # Company Interview Prep

    ## Job Description
    <paste the actual JD here>

    ---

    ## About the Company
    ...rest of your prep notes...

The script splits on "## Job Description" — everything under that heading
(until the next ## heading or end of file) goes into job_description.
Everything else (the prep notes) is appended to your resume.

WORKFLOW FOR A NEW INTERVIEW
-----------------------------
1. Create ai-cs-system/docs/interview_<company>.md with the JD + your prep
2. Run:  python setup_interview.py
3. Run:  python main.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SETTINGS_PATH = Path.home() / ".diycopilot" / "settings.json"
DOCS_DIR = Path(__file__).parent / "ai-cs-system" / "docs"

# Heading that marks the start of the JD section in the prep doc
JD_HEADING = re.compile(r"^##\s+Job Description\s*$", re.IGNORECASE | re.MULTILINE)
# Any ## heading (to find where the JD section ends)
NEXT_HEADING = re.compile(r"^##\s+", re.MULTILINE)


# ── settings helpers ──────────────────────────────────────────────────────────

def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text())
        except Exception as exc:
            print(f"[warn] Could not parse existing settings: {exc}")
    return {}


def save_settings(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(SETTINGS_PATH, 0o600)
    except OSError:
        pass


# ── prep doc parsing ──────────────────────────────────────────────────────────

def split_prep_doc(content: str) -> tuple[str, str]:
    """
    Split the prep doc into (job_description, prep_notes).

    - job_description: the text under the "## Job Description" heading
    - prep_notes:      everything else (title + all other sections)

    If no "## Job Description" heading is found, job_description is empty
    and prep_notes is the full document.
    """
    match = JD_HEADING.search(content)
    if not match:
        return "", content

    jd_start = match.end()  # character after the heading line

    # Find the next ## heading after the JD section
    next_match = NEXT_HEADING.search(content, jd_start)
    if next_match:
        jd_text = content[jd_start:next_match.start()].strip()
        # prep_notes = everything before the JD heading + everything after it
        prep_notes = (content[:match.start()].rstrip() + "\n\n" +
                      content[next_match.start():]).strip()
    else:
        jd_text = content[jd_start:].strip()
        prep_notes = content[:match.start()].strip()

    return jd_text, prep_notes


# ── file discovery ────────────────────────────────────────────────────────────

def discover_interview_docs() -> list[Path]:
    """Return all interview_*.md files in the docs dir, sorted by name."""
    if not DOCS_DIR.exists():
        return []
    return sorted(DOCS_DIR.glob("interview_*.md"))


def pick_prep_file() -> Path | None:
    """
    Resolve which prep file to use:
    - If a path was passed on the command line, use that.
    - If exactly one interview_*.md exists in docs/, use it automatically.
    - If multiple exist, show a numbered menu.
    """
    if len(sys.argv) >= 2:
        p = Path(sys.argv[1])
        if not p.exists():
            print(f"Error: file not found: {p}")
            return None
        return p

    docs = discover_interview_docs()

    if not docs:
        print(f"No interview_*.md files found in {DOCS_DIR}")
        print("Either pass a path explicitly:")
        print("    python setup_interview.py path/to/prep.md")
        print("Or drop your prep doc into ai-cs-system/docs/ named interview_<company>.md")
        return None

    if len(docs) == 1:
        print(f"Auto-selected: {docs[0].name}")
        return docs[0]

    # Multiple files — show a menu
    print("Multiple interview prep docs found. Pick one:\n")
    for i, p in enumerate(docs, 1):
        print(f"  [{i}] {p.name}")
    print()
    while True:
        raw = input(f"Enter number (1–{len(docs)}): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(docs):
            return docs[int(raw) - 1]
        print(f"  Please enter a number between 1 and {len(docs)}.")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    prep_path = pick_prep_file()
    if prep_path is None:
        return 1

    content = prep_path.read_text(encoding="utf-8")
    jd_text, prep_notes = split_prep_doc(content)

    settings = load_settings()

    # Strip any previously injected prep notes from the resume so re-running
    # this script doesn't keep appending duplicates.
    PREP_SEPARATOR = "\n\n---\n\n## Interview Prep Notes\n\n"
    raw_resume = settings.get("resume", "").strip()
    if PREP_SEPARATOR in raw_resume:
        base_resume = raw_resume.split(PREP_SEPARATOR)[0].strip()
    else:
        base_resume = raw_resume

    # job_description = the actual JD (or full doc if no JD section found)
    if jd_text:
        settings["job_description"] = jd_text
    else:
        # No ## Job Description section — fall back to putting everything in JD
        settings["job_description"] = content
        prep_notes = ""

    # resume = base CV + fresh prep notes appended (separated clearly)
    if prep_notes:
        if base_resume:
            settings["resume"] = base_resume + PREP_SEPARATOR + prep_notes
        else:
            settings["resume"] = prep_notes
    else:
        # Restore clean resume (no prep notes)
        settings["resume"] = base_resume

    save_settings(settings)

    print(f"✓ Loaded prep from:  {prep_path}")
    print(f"✓ Settings updated:  {SETTINGS_PATH}")
    if jd_text:
        print(f"  job_description:   {len(jd_text)} chars  ← actual JD")
        print(f"  resume:            {len(settings['resume'])} chars  ← CV + prep notes")
    else:
        print(f"  job_description:   {len(content)} chars  ← full doc (no JD section found)")
        print( "  resume:            unchanged")
        print()
        print("  Tip: add a '## Job Description' section to your prep doc to split")
        print("  the JD and prep notes into the correct fields automatically.")
    print()
    print("DIY Copilot is ready. Run:  python main.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
