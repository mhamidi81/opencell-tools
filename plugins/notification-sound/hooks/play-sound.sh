#!/usr/bin/env bash
# Play a notification sound when Claude asks for user action.
# Uses aplay for WAV or paplay/ogg123 for OGG files.
# Falls back to terminal bell if no sound utility is found.

SOUND_FILE="${NOTIFICATION_SOUND:-/usr/share/sounds/gnome/default/alerts/string.ogg}"

if [ -f "$SOUND_FILE" ]; then
  case "$SOUND_FILE" in
    *.wav)
      if command -v aplay &>/dev/null; then
        aplay -q "$SOUND_FILE" &>/dev/null &
      fi
      ;;
    *.ogg)
      if command -v paplay &>/dev/null; then
        paplay "$SOUND_FILE" &>/dev/null &
      elif command -v ogg123 &>/dev/null; then
        ogg123 -q "$SOUND_FILE" &>/dev/null &
      elif command -v ffplay &>/dev/null; then
        ffplay -nodisp -autoexit -loglevel quiet "$SOUND_FILE" &>/dev/null &
      fi
      ;;
  esac
else
  # Fallback: terminal bell
  printf '\a'
fi

exit 0
