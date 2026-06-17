import json
import glob
import os
import matplotlib.pyplot as plt
import numpy as np

SAVE_DIR = "./manual-evaluations/criteria-extraction"
PLOTS_DIR = "./manual-evaluations/criteria-extraction/plots/"

os.makedirs(PLOTS_DIR, exist_ok=True)

eval_files = glob.glob(os.path.join(SAVE_DIR, "manual_eval_*.json"))

print(f"Found {len(eval_files)} evaluation files.")

models = {}

for fpath in eval_files:
    fname = os.path.basename(fpath)

    core = (
        fname.replace("extraction_eval_", "")
             .replace("manual_eval_", "")
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

    metrics = data.get("metrics", {})

    correct = metrics.get("correct", 0)
    partial = metrics.get("partial", 0)
    wrong = metrics.get("wrong", 0)
    evaluated = metrics.get("evaluated", correct + partial + wrong)
    partial_score = metrics.get("partial_score", 0.0)
    human_accuracy = metrics.get("human_accuracy", 0.0)

    if model not in models:
        models[model] = {
            "total_fields": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "per_trial": {}
        }

    m = models[model]
    m["total_fields"] += evaluated
    m["correct"] += correct
    m["partial"] += partial
    m["wrong"] += wrong

    if trial not in m["per_trial"]:
        m["per_trial"][trial] = {
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "total": 0,
            "human_accuracy": 0.0,
            "partial_score": 0.0
        }

    t = m["per_trial"][trial]
    t["correct"] += correct
    t["partial"] += partial
    t["wrong"] += wrong
    t["total"] += evaluated
    t["human_accuracy"] = human_accuracy
    t["partial_score"] = partial_score

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
            "total": vals["total"],
            "human_accuracy": vals["human_accuracy"],
            "partial_score": vals["partial_score"]
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

model_names = list(models.keys())
correct = [models[m]["correct"] for m in model_names]
partial = [models[m]["partial"] for m in model_names]
wrong = [models[m]["wrong"] for m in model_names]
accuracy = [models[m]["global_accuracy"] for m in model_names]
partial_score = [models[m]["global_partial_score"] for m in model_names]

x = np.arange(len(model_names))
width = 0.25

plt.figure(figsize=(10, 6))
plt.bar(x, correct, width, label="Correct", color="#4CAF50")
plt.bar(x, partial, width, bottom=correct, label="Partial", color="#FFC107")
plt.bar(x, wrong, width, bottom=[c+p for c,p in zip(correct,partial)], label="Wrong", color="#F44336")
plt.xticks(x, model_names, rotation=20)
plt.ylabel("Number of criteria")
plt.title("Criteria extraction – per-model outcome distribution")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, "criteria_extraction_outcome_distribution.png"), dpi=300)
plt.close()

plt.figure(figsize=(10, 6))
plt.bar(x - width/2, accuracy, width, label="Accuracy (%)", color="#2196F3")
plt.bar(x + width/2, partial_score, width, label="Partial-aware score (%)", color="#9C27B0")
plt.xticks(x, model_names, rotation=20)
plt.ylabel("Score (%)")
plt.ylim(0, 100)
plt.title("Criteria extraction – global accuracy vs partial-aware score")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, "criteria_extraction_global_scores.png"), dpi=300)
plt.close()

print(f"Saved plots to {PLOTS_DIR}")
