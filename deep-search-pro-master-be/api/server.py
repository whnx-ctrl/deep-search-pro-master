"""Local research workbench API. Start with python -m uvicorn api.server:app."""
import asyncio
# Python 崩溃调试模块。程序发生 C 层面段错误崩溃时，打印 Python 调用栈。
import faulthandler
import logging
import os
import shutil
# 系统模块，获取 Python 版本、进程相关信息
import sys
import time

# 异步上下文管理器装饰器，用来写 lifespan
from contextlib import asynccontextmanager

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

# 上下文记忆持久化
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from api.settings import (APP_DATABASE_URL,CHECKPOINTS,DATA,EXTENSIONS,MAX_FILE_BYTES,MINIO_ACCESS_KEY,MINIO_BUCKET,MINIO_DOWNLOAD_EXPIRES_SECONDS,MINIO_ENDPOINT,MINIO_PUBLIC_ENDPOINT,
    MINIO_SECRET_KEY,MINIO_SECURE,OUTPUT,ROOT,UPLOAD,WORKSPACE_MAX_AGE_HOURS,capabilities,env_flag)
from api.task_store import TaskStore
from api.monitor import manager, monitor
from api.context import set_thread_context, set_run_context, reset_run_context, _thread_id_ctx

# minIO操作文件
from api.file_repository import FileRepository
from api.file_service import FileService
from api.minio_storage import MinioStorage


# 创建本模块的日志实例，名字是当前模块 api.serve
logger = logging.getLogger(__name__)

try:
    if not faulthandler.is_enabled():
        faulthandler.enable()
except (RuntimeError, OSError):
    logger.warning('Python faulthandler could not be enabled', exc_info=True)


def fail(status, code, message):
    raise HTTPException(status_code=status, detail={'code': code, 'message': message})


def session_uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError):
        fail(422, 'invalid_session', '会话标识必须为有效 UUID')


def session_root(thread_id):
    return OUTPUT / f'session_{session_uuid(thread_id)}'




def task_finished(task):
    """Consume background task failures so they never become silent loop errors."""
    app.state.tasks.discard(task)
    if task.cancelled():
        return
    try:
        error = task.exception()
    except asyncio.CancelledError:
        return
    if error is not None:
        logger.error(
            'Unhandled background task failure',
            exc_info=(type(error), error, error.__traceback__),
        )

# app.state 是 FastAPI 提供的“应用级共享状态容器”。
# 它适合保存整个后端进程共同使用、需要从多个请求中访问的对象，比如：
# - 数据库连接池
# - TaskStore
# - 服务实例 ID
# - 后台任务集合
# - 上传锁
# - HTTP 客户端
# - 缓存客户端


@asynccontextmanager
async def lifespan(app):
    for path in (OUTPUT, UPLOAD, DATA):
        path.mkdir(parents=True, exist_ok=True)

    # 后端每次重启会产生新的 ID。前端发现 ID 变化后，就知道后端已经重启
    app.state.instance_id = str(uuid4())

    # 保存当前进程 pid，日志里方便看是哪个进程。
    # pid 指当前后端 Python 进程的操作系统进程编号，用于前端识别哪个进程
    app.state.pid = os.getpid()

    app.state.started_at = datetime.now(timezone.utc).isoformat()

    # 单调时钟，只增不减，不受系统时间修改影响，用来计算运行时长。
    app.state.started_monotonic = time.monotonic()

    #TaskStore(DATA / 'tasks.sqlite3')创建了一个本地 SQLite 数据库，store 任务状态和任务事件的持久化管理器
    #store负责把任务状态、埋点事件、最终结果保存到 SQLite。这样即使 WebSocket 断开或页面刷新，前端仍可以重新查询任务进度。
    app.state.store = TaskStore(DATA / 'tasks.sqlite3')

    # 全局任务集合 → 管 Agent 后台任务
    app.state.tasks = set()
    #会话锁字典 → 控制同一个会话不能同时上传文件
    app.state.upload_locks = {}

    #初始化 FileRepository,只管理 MySQL 文件元数据
    app.state.file_repository = FileRepository(
        database_url=APP_DATABASE_URL,
    )
    await app.state.file_repository.open()

    #初始化 MinioStorage,只管理 MinIO 文件内容
    app.state.minio_storage = MinioStorage(
        endpoint=MINIO_ENDPOINT,
        public_endpoint=MINIO_PUBLIC_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        bucket=MINIO_BUCKET,
        secure=MINIO_SECURE,
        download_expires_seconds=(
            MINIO_DOWNLOAD_EXPIRES_SECONDS
        ),
    )
    await app.state.minio_storage.ensure_bucket()

    #初始化 FileService,只管理 MinIO 文件内容
    app.state.file_service = FileService(
        repository=app.state.file_repository,
        storage=app.state.minio_storage,
        output_root=OUTPUT,
        upload_root=UPLOAD,
        max_file_bytes=MAX_FILE_BYTES,
        extensions=EXTENSIONS,
    )
    await app.state.file_service.cleanup_stale_workspaces(
        max_age_hours=WORKSPACE_MAX_AGE_HOURS,
    )

    manager.store = app.state.store
    #获取loop事件循环
    manager.set_loop(asyncio.get_running_loop())

    # 打开AsyncSqliteSaver，同时必须在 FastAPI 的整个运行期间保持打开，
    # 原本lifespan结束板块finally也写在其内部
    # 确保所有任务都关闭时，最后再退出退出async with，关闭AsyncSqliteSave
    async with AsyncSqliteSaver.from_conn_string(
            str(CHECKPOINTS)
    ) as checkpointer:
        app.state.checkpointer = checkpointer

        logger.info(
            'Backend started pid=%s python=%s cwd=%s',
            app.state.pid,  # 进程 id
            sys.version.split()[0],  # python 版本
            ROOT,
        )
        try:
            yield
        finally:  # 生命周期函数，结束后：
            logger.info('Backend shutdown requested pid=%s', app.state.pid)
            tasks = list(app.state.tasks)
            # 服务关闭时，取消集合里剩下未完成的任务
            for task in tasks:
                task.cancel()
            # gather 给了任务一次继续被 event loop 调度并完成清理的机会。
            # 负责等它们真正停止并完成清理，return_exceptions=True负责防止单个任务异常打断整个服务关闭流程
            await asyncio.gather(*tasks, return_exceptions=True)
            manager.store = None
            manager.loop = None
            # file_repository持有 MySQL 连接池，需要关闭。
            # MinioStorage通常只是包装 MinIO Client，没有独占连接需要关闭
            # FileService 只组合前两者，自身没有底层资源,不用关闭
            await app.state.file_repository.close()
            app.state.store.close()
            logger.info('Backend shutdown complete pid=%s', app.state.pid)
# 不能先关闭 checkpointer，再等待 Agent 任务，否则任务可能仍在写 SQLite

app = FastAPI(title='Deep Search Pro API',
              lifespan=lifespan)
origins = [v.strip() for v in os.getenv('CORS_ORIGINS',
                                        'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173').split(',') if v.strip()]
app.add_middleware(CORSMiddleware,
                   allow_origins=origins,
                   allow_credentials=False,
                   allow_methods=['GET', 'POST','DELETE'],
                   allow_headers=['Content-Type', 'X-Request-Id'])

# 这是 FastAPI的全局异常装饰器
@app.exception_handler(HTTPException)
#  当这个 FastAPI 应用处理请求时遇到 HTTPException，调用下面的 http_error() 函数处理
async def http_error(request, exc):
    body = exc.detail if isinstance(exc.detail, dict) else {'code': 'request_error', 'message': str(exc.detail)}
    return JSONResponse({'error': body}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({'error': {'code': 'invalid_request', 'message': '请求参数无效，请检查输入内容及会话标识。'}}, status_code=422)


# TaskRequest 是前端提交 Agent 任务时的 JSON 请求说明书和自动校验器。
# 就是在请求进入真正的业务逻辑之前，先对前端提交的数据进行自动检验和转换。
class TaskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20000)
    thread_id: UUID | None = None


@app.get('/api/health')
async def health():
    return {
        'status': 'ok',
        'instance_id': app.state.instance_id,
        'capabilities': capabilities(),
        'pid': app.state.pid,
        'started_at': app.state.started_at,
        'uptime_seconds': round(max(0.0, time.monotonic() - app.state.started_monotonic), 3),
    }

# agent调用过程中，出现异常，端终端保留完整技术错误
# user_error() 将其转为安全、简洁、便于理解的提示，通过monitor向前端报点过程中，通过append也存入sqlite中
def user_error(exc):
    status = getattr(exc, 'status_code', None)
    if status in (401, 403, 404):
        return '模型服务拒绝访问，请检查后端模型名称、API Key 和模型权限。'
    if status == 429:
        return '模型服务额度或频率受限，请稍后重试。'
    if isinstance(exc, (ConnectionError, TimeoutError)) or 'connection' in type(exc).__name__.lower():
        return '无法连接模型或外部服务，请检查网络和服务配置。'
    return '任务执行失败，请查看后端终端日志后重试。'


async def execute_task(query, thread_id, run_id):
    thread_token = set_thread_context(thread_id)
    run_token = set_run_context(run_id)
    # run_id= 新设置进去的值  run_token= 修改前状态的快照/恢复凭证
    try:
        app.state.store.running(run_id)
        from agent.main_agent import run_deep_agent
        result = await run_deep_agent(query, thread_id,app.state.checkpointer,app.state.file_service)
        monitor.report_task_result(result)
    except asyncio.CancelledError:
        monitor._emit('interrupted', '服务关闭，本次任务已中断。')
        raise
    except Exception as exc:
        logger.exception('Agent run failed: %s', run_id)
        monitor._emit('error', user_error(exc))
    finally:
        reset_run_context(run_token)
        #恢复是恢复之前的状态，而不是直接清空
        _thread_id_ctx.reset(thread_token)


@app.post('/api/task', status_code=202)
async def run_task(request: TaskRequest):
    query = request.query.strip()
    if not query:
        fail(422, 'empty_query', '请输入问题')
    thread_id = str(request.thread_id or uuid4())
    # 会话的上传锁存在并且正在锁定
    if app.state.upload_locks.get(thread_id) and app.state.upload_locks[thread_id].locked():
        fail(409, 'upload_active', '文件正在上传，请等待上传完成')
    try:
        run_id = app.state.store.create(thread_id)
    except ValueError as exc:
        fail(409, 'task_active', str(exc))
    task = asyncio.create_task(execute_task(query, thread_id, run_id))
    app.state.tasks.add(task)
    # 注册回调：任务结束（成功/报错/取消）自动执行task_finished
    task.add_done_callback(task_finished)
    return {'status': 'started', 'thread_id': thread_id, 'run_id': run_id}


@app.get('/api/tasks/{run_id}')
async def task_status(run_id: UUID):
    result = app.state.store.get(str(run_id))
    if not result:
        fail(404, 'task_missing', '任务不存在')
    return result


@app.get('/api/sessions/{thread_id}/active')
async def active_task(thread_id: UUID):
    return {'run_id': app.state.store.active(str(thread_id))}


def remove_session_tree(path: Path):
    """删除会话目录；目录不存在时视为已经删除成功。"""
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass


@app.delete('/api/sessions/{thread_id}', status_code=204)
async def delete_session(thread_id: UUID):
    thread_id = str(thread_id)

    # 任务执行中不能删除，避免 Agent 继续向已删除的会话写入数据。
    if app.state.store.active(thread_id):
        fail(409, 'session_busy', '会话正在执行任务，暂时不能删除')

    # 文件上传中不能删除，避免上传程序重新创建已删除的目录。
    upload_lock = app.state.upload_locks.get(thread_id)
    if upload_lock and upload_lock.locked():
        fail(409, 'session_busy', '会话正在上传文件，暂时不能删除')

    # delete_session_files:找到会话全部文件→ 标记 deleting→ 删除 MinIO 对象→ 软删除 MySQL 元数据→ 清理本地临时目录
    await app.state.file_service.delete_session_files(thread_uuid=thread_id)

    # 删除 LangGraph / DeepAgents 保存的对话上下文。
    # 用来确保 LangGraph checkpoint 所需的数据表和迁移已经完成。
    await app.state.checkpointer.setup()
    #
    await app.state.checkpointer.adelete_thread(thread_id)

    # 删除 tasks.sqlite3 中该会话的任务记录和事件记录。
    app.state.store.delete_thread(thread_id)

    # 文件删除属于阻塞型磁盘操作，放到工作线程执行，
    # 避免阻塞 FastAPI 的 asyncio 事件循环。
    await asyncio.gather(
        asyncio.to_thread(
            remove_session_tree,
            session_root(thread_id),
        ),
        asyncio.to_thread(
            remove_session_tree,
            UPLOAD / f'session_{thread_id}',
        ),
    )

    # 清除不再需要的上传锁对象。
    app.state.upload_locks.pop(thread_id, None)

    return Response(status_code=204)

@app.post('/api/upload')
async def upload_files(files: list[UploadFile] = File(...), thread_id: str = Form(...)):
    # 标准化会话id
    thread_id = session_uuid(thread_id)
    # 限制单次最多上传5个文件
    if len(files) > 5:
        fail(413, 'too_many_files', '每次最多上传 5 个文件')
    # 获取当前会话对应的异步锁，没有就新建一把
    lock = app.state.upload_locks.setdefault(thread_id, asyncio.Lock())
    # 双重判断：上传锁被占用 OR 会话有正在跑的Agent任务 → 拒绝上传，防止冲突
    if lock.locked() or app.state.store.active(thread_id):
        fail(409, 'session_busy', '会话正在处理，请稍后上传')
    async with lock:
        try:
            results = await app.state.file_service.upload_files(
                thread_uuid=thread_id,
                uploads=files,
            )
        finally:
            for upload in files:
                await upload.close()
    return {'status': 'uploaded','files': results}


@app.get('/api/files')
async def list_files(thread_id: UUID):
    files = await app.state.file_service.list_files(
        thread_uuid=str(thread_id),
    )
    return {
        'files': files,
    }

@app.post('/api/files/{file_uuid}/download-url')
# 下载时，前端发请求，后端返回限时预签名 URL
async def create_download_url(file_uuid: UUID):
    try:
        return await app.state.file_service.create_download_url(
            file_uuid=str(file_uuid),
        )
    except FileNotFoundError:
        fail(404, 'file_missing', '文件不存在或不可下载')


@app.websocket('/ws/{thread_id}')
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    # 只允许配置里的前端域名连接，防止别的网站跨域连websocket
    origin = websocket.headers.get('origin')
    if origin and origin not in origins:
        await websocket.close(code=1008)
        return

    # 校验url里的thread_id是不是合法UUID，格式不对直接断开
    try:
        thread_id = str(UUID(thread_id))
    except ValueError:
        await websocket.close(code=1008)
        return

    try:
        # 把当前ws连接注册进连接管理器，同个thread_id支持多设备/多页面同时连
        await manager.connect(websocket, thread_id)
        while True:
            # 阻塞等待前端发来消息（ping心跳包）
            await websocket.receive_text()
            # 拿到这个websocket专属锁
            lock = manager.active_connections.get(thread_id, {}).get(websocket)
            if lock:
                # 加锁后回复pong，保证这个ws串行发消息，不并发send报错
                async with lock:
                    await websocket.send_json({'type': 'pong'})
    except (WebSocketDisconnect, RuntimeError):
        # 前端主动断开、连接异常，不抛堆栈
        pass
    finally:
        # 不管正常断开还是异常断开，都清理连接记录
        manager.disconnect(websocket, thread_id)


if __name__ == '__main__':
    import uvicorn
    reload_enabled = env_flag('BACKEND_RELOAD')
    logging.basicConfig(level=logging.INFO)
    logger.info('Starting Uvicorn reload=%s', reload_enabled)
    uvicorn.run('api.server:app', host='127.0.0.1', port=8000, reload=reload_enabled)
