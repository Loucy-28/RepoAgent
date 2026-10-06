import redis.asyncio as redis
from app.config import settings

redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return redis_client


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None


class RedisLock:
    def __init__(self, key: str, ttl: int = 60):
        self.key = f"agent:lock:{key}"
        self.ttl = ttl

    async def acquire(self) -> bool:
        r = await get_redis()
        return bool(await r.set(self.key, "1", nx=True, ex=self.ttl))

    async def release(self):
        r = await get_redis()
        await r.delete(self.key)


class AgentStateStore:
    @staticmethod
    async def set(task_id: str, state: dict, ttl: int = 3600):
        import json
        r = await get_redis()
        await r.set(f"agent:state:{task_id}", json.dumps(state), ex=ttl)

    @staticmethod
    async def get(task_id: str) -> dict | None:
        import json
        r = await get_redis()
        data = await r.get(f"agent:state:{task_id}")
        if data:
            return json.loads(data)
        return None

    @staticmethod
    async def delete(task_id: str):
        r = await get_redis()
        await r.delete(f"agent:state:{task_id}")
