import asyncio
import config
import os
import platform
# This adds the VLC directory to the system's DLL search path for the script
if config.VLC_PATH:
    os.add_dll_directory(config.VLC_PATH)
import vlc
import streamlink
import requests
import tkinter as tk
from collections import deque
from random import random, choice

from twitchAPI.type import ChatEvent
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.chat import Chat, EventData, ChatCommand

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
        self.is_resizing = False
        self.is_playing = False
        self.initial_size_set = False # <--- NEW: Flag to control initial size jump
        self.current_w, self.current_h = config.CONFIG["MIN_WINDOW_SIZE"]
        
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

        # If VLC hasn't loaded dimensions yet, return a safe size.
        if video_w <= 0:
            return config.CONFIG["MAX_VIDEO_WIDTH"], 450
        
        scale_factor = config.CONFIG["MAX_VIDEO_WIDTH"] / video_w
        return int(video_w * scale_factor), int(video_h * scale_factor)

    def _update_ui_geometry(self):
        """Smoothly interpolates window size towards the target dimensions."""
        
        if self.is_resizing:
            target_w, target_h = self._get_scaled_dimensions()
            
            # --- START OF FIX: Only initialize size once we have the target dimensions ---
            if not self.initial_size_set and target_w > 0 and target_h > 0:
                
                # 1. Reset to minimum size to ensure a smooth scale-up
                self.current_w, self.current_h = config.CONFIG["MIN_WINDOW_SIZE"]
                
                # 2. Apply 10% 'chaos' shrink to the STARTING dimensions (if triggered)
                if random() < 0.1: 
                    self.current_w = target_w * 0.25
                    self.current_h = target_h * 0.25

                # 3. Set the initial window geometry immediately to the small size
                self.master.geometry(f"{int(self.current_w)}x{int(self.current_h)}")
                
                self.initial_size_set = True # Now we are ready to start interpolation
            # --- END OF FIX ---

            if self.initial_size_set:
                # Smooth interpolation for a 'growing' window effect
                if self.current_w < target_w:
                    # Calculate step size based on the remaining difference
                    self.current_w += max(1, (target_w - self.current_w) * config.CONFIG["RESIZE_SMOOTHNESS"])
                
                if self.current_h < target_h:
                    self.current_h += max(1, (target_h - self.current_h) * config.CONFIG["RESIZE_SMOOTHNESS"])
                
                # Apply the current interpolated size
                self.master.geometry(f"{int(self.current_w)}x{int(self.current_h)}")
                
        self.after(10, self._update_ui_geometry)

    def queue_clip(self, slug):
        """Fetches the stream URL and adds it to the playback queue."""
        try:
            # Use streamlink to get the direct stream URL
            streams = streamlink.streams(f"https://clips.twitch.tv/{slug}")
            if "best" in streams:
                self.queue.append(streams["best"].url)
                if not self.is_playing:
                    self._play_next_in_queue()
            else:
                 print(f"Error: Could not find 'best' stream quality for clip {slug}")
        except Exception as e:
            print(f"Error fetching clip {slug}: {e}")

    def _play_next_in_queue(self):
        """Starts playback of the next URL in the deque."""
        if not self.queue:
            self.is_playing = False
            return
        self.is_playing = True

        url = self.queue.popleft()
        media = self.vlc_instance.media_new(url)
        self.player.set_media(media)

        # --- CHANGE: Reset the flag but DO NOT set the size here ---
        self.initial_size_set = False 
        
        # Reset to MIN size before playback starts, just in case
        self.current_w, self.current_h = config.CONFIG["MIN_WINDOW_SIZE"]
        self.master.geometry(f"{self.current_w}x{self.current_h}")
        
        self.player.play()
        
        # Delay marking as resizing. This delay gives VLC enough time to load the
        # video's actual dimensions (width/height) before the geometry loop starts interpolating.
        self.after(3000, self._set_resizing_state, True)

    def _set_resizing_state(self, state: bool):
        self.is_resizing = state

    def _handle_video_end(self, event):
        """Resets window and prepares for next clip."""
        self.initial_size_set = False # Reset flag for the next clip
        self.current_w, self.current_h = config.CONFIG["MIN_WINDOW_SIZE"]
        self.master.geometry(f"{self.current_w}x{self.current_h}")
        self.is_playing = False
        self.is_resizing = False
        # Brief pause before next clip
        self.after(30, self._play_next_in_queue)

    def shutdown(self):
        self.player.stop()
        self.queue.clear()
        self.is_playing = False
        self.is_resizing = False

class TwitchBot:
    """Handles Twitch API authentication and Shoutout command logic."""
    
    def __init__(self, player_ui):
        self.ui = player_ui
        self.twitch = None
        self.chat = None
        self.token = None

    async def start(self):
        self.twitch = await Twitch(config.CONFIG["CLIENT_ID"], config.CONFIG["CLIENT_SECRET"])
        auth = UserAuthenticator(self.twitch, config.CONFIG["SCOPES"])
        # NOTE: Authentication step is blocking and may require browser interaction
        self.token, refresh_token = await auth.authenticate() 
        await self.twitch.set_user_authentication(self.token, config.CONFIG["SCOPES"], refresh_token)
        
        self.chat = await Chat(self.twitch)
        self.chat.register_event(ChatEvent.READY, self._on_ready)
        self.chat.register_command("so", self._cmd_shoutout)
        self.chat.start()

    async def _on_ready(self, ready_event: EventData):
        print(f"Bot connected to Twitch. Joining #{config.CONFIG['CHANNEL']}")
        await ready_event.chat.join_room(config.CONFIG["CHANNEL"])

    def _get_random_clip_id(self, username):
        headers = {
            'Client-ID': config.CONFIG["CLIENT_ID"],
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
    root.geometry(f"{config.CONFIG['MIN_WINDOW_SIZE'][0]}x{config.CONFIG['MIN_WINDOW_SIZE'][1]}")
    
    player_ui = TwitchClipPlayer(root)
    bot = TwitchBot(player_ui)

    loop = asyncio.new_event_loop()
    
    def process_async_queue():
        """Allows the asyncio loop to run alongside Tkinter."""
        # Stop the event loop to check if the main window is still open
        loop.stop() 
        try:
             # Run pending tasks on the event loop
            loop.run_until_complete(asyncio.sleep(0))
        except RuntimeError:
             # Handle the case where the loop is closed before all tasks run
            pass
        
        if root.winfo_exists():
            root.after(10, process_async_queue) # Schedule next run

    def on_closing():
        player_ui.shutdown()
        # Shut down the asyncio loop and the bot gracefully
        loop.run_until_complete(bot.stop()) 
        loop.close()
        root.destroy()

    # Initialization
    # Start the bot and the chat system
    loop.run_until_complete(bot.start()) 
    root.protocol("WM_DELETE_WINDOW", on_closing)
    # Start the continuous loop to process asyncio tasks
    root.after(10, process_async_queue)
    root.mainloop()

if __name__ == "__main__":
    run_app()
