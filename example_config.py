from twitchAPI.type import AuthScope

# IMPORTANT: Replace this with your actual VLC installation path!
# Example paths:
#   vlc_path = r"C:\Program Files\VideoLAN\VLC"   # 64-bit default
#   vlc_path = r"C:\Program Files (x86)\VideoLAN\VLC" # 32-bit default

VLC_PATH = r""

CONFIG = {
    "CLIENT_ID": "",
    "CLIENT_SECRET": "",
    "CHANNEL": "",
    "SCOPES": [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT],
    "MIN_WINDOW_SIZE": (400, 10), # Small initial size
    "MAX_VIDEO_WIDTH": 800,
    "RESIZE_SMOOTHNESS": 0.007
}