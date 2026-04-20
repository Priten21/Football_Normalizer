import ollama
import json

MAPPING_RULES = """
⚽ MATCH MAPPING RULES
CORE PRINCIPLE: INPUT SOURCE TRACEABILITY. The PROVIDED INPUT is your ONLY source of truth. 
- DO NOT invent or hallucinate IDs, scores, or names. 
- If data is missing from input, output null/0 per schema.
- All normalized strings must be lowercase.

1. Identifiers & Timing:
- data_id (number/string): Extracted strictly by priority (event_key > fixture.id > idEvent > matchId).
- start_at (string/null): Format "YYYY-MM-DD HH:MM+00". For AllSports, you MUST combine `event_date` + `event_time`. For others, extract from UTC/ISO fields.
- start_time (string/null): HH:MM extracted from input (event_time, strTime). 
- timer (integer): Minute from input `timer` or `status`. If missing, 0.
- week_day (string/null): Strictly from input payload. DO NOT calculate from date. If missing, output null.
- end_at & data_static_id: Always null.

2. Team Information:
- local_team_id (integer/null): Priority keys: [home_team_key, localteam_id, home_id, team_home_id].
- visitor_team_id (integer/null): Priority keys: [away_team_key, visitorteam_id, away_id, team_away_id].
- local_team_name (string/null): Priority keys: [event_home_team, localteam_name, home_team, strHomeTeam, team_1]. Must be lowercase.
- visitor_team_name (string/null): Priority keys: [event_away_team, visitorteam_name, away_team, strAwayTeam, team_2]. Must be lowercase.
- TRACEABILITY: Only extract names present in the input. Do not invent team names.

3. Scores (All integers, default to 0 if unknown):
- CRITICAL PRIORITY: Extract `local_team_score` and `visitor_team_score` using the most specific keys available (e.g., `event_home_team_score` and `event_away_team_score`). 
- STRING PARSING: If ONLY a composite string like `event_final_result` (e.g. "2 - 0") or `score` (e.g. "1-4") is present, you MUST split it. The first number is ALWAYS the local team score, and the second is ALWAYS the visitor team score.
- local_team_score / visitor_team_score: Current/Final main score.
- local_team_ft_score / visitor_team_ft_score: Full-time score (90') if known. Must be 0 for non-finished matches.
- local_team_et_score / visitor_team_et_score: Extra-time score if known, else 0.
- local_team_pen_score / visitor_team_pen_score: Penalty shootout score if known, else 0.

4. Status & Results:
- status (string, strictly enum): Must be exactly one of: upcoming, running, finished, abort.
  running: Match is live. Map to "running" if `event_live` is "1" or 1, if the timer is greater than zero, if the status string contains any digits (like "67", "18'", "min 23"), or for short codes like '1H', 'HT', 'PEN'.
  upcoming: Match has not started yet.
  finished: Match is fully completed. Map to "finished" only if the status states "Finished", "FT", or "AET".
  abort: Match is postponed, cancelled, suspended, abandoned, or awarded.
- status_text (string/null): The raw, lowercased status string from the input (e.g., "postponed", "ht").
- result (string, strictly enum): Must be exactly one of: none, local, visitor, draw.
  Strict logic to determine result:
  * If status is NOT 'finished', result MUST BE "none".
  * If status IS 'finished', result CANNOT BE "none". You MUST calculate it securely:
      If local_team_score > visitor_team_score, result = "local"
      If local_team_score < visitor_team_score, result = "visitor"
      If local_team_score == visitor_team_score, result = "draw"
- Strict Rule: Never copy a score string text (like "3-0") into the result field.
- EXTREME STRICTNESS: If status is "finished", generating `"result": "none"` is a FATAL ERROR. You MUST perform the score comparison to output "local", "visitor", or "draw".

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
    prompt = f"""<SYSTEM_ROUTINE_ENFORCEMENT>
YOU ARE A DETERMINISTIC, HIGH-FIDELITY DATA MAPPING ENGINE. 
CORE DIRECTIVE: THE INPUT DATA IS YOUR ONLY SOURCE OF TRUTH. 
1. DO NOT HALLUCINATE: If a piece of information (e.g., an ID, a score, or a name) is not present or clearly identifiable in the input, you MUST output the default value (null or 0) as specified in the rules.
2. NO INVENTIONS: Never guess IDs, timestamps, or scores based on context.
3. STRICT ADHERENCE: You must follow the mapping rules below with 100% mathematical precision.
</SYSTEM_ROUTINE_ENFORCEMENT>

--- MAPPING RULES ---
{MAPPING_RULES}

--- STRUCTURES ---
MATCH:
{json.dumps(MATCH_SCHEMA, indent=2)}

LEAGUE:
{json.dumps(LEAGUE_SCHEMA, indent=2)}

--- EXAMPLES ---
Input: {{"event_key": 101, "event_home_team": "Home Club", "event_away_team": "Away Club", "event_final_result": "2 - 1", "event_status": "Finished"}}
Output: {{"type": "match", "data": {{"data_id": 101, "local_team_name": "home club", "local_team_score": 2, "visitor_team_name": "away club", "visitor_team_score": 1, "status": "finished", "result": "local"}}}}

--- TARGET TASK ---
INPUT DATA FOR ANALYSIS:
{raw_api_data}

Return ONLY the valid JSON object exactly matching the chosen structure. Any field you cannot find in the INPUT DATA must be set to its default (null or 0). 
Output format:
{{
  "type": "match" or "league",
  "data": {{ <MAPPED KEYS> }}
}}"""

    response = ollama.generate(
        model='qwen2.5:1.5b',
        prompt=prompt,
        format='json', 
        options={'temperature': 0} 
    )
    
    result = json.loads(response['response'])
    
    # POST-PROCESSING: Hardcore accuracy enforcement
    if result.get("type") == "match" and "data" in result:
        data = result["data"]
        raw_dict = {}
        try:
            raw_dict = json.loads(raw_api_data)
        except: pass

        # 1. ENFORCE data_id if missing/0
        if not data.get("data_id") or data.get("data_id") == 0:
            data["data_id"] = raw_dict.get("event_key") or raw_dict.get("id") or 0

        # 2. ENFORCE Date & Time Recovery (Aggressive Sync)
        e_date = raw_dict.get("event_date") or raw_dict.get("fixture", {}).get("date") or raw_dict.get("utcDate") or raw_dict.get("match_date")
        e_time = raw_dict.get("event_time") or raw_dict.get("start_time") or ""
        
        if e_date:
            date_part = str(e_date).split(" ")[0].split("T")[0]
            time_part = str(e_time) if e_time else ("00:00" if "T" not in str(e_date) else str(e_date).split("T")[1][:5])
            canonical_start_at = f"{date_part} {time_part}+00"
            canonical_start_time = time_part[:5]

            # Overwrite if model hallucinated or returned placeholder
            if not data.get("start_at") or data.get("start_at") in ["string", None] or date_part not in str(data.get("start_at")):
                data["start_at"] = canonical_start_at
            
            if not data.get("start_time") or data.get("start_time") in ["string", None] or data.get("start_time") != canonical_start_time:
                data["start_time"] = canonical_start_time

        # 3. ENFORCE Score Extraction from result strings 
        # Only split if scores are 0 OR the result logic feels wrong
        res_str = raw_dict.get("event_final_result") or raw_dict.get("event_ft_result") or raw_dict.get("score") or raw_dict.get("result", {}).get("score", {}).get("fulltime")
        if res_str and any(sep in str(res_str) for sep in [" - ", ":", "-"]):
            try:
                # Normalize separator to " - "
                normalized = str(res_str).replace(":", " - ").replace("-", " - ")
                if " - " in normalized:
                    parts = [p.strip() for p in normalized.split(" - ") if p.strip().isdigit()]
                    if len(parts) >= 2:
                        # Use these scores as the ground truth if the model failed
                        data["local_team_score"] = int(parts[0])
                        data["visitor_team_score"] = int(parts[1])
            except: pass

        # 4. ENFORCE Correct Status & Result Logic (Mathematical Safeguard)
        status = data.get("status")
        # Check for live indicators even if model missed them
        status_val = str(raw_dict.get("event_status")).lower()
        has_digits = any(char.isdigit() for char in status_val)
        is_live_indicator = (str(raw_dict.get("event_live")) == "1" or 
                             has_digits or 
                             status_val in ["ht", "1h", "2h", "et", "pen"])
        
        if is_live_indicator and status != "finished":
            data["status"] = "running"
            status = "running"

        l_score = data.get("local_team_score", 0) or 0
        v_score = data.get("visitor_team_score", 0) or 0
        
        if status == "finished":
            if l_score > v_score: data["result"] = "local"
            elif v_score > l_score: data["result"] = "visitor"
            else: data["result"] = "draw"
        else:
            data["result"] = "none"

        # 5. ENFORCE Timer Safety 
        if status in ["finished", "upcoming", "abort"]:
            data["timer"] = 0
        elif status == "running":
            potential_timer = str(raw_dict.get("timer") or raw_dict.get("event_timer") or raw_dict.get("event_status"))
            # Extract first numeric sequence (e.g. "67'" -> 67, "45+2" -> 45)
            import re
            match = re.search(r'\d+', potential_timer)
            if match:
                data["timer"] = int(match.group())

        # 6. ENFORCE Week Day (Strictly from source or null)
        input_wd = raw_dict.get("week_day") or raw_dict.get("day") or raw_dict.get("strDay")
        if input_wd:
            data["week_day"] = str(input_wd).lower()
        else:
            data["week_day"] = None

        # 7. ENFORCE Team Name Recovery
        placeholders = ["team a", "team b", "home club", "away club", "string", None, ""]
        if str(data.get("local_team_name")).lower() in placeholders:
            name = (raw_dict.get("event_home_team") or 
                    raw_dict.get("localteam_name") or 
                    raw_dict.get("home_team") or 
                    raw_dict.get("strHomeTeam") or 
                    raw_dict.get("team_1"))
            if name: data["local_team_name"] = str(name).lower().strip()
            
        if str(data.get("visitor_team_name")).lower() in placeholders:
            name = (raw_dict.get("event_away_team") or 
                    raw_dict.get("visitorteam_name") or 
                    raw_dict.get("away_team") or 
                    raw_dict.get("strAwayTeam") or 
                    raw_dict.get("team_2"))
            if name: data["visitor_team_name"] = str(name).lower().strip()

        # 8. ENFORCE Team ID Recovery
        if not data.get("local_team_id") or data.get("local_team_id") == 0:
            data["local_team_id"] = raw_dict.get("home_team_key") or raw_dict.get("localteam_id") or 0
        if not data.get("visitor_team_id") or data.get("visitor_team_id") == 0:
            data["visitor_team_id"] = raw_dict.get("away_team_key") or raw_dict.get("visitorteam_id") or 0

    elif result.get("type") == "league" and "data" in result:
        data = result["data"]
        raw_dict = {}
        try:
            raw_dict = json.loads(raw_api_data)
        except: pass
        
        # Enforce League ID
        if not data.get("data_id") or data.get("data_id") == 0:
            data["data_id"] = raw_dict.get("league_key") or raw_dict.get("id") or 0
        
        # Enforce Name consistency
        if not data.get("league_name") or data.get("league_name") == "string":
            data["league_name"] = (raw_dict.get("league_name") or raw_dict.get("name") or "").lower()
        
        if not data.get("display_name") or data.get("display_name") in ["string", None]:
            data["display_name"] = data.get("league_name")
            
        if not data.get("country") or data.get("country") == "string":
            data["country"] = (raw_dict.get("country_name") or raw_dict.get("strCountry") or "").lower()
                
    return result

def assess_mapping_quality(mapped_result):
    """
    Analyzes the mapped JSON and buckets ALL fields into quality categories.
    """
    data = mapped_result.get("data", {})
    type_ = mapped_result.get("type")
    
    # Define schema fields to ensure 100% coverage
    match_fields = ["start_at", "end_at", "data_id", "data_static_id", "start_time", "timer", 
                    "local_team_id", "local_team_name", "local_team_pen_score", "local_team_score", 
                    "local_team_et_score", "local_team_ft_score", "visitor_team_id", "visitor_team_name", 
                    "visitor_team_pen_score", "visitor_team_score", "visitor_team_et_score", 
                    "visitor_team_ft_score", "status", "status_text", "result", "week_day"]
    
    league_fields = ["league_name", "display_name", "country", "date_start", "date_end", "data_id", "is_mixed"]

    buckets = {
        "perfect": [],
        "optimization": [],
        "critical": []
    }

    if type_ == "match":
        for field in match_fields:
            val = data.get(field)
            
            # --- CRITICAL (Bucket 3) ---
            is_critical = False
            if field == "data_id" and (not val or val == 0): is_critical = True
            if field == "local_team_name" and not val: is_critical = True
            if field == "visitor_team_name" and not val: is_critical = True
            if field == "status" and not val: is_critical = True
            if field == "result" and (val == "none" and data.get("status") == "finished"): is_critical = True
            
            if is_critical:
                buckets["critical"].append(field)
                continue

            # --- OPTIMIZATION (Bucket 2) ---
            is_warning = False
            if val is None and field not in ["end_at", "data_static_id"]: is_warning = True
            if field == "start_at" and not val: is_warning = True
            if field == "timer" and val == 0 and data.get("status") == "running": is_warning = True
            if field == "week_day" and not val: is_warning = True
            
            if is_warning:
                buckets["optimization"].append(field)
                continue
            
            # --- PERFECT (Bucket 1) ---
            buckets["perfect"].append(field)

    elif type_ == "league":
        for field in league_fields:
            val = data.get(field)
            if field in ["league_name", "data_id"] and not val:
                buckets["critical"].append(field)
            elif val is None and field not in ["date_start", "date_end"]:
                buckets["optimization"].append(field)
            else:
                buckets["perfect"].append(field)

    # Determine Final Status
    if buckets["critical"]:
        status = "Critical Errors Found"
        css_class = "review"
        confidence = 40
    elif buckets["optimization"]:
        status = "Needs Optimization"
        css_class = "okayish"
        confidence = 75
    else:
        status = "Perfectly Mapped"
        css_class = "perfect"
        confidence = 100

    return {
        "status": status,
        "css_class": css_class,
        "confidence": confidence,
        "buckets": buckets
    }

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
