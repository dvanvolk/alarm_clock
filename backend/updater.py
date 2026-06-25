"""OTA update — Phase 9 implementation. Stub for MVP."""

import asyncio
import logging
import subprocess

log = logging.getLogger(__name__)


async def run_ota(manager) -> None:
    log.info("OTA update triggered")
    await manager.broadcast({"type": "ota_status", "status": "starting"})
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "pull"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            log.info("git pull succeeded: %s", result.stdout.strip())
            await manager.broadcast({"type": "ota_status", "status": "success", "detail": result.stdout.strip()})
            # systemd restart happens outside this process
        else:
            log.error("git pull failed: %s", result.stderr.strip())
            await manager.broadcast({"type": "ota_status", "status": "error", "detail": result.stderr.strip()})
    except Exception as exc:
        log.exception("OTA error: %s", exc)
        await manager.broadcast({"type": "ota_status", "status": "error", "detail": str(exc)})
