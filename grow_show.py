import asyncio
import platform
import os
import sys

# IMPORTANT: Replace this with your actual VLC installation path!
# Example paths:
#   vlc_path = r"C:\Program Files\VideoLAN\VLC"   # 64-bit default
#   vlc_path = r"C:\Program Files (x86)\VideoLAN\VLC" # 32-bit default

vlc_path = r""

# This adds the VLC directory to the system's DLL search path for the script
os.add_dll_directory(vlc_path)

import vlc
import streamlink
import requests
import tkinter as tk
from collections import deque
from random import random, choice

from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.chat import Chat, EventData, ChatCommand

# --- Configuration ---
CONFIG = {
    "CLIENT_ID": "",
    "CLIENT_SECRET": "",
    "CHANNEL": "",
    "SCOPES": [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT],
    "MIN_WINDOW_SIZE": (400, 10),
    "MAX_VIDEO_WIDTH": 800,
    "RESIZE_SMOOTHNESS": 0.007
}

class TwitchClipPlayer(tk.Frame):
    """A VLC-powered video player embedded in Tkinter that handles Twitch clip playback."""
    
    def __init__(self, master):
        super().__init__(master, bg="")
        self.pack(fill="both", expand=True)

        # VLC Setup
        self.vlc_instance = vlc.Instance()
        self.player = self.vlc_instance.media_player_new()
        self._attach_window_handle()

        # State Management
        self.queue = deque()
        self.is_playing = False
        self.current_w, self.current_h = CONFIG["MIN_WINDOW_SIZE"]
        
        # Event Listeners
        event_manager = self.player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._handle_video_end)

        # Start UI Refresh Loop
        self._update_ui_geometry()

    def _attach_window_handle(self):
        """Attaches the VLC player to the Tkinter frame based on the OS."""
        sys_plat = platform.system()
        window_id = self.winfo_id()
        if sys_plat == "Windows":
            self.player.set_hwnd(window_id)
        elif sys_plat == "Linux":
            self.player.set_xwindow(window_id)
        elif sys_plat == "Darwin":
            self.player.set_nsobject(window_id)

    def _get_scaled_dimensions(self):
        """Calculates dimensions based on video aspect ratio and max width."""
        video_w = self.player.video_get_width()
        video_h = self.player.video_get_height()

        if video_w > 0:
            scale_factor = CONFIG["MAX_VIDEO_WIDTH"] / video_w
            return int(video_w * scale_factor), int(video_h * scale_factor)
        return CONFIG["MAX_VIDEO_WIDTH"], 450

    def _update_ui_geometry(self):
        """Smoothly interpolates window size towards the target dimensions."""
        if self.is_playing:
            target_w, target_h = self._get_scaled_dimensions()
            
            # Smooth interpolation for a 'growing' window effect
            if self.current_w < target_w:
                self.current_w += max(0, (target_w - self.current_w) * CONFIG["RESIZE_SMOOTHNESS"])
            if self.current_h < target_h:
                self.current_h += max(0, (target_h - self.current_h) * CONFIG["RESIZE_SMOOTHNESS"])
            
            self.master.geometry(f"{int(self.current_w)}x{int(self.current_h)}")
            
        self.after(10, self._update_ui_geometry)

    def queue_clip(self, slug):
        """Fetches the stream URL and adds it to the playback queue."""
        try:
            streams = streamlink.streams(f"https://clips.twitch.tv/{slug}")
            if "best" in streams:
                self.queue.append(streams["best"].url)
                if not self.is_playing:
                    self._play_next_in_queue()
        except Exception as e:
            print(f"Error fetching clip {slug}: {e}")

    def _play_next_in_queue(self):
        """Starts playback of the next URL in the deque."""
        if not self.queue:
            self.is_playing = False
            return

        url = self.queue.popleft()
        media = self.vlc_instance.media_new(url)
        self.player.set_media(media)

        # Trigger initial size and random 'chaos' shrink
        self.current_w, self.current_h = self._get_scaled_dimensions()
        if random() < 0.1: # 10% chance of 'mini-mode'
            self.current_w *= 0.25
            self.current_h *= 0.25

        self.master.geometry(f"{int(self.current_w)}x{int(self.current_h)}")
        self.player.play()
        
        # Delay marking as playing to let VLC load video dimensions
        self.after(3000, self._set_playing_state, True)

    def _set_playing_state(self, state: bool):
        self.is_playing = state

    def _handle_video_end(self, event):
        """Resets window and prepares for next clip."""
        self.current_w, self.current_h = CONFIG["MIN_WINDOW_SIZE"]
        self.master.geometry(f"{self.current_w}x{self.current_h}")
        self.is_playing = False
        # Brief pause before next clip
        self.after(30, self._play_next_in_queue)

    def shutdown(self):
        self.player.stop()
        self.queue.clear()
        self.is_playing = False

class TwitchBot:
    """Handles Twitch API authentication and Shoutout command logic."""
    
    def __init__(self, player_ui):
        self.ui = player_ui
        self.twitch = None
        self.chat = None
        self.token = None

    async def start(self):
        self.twitch = await Twitch(CONFIG["CLIENT_ID"], CONFIG["CLIENT_SECRET"])
        auth = UserAuthenticator(self.twitch, CONFIG["SCOPES"])
        self.token, refresh_token = await auth.authenticate()
        await self.twitch.set_user_authentication(self.token, CONFIG["SCOPES"], refresh_token)
        
        self.chat = await Chat(self.twitch)
        self.chat.register_event(ChatEvent.READY, self._on_ready)
        self.chat.register_command("so", self._cmd_shoutout)
        self.chat.start()

    async def _on_ready(self, ready_event: EventData):
        print(f"Bot connected to Twitch. Joining #{CONFIG['CHANNEL']}")
        await ready_event.chat.join_room(CONFIG["CHANNEL"])

    def _get_random_clip_id(self, username):
        headers = {
            'Client-ID': CONFIG["CLIENT_ID"],
            'Authorization': f'Bearer {self.token}'
        }
        # Get User ID
        user_res = requests.get(f'https://api.twitch.tv/helix/users?login={username}', headers=headers)
        user_data = user_res.json().get('data')
        
        if not user_data:
            return None
        
        # Get Clips
        params = {'broadcaster_id': user_data[0]['id'], 'first': 100}
        clips_res = requests.get('https://api.twitch.tv/helix/clips', headers=headers, params=params)
        clips_data = clips_res.json().get('data')
        
        return choice(clips_data)['id'] if clips_data else None

    async def _cmd_shoutout(self, cmd: ChatCommand):
        target_user = cmd.parameter.replace("@", "").strip()
        if not target_user:
            return

        clip_id = self._get_random_clip_id(target_user)
        if clip_id:
            # Safely schedule the UI update back on the Tkinter thread
            self.ui.master.after(0, lambda: self.ui.queue_clip(clip_id))

    async def stop(self):
        if self.chat:
            self.chat.stop()
        if self.twitch:
            await self.twitch.close()

def run_app():
    root = tk.Tk()
    root.title("Twitch Clip SO")
    root.geometry(f"{CONFIG['MIN_WINDOW_SIZE'][0]}x{CONFIG['MIN_WINDOW_SIZE'][1]}")
    
    player_ui = TwitchClipPlayer(root)
    bot = TwitchBot(player_ui)

    loop = asyncio.new_event_loop()
    
    def process_async_queue():
        """Allows the asyncio loop to run alongside Tkinter."""
        loop.stop()
        loop.run_forever()
        root.after(10, process_async_queue)

    def on_closing():
        player_ui.shutdown()
        loop.run_until_complete(bot.stop())
        root.destroy()

    # Initialization
    loop.run_until_complete(bot.start())
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.after(10, process_async_queue)
    root.mainloop()

if __name__ == "__main__":
    run_app()
