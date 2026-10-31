"""Select FileUrlProvider implementation from settings."""

from __future__ import annotations

import logging

from billing_agent.config import Settings
from billing_agent.services.local_tunnel_storage import LocalTunnelProvider
from billing_agent.services.oss_storage import AliyunOSSStorage, FileUrlProvider, StorageError
from billing_agent.services.r2_worker_storage import CloudflareR2WorkerProvider

logger = logging.getLogger(__name__)

PROVIDER_ALIYUN_OSS = "aliyun_oss"
PROVIDER_CLOUDFLARE_R2_WORKER = "cloudflare_r2_worker"
PROVIDER_LOCAL_TUNNEL = "local_tunnel"


def create_file_url_provider(settings: Settings) -> FileUrlProvider | None:
    """Build the active FileUrlProvider, or None when storage is not configured."""
    choice = (settings.file_url_provider or "").strip().lower()

    if choice == PROVIDER_LOCAL_TUNNEL:
        lt = settings.local_tunnel.refresh_from_status_file()
        if not lt.configured:
            logger.warning(
                "FILE_URL_PROVIDER=%s but local tunnel incomplete: %s",
                choice,
                lt.missing_fields(),
            )
            return None
        # Construct even if gateway is temporarily down; put_temporary fails loudly.
        return LocalTunnelProvider(lt)

    if choice == PROVIDER_CLOUDFLARE_R2_WORKER:
        if not settings.r2_worker.configured:
            logger.warning(
                "FILE_URL_PROVIDER=%s but R2 Worker settings incomplete: %s",
                choice,
                settings.r2_worker.missing_fields(),
            )
            return None
        return CloudflareR2WorkerProvider(settings.r2_worker)

    if choice == PROVIDER_ALIYUN_OSS:
        if not settings.oss.configured:
            logger.warning(
                "FILE_URL_PROVIDER=%s but OSS settings incomplete: %s",
                choice,
                settings.oss.missing_fields(),
            )
            return None
        return AliyunOSSStorage(settings.oss)

    # Auto: prefer explicit R2 when fully configured, else OSS.
    # local_tunnel is never auto-selected (requires intentional Quick Tunnel demo).
    if not choice:
        if settings.r2_worker.configured and not settings.oss.configured:
            return CloudflareR2WorkerProvider(settings.r2_worker)
        if settings.oss.configured:
            try:
                return AliyunOSSStorage(settings.oss)
            except StorageError:
                return None
        if settings.r2_worker.configured:
            return CloudflareR2WorkerProvider(settings.r2_worker)
        return None

    logger.warning("Unknown FILE_URL_PROVIDER=%r; no storage provider created", choice)
    return None
