    #import some modules
import os
import json
    #Basic info
print("Current Working Directory:", os.getcwd())
print("Hello, World!")
    # Asks name and greets the user, and save the info in a json file
Name = input("What is your name? ")
print("Hello, " + Name + "! Welcome to Vaini.")
with open("user_info.json", "w") as f:
    json.dump({"name": Name}, f, ensure_ascii=False, indent=2)
    #now the program will actaully start it will use the any input to send to the AI and get a response
def main():
    prompt = input("")
    if prompt != prompt:
        print("You said: " + prompt)
        # Here you can add code to send the prompt to an AI model and get a response
        # For example, you could use OpenAI's API or any other AI service
        # response = ai_model.get_response(prompt)
        # print("AI Response: " + response)
if __name__ == "__main__":
    main()