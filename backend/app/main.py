import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import bootstrap, database
from app.routers import (
    admin,
    auth,
    backup,
    bundles,
    calendar,
    categories,
    currencies,
    dashboard,
    icons,
    integrations,
    logs,
    notifications,
    payment_methods,
    reports,
    setup,
    subscriptions,
    system,
    users,
)
from app.services import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 若磁盘上已有数据库配置，则尝试初始化；否则进入安装向导模式。
    # 宿主机/容器异常重启时，app 常比 MySQL 先起来——这里做多次重试，
    # 避免因 MySQL 尚未就绪而一次性失败、掉进「需要重新配置数据库」的状态。
    if bootstrap.config_exists():
        attempts = 10
        for i in range(1, attempts + 1):
            if database.connect_from_saved_config(force=True):
                print("[startup] 数据库已连接，系统就绪。")
                break
            print(f"[startup] 数据库暂不可用，重试 {i}/{attempts} …")
            if i < attempts:
                await asyncio.sleep(3)
        else:
            # 仍未连上：不阻塞启动，后续请求到达时会自动重连（database.get_db 自愈）
            print("[startup] 数据库多次重试仍不可用，转为按需自动重连（无需重走安装向导）。")
    else:
        print("[startup] 未检测到数据库配置，进入安装向导模式。")
    yield
    scheduler.shutdown_scheduler()


app = FastAPI(title="订阅保号通知系统 API", version="1.1.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    """未处理异常也以 JSON detail 返回，避免 500 纯文本掩盖真实错误原因。"""
    print(f"[error] {request.method} {request.url.path}: {type(exc).__name__}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请查看服务运行状态后重试"},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    setup.router,
    auth.router,
    users.router,
    categories.router,
    payment_methods.router,
    currencies.router,
    subscriptions.router,
    bundles.router,
    dashboard.router,
    reports.router,
    notifications.router,
    icons.router,
    admin.router,
    logs.router,
    system.router,
    backup.router,
    calendar.router,
    integrations.router,
):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "configured": database.is_configured()}


# 静态资源（上传的图标：加 CSP 沙箱与 nosniff，保留 SVG 显示但阻止直接打开时执行脚本）
class IconStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            response = JSONResponse(
                {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
            )
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


os.makedirs(os.path.join("data", "icons"), exist_ok=True)
app.mount("/static/icons", IconStaticFiles(directory=os.path.join("data", "icons")), name="icons")

# 前端构建产物（若存在则托管，实现单服务部署 + SPA history 路由兜底）
_frontend_dist = os.path.join("frontend_dist")
if os.path.isdir(_frontend_dist):
    dist_root = os.path.realpath(_frontend_dist)
    _assets = os.path.join(_frontend_dist, "assets")
    if os.path.isdir(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "API endpoint not found")
        candidate = os.path.realpath(os.path.join(dist_root, full_path))
        try:
            contained = os.path.commonpath([dist_root, candidate]) == dist_root
        except ValueError:
            contained = False
        if contained and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(dist_root, "index.html"))
