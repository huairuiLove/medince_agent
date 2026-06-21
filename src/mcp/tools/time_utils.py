"""
时间工具：获取当前系统时间
"""
from datetime import datetime


def get_current_time() -> str:
    """获取当前系统时间（中文格式）"""
    now = datetime.now()
    return f"当前时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')} (星期{['一','二','三','四','五','六','日'][now.weekday()]})"
