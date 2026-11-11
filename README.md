# Spectrum-Moodle-notebook-workflow
Automatically download moodle/spectrum files and upload to LM notebook and generate quiz and flashcards. For um students.

Here is a comprehensive, production-ready, and well-structured `README.md` written in English for your GitHub repository.

---

```markdown
# 🥔 Oh~ Potato~~ (哦~土豆~~) - UM SPeCTRUM Automation Suite

An all-in-one automation toolkit for University of Malaya (UM) students using the SPeCTRUM (Moodle) learning platform. 

This toolkit streamlines checking announcements, tracking assignment deadlines, auto-downloading course lecture notes/tutorials, and integrating lecture slides with **Google NotebookLM** to generate AI-powered weekly study quizzes and flashcards automatically.

---

## 📋 Features

- **🥔 Oh~ Potato~~ Launcher**: A clean, interactive terminal menu (or double-clickable `.bat` on Windows) to launch any tool instantly.
- **📰 SPeCTRUM Announcements**: View the latest 48-hour breaking news and forum discussions course-by-course; open links directly in your browser.
- **⏰ Deadlines Tracker**: Color-coded assignment & quiz tracker sorted by urgency. Supports hiding unwanted tasks and opening submission portals.
- **📥 Smart Slide Downloader**: Selectively downloads PPTs/PDFs/DOCXs, organizes lecture notes by week (e.g., L1/L2 $\rightarrow$ Week 1/2), and tracks file modifications to avoid duplicate downloads.
- **🧠 Google NotebookLM AI Pipeline**: Synchronizes weekly course materials to Google NotebookLM notebooks and auto-generates study quizzes and flashcards using custom prompts.

---

## 📂 Repository File Structure

Ensure your directory is arranged as follows:

```text
.
├── 哦~土豆~~.bat               # Windows one-click launcher (Double-click to start)
├── 哦~土豆~~.py                # Interactive master menu CLI
├── spectrum_announcements.py  # Announcements and forum feed viewer
├── moodle_deadlines.py        # Assignment & Quiz deadline tracker
├── spectrum_download.py       # Differential course slide downloader
├── notebooklm_pipeline.py     # Local-to-NotebookLM sync & AI generator
├── att.py                     # Attendance tool (optional/custom)
├── token.txt                  # (You must create this) SPeCTRUM WebService token
├── prompts/                   # Custom prompts for NotebookLM generation
│   ├── quiz.txt               # Instructions for generating quizzes
│   └── flashcards.txt         # Instructions for generating flashcards
└── UM_Courses/                # (Auto-created) Downloaded course materials
```

---

## 🚀 Getting Started & Prerequisites

### 1. Requirements

- **Python 3.10+** installed.
- Install the required Python libraries:
  ```bash
  pip install requests urllib3 notebooklm-py
  ```

### 2. Configure Your SPeCTRUM Token

1. Log into [UM SPeCTRUM](https://spectrum.um.edu.my).
2. Go to **Preferences $\rightarrow$ Security keys** (or grab your mobile web service token).
3. Create a plain text file named `token.txt` (or `token.text`) in the root directory of this project.
4. Paste your token as a single line in that file.

> ⚠️ **IMPORTANT**: Never commit your `token.txt` to GitHub! Add it to your `.gitignore`.

### 3. Authenticate NotebookLM (For AI Features Only)

If you plan to use `notebooklm_pipeline.py`, log into your Google NotebookLM session via the CLI:
```bash
notebooklm login
```

---

## ⚡ Quick Start (The Launcher)

### On Windows
Simply **double-click** the batch script:
```text
哦~土豆~~.bat
```
This opens the terminal menu directly without needing to type terminal commands.

### On macOS / Linux
Run the Python launcher in your terminal:
```bash
python 哦~土豆~~.py
```

---

## 🛠️ Detailed Tool Usage & Special Commands

You can run individual scripts independently from the command line if you want to use advanced flags and options.

---

### 1. `spectrum_announcements.py` (Forum & News Viewer)
Fetches recent forum posts and announcements across enrolled courses.

```bash
# Default: view last 14 days of announcements + last 48 hours "Today's News"
python spectrum_announcements.py

# Custom time window (e.g., past 7 days)
python spectrum_announcements.py --days 7

# Include past/archived courses (not just in-progress courses)
python spectrum_announcements.py --all-courses
```

**Interactive Controls:**
- Type letters (`a`, `b`, `c`...) to open items listed under **Today's News**.
- Type numbers (`1`, `2`, `3`...) to open items listed by course.
- Multiple selections are allowed (e.g., `1 3` or `a, b`).
- Type `q` or press `Enter` to exit.

---

### 2. `moodle_deadlines.py` (Deadline Tracker)
Displays all uncompleted and past assignments & quizzes grouped into:
1. **Pending** (待提交) - Sorted from closest deadline to furthest.
2. **Overdue** (已过期未交) - Deadline passed without submission.
3. **Submitted** (已提交) - Already turned in (marks late submissions).

```bash
# Show all 3 categories (Pending, Overdue, Submitted)
python moodle_deadlines.py

# Only show Pending tasks
python moodle_deadlines.py --pending

# Debug mode: check assignment/quiz count and module types per course
python moodle_deadlines.py --debug

# Display the table and exit immediately without opening the interactive prompt
python moodle_deadlines.py --no-open
```

**Interactive CLI Commands (in the `>` prompt):**
| Command | Action | Example |
| :--- | :--- | :--- |
| `<index>` | Open assignment submission page in browser | `1 3` or `1,3` |
| `d <index>` | **Hide/Delete** items (won't appear again; saved to `hidden_tasks.json`) | `d 2 4` |
| `r` | View and **restore** hidden tasks | `r` |
| `l` | Reprint the table list | `l` |
| `q` / `Enter`| Exit | `q` |

---

### 3. `spectrum_download.py` (Course Slides Downloader)
Incrementally downloads lecture slides, PPTs, PDFs, and tutorials from SPeCTRUM.

```bash
# Standard interactive download
python spectrum_download.py

# Re-download files that you deleted/moved locally
python spectrum_download.py --restore-missing
```

**Features:**
- **Course Selection Memory**: Remembers your course selections in `selected_courses.json`. Press `Enter` to use the cached selection on subsequent runs.
- **Smart Organization**: Automatically converts monolithic "Lecture Notes" into `Week 1`, `Week 2`, etc., based on titles like `L1`, `L2`, `Lecture 3`.
- **Safe Downloads**: Writes to `.part` temporary files first to prevent corrupt or incomplete downloads.

---

### 4. `notebooklm_pipeline.py` (NotebookLM Sync & AI Generator)
Reads course folders from `UM_Courses/`, uploads lecture materials to NotebookLM, and creates/updates weekly Quizzes and Flashcards.

```bash
# Preview the synchronization plan without modifying cloud resources
python notebooklm_pipeline.py --dry-run

# Run full synchronization and skip confirmation prompts on file deletions
python notebooklm_pipeline.py --yes
```

**Rules & Behavior:**
- Only folders containing `week` (e.g., `Week 3`, `week 4 (F2F)`) will trigger quiz and flashcard generation.
- Folders containing `exam` (e.g., `EXAM`) will be uploaded to NotebookLM for reference, but will **not** trigger quiz/flashcard creation.
- Avoids regenerating artifacts if cloud documents already match local files.
- Uses prompts configured in `prompts/quiz.txt` and `prompts/flashcards.txt`.

---

*Happy studying with Oh~ Potato~~! *
