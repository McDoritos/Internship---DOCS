import json
import glob
import os

SAVE_DIR = "./manual-evaluations/patient-matching/"

eval_files = glob.glob(os.path.join(SAVE_DIR, "manual_eval_*.json"))

print(f"Found {len(eval_files)} evaluation files.")

models = {}

for fpath in eval_files:
    fname = os.path.basename(fpath)

    # Remove prefix and suffix
    core = fname.replace("manual_eval_", "").replace(".json", "")

    # Split into model + patient
    # Example: gpt4o-experiment-1_patient-3
    if "_patient-" in core:
        exp_name, patient = core.split("_patient-")
    else:
        exp_name = core
        patient = "unknown"

    # Extract model name (before "-experiment")
    if "-experiment" in exp_name:
        model = exp_name.split("-experiment")[0]
    else:
        model = exp_name

    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    metrics = data["metrics"]
    correct = metrics["correct"]
    partial = metrics["partial"]
    wrong = metrics["wrong"]
    total = metrics["total"]

    if model not in models:
        models[model] = {
            "total_fields": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "per_patient": []
        }

    m = models[model]
    m["total_fields"] += total
    m["correct"] += correct
    m["partial"] += partial
    m["wrong"] += wrong

    m["per_patient"].append({
        "patient": patient,
        "correct": correct,
        "partial": partial,
        "wrong": wrong,
        "human_accuracy": metrics["human_accuracy"],
        "partial_score": metrics["partial_score"]
    })

# Compute global metrics
for model, agg in models.items():
    total_fields = agg["total_fields"]
    correct = agg["correct"]
    partial = agg["partial"]
    wrong = agg["wrong"]

    global_accuracy = correct / total_fields * 100 if total_fields else 0.0
    global_partial_score = (correct + 0.5 * partial) / total_fields * 100 if total_fields else 0.0

    agg["global_accuracy"] = global_accuracy
    agg["global_partial_score"] = global_partial_score

    print(f"\n=== RESULTS FOR MODEL: {model} ===")
    print(f"Total criteria evaluated: {total_fields}")
    print(f"Correct: {correct}")
    print(f"Partial: {partial}")
    print(f"Wrong: {wrong}")
    print(f"Global human accuracy: {global_accuracy:.2f}%")
    print(f"Global partial-aware score: {global_partial_score:.2f}%")

# Save aggregated results
save_path = os.path.join(SAVE_DIR, "AGGREGATED_RESULTS_BY_MODEL.json")

with open(save_path, "w", encoding="utf-8") as f:
    json.dump(models, f, indent=4, ensure_ascii=False)

print(f"\nSaved aggregated results by model to {save_path}")
