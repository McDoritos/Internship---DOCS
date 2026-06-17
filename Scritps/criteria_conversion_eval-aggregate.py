import json
import glob
import os
import json
import os
import matplotlib.pyplot as plt
import numpy as np

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

SAVE_DIR = "./manual-evaluations/criteria-conversion"
agg_path = os.path.join(SAVE_DIR, "AGGREGATED_RESULTS_BY_MODEL.json")

with open(agg_path, "r", encoding="utf-8") as f:
    models = json.load(f)

model_names = list(models.keys())
correct = [models[m]["correct"] for m in model_names]
partial = [models[m]["partial"] for m in model_names]
wrong = [models[m]["wrong"] for m in model_names]
acc = [models[m]["global_accuracy"] for m in model_names]
partial_score = [models[m]["global_partial_score"] for m in model_names]

x = np.arange(len(model_names))
width = 0.6

plt.figure(figsize=(8, 5))
p1 = plt.bar(x, correct, width, label="Correct", color="#4CAF50")
p2 = plt.bar(x, partial, width, bottom=correct, label="Partial", color="#FFC107")
bottom_wrong = [c + p for c, p in zip(correct, partial)]
p3 = plt.bar(x, wrong, width, bottom=bottom_wrong, label="Wrong", color="#F44336")

plt.xticks(x, model_names, rotation=20)
plt.ylabel("Number of criteria")
plt.title("Criteria conversion – distribution by model")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(SAVE_DIR, "criteria_conversion_stacked_counts.png"), dpi=300)

bar_width = 0.35
plt.figure(figsize=(8, 5))
plt.bar(x - bar_width/2, acc, bar_width, label="Accuracy (%)", color="#2196F3")
plt.bar(x + bar_width/2, partial_score, bar_width, label="Partial-aware score (%)", color="#9C27B0")

plt.xticks(x, model_names, rotation=20)
plt.ylabel("Score (%)")
plt.ylim(0, 105)
plt.title("Criteria conversion – global scores by model")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(SAVE_DIR, "criteria_conversion_global_scores.png"), dpi=300)

plt.show()
