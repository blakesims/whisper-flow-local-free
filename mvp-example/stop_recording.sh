#/bin/bash


# Create the stop recording file which is located in the same directory as this script, in the 'recording' folder
# first get the current directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
touch $DIR/recordings/stop_recording.txt
echo "Stop recording file created."
