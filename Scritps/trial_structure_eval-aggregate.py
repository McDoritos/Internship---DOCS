import json
import glob
import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

SAVE_DIR = "./manual-evaluations/trial-structure"
PLOTS_SAVE_DIR = "./manual-evaluations/trial-structure/plots"

eval_files = glob.glob(os.path.join(SAVE_DIR, "manual_eval_*.json"))

print(f"Found {len(eval_files)} evaluation files.")

models = {}

for fpath in eval_files:
    fname = os.path.basename(fpath)

    core = (
        fname.replace("structure_eval_", "")
             .replace("manual_eval_", "")   # REMOVE PREFIX
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
    total = correct + partial + wrong
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

os.makedirs(PLOTS_SAVE_DIR, exist_ok=True)

rows = []
for model, agg in models.items():
    rows.append({
        "model": model,
        "accuracy": agg["global_accuracy"],
        "partial_score": agg["global_partial_score"]
    })

df_global = pd.DataFrame(rows)

plt.figure(figsize=(8,5))
sns.barplot(data=df_global, x="accuracy", y="model", palette="viridis")
plt.title("Global accuracy by model (Trial Structure Identification)")
plt.xlabel("Accuracy (%)")
plt.ylabel("Model")
plt.tight_layout()

plt.savefig(f"{PLOTS_SAVE_DIR}/global_accuracy_by_model.png", dpi=300)
plt.show()

plt.figure(figsize=(8,5))
sns.barplot(data=df_global, x="partial_score", y="model", palette="magma")
plt.title("Partial-aware score by model (Trial Structure Identification)")
plt.xlabel("Partial-aware score (%)")
plt.ylabel("Model")
plt.tight_layout()

plt.savefig(f"{PLOTS_SAVE_DIR}/partial_score_by_model.png", dpi=300)
plt.show()

rows = []
for model, agg in models.items():
    for trial in agg["per_trial"]:
        rows.append({
            "model": model,
            "trial": trial["trial"],
            "accuracy": trial["human_accuracy"]
        })

df_trials = pd.DataFrame(rows)
pivot = df_trials.pivot(index="trial", columns="model", values="accuracy")

plt.figure(figsize=(12,8))
sns.heatmap(pivot, annot=True, cmap="coolwarm", fmt=".1f")
plt.title("Per-trial accuracy heatmap (Trial Structure Identification)")
plt.tight_layout()

plt.savefig(f"{PLOTS_SAVE_DIR}/per_trial_accuracy_heatmap.png", dpi=300)
plt.show()
