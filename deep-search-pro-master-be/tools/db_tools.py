"""Read-only MySQL tools. Use a SELECT-only database account."""
import csv
import io
import os
from mysql.connector import connect, Error
from langchain_core.tools import tool

# sqlglot：SQL语法解析器，把 SQL字符串转成语法 AST树，比正则 / 字符串判断安全得多，用来审计 SQL
#防止sql语句通过注释、换行、大小写、关键字变形绕过，损坏数据库
from sqlglot import parse, exp
from sqlglot.errors import SqlglotError
from api.settings import ROOT
from api.monitor import monitor

# 全局最多返回 100 行，防止大表全表扫描拖垮数据库
MAX_ROWS = 100


def get_db_config():
    required = {'user': os.getenv('MYSQL_USER'),
                'password': os.getenv('MYSQL_PASSWORD'),
                'database': os.getenv('MYSQL_DATABASE')
                }

    if not all(value is not None for value in required.values()):
        raise ValueError('数据库尚未配置')
    return {**required,
            'host': os.getenv('MYSQL_HOST', 'localhost'),
            'port': int(os.getenv('MYSQL_PORT', '3306')),
            'charset': 'utf8mb4',
            #超时配置：连接 8s、读写 15s，防止慢查询卡死服务
            'connection_timeout': 8,
            'read_timeout': 15,
            'write_timeout': 15,
            # 关闭自动提交，后面用只读事务
            'autocommit': False,
            # Windows下 C 扩展驱动会发生底层内存访问冲突
            # 直接把 Uvicorn 进程干崩，后端会直接自己断开
            # Python的try-except 抓不住，所以强制纯 Python驱动。
            'use_pure': True}


def validate_query(query, allowed_tables):
    """输入原始 SQL 字符串 + 当前库真实允许的表集合，返回修改后安全的 SQL"""
    try:
        statements = parse(query, read='mysql')
    except SqlglotError as exc:
        raise ValueError('SQL 语法无效或不受支持') from exc

    #禁止多语句执行，防多语句注入  or 第一条语句不是 Select，也不是 Union（union 是多段 select 合并结果）
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union)):
        raise ValueError('仅允许单条 SELECT 查询')

    # 解析得到的第一条 SQL 语法树拿出来（前面已经校验过只有 1 条语句）
    tree = statements[0]
    forbidden = {'insert','update','delete','drop','create','alter','command','into','lock',
                 'transaction','commit','grant','revoke','execute','merge','copy'}

    # 管语句类型：遍历 SQL 语法树里每一个语法节点，只要出现黑名单里任意命令，直接抛异常拦截。
    if any(node.key.lower() in forbidden for node in tree.walk()):
        raise ValueError('禁止写入、锁定或执行管理语句')

    # 管函数类型：在AST里面，找到全部函数调用节点（只抓函数，不再遍历所有节点，比 walk 精准）
    for node in tree.find_all(exp.Func):
        # exp.Anonymous为特殊函数，用node.name取名,普通函数用node.sql_name 取
        # 这两种函数节点存名字的属性不一样，兼容两种情况，避免拿不到函数名。
        name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
        if name.lower() in {'sleep','benchmark','load_file','get_lock','release_lock','is_free_lock','is_used_lock','master_pos_wait'}:
            raise ValueError('禁止危险 SQL 函数')

    #把 CTE 临时表名字放进集合ctes
    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if table.db or table.catalog or table.name not in allowed_tables | ctes:
            raise ValueError('只能查询当前数据库中的已知表')
    # Always cap the outer result. Preserve smaller explicit limits.

    #管理最大查询范围：limit是 AST树的一个子节点，存在tree.args字典里面
    limit = tree.args.get('limit')
    count = limit.expression if limit else None
    if not isinstance(count, exp.Literal) or not count.is_int or int(count.this) > MAX_ROWS:
        tree = tree.limit(MAX_ROWS)
    return tree.sql(dialect='mysql')


def table_names(cursor):
    cursor.execute('SHOW TABLES')
    return {row[0] for row in cursor.fetchall()}


def query_csv(query):
    with connect(**get_db_config()) as connection:
        with connection.cursor() as cursor:
            #防止llm恶意注入，先拿到白名单
            allowed = table_names(cursor)
            safe = validate_query(query, allowed)

            #设置当前会话的 SQL 最大执行时间：**10000 毫秒 = 10 秒
            cursor.execute('SET SESSION MAX_EXECUTION_TIME=10000')

            #开启只读事务，在这个事务里面，任何写语句（INSERT/UPDATE/DELETE）都会直接报错。
            cursor.execute('START TRANSACTION READ ONLY')
            cursor.execute(safe)
            rows = cursor.fetchmany(MAX_ROWS)
            #拿到查询结果的表头，用于生成 CSV 第一行
            columns = [d[0] for d in cursor.description or []]

            #在内存创建字符串缓冲区，不生成磁盘文件，CSV 内容全部放内存
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
            # 把结果集剩下还没读取的数据全部读完、清空。
            # MySQL协议坑：如果服务端还有剩余数据包没读完就关闭游标 / 回滚，会抛出数据包异常，连接可能损坏。
            # 哪怕不需要这些数据，也要读完排空。
            cursor.fetchall()
            #回滚，哪怕只读也回滚，START TRANSACTION开启了事务，需要结束事务。
            connection.rollback()
            # 取出内存缓冲区里完整的 CSV 字符串，返回给调用方（Agent 拿到 CSV 文本）。
            return stream.getvalue()


@tool
def list_sql_tables() -> str:
    """列出当前数据库可查询的表。"""
    monitor.report_tool('数据库表名查询工具')
    try:
        with connect(**get_db_config()) as connection:
            with connection.cursor() as cursor:
                return '可用的表：' + '、'.join(sorted(table_names(cursor)))
    except (Error, ValueError) as exc:
        return f'数据库查询失败：{exc}'


@tool
def get_table_data(table_name: str) -> str:
    """预览已存在数据表的前 100 行。"""
    monitor.report_tool('数据库表数据查询工具', {'table_name': table_name})
    if not table_name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in table_name):
        return '表名无效'
    try:
        return query_csv(f'SELECT * FROM `{table_name}` LIMIT 100')
    except (Error, ValueError) as exc:
        return f'数据库查询失败：{exc}'


@tool
def execute_sql_query(query: str) -> str:
    """执行单条只读 SELECT，限制最多 100 行并设置超时。"""
    monitor.report_tool('自定义 SQL 查询', {'query': query})
    try:
        return query_csv(query)
    except (Error, ValueError) as exc:
        return f'数据库查询失败：{exc}'






