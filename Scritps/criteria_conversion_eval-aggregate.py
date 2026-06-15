import json
import glob
import os

SAVE_DIR = "./manual-evaluations/criteria-conversion"

eval_files = glob.glob(os.path.join(SAVE_DIR, "manual_eval_*.json"))
eval_files += glob.glob(os.path.join("./manual-evaluations/criteria-conversion-human", "human_eval_*.json"))

print(f"Found {len(eval_files)} evaluation files.")

models = {}

def normalize_classification(label):
    if label is None:
        return "unknown"
    label = label.lower().strip()
    if "very_likely_correct" in label or "likely_correct" in label or label == "correct":
        return "correct"
    if "partial" in label:
        return "partial"
    if "likely_wrong" in label or "very_likely_wrong" in label or label == "wrong":
        return "wrong"
    return "unknown"


for fpath in eval_files:
    fname = os.path.basename(fpath)

    core = (
        fname.replace("manual_eval_", "")
            .replace("human_eval_", "")
            .replace(".json", "")
    )

    if "_trial-" in core:
        exp_name, trial = core.split("_trial-")
    else:
        exp_name = core
        trial = "unknown"

    if "-experiment" in exp_name:
        model = exp_name.split("-experiment")[0]
    else:
        model = exp_name

    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if model not in models:
        models[model] = {
            "total_fields": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "per_trial": {}
        }

    correct = partial = wrong = 0

    for entry in data:
        human_label = entry.get("human_classification", None)
        auto_label = entry.get("auto_classification", None)
        eval_obj = entry.get("evaluation", None)
        eval_label = None
        if isinstance(eval_obj, dict):
            eval_label = eval_obj.get("classification", None)

        if human_label is not None and human_label.strip() != "":
            label = human_label
        elif auto_label is not None and auto_label.strip() != "":
            label = auto_label
        else:
            label = eval_label

        norm = normalize_classification(label)

        if norm == "correct":
            correct += 1
        elif norm == "partial":
            partial += 1
        elif norm == "wrong":
            wrong += 1

    total = correct + partial + wrong

    m = models[model]
    m["total_fields"] += total
    m["correct"] += correct
    m["partial"] += partial
    m["wrong"] += wrong

    if trial not in m["per_trial"]:
        m["per_trial"][trial] = {
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "total": 0
        }

    t = m["per_trial"][trial]
    t["correct"] += correct
    t["partial"] += partial
    t["wrong"] += wrong
    t["total"] += total

for model, agg in models.items():
    total_fields = agg["total_fields"]
    correct = agg["correct"]
    partial = agg["partial"]
    wrong = agg["wrong"]

    global_accuracy = correct / total_fields * 100 if total_fields else 0.0
    global_partial_score = (correct + 0.5 * partial) / total_fields * 100 if total_fields else 0.0

    agg["global_accuracy"] = global_accuracy
    agg["global_partial_score"] = global_partial_score

    per_trial_list = []
    for trial_id, vals in agg["per_trial"].items():
        per_trial_list.append({
            "trial": trial_id,
            "correct": vals["correct"],
            "partial": vals["partial"],
            "wrong": vals["wrong"],
            "total": vals["total"]
        })
    agg["per_trial"] = per_trial_list

    print(f"\n=== RESULTS FOR MODEL: {model} ===")
    print(f"Total criteria evaluated: {total_fields}")
    print(f"Correct: {correct}")
    print(f"Partial: {partial}")
    print(f"Wrong: {wrong}")
    print(f"Global accuracy: {global_accuracy:.2f}%")
    print(f"Global partial-aware score: {global_partial_score:.2f}%")


save_path = os.path.join(SAVE_DIR, "AGGREGATED_RESULTS_BY_MODEL.json")

with open(save_path, "w", encoding="utf-8") as f:
    json.dump(models, f, indent=4, ensure_ascii=False)

print(f"\nSaved aggregated results by model to {save_path}")
