#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Open KB Dashboard
# @raycast.mode silent

# Optional parameters:
# @raycast.icon
# @raycast.packageName Knowledge Base

# Documentation:
# @raycast.description Opens the KB Action Queue Dashboard (running on zen server via Tailscale)
# @raycast.author Blake
# @raycast.authorURL https://github.com/blake

# KB Dashboard URL (via Tailscale)
KB_URL="http://zen:8765"

# Open in default browser
open "$KB_URL"
