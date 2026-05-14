# Sprint Prompt: JARVIS v0.8.2 — Safe File Access

> Paste this to Claude Code to implement.

---

JARVIS v0.8.2 — Safe File Access (Read-Only + Summarize)

Add voice commands to read and summarize files from approved directories.

SCOPE:
- Read files from approved paths only (whitelist)
- Summarize content via Claude (PDFs, DOCX, TXT, XLSX)
- NO write, NO delete, NO execute

CONSTRAINTS:
- New file: `core/file_bridge.py` — FileBridge class
- Add `file_read` action to safe_actions.py + ACTION_MAP
- Approved paths whitelist: `C:\Users\walid\Documents\MSMA\`, `C:\Users\walid\Desktop\`
- Path traversal prevention: resolve path, verify it starts with approved prefix
- Max file size: 5MB
- Summarization via Claude Sonnet (not Opus — cost control)
- DO NOT modify core/*.py beyond safe_actions.py

IMPLEMENTATION STEPS:
1. Create core/file_bridge.py:
   - `APPROVED_ROOTS = [Path('C:/Users/walid/Documents/MSMA'), Path('C:/Users/walid/Desktop')]`
   - `is_safe_path(path: Path) → bool` — resolves symlinks, checks prefix
   - `read_file(path: Path) → str` — extract text from PDF/DOCX/TXT/XLSX
   - `summarize(text: str, question: str) → str` — Claude Sonnet summary
   - Supported: `.txt`, `.md`, `.pdf` (via pypdf), `.docx` (via python-docx), `.xlsx` (via openpyxl first sheet)

2. Add to safe_actions.py:
   - `file_read(transcript=None) → dict`
   - Extract filename from transcript using regex
   - Search approved roots for matching filename (case-insensitive)
   - If multiple matches: speak "Found X files, be more specific"
   - Summarize and speak result

3. Security: ALWAYS validate path after resolution. Never accept absolute paths from transcript. Search by filename only.

VOICE EXAMPLES:
"summarize the Zamilfood quote" → finds Zamilfood*.pdf or .docx in Documents/MSMA
"read the electrical specs" → finds matching file in approved roots
"what's in the SMI report" → same

DEPENDENCIES: pypdf, python-docx, openpyxl (add to requirements.txt)

TESTS: tests/test_file_bridge.py — mock filesystem, test path traversal prevention

COMMIT: feat: v0.8.2 — safe file access + summarization (approved paths only)
