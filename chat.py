import ollama

def ask_football_question(question, mapped_data):
    system_context = f"""You are a helpful football knowledge assistant.
Your job is to answer questions using strictly the JSON data provided below. Do not guess information outside the JSON.

--- FOOTBALL TERMINOLOGY GUIDE ---
- 'local_team' fields ALWAYS represent the Home Team.
- 'visitor_team' fields ALWAYS represent the Away Team.
- 'local_team_score' / 'visitor_team_score' are the current or final goals scored by the Home and Away teams.
- 'result': 'local' means the Home team won, 'visitor' means the Away team won, 'none' means it's still running or upcoming.
- 'status': 'running' means it is Live. 'upcoming' means it hasn't started. 'finished' means the match is totally over.
- 'timer': Represents the current live minute of the match.

--- DATA ---
{mapped_data}
"""
    
    response = ollama.chat(
        model='qwen2.5:1.5b',
        messages=[
            {'role': 'system', 'content': system_context},
            {'role': 'user', 'content': question},
        ]
    )
    return response['message']['content']

# Example Usage:
# result = ask_football_question("Who won the match?", mapped_data)
# print(result)
