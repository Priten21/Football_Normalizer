import json
from mapper import map_api_to_json

failing_payload = {
    "event_key": 1746972,
    "event_date": "2026-04-01",
    "event_time": "06:30",
    "event_home_team": "Mexico",
    "home_team_key": 511,
    "event_away_team": "Belgium",
    "away_team_key": 6,
    "event_halftime_result": "1 - 0",
    "event_final_result": "1 - 1",
    "event_ft_result": "1 - 1",
    "event_penalty_result": "",
    "event_status": "Finished",
    "country_name": "intl",
    "event_live": 0,
    "week_day": "monday"
}

print("Running validation for Mexico vs Belgium...")
result = map_api_to_json(json.dumps(failing_payload))
data = result["data"]

print(f"Data ID: {data['data_id']} (Expected: 1746972)")
print(f"Start At: {data['start_at']} (Expected: 2026-04-01 06:30+00)")
print(f"Start Time: {data['start_time']} (Expected: 06:30)")
print(f"Local Score: {data['local_team_score']} (Expected: 1)")
print(f"Visitor Score: {data['visitor_team_score']} (Expected: 1)")
print(f"Result: {data['result']} (Expected: draw)")
print(f"Week Day: {data['week_day']} (Expected: monday)")

assert data['data_id'] == 1746972
assert "2026-04-01 06:30" in str(data['start_at'])
assert data['start_time'] == "06:30"
assert data['local_team_score'] == 1
assert data['visitor_team_score'] == 1
assert data['result'] == "draw"
assert data['week_day'] == "monday"

print("\nRunning validation for AllSports (No Model Support)...")
raw_payload = '{"event_key": 12345, "event_date": "2025-12-25", "event_time": "20:00", "event_home_team": "X", "event_away_team": "Y", "event_status": "Finished", "event_final_result": "3 - 0"}'
# Mocking a model failure where it returns "string" or None
result = map_api_to_json(raw_payload)
data = result["data"]
print(f"Recovered Start At: {data['start_at']}")
print(f"Recovered Start Time: {data['start_time']}")
assert data['start_at'] == "2025-12-25 20:00+00"
assert data['start_time'] == "20:00"
assert data['data_id'] == 12345
assert data['result'] == "local"

print("\nSUCCESS: All heuristics correctly recovered the data!")
