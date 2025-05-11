import subprocess
import json

class FabricService:
    def __init__(self, fabric_executable_path="fabric"):
        self.fabric_executable_path = fabric_executable_path

    def list_patterns(self):
        """
        Lists all available fabric patterns by running 'fabric -l'.
        Returns a list of pattern names or None if an error occurs.
        """
        try:
            process = subprocess.run(
                [self.fabric_executable_path, "-l"],
                capture_output=True,
                text=True,
                check=True
            )
            # Output is plain text, one pattern per line
            patterns_output = process.stdout.strip()
            if patterns_output:
                return [line for line in patterns_output.split('\n') if line] # Split by newline and remove empty lines
            else:
                return [] # Return an empty list if there's no output

        except subprocess.CalledProcessError as e:
            print(f"Error running fabric command: {e}")
            print(f"Stderr: {e.stderr}")
            return None
        except FileNotFoundError:
            print(f"Error: The fabric executable was not found at '{self.fabric_executable_path}'.")
            return None

    def run_pattern(self, pattern_name: str, text_input: str):
        """
        Runs a specific fabric pattern with the given text input using stdin.
        Returns the processed text or None if an error occurs.
        """
        try:
            # print(f"Attempting: echo \"{text_input}\" | fabric --pattern {pattern_name}") # Debug
            process = subprocess.run(
                [self.fabric_executable_path, "--pattern", pattern_name],
                input=text_input,
                capture_output=True,
                text=True,
                check=True # Re-enable check=True, as we expect this to work or fail clearly
            )
            return process.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Error running fabric pattern '{pattern_name}' with stdin: {e}")
            # Attempt to print more detailed error if API related based on recent findings
            if e.stderr:
                print(f"Stderr: {e.stderr.strip()}")
            if e.stdout: # Sometimes API errors might go to stdout before exiting
                print(f"Stdout: {e.stdout.strip()}")
            if "Anthropic API" in str(e.stderr) or "credit balance" in str(e.stderr) or \
               (e.stdout and ("Anthropic API" in str(e.stdout) or "credit balance" in str(e.stdout))):
                print("This error appears to be related to Anthropic API access or credit issues.")
            return None
        except FileNotFoundError:
            print(f"Error: The fabric executable was not found at '{self.fabric_executable_path}'.")
            return None
        except Exception as e:
            print(f"An unexpected error occurred in run_pattern: {e}")
            return None

if __name__ == '__main__':
    # This is for basic testing of the service
    service = FabricService()

    print("Testing list_patterns():")
    patterns = service.list_patterns()
    if patterns:
        print("Available patterns:")
        for p_name in patterns:
            print(f"- {p_name}")
        
        if patterns: # If there are patterns, test run_pattern with the first one
            first_pattern = patterns[0]
            sample_text = "This is a test sentence. How are you today?"
            print(f"\nTesting run_pattern() with pattern '{first_pattern}' and text: '{sample_text}'")
            output = service.run_pattern(first_pattern, sample_text)
            if output:
                print(f"Output:\n{output}")
            else:
                print("Failed to run pattern.")
    else:
        print("No patterns found or error listing patterns.") 