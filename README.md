# grow-show

A Twitch shoutout player that grows, and then shows

## Windows Installation Instructions

### Pre-requisites

1. Python
2. VLC Media Player

### Installation

1. Go to https://dev.twitch.tv and create an application. Note the client ID. Create a new secret and note the token. Set the redirect URL to http://localhost:17563.
2. Install dependencies
   1. `pip install streamlink`
   2. `pip install twitchAPI`
   3. `pip install python-vlc`
3. Copy example_config.py to config.py and update
   1. `vlc_path` to the directory containing your VLC installation
   2. `CLIENT_ID` to the client ID of your Twitch app
   3. `CLIENT_SECRET` to the token created during creation of the Twitch app
   4. `CHANNEL` to your Twitch channel name
4. Run the script in a command prompt: `python grow_show.py`
5. In OBS, add a Window Capture and make sure the mode is set to "Windows 10 (1903 and up)" and be sure to add an Application Audio source for the clip audio.
