import asyncio
import tools.web
from unittest.mock import MagicMock

async def main():
    tools.web._http_client = None
    try:
        ctx = MagicMock()
        result = await tools.web.web_fetch({'url': 'https://httpbin.org/html'}, ctx)
        print(f'Summary: {result.summary}')
        print(f'Error: {result.error}')
        print(f'Skipped: {result.skipped}')
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
