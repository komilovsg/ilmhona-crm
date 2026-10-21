"""TCP proxy that adds a one-way delay to every chunk (fakes a WAN link to Postgres):

uv run python -m tools.delay_proxy 55943 55433 25     # listen, target, one-way ms
"""

import asyncio
import sys


async def pipe(r: asyncio.StreamReader, w: asyncio.StreamWriter, delay: float) -> None:
    queue: asyncio.Queue[tuple[float, bytes] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    async def reader() -> None:
        while data := await r.read(65536):
            queue.put_nowait((loop.time() + delay, data))
        queue.put_nowait(None)

    task = asyncio.create_task(reader())
    try:
        while (item := await queue.get()) is not None:
            at, data = item
            await asyncio.sleep(max(0.0, at - loop.time()))
            w.write(data)
            await w.drain()
    finally:
        task.cancel()
        w.close()


async def main(listen: int, target: int, ms: float) -> None:
    async def handle(cr: asyncio.StreamReader, cw: asyncio.StreamWriter) -> None:
        sr, sw = await asyncio.open_connection("127.0.0.1", target)
        await asyncio.gather(
            pipe(cr, sw, ms / 1000), pipe(sr, cw, ms / 1000), return_exceptions=True
        )

    server = await asyncio.start_server(handle, "127.0.0.1", listen)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])))
