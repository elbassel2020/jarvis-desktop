"""Vision module — analyze images via Claude vision."""
import os, base64, time
from pathlib import Path
from loguru import logger


class JarvisVision:
    def __init__(self):
        key = os.getenv('ANTHROPIC_API_KEY')
        if key:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=key)
        else:
            self.client = None

    def _encode_image(self, image_path: Path) -> tuple:
        """Read image, return (base64, media_type)."""
        ext = image_path.suffix.lower()
        media_type = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'
        }.get(ext, 'image/png')
        with open(image_path, 'rb') as f:
            data = base64.standard_b64encode(f.read()).decode('utf-8')
        return data, media_type

    def analyze(self, image_path: Path, prompt: str = None) -> dict:
        """Analyze image, return description + insights."""
        if not self.client:
            return {'error': 'No Anthropic key', 'success': False}
        if not image_path.exists():
            return {'error': f'Image not found: {image_path}', 'success': False}
        try:
            data, media_type = self._encode_image(image_path)
            t0 = time.time()
            default_prompt = (
                "You are looking at an image for Walid (B2B electrical contractor, Jubail KSA).\n"
                "Describe in Egyptian Arabic, 2-3 sentences max:\n"
                "- What you see\n"
                "- Anything notable (electrical components, products, prices, customer info, etc.)\n"
                "- Any concerns or recommendations\n\n"
                "Be casual, direct. No markdown, no bullets."
            )
            response = self.client.messages.create(
                model='claude-sonnet-4-6', max_tokens=400,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                        {"type": "text", "text": prompt or default_prompt}
                    ]
                }]
            )
            description = response.content[0].text.strip()
            elapsed = time.time() - t0
            logger.success(f"Vision: [{elapsed:.1f}s] {description[:100]}")
            return {
                'description': description,
                'duration_s': elapsed,
                'image_path': str(image_path),
                'success': True
            }
        except Exception as e:
            logger.error(f"Vision failed: {e}")
            return {'error': str(e), 'success': False}

    def find_recent_image(self) -> Path:
        """Find most recent screenshot or image from common locations."""
        candidates = [
            Path.home() / 'Pictures' / 'Screenshots',
            Path.home() / 'Downloads',
            Path.home() / 'Desktop',
            Path('logs/screenshots'),
        ]
        all_images = []
        for d in candidates:
            if d.exists():
                for ext in ['*.png', '*.jpg', '*.jpeg']:
                    all_images.extend(d.glob(ext))
        if not all_images:
            return None
        return max(all_images, key=lambda p: p.stat().st_mtime)

    def from_clipboard(self) -> Path:
        """Save clipboard image to temp file."""
        try:
            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
            if img is None:
                return None
            from datetime import datetime
            path = Path('logs/captures') / f'clipboard_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(path))
            return path
        except Exception as e:
            logger.error(f"Clipboard image: {e}")
            return None
