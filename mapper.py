import ollama
import json

MAPPING_RULES = """
⚽ MATCH MAPPING RULES
The output for a match must be exactly 22 keys. Missing or unknown fields must be null (except for numeric score/timer fields which default to 0). All output strings must be lowercase.

1. Identifiers & Timing:
- data_id (number/string): Extracted by priority (event_key > fixture.id > idEvent > data.id > matchId > id > match_id). Numeric strings are converted to integers.
- start_at (string/null): Format "YYYY-MM-DD HH:MM+00". Prefers UTC fields (utcDate, fixture.date). For AllSports, combines event_date + event_time.
- start_time (string/null): HH:MM extracted from input (event_time, strTime) or inferred from ISO datetime.
- timer (integer): Match minute. If status != running, timer is 0. If running, extracted by priority (timer > AllSports event_status > API-Football fixture.status.elapsed > SportMonks time.minute). Never inferred from words like "half time" or score strings.
- week_day (string/null): Extracted strictly from input fields (e.g., week_day, day_of_week), lowercased. Never inferred from the date.
- end_at & data_static_id: Always null.

2. Team Information:
- local_team_id / visitor_team_id (integer/null): Extracted via prioritized keys from respective providers.
- local_team_name / visitor_team_name (string/null): Put in lowercase, from the best-available team name field.

3. Scores (All integers, default to 0 if unknown):
- CRITICAL STRING PARSING: If you see a field like `event_final_result` containing "A - B" (e.g. "2 - 0"), you MUST extract the first number (A) as `local_team_score` and the second number (B) as `visitor_team_score`.
- local_team_score / visitor_team_score: Current/Final main score.
- local_team_ft_score / visitor_team_ft_score: Full-time score (90') if known. Must be 0 for non-finished matches.
- local_team_et_score / visitor_team_et_score: Extra-time score if known, else 0.
- local_team_pen_score / visitor_team_pen_score: Penalty shootout score if known, else 0.

4. Status & Results:
- status (string, strictly enum): Must be exactly one of: upcoming, running, finished, abort.
  running: Match is live. Map to "running" if `event_live` is "1" or 1, if the timer is greater than zero, if the status is digits-only (like "18" or "23"), or for short codes like '1H', 'HT', 'PEN'.
  upcoming: Match has not started yet.
  finished: Match is fully completed. Map to "finished" only if the status states "Finished", "FT", or "AET".
  abort: Match is postponed, cancelled, suspended, abandoned, or awarded.
- status_text (string/null): The raw, lowercased status string from the input (e.g., "postponed", "ht").
- result (string, strictly enum): Must be exactly one of: none, local, visitor, draw.
  Strict logic to determine result:
  * If status is NOT 'finished', result MUST BE "none".
  * If status IS 'finished':
      If local_team_score > visitor_team_score, result = "local"
      If local_team_score < visitor_team_score, result = "visitor"
      If local_team_score == visitor_team_score, result = "draw"
- Strict Rule: Never copy a score string text (like "3-0") into the result field.

🏆 LEAGUE MAPPING RULES
The output for a league must be exactly 7 keys.
- league_name (string/null): Lowercased league/competition name from input.
- display_name (string/null): Same as league_name unless a separate display field exists.
- country (string/null): Lowercased country/area/region name from input string fields (country_name, strCountry). Never mapped from numeric keys.
- data_id (number/string): Unique league identifier, extracted by priority (league_key > league.id > competition.id, etc.).
- date_start & date_end: Always null.
- is_mixed: Always false.
"""

MATCH_SCHEMA = {
  "start_at": "string",
  "end_at": None,
  "data_id": 0,
  "data_static_id": None,
  "start_time": "string",
  "timer": 0,
  "local_team_id": 0,
  "local_team_name": "string",
  "local_team_pen_score": 0,
  "local_team_score": 0,
  "local_team_et_score": 0,
  "local_team_ft_score": 0,
  "visitor_team_id": 0,
  "visitor_team_name": "string",
  "visitor_team_pen_score": 0,
  "visitor_team_score": 0,
  "visitor_team_et_score": 0,
  "visitor_team_ft_score": 0,
  "status": "string",
  "status_text": "string",
  "result": "string",
  "week_day": None
}

LEAGUE_SCHEMA = {
  "league_name": "string",
  "display_name": "string",
  "country": "string",
  "date_start": None,
  "date_end": None,
  "data_id": 0,
  "is_mixed": "False"
}

def map_api_to_json(raw_api_data):
    prompt = f"""You are a strict JSON data converter.
First, DETERMINE if the INPUT DATA is a football match (contains teams, scores, events) or a league (contains league_name, country).
Then, map the INPUT DATA to the exact STRUCTURE keys corresponding to your choice.
Finally, evaluate your confidence in your mapping from 0 to 100. Output a "confidence" dictionary alongside "type" and "data", containing percentage scores for "overall", "scores", "team_names", "result", and "status". Penalize confidence if data was missing or explicitly guessed.

--- MAPPING RULES ---
{MAPPING_RULES}

--- STRUCTURES ---
MATCH:
{json.dumps(MATCH_SCHEMA, indent=2)}

LEAGUE:
{json.dumps(LEAGUE_SCHEMA, indent=2)}

--- FULLY MAPPED EXAMPLES ---

Input: {{"event_key": 999123, "event_date": "2025-05-15", "event_time": "18:00", "home_team_key": 44, "event_home_team": "Lions", "away_team_key": 55, "event_away_team": "Tigers", "event_final_result": "2 - 1", "event_status": "Finished"}}
Output JSON:
{{
  "type": "match",
  "data": {{ "start_at": "2025-05-15 18:00+00", "end_at": null, "data_id": 999123, "data_static_id": null, "start_time": "18:00", "timer": 0, "local_team_id": 44, "local_team_name": "lions", "local_team_pen_score": 0, "local_team_score": 2, "local_team_et_score": 0, "local_team_ft_score": 0, "visitor_team_id": 55, "visitor_team_name": "tigers", "visitor_team_pen_score": 0, "visitor_team_score": 1, "visitor_team_et_score": 0, "visitor_team_ft_score": 0, "status": "finished", "status_text": "finished", "result": "local", "week_day": null }},
  "confidence": {{
    "overall": 98.0,
    "scores": 100.0,
    "team_names": 100.0,
    "result": 100.0,
    "status": 100.0
  }}
}}

Input: {{"league_key": 28, "league_name": "World Cup", "country_key": 8, "country_name": "Worldcup"}}
Output JSON:
{{
  "type": "league",
  "data": {{ "league_name": "world cup", "display_name": "world cup", "country": "worldcup", "date_start": null, "date_end": null, "data_id": 28, "is_mixed": "False" }},
  "confidence": {{
    "overall": 95.0,
    "scores": 0.0,
    "team_names": 0.0,
    "result": 0.0,
    "status": 0.0
  }}
}}

--- TARGET TASK ---
INPUT DATA:
{raw_api_data}

Return ONLY the valid JSON object exactly matching the chosen structure. Output format must be:
{{
  "type": "match" or "league",
  "data": {{ <MAPPED KEYS> }},
  "confidence": {{ <SCORES> }}
}}"""

    response = ollama.generate(
        model='qwen2.5:1.5b',
        prompt=prompt,
        format='json', 
        options={'temperature': 0} 
    )
    
    return json.loads(response['response'])

if __name__ == "__main__":
    # Test Match
    test_match_data = '{"team_1": "Arsenal", "team_2": "Chelsea", "scr_1": 2, "scr_2": 1}'
    print("Mapping Match Data...")
    mapped_match = map_api_to_json(test_match_data)
    print(json.dumps(mapped_match, indent=2))

    # Test League
    test_league_data = '{"name": "EPL", "location": "England", "id": 10}'
    print("\nMapping League Data...")
    mapped_league = map_api_to_json(test_league_data)
    print(json.dumps(mapped_league, indent=2))
