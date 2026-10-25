"""Persist ordered events before delivering them to live subscribers."""
import asyncio
import logging
from api.context import get_thread_context, get_run_context
from api.task_store import now
#导入异步库与日志。
logger = logging.getLogger(__name__)

def log_task_exception(task: asyncio.Task) -> None:
    """记录后台任务异常，避免异常被静默忽略。任务执行后回过头来检验是否有报错，上传到后端"""
    #如果任务被取消，直接返回，不报错
    if task.cancelled():
        return
    try:
        exception = task.exception()  #取出任务里面抛出的异常
    except asyncio.CancelledError:
        #任务主动取消不算错误，直接return
        return
    if exception is not None:
        logger.error(
            "WebSocket 后台推送失败",
            exc_info=(
                type(exception),           #异常类，例如 `OSError`
                exception,                 #异常实例对象，包含异常描述信息
                exception.__traceback__,   #堆栈对象，记录报错在哪一行代码
            ),
        )

class ConnectionManager:
    def __init__(self):
        #改进：一个会话 thread_id，可以同时存在多个 websocket 连接，可以多个页面同时打开这个对话
        self.active_connections = {} #嵌套字典 {thread_id: {websocket对象: asyncio.Lock()}}
        self.loop = None
        #task_store 事件持久化存储器，用来保存监控事件，支持历史回放
        self.store = None

    def set_loop(self, loop):
        """显式设置事件循环"""
        self.loop = loop

    async def connect(self, websocket, thread_id):
        await websocket.accept()
        lock = asyncio.Lock()#给每一个 websocket 配置锁

        # setdefault：查active_connections这个字典里的key:thread_id
        # 如果不存在就新建value为空字典；然后把 ws:lock 塞进字典，作为key:thread_id的value
        self.active_connections.setdefault(thread_id, {})[websocket] = lock

        #Agent运行时，可能短时间连续触发多个monitor埋点，通过call_soon_threadsafe丢进事件循环
        # 各自创建独立send_to_thread的协程任务。
        # 同时就绪都要推送给同一个浏览器标签页的那一条ws连接，
        #给锁就是为了并发执行，底层会报错，消息乱序。同一个 WS，发送消息必须串行排队。
        async with lock:
            await websocket.send_json({'type': 'ready', 'thread_id': thread_id})

    def disconnect(self, websocket, thread_id):
        connections = self.active_connections.get(thread_id, {})
        #删除指定 WebSocket
        connections.pop(websocket, None)
        if not connections:
            #这个会话还有其他连接？-> 有：保留会话   没有：连同 thread_id一起删除
            self.active_connections.pop(thread_id, None)

    async def send_to_thread(self, message, thread_id):
        #如果不使用 list()，环过程中一旦发送失败，就会调用：disconnect() 内部会删除当前字典元素：
        #使用 list() 后，遍历的是临时列表，即使原始字典被修改，也不影响这个循环。
        for websocket, lock in list(self.active_connections.get(thread_id, {}).items()):
            try:
                async with lock:
                    await asyncio.wait_for(websocket.send_json(message), timeout=5)
            except Exception:
                logger.warning(
                    "WebSocket 推送失败，连接将被移除",
                    exc_info=True,
                )
                self.disconnect(websocket, thread_id)


manager = ConnectionManager()


class ToolMonitor:
    def __init__(self,manager):
        self.manager = manager
    def _emit(self, event_type, message, data=None):

        thread_id, run_id = get_thread_context(), get_run_context()

        payload = {'type': 'monitor_event',
                   'event': event_type,
                   'message': message,
                   'data': data or {},
                   'timestamp': now()}

        if self.manager.store and run_id:
            payload = self.manager.store.append(run_id, payload)
        if payload and self.manager.loop and thread_id:
            def dispatch():
                task = asyncio.create_task(self.manager.send_to_thread(payload, thread_id))
                #告诉 asyncio：等这个推送任务结束，自动执行 log_task_exception(task)
                task.add_done_callback(log_task_exception)

            #通知事件循环 loop：这里有一个 dispatch 回调需要执行，请安排一下，从别的线程，安全往主线程的 asyncio 事件循环里丢任务
            try:
                self.manager.loop.call_soon_threadsafe(dispatch)
            except RuntimeError:
                logger.info("事件循环已关闭，忽略本次 WebSocket 推送")
        #显示后端日志
        logger.info('[%s] %s', event_type, message)

    @staticmethod
    def sanitize_args(args):
        """静态方法，处理 args=None，把参数值转换成字符串，限制每个参数最多保留 1200 个字符"""
        safe_args = {}
        for key, value in (args or {}).items():
            safe_args[str(key)] = str(value)[:1200]
        return safe_args

    def report_tool(self, tool_name, args=None):
        safe = self.sanitize_args(args)
        self._emit('tool_start', f'开始执行工具：{tool_name}', {'tool_name': tool_name, 'args': safe})

    def report_assistant(self, assistant_name, args=None):
        safe = self.sanitize_args(args)
        self._emit('assistant_call', f'正在调用助手：{assistant_name}', {'assistant_name': assistant_name, 'args': safe})

    def report_task_result(self, result):
        self._emit('task_result', '任务执行完成', {'result': result})

    def report_session_dir(self,path):
        self._emit('session_created', '会话工作目录已准备好')


monitor = ToolMonitor(manager)
