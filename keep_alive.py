from aiohttp import web
import threading
import asyncio

async def handle(request):
    return web.Response(text="I'm awake! Dattebayo! 🍥", status=200)

def run_server():
    app = web.Application()
    app.router.add_get('/', handle)
    web.run_app(app, port=8080)

def keep_alive():
    t = threading.Thread(target=run_server)
    t.start()
