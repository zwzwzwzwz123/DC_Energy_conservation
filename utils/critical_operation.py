"""
关键操作保护模块

提供上下文管理器来保护关键操作（如数据库写入、模型保存），
确保这些操作在程序退出时能够完成，避免数据损坏。

"""

from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from DC_Energy_conservation.main import AppContext


@contextmanager
def critical_operation(ctx: 'AppContext'):
    """
    关键操作保护上下文管理器
    
    用法：
        with critical_operation(ctx):
            # 执行关键操作（如数据库写入、模型保存）
            ctx.influxdb_client.write_points(data)
    
    功能：
        - 在关键操作开始时，增加计数器
        - 在关键操作结束时，减少计数器
        - 主线程可以通过检查计数器来等待所有关键操作完成
    
    线程安全：
        - 使用 Lock 保护计数器的读写操作
        - 确保多个线程同时执行关键操作时不会出现竞态条件
    
    参数：
        ctx: AppContext 实例，包含 critical_operation_lock 和 critical_operation_count
    
    示例：
        # 保护数据库写入操作
        with critical_operation(ctx):
            ctx.prediction_client.write_points(data)
        
        # 保护模型保存操作
        with critical_operation(ctx):
            model.save("checkpoint.pth")
    
    注意：
        - 仅在真正关键的操作处使用此上下文管理器
        - 不要在长时间运行的任务（如训练循环）中使用
        - 关键操作应该尽可能快速完成（建议 < 5秒）
    """
    # 进入关键操作：增加计数器
    with ctx.critical_operation_lock:
        ctx.critical_operation_count += 1
        current_count = ctx.critical_operation_count

    #ctx.loggers["main"].debug(f"进入关键操作，当前关键操作数量: {current_count}")

    try:
        # 执行关键操作
        yield
    finally:
        # 退出关键操作：减少计数器
        with ctx.critical_operation_lock:
            ctx.critical_operation_count -= 1
            current_count = ctx.critical_operation_count

        #ctx.loggers["main"].debug(f"退出关键操作，当前关键操作数量: {current_count}")


def get_critical_operation_count(ctx: 'AppContext') -> int:
    """
    获取当前正在执行的关键操作数量（线程安全）
    
    参数：
        ctx: AppContext 实例
    
    返回：
        int: 当前关键操作数量
    """
    with ctx.critical_operation_lock:
        return ctx.critical_operation_count


def wait_for_critical_operations(ctx: 'AppContext', timeout: int = 30) -> bool:
    """
    等待所有关键操作完成
    
    参数：
        ctx: AppContext 实例
        timeout: 最大等待时间（秒），默认30秒
    
    返回：
        bool: True 表示所有关键操作已完成，False 表示超时
    
    示例：
        if wait_for_critical_operations(ctx, timeout=30):
            ctx.loggers["main"].info("所有关键操作已完成")
        else:
            ctx.loggers["main"].warning("等待超时，仍有关键操作未完成")
    """
    import time

    ctx.loggers["main"].info(f"等待关键操作完成（最多 {timeout} 秒）...")

    for i in range(timeout):
        count = get_critical_operation_count(ctx)

        if count == 0:
            ctx.loggers["main"].info(f"所有关键操作已完成（耗时 {i} 秒）")
            return True

        if i % 5 == 0:  # 每5秒记录一次
            ctx.loggers["main"].info(f"等待关键操作完成... 剩余 {count} 个操作，已等待 {i} 秒")

        time.sleep(1)

    # 超时
    final_count = get_critical_operation_count(ctx)
    ctx.loggers["main"].warning(f"等待超时（{timeout} 秒），仍有 {final_count} 个关键操作未完成")
    return False

