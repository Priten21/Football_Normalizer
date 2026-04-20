import json
import os
import sys
from mapper import map_api_to_json

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"

def compare_objects(expected, actual, raw_input=None):
    """
    Compares two objects field by field and returns a dict of results.
    Includes strict logic validation if raw_input is provided.
    """
    metrics = {"total": 0, "correct": 0, "errors": []}
    
    # 1. Field-by-field comparison
    for key, expected_val in expected.items():
        metrics["total"] += 1
        actual_val = actual.get(key)
        
        # Normalize comparison (handling string/int variations if necessary)
        if str(expected_val).lower() == str(actual_val).lower():
            metrics["correct"] += 1
        else:
            metrics["errors"].append({
                "field": key,
                "expected": expected_val,
                "actual": actual_val
            })
            
    # 2. Strict Logic Validation
    if raw_input:
        event_live = str(raw_input.get("event_live", "0"))
        event_status = str(raw_input.get("event_status", ""))
        
        status = actual.get("status")
        timer = actual.get("timer", 0) or 0
        result = actual.get("result")

        # Determine if it SHOULD be live
        should_be_live = (event_live == "1") or any(c.isdigit() for c in event_status) or event_status.lower() in ["ht", "1h", "2h", "et", "pen"]
        
        # Exclude "Finished" strings from live detection if they contain "digits" that aren't timers
        # But per mapping rules, digits in status almost always mean running.
        if event_status.lower() in ["finished", "ft", "aet"]:
            should_be_live = False

        if should_be_live:
            if status != "running":
                metrics["total"] += 1
                metrics["errors"].append({"field": "STRICT_LOGIC", "expected": "running", "actual": status})
            if timer == 0:
                metrics["total"] += 1
                metrics["errors"].append({"field": "STRICT_LOGIC", "expected": "timer > 0", "actual": "0"})
            if result != "none":
                metrics["total"] += 1
                metrics["errors"].append({"field": "STRICT_LOGIC", "expected": "none", "actual": result})
            
    return metrics

def run_evaluation():
    test_cases_path = os.path.join("tests", "test_cases.json")
    if not os.path.exists(test_cases_path):
        return {"error": f"Test cases file not found at {test_cases_path}"}

    with open(test_cases_path, "r") as f:
        test_cases = json.load(f)

    case_summaries = []
    field_stats = {} # {field_name: {total: X, correct: Y}}
    global_total_fields = 0
    global_correct_fields = 0
    
    for case in test_cases:
        try:
            # Execute Mapper
            raw_input_str = json.dumps(case["input"])
            mapped_result = map_api_to_json(raw_input_str)
            
            actual_data = mapped_result.get("data", {})
            metrics = compare_objects(case["expected"], actual_data, raw_input=case["input"])
            
            # Field-level stats tracking
            for key, expected_val in case["expected"].items():
                if key not in field_stats:
                    field_stats[key] = {"total": 0, "correct": 0}
                field_stats[key]["total"] += 1
                actual_val = actual_data.get(key)
                if str(expected_val).lower() == str(actual_val).lower():
                    field_stats[key]["correct"] += 1
            
            global_total_fields += metrics["total"]
            global_correct_fields += metrics["correct"]
            
            case_passed = metrics["total"] == metrics["correct"]
            case_summaries.append({
                "id": case["id"],
                "passed": case_passed,
                "accuracy": (metrics["correct"] / metrics["total"]) * 100,
                "errors": metrics["errors"]
            })
                
        except Exception as e:
            case_summaries.append({
                "id": case["id"],
                "passed": False,
                "accuracy": 0,
                "errors": [{"field": "SYSTEM", "expected": "success", "actual": str(e)}]
            })

    # Prepare final report object
    field_accuracy = {k: (v["correct"] / v["total"]) * 100 for k, v in field_stats.items()}
    passed_count = sum(1 for c in case_summaries if c["passed"])
    
    return {
        "overall_accuracy": (global_correct_fields / global_total_fields) * 100 if global_total_fields > 0 else 0,
        "case_pass_rate": (passed_count / len(test_cases)) * 100 if test_cases else 0,
        "total_cases": len(test_cases),
        "passed_cases": passed_count,
        "field_accuracy": field_accuracy,
        "case_details": case_summaries
    }

if __name__ == "__main__":
    report = run_evaluation()
    if "error" in report:
        print(f"{RED}{report['error']}{RESET}")
        sys.exit(1)
        
    print(f"{BLUE}Starting Accuracy Audit ({report['total_cases']} cases)...{RESET}\n")
    
    for case in report["case_details"]:
        color = GREEN if case["passed"] else RED
        status = "PASS" if case["passed"] else "FAIL"
        print(f"Running Case: {case['id']}... {color}{status}{RESET} ({case['accuracy']:.1f}%)")
        for err in case["errors"]:
            print(f"    - {RED}[Field Error]{RESET} {err['field']}: Expected '{err['expected']}', Got '{err['actual']}'")

    print(f"\n{BLUE}{'='*40}{RESET}")
    print(f"{BLUE}FINAL AUDIT SUMMARY{RESET}")
    print(f"{'='*40}")
    print(f"Total Cases: {report['total_cases']}")
    print(f"Passed Cases: {report['passed_cases']} ({report['case_pass_rate']:.1f}%)")
    print(f"Global Field-Level Accuracy: {report['overall_accuracy']:.2f}%")
    
    if report['passed_cases'] < report['total_cases']:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    run_evaluation()
