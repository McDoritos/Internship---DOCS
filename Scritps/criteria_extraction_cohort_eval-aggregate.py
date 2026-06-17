import json
import glob
import os
import matplotlib.pyplot as plt
import numpy as np

SAVE_DIR = "./manual-evaluations/cohort-assignment"
PLOTS_DIR = "./manual-evaluations/cohort-assignment/plots/"

os.makedirs(PLOTS_DIR, exist_ok=True)

eval_files = glob.glob(os.path.join(SAVE_DIR, "manual_eval_*.json"))

print(f"Found {len(eval_files)} evaluation files.")

models = {}

for fpath in eval_files:
    fname = os.path.basename(fpath)

    core = (
        fname.replace("cohort_eval_", "")
             .replace(".json", "")
    )

    if "_trial-" in core:
        exp_name, trial = core.split("_trial-")
    else:
        exp_name = core
        trial = "unknown"

    if exp_name.startswith("manual_eval_"):
        exp_name = exp_name[len("manual_eval_"):]

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
    total = metrics.get("total", correct + partial + wrong)
    human_accuracy = metrics.get("human_accuracy", 0.0)
    partial_score = metrics.get("partial_score", 0.0)

    if model not in models:
        models[model] = {
            "total_fields": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "per_trial": {}
        }

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
            "total": 0,
            "human_accuracy": 0.0,
            "partial_score": 0.0
        }

    t = m["per_trial"][trial]
    t["correct"] += correct
    t["partial"] += partial
    t["wrong"] += wrong
    t["total"] += total
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
    print(f"Total evaluated: {total_fields}")
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
accuracies = [models[m]["global_accuracy"] for m in model_names]
partial_scores = [models[m]["global_partial_score"] for m in model_names]
correct_counts = [models[m]["correct"] for m in model_names]
partial_counts = [models[m]["partial"] for m in model_names]
wrong_counts = [models[m]["wrong"] for m in model_names]

x = np.arange(len(model_names))

plt.figure(figsize=(8, 5))
plt.bar(x, accuracies, color="#4C72B0")
plt.xticks(x, model_names, rotation=30, ha="right")
plt.ylabel("Global accuracy (%)")
plt.title("Cohort assignment – Global accuracy by model")
plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, "cohort_assignment_global_accuracy.png"), dpi=300)
plt.close()

plt.figure(figsize=(8, 5))
plt.bar(x, partial_scores, color="#55A868")
plt.xticks(x, model_names, rotation=30, ha="right")
plt.ylabel("Partial-aware score (%)")
plt.title("Cohort assignment – Partial-aware score by model")
plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, "cohort_assignment_partial_score.png"), dpi=300)
plt.close()

plt.figure(figsize=(8, 5))
bar_correct = plt.bar(x, correct_counts, color="#4C72B0", label="Correct")
bar_partial = plt.bar(x, partial_counts, bottom=correct_counts, color="#DD8452", label="Partial")
bottom_wrong = [c + p for c, p in zip(correct_counts, partial_counts)]
bar_wrong = plt.bar(x, wrong_counts, bottom=bottom_wrong, color="#C44E52", label="Wrong")

plt.xticks(x, model_names, rotation=30, ha="right")
plt.ylabel("Number of criteria")
plt.title("Cohort assignment – Outcome distribution by model")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, "cohort_assignment_outcome_distribution.png"), dpi=300)
plt.close()

print(f"Saved plots to {PLOTS_DIR}")
