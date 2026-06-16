import json
import glob
import os
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

SAVE_DIR = "./manual-evaluations/parameter-extraction"
PLOTS_SAVE_DIR = "./manual-evaluations/parameter-extraction/plots"

eval_files = glob.glob(os.path.join(SAVE_DIR, "manual_eval_*.json"))

print(f"Found {len(eval_files)} evaluation files.")

models = {}

def normalize(label):
    if label is None:
        return "unknown"
    label = label.lower().strip()
    if label == "y":
        return "correct"
    if label == "partial":
        return "partial"
    if label == "n":
        return "wrong"
    return "unknown"


for fpath in eval_files:
    fname = os.path.basename(fpath)

    core = fname.replace("manual_eval_", "").replace(".json", "")
    exp_name, diary = core.rsplit("_", 1)

    if "-experiment" in exp_name:
        model = exp_name.split("-experiment")[0]
    else:
        model = "deepseek-r1-8b"

    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    manual = data["manual_results"]
    metrics = data["metrics"]

    if model not in models:
        models[model] = {
            "total_fields": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "per_diary": [],
            "per_field": {}  # NEW
        }

    correct = metrics["correct"]
    partial = metrics["partial"]
    wrong = metrics["wrong"]
    total = correct + partial + wrong

    m = models[model]
    m["total_fields"] += total
    m["correct"] += correct
    m["partial"] += partial
    m["wrong"] += wrong

    m["per_diary"].append({
        "diary": diary,
        "correct": correct,
        "partial": partial,
        "wrong": wrong,
        "human_accuracy": metrics["human_accuracy"],
        "partial_score": metrics["partial_score"]
    })

    for field, label in manual.items():
        norm = normalize(label)

        if field not in m["per_field"]:
            m["per_field"][field] = {
                "correct": 0,
                "partial": 0,
                "wrong": 0,
                "total": 0
            }

        fstats = m["per_field"][field]

        if norm == "correct":
            fstats["correct"] += 1
        elif norm == "partial":
            fstats["partial"] += 1
        elif norm == "wrong":
            fstats["wrong"] += 1

        if norm in ["correct", "partial", "wrong"]:
            fstats["total"] += 1


for model, agg in models.items():
    total_fields = agg["total_fields"]
    correct = agg["correct"]
    partial = agg["partial"]
    wrong = agg["wrong"]

    agg["global_accuracy"] = correct / total_fields * 100 if total_fields else 0.0
    agg["global_partial_score"] = (correct + 0.5 * partial) / total_fields * 100 if total_fields else 0.0

    for field, stats in agg["per_field"].items():
        if stats["total"] > 0:
            stats["accuracy"] = stats["correct"] / stats["total"] * 100
            stats["partial_score"] = (stats["correct"] + 0.5 * stats["partial"]) / stats["total"] * 100
        else:
            stats["accuracy"] = 0.0
            stats["partial_score"] = 0.0

    print(f"\n=== RESULTS FOR MODEL: {model} ===")
    print(f"Total fields evaluated: {total_fields}")
    print(f"Correct: {correct}")
    print(f"Partial: {partial}")
    print(f"Wrong: {wrong}")
    print(f"Global accuracy: {agg['global_accuracy']:.2f}%")
    print(f"Global partial-aware score: {agg['global_partial_score']:.2f}%")

save_path = os.path.join(SAVE_DIR, "AGGREGATED_RESULTS_BY_MODEL.json")

with open(save_path, "w", encoding="utf-8") as f:
    json.dump(models, f, indent=4, ensure_ascii=False)

print(f"\nSaved aggregated results by model to {save_path}")

os.makedirs(PLOTS_SAVE_DIR, exist_ok=True)

rows = []
for model, agg in models.items():
    for field, stats in agg["per_field"].items():
        rows.append({
            "model": model,
            "field": field,
            "correct": stats["correct"],
            "partial": stats["partial"],
            "wrong": stats["wrong"],
            "accuracy": stats["accuracy"],
            "partial_score": stats["partial_score"]
        })

df = pd.DataFrame(rows)

plt.figure(figsize=(10,6))
sns.barplot(data=df, x="accuracy", y="field", hue="model", palette="viridis")
plt.title("Accuracy by patient schema field")
plt.xlabel("Accuracy (%)")
plt.ylabel("Field")
plt.tight_layout()

plt.savefig(f"{PLOTS_SAVE_DIR}/accuracy_by_field.png", dpi=300)

plt.show()

pivot = df.pivot(index="field", columns="model", values="partial_score")

plt.figure(figsize=(12,8))
sns.heatmap(pivot, annot=True, cmap="coolwarm", fmt=".1f")
plt.title("Partial-aware score by field and model")
plt.tight_layout()

plt.savefig(f"{PLOTS_SAVE_DIR}/partial_score_heatmap.png", dpi=300)

plt.show()

df_stacked = df[["field", "correct", "partial", "wrong"]].set_index("field")

df_stacked.plot(kind="bar", stacked=True, figsize=(12,6), colormap="tab20")
plt.title("Classification distribution by field")
plt.ylabel("Number of occurrences")
plt.tight_layout()

plt.savefig(f"{PLOTS_SAVE_DIR}/distribution_by_field.png", dpi=300)

plt.show()
