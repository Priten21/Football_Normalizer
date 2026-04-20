import json
from mapper import map_api_to_json
from chat import ask_football_question

def main():
    print("=== Football Data Mapper & Chat ===")
    print("Paste your raw API data below (press Enter on an empty line to finish):")
    
    lines = []
    while True:
        line = input()
        if not line.strip():
            break
        lines.append(line)
        
    raw_api_data = "\n".join(lines)
    
    if not raw_api_data.strip():
        print("No data provided. Exiting.")
        return

    print("\n[+] Mapping data with Qwen2.5:1.5b...")
    
    try:
        mapped_result = map_api_to_json(raw_api_data)
        classification = mapped_result.get("type", "unknown")
        data_object = mapped_result.get("data", {})
        
        print(f"\n[+] Successfully mapped as: {classification.upper()}")
        print(json.dumps(data_object, indent=2))
        
    except Exception as e:
        print(f"Error during mapping: {e}")
        return

    print("\n=== Chat Interface ===")
    print("You can now ask questions about the mapped data.")
    print("Type 'exit' or 'quit' to stop.")
    
    while True:
        question = input("\nUser: ")
        if question.lower().strip() in ['exit', 'quit']:
            break
            
        if not question.strip():
            continue
            
        print("Model: (thinking...)")
        try:
            answer = ask_football_question(question, json.dumps(mapped_result))
            print(f"Model: {answer}")
        except Exception as e:
            print(f"Error chatting with model: {e}")

if __name__ == "__main__":
    main()
