"""Self-analyze — Jarvis reads its own code and suggests improvements (no auto-modify)."""
import os, time
from pathlib import Path
from loguru import logger

ANALYZE_PROMPT = """You are Jarvis reviewing your own source file: {filename}

```python
{code}
```

Analyze in Arabic + English mix, casual:
1. Strengths of this file
2. 2-3 specific improvement opportunities (NOT trivial style)
3. Bug risks if any
4. Performance concerns
5. Suggested next features

Max 200 words. Be concrete. No fluff."""


class SelfAnalyzer:
    def __init__(self):
        key = os.getenv('ANTHROPIC_API_KEY')
        if key:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=key)
        else:
            self.client = None

    def analyze_file(self, file_path: Path) -> dict:
        if not self.client or not file_path.exists():
            return {'error': 'Setup issue', 'success': False}
        try:
            code = file_path.read_text(encoding='utf-8')[:8000]
            t0 = time.time()
            response = self.client.messages.create(
                model='claude-sonnet-4-6', max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": ANALYZE_PROMPT.format(filename=file_path.name, code=code)
                }]
            )
            review = response.content[0].text.strip()
            return {
                'file': str(file_path),
                'review': review,
                'duration_s': time.time() - t0,
                'success': True
            }
        except Exception as e:
            return {'error': str(e), 'success': False}

    def analyze_self(self) -> dict:
        """Analyze all core/ files, return combined report."""
        core_files = list(Path('core').glob('*.py'))
        reports = []
        for f in core_files:
            if f.name == '__init__.py':
                continue
            result = self.analyze_file(f)
            if result.get('success'):
                reports.append(f"## {f.name}\n{result['review']}\n")

        report = "\n".join(reports)
        from datetime import datetime
        out = Path('audits') / f'SELF_REVIEW_{datetime.now().strftime("%Y%m%d")}.md'
        out.parent.mkdir(exist_ok=True)
        out.write_text(report, encoding='utf-8')
        return {'report_file': str(out), 'files_analyzed': len(reports), 'success': True}
