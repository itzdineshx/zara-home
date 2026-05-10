from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import urllib.parse
import urllib.request
import webbrowser
from typing import TYPE_CHECKING, Any

from app.config import Settings

if TYPE_CHECKING:
    from app.services.mcp_service import MCPService
    from app.services.mode_state import ModeState
    from app.services.mqtt_home import MQTTHomeAutomationController


logger = logging.getLogger(__name__)


class AutomationEngine:
    """Safe rule-based automation. No arbitrary command execution."""

    ENGINE_ALIAS_RE = re.compile(
        r"\b(?:injin|enjin|engin|ingine|injan|njin|enginee|engin)\b",
        re.IGNORECASE,
    )
    ENGINE_SPLIT_ALIAS_RE = re.compile(r"\b(?:in|en)\s+gin\b", re.IGNORECASE)
    TURN_OR_SWITCH_OF_RE = re.compile(r"\b(turn|switch)\s+of\b", re.IGNORECASE)
    COMPACT_TURNOFF_RE = re.compile(r"\b(turn|switch)off\b", re.IGNORECASE)
    ENGINE_OF_RE = re.compile(r"\bengine\s+of\b", re.IGNORECASE)
    ENGINE_KEYWORD_RE = re.compile(r"\bengine\b", re.IGNORECASE)
    ENGINE_ON_HINT_RE = re.compile(r"\b(turn|switch|set|enable|start|run|spin)\s+on\b|\bstart\b|\bon\b", re.IGNORECASE)
    ENGINE_OFF_HINT_RE = re.compile(
        r"\b(turn|switch|set|disable|stop)\s+off\b|\boff\b|\bstop\b|\bshutdown\b|\bshut\s*down\b",
        re.IGNORECASE,
    )
    LIGHT_KEYWORD_RE = re.compile(r"\b(light|lights|led|leds)\b", re.IGNORECASE)
    LIGHT_ON_HINT_RE = re.compile(r"\b(turn|switch|start)\s+on\b|\bon\b", re.IGNORECASE)
    LIGHT_OFF_HINT_RE = re.compile(r"\b(turn|switch|stop)\s+off\b|\boff\b", re.IGNORECASE)

    COMMAND_REPLACEMENTS: tuple[tuple[str, str], ...] = (
        # Engine intent phrases
        ("engine chalu karo", "turn on engine"),
        ("इंजन चालू करो", "turn on engine"),
        ("எஞ்சின் ஆன் பண்ணு", "turn on engine"),
        ("engine on pannu", "turn on engine"),
        ("ఇంజిన్ ఆన్ చేయి", "turn on engine"),
        ("engine on chey", "turn on engine"),
        ("എഞ്ചിൻ ഓൺ ആക്കു", "turn on engine"),
        ("engine on aakku", "turn on engine"),

















        
        ("engine band karo", "turn off engine"),
        ("इंजन बंद करो", "turn off engine"),
        ("எஞ்சின் ஆஃப் பண்ணு", "turn off engine"),
        ("engine off pannu", "turn off engine"),
        ("ఇంజిన్ ఆఫ్ చేయి", "turn off engine"),
        ("engine off chey", "turn off engine"),
        ("എഞ്ചിൻ ഓഫ് ആക്കു", "turn off engine"),
        ("engine off aakku", "turn off engine"),
        # Platform names
        ("यूट्यूब", "youtube"),
        ("யூடியூப்", "youtube"),
        ("యూట్యూబ్", "youtube"),
        ("യൂട്യൂബ്", "youtube"),
        ("स्पॉटिफाई", "spotify"),
        ("ஸ்பாட்டிஃபை", "spotify"),
        ("స్పాటిఫై", "spotify"),
        ("സ്പോട്ടിഫൈ", "spotify"),
        ("गूगल मैप्स", "google maps"),
        ("கூகுள் மேப்ஸ்", "google maps"),
        ("గూగుల్ మ్యాప్స్", "google maps"),
        ("ഗൂഗിൾ മാപ്സ്", "google maps"),
        ("जीमेल", "gmail"),
        ("ஜிமெயில்", "gmail"),
        ("జిమెయిల్", "gmail"),
        ("ജിമെയിൽ", "gmail"),
        ("गूगल", "google"),
        ("கூகுள்", "google"),
        ("గూగుల్", "google"),
        ("ഗൂഗിൾ", "google"),
        ("गिटहब", "github"),
        ("கிட்ஹப்", "github"),
        ("గిట్ హబ్", "github"),
        ("ഗിറ്റ്ഹബ്", "github"),
        # Core verbs
        ("खोल दो", "open"),
        ("खोलो", "open"),
        ("खोल", "open"),
        ("khol do", "open"),
        ("kholo", "open"),
        ("khol", "open"),
        ("திறக்க", "open"),
        ("திற", "open"),
        ("thirakka", "open"),
        ("thira", "open"),
        ("తెరవండి", "open"),
        ("తెరవు", "open"),
        ("తెరువు", "open"),
        ("ఓపెన్ చేయి", "open"),
        ("open చేయి", "open"),
        ("ఓపెన్", "open"),
        ("teravandi", "open"),
        ("teruvu", "open"),
        ("തുറക്കൂ", "open"),
        ("തുറക്ക", "open"),
        ("തുറ", "open"),
        ("thurakku", "open"),
        ("चलाओ", "play"),
        ("बजाओ", "play"),
        ("ப்ளே", "play"),
        ("play pannu", "play"),
        ("ప్లే", "play"),
        ("play chey", "play"),
        ("കളി", "play"),
        ("play cheyyu", "play"),
        ("ढूंढो", "search"),
        ("खोजो", "search"),
        ("தேடு", "search"),
        ("தேட", "search"),
        ("வெதுக்கு", "search"),
        ("வெச்சு பார்", "search"),
        ("వెతుకు", "search"),
        ("వెతకండి", "search"),
        ("തിരയൂ", "search"),
        ("തിരയു", "search"),
        ("തേടു", "search"),
    )

    YOUTUBE_RE = re.compile(
        r"\b(open|launch|start|visit|go to)\s+(youtube|yt)\b|\b(youtube|yt)\s+(open|launch|start|visit)\b",
        re.IGNORECASE,
    )
    YOUTUBE_PLAY_RE = re.compile(
        r"\b(play|put on|search|find|look up)\s+(?P<query>.+?)\s+(on|in)\s+(youtube|yt)\b",
        re.IGNORECASE,
    )
    YOUTUBE_PLAY_TAIL_RE = re.compile(
        r"\b(play|put on|search|find|look up)\s+(?P<query>.+?)\s+(youtube|yt)\b",
        re.IGNORECASE,
    )
    YOUTUBE_PLAY_PREFIX_RE = re.compile(
        r"\b(youtube|yt)\s+(play|put on|search|find|look up)\s+(?P<query>.+)\b",
        re.IGNORECASE,
    )
    YOUTUBE_SEARCH_PLAY_RE = re.compile(
        r"\bsearch\s+(?P<query>.+?)\s+(on|in)?\s*(youtube|yt)\b(?:\s+and\s+play|\s+play)?",
        re.IGNORECASE,
    )
    SPOTIFY_RE = re.compile(
        r"\b(open|launch|start|visit)\s+spotify\b|\bspotify\s+(open|launch|start|visit)\b",
        re.IGNORECASE,
    )
    SPOTIFY_PLAY_RE = re.compile(
        r"\b(play|put on|search|find)\s+(?P<query>.+?)\s+(on|in)\s+spotify\b",
        re.IGNORECASE,
    )
    SPOTIFY_PLAY_TAIL_RE = re.compile(
        r"\b(play|put on|search|find)\s+(?P<query>.+?)\s+spotify\b",
        re.IGNORECASE,
    )
    SPOTIFY_PLAY_PREFIX_RE = re.compile(
        r"\bspotify\s+(play|put on|search|find)\s+(?P<query>.+)\b",
        re.IGNORECASE,
    )
    DEFAULT_SPOTIFY_PLAY_RE = re.compile(
        r"\b(play|put on|start)\s+(?P<query>.+)$",
        re.IGNORECASE,
    )
    SPOTIFY_SEARCH_PLAY_RE = re.compile(
        r"\bsearch\s+(?P<query>.+?)\s+(on|in)?\s*spotify\b(?:\s+and\s+play|\s+play)?",
        re.IGNORECASE,
    )
    SPOTIFY_MUSIC_RE = re.compile(
        r"\b(play|start)\s+(some\s+)?(music|songs?)\s*((on|in)\s+)?spotify\b|\bspotify\s+(play|start)\s+(some\s+)?(music|songs?)\b",
        re.IGNORECASE,
    )
    MAPS_RE = re.compile(r"\b(open|launch|start)\s+(google\s+)?maps\b|\b(google\s+)?maps\s+(open|launch|start)\b", re.IGNORECASE)
    NAVIGATE_RE = re.compile(r"\b(navigate|directions?|route)\s+(to\s+)?(?P<destination>.+)$", re.IGNORECASE)
    TAKE_ME_TO_RE = re.compile(r"\b(take me to|show me route to)\s+(?P<destination>.+)$", re.IGNORECASE)
    MAPS_TO_RE = re.compile(r"\bmaps\s+to\s+(?P<destination>.+)$", re.IGNORECASE)
    GMAIL_RE = re.compile(r"\b(open|launch)\s+gmail\b|\bgmail\s+(open|launch)\b", re.IGNORECASE)
    GOOGLE_RE = re.compile(r"\b(open|launch)\s+google\b|\bgoogle\s+(open|launch)\b", re.IGNORECASE)
    GITHUB_RE = re.compile(r"\b(open|launch)\s+github\b|\bgithub\s+(open|launch)\b", re.IGNORECASE)
    GENERIC_SITE_RE = re.compile(
        r"\b(open|launch|visit)\s+(?P<domain>(?:[a-z0-9-]+\.)+[a-z]{2,})(?P<path>/[^\s]*)?\b",
        re.IGNORECASE,
    )
    SEARCH_RE = re.compile(r"\b(search|find|look up)\s+(for\s+)?(?P<query>.+)", re.IGNORECASE)
    TIME_RE = re.compile(r"\b(what(?:'s| is)?\s+the\s+time|current\s+time)\b", re.IGNORECASE)
    DATE_RE = re.compile(r"\b(what(?:'s| is)?\s+the\s+date|today'?s\s+date)\b", re.IGNORECASE)
    ENGINE_ON_RE = re.compile(
        r"\b(turn|switch|set|enable)\s+on\s+(the\s+)?engine\b|\bstart\s+(the\s+)?engine\b|\bengine\s+on\b",
        re.IGNORECASE,
    )
    ENGINE_OFF_RE = re.compile(
        r"\b(turn|switch|set|disable)\s+off\s+(the\s+)?engine\b|\bstop\s+(the\s+)?engine\b|\bengine\s+off\b",
        re.IGNORECASE,
    )
    HOME_LED_ON_RE = re.compile(
        r"\b(?:turn|switch)\s+on\s+(?:the\s+|all\s+)?(?:light|lights|led|leds)\b"
        r"|\bstart\s+(?:the\s+|all\s+)?(?:light|lights|led|leds)\b"
        r"|\b(?:light|lights|led|leds)\s+on\b",
        re.IGNORECASE,
    )
    HOME_LED_OFF_RE = re.compile(
        r"\b(?:turn|switch)\s+(?:off|of)\s+(?:the\s+|all\s+)?(?:light|lights|led|leds)\b"
        r"|\bstop\s+(?:the\s+|all\s+)?(?:light|lights|led|leds)\b"
        r"|\b(?:turn|switch|stop)\s+(?:the\s+|all\s+)?(?:light|lights|led|leds)\s+(?:off|of)\b"
        r"|\b(?:light|lights|led|leds)\s+(?:off|of)\b",
        re.IGNORECASE,
    )
    YOUTUBE_VIDEO_ID_RE = re.compile(r'"videoId":"(?P<id>[A-Za-z0-9_-]{11})"')

    HOME_LIGHT_ON_RE = re.compile(
        r"\b(?:turn|switch|set|enable|start)\s+on\s+(?:the\s+|all\s+)?(?:light|lights|lamp|lamps|bulb|bulbs|led|leds)\b"
        r"|\b(?:light|lights|lamp|lamps|bulb|bulbs|led|leds)\s+on\b",
        re.IGNORECASE,
    )
    HOME_LIGHT_OFF_RE = re.compile(
        r"\b(?:turn|switch|set|disable|stop)\s+(?:off|of)\s+(?:the\s+|all\s+)?(?:light|lights|lamp|lamps|bulb|bulbs|led|leds)\b"
        r"|\b(?:light|lights|lamp|lamps|bulb|bulbs|led|leds)\s+(?:off|of)\b",
        re.IGNORECASE,
    )
    HOME_FAN_ON_RE = re.compile(r"\b(?:turn|switch|set|enable|start)\s+on\s+(?:the\s+)?fan\b|\bfan\s+on\b", re.IGNORECASE)
    HOME_FAN_OFF_RE = re.compile(r"\b(?:turn|switch|set|disable|stop)\s+(?:off|of)\s+(?:the\s+)?fan\b|\bfan\s+(?:off|of)\b", re.IGNORECASE)
    HOME_AC_ON_RE = re.compile(
        r"\b(?:turn|switch|set|enable|start)\s+on\s+(?:the\s+)?(?:ac|air\s+conditioner|air\s+conditioning|cooler)\b"
        r"|\b(?:ac|air\s+conditioner|air\s+conditioning|cooler)\s+on\b",
        re.IGNORECASE,
    )
    HOME_AC_OFF_RE = re.compile(
        r"\b(?:turn|switch|set|disable|stop)\s+(?:off|of)\s+(?:the\s+)?(?:ac|air\s+conditioner|air\s+conditioning|cooler)\b"
        r"|\b(?:ac|air\s+conditioner|air\s+conditioning|cooler)\s+(?:off|of)\b",
        re.IGNORECASE,
    )
    HOME_TV_ON_RE = re.compile(r"\b(?:turn|switch|set|enable|start)\s+on\s+(?:the\s+)?tv\b|\btv\s+on\b|\btelevision\s+on\b", re.IGNORECASE)
    HOME_TV_OFF_RE = re.compile(r"\b(?:turn|switch|set|disable|stop)\s+(?:off|of)\s+(?:the\s+)?tv\b|\btv\s+(?:off|of)\b|\btelevision\s+off\b", re.IGNORECASE)
    HOME_CURTAIN_OPEN_RE = re.compile(
        r"\b(?:open|draw|raise)\s+(?:the\s+)?(?:curtain|curtains|blind|blinds)\b|\b(?:curtain|curtains|blind|blinds)\s+open\b",
        re.IGNORECASE,
    )
    HOME_CURTAIN_CLOSE_RE = re.compile(
        r"\b(?:close|shut|lower)\s+(?:the\s+)?(?:curtain|curtains|blind|blinds)\b|\b(?:curtain|curtains|blind|blinds)\s+close\b",
        re.IGNORECASE,
    )
    HOME_DOOR_LOCK_RE = re.compile(r"\b(?:lock|secure|lock\s+the)\s+(?:main\s+)?door\b|\bdoor\s+lock\b", re.IGNORECASE)
    HOME_DOOR_UNLOCK_RE = re.compile(r"\b(?:unlock|open|unsecure)\s+(?:the\s+)?(?:main\s+)?door\b|\bdoor\s+unlock\b", re.IGNORECASE)
    HOME_ALL_ON_RE = re.compile(r"\b(?:turn|switch|set|enable|start)\s+everything\s+on\b|\ball\s+on\b", re.IGNORECASE)
    HOME_ALL_OFF_RE = re.compile(r"\b(?:turn|switch|set|disable|stop)\s+everything\s+off\b|\ball\s+off\b", re.IGNORECASE)
    HOME_STATUS_CHECK_RE = re.compile(r"\bstatus\s+check\b|\bcheck\s+status\b|\bhome\s+status\b", re.IGNORECASE)
    HOME_SCENE_GOOD_MORNING_RE = re.compile(r"\b(good\s+morning|morning\s+scene|wake\s+up\s+scene)\b", re.IGNORECASE)
    HOME_SCENE_GOOD_NIGHT_RE = re.compile(r"\b(good\s+night|night\s+scene|sleep\s+scene)\b", re.IGNORECASE)
    HOME_SCENE_AWAY_RE = re.compile(r"\b(away\s+mode|leave\s+home|exit\s+mode)\b", re.IGNORECASE)
    HOME_SCENE_HOME_RE = re.compile(r"\b(home\s+mode|i'?m\s+home|welcome\s+home)\b", re.IGNORECASE)

    def __init__(
        self,
        settings: Settings,
        mcp_service: MCPService | None = None,
        mode_state: ModeState | None = None,
        home_controller: MQTTHomeAutomationController | None = None,
    ) -> None:
        self.settings = settings
        self.mcp_service = mcp_service
        self.mode_state = mode_state
        self.home_controller = home_controller

    async def detect_and_execute(self, text: str, language_code: str | None = None) -> dict[str, Any] | None:
        normalized = self._canonicalize_command_text(text)
        if not normalized:
            return None

        home_result = await self._detect_and_execute_home_command(normalized)
        if home_result is not None:
            return self._with_language(home_result, language_code)

        if self.HOME_ALL_OFF_RE.search(normalized):
            result = await self._trigger_home_command("all_off")
            return self._with_language(result, language_code)

        if self.HOME_ALL_ON_RE.search(normalized):
            result = await self._trigger_home_command("all_on")
            return self._with_language(result, language_code)

        if self.HOME_STATUS_CHECK_RE.search(normalized):
            result = await self._trigger_home_command("status_check")
            return self._with_language(result, language_code)

        if self.SPOTIFY_MUSIC_RE.search(normalized):
            result = await self._open_url(
                "https://open.spotify.com/genre/0JQ5DAqbMKFQ00XGBls6ym",
                action_type="spotify_music",
                intent="Play music on Spotify",
            )
            return self._with_language(result, language_code)

        spotify_query = self._extract_spotify_query(normalized)
        if spotify_query:
            url = f"https://open.spotify.com/search/{urllib.parse.quote(spotify_query)}/tracks"
            result = await self._open_url(url, action_type="spotify_play", intent="Play track on Spotify")
            result["query"] = spotify_query
            result["spotify_uri"] = f"spotify:search:{urllib.parse.quote(spotify_query)}"
            result["fallback_target"] = url
            result["autoplay"] = True
            return self._with_language(result, language_code)

        if self.SPOTIFY_RE.search(normalized):
            result = await self._open_url(
                "https://open.spotify.com",
                action_type="open_spotify",
                intent="Open Spotify",
            )
            return self._with_language(result, language_code)

        youtube_query = self._extract_youtube_query(normalized)
        if youtube_query:
            url, video_id = await self._resolve_youtube_play_url(youtube_query)
            result = await self._open_url(url, action_type="youtube_play", intent="Play video on YouTube")
            result["query"] = youtube_query
            result["autoplay"] = True
            if video_id:
                result["video_id"] = video_id
            return self._with_language(result, language_code)

        default_spotify_query = self._extract_default_spotify_query(normalized)
        if default_spotify_query:
            if default_spotify_query == "__SPOTIFY_MUSIC__":
                result = await self._open_url(
                    "https://open.spotify.com/genre/0JQ5DAqbMKFQ00XGBls6ym",
                    action_type="spotify_music",
                    intent="Play music on Spotify",
                )
                result["autoplay"] = True
                result["default_platform"] = "spotify"
                return self._with_language(result, language_code)

            url = f"https://open.spotify.com/search/{urllib.parse.quote(default_spotify_query)}/tracks"
            result = await self._open_url(url, action_type="spotify_play", intent="Play track on Spotify")
            result["query"] = default_spotify_query
            result["spotify_uri"] = f"spotify:search:{urllib.parse.quote(default_spotify_query)}"
            result["fallback_target"] = url
            result["autoplay"] = True
            result["default_platform"] = "spotify"
            return self._with_language(result, language_code)

        if self.YOUTUBE_RE.search(normalized):
            result = await self._open_url("https://www.youtube.com", action_type="open_youtube", intent="Open YouTube")
            return self._with_language(result, language_code)

        destination = self._extract_maps_destination(normalized)
        if destination:
            url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(destination)}"
            result = await self._open_url(url, action_type="open_maps", intent="Open map directions")
            result["destination"] = destination
            return self._with_language(result, language_code)

        if self.MAPS_RE.search(normalized):
            result = await self._open_url(
                "https://www.google.com/maps",
                action_type="open_maps",
                intent="Open Google Maps",
            )
            return self._with_language(result, language_code)

        if self.GMAIL_RE.search(normalized):
            result = await self._open_url("https://mail.google.com", action_type="open_gmail", intent="Open Gmail")
            return self._with_language(result, language_code)

        if self.GITHUB_RE.search(normalized):
            result = await self._open_url("https://github.com", action_type="open_github", intent="Open GitHub")
            return self._with_language(result, language_code)

        if self.GOOGLE_RE.search(normalized):
            result = await self._open_url("https://www.google.com", action_type="open_google", intent="Open Google")
            return self._with_language(result, language_code)

        generic_site_match = self.GENERIC_SITE_RE.search(normalized)
        if generic_site_match:
            domain = generic_site_match.group("domain").strip().lower()
            path = (generic_site_match.group("path") or "").strip()
            url = f"https://{domain}{path}"
            result = await self._open_url(url, action_type="open_website", intent="Open website")
            result["domain"] = domain
            return self._with_language(result, language_code)

        search_match = self.SEARCH_RE.search(normalized)
        if search_match:
            query = search_match.group("query").strip()
            if query:
                url = f"https://duckduckgo.com/?q={urllib.parse.quote_plus(query)}"
                result = await self._open_url(url, action_type="web_search", intent="Run web search")
                result["query"] = query
                return self._with_language(result, language_code)

        if self.TIME_RE.search(normalized):
            current_time = dt.datetime.now().strftime("%H:%M")
            return self._with_language(
                {
                "type": "system_time",
                "status": "resolved",
                "value": current_time,
                },
                language_code,
            )

        if self.DATE_RE.search(normalized):
            current_date = dt.datetime.now().strftime("%Y-%m-%d")
            return self._with_language(
                {
                "type": "system_date",
                "status": "resolved",
                "value": current_date,
                },
                language_code,
            )

        return None

    async def _detect_and_execute_home_command(self, normalized: str) -> dict[str, Any] | None:
        action = self._match_home_action(normalized)
        if not action:
            return None

        if not self.mode_state:
            return {
                "type": action,
                "action": action,
                "domain": "home",
                "status": "failed",
                "error": "Home automation state is unavailable",
            }

        home_automation_enabled = await self.mode_state.is_home_automation_enabled()
        if not home_automation_enabled:
            return {
                "type": action,
                "action": action,
                "domain": "home",
                "status": "blocked_home_mode",
                "detail": "Home Automation is OFF. Enable it in settings to send device commands.",
            }

        if not self.home_controller:
            return {
                "type": action,
                "action": action,
                "domain": "home",
                "status": "failed",
                "error": "MQTT home controller is unavailable",
            }

        result = await self.home_controller.publish_action(action)
        result.setdefault("domain", "home")
        result.setdefault("action", action)
        return result

    def _match_home_action(self, normalized: str) -> str | None:
        if self.HOME_LIGHT_ON_RE.search(normalized):
            return "light_on"
        if self.HOME_LIGHT_OFF_RE.search(normalized):
            return "light_off"
        if self.HOME_FAN_ON_RE.search(normalized):
            return "fan_on"
        if self.HOME_FAN_OFF_RE.search(normalized):
            return "fan_off"
        if self.HOME_AC_ON_RE.search(normalized):
            return "ac_on"
        if self.HOME_STATUS_CHECK_RE.search(normalized):
            return "status_check"
        if self.HOME_AC_OFF_RE.search(normalized):
            return "ac_off"
        if self.HOME_TV_ON_RE.search(normalized):
            return "tv_on"
        if self.HOME_TV_OFF_RE.search(normalized):
            return "tv_off"
        if self.HOME_CURTAIN_OPEN_RE.search(normalized):
            return "curtain_open"
        if self.HOME_CURTAIN_CLOSE_RE.search(normalized):
            return "curtain_close"
        if self.HOME_DOOR_LOCK_RE.search(normalized):
            return "door_lock"
        if self.HOME_DOOR_UNLOCK_RE.search(normalized):
            return "door_unlock"
        if self.HOME_SCENE_GOOD_MORNING_RE.search(normalized):
            return "scene_good_morning"
        if self.HOME_SCENE_GOOD_NIGHT_RE.search(normalized):
            return "scene_good_night"
        if self.HOME_SCENE_AWAY_RE.search(normalized):
            return "scene_away"
        if self.HOME_SCENE_HOME_RE.search(normalized):
            return "scene_home"

        fuzzy_action = self._match_home_action_fuzzy(normalized)
        if fuzzy_action:
            return fuzzy_action

        return None

    def _match_home_action_fuzzy(self, normalized: str) -> str | None:
        if re.search(r"\b(?:lights?|lamps?|bulbs?|leds?)\b", normalized, re.IGNORECASE):
            if re.search(r"\b(?:on|start|enable|open)\b", normalized, re.IGNORECASE):
                return "light_on"
            if re.search(r"\b(?:off|stop|disable|close)\b", normalized, re.IGNORECASE):
                return "light_off"

        if re.search(r"\bfan\b", normalized, re.IGNORECASE):
            if re.search(r"\b(?:on|start|enable)\b", normalized, re.IGNORECASE):
                return "fan_on"
            if re.search(r"\b(?:off|stop|disable)\b", normalized, re.IGNORECASE):
                return "fan_off"

        return None

    def _canonicalize_command_text(self, text: str) -> str:
        normalized = " ".join(text.strip().lower().split())
        normalized = normalized.replace("_", " ").replace("-", " ")
        normalized = re.sub(r"[^\w\s]", " ", normalized)

        normalized = re.sub(r"^(?:hey|hi|hello|ok|okay|please|kindly)\s+", "", normalized)
        normalized = re.sub(r"^(?:can you|could you|would you)\s+", "", normalized)
        normalized = re.sub(r"^zara\s+", "", normalized)
        ordered_replacements = sorted(self.COMMAND_REPLACEMENTS, key=lambda item: len(item[0]), reverse=True)

        for source, target in ordered_replacements:
            normalized = normalized.replace(source, target)

        # Handle common ASR token mistakes around "off".
        normalized = self.TURN_OR_SWITCH_OF_RE.sub(r"\1 off", normalized)
        normalized = self.COMPACT_TURNOFF_RE.sub(r"\1 off", normalized)

        return normalized

    async def _trigger_home_command(self, action: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": action,
            "status": "planned",
            "intent": "Execute home automation command",
        }

        if not self.settings.automation_execute:
            return payload

        try:
            if not self.home_controller:
                raise RuntimeError("MQTT home controller is unavailable")
            result = await self.home_controller.publish_action(action)
            payload.update(result)
            payload["status"] = result.get("status", "executed")
        except Exception as exc:
            payload["status"] = "failed"
            payload["error"] = str(exc)

        return payload

    def _with_language(self, payload: dict[str, Any], language_code: str | None) -> dict[str, Any]:
        if language_code:
            payload["language"] = language_code
        return payload

    async def _open_url(self, url: str, action_type: str, intent: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": action_type,
            "status": "planned",
            "target": url,
            "intent": intent,
            "mcp_server": "zara-browser-mcp",
            "mcp_tool": self.settings.mcp_open_url_tool,
            "mcp_url": url,
        }

        if not self.settings.automation_execute:
            return payload

        if self.mcp_service and self.mcp_service.enabled:
            mcp_result = await self.mcp_service.call_tool(
                tool_name=self.settings.mcp_open_url_tool,
                arguments={
                    "url": url,
                    "new_tab": True,
                    "intent": intent,
                },
            )

            payload["status"] = "executed" if bool(mcp_result.get("ok")) else "failed"
            payload["mcp_transport"] = self.mcp_service.transport

            if mcp_result.get("result") is not None:
                payload["mcp_result"] = mcp_result.get("result")
            if mcp_result.get("error"):
                payload["error"] = mcp_result.get("error")

            if payload["status"] == "failed":
                try:
                    await asyncio.to_thread(webbrowser.open_new_tab, url)
                    payload["status"] = "executed_fallback"
                    payload["executor"] = "local_browser"
                except Exception as exc:
                    payload["fallback_error"] = str(exc)

            return payload

        try:
            await asyncio.to_thread(webbrowser.open_new_tab, url)
            payload["status"] = "executed"
            payload["executor"] = "local_browser"
        except Exception as exc:
            payload["status"] = "failed"
            payload["error"] = str(exc)

        return payload

    async def _resolve_youtube_play_url(self, query: str) -> tuple[str, str | None]:
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"

        try:
            video_id = await asyncio.to_thread(self._fetch_first_youtube_video_id, search_url)
        except Exception as exc:
            logger.debug("YouTube video resolution failed for query=%s: %s", query, exc)
            video_id = None

        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}&autoplay=1", video_id

        # Fallback to videos tab search when direct video lookup fails.
        return f"{search_url}&sp=EgIQAQ%253D%253D", None

    def _fetch_first_youtube_video_id(self, search_url: str) -> str | None:
        request = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=4) as response:
            page = response.read().decode("utf-8", errors="ignore")

        seen: set[str] = set()
        for match in self.YOUTUBE_VIDEO_ID_RE.finditer(page):
            candidate = match.group("id")
            if candidate in seen:
                continue
            seen.add(candidate)
            return candidate

        return None

    def _sanitize_media_query(self, query: str, platform: str) -> str:
        cleaned = " ".join(query.strip().split())
        cleaned = re.sub(r"^(and\s+play|and\s+search|play\s+and\s+search)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^search\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^(the\s+song|song|songs?)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"^(some|any)\s+(songs?|music|videos?)\s+(from|of|by)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^(songs?|music|videos?)\s+(from|of|by)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^(some|any)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+(and\s+play|play\s+it|right\s+now|please)$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+(on|in)\s+(spotify|youtube|yt)$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+(spotify|youtube|yt)$", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(" .,!?")

        lower_cleaned = cleaned.lower()

        if platform == "spotify" and lower_cleaned in {"music", "song", "songs", "track", "tracks"}:
            return ""

        if platform == "youtube" and lower_cleaned in {"video", "videos", "song", "songs", "music"}:
            return "latest music video"

        if cleaned:
            return cleaned

        return "latest songs" if platform == "spotify" else "latest music video"

    def _extract_spotify_query(self, normalized: str) -> str | None:
        patterns = (
            self.SPOTIFY_PLAY_RE,
            self.SPOTIFY_PLAY_TAIL_RE,
            self.SPOTIFY_PLAY_PREFIX_RE,
            self.SPOTIFY_SEARCH_PLAY_RE,
        )

        for pattern in patterns:
            match = pattern.search(normalized)
            if not match:
                continue

            query = self._sanitize_media_query(match.group("query"), platform="spotify")
            if query:
                return query

        return None

    def _extract_youtube_query(self, normalized: str) -> str | None:
        patterns = (
            self.YOUTUBE_PLAY_RE,
            self.YOUTUBE_PLAY_TAIL_RE,
            self.YOUTUBE_PLAY_PREFIX_RE,
            self.YOUTUBE_SEARCH_PLAY_RE,
        )

        for pattern in patterns:
            match = pattern.search(normalized)
            if not match:
                continue

            query = self._sanitize_media_query(match.group("query"), platform="youtube")
            if query:
                return query

        return None

    def _extract_maps_destination(self, normalized: str) -> str | None:
        patterns = (self.NAVIGATE_RE, self.TAKE_ME_TO_RE, self.MAPS_TO_RE)
        for pattern in patterns:
            match = pattern.search(normalized)
            if not match:
                continue

            destination = " ".join((match.group("destination") or "").strip().split())
            destination = re.sub(r"\s+(in\s+)?maps?$", "", destination, flags=re.IGNORECASE).strip(" .,!?")
            if destination:
                return destination

        return None

    def _extract_default_spotify_query(self, normalized: str) -> str | None:
        match = self.DEFAULT_SPOTIFY_PLAY_RE.search(normalized)
        if not match:
            return None

        raw_query = " ".join(match.group("query").strip().split())
        if not raw_query:
            return None

        # Respect explicit platform/service commands handled elsewhere.
        if re.search(
            r"\b(youtube|yt|video|videos|maps?|navigate|route|direction|gmail|github|google|search\s+for|web\s+search)\b",
            raw_query,
            flags=re.IGNORECASE,
        ):
            return None

        if re.fullmatch(r"(music|songs?|playlist)", raw_query, flags=re.IGNORECASE):
            return "__SPOTIFY_MUSIC__"

        query = self._sanitize_media_query(raw_query, platform="spotify")
        if not query:
            return None

        return query
