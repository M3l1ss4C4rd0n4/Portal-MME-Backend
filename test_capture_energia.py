import asyncio
import base64
import logging
from domain.services.portal_capture_service import capture_tablero

logging.basicConfig(level=logging.INFO)

async def main():
    result = await capture_tablero("energia", dpr=4)
    print("Capturas:", list(result.keys()))
    for name, b64 in result.items():
        png = base64.b64decode(b64)
        with open(f"/tmp/cap_energia_{name}.png", "wb") as f:
            f.write(png)
        print(f"  {name}: {len(png)} bytes")

if __name__ == "__main__":
    asyncio.run(main())
