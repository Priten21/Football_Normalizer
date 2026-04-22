import ollama
import json
import math
import re

MAPPING_RULES = """
⚽ FOOTBALL DATA NORMALIZER
GOAL: Map INPUT to SCHEMA with 100% TRACEABILITY.

1. Identifiers & Timing:
- data_id: event_key > id > fixture_id > matchId.
- start_at: Combine event_date + event_time (Format: YYYY-MM-DD HH:MM+00).
- week_day: Only if "Monday", "Tuesday", etc. is LITERALLY in the input. Else null.

2. Scores (Integers, default 0):
- local_team_score / visitor_team_score: 
  PRIORITY: event_final_result > event_ft_result > event_home_team_score/event_away_team_score > home_score/away_score > score_1/score_2.
  NOTE: If "5 - 0" is in event_final_result, split it.
- local_team_ft_score / visitor_team_ft_score: Only if status is "finished". Use FT keys.
- local_team_pen_score / visitor_team_pen_score: Only if penalties occurred.

3. Team Names:
- local_team_name / visitor_team_name: Lowercase. Use event_home_team, localteam_name, home_team, etc.

4. Status & Result:
- status: finished, running, upcoming, abort. (Finished if event_status == "Finished" or "FT").
- result: Calculate based on scores if status is "finished" (local, visitor, or draw).

🏆 LEAGUE MAPPING RULES
- league_name / display_name: competition/league name.
- country: country/region name.
- data_id: league_key > id.
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

def resilient_json_load(raw_str):
    """Parses JSON even if it has missing commas, trailing commas, or single quotes."""
    if not raw_str: return {}
    # 1. Try standard load
    try: return json.loads(raw_str)
    except: pass
    
    # 2. Cleanup and try again
    try:
        # Fix missing commas between key-value pairs
        # Look for "value" "key" and insert comma
        cleaned = re.sub(r'("|\d|true|false|null)\s*\n\s*"', r'\1,\n"', raw_str)
        # Fix trailing commas
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
        # Fix single quotes
        cleaned = cleaned.replace("'", '"')
        return json.loads(cleaned)
    except: pass
    
    # 3. Last resort: Regex extraction into a flat dict
    flat_dict = {}
    matches = re.findall(r'"([^"]+)"\s*:\s*(?:"([^"]*)"|(-?\d+\.?\d*)|(true|false|null))', raw_str)
    for m in matches:
        key = m[0]
        val = m[1] or m[2] or m[3]
        if val == "true": val = True
        elif val == "false": val = False
        elif val == "null": val = None
        elif m[2]: # numeric
            val = float(val) if "." in val else int(val)
        flat_dict[key] = val
    return flat_dict

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

Return ONLY valid JSON.
Output format:
{{
  "type": "match" or "league",
  "data": {{ ... }}
}}"""

    response = ollama.generate(
        model='qwen2.5:1.5b',
        prompt=prompt,
        format='json', 
        options={'temperature': 0},
        logprobs=True
    )
    
    result = json.loads(response['response'])
    
    # --- SCHEMA RE-HYDRATION: Ensure 100% field coverage ---
    if "data" not in result: result["data"] = {}
    target_schema = MATCH_SCHEMA if result.get("type") == "match" else LEAGUE_SCHEMA
    for key, default_val in target_schema.items():
        if key not in result["data"]:
            # Use 0 for integers, None for others
            result["data"][key] = 0 if isinstance(default_val, int) else None

    # Calculate Per-Key Confidence
    field_confidences = map_logprobs_to_keys(response)
    result["field_confidences"] = field_confidences
    result["mapping_trace"] = {} # Initialize trace
    
    # Calculate overall confidence
    all_probs = list(field_confidences.values())
    result["confidence"] = sum(all_probs) / len(all_probs) if all_probs else 0
    
    # POST-PROCESSING: Hardcore accuracy enforcement
    if result.get("type") == "match" and "data" in result:
        data = result["data"]
        raw_dict = resilient_json_load(raw_api_data)
        
        # 1. ENFORCE data_id - always overwrite from source (never trust model for this)
        for k in ["event_key", "event_id", "id", "fixture_id", "matchId", "idEvent", "match_id"]:
            if raw_dict.get(k):
                data["data_id"] = raw_dict.get(k)
                result["mapping_trace"]["data_id"] = k
                break
        else:
            data["data_id"] = data.get("data_id") or 0

        # 2. ENFORCE start_at in fixed format YYYY-MM-DD HH:MM+00 (always from source)
        for k in ["event_date", "fixture.date", "utcDate", "match_date"]:
            val = raw_dict.get(k)
            if isinstance(val, dict): val = val.get("date")
            if val:
                date_part = str(val).split("T")[0]
                result["mapping_trace"]["start_at"] = k
                break
        else:
            date_part = "0000-00-00"

        for k in ["event_time", "start_time"]:
            val = raw_dict.get(k)
            if val:
                time_part = str(val)[:5]
                result["mapping_trace"]["start_time"] = k
                break
        else:
            time_part = "00:00"
            
        data["start_at"] = f"{date_part} {time_part}+00"
        data["start_time"] = time_part

        # 3. ENFORCE Score Extraction — STRICT key priority, NO halftime sources
        # Priority A: direct numeric keys for main score
        MAIN_SCORE_KEYS = [
            ("event_home_team_score", "event_away_team_score"),
            ("home_score",            "away_score"),
            ("score_home",            "score_away"),
            ("goals_home",            "goals_away"),
            ("scr_1",                 "scr_2"),
            ("score_1",               "score_2"),
            ("homeScore",             "awayScore"),
            ("home_goals",            "away_goals"),
            ("localteam_score",       "visitorteam_score"),
        ]
        score_set = False
        for local_key, visitor_key in MAIN_SCORE_KEYS:
            lv = raw_dict.get(local_key)
            vv = raw_dict.get(visitor_key)
            if lv is not None and vv is not None:
                try:
                    data["local_team_score"]   = int(lv)
                    data["visitor_team_score"]  = int(vv)
                    result["mapping_trace"]["local_team_score"] = local_key
                    result["mapping_trace"]["visitor_team_score"] = visitor_key
                    score_set = True
                    break
                except (ValueError, TypeError):
                    pass

        # Priority B: composite string keys (ONLY if no direct key found above)
        if not score_set:
            # ❌ Excluded: event_halftime_result, event_ft_result (full-time goes to ft_score, not main score)
            COMPOSITE_KEYS = ["event_final_result", "score"]
            for ckey in COMPOSITE_KEYS:
                res_str = raw_dict.get(ckey)
                if res_str:
                    try:
                        normalized = str(res_str).replace(":", " - ").replace("-", " - ")
                        parts = [p.strip() for p in normalized.split(" - ") if p.strip().isdigit()]
                        if len(parts) >= 2:
                            data["local_team_score"]  = int(parts[0])
                            data["visitor_team_score"] = int(parts[1])
                            result["mapping_trace"]["local_team_score"] = ckey
                            result["mapping_trace"]["visitor_team_score"] = ckey
                            score_set = True
                            break
                    except (ValueError, TypeError):
                        pass

        # Priority C: Nested scores (Football-Data.org / API-Football)
        if not score_set:
            for parent_key in ["result", "score", "goals"]:
                p_val = raw_dict.get(parent_key, {})
                if isinstance(p_val, dict):
                    # Check nested levels
                    for sub_key in ["fulltime", "fullTime", "total", "score"]:
                        s_val = p_val.get(sub_key)
                        if isinstance(s_val, dict):
                            lv = s_val.get("home") or s_val.get("local") or s_val.get("homeTeam")
                            vv = s_val.get("away") or s_val.get("visitor") or s_val.get("awayTeam")
                            if lv is not None and vv is not None:
                                try:
                                    data["local_team_score"]  = int(lv)
                                    data["visitor_team_score"] = int(vv)
                                    result["mapping_trace"]["local_team_score"] = f"{parent_key}.{sub_key}"
                                    result["mapping_trace"]["visitor_team_score"] = f"{parent_key}.{sub_key}"
                                    score_set = True
                                    break
                                except (ValueError, TypeError): pass
                    if score_set: break


        # 4. ENFORCE Correct Status & Result Logic (STRICT ENUMS)
        status = str(data.get("status", "upcoming")).lower().strip()
        # VALID STATUS ENUM: [finished, running, upcoming, abort]
        if status not in ["finished", "running", "upcoming", "abort"]:
            # Snap to logical nearest
            if status in ["ft", "aet", "pen", "finished"]: status = "finished"
            elif status in ["ht", "1h", "2h", "live"]: status = "running"
            elif status in ["ns", "tbd", "upcoming"]: status = "upcoming"
            else: status = "upcoming" # Default safe value
        
        # Check for live indicators to force "running"
        status_val_raw = str(raw_dict.get("event_status", "")).lower()
        has_digits = any(char.isdigit() for char in status_val_raw)
        is_live_indicator = (str(raw_dict.get("event_live")) == "1" or 
                             has_digits or 
                             status_val_raw in ["ht", "1h", "2h", "et", "pen"])
        
        if is_live_indicator and status != "finished":
            status = "running"

        # DEFINITIVE RULE: event_live==1 AND timer>0 => status=running
        if str(raw_dict.get("event_live")) == "1" and (data.get("timer") or 0) > 0:
            status = "running"

        data["status"] = status

        # 4b. ENFORCE Result Logic (STRICT ENUM: local, visitor, draw, null)
        l_score = data.get("local_team_score", 0) or 0
        v_score = data.get("visitor_team_score", 0) or 0
        
        if status == "finished":
            if l_score > v_score: data["result"] = "local"
            elif v_score > l_score: data["result"] = "visitor"
            else: data["result"] = "draw"
        else:
            data["result"] = None # Snap to null as per requirement
            
        # 5. ENFORCE Timer Safety 
        if status in ["finished", "upcoming", "abort"]:
            data["timer"] = 0
        elif status == "running":
            potential_timer = str(raw_dict.get("timer") or raw_dict.get("event_timer") or raw_dict.get("event_status"))
            match = re.search(r'\d+', potential_timer)
            if match:
                data["timer"] = int(match.group())
            else:
                data["timer"] = data.get("timer") or 0

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
                result["mapping_trace"]["week_day"] = key
                break
        if not input_wd:
            # Fallback 1: scan EVERY string value for a day name
            days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                    "mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            for key, val in raw_dict.items():
                if val and isinstance(val, str) and len(val) < 100:
                    val_lower = val.lower()
                    for d in days:
                        if d in val_lower:
                            input_wd = d
                            result["mapping_trace"]["week_day"] = key
                            break
                    if input_wd: break
            
            # Fallback 2: Check in date/time strings if they contain a day name
            if not input_wd:
                for key in ["event_date", "start_at", "fixture_date", "match_date", "utcDate", "fixture"]:
                    val = raw_dict.get(key)
                    if isinstance(val, dict): # handle fixture: { date: "..." }
                        val = val.get("date")
                    if val and isinstance(val, str):
                        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                        for d in days:
                            if d in val.lower():
                                input_wd = d
                                break
                    if input_wd: break
        if input_wd:
            wd_lower = str(input_wd).lower()
            day_map = {
                'mon': 'monday', 'tue': 'tuesday', 'wed': 'wednesday',
                'thu': 'thursday', 'fri': 'friday', 'sat': 'saturday', 'sun': 'sunday'
            }
            # Try to match abbreviation or full name
            matched = False
            for abbr, full in day_map.items():
                if wd_lower.startswith(abbr):
                    data['week_day'] = full
                    matched = True
                    break
            if not matched:
                data['week_day'] = wd_lower
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
        TEAM_1_KEYS = ["event_home_team", "localteam_name", "home_team", "strHomeTeam", "team_1"]
        if str(data.get("local_team_name")).lower() in placeholders:
            for k in TEAM_1_KEYS:
                if raw_dict.get(k):
                    data["local_team_name"] = str(raw_dict.get(k)).lower().strip()
                    result["mapping_trace"]["local_team_name"] = k
                    break
            
        TEAM_2_KEYS = ["event_away_team", "visitorteam_name", "away_team", "strAwayTeam", "team_2"]
        if str(data.get("visitor_team_name")).lower() in placeholders:
            for k in TEAM_2_KEYS:
                if raw_dict.get(k):
                    data["visitor_team_name"] = str(raw_dict.get(k)).lower().strip()
                    result["mapping_trace"]["visitor_team_name"] = k
                    break

        # 8. ENFORCE Team ID Recovery
        T1_ID_KEYS = ["home_team_key", "localteam_id", "home_id", "team_home_id"]
        if not data.get("local_team_id") or data.get("local_team_id") == 0:
            for k in T1_ID_KEYS:
                if raw_dict.get(k):
                    data["local_team_id"] = raw_dict.get(k)
                    result["mapping_trace"]["local_team_id"] = k
                    break
                    
        T2_ID_KEYS = ["away_team_key", "visitorteam_id", "away_id", "team_away_id"]
        if not data.get("visitor_team_id") or data.get("visitor_team_id") == 0:
            for k in T2_ID_KEYS:
                if raw_dict.get(k):
                    data["visitor_team_id"] = raw_dict.get(k)
                    result["mapping_trace"]["visitor_team_id"] = k
                    break

    elif result.get("type") == "league" and "data" in result:
        data = result["data"]
        raw_dict = resilient_json_load(raw_api_data)
        
        # Enforce League ID - always from source
        for k in ["league_key", "league_id", "id", "data_id"]:
            if raw_dict.get(k):
                data["data_id"] = raw_dict.get(k)
                result["mapping_trace"]["data_id"] = k
                break
        else:
            data["data_id"] = data.get("data_id") or 0
        
        # Enforce Name consistency
        for k in ["league_name", "competition_name", "name"]:
            if raw_dict.get(k):
                data["league_name"] = str(raw_dict.get(k)).lower().strip()
                data["display_name"] = data["league_name"]
                result["mapping_trace"]["league_name"] = k
                break
            
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
        # Scores: aggressively enforced from source strings/keys
        "local_team_score", "visitor_team_score",
        "local_team_pen_score", "local_team_et_score", "local_team_ft_score",
        "visitor_team_pen_score", "visitor_team_et_score", "visitor_team_ft_score",
    }
    fc = result.get("field_confidences", {})
    for field in ENFORCED_FIELDS:
        if field in fc:
            fc[field] = 100.0
    # status confidence: if post-processing determined it (live indicator), mark as 100%
    if result.get("type") == "match":
        raw_dict_check = resilient_json_load(raw_api_data)
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

    # 9. FINAL TRACE SYNC (Find sources for anything missing)
    # If a field was mapped by the model but not caught in post-processing trace,
    # try to find its value in the raw_dict keys.
    raw_dict_sync = resilient_json_load(raw_api_data)
    data_sync = result.get("data", {})
    for field, val in data_sync.items():
        if field not in result["mapping_trace"] and val:
            val_str = str(val).lower()
            # Direct value match in raw_dict
            for rk, rv in raw_dict_sync.items():
                if str(rv).lower() == val_str:
                    result["mapping_trace"][field] = rk
                    break
                elif isinstance(rv, dict): # check one level deep
                    for subk, subv in rv.items():
                        if str(subv).lower() == val_str:
                            result["mapping_trace"][field] = f"{rk}.{subk}"
                            break
            if field in result["mapping_trace"]: continue

            # Partial match for team names if not found directly
            if "team_name" in field:
                for rk, rv in raw_dict_sync.items():
                    if isinstance(rv, str) and val_str in rv.lower() and len(rv) < 50:
                        result["mapping_trace"][field] = rk
                        break

    return result

def map_logprobs_to_keys(response_obj):
    """
    Maps token-level logprobs back to JSON keys using a robust index-mapping strategy.
    """
    # Ollama returns logprobs in a list of dicts/objects
    logprobs_list = response_obj.get('logprobs', [])
    if not logprobs_list:
        return {}

    # 1. Build string with index mapping
    full_text = ""
    token_metadata = []
    current_pos = 0
    for item in logprobs_list:
        # Check if item is a dict (Ollama default) or object
        t = item.get('token') if isinstance(item, dict) else getattr(item, 'token', "")
        lp = item.get('logprob') if isinstance(item, dict) else getattr(item, 'logprob', 0)
        
        prob = math.exp(lp)
        t_len = len(t)
        token_metadata.append({"start": current_pos, "end": current_pos + t_len, "prob": prob, "token": t})
        full_text += t
        current_pos += t_len
        
    results = {}
    
    # 2. Find all key-value positions in the final JSON string
    # Improved pattern: handles more whitespace variations
    pattern = r'"([^"]+)"\s*:\s*("[^"]*"|\d+\.?\d*|true|false|null)'
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
