#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Open KB Browse
# @raycast.mode silent

# Optional parameters:
# @raycast.icon
# @raycast.packageName Knowledge Base

# Documentation:
# @raycast.description Opens the KB Browse Mode to search and view transcripts
# @raycast.author Blake
# @raycast.authorURL https://github.com/blake

# KB Browse URL (via Tailscale)
KB_URL="http://zen:8765/browse"

# Open in default browser
open "$KB_URL"
