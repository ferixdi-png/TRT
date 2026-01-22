import concurrent.futures
import logging

from app.storage.factory import get_storage
from bot_kie import _run_storage_coro_sync


logger = logging.getLogger(__name__)


def _run_iteration(storage, filename: str, index: int) -> None:
    payload = {"iteration": index}
    _run_storage_coro_sync(storage.write_json_file(filename, payload), label=f"smoke_write:{index}")
    _run_storage_coro_sync(storage.read_json_file(filename, {}), label=f"smoke_read:{index}")


def main(iterations: int = 20) -> None:
    storage = get_storage()
    filename = "smoke_storage_sync.json"
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(_run_iteration, storage, filename, index)
            for index in range(iterations)
        ]
        for future in concurrent.futures.as_completed(futures):
            future.result()
    logger.info("Storage sync bridge smoke finished (%s iterations).", iterations)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
