import asyncio
import os
from pathlib import Path

from research_analyser.diagram_generator import DiagramGenerator
from research_analyser.models import ExtractedContent, Section


def load_google_key() -> None:
    env_path = Path('.env')
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key.strip() == 'GOOGLE_API_KEY':
            os.environ['GOOGLE_API_KEY'] = value.strip().strip('"').strip("'")


async def main() -> None:
    os.environ.pop('SKIP_SSL_VERIFICATION', None)
    os.environ.pop('PYTHONHTTPSVERIFY', None)
    load_google_key()

    content = ExtractedContent(
        full_text='Architecture with encoder blocks, attention, feed-forward, and evaluation metrics.',
        title='SSL Retry Validation',
        authors=['RA'],
        abstract='Test',
        sections=[Section(title='Method', level=1, content='encoder -> attention -> output')],
        equations=[],
        tables=[],
        figures=[],
        references=[],
    )

    dg = DiagramGenerator(
        provider='gemini',
        vlm_model='gemini-2.0-flash',
        image_model='gemini-3-pro-image-preview',
        output_dir='output/paperbanana_retry_check',
        skip_ssl_verification=False,
        max_iterations=1,
    )

    diagrams = await dg.generate(content, ['methodology'])
    if not diagrams:
        print('RESULT=FAIL_NO_OUTPUT')
        return

    d = diagrams[0]
    exists = Path(d.image_path).exists()
    if exists and not d.is_fallback:
        print('RESULT=PASS')
    else:
        print('RESULT=WARN')
    print(f'IS_FALLBACK={d.is_fallback}')
    print(f'IMAGE_PATH={d.image_path}')
    print(f'ERROR={d.error}')


if __name__ == '__main__':
    asyncio.run(main())
