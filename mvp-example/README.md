pbpaste | fabric -sp explain_project
# PROJECT OVERVIEW

Automates audio recording, transcription, and optional Fabric response generation with Whisper AI integration.
Puts local whisper ai together into the same script as running a fabric command. The options are presented to the user to enter in manually when running the script. 
To run the script you need to activate the python virtual env to manage packages so that whisper ai will work locally.

# THE PROBLEM IT ADDRESSES

Simplifies the process of recording, transcribing, and generating responses from audio inputs from llms given a fabric pattern.

# THE APPROACH TO SOLVING THE PROBLEM

Combines audio recording, Whisper AI transcription, and Fabric response generation into a seamless workflow.

# INSTALLATION

- Clone the repository.
- Navigate to the project directory.
- Create a virtual environment: `python -m venv fabric-app-venv`
- Activate the virtual environment: `source fabric-app-venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`

# USAGE
## Simple and quick transcription using whisper locally

- Run the script in automated mode: `./run_transcription.sh`
	- This runs the quick and dirty version of the main script that just transcribes the recording to text and copies to clipboard
## Full usage

- Activate the virtual environment: `source fabric-app-venv/bin/activate`
- For manual mode, run: `python transcribe_pattern.py --language <language> --model <model>`

# EXAMPLE

- Activate the virtual environment: `source fabric-app-venv/bin/activate`

- Record and transcribe audio in English: `python transcribe_pattern.py --language english`
- Transcribe and translate Thai audio to English: `python transcribe_pattern.py --language thai --translate`
- Generate Fabric response from transcription: `python transcribe_pattern.py --language english --model base`%                            
