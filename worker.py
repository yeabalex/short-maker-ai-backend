import os
from redis import Redis
from rq import SimpleWorker, Queue  # Changed from Worker to SimpleWorker
from dotenv import load_dotenv

load_dotenv()

redis_conn = Redis.from_url(os.getenv("REDIS_URL"))
queue = Queue("video_queue", connection=redis_conn)

if __name__ == "__main__":
    worker = SimpleWorker([queue], connection=redis_conn)  # Changed to SimpleWorker
    worker.work()