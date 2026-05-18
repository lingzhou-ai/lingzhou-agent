"""channels — 外部消息通道入口。"""

from channels.wechat import WechatChannel, WechatConfig, start_wechat_channel

__all__ = ["WechatChannel", "WechatConfig", "start_wechat_channel"]