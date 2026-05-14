"""GitHub watch — scan trusted AI/agent repos daily for relevant updates."""
import os, time, requests
from datetime import datetime, timedelta
from loguru import logger

TRUSTED_REPOS = [
    'anthropics/anthropic-sdk-python',
    'openai/openai-python',
    'ollama/ollama',
    'NousResearch/Hermes-Function-Calling',
    'simonw/llm',
    'BerriAI/litellm',
    'langchain-ai/langchain',
    'guidance-ai/guidance',
    'microsoft/autogen',
    'crewAIInc/crewAI',
]


class GitHubWatcher:
    def __init__(self):
        self.api = 'https://api.github.com'

    def watch_repos(self) -> list:
        """Check trusted repos for recent commits/releases."""
        insights = []
        since = (datetime.now() - timedelta(days=1)).isoformat()

        for repo in TRUSTED_REPOS:
            try:
                # Latest release
                r = requests.get(f'{self.api}/repos/{repo}/releases/latest', timeout=10)
                if r.status_code == 200:
                    rel = r.json()
                    published = rel.get('published_at', '')
                    if published > since:
                        insights.append({
                            'type': 'release',
                            'repo': repo,
                            'name': rel.get('name', ''),
                            'url': rel.get('html_url', ''),
                            'body': (rel.get('body', '') or '')[:200]
                        })

                # Recent commits
                r = requests.get(
                    f'{self.api}/repos/{repo}/commits',
                    params={'since': since, 'per_page': 3},
                    timeout=10
                )
                if r.status_code == 200:
                    commits = r.json()
                    if commits and isinstance(commits, list):
                        for c in commits[:2]:
                            msg = c.get('commit', {}).get('message', '')[:100]
                            insights.append({
                                'type': 'commit',
                                'repo': repo,
                                'message': msg,
                                'url': c.get('html_url', '')
                            })

                time.sleep(0.5)  # rate limit
            except Exception as e:
                logger.debug(f"GitHub repo {repo}: {e}")
                continue

        logger.success(f"GitHub watch: {len(insights)} new items")
        return insights

    def scan(self):
        """Store insights to memory."""
        from core.memory import JarvisMemory
        memory = JarvisMemory()
        insights = self.watch_repos()
        for item in insights:
            summary = (
                f"[{item['type']}] {item['repo']}: "
                f"{item.get('name') or item.get('message', '')[:80]}"
            )
            memory.add_insight(
                'github',
                f"trusted repos {datetime.now().strftime('%Y-%m-%d')}",
                summary,
                item.get('url', '')
            )
        return insights
