"""外部消息通道。"""

from .weixin import WeixinApi, WeixinWorker, weixin_manager

__all__ = ["WeixinApi", "WeixinWorker", "weixin_manager"]
