import yaml
from Python_scripts.standard_fact_checker.sel_search import *
from huggingface_hub import InferenceClient
import os

# temorary function to test the model on tool use 
def get_current_temperature(location: str) -> float:
    """
    Get the current temperature at a location.
    
    Args:
        location: The location to get the temperature for, in the format "City, Country"
    Returns:
        The current temperature at the specified location in the specified units, as a float.
    """
    return 22

def load_config(filename='config.yaml'):
    with open(filename, 'r') as f:
        config = yaml.safe_load(f)
    return config

config = load_config()
max_searches = config['max_searches']
model_name = config['model_name']
model_id = config['model_id']
tools = config['tools']

standard_system_prompt = config['standard_system_prompt_1']
if max_searches == 1:
    standard_system_prompt += "you can use the function at least and only once. "
else:
    standard_system_prompt += "you can use the function from one up to "+str(max_searches)+" times. "
standard_system_prompt += config['standard_system_prompt_2']

try:
    API_TOKEN = os.getenv("HF_TOKEN")
except:
    print("Please set the HF_TOKEN environment variable to your Hugging Face API token.")
    exit(1)

def load_model_and_generate_output(user_input):
    """
    Uses the huggingface API to load the model and make it assess the claim.
    
    Args:
        user_input: A dictionary containing the user's input, with the keys 'claim' and 'date'.
    Returns:
        The model's final assessment of the claim as a string. The search results are also printed.
    """
    messages = [
         {"role": "system", "content": standard_system_prompt},
         {"role": "user", "content": "Claim: "+user_input["claim"]+". Date:"+user_input["date"]}
    ]

    # Load the model from the Hugging Face Hub
    client = InferenceClient(model=model_id, token=API_TOKEN)
    response = client.chat_completion(messages=messages,tools=tools,tool_choice="auto",max_tokens=1000)
    response = response.choices[0].message

    # while the model asks for a tool, get the tool result and continue
    while response.tool_calls != None: 
        query = response.tool_calls[0].function.arguments["query"]
        search_results = google_search(query, date=user_input["date"])
        tool_call = {"name": "google_search", "parameters": {"query": query}}
        print("Search Results:", search_results)
        messages.append({"role": "assistant", "tool_calls": [{"type": "function", "function": tool_call}]})
        messages.append({"role": "tool", "name": "google_search", "content": search_results})
        response = client.chat_completion(messages=messages,tools=tools,tool_choice="auto",max_tokens=1000)

    return response

'''def load_model_and_generate_output(user_input):
    messages = [
        {"role": "system", "content": "You are a bot that responds to weather queries."},
        {"role": "user", "content": "Hey, what's the temperature in Paris right now?"}
    ]
    tool_call = {"name": "get_current_temperature", "arguments": {"location": "Paris, France"}}
    messages.append({"role": "assistant", "tool_calls": [{"type": "function", "function": tool_call}]})
    messages.append({"role": "tool", "name": "get_current_temperature", "content": str(get_current_temperature("Paris, France"))})

    # Load the model from the Hugging Face Hub
    client = InferenceClient(model=model_id, token=API_TOKEN)
    response = client.chat_completion(messages=messages,max_tokens=100,tools=tools)
    #response = response.choices[0].message
    return response'''


def main():
    print("Welcome to the Fact Checker! The language model "+model_name+" will verify your claim with the help of google search results.")
    # Get input from the user
    claim = input("Enter the claim to fact-check: ")
    date = input("Enter the date of the claim (optional): ")
    user_input = {"claim": claim, "date": date}
    # Generate output from the model
    output = load_model_and_generate_output(user_input)
    # Print the model's output
    print("Model Output:\n" + str(output))

if __name__ == "__main__":
    main()