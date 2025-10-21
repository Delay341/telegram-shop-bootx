import os
from aiohttp import web

PORT = int(os.getenv("PORT", "10000"))

async def healthcheck(request):
    return web.Response(text="OK")

async def index(request):
    return web.json_response({"status": "ok", "service": "BoostX Uptime", "port": PORT})

def main():
    app = web.Application()
    app.add_routes([
        web.get("/", healthcheck),
        web.get("/health", healthcheck),
        web.get("/status", index),
    ])
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    print(f"🌐 Health server starting on 0.0.0.0:{PORT}", flush=True)
    main()
