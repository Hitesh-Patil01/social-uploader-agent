#!/usr/bin/env bash
# Moves new videos from your Google Drive folder into the agent's inbox. Cron runs this every minute.
# Settings (optional): RCLONE_REMOTE (default gdrive) and DRIVE_FOLDER (default social-inbox).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="${RCLONE_REMOTE:-gdrive}:${DRIVE_FOLDER:-social-inbox}"
mkdir -p "$DIR/inbox"
# flock stops two runs from overlapping; --min-age waits until an upload from the phone has finished
exec flock -n /tmp/social-uploader-sync.lock \
  rclone move "$REMOTE" "$DIR/inbox" \
    --include "*.mp4" --include "*.mov" --include "*.m4v" --include "*.txt" \
    --min-age 1m --delete-empty-src-dirs \
    --log-file "$DIR/sync.log" --log-level NOTICE
