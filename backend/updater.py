"""OTA update — Phase 9."""

import asyncio
import logging
import subprocess
import sys

log = logging.getLogger(__name__)


async def run_ota(manager, branch: str = "main") -> None:
    log.info("OTA update triggered (branch: %s)", branch)
    await manager.broadcast({"type": "ota_status", "status": "starting"})
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "pull", "origin", branch],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            log.info("git pull succeeded: %s", result.stdout.strip())
            await manager.broadcast({"type": "ota_status", "status": "success", "detail": result.stdout.strip()})
            await manager.broadcast({"type": "ota_status", "status": "restarting"})
            await asyncio.sleep(2)
            sys.exit(0)
        else:
            log.error("git pull failed: %s", result.stderr.strip())
            await manager.broadcast({"type": "ota_status", "status": "error", "detail": result.stderr.strip()})
    except Exception as exc:
        log.exception("OTA error: %s", exc)
        await manager.broadcast({"type": "ota_status", "status": "error", "detail": str(exc)})
