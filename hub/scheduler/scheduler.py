import logging
import redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from hub.config import settings

logger = logging.getLogger(__name__)

_scheduler = None

redis_client = redis.from_url(settings.redis_url)

def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        from hub.config import settings

        try:
            # Attempt to parse URL and connect to Redis
            host = settings.redis_url.split("//")[1].split(":")[0]
            port = int(settings.redis_url.split(":")[-1].split("/")[0])
            
            jobstores = {
                "default": RedisJobStore(
                    connection_pool=redis_client.connection_pool
                )
            }
            logger.info(f"Successfully configured RedisJobStore at {host}:{port}")
            
        except Exception as e:
            # Catch parsing errors or Redis connection timeouts
            logger.error(f"Failed to initialize RedisJobStore (URL: {settings.redis_url}): {e}")
            logger.warning("Falling back to MemoryJobStore. Scheduler will not persist across restarts.")
            jobstores = {
                "default": MemoryJobStore()
            }

        executors = {
            "default": AsyncIOExecutor()
        }
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 300,
        }
        _scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="UTC"
        )
    return _scheduler