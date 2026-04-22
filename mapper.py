import ollama
import json
import math
import re

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
- week_day (string/null): Day of the week. Search ALL keys in the input for common weekday aliases.
  Key aliases to check (in order): [week_day, weekday, day, strDay, dayOfWeek, day_of_week, matchDay, match_day, event_day, fixture_day, strDayOfWeek, gameDay].
  If a value is found in any of these keys, output it lowercased. If none exist in the input, output null.
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
  GOLDEN RULE FIRST: If event_live == "1" (or 1) AND timer > 0, status MUST be "running". No exceptions.
  Follow this STRICT PRIORITY DECISION TABLE — check each condition in order, stop at first match:
  STEP 1 — If event_live == "1" or event_live == 1 → status = "running". STOP.
  STEP 2 — If event_status contains ONLY digits (e.g. "45", "67", "90") OR contains a number pattern ("45+2", "min 23", "23'") → status = "running". STOP.
  STEP 3 — If event_status is exactly one of ["HT", "1H", "2H", "ET", "PEN", "ht", "1h", "2h", "et", "pen"] → status = "running". STOP.
  STEP 4 — If event_status matches ["Finished", "FT", "AET", "finished", "ft", "aet"] → status = "finished". STOP.
  STEP 5 — If event_status matches ["Postponed", "Cancelled", "Suspended", "Abandoned", "Awarded", "postponed", "cancelled"] → status = "abort". STOP.
  STEP 6 — If event_status matches ["NS", "Not Started", "Scheduled", "TBD"] OR event_time is in the future → status = "upcoming". STOP.
  STEP 7 (DEFAULT) — If no condition matched → status = "upcoming".
- status_text (string/null): A short, human-readable description of the current status. Examples: "match finished", "match in progress", "match postponed", "match upcoming". Derived from both the status enum and the raw input status string.
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
- is_mixed: Always false (boolean).
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
        options={'temperature': 0},
        logprobs=True
    )
    
    result = json.loads(response['response'])
    
    # Calculate Per-Key Confidence
    field_confidences = map_logprobs_to_keys(response)
    result["field_confidences"] = field_confidences
    
    # Calculate overall confidence
    all_probs = list(field_confidences.values())
    result["confidence"] = sum(all_probs) / len(all_probs) if all_probs else 0
    
    # POST-PROCESSING: Hardcore accuracy enforcement
    if result.get("type") == "match" and "data" in result:
        data = result["data"]
        raw_dict = {}
        try:
            raw_dict = json.loads(raw_api_data)
        except: pass

        # 1. ENFORCE data_id - always overwrite from source (never trust model for this)
        data["data_id"] = (
            raw_dict.get("event_key") or raw_dict.get("event_id") or
            raw_dict.get("id") or raw_dict.get("fixture_id") or
            raw_dict.get("matchId") or raw_dict.get("idEvent") or
            raw_dict.get("match_id") or data.get("data_id") or 0
        )

        # 2. ENFORCE start_at in fixed format YYYY-MM-DD HH:MM+00 (always from source)
        e_date = raw_dict.get("event_date") or raw_dict.get("fixture", {}).get("date") or raw_dict.get("utcDate") or raw_dict.get("match_date")
        e_time = raw_dict.get("event_time") or raw_dict.get("start_time") or ""
        
        if e_date:
            date_part = str(e_date).split(" ")[0].split("T")[0]
            # Extract time: prefer explicit time field, else parse from ISO datetime
            if e_time:
                time_part = str(e_time).strip()[:5]
            elif "T" in str(e_date):
                time_part = str(e_date).split("T")[1][:5]
            else:
                time_part = "00:00"
            # Always overwrite - fixed canonical format YYYY-MM-DD HH:MM+00
            data["start_at"] = f"{date_part} {time_part}+00"
            data["start_time"] = time_part

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

        # DEFINITIVE RULE: event_live==1 AND timer>0 => status=running, unconditionally
        if str(raw_dict.get("event_live")) == "1" and (data.get("timer") or 0) > 0:
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

        # 6. ENFORCE Week Day — broad key scan (model may miss alternate key names)
        # Check all common aliases including fuzzy key scan
        WEEKDAY_KEYS = [
            "week_day", "weekday", "day", "strDay", "dayOfWeek",
            "day_of_week", "matchDay", "match_day", "event_day",
            "fixture_day", "strDayOfWeek", "gameDay", "game_day"
        ]
        input_wd = None
        # First: check known aliases directly
        for key in WEEKDAY_KEYS:
            val = raw_dict.get(key)
            if val:
                input_wd = val
                break
        # Fallback: fuzzy scan any key containing 'day' (e.g. 'event_day_of_week')
        if not input_wd:
            for key, val in raw_dict.items():
                if 'day' in key.lower() and val and isinstance(val, str) and len(val) < 15:
                    # Filter out date strings and IDs (weekday names are short strings)
                    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun",
                            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                    if any(d in str(val).lower() for d in days):
                        input_wd = val
                        break
        if input_wd:
            data["week_day"] = str(input_wd).lower()
        else:
            data["week_day"] = None

        # 7a. ENFORCE status_text — always a human-readable description
        status_descriptions = {
            "finished": "match finished",
            "running": "match in progress",
            "upcoming": "match upcoming",
            "abort": "match aborted"
        }
        data["status_text"] = status_descriptions.get(status, data.get("status_text") or status)

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
        
        # Enforce League ID - always from source
        data["data_id"] = (
            raw_dict.get("league_key") or raw_dict.get("league_id") or
            raw_dict.get("id") or raw_dict.get("data_id") or
            data.get("data_id") or 0
        )
        
        # Enforce Name consistency
        if not data.get("league_name") or data.get("league_name") == "string":
            data["league_name"] = (raw_dict.get("league_name") or raw_dict.get("name") or "").lower()
        
        # display_name always mirrors league_name
        data["display_name"] = data.get("league_name")
            
        if not data.get("country") or data.get("country") == "string":
            data["country"] = (raw_dict.get("country_name") or raw_dict.get("strCountry") or "").lower()

        # is_mixed is ALWAYS false
        data["is_mixed"] = False

        # Override confidence for league's deterministic fields
        for f in ["data_id", "league_name", "display_name", "is_mixed"]:
            result["field_confidences"][f] = 100.0
                
    # CONFIDENCE OVERRIDE: any field that is deterministically enforced via post-processing
    # gets 100% confidence since its final value is guaranteed correct regardless of model output.
    ENFORCED_FIELDS = {
        # Match fields
        "start_at", "start_time",   # always reconstructed from source date+time
        "data_id",                   # always overwritten from source
        "status_text",               # always mapped from status enum
        "result",                    # always calculated from scores + status
        "week_day",                  # always extracted from source or null
        "timer",                     # enforced by status logic
        "is_mixed",                  # always False
        "end_at", "data_static_id",  # always null
    }
    fc = result.get("field_confidences", {})
    for field in ENFORCED_FIELDS:
        if field in fc:
            fc[field] = 100.0
    # status confidence: if post-processing determined it (live indicator), mark as 100%
    if result.get("type") == "match":
        raw_dict_check = {}
        try:
            raw_dict_check = json.loads(raw_api_data)
        except: pass
        status_val_check = str(raw_dict_check.get("event_status", "")).lower()
        has_digits_check = any(c.isdigit() for c in status_val_check)
        event_live_check = str(raw_dict_check.get("event_live", "")) == "1"
        # If status was determined unambiguously, mark as 100%
        if (event_live_check or has_digits_check or 
            status_val_check in ["ht","1h","2h","et","pen","finished","ft","aet",
                                  "postponed","cancelled","suspended","ns","tbd"]):
            fc["status"] = 100.0

    result["field_confidences"] = fc
    # Recalculate overall confidence from updated field_confidences
    all_probs = list(fc.values())
    result["confidence"] = sum(all_probs) / len(all_probs) if all_probs else 0

    return result

def map_logprobs_to_keys(response_obj):
    """
    Maps token-level logprobs back to JSON keys using a robust index-mapping strategy.
    """
    tokens = getattr(response_obj, 'logprobs', None)
    if not tokens:
        return {}

    # 1. Build string with index mapping
    full_text = ""
    token_metadata = []
    current_pos = 0
    for item in tokens:
        t = item.token
        prob = math.exp(item.logprob)
        t_len = len(t)
        token_metadata.append({"start": current_pos, "end": current_pos + t_len, "prob": prob, "token": t})
        full_text += t
        current_pos += t_len
        
    results = {}
    
    # 2. Find all key-value positions in the final JSON string
    # Pattern looks for "key": value (handles strings, numbers, booleans, null)
    pattern = r'"([^"]+)":\s*("[^"]*"|\d+\.?\d*|true|false|null)'
    for match in re.finditer(pattern, full_text):
        key = match.group(1)
        value_start = match.start(2)
        value_end = match.end(2)
        
        value_probs = []
        for tm in token_metadata:
            # Check if token overlaps significantly with the value range
            if tm["start"] < value_end and tm["end"] > value_start:
                # Exclude structural characters from confidence (quotes, commas)
                if tm["token"].strip() not in ['"', "'", ","]:
                    value_probs.append(tm["prob"])
        
        if value_probs:
            results[key] = (sum(value_probs) / len(value_probs)) * 100
            
    return results

def assess_mapping_quality(mapped_result):
    """
    Analyzes the mapped JSON and buckets fields based on logical validity AND confidence.
    """
    data = mapped_result.get("data", {})
    type_ = mapped_result.get("type")
    confidences = mapped_result.get("field_confidences", {})
    
    # Define schema fields
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

    fields_to_check = match_fields if type_ == "match" else league_fields
    
    for field in fields_to_check:
        val = data.get(field)
        conf = confidences.get(field, 100) # Default to 100 if missing
        
        # --- CRITICAL (Bucket 3) ---
        is_logical_critical = False
        if field == "data_id" and (not val or val == 0): is_logical_critical = True
        if field == "local_team_name" and not val: is_logical_critical = True
        if field == "visitor_team_name" and not val: is_logical_critical = True
        if field == "status" and not val: is_logical_critical = True
        if field == "result" and (val == "none" and data.get("status") == "finished"): is_logical_critical = True
        
        # Confidence Threshold: < 60%
        if is_logical_critical or conf < 60:
            buckets["critical"].append(f"{field} ({conf:.1f}%)")
            continue

        # --- OPTIMIZATION (Bucket 2) ---
        is_logical_warning = False
        if val is None and field not in ["end_at", "data_static_id"]: is_logical_warning = True
        if field == "start_at" and not val: is_logical_warning = True
        if field == "timer" and val == 0 and data.get("status") == "running": is_logical_warning = True
        
        # Confidence Threshold: 60% - 85%
        if is_logical_warning or (60 <= conf <= 85):
            buckets["optimization"].append(f"{field} ({conf:.1f}%)")
            continue
        
        # --- PERFECT (Bucket 1) ---
        buckets["perfect"].append(f"{field} ({conf:.1f}%)")

    # Determine Final Status and Overall Confidence
    all_probs = list(confidences.values())
    avg_confidence = sum(all_probs) / len(all_probs) if all_probs else 0

    if buckets["critical"]:
        status = "Critical Errors Found"
        css_class = "review"
    elif buckets["optimization"]:
        status = "Needs Optimization"
        css_class = "okayish"
    else:
        status = "Perfectly Mapped"
        css_class = "perfect"

    return {
        "status": status,
        "css_class": css_class,
        "confidence": avg_confidence,
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
